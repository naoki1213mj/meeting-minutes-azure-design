from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import Field

from meeting_minutes_backend.minutes_generation import MINUTES_SCHEMA_PATH, _load_schema, _validate
from meeting_minutes_backend.models import StrictModel


class ExpectedDecision(StrictModel):
    text: str
    sourceTimestamps: list[str] = Field(default_factory=list)


class ExpectedActionItem(StrictModel):
    task: str
    owner: str | None
    dueDate: str | None
    sourceTimestamps: list[str] = Field(default_factory=list)


class ExpectedMinutesFacts(StrictModel):
    goldenSetId: str
    exhaustive: bool = True
    decisions: list[ExpectedDecision] = Field(default_factory=list)
    actionItems: list[ExpectedActionItem] = Field(default_factory=list)


class EvaluationResult(StrictModel):
    goldenSetId: str
    schemaValid: bool
    expectedDecisionCount: int
    matchedDecisionCount: int
    decisionRecall: float
    decisionPrecision: float | None
    expectedActionItemCount: int
    matchedActionItemCount: int
    actionItemRecall: float
    actionItemPrecision: float | None
    timestampCoverage: float
    unexpectedDecisionCount: int
    unexpectedActionItemCount: int


def load_expected_facts(path: Path) -> ExpectedMinutesFacts:
    return ExpectedMinutesFacts.model_validate(json.loads(path.read_text(encoding="utf-8")))


def evaluate_minutes(minutes: dict[str, Any], expected: ExpectedMinutesFacts) -> EvaluationResult:
    schema_valid = _schema_valid(minutes)
    matched_decisions = _match_items(minutes.get("decisions", []), expected.decisions, "text")
    matched_actions = _match_items(minutes.get("actionItems", []), expected.actionItems, "task")
    timestamp_hits = _timestamp_hits(matched_decisions) + _timestamp_hits(matched_actions)
    matched_total = len(matched_decisions) + len(matched_actions)

    decision_precision = _precision(
        len(matched_decisions), len(minutes.get("decisions", [])), expected.exhaustive
    )
    action_precision = _precision(
        len(matched_actions), len(minutes.get("actionItems", [])), expected.exhaustive
    )

    return EvaluationResult(
        goldenSetId=expected.goldenSetId,
        schemaValid=schema_valid,
        expectedDecisionCount=len(expected.decisions),
        matchedDecisionCount=len(matched_decisions),
        decisionRecall=_ratio(len(matched_decisions), len(expected.decisions)),
        decisionPrecision=decision_precision,
        expectedActionItemCount=len(expected.actionItems),
        matchedActionItemCount=len(matched_actions),
        actionItemRecall=_ratio(len(matched_actions), len(expected.actionItems)),
        actionItemPrecision=action_precision,
        timestampCoverage=_ratio(timestamp_hits, matched_total),
        unexpectedDecisionCount=_unexpected_count(
            len(minutes.get("decisions", [])), len(matched_decisions), expected.exhaustive
        ),
        unexpectedActionItemCount=_unexpected_count(
            len(minutes.get("actionItems", [])), len(matched_actions), expected.exhaustive
        ),
    )


def build_evaluation_record(
    fixture_path: Path,
    model_name: str,
    latency_ms: int,
    prompt_tokens: int,
    completion_tokens: int,
    result: EvaluationResult,
) -> dict[str, Any]:
    return {
        "evaluatedAt": datetime.now(UTC).isoformat(),
        "goldenSetId": result.goldenSetId,
        "fixtureSha256": _sha256(fixture_path),
        "modelName": model_name,
        "latencyMilliseconds": latency_ms,
        "promptTokens": prompt_tokens,
        "completionTokens": completion_tokens,
        "result": result.model_dump(mode="json"),
    }


def _match_items(
    actual_items: object,
    expected_items: list[ExpectedDecision] | list[ExpectedActionItem],
    field: str,
) -> list[tuple[dict[str, Any], ExpectedDecision | ExpectedActionItem]]:
    if not isinstance(actual_items, list):
        return []
    matches: list[tuple[dict[str, Any], ExpectedDecision | ExpectedActionItem]] = []
    unmatched_actual = [item for item in actual_items if isinstance(item, dict)]
    for expected in expected_items:
        expected_text = _normalize_text(getattr(expected, field))
        for actual in list(unmatched_actual):
            actual_value = actual.get(field)
            if isinstance(actual_value, str) and expected_text in _normalize_text(actual_value):
                matches.append((actual, expected))
                unmatched_actual.remove(actual)
                break
    return matches


def _timestamp_hits(
    matches: list[tuple[dict[str, Any], ExpectedDecision | ExpectedActionItem]]
) -> int:
    hits = 0
    for actual, expected in matches:
        actual_timestamps = set(actual.get("sourceTimestamps", []))
        if set(expected.sourceTimestamps).issubset(actual_timestamps):
            hits += 1
    return hits


def _schema_valid(minutes: dict[str, Any]) -> bool:
    try:
        _validate(_load_schema(MINUTES_SCHEMA_PATH), minutes)
    except Exception:
        return False
    return True


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).lower()
    return re.sub(r"[\s\W_]+", "", normalized)


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 1.0
    return numerator / denominator


def _precision(matched: int, actual_count: int, exhaustive: bool) -> float | None:
    if not exhaustive:
        return None
    return _ratio(matched, actual_count)


def _unexpected_count(actual_count: int, matched_count: int, exhaustive: bool) -> int:
    if not exhaustive:
        return 0
    return max(0, actual_count - matched_count)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
