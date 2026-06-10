from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

import pytest

import meeting_minutes_backend.workflow_activities as workflow_activities
from meeting_minutes_backend.blob_sas import UploadSas
from meeting_minutes_backend.errors import AppError
from meeting_minutes_backend.models import ProcessingRoute, Progress
from meeting_minutes_backend.workflow_activities import (
    _should_fallback_to_chunk_minutes,
    create_read_sas,
    poll_content_understanding_analysis,
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

    class FakeIngestStore:
        def get_blob_size(self, container_name: str, blob_name: str) -> int:
            assert (container_name, blob_name) == (
                "audio",
                "raw-audio/tenant-a/job-a/input.mp4",
            )
            return 1_024

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
        lambda _settings: FakeIngestStore(),
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

    class FakeIngestStore:
        def get_blob_size(self, container_name: str, blob_name: str) -> int:
            assert (container_name, blob_name) == (
                "ingest-audio",
                "raw-audio/tenant-a/job-a/input.m4a",
            )
            return 3_221_225_472

    repo = FakeRepository()
    issuer = FakeSasIssuer()
    ingest_store = FakeIngestStore()
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


def test_create_read_sas_rejects_actual_preprocessed_source_over_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeRepository:
        def get(self, tenant_id: str, job_id: str) -> SimpleNamespace:
            assert (tenant_id, job_id) == ("tenant-a", "job-a")
            return SimpleNamespace(
                blobName="raw-audio/tenant-a/job-a/input.mp4",
                contentType="video/mp4",
                processingRoute=ProcessingRoute.STABLE,
            )

    class FakeIngestStore:
        def get_blob_size(self, _container_name: str, _blob_name: str) -> int:
            return 4_294_967_297

    monkeypatch.setattr(
        workflow_activities.AppSettings,
        "from_env",
        lambda: SimpleNamespace(ingest_container_name="audio"),
    )
    monkeypatch.setattr(
        workflow_activities,
        "build_job_repository",
        lambda _settings: FakeRepository(),
    )
    monkeypatch.setattr(
        workflow_activities,
        "build_ingest_blob_store",
        lambda _settings: FakeIngestStore(),
    )

    with pytest.raises(AppError) as exc_info:
        create_read_sas({"tenantId": "tenant-a", "jobId": "job-a"})

    assert exc_info.value.code == "STABLE_PREPROCESSED_SOURCE_TOO_LARGE"


def test_poll_content_understanding_failed_result_preserves_sanitized_details(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FakeClient:
        def get_result(self, operation_url: str) -> dict[str, object]:
            assert operation_url == "https://foundry.example/operations/op-a"
            return {
                "status": "Failed",
                "error": {
                    "code": "InvalidContent",
                    "message": (
                        "Could not fetch https://storage.example/video.mp4?"
                        "sv=2024&sig=secret-signature"
                    ),
                },
            }

    monkeypatch.setattr(
        workflow_activities.AppSettings,
        "from_env",
        lambda: SimpleNamespace(),
    )
    monkeypatch.setattr(
        workflow_activities,
        "build_content_understanding_client",
        lambda _settings: FakeClient(),
    )

    caplog.set_level(logging.ERROR, logger=workflow_activities.LOGGER.name)

    result = poll_content_understanding_analysis(
        {
            "job": {"tenantId": "tenant-a", "jobId": "job-a"},
            "operationUrl": "https://foundry.example/operations/op-a",
        }
    )

    assert result["status"] == "Failed"
    error = result["error"]
    assert isinstance(error, dict)
    assert error["operationStatus"] == "Failed"
    operation_error = error["operationError"]
    assert isinstance(operation_error, dict)
    assert operation_error["code"] == "InvalidContent"
    assert operation_error["message"] == "Could not fetch [REDACTED_SAS_URL]"
    assert "secret-signature" not in str(operation_error)
    log_records = [
        record for record in caplog.records if "content_understanding_failed" in record.message
    ]
    assert log_records
    rendered = log_records[0].message
    assert "secret-signature" not in rendered
    logged = json.loads(rendered)
    assert logged["event"] == "content_understanding_failed"
    assert logged["details"]["operationError"]["code"] == "InvalidContent"


def test_poll_content_understanding_http_error_logs_sanitized_details(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FakeClient:
        def get_result(self, operation_url: str) -> dict[str, object]:
            assert operation_url == "https://foundry.example/operations/op-a"
            raise AppError(
                code="CONTENT_UNDERSTANDING_FAILED",
                message="Content Understanding による動画解析に失敗しました。",
                http_status=502,
                details={
                    "statusCode": 502,
                    "operationError": {
                        "code": "BadGateway",
                        "message": "Could not fetch [REDACTED_URL]",
                    },
                },
            )

    monkeypatch.setattr(
        workflow_activities.AppSettings,
        "from_env",
        lambda: SimpleNamespace(),
    )
    monkeypatch.setattr(
        workflow_activities,
        "build_content_understanding_client",
        lambda _settings: FakeClient(),
    )

    caplog.set_level(logging.ERROR, logger=workflow_activities.LOGGER.name)

    result = poll_content_understanding_analysis(
        {
            "job": {"tenantId": "tenant-a", "jobId": "job-a"},
            "operationUrl": "https://foundry.example/operations/op-a",
        }
    )

    error = result["error"]
    assert isinstance(error, dict)
    assert error["statusCode"] == 502
    log_records = [
        record for record in caplog.records if "content_understanding_failed" in record.message
    ]
    assert log_records
    logged = json.loads(log_records[0].message)
    assert logged["details"]["statusCode"] == 502
    assert logged["details"]["operationError"]["code"] == "BadGateway"


def test_poll_content_understanding_running_updates_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeRecord:
        def __init__(self) -> None:
            self.saved_update: dict[str, object] | None = None

        def model_copy(self, update: dict[str, object]) -> FakeRecord:
            self.saved_update = update
            return self

    class FakeRepository:
        def __init__(self) -> None:
            self.record = FakeRecord()
            self.saved: FakeRecord | None = None

        def get(self, tenant_id: str, job_id: str) -> FakeRecord:
            assert (tenant_id, job_id) == ("tenant-a", "job-a")
            return self.record

        def save(self, record: FakeRecord) -> None:
            self.saved = record

    class FakeClient:
        def get_result(self, operation_url: str) -> dict[str, object]:
            assert operation_url == "https://foundry.example/operations/op-a"
            return {"status": "Running"}

    repo = FakeRepository()
    monkeypatch.setattr(
        workflow_activities.AppSettings,
        "from_env",
        lambda: SimpleNamespace(),
    )
    monkeypatch.setattr(
        workflow_activities,
        "build_content_understanding_client",
        lambda _settings: FakeClient(),
    )
    monkeypatch.setattr(workflow_activities, "build_job_repository", lambda _settings: repo)

    result = poll_content_understanding_analysis(
        {
            "job": {"tenantId": "tenant-a", "jobId": "job-a"},
            "operationUrl": "https://foundry.example/operations/op-a",
            "pollAttempt": 3,
        }
    )

    assert result == {"status": "Running"}
    assert repo.saved is repo.record
    assert repo.record.saved_update is not None
    progress = repo.record.saved_update["progress"]
    assert isinstance(progress, Progress)
    expected_message = "Content Understandingで動画を解析しています。状態: Running（確認 3 回目）"
    assert progress.message == expected_message
