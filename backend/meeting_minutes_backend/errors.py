from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import ValidationError


@dataclass(frozen=True)
class AppError(Exception):
    code: str
    message: str
    http_status: int
    details: dict[str, object] = field(default_factory=dict)


def validation_error_to_app_error(error: ValidationError) -> AppError:
    validation_errors: list[dict[str, object]] = []
    for item in error.errors():
        validation_errors.append(
            {
                "loc": list(item.get("loc", ())),
                "type": item.get("type", "validation_error"),
            }
        )

    return AppError(
        code="INVALID_REQUEST",
        message="リクエスト内容を確認してください。",
        http_status=400,
        details={"validationErrors": validation_errors},
    )


def to_error_response(error: AppError, correlation_id: str) -> dict[str, object]:
    error_body: dict[str, object] = {
        "code": error.code,
        "message": error.message,
        "correlationId": correlation_id,
    }
    if error.details:
        error_body["details"] = error.details
    return {"error": error_body}
