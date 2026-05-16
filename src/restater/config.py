from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: Path | None = None) -> None:
    env_path = path or Path(".env")
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return float(value)


@dataclass(frozen=True)
class RestaterConfig:
    api_key: str
    api_base: str
    model: str
    default_project_path: str
    temperature: float
    max_tokens: int
    context_file_limit: int
    text_read_limit: int
    pdf_page_limit: int
    model_timeout_seconds: int
    inspection_max_iterations: int

    @classmethod
    def from_env(cls) -> "RestaterConfig":
        api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("RESTATER_API_KEY") or ""
        return cls(
            api_key=api_key,
            api_base=os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com").rstrip("/"),
            model=os.getenv("RESTATER_MODEL", "deepseek-v4-pro"),
            default_project_path=os.getenv("RESTATER_DEFAULT_PROJECT_PATH", ""),
            temperature=_env_float("RESTATER_TEMPERATURE", 0.2),
            max_tokens=_env_int("RESTATER_MAX_TOKENS", 4096),
            context_file_limit=_env_int("RESTATER_CONTEXT_FILE_LIMIT", 300),
            text_read_limit=_env_int("RESTATER_TEXT_READ_LIMIT", 20000),
            pdf_page_limit=_env_int("RESTATER_PDF_PAGE_LIMIT", 6),
            model_timeout_seconds=_env_int("RESTATER_MODEL_TIMEOUT_SECONDS", 120),
            inspection_max_iterations=_env_int("RESTATER_INSPECTION_MAX_ITERATIONS", 10),
        )

    def validate_for_model_call(self) -> None:
        if not self.api_key:
            raise RuntimeError(
                "Missing DEEPSEEK_API_KEY or RESTATER_API_KEY. "
                "Create .env from .env.example before running model-backed checks."
            )
