from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

from meeting_minutes_backend.errors import AppError
from meeting_minutes_backend.transcript_normalizer import validate_normalized_transcript


def normalize_content_understanding_transcript(
    raw_response: dict[str, Any],
    job_id: str,
    tenant_id: str,
    locale: str,
    raw_transcript_blob_uri: str,
    api_version: str,
) -> dict[str, Any]:
    content = _audio_visual_content(raw_response)
    transcript_phrases = content.get("transcriptPhrases")
    if not isinstance(transcript_phrases, list) or not transcript_phrases:
        raise AppError(
            code="CONTENT_UNDERSTANDING_TRANSCRIPT_MISSING",
            message="Content Understanding の解析結果に文字起こしが含まれていません。",
            http_status=502,
        )
    normalized_phrases = [
        _normalize_phrase(index, phrase) for index, phrase in enumerate(transcript_phrases)
    ]
    normalized = {
        "jobId": job_id,
        "tenantId": tenant_id,
        "locale": locale,
        "source": {
            "speechApi": "content-understanding",
            "apiVersion": api_version,
            "rawTranscriptBlobUri": raw_transcript_blob_uri,
        },
        "durationMilliseconds": _duration_milliseconds(content, normalized_phrases),
        "speakers": _build_speakers(normalized_phrases),
        "phrases": normalized_phrases,
    }
    validate_normalized_transcript(normalized)
    return normalized


def build_visual_context(raw_response: dict[str, Any]) -> dict[str, Any]:
    content = _audio_visual_content(raw_response)
    return {
        "kind": content.get("kind"),
        "startTimeMs": content.get("startTimeMs"),
        "endTimeMs": content.get("endTimeMs"),
        "width": content.get("width"),
        "height": content.get("height"),
        "markdown": content.get("markdown"),
        "fields": content.get("fields"),
        "keyFrameTimesMs": content.get("keyFrameTimesMs"),
        "cameraShotTimesMs": content.get("cameraShotTimesMs"),
    }


def _audio_visual_content(raw_response: dict[str, Any]) -> dict[str, Any]:
    result = raw_response.get("result")
    if not isinstance(result, dict):
        raise TypeError("Content Understanding result must be an object")
    contents = result.get("contents")
    if not isinstance(contents, list):
        raise TypeError("Content Understanding contents must be an array")
    for item in contents:
        if isinstance(item, dict) and item.get("kind") == "audioVisual":
            return item
    raise AppError(
        code="CONTENT_UNDERSTANDING_AUDIO_VISUAL_MISSING",
        message="Content Understanding の解析結果に音声/動画コンテンツが含まれていません。",
        http_status=502,
    )


def _normalize_phrase(index: int, phrase: object) -> dict[str, Any]:
    if not isinstance(phrase, dict):
        raise TypeError("transcript phrase must be an object")
    start_ms = _int_value(phrase.get("startTimeMs"), 0)
    end_ms = _int_value(phrase.get("endTimeMs"), start_ms)
    duration_ms = max(0, end_ms - start_ms)
    text = str(phrase.get("text", ""))
    speaker_label = str(phrase.get("speaker") or "Unknown")
    return {
        "phraseId": _phrase_id(index, start_ms, speaker_label, text),
        "speakerLabel": speaker_label,
        "displayName": None,
        "offsetMilliseconds": start_ms,
        "durationMilliseconds": duration_ms,
        "startTimeText": _format_timestamp(start_ms),
        "endTimeText": _format_timestamp(start_ms + duration_ms),
        "text": text,
        "confidence": None,
    }


def _build_speakers(phrases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for phrase in phrases:
        grouped[str(phrase["speakerLabel"])].append(phrase)
    return [
        {
            "speakerLabel": speaker_label,
            "displayName": None,
            "phraseCount": len(speaker_phrases),
            "representativePhrases": [
                {
                    "offsetMilliseconds": phrase["offsetMilliseconds"],
                    "startTimeText": phrase["startTimeText"],
                    "text": phrase["text"],
                }
                for phrase in speaker_phrases[:10]
            ],
        }
        for speaker_label, speaker_phrases in sorted(grouped.items())
    ]


def _duration_milliseconds(content: dict[str, Any], phrases: list[dict[str, Any]]) -> int:
    end_time = content.get("endTimeMs")
    start_time = content.get("startTimeMs")
    if isinstance(end_time, int) and isinstance(start_time, int) and end_time >= start_time:
        return end_time - start_time
    if not phrases:
        return 0
    return max(
        int(phrase["offsetMilliseconds"]) + int(phrase["durationMilliseconds"])
        for phrase in phrases
    )


def _format_timestamp(milliseconds: int) -> str:
    total_seconds = max(0, milliseconds // 1000)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02}:{minutes:02}:{seconds:02}"


def _phrase_id(index: int, offset: int, speaker_label: str, text: str) -> str:
    digest = hashlib.sha256(f"{offset}|{speaker_label}|{text}".encode()).hexdigest()[:12]
    return f"cu{index:05d}-{digest}"


def _int_value(value: object, default: int) -> int:
    return value if isinstance(value, int) else default
