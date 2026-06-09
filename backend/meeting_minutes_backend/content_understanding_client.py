from __future__ import annotations

import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx
from azure.core.credentials import TokenCredential

from meeting_minutes_backend.errors import AppError
from meeting_minutes_backend.telemetry import safe_log_payload

COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"
TERMINAL_STATUSES = {"Succeeded", "Failed", "Canceled"}
ANY_URL_PATTERN = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)


@dataclass(frozen=True)
class ContentUnderstandingRequest:
    content_url: str


class ContentUnderstandingClient:
    def __init__(
        self,
        endpoint: str,
        analyzer_id: str,
        credential: TokenCredential,
        api_version: str = "2025-11-01",
        http_client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        request_timeout_seconds: float = 60.0,
        poll_interval_seconds: float = 2.0,
        operation_timeout_seconds: float = 900.0,
    ) -> None:
        self._endpoint = endpoint.rstrip("/") + "/"
        self._analyzer_id = analyzer_id
        self._credential = credential
        self._api_version = api_version
        self._http_client = http_client or httpx.Client(timeout=request_timeout_seconds)
        self._sleep = sleep
        self._request_timeout_seconds = request_timeout_seconds
        self._poll_interval_seconds = poll_interval_seconds
        self._operation_timeout_seconds = operation_timeout_seconds

    def analyze_url(self, request: ContentUnderstandingRequest) -> dict[str, object]:
        operation_url = self.start_analysis(request)
        deadline = time.monotonic() + self._operation_timeout_seconds
        last_status: str | None = None
        while time.monotonic() <= deadline:
            result = self.get_result(operation_url)
            status = result.get("status")
            last_status = status if isinstance(status, str) else None
            if last_status in TERMINAL_STATUSES:
                if last_status == "Succeeded":
                    return result
                raise _content_understanding_error(None, last_status, result)
            self._sleep(self._poll_interval_seconds)
        raise _content_understanding_error(None, last_status or "TimedOut")

    def start_analysis(self, request: ContentUnderstandingRequest) -> str:
        token = self._credential.get_token(COGNITIVE_SERVICES_SCOPE).token
        response = self._http_client.post(
            self._analyze_url(),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"inputs": [{"url": request.content_url}]},
            timeout=self._request_timeout_seconds,
        )
        if response.status_code >= 400:
            raise _content_understanding_error(response.status_code, None, _safe_json(response))
        operation_location = response.headers.get("operation-location") or response.headers.get(
            "Operation-Location"
        )
        if not operation_location:
            raise _content_understanding_error(response.status_code, "OperationLocationMissing")
        return urljoin(self._endpoint, operation_location)

    def get_result(self, operation_url: str) -> dict[str, object]:
        token = self._credential.get_token(COGNITIVE_SERVICES_SCOPE).token
        response = self._http_client.get(
            operation_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=self._request_timeout_seconds,
        )
        if response.status_code >= 400:
            raise _content_understanding_error(response.status_code, None, _safe_json(response))
        result = response.json()
        if not isinstance(result, dict):
            raise _content_understanding_error(response.status_code, None)
        return result

    def _analyze_url(self) -> str:
        return (
            f"{self._endpoint}contentunderstanding/analyzers/"
            f"{self._analyzer_id}:analyze?api-version={self._api_version}"
        )


def _content_understanding_error(
    status_code: int | None,
    operation_status: str | None,
    response_body: object | None = None,
) -> AppError:
    details: dict[str, object] = {}
    if status_code is not None:
        details["statusCode"] = status_code
    if operation_status:
        details["operationStatus"] = operation_status
    details.update(sanitized_content_understanding_error_details(response_body))
    return AppError(
        code="CONTENT_UNDERSTANDING_FAILED",
        message="Content Understanding による動画解析に失敗しました。",
        http_status=502 if status_code is None or status_code >= 500 else 400,
        details=details,
    )


def sanitized_content_understanding_error_details(
    response_body: object | None,
) -> dict[str, object]:
    if not isinstance(response_body, Mapping):
        return {}

    error_value = response_body.get("error")
    if isinstance(error_value, Mapping):
        sanitized_error = _redact_remaining_urls(
            safe_log_payload(_pick_error_fields(error_value), max_depth=4)
        )
        if isinstance(sanitized_error, dict) and sanitized_error:
            return {"operationError": sanitized_error}

    details: dict[str, object] = {}
    for key in ("code", "message"):
        value = response_body.get(key)
        if isinstance(value, str) and value:
            details[key] = value
    if details:
        sanitized = _redact_remaining_urls(safe_log_payload(details, max_depth=2))
        if isinstance(sanitized, dict):
            return {"operationError": sanitized}
    return {}


def _pick_error_fields(error_value: Mapping[object, object]) -> dict[str, object]:
    picked: dict[str, object] = {}
    for key in ("code", "message", "target"):
        value = error_value.get(key)
        if isinstance(value, str) and value:
            picked[key] = value
    inner = error_value.get("innererror") or error_value.get("innerError")
    if isinstance(inner, Mapping):
        picked["innerError"] = _pick_error_fields(inner)
    details = error_value.get("details")
    if isinstance(details, list):
        picked["details"] = [
            _pick_error_fields(item) for item in details if isinstance(item, Mapping)
        ]
    return picked


def _safe_json(response: httpx.Response) -> object | None:
    try:
        return response.json()
    except ValueError:
        return None


def _redact_remaining_urls(value: object) -> object:
    if isinstance(value, str):
        return ANY_URL_PATTERN.sub("[REDACTED_URL]", value)
    if isinstance(value, Mapping):
        return {str(key): _redact_remaining_urls(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_remaining_urls(item) for item in value]
    return value
