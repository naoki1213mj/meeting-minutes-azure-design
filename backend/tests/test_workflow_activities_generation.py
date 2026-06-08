from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

import pytest

import meeting_minutes_backend.workflow_activities as workflow_activities
from meeting_minutes_backend.blob_sas import UploadSas
from meeting_minutes_backend.errors import AppError
from meeting_minutes_backend.models import ProcessingRoute
from meeting_minutes_backend.workflow_activities import (
    _should_fallback_to_chunk_minutes,
    create_read_sas,
)


def test_minutes_generation_fallbacks_on_truncated_direct_response() -> None:
    error = AppError(
        code="OPENAI_GENERATION_FAILED",
        message="議事録生成に失敗しました。",
        http_status=502,
        details={"reason": "Response was truncated"},
    )

    assert _should_fallback_to_chunk_minutes(error)


def test_minutes_generation_fallbacks_on_schema_validation_failure() -> None:
    error = AppError(
        code="MINUTES_SCHEMA_VALIDATION_FAILED",
        message="議事録JSONの検証に失敗しました。",
        http_status=502,
    )

    assert _should_fallback_to_chunk_minutes(error)


def test_minutes_generation_does_not_fallback_on_content_filter() -> None:
    error = AppError(
        code="OPENAI_GENERATION_FAILED",
        message="議事録生成に失敗しました。",
        http_status=502,
        details={"reason": "Response blocked by content filter"},
    )

    assert not _should_fallback_to_chunk_minutes(error)


def test_create_read_sas_uses_original_mp4_for_content_understanding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeRepository:
        saved = False

        def get(self, tenant_id: str, job_id: str) -> SimpleNamespace:
            assert (tenant_id, job_id) == ("tenant-a", "job-a")
            return SimpleNamespace(
                blobName="raw-audio/tenant-a/job-a/input.mp4",
                contentType="video/mp4",
                processingRoute=ProcessingRoute.CONTENT_UNDERSTANDING,
            )

        def save(self, _record: object) -> None:
            self.saved = True

    class FakeSasIssuer:
        blob_names: list[str] = []

        def create_read_sas(self, blob_name: str, now: datetime) -> UploadSas:
            assert now.tzinfo == UTC
            self.blob_names.append(blob_name)
            return UploadSas(
                url=f"https://storage.example/{blob_name}?sig=redacted",
                expires_at=now,
            )

    repo = FakeRepository()
    issuer = FakeSasIssuer()
    monkeypatch.setattr(
        workflow_activities.AppSettings,
        "from_env",
        lambda: SimpleNamespace(ingest_container_name="audio"),
    )
    monkeypatch.setattr(workflow_activities, "build_job_repository", lambda _settings: repo)
    monkeypatch.setattr(
        workflow_activities,
        "build_ingest_blob_sas_issuer",
        lambda _settings: issuer,
    )
    monkeypatch.setattr(
        workflow_activities,
        "build_artifact_store",
        lambda _settings: (_ for _ in ()).throw(AssertionError("artifact store not needed")),
    )
    monkeypatch.setattr(
        workflow_activities,
        "build_ingest_blob_store",
        lambda _settings: (_ for _ in ()).throw(AssertionError("ingest store not needed")),
    )

    result = create_read_sas({"tenantId": "tenant-a", "jobId": "job-a"})

    assert cast(str, result["audioUrl"]).endswith(
        "raw-audio/tenant-a/job-a/input.mp4?sig=redacted"
    )
    assert issuer.blob_names == ["raw-audio/tenant-a/job-a/input.mp4"]
    assert not repo.saved


def test_create_read_sas_preprocesses_stable_media_in_ingest_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeRecord:
        blobName = "raw-audio/tenant-a/job-a/input.m4a"
        contentType = "audio/x-m4a"
        processingRoute = ProcessingRoute.STABLE
        update: dict[str, object] | None = None

        def model_copy(self, update: dict[str, object]) -> FakeRecord:
            self.update = update
            return self

    class FakeRepository:
        def __init__(self) -> None:
            self.record = FakeRecord()
            self.saved_records: list[FakeRecord] = []

        def get(self, tenant_id: str, job_id: str) -> FakeRecord:
            assert (tenant_id, job_id) == ("tenant-a", "job-a")
            return self.record

        def save(self, record: FakeRecord) -> None:
            self.saved_records.append(record)

    class FakeSasIssuer:
        pass

    repo = FakeRepository()
    issuer = FakeSasIssuer()
    ingest_store = object()
    monkeypatch.setattr(
        workflow_activities.AppSettings,
        "from_env",
        lambda: SimpleNamespace(ingest_container_name="ingest-audio"),
    )
    monkeypatch.setattr(workflow_activities, "build_job_repository", lambda _settings: repo)
    monkeypatch.setattr(
        workflow_activities,
        "build_ingest_blob_sas_issuer",
        lambda _settings: issuer,
    )
    monkeypatch.setattr(
        workflow_activities,
        "build_ingest_blob_store",
        lambda _settings: ingest_store,
    )
    monkeypatch.setattr(
        workflow_activities,
        "build_artifact_store",
        lambda _settings: (_ for _ in ()).throw(AssertionError("artifact store not needed")),
    )

    def fake_prepare_audio_for_transcription(**kwargs: object) -> UploadSas:
        assert kwargs["container_name"] == "ingest-audio"
        assert kwargs["store"] is ingest_store
        assert kwargs["sas_issuer"] is issuer
        return UploadSas(
            url="https://ingest.example/preprocessed/tenant-a/job-a/input.flac?sig=redacted",
            expires_at=datetime(2026, 6, 1, tzinfo=UTC),
        )

    monkeypatch.setattr(
        workflow_activities,
        "prepare_audio_for_transcription",
        fake_prepare_audio_for_transcription,
    )

    result = create_read_sas({"tenantId": "tenant-a", "jobId": "job-a"})

    expected_url = "https://ingest.example/preprocessed/tenant-a/job-a/input.flac?sig=redacted"
    assert result == {"audioUrl": expected_url}
    assert repo.saved_records == [repo.record]
