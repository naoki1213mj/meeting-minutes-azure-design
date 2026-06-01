from meeting_minutes_backend.health import build_health_payload


def test_build_health_payload() -> None:
    payload = build_health_payload()

    assert payload["status"] == "ok"
    assert payload["service"] == "meeting-minutes-backend"
    assert payload["runtime"] == "python3.13"
