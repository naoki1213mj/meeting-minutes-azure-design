from meeting_minutes_backend.telemetry import measure_activity
from meeting_minutes_backend.workflow_activities import build_transcript_chunks_artifact


def main(payload: object) -> list:
    if not isinstance(payload, dict):
        raise TypeError("payload must be an object")
    return measure_activity(
        "BuildTranscriptChunksActivity",
        payload,
        build_transcript_chunks_artifact,
    )
