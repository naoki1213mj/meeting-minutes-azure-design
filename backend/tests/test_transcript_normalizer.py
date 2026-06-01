from __future__ import annotations

from meeting_minutes_backend.transcript_normalizer import normalize_transcript


def test_normalize_transcript_with_speakers_validates_schema() -> None:
    normalized = normalize_transcript(
        raw_response={
            "durationMilliseconds": 2500,
            "phrases": [
                {
                    "speaker": 1,
                    "offsetMilliseconds": 0,
                    "durationMilliseconds": 1000,
                    "text": "こんにちは。",
                    "confidence": 0.9,
                },
                {
                    "speaker": 2,
                    "offsetMilliseconds": 1500,
                    "durationMilliseconds": 1000,
                    "text": "よろしくお願いします。",
                    "confidence": 0.8,
                },
            ],
        },
        job_id="job-a",
        tenant_id="tenant-a",
        locale="ja-JP",
        raw_transcript_blob_uri="transcript/raw/tenant-a/job-a/speech-response.json",
        api_version="2025-10-15",
    )

    assert normalized["durationMilliseconds"] == 2500
    assert len(normalized["phrases"]) == 2
    assert normalized["phrases"][0]["speakerLabel"] == "Speaker 1"
    assert normalized["phrases"][0]["startTimeText"] == "00:00:00"
    assert normalized["phrases"][1]["startTimeText"] == "00:00:01"
    assert len(normalized["speakers"]) == 2


def test_normalize_transcript_handles_unknown_speaker_and_empty_phrases() -> None:
    normalized = normalize_transcript(
        raw_response={
            "phrases": [
                {
                    "offsetMilliseconds": 0,
                    "durationMilliseconds": 1000,
                    "text": "話者不明です。",
                }
            ]
        },
        job_id="job-a",
        tenant_id="tenant-a",
        locale="ja-JP",
        raw_transcript_blob_uri="transcript/raw/tenant-a/job-a/speech-response.json",
        api_version="2025-10-15",
    )

    assert normalized["durationMilliseconds"] == 1000
    assert normalized["phrases"][0]["speakerLabel"] == "Unknown"
    assert normalized["speakers"][0]["speakerLabel"] == "Unknown"

    empty = normalize_transcript(
        raw_response={"phrases": []},
        job_id="job-a",
        tenant_id="tenant-a",
        locale="ja-JP",
        raw_transcript_blob_uri="transcript/raw/tenant-a/job-a/speech-response.json",
        api_version="2025-10-15",
    )
    assert empty["durationMilliseconds"] == 0
    assert empty["speakers"] == []
