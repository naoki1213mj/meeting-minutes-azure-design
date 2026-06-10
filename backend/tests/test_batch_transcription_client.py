from __future__ import annotations

import json

import httpx
from azure.core.credentials import AccessToken

from meeting_minutes_backend.batch_transcription_client import (
    BatchTranscriptionClient,
    BatchTranscriptionRequest,
)


class FakeCredential:
    def get_token(
        self,
        *scopes: str,
        claims: str | None = None,
        tenant_id: str | None = None,
        enable_cae: bool = False,
        **kwargs: object,
    ) -> AccessToken:
        _ = (claims, tenant_id, enable_cae, kwargs)
        assert scopes == ("https://cognitiveservices.azure.com/.default",)
        return AccessToken("token", 9999999999)


def test_batch_transcription_client_starts_polls_and_fetches_result() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            assert request.url == (
                "https://speech.example/speechtotext/transcriptions:submit"
                "?api-version=2024-11-15"
            )
            body = json.loads(request.content.decode("utf-8"))
            assert body["contentUrls"] == ["https://storage.example/audio.flac?sig=redacted"]
            assert body["properties"]["diarization"] == {
                "enabled": True,
                "maxSpeakers": 8,
            }
            assert body["properties"]["timeToLiveHours"] == 24
            assert "channels" not in body["properties"]
            assert body["displayName"] == "minutes-job-a"
            assert "Authorization" in request.headers
            return httpx.Response(
                201,
                headers={
                    "Location": (
                        "https://speech.example/speechtotext/transcriptions/batch-a"
                        "?api-version=2024-11-15"
                    )
                },
            )
        if request.url.path.endswith("/files"):
            return httpx.Response(
                200,
                json={
                    "values": [
                        {
                            "kind": "Transcription",
                            "links": {"contentUrl": "https://results.example/result.json?sig=x"},
                        }
                    ]
                },
            )
        if request.url.host == "results.example":
            assert "Authorization" not in request.headers
            return httpx.Response(200, json={"recognizedPhrases": []})
        return httpx.Response(
            200,
            json={
                "self": (
                    "https://speech.example/speechtotext/transcriptions/batch-a"
                    "?api-version=2024-11-15"
                ),
                "status": "Succeeded",
                "links": {
                    "files": (
                        "https://speech.example/speechtotext/transcriptions/batch-a/files"
                        "?api-version=2024-11-15"
                    )
                },
            },
        )

    client = BatchTranscriptionClient(
        endpoint="https://speech.example",
        credential=FakeCredential(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _: None,
    )

    transcription_url = client.start_transcription(
        BatchTranscriptionRequest(
            audioUrl="https://storage.example/audio.flac?sig=redacted",
            jobId="job-a",
        )
    )
    status = client.get_transcription(transcription_url)
    result = client.get_result(status)

    assert transcription_url.endswith("/batch-a?api-version=2024-11-15")
    assert result.status == "Succeeded"
    assert result.raw_result == {"recognizedPhrases": []}
    assert [request.method for request in requests] == ["POST", "GET", "GET", "GET"]


def test_batch_transcription_client_builds_files_url_before_api_version_query() -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if request.url.path.endswith("/files"):
            return httpx.Response(
                200,
                json={
                    "values": [
                        {
                            "kind": "Transcription",
                            "links": {"contentUrl": "https://results.example/result.json?sig=x"},
                        }
                    ]
                },
            )
        if request.url.host == "results.example":
            return httpx.Response(200, json={"recognizedPhrases": []})
        raise AssertionError(f"unexpected url: {request.url}")

    client = BatchTranscriptionClient(
        endpoint="https://speech.example",
        credential=FakeCredential(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _: None,
    )

    result = client.get_result(
        {
            "self": (
                "https://speech.example/speechtotext/transcriptions/batch-a"
                "?api-version=2024-11-15"
            ),
            "status": "Succeeded",
        }
    )

    assert result.raw_result == {"recognizedPhrases": []}
    assert requested_urls[0] == (
        "https://speech.example/speechtotext/transcriptions/batch-a/files"
        "?api-version=2024-11-15"
    )
