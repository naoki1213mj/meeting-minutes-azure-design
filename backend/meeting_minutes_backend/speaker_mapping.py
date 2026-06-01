from __future__ import annotations

from datetime import datetime

from meeting_minutes_backend.models import StrictModel


class SpeakerMappingEntry(StrictModel):
    speakerLabel: str
    displayName: str | None


class SpeakerMapping(StrictModel):
    id: str
    tenantId: str
    jobId: str
    version: int
    speakers: list[SpeakerMappingEntry]
    updatedAt: datetime
    updatedBy: str
