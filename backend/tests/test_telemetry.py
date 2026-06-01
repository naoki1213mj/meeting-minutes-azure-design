from __future__ import annotations

from typing import cast

from meeting_minutes_backend.telemetry import build_job_metric, safe_log_payload


def test_safe_log_payload_redacts_sas_url_anywhere() -> None:
    payload = {
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
    payload = {
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
    payload = {
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
