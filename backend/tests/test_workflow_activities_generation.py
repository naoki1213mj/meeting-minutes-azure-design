from __future__ import annotations

from meeting_minutes_backend.errors import AppError
from meeting_minutes_backend.workflow_activities import _should_fallback_to_chunk_minutes


def test_minutes_generation_fallbacks_on_truncated_direct_response() -> None:
    error = AppError(
        code="OPENAI_GENERATION_FAILED",
        message="議事録生成に失敗しました。",
        http_status=502,
        details={"reason": "Response was truncated"},
    )

    assert _should_fallback_to_chunk_minutes(error)


def test_minutes_generation_fallbacks_on_schema_validation_failure() -> None:
    error = AppError(
        code="MINUTES_SCHEMA_VALIDATION_FAILED",
        message="議事録JSONの検証に失敗しました。",
        http_status=502,
    )

    assert _should_fallback_to_chunk_minutes(error)


def test_minutes_generation_does_not_fallback_on_content_filter() -> None:
    error = AppError(
        code="OPENAI_GENERATION_FAILED",
        message="議事録生成に失敗しました。",
        http_status=502,
        details={"reason": "Response blocked by content filter"},
    )

    assert not _should_fallback_to_chunk_minutes(error)
