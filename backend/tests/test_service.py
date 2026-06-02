from __future__ import annotations

import pytest

from meeting_minutes_backend.auth import AuthContext
from meeting_minutes_backend.blob_sas import LocalBlobSasIssuer
from meeting_minutes_backend.errors import AppError
from meeting_minutes_backend.file_names import build_safe_file_name
from meeting_minutes_backend.models import (
    CreateJobRequest,
    JobStatus,
    MinutesModel,
    UploadCompleteRequest,
)
from meeting_minutes_backend.orchestration import InMemoryDurableStarter
from meeting_minutes_backend.repositories import InMemoryJobRepository
from meeting_minutes_backend.service import JobService


class _RecordingDurableStarter:
    def __init__(self) -> None:
        self.started_job_ids: list[str] = []

    def start_job(self, job_id: str) -> str:
        self.started_job_ids.append(job_id)
        return f"instance-{job_id}"


def _service() -> JobService:
    return JobService(InMemoryJobRepository(), LocalBlobSasIssuer(), InMemoryDurableStarter())


def _service_with_starter(starter: _RecordingDurableStarter) -> JobService:
    return JobService(InMemoryJobRepository(), LocalBlobSasIssuer(), starter)


def _auth(tenant_id: str = "tenant-a", user_id: str = "user-a") -> AuthContext:
    return AuthContext(tenant_id=tenant_id, user_id=user_id)


def _create_request(file_size_bytes: int = 1024) -> CreateJobRequest:
    return CreateJobRequest(
        fileName="..\\secret meeting!!.mp3",
        contentType="audio/mpeg",
        fileSizeBytes=file_size_bytes,
    )


def test_create_job_initializes_created_progress_and_safe_blob_name() -> None:
    service = _service()

    response = service.create_job(_auth(), _create_request())
    status = service.get_job(_auth(), response.jobId)

    assert response.status == JobStatus.CREATED
    assert response.blobName.startswith("raw-audio/tenant-a/")
    assert ".." not in response.blobName
    assert response.blobName.endswith("/secret-meeting.mp3")
    assert status.progress.step == "CREATED"
    assert status.progress.percent == 0
    assert status.minutesModel == MinutesModel.FAST


def test_create_job_persists_requested_minutes_model() -> None:
    service = _service()
    request = _create_request()
    request = request.model_copy(update={"minutesModel": MinutesModel.QUALITY})

    response = service.create_job(_auth(), request)

    assert service.get_job(_auth(), response.jobId).minutesModel == MinutesModel.QUALITY


def test_create_job_rejects_normal_size_limit() -> None:
    service = _service()

    with pytest.raises(AppError) as exc_info:
        service.create_job(_auth(), _create_request(file_size_bytes=400_000_000))

    assert exc_info.value.code == "AUDIO_TOO_LARGE"
    assert exc_info.value.http_status == 400


def test_get_job_from_other_tenant_returns_not_found() -> None:
    service = _service()
    response = service.create_job(_auth(), _create_request())

    with pytest.raises(AppError) as exc_info:
        service.get_job(_auth(tenant_id="tenant-b"), response.jobId)

    assert exc_info.value.code == "JOB_NOT_FOUND"
    assert exc_info.value.http_status == 404


def test_get_job_from_other_user_returns_not_found() -> None:
    service = _service()
    response = service.create_job(_auth(), _create_request())

    with pytest.raises(AppError) as exc_info:
        service.get_job(_auth(user_id="user-b"), response.jobId)

    assert exc_info.value.code == "JOB_NOT_FOUND"
    assert exc_info.value.http_status == 404


@pytest.mark.parametrize(
    "unauthorized_auth",
    [
        AuthContext(tenant_id="tenant-b", user_id="user-a"),
        AuthContext(tenant_id="tenant-a", user_id="user-b"),
    ],
)
def test_complete_upload_from_other_owner_returns_not_found_without_starting_orchestration(
    unauthorized_auth: AuthContext,
) -> None:
    starter = _RecordingDurableStarter()
    service = _service_with_starter(starter)
    response = service.create_job(_auth(), _create_request())

    with pytest.raises(AppError) as exc_info:
        service.complete_upload(
            unauthorized_auth,
            response.jobId,
            UploadCompleteRequest(uploadedSizeBytes=1024),
        )

    assert exc_info.value.code == "JOB_NOT_FOUND"
    assert exc_info.value.http_status == 404
    assert starter.started_job_ids == []
    assert service.get_job(_auth(), response.jobId).status == JobStatus.CREATED


@pytest.mark.parametrize(
    "unauthorized_auth",
    [
        AuthContext(tenant_id="tenant-b", user_id="user-a"),
        AuthContext(tenant_id="tenant-a", user_id="user-b"),
    ],
)
def test_get_orchestration_instance_id_from_other_owner_returns_not_found(
    unauthorized_auth: AuthContext,
) -> None:
    starter = _RecordingDurableStarter()
    service = _service_with_starter(starter)
    response = service.create_job(_auth(), _create_request())
    service.complete_upload(_auth(), response.jobId, UploadCompleteRequest(uploadedSizeBytes=1024))

    assert service.get_orchestration_instance_id(_auth(), response.jobId) == (
        f"instance-{response.jobId}"
    )
    with pytest.raises(AppError) as exc_info:
        service.get_orchestration_instance_id(unauthorized_auth, response.jobId)

    assert exc_info.value.code == "JOB_NOT_FOUND"
    assert exc_info.value.http_status == 404


def test_upload_complete_is_idempotent() -> None:
    service = _service()
    create_response = service.create_job(_auth(), _create_request())
    request = UploadCompleteRequest(uploadedSizeBytes=1024)

    first = service.complete_upload(_auth(), create_response.jobId, request)
    second = service.complete_upload(_auth(), create_response.jobId, request)

    assert first.status == JobStatus.UPLOADED
    assert second.status == JobStatus.UPLOADED
    assert first.orchestrationInstanceId == second.orchestrationInstanceId
    assert first.statusUrl == f"/api/jobs/{create_response.jobId}"


def test_upload_complete_rejects_hard_limit() -> None:
    service = _service()
    create_response = service.create_job(_auth(), _create_request())

    with pytest.raises(AppError) as exc_info:
        service.complete_upload(
            _auth(),
            create_response.jobId,
            UploadCompleteRequest(uploadedSizeBytes=600_000_000),
        )

    assert exc_info.value.code == "AUDIO_EXCEEDS_HARD_LIMIT"


def test_build_safe_file_name_falls_back_for_unsafe_stem() -> None:
    assert build_safe_file_name("!!!!.mp3", "audio/mpeg") == "input.mp3"
