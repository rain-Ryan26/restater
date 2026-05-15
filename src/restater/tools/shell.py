from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

from restater.models import ShellResult


BLOCKED_PATTERNS = [
    r"\brm\b",
    r"\bdel\b",
    r"\brmdir\b",
    r"\bRemove-Item\b",
    r"\bgit\s+reset\b",
    r"\bgit\s+clean\b",
    r"\bformat\b",
    r">\s*",
    r">>\s*",
]


def ensure_safe_command(command: str) -> None:
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, command, flags=re.IGNORECASE):
            raise ValueError(f"Blocked potentially destructive command: {command}")


def run_powershell(command: str, cwd: Path, *, timeout_seconds: int = 120) -> ShellResult:
    ensure_safe_command(command)
    start = time.perf_counter()
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout_seconds,
    )
    duration_ms = int((time.perf_counter() - start) * 1000)
    return ShellResult(
        command=command,
        cwd=str(cwd),
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        duration_ms=duration_ms,
    )

