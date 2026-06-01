from meeting_minutes_backend.workflow_activities import render_markdown


def main(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise TypeError("payload must be an object")
    return render_markdown(payload)
