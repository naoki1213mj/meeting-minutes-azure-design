from __future__ import annotations

import json
import logging
from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

import azure.functions as func
from pydantic import BaseModel, ValidationError

from meeting_minutes_backend.correlation import CORRELATION_HEADER, resolve_correlation_id
from meeting_minutes_backend.errors import (
    AppError,
    to_error_response,
    validation_error_to_app_error,
)

P = ParamSpec("P")
R = TypeVar("R", bound=func.HttpResponse)
M = TypeVar("M", bound=BaseModel)
LOGGER = logging.getLogger(__name__)


def parse_json_model(req: func.HttpRequest, model_type: type[M]) -> M:
    try:
        return model_type.model_validate_json(req.get_body())
    except ValueError as exc:
        if isinstance(exc, ValidationError):
            raise validation_error_to_app_error(exc) from exc
        raise AppError(
            code="INVALID_REQUEST",
            message="JSONリクエスト本文を確認してください。",
            http_status=400,
        ) from exc


def json_response(
    body: dict[str, object], status_code: int, correlation_id: str
) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(body, ensure_ascii=False),
        status_code=status_code,
        mimetype="application/json",
        headers={CORRELATION_HEADER: correlation_id},
    )


def error_boundary(handler: Callable[P, R]) -> Callable[P, func.HttpResponse]:
    @wraps(handler)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> func.HttpResponse:
        req = args[0]
        if not isinstance(req, func.HttpRequest):
            raise TypeError("First handler argument must be an HttpRequest")

        correlation_id = resolve_correlation_id(req.headers)
        try:
            return handler(*args, **kwargs)
        except AppError as exc:
            return json_response(
                to_error_response(exc, correlation_id), exc.http_status, correlation_id
            )
        except Exception as exc:
            LOGGER.error("Unhandled HTTP error: %s", exc.__class__.__name__)
            error = AppError(
                code="INTERNAL_ERROR",
                message="内部エラーが発生しました。",
                http_status=500,
            )
            return json_response(to_error_response(error, correlation_id), 500, correlation_id)

    return wrapper
