from __future__ import annotations

import uuid
from datetime import UTC, datetime

from meeting_minutes_backend.auth import AuthContext
from meeting_minutes_backend.blob_sas import BlobSasIssuer
from meeting_minutes_backend.errors import AppError
from meeting_minutes_backend.file_names import build_safe_file_name
from meeting_minutes_backend.models import (
    CreateJobRequest,
    CreateJobResponse,
    InputConstraints,
    JobRecord,
    JobStatus,
    JobStatusResponse,
    Outputs,
    Progress,
    UploadCompleteRequest,
    UploadCompleteResponse,
)
from meeting_minutes_backend.orchestration import DurableStarter
from meeting_minutes_backend.repositories import JobRepository, uploaded_progress


class JobService:
    def __init__(
        self,
        repository: JobRepository,
        blob_sas_issuer: BlobSasIssuer,
        durable_starter: DurableStarter,
        constraints: InputConstraints | None = None,
    ) -> None:
        self._repository = repository
        self._blob_sas_issuer = blob_sas_issuer
        self._durable_starter = durable_starter
        self._constraints = constraints or InputConstraints()

    def create_job(self, auth: AuthContext, request: CreateJobRequest) -> CreateJobResponse:
        self._validate_create_request(request)

        now = _utc_now()
        job_id = uuid.uuid4().hex
        safe_file_name = build_safe_file_name(request.fileName, request.contentType)
        blob_name = f"raw-audio/{auth.tenant_id}/{job_id}/{safe_file_name}"
        upload_sas = self._blob_sas_issuer.create_upload_sas(blob_name, now)

        record = JobRecord(
            jobId=job_id,
            tenantId=auth.tenant_id,
            userId=auth.user_id,
            meetingTitle=request.meetingTitle,
            locale=request.locale,
            maxSpeakers=request.maxSpeakers,
            minutesModel=request.minutesModel,
            processingRoute=request.processingRoute,
            status=JobStatus.CREATED,
            originalFileName=request.fileName,
            contentType=request.contentType,
            fileSizeBytes=request.fileSizeBytes,
            blobName=blob_name,
            uploadExpiresAt=upload_sas.expires_at,
            progress=Progress(
                step=JobStatus.CREATED.value,
                percent=0,
                message="Job created",
                updatedAt=now,
            ),
            outputs=Outputs(),
            createdAt=now,
            updatedAt=now,
        )
        self._repository.create(record)

        return CreateJobResponse(
            jobId=job_id,
            status=JobStatus.CREATED,
            blobName=blob_name,
            uploadUrl=upload_sas.url,
            uploadExpiresAt=upload_sas.expires_at,
            constraints=self._constraints,
        )

    def get_job(self, auth: AuthContext, job_id: str) -> JobStatusResponse:
        record = self._get_record_or_404(auth, job_id)
        return _to_job_status_response(record)

    def get_orchestration_instance_id(self, auth: AuthContext, job_id: str) -> str | None:
        record = self._get_record_or_404(auth, job_id)
        return record.orchestrationInstanceId

    def complete_upload(
        self,
        auth: AuthContext,
        job_id: str,
        request: UploadCompleteRequest,
    ) -> UploadCompleteResponse:
        record = self._get_record_or_404(auth, job_id)

        if (
            request.uploadedSizeBytes
            and request.uploadedSizeBytes > self._constraints.hardMaxFileSizeBytes
        ):
            raise AppError(
                code="AUDIO_EXCEEDS_HARD_LIMIT",
                message="Fast Transcriptionの上限を超えています。",
                http_status=400,
                details={"hardMaxFileSizeBytes": self._constraints.hardMaxFileSizeBytes},
            )

        if record.orchestrationInstanceId:
            return _upload_complete_response(record)

        now = _utc_now()
        orchestration_instance_id = self._durable_starter.start_job(record.jobId)
        updated_record = record.model_copy(
            update={
                "status": JobStatus.UPLOADED,
                "orchestrationInstanceId": orchestration_instance_id,
                "progress": uploaded_progress(now),
                "updatedAt": now,
            }
        )
        saved = self._repository.save(updated_record)
        return _upload_complete_response(saved)

    def complete_upload_with_instance_id(
        self,
        auth: AuthContext,
        job_id: str,
        request: UploadCompleteRequest,
        orchestration_instance_id: str,
    ) -> UploadCompleteResponse:
        record = self._get_record_or_404(auth, job_id)

        if (
            request.uploadedSizeBytes
            and request.uploadedSizeBytes > self._constraints.hardMaxFileSizeBytes
        ):
            raise AppError(
                code="AUDIO_EXCEEDS_HARD_LIMIT",
                message="Fast Transcriptionの上限を超えています。",
                http_status=400,
                details={"hardMaxFileSizeBytes": self._constraints.hardMaxFileSizeBytes},
            )

        if record.orchestrationInstanceId:
            return _upload_complete_response(record)

        now = _utc_now()
        updated_record = record.model_copy(
            update={
                "status": JobStatus.UPLOADED,
                "orchestrationInstanceId": orchestration_instance_id,
                "progress": uploaded_progress(now),
                "updatedAt": now,
            }
        )
        saved = self._repository.save(updated_record)
        return _upload_complete_response(saved)

    def _validate_create_request(self, request: CreateJobRequest) -> None:
        if request.fileSizeBytes > self._constraints.hardMaxFileSizeBytes:
            raise AppError(
                code="AUDIO_EXCEEDS_HARD_LIMIT",
                message="Fast Transcriptionの上限を超えています。",
                http_status=400,
                details={"hardMaxFileSizeBytes": self._constraints.hardMaxFileSizeBytes},
            )

        if request.fileSizeBytes > self._constraints.normalMaxFileSizeBytes:
            raise AppError(
                code="AUDIO_TOO_LARGE",
                message="通常上限の300MBを超えています。音声を圧縮して再アップロードしてください。",
                http_status=400,
                details={
                    "normalMaxFileSizeBytes": self._constraints.normalMaxFileSizeBytes,
                    "fileSizeBytes": request.fileSizeBytes,
                },
            )

        if (
            request.clientEstimatedDurationSeconds is not None
            and request.clientEstimatedDurationSeconds
            > self._constraints.maxDurationSecondsWithDiarization
        ):
            raise AppError(
                code="AUDIO_TOO_LONG_FOR_DIARIZATION",
                message="diarization有効時の上限時間を超えています。",
                http_status=400,
                details={
                    "maxDurationSecondsWithDiarization": (
                        self._constraints.maxDurationSecondsWithDiarization
                    )
                },
            )

    def _get_record_or_404(self, auth: AuthContext, job_id: str) -> JobRecord:
        record = self._repository.get(auth.tenant_id, job_id)
        if record is None or record.userId != auth.user_id:
            raise AppError(
                code="JOB_NOT_FOUND",
                message="指定されたジョブが見つかりません。",
                http_status=404,
            )
        return record


def _to_job_status_response(record: JobRecord) -> JobStatusResponse:
    return JobStatusResponse(
        jobId=record.jobId,
        tenantId=record.tenantId,
        userId=record.userId,
        minutesModel=record.minutesModel,
        processingRoute=record.processingRoute,
        status=record.status,
        progress=record.progress,
        outputs=record.outputs,
        error=record.error,
        createdAt=record.createdAt,
        updatedAt=record.updatedAt,
    )


def _upload_complete_response(record: JobRecord) -> UploadCompleteResponse:
    if not record.orchestrationInstanceId:
        raise RuntimeError("orchestrationInstanceId is required after upload completion")
    return UploadCompleteResponse(
        jobId=record.jobId,
        status=JobStatus.UPLOADED,
        orchestrationInstanceId=record.orchestrationInstanceId,
        statusUrl=f"/api/jobs/{record.jobId}",
    )


def _utc_now() -> datetime:
    return datetime.now(UTC)
