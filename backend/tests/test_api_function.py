from __future__ import annotations

import json

import azure.functions as func

from function_app import create_job


def test_create_job_function_returns_correlation_header() -> None:
    req = func.HttpRequest(
        method="POST",
        url="/api/jobs",
        headers={
            "x-correlation-id": "test-correlation",
            "x-dev-tenant-id": "tenant-a",
            "x-dev-user-id": "user-a",
        },
        params={},
        body=json.dumps(
            {
                "fileName": "meeting.mp3",
                "contentType": "audio/mpeg",
                "fileSizeBytes": 1024,
            }
        ).encode("utf-8"),
    )

    res = create_job(req)
    body = json.loads(res.get_body())

    assert res.status_code == 201
    assert res.headers["x-correlation-id"] == "test-correlation"
    assert body["status"] == "CREATED"
    assert body["blobName"].startswith("raw-audio/tenant-a/")
