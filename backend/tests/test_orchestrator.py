from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

from MeetingMinutesOrchestrator import MAX_CHUNK_SUMMARY_BATCH_SIZE, orchestrator_function


@dataclass(frozen=True)
class ActivityCall:
    name: str
    payload: object


@dataclass(frozen=True)
class TaskAllCall:
    tasks: list[ActivityCall]


class FakeDurableContext:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload
        self.statuses: list[dict[str, object]] = []

    def get_input(self) -> dict[str, object]:
        return self._payload

    def set_custom_status(self, status: dict[str, object]) -> None:
        self.statuses.append(status)

    def call_activity(self, name: str, payload: object) -> ActivityCall:
        return ActivityCall(name, payload)

    def task_all(self, tasks: list[ActivityCall]) -> TaskAllCall:
        return TaskAllCall(tasks)


def test_orchestrator_fans_out_chunk_summary_activities() -> None:
    context = FakeDurableContext({"tenantId": "tenant-a", "jobId": "job-a"})
    generator = orchestrator_function(context)  # type: ignore[arg-type]
    job = {"tenantId": "tenant-a", "jobId": "job-a"}
    normalized = {"normalizedTranscriptBlobName": "normalized.json"}
    chunks = [
        {"chunkIndex": 0, "chunkBlobName": "chunk-0.json"},
        {"chunkIndex": 1, "chunkBlobName": "chunk-1.json"},
    ]
    summaries = [
        {"chunkIndex": 0, "chunkSummaryBlobName": "summary-0.json"},
        {"chunkIndex": 1, "chunkSummaryBlobName": "summary-1.json"},
    ]

    assert _next_activity(generator).name == "LoadJobActivity"
    assert _send_activity(generator, job).name == "ValidateInputActivity"
    assert _send_activity(generator, {"valid": True}).name == "CreateReadSasActivity"
    assert _send_activity(generator, {"audioUrl": "https://example.invalid/audio"}).name == (
        "TranscribeAudioActivity"
    )
    assert _send_activity(generator, {"rawTranscriptBlobName": "raw.json"}).name == (
        "NormalizeTranscriptActivity"
    )
    assert _send_activity(generator, normalized).name == "BuildTranscriptChunksActivity"

    task_all = generator.send(chunks)
    assert isinstance(task_all, TaskAllCall)
    assert [task.name for task in task_all.tasks] == [
        "GenerateChunkSummaryActivity",
        "GenerateChunkSummaryActivity",
    ]

    final_call = generator.send(summaries)
    assert isinstance(final_call, ActivityCall)
    assert final_call.name == "GenerateFinalMinutesActivity"
    assert isinstance(final_call.payload, dict)
    assert final_call.payload["chunkSummaries"] == summaries


def test_orchestrator_batches_chunk_summary_fan_out() -> None:
    context = FakeDurableContext({"tenantId": "tenant-a", "jobId": "job-a"})
    generator = orchestrator_function(context)  # type: ignore[arg-type]
    job = {"tenantId": "tenant-a", "jobId": "job-a"}
    normalized = {"normalizedTranscriptBlobName": "normalized.json"}
    chunks = [
        {"chunkIndex": index, "chunkBlobName": f"chunk-{index}.json"}
        for index in range(MAX_CHUNK_SUMMARY_BATCH_SIZE + 2)
    ]
    first_summaries = [
        {"chunkIndex": index, "chunkSummaryBlobName": f"summary-{index}.json"}
        for index in range(MAX_CHUNK_SUMMARY_BATCH_SIZE)
    ]
    second_summaries = [
        {"chunkIndex": index, "chunkSummaryBlobName": f"summary-{index}.json"}
        for index in range(MAX_CHUNK_SUMMARY_BATCH_SIZE, MAX_CHUNK_SUMMARY_BATCH_SIZE + 2)
    ]

    assert _next_activity(generator).name == "LoadJobActivity"
    assert _send_activity(generator, job).name == "ValidateInputActivity"
    assert _send_activity(generator, {"valid": True}).name == "CreateReadSasActivity"
    assert _send_activity(generator, {"audioUrl": "https://example.invalid/audio"}).name == (
        "TranscribeAudioActivity"
    )
    assert _send_activity(generator, {"rawTranscriptBlobName": "raw.json"}).name == (
        "NormalizeTranscriptActivity"
    )
    assert _send_activity(generator, normalized).name == "BuildTranscriptChunksActivity"

    first_task_all = generator.send(chunks)
    assert isinstance(first_task_all, TaskAllCall)
    assert len(first_task_all.tasks) == MAX_CHUNK_SUMMARY_BATCH_SIZE

    second_task_all = generator.send(first_summaries)
    assert isinstance(second_task_all, TaskAllCall)
    assert len(second_task_all.tasks) == 2

    final_call = generator.send(second_summaries)
    assert isinstance(final_call, ActivityCall)
    assert final_call.name == "GenerateFinalMinutesActivity"
    assert isinstance(final_call.payload, dict)
    assert final_call.payload["chunkSummaries"] == [*first_summaries, *second_summaries]


def test_orchestrator_continues_from_final_minutes_to_markdown_and_complete() -> None:
    context = FakeDurableContext({"tenantId": "tenant-a", "jobId": "job-a"})
    generator = orchestrator_function(context)  # type: ignore[arg-type]
    job = {"tenantId": "tenant-a", "jobId": "job-a"}
    normalized = {
        "normalizedTranscriptBlobName": "normalized.json",
        "normalizedTranscriptBlobUri": "https://storage.example/transcript/normalized.json",
    }
    chunks = [{"chunkIndex": 0, "chunkBlobName": "chunk-0.json"}]
    summaries = [{"chunkIndex": 0, "chunkSummaryBlobName": "summary-0.json"}]
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
    assert _send_activity(generator, normalized).name == "BuildTranscriptChunksActivity"
    task_all = generator.send(chunks)
    assert isinstance(task_all, TaskAllCall)

    final_call = generator.send(summaries)
    assert isinstance(final_call, ActivityCall)
    assert final_call.name == "GenerateFinalMinutesActivity"

    render_call = _send_activity(generator, minutes)
    assert render_call.name == "RenderMarkdownActivity"
    assert render_call.payload == {"job": job, **minutes}

    complete_call = _send_activity(generator, markdown)
    assert complete_call.name == "CompleteJobActivity"
    assert complete_call.payload == {"tenantId": "tenant-a", "jobId": "job-a", **markdown}

    assert _finish_generator(generator, complete_result) == complete_result
    assert context.statuses[-1] == {"step": "DONE", "percent": 100}


def test_orchestrator_skips_task_all_for_empty_chunks() -> None:
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
    assert _send_activity(generator, normalized).name == "BuildTranscriptChunksActivity"

    final_call = generator.send([])
    assert isinstance(final_call, ActivityCall)
    assert final_call.name == "GenerateFinalMinutesActivity"
    assert isinstance(final_call.payload, dict)
    assert final_call.payload["chunkSummaries"] == []


def test_orchestrator_activity_names_have_v1_wrappers() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    activity_names = {
        "LoadJobActivity",
        "ValidateInputActivity",
        "CreateReadSasActivity",
        "TranscribeAudioActivity",
        "NormalizeTranscriptActivity",
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
