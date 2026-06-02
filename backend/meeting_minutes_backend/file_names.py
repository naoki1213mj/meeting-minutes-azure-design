from __future__ import annotations

import re
from pathlib import PureWindowsPath

from meeting_minutes_backend.errors import AppError

SUPPORTED_AUDIO_EXTENSIONS = frozenset(
    {".mp3", ".wav", ".m4a", ".mp4", ".ogg", ".webm", ".flac"}
)
ALLOWED_EXTENSIONS_BY_CONTENT_TYPE = {
    "audio/mpeg": frozenset({".mp3"}),
    "audio/mp3": frozenset({".mp3"}),
    "audio/wav": frozenset({".wav"}),
    "audio/x-wav": frozenset({".wav"}),
    "audio/mp4": frozenset({".m4a", ".mp4"}),
    "audio/m4a": frozenset({".m4a"}),
    "audio/x-m4a": frozenset({".m4a"}),
    "audio/aac": frozenset({".m4a"}),
    "video/mp4": frozenset({".mp4"}),
    "application/mp4": frozenset({".mp4"}),
    "audio/ogg": frozenset({".ogg"}),
    "audio/webm": frozenset({".webm"}),
    "audio/flac": frozenset({".flac"}),
    "application/octet-stream": SUPPORTED_AUDIO_EXTENSIONS,
}
_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
_SAFE_FILE_NAME = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def build_safe_file_name(file_name: str, content_type: str) -> str:
    content_type_key = content_type.split(";", 1)[0].strip().lower()
    allowed_extensions = ALLOWED_EXTENSIONS_BY_CONTENT_TYPE.get(content_type_key)
    if allowed_extensions is None:
        raise AppError(
            code="UNSUPPORTED_AUDIO_FORMAT",
            message="対応していない音声形式です。",
            http_status=400,
        )

    leaf_name = PureWindowsPath(file_name).name
    suffix = PureWindowsPath(leaf_name).suffix.lower()
    if suffix not in allowed_extensions:
        raise AppError(
            code="UNSUPPORTED_AUDIO_FORMAT",
            message="拡張子とContent-Typeの組み合わせを確認してください。",
            http_status=400,
        )

    stem = leaf_name[: -len(suffix)] if suffix else leaf_name
    safe_stem = _SAFE_CHARS.sub("-", stem).strip(".-_")
    candidate = f"{safe_stem}{suffix}" if safe_stem else f"input{suffix}"
    candidate = candidate[:128]

    if not _SAFE_FILE_NAME.fullmatch(candidate):
        return f"input{suffix}"
    return candidate
