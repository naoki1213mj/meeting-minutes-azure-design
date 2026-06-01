from meeting_minutes_backend.workflow_activities import transcribe_audio


def main(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise TypeError("payload must be an object")
    return transcribe_audio(payload)
