from meeting_minutes_backend.telemetry import measure_activity
from meeting_minutes_backend.workflow_activities import start_batch_transcription


def main(payload: dict[str, object]) -> dict[str, object]:
    return measure_activity(
        "StartBatchTranscriptionActivity",
        payload,
        start_batch_transcription,
    )
