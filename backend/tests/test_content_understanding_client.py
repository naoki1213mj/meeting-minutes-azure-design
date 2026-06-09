from __future__ import annotations

import httpx
import pytest
from azure.core.credentials import AccessToken

from meeting_minutes_backend.content_understanding_client import (
    ContentUnderstandingClient,
    ContentUnderstandingRequest,
    sanitized_content_understanding_error_details,
)
from meeting_minutes_backend.errors import AppError


class FakeCredential:
    def __init__(self) -> None:
        self.calls = 0

    def get_token(
        self,
        *scopes: str,
        claims: str | None = None,
        tenant_id: str | None = None,
        enable_cae: bool = False,
        **kwargs: object,
    ) -> AccessToken:
        _ = (claims, tenant_id, enable_cae, kwargs)
        self.calls += 1
        assert scopes == ("https://cognitiveservices.azure.com/.default",)
        return AccessToken(token=f"token-{self.calls}", expires_on=9999999999)


def test_content_understanding_analyze_url_starts_and_polls_operation() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            assert request.url == (
                "https://foundry.example/contentunderstanding/analyzers/"
                "prebuilt-videoSearch:analyze?api-version=2025-11-01"
            )
            assert b"https://storage.example/video.mp4?sig=redacted" in request.content
            return httpx.Response(
                202,
                headers={
                    "Operation-Location": (
                        "https://foundry.example/contentunderstanding/analyzerResults/op-a"
                        "?api-version=2025-11-01"
                    )
                },
            )
        return httpx.Response(
            200,
            json={"status": "Succeeded", "result": {"contents": []}},
        )

    client = ContentUnderstandingClient(
        endpoint="https://foundry.example",
        analyzer_id="prebuilt-videoSearch",
        credential=FakeCredential(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _: None,
    )

    result = client.analyze_url(
        ContentUnderstandingRequest(
            content_url="https://storage.example/video.mp4?sig=redacted"
        )
    )

    assert result["status"] == "Succeeded"
    assert [request.method for request in requests] == ["POST", "GET"]


def test_content_understanding_failed_operation_keeps_sanitized_error_details() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                202,
                headers={
                    "Operation-Location": (
                        "https://foundry.example/contentunderstanding/analyzerResults/op-a"
                        "?api-version=2025-11-01"
                    )
                },
            )
        return httpx.Response(
            200,
            json={
                "status": "Failed",
                "error": {
                    "code": "InvalidContent",
                    "message": (
                        "Could not fetch https://storage.example/video.mp4?"
                        "sv=2024&sig=secret-signature"
                    ),
                    "innererror": {
                        "code": "FetchFailed",
                        "message": "The content URL could not be read.",
                    },
                },
            },
        )

    client = ContentUnderstandingClient(
        endpoint="https://foundry.example",
        analyzer_id="prebuilt-videoSearch",
        credential=FakeCredential(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _: None,
    )

    with pytest.raises(AppError) as exc_info:
        client.analyze_url(ContentUnderstandingRequest(content_url="https://storage.example/video.mp4"))

    assert exc_info.value.code == "CONTENT_UNDERSTANDING_FAILED"
    assert exc_info.value.details["operationStatus"] == "Failed"
    operation_error = exc_info.value.details["operationError"]
    assert isinstance(operation_error, dict)
    assert operation_error["code"] == "InvalidContent"
    assert operation_error["message"] == "Could not fetch [REDACTED_SAS_URL]"
    assert "secret-signature" not in str(operation_error)


def test_sanitized_content_understanding_error_details_supports_top_level_error() -> None:
    details = sanitized_content_understanding_error_details(
        {
            "error": {
                "code": "BadRequest",
                "message": "Unsupported file.",
                "target": "inputs[0]",
                "details": [{"code": "Format", "message": "Unsupported codec."}],
            }
        }
    )

    assert details == {
        "operationError": {
            "code": "BadRequest",
            "message": "Unsupported file.",
            "target": "inputs[0]",
            "details": [{"code": "Format", "message": "Unsupported codec."}],
        }
    }


def test_sanitized_content_understanding_error_details_redacts_bare_urls() -> None:
    details = sanitized_content_understanding_error_details(
        {
            "error": {
                "code": "FetchFailed",
                "message": "Could not fetch https://account.blob.core.windows.net/audio/job/input.mp4",
            }
        }
    )

    operation_error = details["operationError"]
    assert isinstance(operation_error, dict)
    assert operation_error["message"] == "Could not fetch [REDACTED_URL]"
    assert "account.blob.core.windows.net" not in str(operation_error)
