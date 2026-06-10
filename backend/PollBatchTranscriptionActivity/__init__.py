from meeting_minutes_backend.telemetry import measure_activity
from meeting_minutes_backend.workflow_activities import poll_batch_transcription


def main(payload: dict[str, object]) -> dict[str, object]:
    return measure_activity(
        "PollBatchTranscriptionActivity",
        payload,
        poll_batch_transcription,
    )
