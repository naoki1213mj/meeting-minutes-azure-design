from meeting_minutes_backend.telemetry import measure_activity
from meeting_minutes_backend.workflow_activities import poll_content_understanding_analysis


def main(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise TypeError("payload must be an object")
    return measure_activity(
        "PollContentUnderstandingActivity",
        payload,
        poll_content_understanding_analysis,
    )
