from __future__ import annotations

import pytest

from meeting_minutes_backend.errors import AppError
from meeting_minutes_backend.file_names import build_safe_file_name


@pytest.mark.parametrize(
    ("file_name", "content_type", "expected"),
    [
        ("meeting.m4a", "audio/mp4", "meeting.m4a"),
        ("meeting.m4a", "audio/x-m4a", "meeting.m4a"),
        ("meeting.m4a", "audio/m4a", "meeting.m4a"),
        ("Meeting.M4A", "application/octet-stream", "Meeting.m4a"),
        ("meeting.mp4", "video/mp4", "meeting.mp4"),
        ("meeting.mp4", "audio/mp4", "meeting.mp4"),
        ("meeting.mp4", "application/mp4", "meeting.mp4"),
        ("Meeting.MP4", "application/octet-stream", "Meeting.mp4"),
        ("meeting.mp3", "audio/mpeg; charset=utf-8", "meeting.mp3"),
        ("!!!!.m4a", "application/octet-stream", "input.m4a"),
        ("!!!!.mp4", "application/octet-stream", "input.mp4"),
    ],
)
def test_build_safe_file_name_accepts_common_audio_mime_variants(
    file_name: str,
    content_type: str,
    expected: str,
) -> None:
    assert build_safe_file_name(file_name, content_type) == expected


@pytest.mark.parametrize(
    ("file_name", "content_type"),
    [
        ("meeting.m4a", "audio/mpeg"),
        ("meeting.mp4", "audio/mpeg"),
        ("meeting.m4a", "video/mp4"),
        ("meeting", "application/octet-stream"),
    ],
)
def test_build_safe_file_name_rejects_mismatched_or_video_formats(
    file_name: str,
    content_type: str,
) -> None:
    with pytest.raises(AppError) as exc_info:
        build_safe_file_name(file_name, content_type)

    assert exc_info.value.code == "UNSUPPORTED_AUDIO_FORMAT"
