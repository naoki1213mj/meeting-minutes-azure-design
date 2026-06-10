from meeting_minutes_backend.telemetry import measure_activity
from meeting_minutes_backend.workflow_activities import normalize_batch_transcript_artifact


def main(payload: dict[str, object]) -> dict[str, object]:
    return measure_activity(
        "NormalizeBatchTranscriptActivity",
        payload,
        normalize_batch_transcript_artifact,
    )
