from __future__ import annotations

import httpx
import pytest
from azure.core.credentials import AccessToken

from meeting_minutes_backend.errors import AppError
from meeting_minutes_backend.speech_client import FastTranscriptionClient, TranscriptionRequest


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


def test_fast_transcription_request_uses_audio_url_and_omits_channels() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"durationMilliseconds": 0, "phrases": []})

    client = FastTranscriptionClient(
        endpoint="https://speech.example",
        credential=FakeCredential(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _: None,
    )

    response = client.transcribe_audio_url(
        TranscriptionRequest(audioUrl="https://storage.example/audio.wav?sig=REDACTED_TEST_VALUE")
    )

    assert response["durationMilliseconds"] == 0
    request = captured[0]
    assert request.url == (
        "https://speech.example/speechtotext/transcriptions:transcribe?api-version=2025-10-15"
    )
    body = request.content.decode("utf-8")
    assert 'name="definition"' in body
    assert "filename=" not in body
    assert "application/json" in body
    assert "audioUrl" in body
    assert "diarization" in body
    assert "channels" not in body


def test_fast_transcription_retries_retryable_status() -> None:
    statuses = [429, 200]
    sleeps: list[float] = []
    credential = FakeCredential()

    def handler(request: httpx.Request) -> httpx.Response:
        _ = request
        status = statuses.pop(0)
        if status == 429:
            return httpx.Response(429, headers={"Retry-After": "0.5"})
        return httpx.Response(200, json={"durationMilliseconds": 0, "phrases": []})

    client = FastTranscriptionClient(
        endpoint="https://speech.example",
        credential=credential,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=sleeps.append,
    )

    client.transcribe_audio_url(TranscriptionRequest(audioUrl="https://storage.example/a.wav"))

    assert credential.calls == 2
    assert sleeps == [0.5]


def test_fast_transcription_does_not_retry_bad_request() -> None:
    credential = FakeCredential()

    def handler(request: httpx.Request) -> httpx.Response:
        _ = request
        return httpx.Response(400, json={"error": {"message": "bad request"}})

    client = FastTranscriptionClient(
        endpoint="https://speech.example",
        credential=credential,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _: None,
    )

    with pytest.raises(AppError) as exc_info:
        client.transcribe_audio_url(
            TranscriptionRequest(audioUrl="https://storage.example/a.wav?sig=REDACTED_TEST_VALUE")
        )

    assert credential.calls == 1
    assert exc_info.value.code == "TRANSCRIPTION_FAILED"
    assert exc_info.value.details == {"attemptCount": 1, "statusCode": 400}
    assert "REDACTED_TEST_VALUE" not in str(exc_info.value.details)
