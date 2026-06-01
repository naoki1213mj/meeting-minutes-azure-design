from meeting_minutes_backend.workflow_activities import validate_input


def main(job: object) -> dict[str, object]:
    if not isinstance(job, dict):
        raise TypeError("job must be an object")
    return validate_input(job)
