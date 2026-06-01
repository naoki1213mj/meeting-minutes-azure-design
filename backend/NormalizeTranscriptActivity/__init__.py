from meeting_minutes_backend.workflow_activities import normalize_transcript_artifact


def main(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise TypeError("payload must be an object")
    return normalize_transcript_artifact(payload)
