from meeting_minutes_backend.workflow_activities import fail_job


def main(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise TypeError("payload must be an object")
    return fail_job(payload)
