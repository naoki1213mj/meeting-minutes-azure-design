from __future__ import annotations

import json
from urllib.parse import unquote, urlparse

import azure.functions as func

from meeting_minutes_backend.auth import resolve_auth_context
from meeting_minutes_backend.correlation import CORRELATION_HEADER, resolve_correlation_id
from meeting_minutes_backend.errors import AppError
from meeting_minutes_backend.health import build_health_payload
from meeting_minutes_backend.http import error_boundary, json_response, parse_json_model
from meeting_minutes_backend.models import CreateJobRequest, UploadCompleteRequest
from meeting_minutes_backend.services import get_job_service
from meeting_minutes_backend.settings import AppSettings, build_artifact_store_for_uri


def health(req: func.HttpRequest) -> func.HttpResponse:
    _ = req
    return func.HttpResponse(
        json.dumps(build_health_payload(), ensure_ascii=False),
        status_code=200,
        mimetype="application/json",
    )


def create_job(req: func.HttpRequest) -> func.HttpResponse:
    return _create_job(req)


@error_boundary
def _create_job(req: func.HttpRequest) -> func.HttpResponse:
    correlation_id = resolve_correlation_id(req.headers)
    auth = resolve_auth_context(req.headers)
    request = parse_json_model(req, CreateJobRequest)
    response = get_job_service().create_job(auth, request)
    return json_response(response.model_dump(mode="json"), 201, correlation_id)


def get_job(req: func.HttpRequest, jobId: str) -> func.HttpResponse:
    return _get_job(req, jobId)


@error_boundary
def _get_job(req: func.HttpRequest, jobId: str) -> func.HttpResponse:
    correlation_id = resolve_correlation_id(req.headers)
    auth = resolve_auth_context(req.headers)
    response = get_job_service().get_job(auth, jobId)
    return json_response(response.model_dump(mode="json"), 200, correlation_id)


def get_transcript(req: func.HttpRequest, jobId: str) -> func.HttpResponse:
    return _get_transcript(req, jobId)


@error_boundary
def _get_transcript(req: func.HttpRequest, jobId: str) -> func.HttpResponse:
    correlation_id = resolve_correlation_id(req.headers)
    auth = resolve_auth_context(req.headers)
    status = get_job_service().get_job(auth, jobId)
    uri = status.outputs.normalizedTranscriptBlobUri
    if not uri:
        raise AppError(
            code="TRANSCRIPT_NOT_READY",
            message="文字起こしはまだ準備できていません。",
            http_status=404,
        )
    settings = AppSettings.from_env()
    transcript = build_artifact_store_for_uri(settings, uri).read_json(
        settings.transcript_container_name,
        _blob_name_from_url(uri, settings.transcript_container_name),
    )
    return json_response(transcript, 200, correlation_id)


def get_visual_context(req: func.HttpRequest, jobId: str) -> func.HttpResponse:
    return _get_visual_context(req, jobId)


@error_boundary
def _get_visual_context(req: func.HttpRequest, jobId: str) -> func.HttpResponse:
    correlation_id = resolve_correlation_id(req.headers)
    auth = resolve_auth_context(req.headers)
    status = get_job_service().get_job(auth, jobId)
    uri = status.outputs.visualContextBlobUri
    if not uri:
        raise AppError(
            code="VISUAL_CONTEXT_NOT_READY",
            message="映像補足はまだ準備できていません。",
            http_status=404,
        )
    settings = AppSettings.from_env()
    visual_context = build_artifact_store_for_uri(settings, uri).read_json(
        settings.transcript_container_name,
        _blob_name_from_url(uri, settings.transcript_container_name),
    )
    return json_response(visual_context, 200, correlation_id)


def get_minutes(req: func.HttpRequest, jobId: str) -> func.HttpResponse:
    return _get_minutes(req, jobId)


@error_boundary
def _get_minutes(req: func.HttpRequest, jobId: str) -> func.HttpResponse:
    correlation_id = resolve_correlation_id(req.headers)
    auth = resolve_auth_context(req.headers)
    status = get_job_service().get_job(auth, jobId)
    settings = AppSettings.from_env()
    requested_format = (req.params.get("format") or "json").lower()
    if requested_format == "markdown":
        uri = status.outputs.minutesMarkdownBlobUri
        if not uri:
            raise AppError(
                code="MINUTES_NOT_READY",
                message="議事録はまだ準備できていません。",
                http_status=404,
            )
        blob_name = _blob_name_from_url(uri, settings.minutes_container_name)
        markdown = build_artifact_store_for_uri(settings, uri).read_text(
            settings.minutes_container_name, blob_name
        )
        return func.HttpResponse(
            markdown,
            status_code=200,
            mimetype="text/markdown",
            headers={CORRELATION_HEADER: correlation_id},
        )

    uri = status.outputs.minutesJsonBlobUri
    if not uri:
        raise AppError(
            code="MINUTES_NOT_READY",
            message="議事録はまだ準備できていません。",
            http_status=404,
        )
    minutes = build_artifact_store_for_uri(settings, uri).read_json(
        settings.minutes_container_name,
        _blob_name_from_url(uri, settings.minutes_container_name),
    )
    return json_response(minutes, 200, correlation_id)


def complete_upload(req: func.HttpRequest, jobId: str) -> func.HttpResponse:
    return _complete_upload(req, jobId)


@error_boundary
def _complete_upload(req: func.HttpRequest, jobId: str) -> func.HttpResponse:
    correlation_id = resolve_correlation_id(req.headers)
    auth = resolve_auth_context(req.headers)
    request = parse_json_model(req, UploadCompleteRequest)
    response = get_job_service().complete_upload(auth, jobId, request)
    return json_response(response.model_dump(mode="json"), 202, correlation_id)


@error_boundary
def complete_upload_with_instance_id(
    req: func.HttpRequest, jobId: str, orchestration_instance_id: str
) -> func.HttpResponse:
    correlation_id = resolve_correlation_id(req.headers)
    auth = resolve_auth_context(req.headers)
    request = parse_json_model(req, UploadCompleteRequest)
    response = get_job_service().complete_upload_with_instance_id(
        auth,
        jobId,
        request,
        orchestration_instance_id,
    )
    return json_response(response.model_dump(mode="json"), 202, correlation_id)


def _blob_name_from_url(blob_url: str, container_name: str) -> str:
    path = unquote(urlparse(blob_url).path).lstrip("/")
    prefix = f"{container_name}/"
    if not path.startswith(prefix):
        raise AppError(
            code="ARTIFACT_URI_INVALID",
            message="成果物URIを解決できませんでした。",
            http_status=500,
        )
    return path[len(prefix) :]
