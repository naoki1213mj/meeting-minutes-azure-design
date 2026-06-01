from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import azure.functions as func
import pytest

import meeting_minutes_backend.entrypoints as entrypoints
from meeting_minutes_backend.models import JobStatus, JobStatusResponse, Outputs, Progress


class _FakeJobService:
    def __init__(self, outputs: Outputs) -> None:
        self._outputs = outputs

    def get_job(self, auth: object, job_id: str) -> JobStatusResponse:
        _ = auth
        return JobStatusResponse(
            jobId=job_id,
            tenantId="tenant-a",
            userId="user-a",
            status=JobStatus.DONE,
            progress=Progress(
                step=JobStatus.DONE.value,
                percent=100,
                message="Done",
                updatedAt=datetime(2025, 1, 1, tzinfo=UTC),
            ),
            outputs=self._outputs,
            createdAt=datetime(2025, 1, 1, tzinfo=UTC),
            updatedAt=datetime(2025, 1, 1, tzinfo=UTC),
        )


class _FakeArtifactStore:
    def __init__(
        self,
        json_artifacts: dict[str, dict[str, Any]],
        text_artifacts: dict[str, str],
    ) -> None:
        self._json_artifacts = json_artifacts
        self._text_artifacts = text_artifacts

    def read_json(self, container_name: str, blob_name: str) -> dict[str, Any]:
        return self._json_artifacts[f"{container_name}/{blob_name}"]

    def read_text(self, container_name: str, blob_name: str) -> str:
        return self._text_artifacts[f"{container_name}/{blob_name}"]


def _request(url: str, params: dict[str, str] | None = None) -> func.HttpRequest:
    return func.HttpRequest(
        method="GET",
        url=url,
        headers={
            "x-correlation-id": "test-correlation",
            "x-dev-tenant-id": "tenant-a",
            "x-dev-user-id": "user-a",
        },
        params=params or {},
        body=b"",
    )


def _patch_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    outputs: Outputs,
    store: _FakeArtifactStore,
) -> None:
    monkeypatch.setattr(entrypoints, "get_job_service", lambda: _FakeJobService(outputs))
    monkeypatch.setattr(
        entrypoints.AppSettings,
        "from_env",
        lambda: SimpleNamespace(
            transcript_container_name="transcripts",
            minutes_container_name="minutes",
        ),
    )
    monkeypatch.setattr(entrypoints, "build_artifact_store", lambda settings: store)


def test_get_transcript_returns_normalized_artifact(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _FakeArtifactStore(
        json_artifacts={"transcripts/jobs/job-a/normalized.json": {"jobId": "job-a"}},
        text_artifacts={},
    )
    _patch_dependencies(
        monkeypatch,
        Outputs(
            transcriptReady=True,
            minutesReady=True,
            normalizedTranscriptBlobUri=(
                "https://storage.blob.core.windows.net/transcripts/jobs/job-a/normalized.json"
            ),
        ),
        store,
    )

    response = entrypoints.get_transcript(_request("/api/jobs/job-a/transcript"), "job-a")

    assert response.status_code == 200
    assert response.headers["x-correlation-id"] == "test-correlation"
    assert json.loads(response.get_body()) == {"jobId": "job-a"}


def test_get_minutes_returns_json_artifact(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _FakeArtifactStore(
        json_artifacts={"minutes/jobs/job-a/minutes.json": {"title": "議事録"}},
        text_artifacts={},
    )
    _patch_dependencies(
        monkeypatch,
        Outputs(
            transcriptReady=True,
            minutesReady=True,
            minutesJsonBlobUri="https://storage.blob.core.windows.net/minutes/jobs/job-a/minutes.json",
        ),
        store,
    )

    response = entrypoints.get_minutes(_request("/api/jobs/job-a/minutes"), "job-a")

    assert response.status_code == 200
    assert response.headers["x-correlation-id"] == "test-correlation"
    assert json.loads(response.get_body()) == {"title": "議事録"}


def test_get_minutes_returns_markdown_artifact(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _FakeArtifactStore(
        json_artifacts={},
        text_artifacts={"minutes/jobs/job-a/minutes.md": "# 議事録"},
    )
    _patch_dependencies(
        monkeypatch,
        Outputs(
            transcriptReady=True,
            minutesReady=True,
            minutesMarkdownBlobUri="https://storage.blob.core.windows.net/minutes/jobs/job-a/minutes.md",
        ),
        store,
    )

    response = entrypoints.get_minutes(
        _request("/api/jobs/job-a/minutes?format=markdown", {"format": "markdown"}),
        "job-a",
    )

    assert response.status_code == 200
    assert response.headers["x-correlation-id"] == "test-correlation"
    assert response.get_body().decode("utf-8") == "# 議事録"


def test_get_transcript_returns_not_ready_when_artifact_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_dependencies(monkeypatch, Outputs(), _FakeArtifactStore({}, {}))

    response = entrypoints.get_transcript(_request("/api/jobs/job-a/transcript"), "job-a")
    body = json.loads(response.get_body())

    assert response.status_code == 404
    assert response.headers["x-correlation-id"] == "test-correlation"
    assert body["error"]["code"] == "TRANSCRIPT_NOT_READY"


def test_get_minutes_returns_json_not_ready_with_correlation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_dependencies(monkeypatch, Outputs(), _FakeArtifactStore({}, {}))

    response = entrypoints.get_minutes(_request("/api/jobs/job-a/minutes"), "job-a")
    body = json.loads(response.get_body())

    assert response.status_code == 404
    assert response.headers["x-correlation-id"] == "test-correlation"
    assert body["error"]["code"] == "MINUTES_NOT_READY"


def test_get_minutes_returns_markdown_not_ready_with_correlation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_dependencies(monkeypatch, Outputs(), _FakeArtifactStore({}, {}))

    response = entrypoints.get_minutes(
        _request("/api/jobs/job-a/minutes?format=markdown", {"format": "markdown"}),
        "job-a",
    )
    body = json.loads(response.get_body())

    assert response.status_code == 404
    assert response.headers["x-correlation-id"] == "test-correlation"
    assert body["error"]["code"] == "MINUTES_NOT_READY"


def test_get_minutes_rejects_artifact_uri_for_other_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_dependencies(
        monkeypatch,
        Outputs(
            minutesReady=True,
            minutesJsonBlobUri="https://storage.blob.core.windows.net/other/jobs/job-a/minutes.json",
        ),
        _FakeArtifactStore({}, {}),
    )

    response = entrypoints.get_minutes(_request("/api/jobs/job-a/minutes"), "job-a")
    body = json.loads(response.get_body())

    assert response.status_code == 500
    assert response.headers["x-correlation-id"] == "test-correlation"
    assert body["error"]["code"] == "ARTIFACT_URI_INVALID"


def test_blob_name_from_url_rejects_other_container() -> None:
    with pytest.raises(entrypoints.AppError) as exc_info:
        entrypoints._blob_name_from_url(  # noqa: SLF001
            "https://storage.blob.core.windows.net/other/jobs/job-a/minutes.json",
            "minutes",
        )

    assert exc_info.value.code == "ARTIFACT_URI_INVALID"
