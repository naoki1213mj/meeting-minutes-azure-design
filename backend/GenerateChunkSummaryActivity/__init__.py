from meeting_minutes_backend.workflow_activities import generate_chunk_summary_artifact


def main(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise TypeError("payload must be an object")
    return generate_chunk_summary_artifact(payload)
