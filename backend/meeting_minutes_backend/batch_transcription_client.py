from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from azure.core.credentials import TokenCredential
from pydantic import Field

from meeting_minutes_backend.errors import AppError
from meeting_minutes_backend.models import StrictModel

COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
NO_RETRY_STATUS_CODES = {400, 401, 422}
DEFAULT_BACKOFF_SECONDS = [2, 4, 8, 16, 32]


class BatchTranscriptionRequest(StrictModel):
    audioUrl: str
    jobId: str
    locale: str = "ja-JP"
    maxSpeakers: int = Field(default=8, ge=2, le=30)


@dataclass(frozen=True)
class BatchTranscriptionResult:
    transcription_url: str
    status: str
    raw_result: dict[str, object] | None = None


class BatchTranscriptionClient:
    def __init__(
        self,
        endpoint: str,
        credential: TokenCredential,
        api_version: str = "2024-11-15",
        http_client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        request_timeout_seconds: float = 60.0,
    ) -> None:
        self._endpoint = endpoint.rstrip("/") + "/"
        self._credential = credential
        self._api_version = api_version
        self._http_client = http_client or httpx.Client(timeout=request_timeout_seconds)
        self._sleep = sleep
        self._request_timeout_seconds = request_timeout_seconds

    def start_transcription(self, request: BatchTranscriptionRequest) -> str:
        response = self._request_with_retries(
            "POST",
            self._transcriptions_url(),
            json={
                "displayName": f"minutes-{request.jobId}",
                "description": "Minutes Studio batch transcription fallback.",
                "locale": request.locale,
                "contentUrls": [request.audioUrl],
                "properties": {
                    "diarization": {"enabled": True, "maxSpeakers": request.maxSpeakers},
                    "wordLevelTimestampsEnabled": False,
                    "displayFormWordLevelTimestampsEnabled": False,
                    "timeToLiveHours": 24,
                },
            },
        )
        location = response.headers.get("Location") or response.headers.get("location")
        if location:
            return urljoin(self._endpoint, location)
        payload = _safe_json(response)
        if isinstance(payload, Mapping):
            self_url = payload.get("self")
            if isinstance(self_url, str) and self_url:
                return self_url
        raise _batch_error(response.status_code, "TranscriptionLocationMissing")

    def get_transcription(self, transcription_url: str) -> dict[str, object]:
        response = self._request_with_retries("GET", transcription_url)
        payload = _safe_json(response)
        if not isinstance(payload, dict):
            raise _batch_error(response.status_code, "TranscriptionStatusInvalid")
        return payload

    def get_result(self, transcription: dict[str, object]) -> BatchTranscriptionResult:
        status = str(transcription.get("status") or "Unknown")
        transcription_url = _required_string(transcription, "self")
        if status != "Succeeded":
            return BatchTranscriptionResult(transcription_url=transcription_url, status=status)

        files_url = _files_url(transcription)
        files = self._request_with_retries("GET", files_url)
        files_payload = _safe_json(files)
        result_url = _result_content_url(files_payload)
        result_response = self._request_with_retries("GET", result_url, auth=False)
        result_payload = _safe_json(result_response)
        if not isinstance(result_payload, dict):
            raise _batch_error(result_response.status_code, "TranscriptionResultInvalid")
        return BatchTranscriptionResult(
            transcription_url=transcription_url,
            status=status,
            raw_result=result_payload,
        )

    def _request_with_retries(
        self,
        method: str,
        url: str,
        *,
        auth: bool = True,
        json: object | None = None,
    ) -> httpx.Response:
        last_status_code: int | None = None
        attempt_count = 0
        for attempt_count, backoff_seconds in enumerate([*DEFAULT_BACKOFF_SECONDS, None], start=1):
            headers = {"Content-Type": "application/json"} if json is not None else {}
            if auth:
                token = self._credential.get_token(COGNITIVE_SERVICES_SCOPE).token
                headers["Authorization"] = f"Bearer {token}"
            try:
                response = self._http_client.request(
                    method,
                    url,
                    headers=headers,
                    json=json,
                    timeout=self._request_timeout_seconds,
                )
            except httpx.HTTPError as exc:
                if backoff_seconds is None:
                    raise _batch_error(None, "NetworkError", attempt_count) from exc
                self._sleep(backoff_seconds)
                continue

            last_status_code = response.status_code
            if response.status_code < 400:
                return response
            if (
                response.status_code in NO_RETRY_STATUS_CODES
                or response.status_code not in RETRY_STATUS_CODES
            ):
                raise _batch_error(response.status_code, None, attempt_count)
            if backoff_seconds is None:
                raise _batch_error(response.status_code, None, attempt_count)
            self._sleep(_retry_after_seconds(response) or backoff_seconds)

        raise _batch_error(last_status_code, None, attempt_count)

    def _transcriptions_url(self) -> str:
        return (
            f"{self._endpoint}speechtotext/transcriptions:submit"
            f"?api-version={self._api_version}"
        )


def _files_url(transcription: dict[str, object]) -> str:
    links = transcription.get("links")
    if isinstance(links, Mapping):
        files = links.get("files")
        if isinstance(files, str) and files:
            return files
    self_url = _required_string(transcription, "self")
    parsed = urlsplit(self_url)
    return urlunsplit(parsed._replace(path=parsed.path.rstrip("/") + "/files"))


def _result_content_url(files_payload: object) -> str:
    if isinstance(files_payload, Mapping):
        values = files_payload.get("values") or files_payload.get("files")
        if isinstance(values, list):
            for item in values:
                if not isinstance(item, Mapping):
                    continue
                kind = str(item.get("kind") or "").lower()
                if kind != "transcription":
                    continue
                links = item.get("links")
                if isinstance(links, Mapping):
                    content_url = links.get("contentUrl")
                    if isinstance(content_url, str) and content_url:
                        return content_url
                content_url = item.get("contentUrl")
                if isinstance(content_url, str) and content_url:
                    return content_url
    raise _batch_error(None, "TranscriptionResultUrlMissing")


def _safe_json(response: httpx.Response) -> object | None:
    try:
        return response.json()
    except ValueError:
        return None


def _required_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise _batch_error(None, f"{key}Missing")
    return value


def _retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _batch_error(
    status_code: int | None,
    reason: str | None,
    attempt_count: int | None = None,
) -> AppError:
    details: dict[str, object] = {}
    if status_code is not None:
        details["statusCode"] = status_code
    if reason:
        details["reason"] = reason
    if attempt_count is not None:
        details["attemptCount"] = attempt_count
    return AppError(
        code="BATCH_TRANSCRIPTION_FAILED",
        message="Batch Transcription による文字起こしに失敗しました。",
        http_status=502 if status_code is None or status_code >= 500 else 400,
        details=details,
    )
