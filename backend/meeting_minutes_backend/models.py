from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class JobStatus(StrEnum):
    CREATED = "CREATED"
    UPLOADING = "UPLOADING"
    UPLOADED = "UPLOADED"
    VALIDATING = "VALIDATING"
    PREPROCESSING = "PREPROCESSING"
    TRANSCRIBING = "TRANSCRIBING"
    TRANSCRIPT_READY = "TRANSCRIPT_READY"
    GENERATING_CHUNK_SUMMARIES = "GENERATING_CHUNK_SUMMARIES"
    GENERATING_FINAL_MINUTES = "GENERATING_FINAL_MINUTES"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class MinutesModel(StrEnum):
    FAST = "fast"
    QUALITY = "quality"


class ProcessingRoute(StrEnum):
    STABLE = "stable"
    CONTENT_UNDERSTANDING = "contentUnderstanding"


class InputConstraints(StrictModel):
    normalMaxFileSizeBytes: int = 314_572_800
    hardMaxFileSizeBytes: int = 524_288_000
    contentUnderstandingMaxFileSizeBytes: int = 4_294_967_296
    maxDurationSecondsWithDiarization: int = 7_200


class CreateJobRequest(StrictModel):
    fileName: str = Field(min_length=1)
    contentType: str = Field(min_length=1)
    fileSizeBytes: int = Field(gt=0)
    clientEstimatedDurationSeconds: int | None = Field(default=None, ge=0)
    meetingTitle: str | None = None
    locale: str = "ja-JP"
    maxSpeakers: int = Field(default=8, ge=2, le=30)
    minutesModel: MinutesModel = MinutesModel.FAST
    processingRoute: ProcessingRoute = ProcessingRoute.STABLE


class CreateJobResponse(StrictModel):
    jobId: str
    status: JobStatus
    blobName: str
    uploadUrl: str
    uploadExpiresAt: datetime
    constraints: InputConstraints


class UploadCompleteRequest(StrictModel):
    uploadedSizeBytes: int | None = Field(default=None, gt=0)
    clientSha256: str | None = None


class UploadCompleteResponse(StrictModel):
    jobId: str
    status: JobStatus
    orchestrationInstanceId: str
    statusUrl: str


class Progress(StrictModel):
    step: str
    percent: int = Field(ge=0, le=100)
    message: str
    updatedAt: datetime


class Outputs(StrictModel):
    transcriptReady: bool = False
    minutesReady: bool = False
    rawTranscriptBlobUri: str | None = None
    normalizedTranscriptBlobUri: str | None = None
    visualContextBlobUri: str | None = None
    minutesJsonBlobUri: str | None = None
    minutesMarkdownBlobUri: str | None = None


class ErrorObject(StrictModel):
    code: str
    message: str
    details: dict[str, object] | None = None
    correlationId: str


class JobStatusResponse(StrictModel):
    jobId: str
    tenantId: str
    userId: str
    minutesModel: MinutesModel = MinutesModel.FAST
    processingRoute: ProcessingRoute = ProcessingRoute.STABLE
    status: JobStatus
    progress: Progress
    outputs: Outputs
    error: ErrorObject | None = None
    createdAt: datetime
    updatedAt: datetime


class JobRecord(StrictModel):
    jobId: str
    tenantId: str
    userId: str
    meetingTitle: str | None
    locale: str
    maxSpeakers: int
    minutesModel: MinutesModel = MinutesModel.FAST
    processingRoute: ProcessingRoute = ProcessingRoute.STABLE
    status: JobStatus
    originalFileName: str
    contentType: str
    fileSizeBytes: int
    blobName: str
    uploadExpiresAt: datetime
    orchestrationInstanceId: str | None = None
    progress: Progress
    outputs: Outputs
    error: ErrorObject | None = None
    createdAt: datetime
    updatedAt: datetime
