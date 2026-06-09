from __future__ import annotations

from collections.abc import Iterable

from meeting_minutes_backend.errors import AppError
from meeting_minutes_backend.models import JobStatus


def load_job_activity(payload: dict[str, object]) -> dict[str, object]:
    tenant_id = _required_string(payload, "tenantId")
    job_id = _required_string(payload, "jobId")
    user_id = _required_string(payload, "userId")
    return {
        "tenantId": tenant_id,
        "jobId": job_id,
        "userId": user_id,
        "rawAudioBlobUri": f"raw-audio/{tenant_id}/{job_id}/input.mp3",
        "locale": payload.get("locale", "ja-JP"),
        "maxSpeakers": payload.get("maxSpeakers", 8),
    }


def validate_input_activity(job: dict[str, object]) -> dict[str, object]:
    return {
        "jobId": _required_string(job, "jobId"),
        "valid": True,
        "message": "Input accepted for workflow skeleton.",
    }


def create_read_sas_activity(job: dict[str, object]) -> dict[str, object]:
    tenant_id = _required_string(job, "tenantId")
    job_id = _required_string(job, "jobId")
    return {
        "audioUrl": f"https://local.blob.invalid/raw-audio/{tenant_id}/{job_id}/input.mp3?sig=stub"
    }


def transcribe_audio_activity(payload: dict[str, object]) -> dict[str, object]:
    job = _required_dict(payload, "job")
    tenant_id = _required_string(job, "tenantId")
    job_id = _required_string(job, "jobId")
    return {
        "rawTranscriptBlobUri": f"transcript/raw/{tenant_id}/{job_id}/speech-response.json",
    }


def normalize_transcript_activity(payload: dict[str, object]) -> dict[str, object]:
    raw_transcript_blob_uri = _required_string(payload, "rawTranscriptBlobUri")
    normalized_transcript_blob_uri = raw_transcript_blob_uri.replace(
        "transcript/raw/", "transcript/normalized/"
    ).replace("speech-response.json", "normalized-transcript.json")
    return {
        "normalizedTranscriptBlobUri": normalized_transcript_blob_uri,
    }


def build_transcript_chunks_activity(payload: dict[str, object]) -> list[dict[str, object]]:
    normalized_uri = _required_string(payload, "normalizedTranscriptBlobUri")
    return [
        {
            "chunkIndex": 0,
            "startOffsetMilliseconds": 0,
            "endOffsetMilliseconds": 300_000,
            "blobUri": normalized_uri.replace("normalized-transcript.json", "chunks/chunk-0.json"),
        }
    ]


def generate_chunk_summary_activity(chunk: dict[str, object]) -> dict[str, object]:
    chunk_index_value = chunk["chunkIndex"]
    if not isinstance(chunk_index_value, int):
        raise TypeError("chunkIndex must be an integer")
    chunk_index = chunk_index_value
    blob_uri = _required_string(chunk, "blobUri")
    return {
        "chunkIndex": chunk_index,
        "chunkSummaryBlobUri": blob_uri.replace(
            f"chunks/chunk-{chunk_index}.json",
            f"summaries/chunk-{chunk_index}-summary.json",
        ),
    }


def generate_final_minutes_activity(payload: dict[str, object]) -> dict[str, object]:
    job = _required_dict(payload, "job")
    tenant_id = _required_string(job, "tenantId")
    job_id = _required_string(job, "jobId")
    chunk_summary_uris = payload.get("chunkSummaryUris", [])
    if not isinstance(chunk_summary_uris, list):
        raise TypeError("chunkSummaryUris must be a list")
    return {
        "minutesJsonBlobUri": f"minutes/{tenant_id}/{job_id}/minutes.json",
        "chunkSummaryCount": len(chunk_summary_uris),
    }


def render_markdown_activity(payload: dict[str, object]) -> dict[str, object]:
    minutes_json_blob_uri = _required_string(payload, "minutesJsonBlobUri")
    return {
        "minutesMarkdownBlobUri": minutes_json_blob_uri.replace("minutes.json", "minutes.md"),
    }


def persist_action_items_activity(payload: dict[str, object]) -> dict[str, object]:
    _required_string(payload, "minutesJsonBlobUri")
    return {"actionItemsCount": 0}


def complete_job_activity(payload: dict[str, object]) -> dict[str, object]:
    return {
        "jobId": _required_string(payload, "jobId"),
        "status": JobStatus.DONE.value,
        "minutesJsonBlobUri": _required_string(payload, "minutesJsonBlobUri"),
        "minutesMarkdownBlobUri": _required_string(payload, "minutesMarkdownBlobUri"),
    }


def fail_job_activity(payload: dict[str, object]) -> dict[str, object]:
    return {
        "jobId": _required_string(payload, "jobId"),
        "status": JobStatus.FAILED.value,
        "error": payload.get(
            "error",
            {
                "code": "INTERNAL_ERROR",
                "message": "Workflow failed.",
                "correlationId": _required_string(payload, "correlationId"),
            },
        ),
    }


def run_sample_workflow(payload: dict[str, object]) -> dict[str, object]:
    job = load_job_activity(payload)
    validate_input_activity(job)
    read_sas = create_read_sas_activity(job)
    raw_transcript = transcribe_audio_activity({"job": job, "audioUrl": read_sas["audioUrl"]})
    normalized = normalize_transcript_activity(raw_transcript)
    chunks = build_transcript_chunks_activity(normalized)
    chunk_summaries = [generate_chunk_summary_activity(chunk) for chunk in chunks]
    minutes = generate_final_minutes_activity({"job": job, "chunkSummaryUris": chunk_summaries})
    markdown = render_markdown_activity(minutes)
    persist_action_items_activity(minutes)
    return complete_job_activity(
        {
            "jobId": job["jobId"],
            "minutesJsonBlobUri": minutes["minutesJsonBlobUri"],
            "minutesMarkdownBlobUri": markdown["minutesMarkdownBlobUri"],
        }
    )


def serialize_workflow_error(error: Exception, correlation_id: str) -> dict[str, object]:
    if isinstance(error, AppError):
        serialized: dict[str, object] = {
            "code": error.code,
            "message": error.message,
            "correlationId": correlation_id,
        }
        if error.details:
            serialized["details"] = error.details
        return serialized

    return {
        "code": error.__class__.__name__,
        "message": str(error) or "Workflow failed.",
        "correlationId": correlation_id,
    }


def _required_string(payload: dict[str, object], key: str) -> str:
    value = payload[key]
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string")
    return value


def _required_dict(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload[key]
    if not isinstance(value, dict):
        raise TypeError(f"{key} must be an object")
    return value


def chunk_summary_uris(chunk_summaries: Iterable[dict[str, object]]) -> list[str]:
    return [_required_string(summary, "chunkSummaryBlobUri") for summary in chunk_summaries]
