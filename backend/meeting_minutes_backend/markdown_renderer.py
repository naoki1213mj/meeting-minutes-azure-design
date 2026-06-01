from __future__ import annotations

from typing import Any


def render_minutes_markdown(minutes: dict[str, Any]) -> str:
    lines = [
        f"# {minutes['title']}",
        "",
        "## 概要",
        str(minutes["summary"]),
        "",
        "## 論点",
    ]

    for topic in minutes.get("topics", []):
        lines.extend(
            [
                f"### {topic['title']}",
                str(topic["discussion"]),
                f"根拠: {', '.join(topic.get('evidenceTimestamps', [])) or '未設定'}",
                "",
            ]
        )

    lines.extend(["## 決定事項"])
    for decision in minutes.get("decisions", []):
        lines.append(
            f"- {decision['text']}（担当: {_display(decision.get('owner'))}、"
            f"根拠: {', '.join(decision.get('sourceTimestamps', []))}）"
        )
    if not minutes.get("decisions"):
        lines.append("- なし")

    lines.extend(["", "## ToDo", "| タスク | 担当 | 期限 | 根拠 |", "|---|---|---|---|"])
    for item in minutes.get("actionItems", []):
        lines.append(
            "| "
            f"{_escape_table(item['task'])} | "
            f"{_escape_table(_display(item.get('owner')))} | "
            f"{_escape_table(_display(item.get('dueDate')))} | "
            f"{_escape_table(', '.join(item.get('sourceTimestamps', [])))} |"
        )
    if not minutes.get("actionItems"):
        lines.append("| なし | 未設定 | 未設定 |  |")

    lines.extend(["", "## 未決事項"])
    for question in minutes.get("openQuestions", []):
        lines.append(f"- {question['text']}（担当: {_display(question.get('owner'))}）")
    if not minutes.get("openQuestions"):
        lines.append("- なし")

    lines.extend(["", "## リスク"])
    for risk in minutes.get("risks", []):
        lines.append(f"- [{risk['severity']}] {risk['text']}")
    if not minutes.get("risks"):
        lines.append("- なし")

    return "\n".join(lines).rstrip() + "\n"


def _display(value: object) -> str:
    return str(value) if value else "未設定"


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|")
