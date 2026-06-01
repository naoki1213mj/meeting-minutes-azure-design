from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlsplit


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
