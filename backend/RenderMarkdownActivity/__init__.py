from meeting_minutes_backend.telemetry import measure_activity
from meeting_minutes_backend.workflow_activities import render_markdown


def main(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise TypeError("payload must be an object")
    return measure_activity("RenderMarkdownActivity", payload, render_markdown)
