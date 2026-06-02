from meeting_minutes_backend.telemetry import measure_activity
from meeting_minutes_backend.workflow_activities import normalize_transcript_artifact


def main(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise TypeError("payload must be an object")
    return measure_activity(
        "NormalizeTranscriptActivity",
        payload,
        normalize_transcript_artifact,
    )
