from meeting_minutes_backend.telemetry import measure_activity
from meeting_minutes_backend.workflow_activities import fetch_batch_transcription_result


def main(payload: dict[str, object]) -> dict[str, object]:
    return measure_activity(
        "FetchBatchTranscriptionResultActivity",
        payload,
        fetch_batch_transcription_result,
    )
