from collections.abc import Generator
from typing import cast

import azure.durable_functions as df

from meeting_minutes_backend.workflow import serialize_workflow_error

MAX_CHUNK_SUMMARY_BATCH_SIZE = 3


def orchestrator_function(
    context: df.DurableOrchestrationContext,
) -> Generator[object, object, object]:
    input_value = context.get_input()
    payload = input_value if isinstance(input_value, dict) else {}
    try:
        context.set_custom_status({"step": "LOADING_JOB", "percent": 1})
        job = yield context.call_activity("LoadJobActivity", payload)
        if not isinstance(job, dict):
            raise TypeError("LoadJobActivity must return an object")

        context.set_custom_status({"step": "VALIDATING", "percent": 5})
        yield context.call_activity("ValidateInputActivity", job)

        context.set_custom_status({"step": "CREATING_AUDIO_READ_URL", "percent": 10})
        read_sas = yield context.call_activity("CreateReadSasActivity", job)
        if not isinstance(read_sas, dict):
            raise TypeError("CreateReadSasActivity must return an object")

        context.set_custom_status({"step": "TRANSCRIBING", "percent": 20})
        raw_transcript = yield context.call_activity(
            "TranscribeAudioActivity",
            {"job": job, "audioUrl": read_sas["audioUrl"]},
        )
        if not isinstance(raw_transcript, dict):
            raise TypeError("TranscribeAudioActivity must return an object")

        context.set_custom_status({"step": "NORMALIZING_TRANSCRIPT", "percent": 55})
        normalized = yield context.call_activity(
            "NormalizeTranscriptActivity",
            {"job": job, **raw_transcript},
        )
        if not isinstance(normalized, dict):
            raise TypeError("NormalizeTranscriptActivity must return an object")

        context.set_custom_status({"step": "GENERATING_CHUNK_SUMMARIES", "percent": 65})
        chunks = yield context.call_activity(
            "BuildTranscriptChunksActivity",
            {"job": job, **normalized},
        )
        if not isinstance(chunks, list):
            raise TypeError("BuildTranscriptChunksActivity must return a list")

        chunk_summaries: list[object] = []
        if chunks:
            for batch_start in range(0, len(chunks), MAX_CHUNK_SUMMARY_BATCH_SIZE):
                chunk_batch = chunks[
                    batch_start : batch_start + MAX_CHUNK_SUMMARY_BATCH_SIZE
                ]
                summary_tasks = [
                    context.call_activity(
                        "GenerateChunkSummaryActivity",
                        {"job": job, **chunk},
                    )
                    for chunk in chunk_batch
                    if isinstance(chunk, dict)
                ]
                chunk_summaries_result = yield context.task_all(summary_tasks)
                if not isinstance(chunk_summaries_result, list):
                    raise TypeError("GenerateChunkSummaryActivity must return a list")
                chunk_summaries.extend(cast(list[object], chunk_summaries_result))

        context.set_custom_status({"step": "GENERATING_FINAL_MINUTES", "percent": 75})
        minutes = yield context.call_activity(
            "GenerateFinalMinutesActivity",
            {"job": job, **normalized, "chunkSummaries": chunk_summaries},
        )
        if not isinstance(minutes, dict):
            raise TypeError("GenerateFinalMinutesActivity must return an object")

        context.set_custom_status({"step": "RENDERING_MARKDOWN", "percent": 90})
        markdown = yield context.call_activity(
            "RenderMarkdownActivity",
            {"job": job, **minutes},
        )
        if not isinstance(markdown, dict):
            raise TypeError("RenderMarkdownActivity must return an object")

        context.set_custom_status({"step": "DONE", "percent": 100})
        result = yield context.call_activity(
            "CompleteJobActivity",
            {
                "tenantId": job["tenantId"],
                "jobId": job["jobId"],
                **markdown,
            },
        )
        return result
    except Exception as error:
        correlation_id = str(payload.get("correlationId", payload.get("jobId", "unknown")))
        result = yield context.call_activity(
            "FailJobActivity",
            {
                "tenantId": payload.get("tenantId"),
                "jobId": payload.get("jobId"),
                "error": serialize_workflow_error(error, correlation_id),
            },
        )
        return result


main = df.Orchestrator.create(orchestrator_function)
