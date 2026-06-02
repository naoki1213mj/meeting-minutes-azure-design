from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime
from pathlib import Path
from typing import Protocol

import imageio_ffmpeg

from meeting_minutes_backend.blob_sas import BlobSasIssuer, UploadSas
from meeting_minutes_backend.errors import AppError
from meeting_minutes_backend.models import InputConstraints

PREPROCESS_CONTENT_TYPES = frozenset(
    {
        "application/mp4",
        "audio/aac",
        "audio/m4a",
        "audio/mp4",
        "audio/x-m4a",
        "video/mp4",
    }
)
PREPROCESS_EXTENSIONS = frozenset({".m4a", ".mp4"})
PREPROCESSED_CONTENT_TYPE = "audio/flac"
PREPROCESSED_EXTENSION = ".flac"


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


class AudioTranscoder(Protocol):
    def transcode_to_fast_transcription_audio(
        self,
        source_path: Path,
        destination_path: Path,
    ) -> None:
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


def should_preprocess_audio(blob_name: str, content_type: str) -> bool:
    content_type_key = content_type.split(";", 1)[0].strip().lower()
    return (
        Path(blob_name).suffix.lower() in PREPROCESS_EXTENSIONS
        or content_type_key in PREPROCESS_CONTENT_TYPES
    )


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
    constraints: InputConstraints | None = None,
    temporary_directory: Callable[
        [], AbstractContextManager[str]
    ] = tempfile.TemporaryDirectory,
) -> UploadSas:
    if not should_preprocess_audio(blob_name, content_type):
        return sas_issuer.create_read_sas(blob_name, now)

    target_blob_name = preprocessed_blob_name(tenant_id, job_id)
    transcoder = transcoder or FfmpegAudioTranscoder()
    constraints = constraints or InputConstraints()

    with temporary_directory() as temp_dir:
        temp_path = Path(temp_dir)
        suffix = Path(blob_name).suffix.lower()
        source_path = temp_path / f"input{suffix if suffix in PREPROCESS_EXTENSIONS else '.media'}"
        converted_path = temp_path / f"input{PREPROCESSED_EXTENSION}"
        store.download_to_path(container_name, blob_name, source_path)
        transcoder.transcode_to_fast_transcription_audio(source_path, converted_path)
        if not converted_path.exists():
            raise _preprocess_error()
        if converted_path.stat().st_size > constraints.hardMaxFileSizeBytes:
            raise AppError(
                code="AUDIO_EXCEEDS_HARD_LIMIT",
                message="変換後の音声サイズが上限を超えています。",
                http_status=400,
                details={"hardMaxFileSizeBytes": constraints.hardMaxFileSizeBytes},
            )
        store.upload_file(
            container_name,
            target_blob_name,
            converted_path,
            PREPROCESSED_CONTENT_TYPE,
        )

    return sas_issuer.create_read_sas(target_blob_name, now)


def preprocessed_blob_name(tenant_id: str, job_id: str) -> str:
    return f"preprocessed/{tenant_id}/{job_id}/input{PREPROCESSED_EXTENSION}"


def _preprocess_error() -> AppError:
    return AppError(
        code="AUDIO_PREPROCESS_FAILED",
        message="音声または動画ファイルを文字起こし用に変換できませんでした。音声トラックが含まれているか確認してください。",
        http_status=400,
    )
