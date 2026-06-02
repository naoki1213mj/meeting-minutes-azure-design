from __future__ import annotations

from function_app import app
from meeting_minutes_backend.models import JobStatus
from meeting_minutes_backend.workflow import (
    build_transcript_chunks_activity,
    fail_job_activity,
    run_sample_workflow,
)


def test_run_sample_workflow_reaches_done() -> None:
    result = run_sample_workflow(
        {
            "tenantId": "tenant-a",
            "jobId": "job-a",
            "userId": "user-a",
            "correlationId": "corr-a",
        }
    )

    assert result["status"] == JobStatus.DONE.value
    assert result["jobId"] == "job-a"
    assert result["minutesJsonBlobUri"] == "minutes/tenant-a/job-a/minutes.json"
    assert result["minutesMarkdownBlobUri"] == "minutes/tenant-a/job-a/minutes.md"


def test_fail_job_activity_returns_failed() -> None:
    result = fail_job_activity(
        {
            "jobId": "job-a",
            "correlationId": "corr-a",
            "error": {
                "code": "TRANSCRIPTION_FAILED",
                "message": "Transcription failed.",
                "correlationId": "corr-a",
            },
        }
    )

    assert result["status"] == JobStatus.FAILED.value
    assert result["jobId"] == "job-a"


def test_build_transcript_chunks_returns_at_least_one_chunk() -> None:
    chunks = build_transcript_chunks_activity(
        {
            "normalizedTranscriptBlobUri": (
                "transcript/normalized/tenant-a/job-a/normalized-transcript.json"
            )
        }
    )

    assert len(chunks) == 1
    assert chunks[0]["chunkIndex"] == 0


def test_http_functions_are_registered() -> None:
    function_names = {function.get_function_name() for function in app.get_functions()}

    expected = {
        "health",
        "create_job",
        "get_job",
        "get_transcript",
        "get_visual_context",
        "get_minutes",
        "complete_upload",
    }

    assert expected.issubset(function_names)
