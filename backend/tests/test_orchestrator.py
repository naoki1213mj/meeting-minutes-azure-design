from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from MeetingMinutesOrchestrator import orchestrator_function


@dataclass(frozen=True)
class ActivityCall:
    name: str
    payload: object


@dataclass(frozen=True)
class TaskAllCall:
    tasks: list[ActivityCall]


@dataclass(frozen=True)
class TimerCall:
    fire_at: datetime


class FakeDurableContext:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload
        self.statuses: list[dict[str, object]] = []
        self.current_utc_datetime = datetime(2026, 6, 2, tzinfo=UTC)

    def get_input(self) -> dict[str, object]:
        return self._payload

    def set_custom_status(self, status: dict[str, object]) -> None:
        self.statuses.append(status)

    def call_activity(self, name: str, payload: object) -> ActivityCall:
        return ActivityCall(name, payload)

    def task_all(self, tasks: list[ActivityCall]) -> TaskAllCall:
        return TaskAllCall(tasks)

    def create_timer(self, fire_at: datetime) -> TimerCall:
        self.current_utc_datetime = fire_at
        return TimerCall(fire_at)


def test_orchestrator_uses_direct_minutes_generation_path() -> None:
    context = FakeDurableContext({"tenantId": "tenant-a", "jobId": "job-a"})
    generator = orchestrator_function(context)  # type: ignore[arg-type]
    job = {"tenantId": "tenant-a", "jobId": "job-a"}
    normalized = {"normalizedTranscriptBlobName": "normalized.json"}

    assert _next_activity(generator).name == "LoadJobActivity"
    assert _send_activity(generator, job).name == "ValidateInputActivity"
    assert _send_activity(generator, {"valid": True}).name == "CreateReadSasActivity"
    assert _send_activity(generator, {"audioUrl": "https://example.invalid/audio"}).name == (
        "TranscribeAudioActivity"
    )
    assert _send_activity(generator, {"rawTranscriptBlobName": "raw.json"}).name == (
        "NormalizeTranscriptActivity"
    )
    final_call = _send_activity(generator, normalized)
    assert final_call.name == "GenerateFinalMinutesActivity"
    assert isinstance(final_call.payload, dict)
    assert "chunkSummaries" not in final_call.payload
    assert final_call.payload == {"job": job, **normalized}


def test_orchestrator_routes_content_understanding_jobs_to_cu_activities() -> None:
    context = FakeDurableContext({"tenantId": "tenant-a", "jobId": "job-a"})
    generator = orchestrator_function(context)  # type: ignore[arg-type]
    job = {
        "tenantId": "tenant-a",
        "jobId": "job-a",
        "processingRoute": "contentUnderstanding",
    }
    operation = {"operationUrl": "https://example.invalid/operation"}
    running = {"status": "Running"}
    cu_raw = {
        "status": "Succeeded",
        "rawTranscriptBlobName": "cu.json",
        "visualContextBlobUri": "https://storage.example/visual.json",
    }
    normalized = {"normalizedTranscriptBlobName": "normalized.json"}

    assert _next_activity(generator).name == "LoadJobActivity"
    assert _send_activity(generator, job).name == "ValidateInputActivity"
    assert _send_activity(generator, {"valid": True}).name == "CreateReadSasActivity"
    analyze_call = _send_activity(generator, {"audioUrl": "https://example.invalid/video"})
    assert analyze_call.name == "AnalyzeContentUnderstandingActivity"
    assert analyze_call.payload == {"job": job, "contentUrl": "https://example.invalid/video"}
    poll_call = _send_activity(generator, operation)
    assert poll_call.name == "PollContentUnderstandingActivity"
    assert poll_call.payload == {"job": job, **operation}
    timer = generator.send(running)
    assert isinstance(timer, TimerCall)
    second_poll_call = generator.send(None)
    assert isinstance(second_poll_call, ActivityCall)
    assert second_poll_call.name == "PollContentUnderstandingActivity"
    normalize_call = _send_activity(generator, cu_raw)
    assert normalize_call.name == "NormalizeContentUnderstandingTranscriptActivity"
    assert normalize_call.payload == {"job": job, **cu_raw}
    final_call = _send_activity(generator, normalized)
    assert final_call.name == "GenerateFinalMinutesActivity"


def test_orchestrator_persists_content_understanding_failure_details() -> None:
    context = FakeDurableContext({"tenantId": "tenant-a", "jobId": "job-a"})
    generator = orchestrator_function(context)  # type: ignore[arg-type]
    job = {
        "tenantId": "tenant-a",
        "jobId": "job-a",
        "processingRoute": "contentUnderstanding",
    }
    operation = {"operationUrl": "https://example.invalid/operation"}
    failed = {
        "status": "Failed",
        "error": {
            "operationStatus": "Failed",
            "operationError": {"code": "InternalServerError"},
        },
    }

    assert _next_activity(generator).name == "LoadJobActivity"
    assert _send_activity(generator, job).name == "ValidateInputActivity"
    assert _send_activity(generator, {"valid": True}).name == "CreateReadSasActivity"
    assert _send_activity(generator, {"audioUrl": "https://example.invalid/video"}).name == (
        "AnalyzeContentUnderstandingActivity"
    )
    poll_call = _send_activity(generator, operation)
    assert poll_call.name == "PollContentUnderstandingActivity"
    fail_call = generator.send(failed)
    assert isinstance(fail_call, ActivityCall)
    assert fail_call.name == "FailJobActivity"
    assert fail_call.payload == {
        "tenantId": "tenant-a",
        "jobId": "job-a",
        "error": {
            "code": "CONTENT_UNDERSTANDING_FAILED",
            "message": "Content Understanding による動画解析に失敗しました。",
            "correlationId": "job-a",
            "details": failed["error"],
        },
    }


def test_orchestrator_continues_from_final_minutes_to_markdown_and_complete() -> None:
    context = FakeDurableContext({"tenantId": "tenant-a", "jobId": "job-a"})
    generator = orchestrator_function(context)  # type: ignore[arg-type]
    job = {"tenantId": "tenant-a", "jobId": "job-a"}
    normalized = {
        "normalizedTranscriptBlobName": "normalized.json",
        "normalizedTranscriptBlobUri": "https://storage.example/transcript/normalized.json",
    }
    minutes = {
        "minutesJsonBlobName": "minutes.json",
        "minutesJsonBlobUri": "https://storage.example/minutes/minutes.json",
    }
    markdown = {
        "minutesJsonBlobUri": "https://storage.example/minutes/minutes.json",
        "minutesMarkdownBlobUri": "https://storage.example/minutes/minutes.md",
    }
    complete_result = {"jobId": "job-a", "status": "DONE"}

    assert _next_activity(generator).name == "LoadJobActivity"
    assert _send_activity(generator, job).name == "ValidateInputActivity"
    assert _send_activity(generator, {"valid": True}).name == "CreateReadSasActivity"
    assert _send_activity(generator, {"audioUrl": "https://example.invalid/audio"}).name == (
        "TranscribeAudioActivity"
    )
    assert _send_activity(generator, {"rawTranscriptBlobName": "raw.json"}).name == (
        "NormalizeTranscriptActivity"
    )
    final_call = _send_activity(generator, normalized)
    assert final_call.name == "GenerateFinalMinutesActivity"

    render_call = _send_activity(generator, minutes)
    assert render_call.name == "RenderMarkdownActivity"
    assert render_call.payload == {"job": job, **minutes}

    complete_call = _send_activity(generator, markdown)
    assert complete_call.name == "CompleteJobActivity"
    assert complete_call.payload == {"tenantId": "tenant-a", "jobId": "job-a", **markdown}

    assert _finish_generator(generator, complete_result) == complete_result
    assert context.statuses[-1] == {"step": "DONE", "percent": 100}

def test_orchestrator_activity_names_have_v1_wrappers() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    activity_names = {
        "LoadJobActivity",
        "ValidateInputActivity",
        "CreateReadSasActivity",
        "AnalyzeContentUnderstandingActivity",
        "PollContentUnderstandingActivity",
        "TranscribeAudioActivity",
        "NormalizeTranscriptActivity",
        "NormalizeContentUnderstandingTranscriptActivity",
        "BuildTranscriptChunksActivity",
        "GenerateChunkSummaryActivity",
        "GenerateFinalMinutesActivity",
        "RenderMarkdownActivity",
        "CompleteJobActivity",
        "FailJobActivity",
    }

    for activity_name in activity_names:
        assert (backend_root / activity_name / "__init__.py").is_file()
        assert (backend_root / activity_name / "function.json").is_file()


def _next_activity(generator: Generator[object, object, object]) -> ActivityCall:
    call = next(generator)
    assert isinstance(call, ActivityCall)
    return call


def _send_activity(generator: Generator[object, object, object], value: object) -> ActivityCall:
    call = generator.send(value)
    assert isinstance(call, ActivityCall)
    return call


def _finish_generator(generator: Generator[object, object, object], value: object) -> object:
    try:
        generator.send(value)
    except StopIteration as exc:
        return exc.value
    raise AssertionError("orchestrator generator did not finish")
