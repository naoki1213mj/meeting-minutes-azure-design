from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "specs"


def _load_json(path: Path) -> object:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _extract_openapi_job_status_enum(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line == "    JobStatusEnum:")
    enum_start = next(i for i in range(start, len(lines)) if lines[i] == "      enum:")

    values: list[str] = []
    for line in lines[enum_start + 1 :]:
        if re.match(r"^    [A-Za-z].*:$", line):
            break
        match = re.match(r"^        - (.+)$", line)
        if match:
            values.append(match.group(1))

    return values


def main() -> None:
    schema_files = [
        "job-status.schema.json",
        "normalized-transcript.schema.json",
        "chunk-summary.structured-output.schema.json",
        "minutes.structured-output.schema.json",
        "minutes.schema.json",
    ]

    for file_name in schema_files:
        _load_json(SPECS / file_name)

    job_status_schema = _load_json(SPECS / "job-status.schema.json")
    if not isinstance(job_status_schema, dict):
        raise TypeError("job-status.schema.json must be a JSON object")

    schema_statuses = job_status_schema["properties"]["status"]["enum"]
    openapi_statuses = _extract_openapi_job_status_enum(SPECS / "openapi.yaml")

    if schema_statuses != openapi_statuses:
        raise ValueError(
            "OpenAPI JobStatusEnum does not match job-status.schema.json: "
            f"{openapi_statuses} != {schema_statuses}"
        )

    print("Specs are valid and JobStatusEnum is synchronized.")


if __name__ == "__main__":
    main()
