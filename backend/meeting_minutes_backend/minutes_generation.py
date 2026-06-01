from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from pydantic import Field

from meeting_minutes_backend.errors import AppError
from meeting_minutes_backend.models import StrictModel
from meeting_minutes_backend.schema_paths import find_specs_dir

SPECS = find_specs_dir()
CHUNK_SCHEMA_PATH = SPECS / "chunk-summary.structured-output.schema.json"
MINUTES_STRUCTURED_SCHEMA_PATH = SPECS / "minutes.structured-output.schema.json"
MINUTES_SCHEMA_PATH = SPECS / "minutes.schema.json"
TIMESTAMP_PATTERN = re.compile(r"^(?:(\d{1,2}):)?(\d{1,2}):(\d{1,2})(?:\.\d+)?$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class TranscriptChunk(StrictModel):
    chunkIndex: int
    timeRange: dict[str, str]
    speakerMapping: list[dict[str, str | None]]
    phrases: list[dict[str, str]]


class DeploymentCapabilities(StrictModel):
    deploymentName: str
    modelName: str
    supportsStructuredOutputs: bool = True
    generationParameters: dict[str, object] = Field(default_factory=dict)


@dataclass(frozen=True)
class ModelResult:
    content: dict[str, Any]
    model_name: str


class OpenAIJsonClient(Protocol):
    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        deployment: DeploymentCapabilities,
    ) -> ModelResult:
        pass


@dataclass
class FakeOpenAIJsonClient(OpenAIJsonClient):
    responses: list[dict[str, Any]]
    calls: list[dict[str, Any]] = field(default_factory=list)

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        deployment: DeploymentCapabilities,
    ) -> ModelResult:
        self.calls.append(
            {
                "systemPrompt": system_prompt,
                "userPrompt": user_prompt,
                "schemaTitle": schema.get("title"),
                "deploymentName": deployment.deploymentName,
            }
        )
        if not self.responses:
            raise AppError(
                code="OPENAI_RESPONSE_MISSING",
                message="テスト用LLM応答が不足しています。",
                http_status=500,
            )
        return ModelResult(content=self.responses.pop(0), model_name=deployment.modelName)


def build_transcript_chunks(
    normalized: dict[str, Any], target_duration_milliseconds: int = 600_000
) -> list[TranscriptChunk]:
    phrases = normalized.get("phrases", [])
    if not isinstance(phrases, list):
        raise TypeError("phrases must be a list")

    speaker_mapping = [
        {"speakerLabel": speaker["speakerLabel"], "displayName": speaker.get("displayName")}
        for speaker in normalized.get("speakers", [])
        if isinstance(speaker, dict)
    ]
    chunks: list[TranscriptChunk] = []
    current: list[dict[str, str]] = []
    chunk_start_ms = 0

    for phrase in phrases:
        if not isinstance(phrase, dict):
            continue
        phrase_start = int(phrase["offsetMilliseconds"])
        phrase_end = phrase_start + int(phrase["durationMilliseconds"])
        if current and phrase_end - chunk_start_ms > target_duration_milliseconds:
            chunks.append(
                _chunk(
                    len(chunks),
                    chunk_start_ms,
                    current[-1]["endTime"],
                    speaker_mapping,
                    current,
                )
            )
            current = []
            chunk_start_ms = phrase_start
        if not current:
            chunk_start_ms = phrase_start
        current.append(
            {
                "startTime": str(phrase["startTimeText"]),
                "endTime": str(phrase["endTimeText"]),
                "speakerLabel": str(phrase["speakerLabel"]),
                "text": str(phrase["text"]),
            }
        )

    if current:
        chunks.append(
            _chunk(len(chunks), chunk_start_ms, current[-1]["endTime"], speaker_mapping, current)
        )

    return chunks


def generate_minutes(
    normalized: dict[str, Any],
    job_id: str,
    tenant_id: str,
    meeting_title: str,
    client: OpenAIJsonClient,
    chunk_deployment: DeploymentCapabilities,
    final_deployment: DeploymentCapabilities,
) -> dict[str, Any]:
    chunk_summaries = [
        generate_chunk_summary(chunk, client, chunk_deployment)
        for chunk in build_transcript_chunks(normalized)
    ]
    return generate_final_minutes_from_summaries(
        normalized,
        chunk_summaries,
        job_id=job_id,
        tenant_id=tenant_id,
        meeting_title=meeting_title,
        client=client,
        final_deployment=final_deployment,
    )


def generate_chunk_summary(
    chunk: TranscriptChunk,
    client: OpenAIJsonClient,
    chunk_deployment: DeploymentCapabilities,
) -> dict[str, Any]:
    chunk_schema = _load_schema(CHUNK_SCHEMA_PATH)
    result = client.generate_json(
        CHUNK_SUMMARY_SYSTEM_PROMPT,
        build_chunk_summary_prompt(chunk),
        chunk_schema,
        chunk_deployment,
    )
    return result.content


def generate_final_minutes_from_summaries(
    normalized: dict[str, Any],
    chunk_summaries: list[dict[str, Any]],
    job_id: str,
    tenant_id: str,
    meeting_title: str,
    client: OpenAIJsonClient,
    final_deployment: DeploymentCapabilities,
) -> dict[str, Any]:
    final_schema = _load_schema(MINUTES_STRUCTURED_SCHEMA_PATH)
    save_schema = _load_schema(MINUTES_SCHEMA_PATH)
    final_result = client.generate_json(
        FINAL_MERGE_SYSTEM_PROMPT,
        build_final_merge_prompt(meeting_title, normalized.get("speakers", []), chunk_summaries),
        final_schema,
        final_deployment,
    )
    enriched = _enrich_minutes(final_result.content, job_id, tenant_id, final_result.model_name)
    normalized_minutes = normalize_minutes_for_save(enriched)

    try:
        _validate(save_schema, normalized_minutes)
        return normalized_minutes
    except ValidationError as first_error:
        repaired = client.generate_json(
            REPAIR_SYSTEM_PROMPT,
            build_repair_prompt(first_error, normalized_minutes),
            final_schema,
            final_deployment,
        )
        repaired_enriched = normalize_minutes_for_save(
            _enrich_minutes(repaired.content, job_id, tenant_id, repaired.model_name)
        )
        try:
            _validate(save_schema, repaired_enriched)
        except ValidationError as repair_error:
            raise AppError(
                code="MINUTES_SCHEMA_VALIDATION_FAILED",
                message="議事録JSONの検証に失敗しました。",
                http_status=502,
                details={"validationError": repair_error.message},
            ) from repair_error
        return repaired_enriched


def build_structured_output_request(
    deployment: DeploymentCapabilities,
    messages: list[dict[str, str]],
    schema: dict[str, Any],
) -> dict[str, Any]:
    request: dict[str, Any] = {
        "model": deployment.deploymentName,
        "messages": messages,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": str(schema.get("title", "StructuredOutput")),
                "strict": True,
                "schema": schema,
            },
        },
    }
    request.update(deployment.generationParameters)
    return request


def normalize_minutes_for_save(minutes: dict[str, Any]) -> dict[str, Any]:
    result = dict(minutes)
    result["meetingDate"] = _clean_date(result.get("meetingDate"))
    result["topics"] = [_normalize_topic(topic) for topic in result.get("topics", [])]
    result["decisions"] = _normalize_items(result.get("decisions", []), "decision")
    result["actionItems"] = _normalize_items(result.get("actionItems", []), "action")
    result["openQuestions"] = _normalize_items(result.get("openQuestions", []), "question")
    result["risks"] = _normalize_items(result.get("risks", []), "risk")
    return result


def build_chunk_summary_prompt(chunk: TranscriptChunk) -> str:
    return (
        "次の transcript chunk から、議事録の材料を抽出してください。\n\n"
        "抽出対象: 論点、決定事項、ToDo、未決事項、リスク、重要な引用timestamp。\n\n"
        f"transcript chunk:\n{chunk.model_dump_json(ensure_ascii=False)}"
    )


def build_final_merge_prompt(
    meeting_title: str, speaker_mapping: object, chunk_summaries: list[dict[str, Any]]
) -> str:
    return (
        "以下の chunk summary を統合して、最終議事録を作成してください。\n\n"
        f"会議タイトル: {meeting_title}\n"
        "会議日時: null\n"
        f"speaker mapping: {json.dumps(speaker_mapping, ensure_ascii=False)}\n"
        f"chunk summaries: {json.dumps(chunk_summaries, ensure_ascii=False)}"
    )


def build_repair_prompt(error: ValidationError, invalid_output: dict[str, Any]) -> str:
    return (
        "前回の出力は保存用JSON Schemaに適合しませんでした。\n"
        "同じ内容を保ったまま、JSONのみを修正してください。\n\n"
        f"validation error: {error.message}\n"
        f"invalid output: {json.dumps(invalid_output, ensure_ascii=False)[:8000]}"
    )


CHUNK_SUMMARY_SYSTEM_PROMPT = (
    "あなたは企業会議の議事録作成を支援するアシスタントです。"
    "入力にない事実を作らず、speakerLabelとtimestampを入力どおり使ってください。"
)
FINAL_MERGE_SYSTEM_PROMPT = (
    "あなたは企業会議の議事録編集者です。chunk summaryにない事実を追加せず、"
    "明示されていない担当者や期限はnullのままにしてください。"
)
REPAIR_SYSTEM_PROMPT = "保存用JSON Schemaに適合するJSONだけを返してください。"


def _chunk(
    chunk_index: int,
    start_ms: int,
    end_time: str,
    speaker_mapping: list[dict[str, str | None]],
    phrases: list[dict[str, str]],
) -> TranscriptChunk:
    return TranscriptChunk(
        chunkIndex=chunk_index,
        timeRange={"start": _format_timestamp(start_ms), "end": end_time},
        speakerMapping=speaker_mapping,
        phrases=phrases,
    )


def _enrich_minutes(
    minutes: dict[str, Any], job_id: str, tenant_id: str, model_name: str
) -> dict[str, Any]:
    enriched = dict(minutes)
    enriched["jobId"] = job_id
    enriched["tenantId"] = tenant_id
    enriched["generatedAt"] = datetime.now(UTC).isoformat()
    enriched["model"] = {
        "deploymentName": model_name,
        "modelName": model_name,
    }
    return enriched


def _normalize_topic(topic: object) -> dict[str, Any]:
    if not isinstance(topic, dict):
        return {}
    normalized = dict(topic)
    normalized["evidenceTimestamps"] = _normalize_timestamps(topic.get("evidenceTimestamps", []))
    normalized["decisions"] = _normalize_items(topic.get("decisions", []), "decision")
    normalized["actionItems"] = _normalize_items(topic.get("actionItems", []), "action")
    normalized["openQuestions"] = _normalize_items(topic.get("openQuestions", []), "question")
    normalized["risks"] = _normalize_items(topic.get("risks", []), "risk")
    return normalized


def _normalize_items(items: object, item_type: str) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    normalized = []
    for item in items:
        if not isinstance(item, dict):
            continue
        source_timestamps = _normalize_timestamps(item.get("sourceTimestamps", []))
        if not source_timestamps:
            continue
        item_copy = dict(item)
        item_copy["sourceTimestamps"] = source_timestamps
        if item_type == "action":
            item_copy["dueDate"] = _clean_date(item.get("dueDate"))
        normalized.append(item_copy)
    return normalized


def _normalize_timestamps(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized = []
    for value in values:
        if not isinstance(value, str):
            continue
        timestamp = _normalize_timestamp(value)
        if timestamp:
            normalized.append(timestamp)
    return normalized


def _normalize_timestamp(value: str) -> str | None:
    match = TIMESTAMP_PATTERN.match(value.strip())
    if not match:
        return None
    hours_text, minutes_text, seconds_text = match.groups()
    hours = int(hours_text or "0")
    minutes = int(minutes_text)
    seconds = int(seconds_text)
    if minutes > 59 or seconds > 59:
        return None
    return f"{hours:02}:{minutes:02}:{seconds:02}"


def _clean_date(value: object) -> str | None:
    if isinstance(value, str) and DATE_PATTERN.match(value):
        return value
    return None


def _format_timestamp(milliseconds: int) -> str:
    total_seconds = max(0, milliseconds // 1000)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02}:{minutes:02}:{seconds:02}"


def _load_schema(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate(schema: dict[str, Any], data: dict[str, Any]) -> None:
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(data)
