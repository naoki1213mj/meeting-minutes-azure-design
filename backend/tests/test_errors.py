from __future__ import annotations

import pytest
from pydantic import ValidationError

from meeting_minutes_backend.errors import validation_error_to_app_error
from meeting_minutes_backend.models import CreateJobRequest


def test_validation_error_details_do_not_echo_input() -> None:
    with pytest.raises(ValidationError) as exc_info:
        CreateJobRequest.model_validate({"fileName": "secret.mp3"})

    error = validation_error_to_app_error(exc_info.value)
    details = error.details["validationErrors"]

    assert isinstance(details, list)
    assert details
    assert "input" not in details[0]
    assert "msg" not in details[0]
