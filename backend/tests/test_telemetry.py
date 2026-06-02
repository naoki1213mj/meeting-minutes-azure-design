from __future__ import annotations

import logging
from typing import cast

import pytest

from meeting_minutes_backend import telemetry
from meeting_minutes_backend.telemetry import (
    ACTIVITY_DURATION_LOGGER_NAME,
    build_job_metric,
    measure_activity,
    safe_log_payload,
)


def test_safe_log_payload_redacts_sas_url_anywhere() -> None:
    payload: dict[str, object] = {
        "links": {
            "contentUrl": (
                "https://storage.blob.core.windows.net/audio/file.wav?"
                "sv=2024&se=tomorrow&sig=REDACTED_TEST_VALUE"
            )
        }
    }

    redacted = safe_log_payload(payload)
    rendered = str(redacted)

    assert "REDACTED_TEST_VALUE" not in rendered
    assert "https://storage.blob.core.windows.net/audio/file.wav" not in rendered
    assert "[REDACTED_SAS_URL]" in rendered


def test_safe_log_payload_redacts_embedded_sas_url() -> None:
    payload: dict[str, object] = {
        "message": (
            "Speech fetch failed for "
            "https://storage.blob.core.windows.net/audio/file.wav?SV=2024&SIG=REDACTED_TEST_VALUE"
        )
    }

    rendered = str(safe_log_payload(payload))

    assert "REDACTED_TEST_VALUE" not in rendered
    assert "storage.blob.core.windows.net" not in rendered
    assert "[REDACTED_SAS_URL]" in rendered


def test_safe_log_payload_redacts_transcript_and_minutes_fields() -> None:
    payload: dict[str, object] = {
        "transcript": "顧客の発言全文",
        "minutes": {"summary": "議事録全文"},
        "safe": "job-a",
    }

    redacted = safe_log_payload(payload)

    assert redacted == {
        "transcript": "[REDACTED]",
        "minutes": "[REDACTED]",
        "safe": "job-a",
    }


def test_safe_log_payload_redacts_sensitive_field_name_variants() -> None:
    payload = {
        "sasUrl": "https://storage.blob.core.windows.net/audio/file.wav?sig=REDACTED_TEST_VALUE",
        "audio_url": "https://storage.blob.core.windows.net/audio/file.wav?sig=REDACTED_TEST_VALUE",
        "accessToken": "REDACTED_TEST_VALUE",
        "apiKey": "REDACTED_TEST_VALUE",
        "storageKey": "REDACTED_TEST_VALUE",
        "audioDurationSeconds": 120,
    }

    redacted = cast(dict[str, object], safe_log_payload(payload))

    assert redacted["sasUrl"] == "[REDACTED]"
    assert redacted["audio_url"] == "[REDACTED]"
    assert redacted["accessToken"] == "[REDACTED]"
    assert redacted["apiKey"] == "[REDACTED]"
    assert redacted["storageKey"] == "[REDACTED]"
    assert redacted["audioDurationSeconds"] == 120


def test_safe_log_payload_redacts_tokens_connection_strings_and_truncates() -> None:
    payload = {
        "message": (
            "Bearer eyJREDACTED.TEST.VALUE "
            "DefaultEndpointsProtocol=https;"
            "AccountKey=REDACTED_TEST_VALUE;"
            "EndpointSuffix=core.windows.net "
            + "あ" * 600
        )
    }

    rendered = str(safe_log_payload(payload))

    assert "eyJREDACTED.TEST.VALUE" not in rendered
    assert "REDACTED_TEST_VALUE" not in rendered
    assert "truncated" in rendered


def test_build_job_metric_drops_sensitive_dimensions() -> None:
    metric = build_job_metric(
        "meeting.total.seconds",
        12.3,
        job_id="job-a",
        tenant_id="tenant-a",
        activity_name="TranscribeAudioActivity",
        extra_dimensions={"token": "REDACTED_TEST_VALUE", "outcome": "success"},
    )

    assert metric.dimensions["tokenRedacted"] == "true"
    assert metric.dimensions["outcome"] == "success"


def test_build_job_metric_redacts_normalized_sensitive_dimension_names() -> None:
    metric = build_job_metric(
        "meeting.total.seconds",
        12.3,
        job_id="job-a",
        tenant_id="tenant-a",
        activity_name="TranscribeAudioActivity",
        extra_dimensions={"accessToken": "REDACTED_TEST_VALUE", "tokenUsage": 100},
    )

    assert metric.dimensions["accessTokenRedacted"] == "true"
    assert metric.dimensions["tokenUsage"] == "100"


def test_measure_activity_logs_duration_with_nested_job_context(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=ACTIVITY_DURATION_LOGGER_NAME)
    payload: dict[str, object] = {
        "job": {"tenantId": "tenant-a", "jobId": "job-a"},
        "chunkIndex": 2,
        "audioUrl": "https://storage.blob.core.windows.net/audio/input.m4a?sig=SECRET",
    }

    result = measure_activity(
        "GenerateChunkSummaryActivity",
        payload,
        lambda _: {"ok": True},
    )

    assert result == {"ok": True}
    record = _single_activity_duration_record(caplog)
    dimensions = cast(dict[str, str], record.__dict__["custom_dimensions"])
    assert dimensions["tenantId"] == "tenant-a"
    assert dimensions["jobId"] == "job-a"
    assert dimensions["activityName"] == "GenerateChunkSummaryActivity"
    assert dimensions["chunkIndex"] == "2"
    assert dimensions["outcome"] == "success"
    assert record.__dict__["custom_metric_name"] == "meeting.activity.duration.seconds"
    assert cast(float, record.__dict__["custom_metric_value"]) >= 0
    assert "SECRET" not in caplog.text
    assert "audioUrl" not in caplog.text


def test_measure_activity_logs_failure_and_reraises_without_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=ACTIVITY_DURATION_LOGGER_NAME)
    payload: dict[str, object] = {
        "tenantId": "tenant-a",
        "jobId": "job-a",
        "transcript": "文字起こし全文",
    }

    def fail(_: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("文字起こし全文を含む内部エラー")

    with pytest.raises(RuntimeError):
        measure_activity("TranscribeAudioActivity", payload, fail)

    record = _single_activity_duration_record(caplog)
    dimensions = cast(dict[str, str], record.__dict__["custom_dimensions"])
    assert dimensions["tenantId"] == "tenant-a"
    assert dimensions["jobId"] == "job-a"
    assert dimensions["activityName"] == "TranscribeAudioActivity"
    assert dimensions["outcome"] == "failure"
    assert dimensions["errorType"] == "RuntimeError"
    assert "文字起こし全文" not in caplog.text
    assert "内部エラー" not in caplog.text


def test_measure_activity_telemetry_failure_does_not_affect_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken_info(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("logger unavailable")

    monkeypatch.setattr(telemetry.LOGGER, "info", broken_info)

    result = measure_activity(
        "LoadJobActivity",
        cast(dict[str, object], {"tenantId": "tenant-a", "jobId": "job-a"}),
        lambda _: {"jobId": "job-a"},
    )

    assert result == {"jobId": "job-a"}


def _single_activity_duration_record(caplog: pytest.LogCaptureFixture) -> logging.LogRecord:
    records = [
        record
        for record in caplog.records
        if getattr(record, "custom_metric_name", None) == "meeting.activity.duration.seconds"
    ]
    assert len(records) == 1
    return records[0]
