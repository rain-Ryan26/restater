from __future__ import annotations

import json
import time
from pathlib import Path

from pydantic import BaseModel

from restater.config import RestaterConfig
from restater.graph.builder import build_graph
from restater.graph.state import ProjectCheckState
from restater.tools.filesystem import write_text_no_bom


def run_check(project_path: Path, user_note: str, output_dir: Path | None, config: RestaterConfig) -> ProjectCheckState:
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
    app = build_graph(config)
    final_state = app.invoke(initial)
    write_state(output_dir / "state.json", final_state)
    return final_state


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
