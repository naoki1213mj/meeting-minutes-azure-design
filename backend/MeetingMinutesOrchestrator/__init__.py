from collections.abc import Generator
from datetime import timedelta

import azure.durable_functions as df

from meeting_minutes_backend.workflow import serialize_workflow_error

MAX_CHUNK_SUMMARY_BATCH_SIZE = 3
CONTENT_UNDERSTANDING_POLL_INTERVAL_SECONDS = 30
CONTENT_UNDERSTANDING_MAX_POLLS = 240


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

        if job.get("processingRoute") == "contentUnderstanding":
            context.set_custom_status({"step": "ANALYZING_CONTENT", "percent": 20})
            operation = yield context.call_activity(
                "AnalyzeContentUnderstandingActivity",
                {"job": job, "contentUrl": read_sas["audioUrl"]},
            )
            if not isinstance(operation, dict):
                raise TypeError("AnalyzeContentUnderstandingActivity must return an object")

            raw_transcript: object = None
            for _attempt in range(CONTENT_UNDERSTANDING_MAX_POLLS):
                poll_result = yield context.call_activity(
                    "PollContentUnderstandingActivity",
                    {"job": job, **operation},
                )
                if not isinstance(poll_result, dict):
                    raise TypeError("PollContentUnderstandingActivity must return an object")
                if poll_result.get("status") == "Succeeded":
                    raw_transcript = poll_result
                    break
                deadline = context.current_utc_datetime + timedelta(
                    seconds=CONTENT_UNDERSTANDING_POLL_INTERVAL_SECONDS
                )
                yield context.create_timer(deadline)
            if raw_transcript is None:
                raise TimeoutError("Content Understanding analysis timed out")
            if not isinstance(raw_transcript, dict):
                raise TypeError("AnalyzeContentUnderstandingActivity must return an object")

            context.set_custom_status({"step": "NORMALIZING_TRANSCRIPT", "percent": 55})
            normalized = yield context.call_activity(
                "NormalizeContentUnderstandingTranscriptActivity",
                {"job": job, **raw_transcript},
            )
        else:
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
            raise TypeError("Normalize transcript activity must return an object")

        context.set_custom_status({"step": "GENERATING_FINAL_MINUTES", "percent": 75})
        minutes = yield context.call_activity(
            "GenerateFinalMinutesActivity",
            {"job": job, **normalized},
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
