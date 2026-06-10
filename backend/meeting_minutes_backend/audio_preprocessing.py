from __future__ import annotations

import os
import re
import subprocess
import tempfile
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

import imageio_ffmpeg

from meeting_minutes_backend.blob_sas import BlobSasIssuer, UploadSas
from meeting_minutes_backend.errors import AppError
from meeting_minutes_backend.file_names import PREPROCESS_EXTENSIONS, should_preprocess_media
from meeting_minutes_backend.models import InputConstraints

PREPROCESSED_CONTENT_TYPE = "audio/flac"
PREPROCESSED_EXTENSION = ".flac"
DURATION_PATTERN = re.compile(
    r"Duration:\s(?P<hours>\d{2}):(?P<minutes>\d{2}):(?P<seconds>\d{2}(?:\.\d+)?)"
)


class BinaryBlobStore(Protocol):
    def download_to_path(
        self,
        container_name: str,
        blob_name: str,
        destination_path: str | os.PathLike[str],
    ) -> None:
        pass

    def upload_file(
        self,
        container_name: str,
        blob_name: str,
        source_path: str | os.PathLike[str],
        content_type: str,
    ) -> str:
        pass


@dataclass(frozen=True)
class PreparedTranscriptionInput:
    audio_sas: UploadSas
    engine: str
    duration_seconds: float | None
    audio_size_bytes: int
    preprocessed: bool


class AudioTranscoder(Protocol):
    def transcode_to_fast_transcription_audio(
        self,
        source_path: Path,
        destination_path: Path,
    ) -> None:
        pass


class MediaDurationProbe(Protocol):
    def duration_seconds(self, source_path: Path) -> float | None:
        pass


class FfmpegAudioTranscoder:
    def __init__(
        self,
        ffmpeg_exe: str | None = None,
        timeout_seconds: int = 1800,
    ) -> None:
        self._ffmpeg_exe = ffmpeg_exe or imageio_ffmpeg.get_ffmpeg_exe()
        self._timeout_seconds = timeout_seconds

    def transcode_to_fast_transcription_audio(
        self,
        source_path: Path,
        destination_path: Path,
    ) -> None:
        command = [
            self._ffmpeg_exe,
            "-hide_banner",
            "-nostdin",
            "-y",
            "-i",
            str(source_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-sample_fmt",
            "s16",
            "-c:a",
            "flac",
            str(destination_path),
        ]
        try:
            subprocess.run(  # noqa: S603
                command,
                check=True,
                capture_output=True,
                timeout=self._timeout_seconds,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            raise _preprocess_error() from exc


class FfmpegMediaDurationProbe:
    def __init__(self, ffmpeg_exe: str | None = None, timeout_seconds: int = 60) -> None:
        self._ffmpeg_exe = ffmpeg_exe or imageio_ffmpeg.get_ffmpeg_exe()
        self._timeout_seconds = timeout_seconds

    def duration_seconds(self, source_path: Path) -> float | None:
        command = [
            self._ffmpeg_exe,
            "-hide_banner",
            "-nostdin",
            "-i",
            str(source_path),
        ]
        try:
            result = subprocess.run(  # noqa: S603
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            raise _preprocess_error() from exc
        match = DURATION_PATTERN.search(result.stderr or "")
        if match is None:
            return None
        return (
            int(match.group("hours")) * 3600
            + int(match.group("minutes")) * 60
            + float(match.group("seconds"))
        )


def should_preprocess_audio(blob_name: str, content_type: str) -> bool:
    return should_preprocess_media(blob_name, content_type)


def prepare_audio_for_transcription(
    *,
    tenant_id: str,
    job_id: str,
    blob_name: str,
    content_type: str,
    container_name: str,
    store: BinaryBlobStore,
    sas_issuer: BlobSasIssuer,
    now: datetime,
    transcoder: AudioTranscoder | None = None,
    duration_probe: MediaDurationProbe | None = None,
    constraints: InputConstraints | None = None,
    source_size_bytes: int | None = None,
    batch_read_sas_ttl_minutes: int | None = None,
    temporary_directory: Callable[
        [], AbstractContextManager[str]
    ] = tempfile.TemporaryDirectory,
) -> UploadSas:
    return prepare_transcription_input(
        tenant_id=tenant_id,
        job_id=job_id,
        blob_name=blob_name,
        content_type=content_type,
        container_name=container_name,
        store=store,
        sas_issuer=sas_issuer,
        now=now,
        transcoder=transcoder,
        duration_probe=duration_probe,
        constraints=constraints,
        source_size_bytes=source_size_bytes,
        batch_read_sas_ttl_minutes=batch_read_sas_ttl_minutes,
        temporary_directory=temporary_directory,
    ).audio_sas


def prepare_transcription_input(
    *,
    tenant_id: str,
    job_id: str,
    blob_name: str,
    content_type: str,
    container_name: str,
    store: BinaryBlobStore,
    sas_issuer: BlobSasIssuer,
    now: datetime,
    transcoder: AudioTranscoder | None = None,
    duration_probe: MediaDurationProbe | None = None,
    constraints: InputConstraints | None = None,
    source_size_bytes: int | None = None,
    batch_read_sas_ttl_minutes: int | None = None,
    temporary_directory: Callable[
        [],
        AbstractContextManager[str],
    ] = tempfile.TemporaryDirectory,
) -> PreparedTranscriptionInput:
    if not should_preprocess_audio(blob_name, content_type):
        duration_seconds: float | None = None
        with temporary_directory() as temp_dir:
            temp_path = Path(temp_dir)
            suffix = Path(blob_name).suffix.lower()
            source_path = temp_path / f"input{suffix if suffix else '.media'}"
            store.download_to_path(container_name, blob_name, source_path)
            duration_probe = duration_probe or FfmpegMediaDurationProbe()
            duration_seconds = duration_probe.duration_seconds(source_path)
            _ensure_within_batch_duration(duration_seconds, constraints or InputConstraints())
        audio_size_bytes = 0
        engine = _select_transcription_engine(
            duration_seconds=duration_seconds,
            audio_size_bytes=source_size_bytes or audio_size_bytes,
            constraints=constraints or InputConstraints(),
        )
        return PreparedTranscriptionInput(
            audio_sas=_create_read_sas_for_engine(
                sas_issuer=sas_issuer,
                blob_name=blob_name,
                now=now,
                engine=engine,
                batch_read_sas_ttl_minutes=batch_read_sas_ttl_minutes,
            ),
            engine=engine,
            duration_seconds=duration_seconds,
            audio_size_bytes=source_size_bytes or audio_size_bytes,
            preprocessed=False,
        )

    target_blob_name = preprocessed_blob_name(tenant_id, job_id)
    transcoder = transcoder or FfmpegAudioTranscoder()
    duration_probe = duration_probe or FfmpegMediaDurationProbe()
    constraints = constraints or InputConstraints()

    with temporary_directory() as temp_dir:
        temp_path = Path(temp_dir)
        suffix = Path(blob_name).suffix.lower()
        source_path = temp_path / f"input{suffix if suffix in PREPROCESS_EXTENSIONS else '.media'}"
        converted_path = temp_path / f"input{PREPROCESSED_EXTENSION}"
        store.download_to_path(container_name, blob_name, source_path)
        duration_seconds = duration_probe.duration_seconds(source_path)
        if (
            duration_seconds is not None
            and duration_seconds >= constraints.batchMaxDurationSecondsWithDiarization
        ):
            _raise_batch_duration_error(constraints)
        transcoder.transcode_to_fast_transcription_audio(source_path, converted_path)
        if not converted_path.exists():
            raise _preprocess_error()
        audio_size_bytes = converted_path.stat().st_size
        if audio_size_bytes >= constraints.batchMaxFileSizeBytes:
            raise AppError(
                code="BATCH_TRANSCRIPTION_INPUT_TOO_LARGE",
                message="Batch Transcriptionの上限サイズを超えています。",
                http_status=400,
                details={"batchMaxFileSizeBytes": constraints.batchMaxFileSizeBytes},
            )
        store.upload_file(
            container_name,
            target_blob_name,
            converted_path,
            PREPROCESSED_CONTENT_TYPE,
        )

    engine = _select_transcription_engine(
        duration_seconds=duration_seconds,
        audio_size_bytes=audio_size_bytes,
        constraints=constraints,
    )
    return PreparedTranscriptionInput(
        audio_sas=_create_read_sas_for_engine(
            sas_issuer=sas_issuer,
            blob_name=target_blob_name,
            now=now,
            engine=engine,
            batch_read_sas_ttl_minutes=batch_read_sas_ttl_minutes,
        ),
        engine=engine,
        duration_seconds=duration_seconds,
        audio_size_bytes=audio_size_bytes,
        preprocessed=True,
    )


def preprocessed_blob_name(tenant_id: str, job_id: str) -> str:
    return f"preprocessed/{tenant_id}/{job_id}/input{PREPROCESSED_EXTENSION}"


def _select_transcription_engine(
    *,
    duration_seconds: float | None,
    audio_size_bytes: int,
    constraints: InputConstraints,
) -> str:
    if (
        duration_seconds is not None
        and duration_seconds >= constraints.maxDurationSecondsWithDiarization
    ):
        return "batch"
    if audio_size_bytes >= constraints.hardMaxFileSizeBytes:
        return "batch"
    return "fast"


def _create_read_sas_for_engine(
    *,
    sas_issuer: BlobSasIssuer,
    blob_name: str,
    now: datetime,
    engine: str,
    batch_read_sas_ttl_minutes: int | None,
) -> UploadSas:
    ttl_minutes = batch_read_sas_ttl_minutes if engine == "batch" else None
    return sas_issuer.create_read_sas(blob_name, now, ttl_minutes=ttl_minutes)


def _ensure_within_batch_duration(
    duration_seconds: float | None,
    constraints: InputConstraints,
) -> None:
    if (
        duration_seconds is not None
        and duration_seconds >= constraints.batchMaxDurationSecondsWithDiarization
    ):
        _raise_batch_duration_error(constraints)


def _raise_batch_duration_error(constraints: InputConstraints) -> None:
    raise AppError(
        code="AUDIO_TOO_LONG_FOR_BATCH",
        message="Batch Transcriptionの上限時間を超えています。",
        http_status=400,
        details={
            "batchMaxDurationSecondsWithDiarization": (
                constraints.batchMaxDurationSecondsWithDiarization
            )
        },
    )


def _preprocess_error() -> AppError:
    return AppError(
        code="AUDIO_PREPROCESS_FAILED",
        message="音声または動画ファイルを文字起こし用に変換できませんでした。音声トラックが含まれているか確認してください。",
        http_status=400,
    )
