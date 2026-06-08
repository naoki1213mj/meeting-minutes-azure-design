from __future__ import annotations

import pytest

from meeting_minutes_backend.blob_sas import LocalBlobSasIssuer
from meeting_minutes_backend.errors import AppError
from meeting_minutes_backend.repositories import InMemoryJobRepository
from meeting_minutes_backend.settings import (
    AppSettings,
    _storage_account_url_for_artifact_uri,
    build_blob_sas_issuer,
    build_ingest_blob_sas_issuer,
    build_job_repository,
)


def test_local_settings_use_in_memory_services(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEETING_MINUTES_ENV", "local")

    settings = AppSettings.from_env()

    assert isinstance(build_job_repository(settings), InMemoryJobRepository)
    assert isinstance(build_blob_sas_issuer(settings), LocalBlobSasIssuer)
    assert isinstance(build_ingest_blob_sas_issuer(settings), LocalBlobSasIssuer)


def test_storage_settings_split_ingest_and_artifact_accounts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEETING_MINUTES_ENV", "azure")
    monkeypatch.setenv("AZURE_INGEST_STORAGE_ACCOUNT_URL", "https://ingest.blob.core.windows.net/")
    monkeypatch.setenv(
        "AZURE_ARTIFACT_STORAGE_ACCOUNT_URL",
        "https://artifact.blob.core.windows.net/",
    )
    monkeypatch.setenv("AZURE_INGEST_CONTAINER_NAME", "incoming")

    settings = AppSettings.from_env()

    assert (
        settings.resolved_ingest_storage_account_url
        == "https://ingest.blob.core.windows.net/"
    )
    assert (
        settings.resolved_artifact_storage_account_url
        == "https://artifact.blob.core.windows.net/"
    )
    assert settings.ingest_container_name == "incoming"
    assert settings.storage_container_name == "incoming"


def test_azure_settings_require_storage_and_cosmos() -> None:
    settings = AppSettings(
        environment="azure",
        storage_account_url=None,
        storage_container_name="audio",
        transcript_container_name="transcript",
        minutes_container_name="minutes",
        cosmos_endpoint=None,
        cosmos_database_name="meeting-minutes",
        cosmos_jobs_container_name="jobs",
        speech_endpoint=None,
        content_understanding_endpoint=None,
        content_understanding_analyzer_id="prebuilt-videoSearch",
        content_understanding_api_version="2025-11-01",
        content_understanding_poll_interval_seconds=2.0,
        content_understanding_operation_timeout_seconds=900.0,
        openai_base_url=None,
        chunk_summary_deployment_name="gpt-5.4-mini",
        final_merge_deployment_name="gpt-5.4",
        speech_request_timeout_seconds=480.0,
    )

    with pytest.raises(AppError) as exc_info:
        settings.validate_for_azure()

    assert exc_info.value.code == "CONFIGURATION_ERROR"
    assert exc_info.value.details["missing"] == [
        "AZURE_INGEST_STORAGE_ACCOUNT_URL or AZURE_STORAGE_ACCOUNT_URL",
        "AZURE_ARTIFACT_STORAGE_ACCOUNT_URL or AZURE_STORAGE_ACCOUNT_URL",
        "AZURE_COSMOS_ENDPOINT",
    ]


def test_artifact_store_uri_resolver_keeps_legacy_storage_compatibility() -> None:
    settings = AppSettings(
        environment="azure",
        storage_account_url="https://legacy.blob.core.windows.net/",
        storage_container_name="audio",
        transcript_container_name="transcript",
        minutes_container_name="minutes",
        cosmos_endpoint="https://cosmos.example/",
        cosmos_database_name="meeting-minutes",
        cosmos_jobs_container_name="jobs",
        speech_endpoint=None,
        content_understanding_endpoint=None,
        content_understanding_analyzer_id="prebuilt-videoSearch",
        content_understanding_api_version="2025-11-01",
        content_understanding_poll_interval_seconds=2.0,
        content_understanding_operation_timeout_seconds=900.0,
        openai_base_url=None,
        chunk_summary_deployment_name="gpt-5.4-mini",
        final_merge_deployment_name="gpt-5.4",
        speech_request_timeout_seconds=480.0,
        ingest_storage_account_url="https://ingest.blob.core.windows.net/",
        artifact_storage_account_url="https://artifact.blob.core.windows.net/",
        private_artifact_storage_account_url="https://private-artifact.blob.core.windows.net/",
        ingest_container_name="audio",
    )

    assert (
        _storage_account_url_for_artifact_uri(
            settings,
            "https://legacy.blob.core.windows.net/transcript/jobs/job-a.json",
        )
        == "https://legacy.blob.core.windows.net/"
    )
    assert (
        _storage_account_url_for_artifact_uri(
            settings,
            "https://artifact.blob.core.windows.net/transcript/jobs/job-a.json",
        )
        == "https://artifact.blob.core.windows.net/"
    )
    assert (
        _storage_account_url_for_artifact_uri(
            settings,
            "https://private-artifact.blob.core.windows.net/transcript/jobs/job-a.json",
        )
        == "https://private-artifact.blob.core.windows.net/"
    )
    assert (
        _storage_account_url_for_artifact_uri(
            settings,
            "https://unknown.blob.core.windows.net/transcript/jobs/job-a.json",
        )
        == "https://artifact.blob.core.windows.net/"
    )
