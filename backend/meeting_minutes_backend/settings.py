from __future__ import annotations

import os
from dataclasses import dataclass

from meeting_minutes_backend.azure_credentials import build_credential
from meeting_minutes_backend.blob_artifacts import BlobArtifactStore
from meeting_minutes_backend.blob_sas import BlobSasIssuer, LocalBlobSasIssuer
from meeting_minutes_backend.blob_storage import AzureBlobSasIssuer
from meeting_minutes_backend.content_understanding_client import ContentUnderstandingClient
from meeting_minutes_backend.cosmos_repository import CosmosJobRepository
from meeting_minutes_backend.errors import AppError
from meeting_minutes_backend.minutes_generation import DeploymentCapabilities
from meeting_minutes_backend.models import MinutesModel
from meeting_minutes_backend.openai_client import AzureOpenAIJsonClient
from meeting_minutes_backend.repositories import InMemoryJobRepository, JobRepository
from meeting_minutes_backend.speech_client import FastTranscriptionClient


@dataclass(frozen=True)
class AppSettings:
    environment: str
    storage_account_url: str | None
    storage_container_name: str
    transcript_container_name: str
    minutes_container_name: str
    cosmos_endpoint: str | None
    cosmos_database_name: str
    cosmos_jobs_container_name: str
    speech_endpoint: str | None
    content_understanding_endpoint: str | None
    content_understanding_analyzer_id: str
    content_understanding_api_version: str
    content_understanding_poll_interval_seconds: float
    content_understanding_operation_timeout_seconds: float
    openai_base_url: str | None
    chunk_summary_deployment_name: str
    final_merge_deployment_name: str
    speech_request_timeout_seconds: float

    @classmethod
    def from_env(cls) -> AppSettings:
        return cls(
            environment=os.getenv("MEETING_MINUTES_ENV", os.getenv("ENVIRONMENT", "local")).lower(),
            storage_account_url=os.getenv("AZURE_STORAGE_ACCOUNT_URL"),
            storage_container_name=os.getenv("AZURE_STORAGE_CONTAINER_NAME", "audio"),
            transcript_container_name=os.getenv("AZURE_TRANSCRIPT_CONTAINER_NAME", "transcript"),
            minutes_container_name=os.getenv("AZURE_MINUTES_CONTAINER_NAME", "minutes"),
            cosmos_endpoint=os.getenv("AZURE_COSMOS_ENDPOINT"),
            cosmos_database_name=os.getenv("AZURE_COSMOS_DATABASE_NAME", "meeting-minutes"),
            cosmos_jobs_container_name=os.getenv("AZURE_COSMOS_JOBS_CONTAINER_NAME", "jobs"),
            speech_endpoint=os.getenv("AZURE_SPEECH_ENDPOINT"),
            content_understanding_endpoint=os.getenv(
                "AZURE_CONTENT_UNDERSTANDING_ENDPOINT",
                os.getenv("AZURE_SPEECH_ENDPOINT"),
            ),
            content_understanding_analyzer_id=os.getenv(
                "AZURE_CONTENT_UNDERSTANDING_ANALYZER_ID",
                "prebuilt-videoSearch",
            ),
            content_understanding_api_version=os.getenv(
                "AZURE_CONTENT_UNDERSTANDING_API_VERSION",
                "2025-11-01",
            ),
            content_understanding_poll_interval_seconds=float(
                os.getenv("AZURE_CONTENT_UNDERSTANDING_POLL_INTERVAL_SECONDS", "2")
            ),
            content_understanding_operation_timeout_seconds=float(
                os.getenv("AZURE_CONTENT_UNDERSTANDING_OPERATION_TIMEOUT_SECONDS", "900")
            ),
            openai_base_url=os.getenv("AZURE_OPENAI_BASE_URL"),
            chunk_summary_deployment_name=os.getenv(
                "AZURE_OPENAI_DEPLOYMENT_CHUNK_SUMMARY",
                "gpt-5.4-mini",
            ),
            final_merge_deployment_name=os.getenv(
                "AZURE_OPENAI_DEPLOYMENT_FINAL_MERGE",
                "gpt-5.4",
            ),
            speech_request_timeout_seconds=float(
                os.getenv("AZURE_SPEECH_REQUEST_TIMEOUT_SECONDS", "480")
            ),
        )

    @property
    def is_local(self) -> bool:
        return self.environment == "local"

    def validate_for_azure(self) -> None:
        missing = []
        if not self.storage_account_url:
            missing.append("AZURE_STORAGE_ACCOUNT_URL")
        if not self.cosmos_endpoint:
            missing.append("AZURE_COSMOS_ENDPOINT")
        if missing:
            raise AppError(
                code="CONFIGURATION_ERROR",
                message="Azure実行に必要な環境変数が不足しています。",
                http_status=500,
                details={"missing": missing},
            )

    def validate_ai_for_azure(self) -> None:
        missing = []
        if not self.speech_endpoint:
            missing.append("AZURE_SPEECH_ENDPOINT")
        if not self.openai_base_url:
            missing.append("AZURE_OPENAI_BASE_URL")
        if missing:
            raise AppError(
                code="CONFIGURATION_ERROR",
                message="AI処理に必要な環境変数が不足しています。",
                http_status=500,
                details={"missing": missing},
            )

    def validate_content_understanding_for_azure(self) -> None:
        if not self.content_understanding_endpoint:
            raise AppError(
                code="CONFIGURATION_ERROR",
                message="Content Understanding実行に必要な環境変数が不足しています。",
                http_status=500,
                details={"missing": ["AZURE_CONTENT_UNDERSTANDING_ENDPOINT"]},
            )


def build_job_repository(settings: AppSettings) -> JobRepository:
    if settings.is_local:
        return InMemoryJobRepository()

    settings.validate_for_azure()
    credential = build_credential()
    return CosmosJobRepository(
        endpoint=_required(settings.cosmos_endpoint),
        database_name=settings.cosmos_database_name,
        jobs_container_name=settings.cosmos_jobs_container_name,
        credential=credential,
    )


def build_blob_sas_issuer(settings: AppSettings) -> BlobSasIssuer:
    if settings.is_local:
        return LocalBlobSasIssuer()

    settings.validate_for_azure()
    return AzureBlobSasIssuer(
        account_url=_required(settings.storage_account_url),
        container_name=settings.storage_container_name,
        credential=build_credential(),
    )


def build_artifact_store(settings: AppSettings) -> BlobArtifactStore:
    settings.validate_for_azure()
    return BlobArtifactStore(
        account_url=_required(settings.storage_account_url),
        credential=build_credential(),
    )


def build_speech_client(settings: AppSettings) -> FastTranscriptionClient:
    settings.validate_ai_for_azure()
    return FastTranscriptionClient(
        endpoint=_required(settings.speech_endpoint),
        credential=build_credential(),
        request_timeout_seconds=settings.speech_request_timeout_seconds,
    )


def build_content_understanding_client(settings: AppSettings) -> ContentUnderstandingClient:
    settings.validate_content_understanding_for_azure()
    return ContentUnderstandingClient(
        endpoint=_required(settings.content_understanding_endpoint),
        analyzer_id=settings.content_understanding_analyzer_id,
        api_version=settings.content_understanding_api_version,
        credential=build_credential(),
        poll_interval_seconds=settings.content_understanding_poll_interval_seconds,
        operation_timeout_seconds=settings.content_understanding_operation_timeout_seconds,
    )


def build_openai_client(settings: AppSettings) -> AzureOpenAIJsonClient:
    settings.validate_ai_for_azure()
    return AzureOpenAIJsonClient(
        base_url=_required(settings.openai_base_url),
        credential=build_credential(),
    )


def build_chunk_deployment(settings: AppSettings) -> DeploymentCapabilities:
    return DeploymentCapabilities(
        deploymentName=settings.chunk_summary_deployment_name,
        modelName=settings.chunk_summary_deployment_name,
        generationParameters={"max_completion_tokens": 4096},
    )


def build_final_deployment(settings: AppSettings) -> DeploymentCapabilities:
    return DeploymentCapabilities(
        deploymentName=settings.final_merge_deployment_name,
        modelName=settings.final_merge_deployment_name,
        generationParameters={"max_completion_tokens": 32768, "reasoning_effort": "low"},
    )


def build_minutes_deployment(
    settings: AppSettings,
    minutes_model: MinutesModel,
) -> DeploymentCapabilities:
    if minutes_model == MinutesModel.QUALITY:
        return build_final_deployment(settings)
    return DeploymentCapabilities(
        deploymentName=settings.chunk_summary_deployment_name,
        modelName=settings.chunk_summary_deployment_name,
        generationParameters={"max_completion_tokens": 32768, "reasoning_effort": "low"},
    )


def _required(value: str | None) -> str:
    if not value:
        raise RuntimeError("Expected non-empty setting after validation")
    return value
