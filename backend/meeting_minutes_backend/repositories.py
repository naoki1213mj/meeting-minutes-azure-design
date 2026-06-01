from __future__ import annotations

from datetime import datetime
from threading import Lock
from typing import Protocol

from meeting_minutes_backend.models import JobRecord, JobStatus, Progress


class JobRepository(Protocol):
    def create(self, record: JobRecord) -> JobRecord:
        pass

    def get(self, tenant_id: str, job_id: str) -> JobRecord | None:
        pass

    def save(self, record: JobRecord) -> JobRecord:
        pass


class InMemoryJobRepository:
    def __init__(self) -> None:
        self._records: dict[str, JobRecord] = {}
        self._lock = Lock()

    def create(self, record: JobRecord) -> JobRecord:
        with self._lock:
            self._records[record.jobId] = record
            return record

    def get(self, tenant_id: str, job_id: str) -> JobRecord | None:
        with self._lock:
            record = self._records.get(job_id)
            if record is None or record.tenantId != tenant_id:
                return None
            return record

    def save(self, record: JobRecord) -> JobRecord:
        with self._lock:
            self._records[record.jobId] = record
            return record


def uploaded_progress(now: datetime) -> Progress:
    return Progress(
        step=JobStatus.UPLOADED.value,
        percent=10,
        message="アップロードを受け付けました。",
        updatedAt=now,
    )
