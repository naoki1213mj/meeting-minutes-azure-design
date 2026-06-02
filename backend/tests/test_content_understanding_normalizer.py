from __future__ import annotations

import pytest

from meeting_minutes_backend.content_understanding_normalizer import (
    build_visual_context,
    normalize_content_understanding_transcript,
)
from meeting_minutes_backend.errors import AppError


def _raw_response() -> dict[str, object]:
    return {
        "status": "Succeeded",
        "result": {
            "contents": [
                {
                    "kind": "audioVisual",
                    "startTimeMs": 0,
                    "endTimeMs": 5440,
                    "width": 640,
                    "height": 360,
                    "markdown": "# Video\n\nTranscript...",
                    "fields": {"Summary": {"type": "string", "valueString": "概要"}},
                    "keyFrameTimesMs": [400, 1800],
                    "cameraShotTimesMs": [760],
                    "transcriptPhrases": [
                        {
                            "speaker": "Speaker 1",
                            "startTimeMs": 280,
                            "endTimeMs": 3560,
                            "text": "本日の方針を確認します。",
                            "words": [],
                        },
                        {
                            "speaker": "Speaker 2",
                            "startTimeMs": 4640,
                            "endTimeMs": 5440,
                            "text": "承知しました。",
                            "words": [],
                        },
                    ],
                }
            ]
        },
    }


def test_normalize_content_understanding_transcript_matches_schema() -> None:
    normalized = normalize_content_understanding_transcript(
        _raw_response(),
        job_id="job-a",
        tenant_id="tenant-a",
        locale="ja-JP",
        raw_transcript_blob_uri="https://storage.example/raw.json",
        api_version="2025-11-01",
    )

    assert normalized["source"]["speechApi"] == "content-understanding"
    assert normalized["durationMilliseconds"] == 5440
    assert len(normalized["phrases"]) == 2
    assert normalized["phrases"][0]["speakerLabel"] == "Speaker 1"
    assert normalized["phrases"][0]["startTimeText"] == "00:00:00"
    assert normalized["phrases"][0]["endTimeText"] == "00:00:03"
    assert normalized["speakers"][0]["phraseCount"] == 1


def test_build_visual_context_keeps_video_metadata() -> None:
    visual_context = build_visual_context(_raw_response())

    assert visual_context["width"] == 640
    assert visual_context["height"] == 360
    assert visual_context["keyFrameTimesMs"] == [400, 1800]
    assert visual_context["cameraShotTimesMs"] == [760]


def test_normalize_content_understanding_transcript_rejects_missing_phrases() -> None:
    raw = {"result": {"contents": [{"kind": "audioVisual", "transcriptPhrases": []}]}}

    with pytest.raises(AppError) as exc_info:
        normalize_content_understanding_transcript(
            raw,
            job_id="job-a",
            tenant_id="tenant-a",
            locale="ja-JP",
            raw_transcript_blob_uri="https://storage.example/raw.json",
            api_version="2025-11-01",
        )

    assert exc_info.value.code == "CONTENT_UNDERSTANDING_TRANSCRIPT_MISSING"
