from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel


PROMPT_DIR = Path(__file__).resolve().parents[2] / "prompts"


def load_prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def compact_json(value: Any, *, limit: int = 30000) -> str:
    def convert(item):
        if isinstance(item, BaseModel):
            return item.model_dump()
        if isinstance(item, list):
            return [convert(child) for child in item]
        if isinstance(item, dict):
            return {key: convert(child) for key, child in item.items()}
        return item

    text = json.dumps(convert(value), ensure_ascii=False, indent=2)
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...<truncated>"


def next_id(prefix: str, count: int) -> str:
    return f"{prefix}-{count + 1:03d}"

