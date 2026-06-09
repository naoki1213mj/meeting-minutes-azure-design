from __future__ import annotations

import pytest
from pydantic import ValidationError

from meeting_minutes_backend.errors import AppError, validation_error_to_app_error
from meeting_minutes_backend.models import CreateJobRequest


def test_validation_error_details_do_not_echo_input() -> None:
    with pytest.raises(ValidationError) as exc_info:
        CreateJobRequest.model_validate({"fileName": "secret.mp3"})

    error = validation_error_to_app_error(exc_info.value)
    details = error.details["validationErrors"]

    assert isinstance(details, list)
    assert details
    assert "input" not in details[0]
    assert "msg" not in details[0]


def test_app_error_string_includes_code_and_user_message_only() -> None:
    error = AppError(
        code="CONTENT_UNDERSTANDING_FAILED",
        message="Content Understanding による動画解析に失敗しました。",
        http_status=502,
        details={"operationError": {"message": "secret detail"}},
    )

    assert str(error) == (
        "CONTENT_UNDERSTANDING_FAILED: "
        "Content Understanding による動画解析に失敗しました。"
    )
    assert "secret detail" not in str(error)
