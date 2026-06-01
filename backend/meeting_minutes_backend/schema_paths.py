from __future__ import annotations

import os
from pathlib import Path


def find_specs_dir() -> Path:
    configured = os.environ.get("MEETING_MINUTES_SPECS_DIR")
    if configured:
        return Path(configured).resolve()

    for parent in Path(__file__).resolve().parents:
        candidate = parent / "specs"
        if candidate.is_dir():
            return candidate

    raise FileNotFoundError("specs directory was not found")
