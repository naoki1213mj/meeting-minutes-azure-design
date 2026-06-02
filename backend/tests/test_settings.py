from __future__ import annotations

import pytest

from meeting_minutes_backend.blob_sas import LocalBlobSasIssuer
from meeting_minutes_backend.errors import AppError
from meeting_minutes_backend.repositories import InMemoryJobRepository
from meeting_minutes_backend.settings import (
    AppSettings,
    build_blob_sas_issuer,
    build_job_repository,
)


def test_local_settings_use_in_memory_services(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEETING_MINUTES_ENV", "local")

    settings = AppSettings.from_env()

    assert isinstance(build_job_repository(settings), InMemoryJobRepository)
    assert isinstance(build_blob_sas_issuer(settings), LocalBlobSasIssuer)


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
        openai_base_url=None,
        chunk_summary_deployment_name="gpt-5.4-mini",
        final_merge_deployment_name="gpt-5.4",
        speech_request_timeout_seconds=480.0,
    )

    with pytest.raises(AppError) as exc_info:
        settings.validate_for_azure()

    assert exc_info.value.code == "CONFIGURATION_ERROR"
    assert exc_info.value.details["missing"] == [
        "AZURE_STORAGE_ACCOUNT_URL",
        "AZURE_COSMOS_ENDPOINT",
    ]
