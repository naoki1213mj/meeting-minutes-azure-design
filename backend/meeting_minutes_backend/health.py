from typing import Any


def build_health_payload() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "meeting-minutes-backend",
        "runtime": "python3.13",
    }
