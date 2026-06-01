from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Protocol

import httpx
from azure.core.credentials import TokenCredential
from pydantic import Field

from meeting_minutes_backend.errors import AppError
from meeting_minutes_backend.models import StrictModel

COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
NO_RETRY_STATUS_CODES = {400, 401, 422}
DEFAULT_BACKOFF_SECONDS = [2, 4, 8, 16, 32]


class TranscriptionRequest(StrictModel):
    audioUrl: str
    locale: str = "ja-JP"
    maxSpeakers: int = Field(default=8, ge=2, le=30)


class SpeechTranscriptionClient(Protocol):
    def transcribe_audio_url(self, request: TranscriptionRequest) -> dict[str, object]:
        pass


class FastTranscriptionClient(SpeechTranscriptionClient):
    def __init__(
        self,
        endpoint: str,
        credential: TokenCredential,
        api_version: str = "2025-10-15",
        http_client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        request_timeout_seconds: float = 120.0,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._credential = credential
        self._api_version = api_version
        self._http_client = http_client or httpx.Client(timeout=request_timeout_seconds)
        self._sleep = sleep
        self._request_timeout_seconds = request_timeout_seconds

    def transcribe_audio_url(self, request: TranscriptionRequest) -> dict[str, object]:
        last_status_code: int | None = None
        attempt_count = 0

        for attempt_count, backoff_seconds in enumerate([*DEFAULT_BACKOFF_SECONDS, None], start=1):
            token = self._credential.get_token(COGNITIVE_SERVICES_SCOPE).token
            try:
                response = self._http_client.post(
                    self._transcribe_url(),
                    headers={"Authorization": f"Bearer {token}"},
                    files={
                        "definition": (
                            None,
                            json.dumps(_definition(request)),
                            "application/json",
                        )
                    },
                    timeout=self._request_timeout_seconds,
                )
            except httpx.HTTPError as exc:
                if backoff_seconds is None:
                    raise _transcription_error(None, attempt_count) from exc
                self._sleep(backoff_seconds)
                continue

            last_status_code = response.status_code
            if response.status_code < 400:
                data = response.json()
                if not isinstance(data, dict):
                    raise _transcription_error(response.status_code, attempt_count)
                return data

            if (
                response.status_code in NO_RETRY_STATUS_CODES
                or response.status_code not in RETRY_STATUS_CODES
            ):
                raise _transcription_error(response.status_code, attempt_count)

            retry_after = _retry_after_seconds(response)
            if backoff_seconds is None:
                raise _transcription_error(response.status_code, attempt_count)
            self._sleep(retry_after if retry_after is not None else backoff_seconds)

        raise _transcription_error(last_status_code, attempt_count)

    def _transcribe_url(self) -> str:
        return (
            f"{self._endpoint}/speechtotext/transcriptions:transcribe"
            f"?api-version={self._api_version}"
        )


def _definition(request: TranscriptionRequest) -> dict[str, object]:
    return {
        "audioUrl": request.audioUrl,
        "locales": [request.locale],
        # Diarization with channels=[0,1] is unsupported. Keep channels omitted.
        "diarization": {
            "enabled": True,
            "maxSpeakers": request.maxSpeakers,
        },
    }


def _retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _transcription_error(status_code: int | None, attempt_count: int) -> AppError:
    details: dict[str, object] = {"attemptCount": attempt_count}
    if status_code is not None:
        details["statusCode"] = status_code
    return AppError(
        code="TRANSCRIPTION_FAILED",
        message="音声の文字起こしに失敗しました。",
        http_status=502 if status_code is None or status_code >= 500 else 400,
        details=details,
    )
