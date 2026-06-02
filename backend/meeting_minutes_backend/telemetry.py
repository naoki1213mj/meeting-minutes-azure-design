from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TypeVar
from urllib.parse import parse_qsl, urlsplit

T = TypeVar("T")

ACTIVITY_DURATION_METRIC_NAME = "meeting.activity.duration.seconds"
ACTIVITY_DURATION_LOGGER_NAME = "meeting_minutes.activity_duration"
LOGGER = logging.getLogger(ACTIVITY_DURATION_LOGGER_NAME)


def _normalize_field_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


SENSITIVE_FIELD_NAMES = {
    "accessToken",
    "audio",
    "audio_url",
    "audioUrl",
    "authorization",
    "body",
    "clientSecret",
    "combinedPhrases",
    "connectionString",
    "content",
    "definition",
    "displayText",
    "apiKey",
    "key",
    "minutes",
    "phrases",
    "result",
    "sas",
    "sasUrl",
    "secret",
    "sharedAccessKey",
    "storageKey",
    "summary",
    "text",
    "token",
    "transcript",
    "upload_url",
    "uploadUrl",
    "value",
}
SENSITIVE_FIELD_KEYS = {_normalize_field_name(name) for name in SENSITIVE_FIELD_NAMES}
SENSITIVE_QUERY_KEYS = {
    "se",
    "ses",
    "si",
    "sig",
    "sip",
    "ske",
    "skoid",
    "sks",
    "skt",
    "sktid",
    "skv",
    "sp",
    "spr",
    "sr",
    "st",
    "sv",
}
JWT_PATTERN = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
CONNECTION_SECRET_PATTERN = re.compile(
    r"(AccountKey|SharedAccessKey|sig)=([^;\s&]+)", re.IGNORECASE
)
LONG_BASE64_PATTERN = re.compile(r"\b[A-Za-z0-9+/]{80,}={0,2}\b")
URL_PATTERN = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)


@dataclass(frozen=True)
class TelemetryMetric:
    name: str
    value: float
    dimensions: dict[str, str] = field(default_factory=dict)


def safe_log_payload(payload: object, max_depth: int = 6) -> object:
    return _redact(payload, depth=0, max_depth=max_depth)


def build_job_metric(
    name: str,
    value: float,
    job_id: str,
    tenant_id: str,
    activity_name: str,
    extra_dimensions: Mapping[str, object] | None = None,
) -> TelemetryMetric:
    dimensions: dict[str, str] = {
        "jobId": job_id,
        "tenantId": tenant_id,
        "activityName": activity_name,
    }
    for key, raw_value in (extra_dimensions or {}).items():
        if _is_sensitive_field_name(str(key)):
            dimensions[f"{key}Redacted"] = "true"
            continue
        sanitized = safe_log_payload(raw_value)
        if sanitized == "[REDACTED]":
            dimensions[f"{key}Redacted"] = "true"
            continue
        dimensions[key] = str(sanitized)
    return TelemetryMetric(name=name, value=value, dimensions=dimensions)


def measure_activity(
    activity_name: str,
    payload: dict[str, object],
    handler: Callable[[dict[str, object]], T],
) -> T:
    started = time.perf_counter()
    outcome = "success"
    error_type: str | None = None
    error_code: str | None = None
    try:
        return handler(payload)
    except Exception as exc:
        outcome = "failure"
        error_type = exc.__class__.__name__
        code = getattr(exc, "code", None)
        if isinstance(code, str):
            error_code = code
        raise
    finally:
        duration_seconds = time.perf_counter() - started
        _safe_emit_activity_duration(
            activity_name=activity_name,
            payload=payload,
            duration_seconds=duration_seconds,
            outcome=outcome,
            error_type=error_type,
            error_code=error_code,
        )


def _safe_emit_activity_duration(
    *,
    activity_name: str,
    payload: Mapping[str, object],
    duration_seconds: float,
    outcome: str,
    error_type: str | None,
    error_code: str | None,
) -> None:
    try:
        context = _activity_context(payload)
        extra_dimensions: dict[str, object] = {"outcome": outcome}
        chunk_index = context.get("chunkIndex")
        if chunk_index is not None:
            extra_dimensions["chunkIndex"] = chunk_index
        if error_type is not None:
            extra_dimensions["errorType"] = error_type
        if error_code is not None:
            extra_dimensions["errorCode"] = error_code

        metric = build_job_metric(
            ACTIVITY_DURATION_METRIC_NAME,
            duration_seconds,
            job_id=context["jobId"],
            tenant_id=context["tenantId"],
            activity_name=activity_name,
            extra_dimensions=extra_dimensions,
        )
        log_payload = {
            "metric": metric.name,
            "value": round(metric.value, 6),
            "dimensions": metric.dimensions,
        }
        LOGGER.info(
            json.dumps(log_payload, ensure_ascii=False, sort_keys=True),
            extra={
                "custom_dimensions": metric.dimensions,
                "custom_metric_name": metric.name,
                "custom_metric_value": metric.value,
            },
        )
    except Exception:
        LOGGER.debug("activity duration telemetry emission failed", exc_info=True)


def _activity_context(payload: Mapping[str, object]) -> dict[str, str]:
    source: Mapping[str, object] = payload
    if not _optional_string(source.get("tenantId")) or not _optional_string(source.get("jobId")):
        nested_job = payload.get("job")
        if isinstance(nested_job, Mapping):
            source = nested_job

    context = {
        "tenantId": _optional_string(source.get("tenantId")) or "unknown",
        "jobId": _optional_string(source.get("jobId")) or "unknown",
    }
    chunk_index = payload.get("chunkIndex")
    if isinstance(chunk_index, int):
        context["chunkIndex"] = str(chunk_index)
    return context


def _optional_string(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _redact(value: object, depth: int, max_depth: int) -> object:
    if depth > max_depth:
        return "[MAX_DEPTH]"
    if isinstance(value, str):
        return _redact_string(value)
    if isinstance(value, Mapping):
        redacted: dict[str, object] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 50:
                redacted["[TRUNCATED_KEYS]"] = True
                break
            key_text = str(key)
            if _is_sensitive_field_name(key_text):
                redacted[key_text] = "[REDACTED]"
            else:
                redacted[key_text] = _redact(item, depth + 1, max_depth)
        return redacted
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        items = list(value[:50]) if hasattr(value, "__getitem__") else list(value)
        result = [_redact(item, depth + 1, max_depth) for item in items]
        if len(value) > 50:
            result.append("[TRUNCATED_ITEMS]")
        return result
    return value


def _redact_string(value: str) -> str:
    redacted = JWT_PATTERN.sub("[REDACTED_TOKEN]", value)
    redacted = CONNECTION_SECRET_PATTERN.sub(r"\1=[REDACTED]", redacted)
    redacted = LONG_BASE64_PATTERN.sub("[REDACTED_BASE64]", redacted)
    redacted = _redact_sensitive_url(redacted)
    if len(redacted) > 512:
        return f"{redacted[:512]}...[truncated {len(redacted) - 512} chars]"
    return redacted


def _redact_sensitive_url(value: str) -> str:
    return URL_PATTERN.sub(_redact_url_match, value)


def _redact_url_match(match: re.Match[str]) -> str:
    value = match.group(0)
    try:
        parts = urlsplit(value)
    except ValueError:
        return value
    if not parts.scheme or not parts.netloc or not parts.query:
        return value

    query = parse_qsl(parts.query, keep_blank_values=True)
    if not any(key.lower() in SENSITIVE_QUERY_KEYS for key, _ in query):
        return value

    return "[REDACTED_SAS_URL]"


def _is_sensitive_field_name(value: str) -> bool:
    return _normalize_field_name(value) in SENSITIVE_FIELD_KEYS
