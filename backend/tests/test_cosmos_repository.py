from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import Mock, patch

from meeting_minutes_backend.cosmos_repository import CosmosJobRepository
from meeting_minutes_backend.models import JobRecord, JobStatus, Outputs, Progress


def _record() -> JobRecord:
    now = datetime(2026, 6, 1, tzinfo=UTC)
    return JobRecord(
        jobId="job-a",
        tenantId="tenant-a",
        userId="user-a",
        meetingTitle=None,
        locale="ja-JP",
        maxSpeakers=8,
        status=JobStatus.CREATED,
        originalFileName="meeting.mp3",
        contentType="audio/mpeg",
        fileSizeBytes=1024,
        blobName="raw-audio/tenant-a/job-a/meeting.mp3",
        uploadExpiresAt=now,
        progress=Progress(step="CREATED", percent=0, message="Job created", updatedAt=now),
        outputs=Outputs(),
        createdAt=now,
        updatedAt=now,
    )


def test_cosmos_repository_writes_id_and_tenant_partition_key() -> None:
    container = Mock()
    database = Mock()
    database.get_container_client.return_value = container
    client = Mock()
    client.get_database_client.return_value = database

    with patch("meeting_minutes_backend.cosmos_repository.CosmosClient", return_value=client):
        repository = CosmosJobRepository(
            endpoint="https://cosmos.example",
            database_name="meeting-minutes",
            jobs_container_name="jobs",
            credential=Mock(),
        )
        repository.create(_record())
        container.read_item.return_value = {
            **container.create_item.call_args.args[0],
            "_rid": "rid",
            "_self": "self",
            "_etag": "etag",
            "_attachments": "attachments",
            "_ts": 1,
        }
        loaded = repository.get("tenant-a", "job-a")

    created_item = container.create_item.call_args.args[0]
    assert created_item["id"] == "job-a"
    assert created_item["tenantId"] == "tenant-a"
    assert loaded is not None
    assert loaded.jobId == "job-a"
    container.read_item.assert_called_with(item="job-a", partition_key="tenant-a")
