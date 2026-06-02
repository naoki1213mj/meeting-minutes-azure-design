from meeting_minutes_backend.telemetry import measure_activity
from meeting_minutes_backend.workflow_activities import create_read_sas


def main(job: object) -> dict:
    if not isinstance(job, dict):
        raise TypeError("job must be an object")
    return measure_activity("CreateReadSasActivity", job, create_read_sas)
