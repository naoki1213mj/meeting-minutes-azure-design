from meeting_minutes_backend.workflow_activities import generate_final_minutes


def main(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise TypeError("payload must be an object")
    return generate_final_minutes(payload)
