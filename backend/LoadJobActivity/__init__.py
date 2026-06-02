from meeting_minutes_backend.telemetry import measure_activity
from meeting_minutes_backend.workflow_activities import load_job


def main(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise TypeError("payload must be an object")
    return measure_activity("LoadJobActivity", payload, load_job)
