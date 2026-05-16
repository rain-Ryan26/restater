from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from restater.config import RestaterConfig
from restater.graph.builder import build_graph
from restater.graph.state import ProjectCheckState
from restater.models import RunError
from restater.tools.filesystem import write_text_no_bom


ProgressCallback = Callable[[str, str], None]


def run_check(
    project_path: Path,
    user_note: str,
    output_dir: Path | None,
    config: RestaterConfig,
    progress: ProgressCallback | None = None,
) -> ProjectCheckState:
    project_path = project_path.resolve()
    run_id = time.strftime("%Y%m%d-%H%M%S")
    output_dir = (output_dir or Path.cwd() / ".restater" / "runs" / run_id).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    initial: ProjectCheckState = {
        "run_id": run_id,
        "project_path": str(project_path),
        "user_note": user_note,
        "output_dir": str(output_dir),
        "context_index": [],
        "requirement_sources": [],
        "requirements": [],
        "plan": [],
        "evidence": [],
        "findings": [],
        "completion_estimate": None,
        "report_path": None,
        "errors": [],
        "shell_results": [],
        "reasoning_log": [],
    }
    state_path = output_dir / "state.json"
    write_state(state_path, initial)
    app = build_graph(config, progress=progress)
    latest_state: ProjectCheckState = dict(initial)
    try:
        for chunk in app.stream(initial, stream_mode="updates"):
            for update in chunk.values():
                if isinstance(update, dict):
                    latest_state.update(update)
            write_state(state_path, latest_state)
    except Exception as exc:
        errors = list(latest_state.get("errors", []))
        errors.append(RunError(stage="runner", message="Graph execution failed.", detail=str(exc)))
        latest_state["errors"] = errors
        write_state(state_path, latest_state)
        raise RuntimeError(f"Restater check failed. Partial state written to {state_path}") from exc
    write_state(state_path, latest_state)
    return latest_state


def make_cli_progress(enabled: bool = True) -> ProgressCallback | None:
    if not enabled:
        return None

    started_at: dict[str, float] = {}

    def progress(stage: str, event: str) -> None:
        now = time.monotonic()
        if event == "start":
            started_at[stage] = now
            print(f"[restater] start {stage}", file=sys.stderr, flush=True)
            return
        elapsed = now - started_at.get(stage, now)
        if event == "failed":
            print(f"[restater] fail  {stage} ({elapsed:.1f}s)", file=sys.stderr, flush=True)
            return
        print(f"[restater] done  {stage} ({elapsed:.1f}s)", file=sys.stderr, flush=True)

    return progress


def write_state(path: Path, state: ProjectCheckState) -> None:
    def convert(value):
        if isinstance(value, BaseModel):
            return value.model_dump()
        if isinstance(value, list):
            return [convert(item) for item in value]
        if isinstance(value, dict):
            return {key: convert(item) for key, item in value.items()}
        return value

    write_text_no_bom(path, json.dumps(convert(state), ensure_ascii=False, indent=2))
