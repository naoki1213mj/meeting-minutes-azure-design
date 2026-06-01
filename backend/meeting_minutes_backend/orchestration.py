from __future__ import annotations

from typing import Protocol


class DurableStarter(Protocol):
    def start_job(self, job_id: str) -> str:
        pass


class InMemoryDurableStarter:
    def __init__(self) -> None:
        self._instances: set[str] = set()

    def start_job(self, job_id: str) -> str:
        self._instances.add(job_id)
        return job_id


class FixedInstanceDurableStarter:
    def __init__(self, instance_id: str) -> None:
        self._instance_id = instance_id

    def start_job(self, job_id: str) -> str:
        _ = job_id
        return self._instance_id
