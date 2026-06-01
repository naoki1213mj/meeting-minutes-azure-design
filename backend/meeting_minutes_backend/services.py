from __future__ import annotations

from meeting_minutes_backend.orchestration import InMemoryDurableStarter
from meeting_minutes_backend.service import JobService
from meeting_minutes_backend.settings import (
    AppSettings,
    build_blob_sas_issuer,
    build_job_repository,
)

_durable_starter = InMemoryDurableStarter()
_job_service: JobService | None = None


def get_job_service() -> JobService:
    global _job_service
    if _job_service is None:
        settings = AppSettings.from_env()
        _job_service = JobService(
            build_job_repository(settings),
            build_blob_sas_issuer(settings),
            _durable_starter,
        )
    return _job_service
