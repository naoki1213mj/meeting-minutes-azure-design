from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx
from azure.core.credentials import TokenCredential

from meeting_minutes_backend.errors import AppError

COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"
TERMINAL_STATUSES = {"Succeeded", "Failed", "Canceled"}


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
                raise _content_understanding_error(None, last_status)
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
            raise _content_understanding_error(response.status_code, None)
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
            raise _content_understanding_error(response.status_code, None)
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
) -> AppError:
    details: dict[str, object] = {}
    if status_code is not None:
        details["statusCode"] = status_code
    if operation_status:
        details["operationStatus"] = operation_status
    return AppError(
        code="CONTENT_UNDERSTANDING_FAILED",
        message="Content Understanding による動画解析に失敗しました。",
        http_status=502 if status_code is None or status_code >= 500 else 400,
        details=details,
    )
