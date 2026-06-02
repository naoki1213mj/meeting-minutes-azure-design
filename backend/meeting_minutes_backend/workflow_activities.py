from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from meeting_minutes_backend.audio_preprocessing import (
    prepare_audio_for_transcription,
    should_preprocess_audio,
)
from meeting_minutes_backend.content_understanding_client import ContentUnderstandingRequest
from meeting_minutes_backend.content_understanding_normalizer import (
    build_visual_context,
    normalize_content_understanding_transcript,
)
from meeting_minutes_backend.errors import AppError
from meeting_minutes_backend.markdown_renderer import render_minutes_markdown
from meeting_minutes_backend.minutes_generation import (
    TranscriptChunk,
    build_transcript_chunks,
    generate_chunk_summary,
    generate_final_minutes_from_summaries,
    generate_minutes_from_full_transcript,
)
from meeting_minutes_backend.models import ErrorObject, JobStatus, ProcessingRoute, Progress
from meeting_minutes_backend.settings import (
    AppSettings,
    build_artifact_store,
    build_blob_sas_issuer,
    build_chunk_deployment,
    build_content_understanding_client,
    build_job_repository,
    build_minutes_deployment,
    build_openai_client,
    build_speech_client,
)
from meeting_minutes_backend.speech_client import TranscriptionRequest
from meeting_minutes_backend.transcript_normalizer import normalize_transcript

LOGGER = logging.getLogger(__name__)


def load_job(payload: dict[str, object]) -> dict[str, object]:
    tenant_id = _required_string(payload, "tenantId")
    job_id = _required_string(payload, "jobId")
    repository = build_job_repository(AppSettings.from_env())
    record = repository.get(tenant_id, job_id)
    if record is None:
        raise AppError(
            code="JOB_NOT_FOUND",
            message="指定されたジョブが見つかりません。",
            http_status=404,
        )
    return record.model_dump(mode="json")


def validate_input(job: dict[str, object]) -> dict[str, object]:
    tenant_id = _required_string(job, "tenantId")
    job_id = _required_string(job, "jobId")
    repository = build_job_repository(AppSettings.from_env())
    record = repository.get(tenant_id, job_id)
    if record is None:
        raise AppError(
            code="JOB_NOT_FOUND",
            message="指定されたジョブが見つかりません。",
            http_status=404,
        )
    now = _utc_now()
    updated = record.model_copy(
        update={
            "status": JobStatus.VALIDATING,
            "progress": Progress(
                step=JobStatus.VALIDATING.value,
                percent=5,
                message="入力音声を検証しています。",
                updatedAt=now,
            ),
            "updatedAt": now,
        }
    )
    repository.save(updated)
    return {"jobId": job_id, "valid": True}


def create_read_sas(job: dict[str, object]) -> dict[str, object]:
    tenant_id = _required_string(job, "tenantId")
    job_id = _required_string(job, "jobId")
    settings = AppSettings.from_env()
    repository = build_job_repository(settings)
    record = repository.get(tenant_id, job_id)
    if record is None:
        raise AppError(
            code="JOB_NOT_FOUND",
            message="指定されたジョブが見つかりません。",
            http_status=404,
        )
    now = _utc_now()
    if record.processingRoute == ProcessingRoute.CONTENT_UNDERSTANDING:
        read_sas = build_blob_sas_issuer(settings).create_read_sas(record.blobName, now)
        return {"audioUrl": read_sas.url}

    if (
        record.processingRoute != ProcessingRoute.CONTENT_UNDERSTANDING
        and should_preprocess_audio(record.blobName, record.contentType)
    ):
        repository.save(
            record.model_copy(
                update={
                    "status": JobStatus.PREPROCESSING,
                    "progress": Progress(
                        step=JobStatus.PREPROCESSING.value,
                        percent=15,
                        message="音声を文字起こし用に変換しています。",
                        updatedAt=now,
                    ),
                    "updatedAt": now,
                }
            )
        )
    read_sas = prepare_audio_for_transcription(
        tenant_id=tenant_id,
        job_id=job_id,
        blob_name=record.blobName,
        content_type=record.contentType,
        container_name=settings.storage_container_name,
        store=build_artifact_store(settings),
        sas_issuer=build_blob_sas_issuer(settings),
        now=now,
    )
    return {"audioUrl": read_sas.url}


def start_content_understanding_analysis(payload: dict[str, object]) -> dict[str, object]:
    job = _required_dict(payload, "job")
    content_url = _required_string(payload, "contentUrl")
    tenant_id = _required_string(job, "tenantId")
    job_id = _required_string(job, "jobId")
    settings = AppSettings.from_env()
    repository = build_job_repository(settings)
    record = repository.get(tenant_id, job_id)
    if record is None:
        raise AppError(
            code="JOB_NOT_FOUND",
            message="指定されたジョブが見つかりません。",
            http_status=404,
        )

    now = _utc_now()
    repository.save(
        record.model_copy(
            update={
                "status": JobStatus.TRANSCRIBING,
                "progress": Progress(
                    step="ANALYZING_CONTENT",
                    percent=20,
                    message="Content Understandingで動画を解析しています。",
                    updatedAt=now,
                ),
                "updatedAt": now,
            }
        )
    )
    operation_url = build_content_understanding_client(settings).start_analysis(
        ContentUnderstandingRequest(content_url=content_url)
    )
    return {"operationUrl": operation_url}


def poll_content_understanding_analysis(payload: dict[str, object]) -> dict[str, object]:
    job = _required_dict(payload, "job")
    operation_url = _required_string(payload, "operationUrl")
    tenant_id = _required_string(job, "tenantId")
    job_id = _required_string(job, "jobId")
    settings = AppSettings.from_env()
    result = build_content_understanding_client(settings).get_result(operation_url)
    status = result.get("status")
    if status != "Succeeded":
        if status in {"Failed", "Canceled"}:
            raise AppError(
                code="CONTENT_UNDERSTANDING_FAILED",
                message="Content Understanding による動画解析に失敗しました。",
                http_status=502,
                details={"operationStatus": str(status)},
            )
        return {"status": str(status or "Running")}

    store = build_artifact_store(settings)
    raw_blob_name = f"raw/{tenant_id}/{job_id}/content-understanding-response.json"
    raw_uri = store.write_json(settings.transcript_container_name, raw_blob_name, result)
    visual_context = build_visual_context(result)
    visual_blob_name = f"visual-context/{tenant_id}/{job_id}/content-understanding.json"
    visual_uri = store.write_json(
        settings.transcript_container_name,
        visual_blob_name,
        visual_context,
    )
    return {
        "status": "Succeeded",
        "rawTranscriptBlobName": raw_blob_name,
        "rawTranscriptBlobUri": raw_uri,
        "visualContextBlobName": visual_blob_name,
        "visualContextBlobUri": visual_uri,
    }


def transcribe_audio(payload: dict[str, object]) -> dict[str, object]:
    job = _required_dict(payload, "job")
    audio_url = _required_string(payload, "audioUrl")
    tenant_id = _required_string(job, "tenantId")
    job_id = _required_string(job, "jobId")
    settings = AppSettings.from_env()
    repository = build_job_repository(settings)
    record = repository.get(tenant_id, job_id)
    if record is None:
        raise AppError(
            code="JOB_NOT_FOUND",
            message="指定されたジョブが見つかりません。",
            http_status=404,
        )

    now = _utc_now()
    repository.save(
        record.model_copy(
            update={
                "status": JobStatus.TRANSCRIBING,
                "progress": Progress(
                    step=JobStatus.TRANSCRIBING.value,
                    percent=20,
                    message="音声を文字起こししています。",
                    updatedAt=now,
                ),
                "updatedAt": now,
            }
        )
    )

    client = build_speech_client(settings)
    raw_response = client.transcribe_audio_url(
        request=TranscriptionRequest(
            audioUrl=audio_url,
            locale=record.locale,
            maxSpeakers=record.maxSpeakers,
        )
    )
    blob_name = f"raw/{tenant_id}/{job_id}/speech-response.json"
    raw_uri = build_artifact_store(settings).write_json(
        settings.transcript_container_name,
        blob_name,
        raw_response,
    )
    return {"rawTranscriptBlobName": blob_name, "rawTranscriptBlobUri": raw_uri}


def normalize_transcript_artifact(payload: dict[str, object]) -> dict[str, object]:
    raw_blob_name = _required_string(payload, "rawTranscriptBlobName")
    raw_blob_uri = _required_string(payload, "rawTranscriptBlobUri")
    job = _required_dict(payload, "job")
    tenant_id = _required_string(job, "tenantId")
    job_id = _required_string(job, "jobId")
    settings = AppSettings.from_env()
    store = build_artifact_store(settings)
    raw_response = store.read_json(settings.transcript_container_name, raw_blob_name)
    normalized = normalize_transcript(
        raw_response,
        job_id=job_id,
        tenant_id=tenant_id,
        locale=str(job.get("locale", "ja-JP")),
        raw_transcript_blob_uri=raw_blob_uri,
        api_version="2025-10-15",
    )
    normalized_blob_name = f"normalized/{tenant_id}/{job_id}/normalized-transcript.json"
    normalized_uri = store.write_json(
        settings.transcript_container_name,
        normalized_blob_name,
        normalized,
    )

    repository = build_job_repository(settings)
    record = repository.get(tenant_id, job_id)
    if record:
        now = _utc_now()
        repository.save(
            record.model_copy(
                update={
                    "status": JobStatus.TRANSCRIPT_READY,
                    "progress": Progress(
                        step=JobStatus.TRANSCRIPT_READY.value,
                        percent=55,
                        message="文字起こしを正規化しました。",
                        updatedAt=now,
                    ),
                    "outputs": record.outputs.model_copy(
                        update={
                            "transcriptReady": True,
                            "rawTranscriptBlobUri": raw_blob_uri,
                            "normalizedTranscriptBlobUri": normalized_uri,
                        }
                    ),
                    "updatedAt": now,
                }
            )
        )
    return {
        "normalizedTranscriptBlobName": normalized_blob_name,
        "normalizedTranscriptBlobUri": normalized_uri,
    }


def normalize_content_understanding_artifact(payload: dict[str, object]) -> dict[str, object]:
    raw_blob_name = _required_string(payload, "rawTranscriptBlobName")
    raw_blob_uri = _required_string(payload, "rawTranscriptBlobUri")
    visual_context_blob_uri = _required_string(payload, "visualContextBlobUri")
    job = _required_dict(payload, "job")
    tenant_id = _required_string(job, "tenantId")
    job_id = _required_string(job, "jobId")
    settings = AppSettings.from_env()
    store = build_artifact_store(settings)
    raw_response = store.read_json(settings.transcript_container_name, raw_blob_name)
    normalized = normalize_content_understanding_transcript(
        raw_response,
        job_id=job_id,
        tenant_id=tenant_id,
        locale=str(job.get("locale", "ja-JP")),
        raw_transcript_blob_uri=raw_blob_uri,
        api_version=settings.content_understanding_api_version,
    )
    normalized_blob_name = f"normalized/{tenant_id}/{job_id}/normalized-transcript.json"
    normalized_uri = store.write_json(
        settings.transcript_container_name,
        normalized_blob_name,
        normalized,
    )

    repository = build_job_repository(settings)
    record = repository.get(tenant_id, job_id)
    if record:
        now = _utc_now()
        repository.save(
            record.model_copy(
                update={
                    "status": JobStatus.TRANSCRIPT_READY,
                    "progress": Progress(
                        step=JobStatus.TRANSCRIPT_READY.value,
                        percent=55,
                        message="Content Understandingの文字起こしを正規化しました。",
                        updatedAt=now,
                    ),
                    "outputs": record.outputs.model_copy(
                        update={
                            "transcriptReady": True,
                            "rawTranscriptBlobUri": raw_blob_uri,
                            "normalizedTranscriptBlobUri": normalized_uri,
                            "visualContextBlobUri": visual_context_blob_uri,
                        }
                    ),
                    "updatedAt": now,
                }
            )
        )
    return {
        "normalizedTranscriptBlobName": normalized_blob_name,
        "normalizedTranscriptBlobUri": normalized_uri,
        "visualContextBlobUri": visual_context_blob_uri,
    }


def build_transcript_chunks_artifact(payload: dict[str, object]) -> list[dict[str, object]]:
    job = _required_dict(payload, "job")
    normalized_blob_name = _required_string(payload, "normalizedTranscriptBlobName")
    tenant_id = _required_string(job, "tenantId")
    job_id = _required_string(job, "jobId")
    settings = AppSettings.from_env()
    store = build_artifact_store(settings)
    normalized = store.read_json(settings.transcript_container_name, normalized_blob_name)

    repository = build_job_repository(settings)
    record = repository.get(tenant_id, job_id)
    if record is not None:
        now = _utc_now()
        repository.save(
            record.model_copy(
                update={
                    "status": JobStatus.GENERATING_CHUNK_SUMMARIES,
                    "progress": Progress(
                        step=JobStatus.GENERATING_CHUNK_SUMMARIES.value,
                        percent=65,
                        message="議事録生成用に文字起こしを分割しています。",
                        updatedAt=now,
                    ),
                    "updatedAt": now,
                }
            )
        )

    chunks = []
    for chunk in build_transcript_chunks(normalized):
        chunk_blob_name = f"chunks/{tenant_id}/{job_id}/chunk-{chunk.chunkIndex}.json"
        chunk_uri = store.write_json(
            settings.transcript_container_name,
            chunk_blob_name,
            chunk.model_dump(mode="json"),
        )
        chunks.append(
            {
                "chunkIndex": chunk.chunkIndex,
                "chunkBlobName": chunk_blob_name,
                "chunkBlobUri": chunk_uri,
            }
        )
    return chunks


def generate_chunk_summary_artifact(payload: dict[str, object]) -> dict[str, object]:
    job = _required_dict(payload, "job")
    chunk_index = _required_int(payload, "chunkIndex")
    chunk_blob_name = _required_string(payload, "chunkBlobName")
    tenant_id = _required_string(job, "tenantId")
    job_id = _required_string(job, "jobId")
    settings = AppSettings.from_env()
    store = build_artifact_store(settings)
    chunk = TranscriptChunk.model_validate(
        store.read_json(settings.transcript_container_name, chunk_blob_name)
    )
    summary = generate_chunk_summary(
        chunk,
        client=build_openai_client(settings),
        chunk_deployment=build_chunk_deployment(settings),
    )
    summary_blob_name = f"chunk-summaries/{tenant_id}/{job_id}/chunk-{chunk_index}-summary.json"
    summary_uri = store.write_json(settings.minutes_container_name, summary_blob_name, summary)
    return {
        "chunkIndex": chunk_index,
        "chunkSummaryBlobName": summary_blob_name,
        "chunkSummaryBlobUri": summary_uri,
    }


def generate_final_minutes(payload: dict[str, object]) -> dict[str, object]:
    job = _required_dict(payload, "job")
    normalized_blob_name = _required_string(payload, "normalizedTranscriptBlobName")
    tenant_id = _required_string(job, "tenantId")
    job_id = _required_string(job, "jobId")
    settings = AppSettings.from_env()
    repository = build_job_repository(settings)
    record = repository.get(tenant_id, job_id)
    if record is None:
        raise AppError(
            code="JOB_NOT_FOUND",
            message="指定されたジョブが見つかりません。",
            http_status=404,
        )

    now = _utc_now()
    repository.save(
        record.model_copy(
            update={
                "status": JobStatus.GENERATING_FINAL_MINUTES,
                "progress": Progress(
                    step=JobStatus.GENERATING_FINAL_MINUTES.value,
                    percent=75,
                    message="議事録を生成しています。",
                    updatedAt=now,
                ),
                "updatedAt": now,
            }
        )
    )

    store = build_artifact_store(settings)
    normalized = store.read_json(settings.transcript_container_name, normalized_blob_name)
    chunk_summary_refs = payload.get("chunkSummaries")
    client = build_openai_client(settings)
    minutes_deployment = build_minutes_deployment(settings, record.minutesModel)
    if isinstance(chunk_summary_refs, list):
        refs = []
        for item in chunk_summary_refs:
            if not isinstance(item, dict):
                raise TypeError("chunkSummaries items must be objects")
            refs.append(item)
        chunk_summaries = [
            store.read_json(
                settings.minutes_container_name,
                _required_string(ref, "chunkSummaryBlobName"),
            )
            for ref in sorted(refs, key=lambda item: _required_int(item, "chunkIndex"))
        ]
        minutes = generate_final_minutes_from_summaries(
            normalized,
            chunk_summaries,
            job_id=job_id,
            tenant_id=tenant_id,
            meeting_title=record.meetingTitle or record.originalFileName,
            client=client,
            final_deployment=minutes_deployment,
        )
    else:
        try:
            minutes = generate_minutes_from_full_transcript(
                normalized,
                job_id=job_id,
                tenant_id=tenant_id,
                meeting_title=record.meetingTitle or record.originalFileName,
                client=client,
                final_deployment=minutes_deployment,
            )
            _log_minutes_generation_mode(
                tenant_id=tenant_id,
                job_id=job_id,
                mode="direct",
                minutes_model=record.minutesModel.value,
            )
        except AppError as error:
            if not _should_fallback_to_chunk_minutes(error):
                raise
            chunk_summaries = [
                generate_chunk_summary(
                    chunk,
                    client=client,
                    chunk_deployment=build_chunk_deployment(settings),
                )
                for chunk in build_transcript_chunks(normalized)
            ]
            minutes = generate_final_minutes_from_summaries(
                normalized,
                chunk_summaries,
                job_id=job_id,
                tenant_id=tenant_id,
                meeting_title=record.meetingTitle or record.originalFileName,
                client=client,
                final_deployment=minutes_deployment,
            )
            _log_minutes_generation_mode(
                tenant_id=tenant_id,
                job_id=job_id,
                mode="chunk_fallback",
                minutes_model=record.minutesModel.value,
                fallback_reason=error.code,
            )
    minutes_blob_name = f"{tenant_id}/{job_id}/minutes.json"
    minutes_uri = store.write_json(settings.minutes_container_name, minutes_blob_name, minutes)
    return {"minutesJsonBlobName": minutes_blob_name, "minutesJsonBlobUri": minutes_uri}


def render_markdown(payload: dict[str, object]) -> dict[str, object]:
    minutes_blob_name = _required_string(payload, "minutesJsonBlobName")
    minutes_uri = _required_string(payload, "minutesJsonBlobUri")
    job = _required_dict(payload, "job")
    tenant_id = _required_string(job, "tenantId")
    job_id = _required_string(job, "jobId")
    settings = AppSettings.from_env()
    store = build_artifact_store(settings)
    minutes = store.read_json(settings.minutes_container_name, minutes_blob_name)
    markdown = render_minutes_markdown(minutes)
    markdown_blob_name = f"{tenant_id}/{job_id}/minutes.md"
    markdown_uri = store.write_text(settings.minutes_container_name, markdown_blob_name, markdown)
    return {
        "minutesJsonBlobUri": minutes_uri,
        "minutesMarkdownBlobUri": markdown_uri,
    }


def complete_job(payload: dict[str, object]) -> dict[str, object]:
    tenant_id = _required_string(payload, "tenantId")
    job_id = _required_string(payload, "jobId")
    repository = build_job_repository(AppSettings.from_env())
    record = repository.get(tenant_id, job_id)
    if record is None:
        raise AppError(
            code="JOB_NOT_FOUND",
            message="指定されたジョブが見つかりません。",
            http_status=404,
        )
    now = _utc_now()
    updated = record.model_copy(
        update={
            "status": JobStatus.DONE,
            "progress": Progress(
                step=JobStatus.DONE.value,
                percent=100,
                message="議事録生成が完了しました。",
                updatedAt=now,
            ),
            "outputs": record.outputs.model_copy(
                update={
                    "minutesReady": True,
                    "minutesJsonBlobUri": _required_string(payload, "minutesJsonBlobUri"),
                    "minutesMarkdownBlobUri": _required_string(
                        payload,
                        "minutesMarkdownBlobUri",
                    ),
                }
            ),
            "updatedAt": now,
        }
    )
    repository.save(updated)
    return {
        "jobId": job_id,
        "status": JobStatus.DONE.value,
        "minutesJsonBlobUri": updated.outputs.minutesJsonBlobUri,
        "minutesMarkdownBlobUri": updated.outputs.minutesMarkdownBlobUri,
    }


def fail_job(payload: dict[str, object]) -> dict[str, object]:
    tenant_id = _required_string(payload, "tenantId")
    job_id = _required_string(payload, "jobId")
    error_payload = payload.get("error")
    error = error_payload if isinstance(error_payload, dict) else {}
    repository = build_job_repository(AppSettings.from_env())
    record = repository.get(tenant_id, job_id)
    if record is None:
        return {"jobId": job_id, "status": JobStatus.FAILED.value}
    now = _utc_now()
    updated = record.model_copy(
        update={
            "status": JobStatus.FAILED,
            "progress": Progress(
                step=JobStatus.FAILED.value,
                percent=100,
                message="処理に失敗しました。",
                updatedAt=now,
            ),
            "error": ErrorObject(
                code=str(error.get("code", "WORKFLOW_FAILED")),
                message=str(error.get("message", "処理に失敗しました。")),
                details=_details(error.get("details")),
                correlationId=str(error.get("correlationId", job_id)),
            ),
            "updatedAt": now,
        }
    )
    repository.save(updated)
    return {"jobId": job_id, "status": JobStatus.FAILED.value}


def _details(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return {str(key): cast_value for key, cast_value in value.items()}
    return None


def _should_fallback_to_chunk_minutes(error: AppError) -> bool:
    if error.code == "MINUTES_SCHEMA_VALIDATION_FAILED":
        return True
    if error.code != "OPENAI_GENERATION_FAILED":
        return False
    reason = error.details.get("reason")
    status_code = error.details.get("statusCode")
    return reason in {
        "Response was truncated",
        "Response content was not valid JSON",
    } or status_code in {400, 413}


def _log_minutes_generation_mode(
    *,
    tenant_id: str,
    job_id: str,
    mode: str,
    minutes_model: str,
    fallback_reason: str | None = None,
) -> None:
    payload: dict[str, object] = {
        "event": "minutes_generation_mode",
        "tenantId": tenant_id,
        "jobId": job_id,
        "minutesGenerationMode": mode,
        "minutesModel": minutes_model,
    }
    if fallback_reason:
        payload["fallbackReason"] = fallback_reason
    try:
        LOGGER.info(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    except Exception:
        LOGGER.debug("minutes generation mode telemetry emission failed", exc_info=True)


def _required_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise TypeError(f"{key} must be a non-empty string")
    return value


def _required_dict(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise TypeError(f"{key} must be an object")
    return value


def _required_int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int):
        raise TypeError(f"{key} must be an integer")
    return value


def _utc_now() -> datetime:
    return datetime.now(UTC)
