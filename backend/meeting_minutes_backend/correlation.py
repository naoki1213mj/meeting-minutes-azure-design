from __future__ import annotations

import re
import uuid
from collections.abc import Mapping

CORRELATION_HEADER = "x-correlation-id"
_CORRELATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def resolve_correlation_id(headers: Mapping[str, str]) -> str:
    incoming = headers.get(CORRELATION_HEADER)
    if incoming and _CORRELATION_ID_PATTERN.fullmatch(incoming):
        return incoming
    return str(uuid.uuid4())
