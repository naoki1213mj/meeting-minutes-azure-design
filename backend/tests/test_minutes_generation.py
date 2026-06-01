from __future__ import annotations

from meeting_minutes_backend.markdown_renderer import render_minutes_markdown
from meeting_minutes_backend.minutes_generation import (
    DeploymentCapabilities,
    FakeOpenAIJsonClient,
    build_structured_output_request,
    build_transcript_chunks,
    generate_chunk_summary,
    generate_final_minutes_from_summaries,
    generate_minutes,
    normalize_minutes_for_save,
)


def _normalized_transcript() -> dict[str, object]:
    return {
        "jobId": "job-a",
        "tenantId": "tenant-a",
        "locale": "ja-JP",
        "durationMilliseconds": 700_000,
        "speakers": [
            {"speakerLabel": "Speaker 1", "displayName": None},
            {"speakerLabel": "Speaker 2", "displayName": None},
        ],
        "phrases": [
            {
                "phraseId": "p1",
                "speakerLabel": "Speaker 1",
                "displayName": None,
                "offsetMilliseconds": 0,
                "durationMilliseconds": 1000,
                "startTimeText": "00:00:00",
                "endTimeText": "00:00:01",
                "text": "本日の方針を決めます。",
                "confidence": 0.9,
            },
            {
                "phraseId": "p2",
                "speakerLabel": "Speaker 2",
                "displayName": None,
                "offsetMilliseconds": 610_000,
                "durationMilliseconds": 1000,
                "startTimeText": "00:10:10",
                "endTimeText": "00:10:11",
                "text": "田中さんが確認します。期限は未定です。",
                "confidence": 0.9,
            },
        ],
    }


def _chunk_summary() -> dict[str, object]:
    return {
        "chunkIndex": 0,
        "timeRange": {"start": "00:00:00", "end": "00:10:00"},
        "summary": "方針確認。",
        "topics": [],
        "decisions": [],
        "actionItems": [],
        "openQuestions": [],
        "risks": [],
    }


def _valid_final_minutes() -> dict[str, object]:
    return {
        "title": "会議",
        "meetingDate": None,
        "summary": "方針を確認した。",
        "speakers": [{"speakerLabel": "Speaker 1", "displayName": None}],
        "topics": [
            {
                "title": "方針",
                "discussion": "方針を確認した。",
                "decisions": [
                    {
                        "text": "方針を確認する",
                        "owner": None,
                        "sourceTimestamps": ["0:00:00"],
                    }
                ],
                "actionItems": [
                    {
                        "task": "確認する",
                        "owner": "田中",
                        "dueDate": "未定",
                        "sourceTimestamps": ["00:10:10.1"],
                    }
                ],
                "openQuestions": [],
                "risks": [],
                "evidenceTimestamps": ["0:00:00"],
            }
        ],
        "decisions": [
            {"text": "方針を確認する", "owner": None, "sourceTimestamps": ["0:00:00"]}
        ],
        "actionItems": [
            {
                "task": "確認する",
                "owner": "田中",
                "dueDate": "未定",
                "sourceTimestamps": ["00:10:10.1"],
            }
        ],
        "openQuestions": [],
        "risks": [],
    }


def test_build_transcript_chunks_preserves_phrase_boundaries() -> None:
    chunks = build_transcript_chunks(_normalized_transcript(), target_duration_milliseconds=600_000)

    assert len(chunks) == 2
    assert chunks[0].phrases[0]["text"] == "本日の方針を決めます。"
    assert chunks[1].phrases[0]["text"] == "田中さんが確認します。期限は未定です。"
    assert chunks[0].speakerMapping[0]["speakerLabel"] == "Speaker 1"


def test_generate_minutes_uses_structured_schemas_and_validates_save_schema() -> None:
    client = FakeOpenAIJsonClient([_chunk_summary(), _chunk_summary(), _valid_final_minutes()])
    chunk_deployment = DeploymentCapabilities(
        deploymentName="gpt-5.4-mini",
        modelName="gpt-5.4-mini",
    )
    final_deployment = DeploymentCapabilities(deploymentName="gpt-5.4", modelName="gpt-5.4")

    minutes = generate_minutes(
        _normalized_transcript(),
        job_id="job-a",
        tenant_id="tenant-a",
        meeting_title="会議",
        client=client,
        chunk_deployment=chunk_deployment,
        final_deployment=final_deployment,
    )

    assert minutes["jobId"] == "job-a"
    assert minutes["tenantId"] == "tenant-a"
    assert minutes["decisions"][0]["sourceTimestamps"] == ["00:00:00"]
    assert minutes["actionItems"][0]["dueDate"] is None
    assert [call["schemaTitle"] for call in client.calls] == [
        "ChunkSummaryStructuredOutput",
        "ChunkSummaryStructuredOutput",
        "MeetingMinutesStructuredOutput",
    ]


def test_split_generation_uses_chunk_then_final_schemas() -> None:
    chunks = build_transcript_chunks(_normalized_transcript(), target_duration_milliseconds=600_000)
    client = FakeOpenAIJsonClient([_chunk_summary(), _chunk_summary(), _valid_final_minutes()])
    chunk_deployment = DeploymentCapabilities(
        deploymentName="gpt-5.4-mini",
        modelName="gpt-5.4-mini",
    )
    final_deployment = DeploymentCapabilities(deploymentName="gpt-5.4", modelName="gpt-5.4")

    chunk_summaries = [
        generate_chunk_summary(chunk, client, chunk_deployment) for chunk in chunks
    ]
    minutes = generate_final_minutes_from_summaries(
        _normalized_transcript(),
        chunk_summaries,
        job_id="job-a",
        tenant_id="tenant-a",
        meeting_title="会議",
        client=client,
        final_deployment=final_deployment,
    )

    assert minutes["jobId"] == "job-a"
    assert [call["schemaTitle"] for call in client.calls] == [
        "ChunkSummaryStructuredOutput",
        "ChunkSummaryStructuredOutput",
        "MeetingMinutesStructuredOutput",
    ]


def test_generate_minutes_repairs_once_for_structural_validation_failure() -> None:
    invalid_final = {**_valid_final_minutes(), "title": 123}
    client = FakeOpenAIJsonClient(
        [_chunk_summary(), _chunk_summary(), invalid_final, _valid_final_minutes()]
    )

    minutes = generate_minutes(
        _normalized_transcript(),
        job_id="job-a",
        tenant_id="tenant-a",
        meeting_title="会議",
        client=client,
        chunk_deployment=DeploymentCapabilities(
            deploymentName="gpt-5.4-mini",
            modelName="gpt-5.4-mini",
        ),
        final_deployment=DeploymentCapabilities(deploymentName="gpt-5.4", modelName="gpt-5.4"),
    )

    assert minutes["title"] == "会議"
    assert len(client.calls) == 4


def test_repair_uses_minutes_structured_output_schema_not_save_schema() -> None:
    invalid_final = {**_valid_final_minutes(), "title": 123}
    client = FakeOpenAIJsonClient([invalid_final, _valid_final_minutes()])

    minutes = generate_final_minutes_from_summaries(
        _normalized_transcript(),
        [_chunk_summary()],
        job_id="job-a",
        tenant_id="tenant-a",
        meeting_title="会議",
        client=client,
        final_deployment=DeploymentCapabilities(deploymentName="gpt-5.4", modelName="gpt-5.4"),
    )

    assert minutes["title"] == "会議"
    assert [call["schemaTitle"] for call in client.calls] == [
        "MeetingMinutesStructuredOutput",
        "MeetingMinutesStructuredOutput",
    ]
    assert all(call["schemaTitle"] != "MeetingMinutes" for call in client.calls)


def test_normalize_minutes_drops_items_without_source_timestamps() -> None:
    minutes = _valid_final_minutes()
    minutes["decisions"] = [{"text": "根拠なし", "owner": "Speaker 1", "sourceTimestamps": []}]

    normalized = normalize_minutes_for_save(minutes)

    assert normalized["decisions"] == []


def test_build_structured_output_request_uses_capability_parameters() -> None:
    request = build_structured_output_request(
        DeploymentCapabilities(
            deploymentName="gpt-5.4-mini",
            modelName="gpt-5.4-mini",
            generationParameters={"max_completion_tokens": 4096},
        ),
        messages=[{"role": "user", "content": "hello"}],
        schema={"title": "MySchema", "type": "object"},
    )

    assert request["model"] == "gpt-5.4-mini"
    assert request["max_completion_tokens"] == 4096
    assert "temperature" not in request
    assert request["response_format"]["json_schema"]["name"] == "MySchema"


def test_render_minutes_markdown_is_stable_and_does_not_infer_unknowns() -> None:
    minutes = normalize_minutes_for_save(
        {
            **_valid_final_minutes(),
            "jobId": "job-a",
            "tenantId": "tenant-a",
            "generatedAt": "2026-06-01T00:00:00Z",
        }
    )

    markdown = render_minutes_markdown(minutes)

    assert markdown.startswith("# 会議")
    assert "未設定" in markdown
    assert "## ToDo" in markdown
