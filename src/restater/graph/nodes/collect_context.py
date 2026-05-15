from __future__ import annotations

from pathlib import Path

from restater.config import RestaterConfig
from restater.graph.state import ProjectCheckState
from restater.models import EvidenceItem, RunError
from restater.services import ProjectScanner


def make_collect_context_node(config: RestaterConfig):
    scanner = ProjectScanner(config)

    def collect_context(state: ProjectCheckState) -> dict:
        project_path = Path(state["project_path"])
        errors = list(state.get("errors", []))
        reasoning_log = list(state.get("reasoning_log", []))
        reasoning_log.append("collect_context: inspect user note, scan project files, and classify requirement sources.")
        try:
            context, sources = scanner.scan(project_path)
        except Exception as exc:
            errors.append(RunError(stage="collect_context", message="Project scan failed.", detail=str(exc)))
            context, sources = [], []
        evidence = list(state.get("evidence", []))
        evidence.append(
            EvidenceItem(
                id="evidence-001",
                source="model",
                content_summary=f"Scanned {len(context)} files and identified {len(sources)} likely requirement sources.",
                raw_ref=str(project_path),
            )
        )
        return {
            "context_index": context,
            "requirement_sources": sources,
            "evidence": evidence,
            "errors": errors,
            "reasoning_log": reasoning_log,
        }

    return collect_context

