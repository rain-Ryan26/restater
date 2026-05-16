from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .config import RestaterConfig

DEFAULT_LANGUAGE_INSTRUCTION = """语言策略：
- 所有面向用户可见的自然语言输出默认使用简体中文。
- 这适用于 JSON 字符串字段，例如 summary、reason、action、expected_evidence、title、description 和面向错误展示的说明。
- 技术标识、文件路径、命令、status 枚举值、JSON key 和代码符号保持原样。
- 不要因为提示词、来源文档或 schema 示例含有英文就切换成英文。"""


@dataclass
class ChatMessage:
    role: str
    content: str


class DeepSeekChatClient:
    def __init__(self, config: RestaterConfig) -> None:
        self.config = config

    def complete(self, messages: list[ChatMessage], *, temperature: float | None = None) -> str:
        self.config.validate_for_model_call()
        payload = {
            "model": self.config.model,
            "messages": [message.__dict__ for message in messages],
            "temperature": self.config.temperature if temperature is None else temperature,
            "max_tokens": self.config.max_tokens,
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.config.api_base}/chat/completions",
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.model_timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Model API HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Model API request failed: {exc}") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise RuntimeError(
                f"Model API request timed out after {self.config.model_timeout_seconds} seconds."
            ) from exc

        try:
            body = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Model API returned invalid JSON: {raw[:500]}") from exc
        choices = body.get("choices") or []
        if not choices:
            raise RuntimeError(f"Model API returned no choices: {raw[:500]}")
        content = choices[0].get("message", {}).get("content")
        if not isinstance(content, str):
            raise RuntimeError(f"Model API returned invalid content: {raw[:500]}")
        return content.strip()

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        localized_system_prompt = f"{DEFAULT_LANGUAGE_INSTRUCTION}\n\n{system_prompt}"
        content = self.complete(
            [
                ChatMessage(role="system", content=localized_system_prompt),
                ChatMessage(role="user", content=user_prompt),
            ]
        )
        return parse_json_object(content)


def parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if not match:
            raise
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object from model output.")
    return value
