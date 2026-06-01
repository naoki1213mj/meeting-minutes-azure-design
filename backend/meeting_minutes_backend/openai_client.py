from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

from azure.core.credentials import TokenCredential
from openai import APIConnectionError, APIStatusError, OpenAI

from meeting_minutes_backend.errors import AppError
from meeting_minutes_backend.minutes_generation import (
    DeploymentCapabilities,
    ModelResult,
    OpenAIJsonClient,
    build_structured_output_request,
)

COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
DEFAULT_BACKOFF_SECONDS = [2, 4, 8, 16, 32]


class AzureOpenAIJsonClient(OpenAIJsonClient):
    def __init__(
        self,
        base_url: str,
        credential: TokenCredential,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._base_url = base_url.rstrip("/") + "/"
        self._credential = credential
        self._sleep = sleep

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        deployment: DeploymentCapabilities,
    ) -> ModelResult:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        request = build_structured_output_request(deployment, messages, schema)
        last_status_code: int | None = None
        attempt_count = 0

        for attempt_count, backoff_seconds in enumerate([*DEFAULT_BACKOFF_SECONDS, None], start=1):
            token = self._credential.get_token(COGNITIVE_SERVICES_SCOPE).token
            client = OpenAI(api_key=token, base_url=self._base_url)
            try:
                response = client.chat.completions.create(**request)
                choice = response.choices[0]
                finish_reason = getattr(choice, "finish_reason", None)
                if finish_reason == "length":
                    raise _openai_error(None, attempt_count, "Response was truncated")
                if finish_reason == "content_filter":
                    raise _openai_error(
                        None,
                        attempt_count,
                        "Response blocked by content filter",
                    )
                content = choice.message.content
                if not content:
                    raise _openai_error(None, attempt_count, "Empty response content")
                data = json.loads(content)
                if not isinstance(data, dict):
                    raise _openai_error(None, attempt_count, "Response JSON must be an object")
                return ModelResult(content=data, model_name=response.model or deployment.modelName)
            except APIStatusError as exc:
                last_status_code = exc.status_code
                if exc.status_code not in RETRY_STATUS_CODES or backoff_seconds is None:
                    raise _openai_error(exc.status_code, attempt_count) from exc
                self._sleep(_retry_after_seconds(exc.response.headers) or backoff_seconds)
            except APIConnectionError as exc:
                if backoff_seconds is None:
                    raise _openai_error(None, attempt_count) from exc
                self._sleep(backoff_seconds)
            except json.JSONDecodeError as exc:
                raise _openai_error(
                    None,
                    attempt_count,
                    "Response content was not valid JSON",
                ) from exc

        raise _openai_error(last_status_code, attempt_count)


def _retry_after_seconds(headers: object) -> float | None:
    value = getattr(headers, "get", lambda _name: None)("retry-after")
    if value is None:
        value = getattr(headers, "get", lambda _name: None)("Retry-After")
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _openai_error(
    status_code: int | None,
    attempt_count: int,
    reason: str | None = None,
) -> AppError:
    details: dict[str, object] = {"attemptCount": attempt_count}
    if status_code is not None:
        details["statusCode"] = status_code
    if reason:
        details["reason"] = reason
    return AppError(
        code="OPENAI_GENERATION_FAILED",
        message="議事録生成に失敗しました。",
        http_status=502 if status_code is None or status_code >= 500 else 400,
        details=details,
    )
