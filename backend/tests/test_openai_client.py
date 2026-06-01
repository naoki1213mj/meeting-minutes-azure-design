from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from azure.core.credentials import AccessToken

import meeting_minutes_backend.openai_client as openai_client
from meeting_minutes_backend.errors import AppError
from meeting_minutes_backend.minutes_generation import DeploymentCapabilities
from meeting_minutes_backend.openai_client import AzureOpenAIJsonClient


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
        return AccessToken(token="fake-access-token", expires_on=9999999999)  # noqa: S106


@dataclass
class FakeMessage:
    content: str | None


@dataclass
class FakeChoice:
    message: FakeMessage
    finish_reason: str | None = "stop"


@dataclass
class FakeResponse:
    choices: list[FakeChoice]
    model: str = "gpt-5.4"


class FakeCompletions:
    def __init__(self, response: FakeResponse) -> None:
        self._response = response

    def create(self, **kwargs: object) -> FakeResponse:
        _ = kwargs
        return self._response


class FakeChat:
    def __init__(self, response: FakeResponse) -> None:
        self.completions = FakeCompletions(response)


class FakeOpenAI:
    response: FakeResponse

    def __init__(self, api_key: str, base_url: str) -> None:
        _ = (api_key, base_url)
        self.chat = FakeChat(self.response)


def _client(monkeypatch: pytest.MonkeyPatch, response: FakeResponse) -> AzureOpenAIJsonClient:
    FakeOpenAI.response = response
    monkeypatch.setattr(openai_client, "OpenAI", FakeOpenAI)
    return AzureOpenAIJsonClient(
        base_url="https://example.openai.azure.com/openai/v1/",
        credential=FakeCredential(),
        sleep=lambda _: None,
    )


def _deployment() -> DeploymentCapabilities:
    return DeploymentCapabilities(deploymentName="gpt-5.4", modelName="gpt-5.4")


def test_generate_json_returns_parsed_object(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(
        monkeypatch,
        FakeResponse(choices=[FakeChoice(message=FakeMessage(json.dumps({"ok": True})))]),
    )

    result = client.generate_json("system", "user", {"title": "Schema"}, _deployment())

    assert result.content == {"ok": True}


def test_generate_json_reports_truncation_without_raw_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_content = '{"partial": "secret transcript text"'
    client = _client(
        monkeypatch,
        FakeResponse(
            choices=[FakeChoice(message=FakeMessage(raw_content), finish_reason="length")]
        ),
    )

    with pytest.raises(AppError) as exc_info:
        client.generate_json("system", "user", {"title": "Schema"}, _deployment())

    assert exc_info.value.code == "OPENAI_GENERATION_FAILED"
    assert exc_info.value.details["reason"] == "Response was truncated"
    assert raw_content not in str(exc_info.value.details)


def test_generate_json_reports_invalid_json_without_raw_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_content = "not json secret transcript text"
    client = _client(
        monkeypatch,
        FakeResponse(choices=[FakeChoice(message=FakeMessage(raw_content))]),
    )

    with pytest.raises(AppError) as exc_info:
        client.generate_json("system", "user", {"title": "Schema"}, _deployment())

    assert exc_info.value.details["reason"] == "Response content was not valid JSON"
    assert raw_content not in str(exc_info.value.details)
