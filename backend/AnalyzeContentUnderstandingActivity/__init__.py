from meeting_minutes_backend.telemetry import measure_activity
from meeting_minutes_backend.workflow_activities import analyze_content_understanding


def main(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise TypeError("payload must be an object")
    return measure_activity(
        "AnalyzeContentUnderstandingActivity",
        payload,
        analyze_content_understanding,
    )
