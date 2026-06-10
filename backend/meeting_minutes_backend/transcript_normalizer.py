from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from typing import Any

from jsonschema import Draft202012Validator

from meeting_minutes_backend.schema_paths import find_specs_dir

NORMALIZED_TRANSCRIPT_SCHEMA = find_specs_dir() / "normalized-transcript.schema.json"
ISO_DURATION_PATTERN = re.compile(
    r"^PT(?:(?P<hours>\d+(?:\.\d+)?)H)?(?:(?P<minutes>\d+(?:\.\d+)?)M)?(?:(?P<seconds>\d+(?:\.\d+)?)S)?$"
)


def normalize_transcript(
    raw_response: dict[str, Any],
    job_id: str,
    tenant_id: str,
    locale: str,
    raw_transcript_blob_uri: str,
    api_version: str,
) -> dict[str, Any]:
    phrases = raw_response.get("phrases", [])
    if not isinstance(phrases, list):
        raise TypeError("phrases must be an array")

    normalized_phrases = [_normalize_phrase(index, phrase) for index, phrase in enumerate(phrases)]
    duration_milliseconds = _duration_milliseconds(raw_response, normalized_phrases)
    normalized = {
        "jobId": job_id,
        "tenantId": tenant_id,
        "locale": locale,
        "source": {
            "speechApi": "fast-transcription",
            "apiVersion": api_version,
            "rawTranscriptBlobUri": raw_transcript_blob_uri,
        },
        "durationMilliseconds": duration_milliseconds,
        "speakers": _build_speakers(normalized_phrases),
        "phrases": normalized_phrases,
    }
    validate_normalized_transcript(normalized)
    return normalized


def normalize_batch_transcript(
    raw_response: dict[str, Any],
    job_id: str,
    tenant_id: str,
    locale: str,
    raw_transcript_blob_uri: str,
    api_version: str,
) -> dict[str, Any]:
    recognized_phrases = raw_response.get("recognizedPhrases", [])
    if not isinstance(recognized_phrases, list):
        raise TypeError("recognizedPhrases must be an array")
    phrases = [
        _normalize_batch_phrase(index, phrase)
        for index, phrase in enumerate(recognized_phrases)
    ]
    normalized = {
        "jobId": job_id,
        "tenantId": tenant_id,
        "locale": locale,
        "source": {
            "speechApi": "batch-transcription",
            "apiVersion": api_version,
            "rawTranscriptBlobUri": raw_transcript_blob_uri,
        },
        "durationMilliseconds": _batch_duration_milliseconds(raw_response, phrases),
        "speakers": _build_speakers(phrases),
        "phrases": phrases,
    }
    validate_normalized_transcript(normalized)
    return normalized


def validate_normalized_transcript(normalized: dict[str, Any]) -> None:
    schema = json.loads(NORMALIZED_TRANSCRIPT_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(normalized)


def _normalize_phrase(index: int, phrase: object) -> dict[str, Any]:
    if not isinstance(phrase, dict):
        raise TypeError("phrase must be an object")

    offset = _int_value(phrase.get("offsetMilliseconds"), 0)
    duration = _int_value(phrase.get("durationMilliseconds"), 0)
    text = str(phrase.get("text", ""))
    speaker_value = phrase.get("speaker")
    speaker_label = f"Speaker {speaker_value}" if speaker_value is not None else "Unknown"
    confidence = phrase.get("confidence")

    normalized = {
        "phraseId": _phrase_id(index, offset, speaker_label, text),
        "speakerLabel": speaker_label,
        "displayName": None,
        "offsetMilliseconds": offset,
        "durationMilliseconds": duration,
        "startTimeText": _format_timestamp(offset),
        "endTimeText": _format_timestamp(offset + duration),
        "text": text,
        "confidence": confidence if isinstance(confidence, int | float) else None,
    }
    return normalized


def _normalize_batch_phrase(index: int, phrase: object) -> dict[str, Any]:
    if not isinstance(phrase, dict):
        raise TypeError("phrase must be an object")
    offset = _ticks_to_milliseconds(phrase.get("offsetInTicks"))
    if offset == 0:
        offset = _duration_text_to_milliseconds(phrase.get("offset"))
    duration = _ticks_to_milliseconds(phrase.get("durationInTicks"))
    if duration == 0:
        duration = _duration_text_to_milliseconds(phrase.get("duration"))
    speaker_value = phrase.get("speaker")
    speaker_label = f"Speaker {speaker_value}" if speaker_value is not None else "Unknown"
    nbest = phrase.get("nBest")
    best = nbest[0] if isinstance(nbest, list) and nbest and isinstance(nbest[0], dict) else {}
    text = str(best.get("display") or phrase.get("display") or "")
    confidence = best.get("confidence")
    return {
        "phraseId": _phrase_id(index, offset, speaker_label, text),
        "speakerLabel": speaker_label,
        "displayName": None,
        "offsetMilliseconds": offset,
        "durationMilliseconds": duration,
        "startTimeText": _format_timestamp(offset),
        "endTimeText": _format_timestamp(offset + duration),
        "text": text,
        "confidence": confidence if isinstance(confidence, int | float) else None,
    }


def _build_speakers(phrases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for phrase in phrases:
        grouped[str(phrase["speakerLabel"])].append(phrase)

    speakers = []
    for speaker_label, speaker_phrases in sorted(grouped.items()):
        speakers.append(
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
        )
    return speakers


def _duration_milliseconds(raw_response: dict[str, Any], phrases: list[dict[str, Any]]) -> int:
    raw_duration = raw_response.get("durationMilliseconds")
    if isinstance(raw_duration, int) and raw_duration >= 0:
        return raw_duration
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
    return f"p{index:05d}-{digest}"


def _int_value(value: object, default: int) -> int:
    return value if isinstance(value, int) else default


def _ticks_to_milliseconds(value: object) -> int:
    if isinstance(value, int | float):
        return max(0, int(value // 10_000))
    return 0


def _duration_text_to_milliseconds(value: object) -> int:
    if not isinstance(value, str):
        return 0
    match = ISO_DURATION_PATTERN.fullmatch(value)
    if match is None:
        return 0
    try:
        hours = float(match.group("hours") or 0)
        minutes = float(match.group("minutes") or 0)
        seconds = float(match.group("seconds") or 0)
    except ValueError:
        return 0
    return int(((hours * 60 * 60) + (minutes * 60) + seconds) * 1000)


def _batch_duration_milliseconds(
    raw_response: dict[str, Any],
    phrases: list[dict[str, Any]],
) -> int:
    duration_from_ticks = _ticks_to_milliseconds(raw_response.get("durationInTicks"))
    if duration_from_ticks:
        return duration_from_ticks
    duration_from_text = _duration_text_to_milliseconds(raw_response.get("duration"))
    if duration_from_text:
        return duration_from_text
    return _duration_milliseconds(raw_response, phrases)
