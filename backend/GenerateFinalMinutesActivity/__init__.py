from meeting_minutes_backend.telemetry import measure_activity
from meeting_minutes_backend.workflow_activities import generate_final_minutes


def main(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise TypeError("payload must be an object")
    return measure_activity("GenerateFinalMinutesActivity", payload, generate_final_minutes)
