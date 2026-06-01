from __future__ import annotations

import json
from pathlib import Path

from meeting_minutes_backend.evaluation import (
    build_evaluation_record,
    evaluate_minutes,
    load_expected_facts,
)

FIXTURES = Path(__file__).parent / "fixtures" / "golden_transcripts"


def _minutes() -> dict[str, object]:
    return {
        "jobId": "golden-basic-decision",
        "tenantId": "tenant-golden",
        "title": "週次会議",
        "meetingDate": None,
        "summary": "週次確認を決めた。",
        "speakers": [{"speakerLabel": "Speaker 1", "displayName": None}],
        "topics": [],
        "decisions": [
            {
                "text": "週次で進捗を確認する",
                "owner": None,
                "sourceTimestamps": ["00:00:10"],
            }
        ],
        "actionItems": [
            {
                "task": "進捗を確認する",
                "owner": "田中",
                "dueDate": None,
                "sourceTimestamps": ["00:00:20"],
            }
        ],
        "openQuestions": [],
        "risks": [],
        "generatedAt": "2026-06-01T00:00:00Z",
    }


def test_evaluate_minutes_matches_expected_facts() -> None:
    expected = load_expected_facts(FIXTURES / "basic_decision.expected.json")

    result = evaluate_minutes(_minutes(), expected)

    assert result.schemaValid
    assert result.decisionRecall == 1.0
    assert result.actionItemRecall == 1.0
    assert result.timestampCoverage == 1.0
    assert result.unexpectedDecisionCount == 0


def test_evaluate_minutes_counts_unexpected_items_when_exhaustive() -> None:
    expected = load_expected_facts(FIXTURES / "basic_decision.expected.json")
    minutes = _minutes()
    assert isinstance(minutes["decisions"], list)
    minutes["decisions"].append(
        {"text": "存在しない決定", "owner": None, "sourceTimestamps": ["00:00:30"]}
    )

    result = evaluate_minutes(minutes, expected)

    assert result.unexpectedDecisionCount == 1
    assert result.decisionPrecision == 0.5


def test_build_evaluation_record_includes_fixture_hash() -> None:
    fixture_path = FIXTURES / "basic_decision.expected.json"
    expected = load_expected_facts(fixture_path)
    result = evaluate_minutes(_minutes(), expected)

    record = build_evaluation_record(fixture_path, "gpt-5.4", 1000, 100, 200, result)

    assert record["goldenSetId"] == "basic-decision-v1"
    assert len(record["fixtureSha256"]) == 64
    json.dumps(record)
