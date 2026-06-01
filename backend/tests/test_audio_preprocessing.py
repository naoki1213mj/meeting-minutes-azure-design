from __future__ import annotations

import shutil
import tempfile
from datetime import UTC, datetime
from os import PathLike
from pathlib import Path

import pytest

from meeting_minutes_backend.audio_preprocessing import (
    PREPROCESSED_CONTENT_TYPE,
    prepare_audio_for_transcription,
    preprocessed_blob_name,
    should_preprocess_audio,
)
from meeting_minutes_backend.blob_sas import UploadSas
from meeting_minutes_backend.errors import AppError


class FakeStore:
    def __init__(self) -> None:
        self.downloads: list[tuple[str, str]] = []
        self.uploads: list[tuple[str, str, str]] = []

    def download_to_path(
        self,
        container_name: str,
        blob_name: str,
        destination_path: str | PathLike[str],
    ) -> None:
        self.downloads.append((container_name, blob_name))
        Path(destination_path).write_bytes(b"m4a")

    def upload_file(
        self,
        container_name: str,
        blob_name: str,
        source_path: str | PathLike[str],
        content_type: str,
    ) -> str:
        self.uploads.append((container_name, blob_name, content_type))
        assert Path(source_path).read_bytes() == b"flac"
        return f"https://storage.example/{container_name}/{blob_name}"


class FakeSasIssuer:
    def __init__(self) -> None:
        self.read_blob_names: list[str] = []

    def create_upload_sas(self, blob_name: str, now: datetime) -> UploadSas:
        _ = (blob_name, now)
        raise NotImplementedError

    def create_read_sas(self, blob_name: str, now: datetime) -> UploadSas:
        self.read_blob_names.append(blob_name)
        return UploadSas(url=f"https://storage.example/{blob_name}?sig=redacted", expires_at=now)


class FakeTranscoder:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[Path, Path]] = []

    def transcode_to_fast_transcription_audio(
        self,
        source_path: Path,
        destination_path: Path,
    ) -> None:
        self.calls.append((source_path, destination_path))
        if self.fail:
            raise AppError(
                code="AUDIO_PREPROCESS_FAILED",
                message="m4a音声を文字起こし用に変換できませんでした。",
                http_status=400,
            )
        destination_path.write_bytes(b"flac")


class TrackingTemporaryDirectory:
    last_path: Path | None = None

    def __init__(self) -> None:
        self._path = Path(tempfile.mkdtemp())
        TrackingTemporaryDirectory.last_path = self._path

    def __enter__(self) -> str:
        return str(self._path)

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        shutil.rmtree(self._path)


@pytest.mark.parametrize(
    ("blob_name", "content_type", "expected"),
    [
        ("raw/job/input.m4a", "audio/x-m4a", True),
        ("raw/job/input.m4a", "application/octet-stream", True),
        ("raw/job/input.mp3", "audio/mpeg", False),
    ],
)
def test_should_preprocess_audio(blob_name: str, content_type: str, expected: bool) -> None:
    assert should_preprocess_audio(blob_name, content_type) is expected


def test_prepare_audio_for_transcription_converts_m4a_to_flac_blob() -> None:
    store = FakeStore()
    sas_issuer = FakeSasIssuer()
    transcoder = FakeTranscoder()
    now = datetime(2026, 6, 1, tzinfo=UTC)

    result = prepare_audio_for_transcription(
        tenant_id="tenant-a",
        job_id="job-a",
        blob_name="raw-audio/tenant-a/job-a/input.m4a",
        content_type="audio/x-m4a",
        container_name="audio",
        store=store,
        sas_issuer=sas_issuer,
        now=now,
        transcoder=transcoder,
        temporary_directory=TrackingTemporaryDirectory,
    )

    expected_blob = preprocessed_blob_name("tenant-a", "job-a")
    assert store.downloads == [("audio", "raw-audio/tenant-a/job-a/input.m4a")]
    assert store.uploads == [("audio", expected_blob, PREPROCESSED_CONTENT_TYPE)]
    assert sas_issuer.read_blob_names == [expected_blob]
    assert result.url.endswith(f"{expected_blob}?sig=redacted")
    assert TrackingTemporaryDirectory.last_path is not None
    assert not TrackingTemporaryDirectory.last_path.exists()


def test_prepare_audio_for_transcription_skips_non_m4a() -> None:
    store = FakeStore()
    sas_issuer = FakeSasIssuer()

    prepare_audio_for_transcription(
        tenant_id="tenant-a",
        job_id="job-a",
        blob_name="raw-audio/tenant-a/job-a/input.mp3",
        content_type="audio/mpeg",
        container_name="audio",
        store=store,
        sas_issuer=sas_issuer,
        now=datetime(2026, 6, 1, tzinfo=UTC),
        transcoder=FakeTranscoder(),
    )

    assert store.downloads == []
    assert store.uploads == []
    assert sas_issuer.read_blob_names == ["raw-audio/tenant-a/job-a/input.mp3"]


def test_prepare_audio_for_transcription_hides_transcoder_details_on_failure() -> None:
    with pytest.raises(AppError) as exc_info:
        prepare_audio_for_transcription(
            tenant_id="tenant-a",
            job_id="job-a",
            blob_name="raw-audio/tenant-a/job-a/input.m4a",
            content_type="audio/x-m4a",
            container_name="audio",
            store=FakeStore(),
            sas_issuer=FakeSasIssuer(),
            now=datetime(2026, 6, 1, tzinfo=UTC),
            transcoder=FakeTranscoder(fail=True),
        )

    assert exc_info.value.code == "AUDIO_PREPROCESS_FAILED"
    assert exc_info.value.details == {}
