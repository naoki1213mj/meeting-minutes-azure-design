from __future__ import annotations

import httpx
from azure.core.credentials import AccessToken

from meeting_minutes_backend.content_understanding_client import (
    ContentUnderstandingClient,
    ContentUnderstandingRequest,
)


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
