from __future__ import annotations

import fnmatch
from pathlib import Path

from restater.config import RestaterConfig
from restater.graph.nodes.helpers import next_id
from restater.graph.state import ProjectCheckState
from restater.models import EvidenceItem, RunError, ShellResult
from restater.tools.filesystem import find_files, read_text_preview, search_text
from restater.tools.pdf import extract_pdf_text
from restater.tools.shell import run_powershell


def make_execute_inspection_node(config: RestaterConfig):
    def execute_inspection(state: ProjectCheckState) -> dict:
        project_path = Path(state["project_path"])
        evidence = list(state.get("evidence", []))
        errors = list(state.get("errors", []))
        shell_results = list(state.get("shell_results", []))
        reasoning_log = list(state.get("reasoning_log", []))
        reasoning_log.append("execute_inspection: execute planned filesystem, pdf, and shell checks and record evidence.")

        for step in state.get("plan", []):
            target_id = step.target_requirement_ids[0] if step.target_requirement_ids else None
            try:
                if step.tool_hint == "shell" or step.commands:
                    for command in step.commands:
                        result = run_powershell(command, project_path)
                        shell_results.append(result)
                        evidence.append(
                            EvidenceItem(
                                id=next_id("evidence", len(evidence)),
                                requirement_id=target_id,
                                source="shell",
                                content_summary=summarize_shell(result),
                                raw_ref=command,
                            )
                        )
                elif step.tool_hint == "pdf":
                    for rel in matching_files(project_path, step.file_patterns or ["*.pdf"]):
                        text = extract_pdf_text(rel, page_limit=config.pdf_page_limit, char_limit=4000)
                        evidence.append(
                            EvidenceItem(
                                id=next_id("evidence", len(evidence)),
                                requirement_id=target_id,
                                source="pdf",
                                content_summary=(text[:800] or "PDF produced no text in first pass."),
                                raw_ref=str(rel.relative_to(project_path)),
                            )
                        )
                else:
                    matches = search_text(project_path, step.search_terms, patterns=step.file_patterns, limit=20)
                    summary = "; ".join(matches) if matches else "No direct text matches found."
                    evidence.append(
                        EvidenceItem(
                            id=next_id("evidence", len(evidence)),
                            requirement_id=target_id,
                            source="file",
                            content_summary=summary,
                            raw_ref=", ".join(step.search_terms),
                        )
                    )
                    for rel in matching_files(project_path, step.file_patterns)[:5]:
                        try:
                            preview = read_text_preview(rel, limit=2000)
                        except Exception:
                            continue
                        evidence.append(
                            EvidenceItem(
                                id=next_id("evidence", len(evidence)),
                                requirement_id=target_id,
                                source="file",
                                content_summary=preview[:800],
                                raw_ref=str(rel.relative_to(project_path)),
                            )
                        )
            except Exception as exc:
                errors.append(RunError(stage="execute_inspection", message=f"Inspection step failed: {step.id}", detail=str(exc)))

        return {
            "evidence": evidence,
            "errors": errors,
            "shell_results": shell_results,
            "reasoning_log": reasoning_log,
        }

    return execute_inspection


def matching_files(project_path: Path, patterns: list[str]) -> list[Path]:
    if not patterns:
        return []
    results: list[Path] = []
    for path in find_files(project_path, limit=1000):
        rel = str(path.relative_to(project_path))
        if any(fnmatch.fnmatch(rel, pattern) for pattern in patterns):
            results.append(path)
    return results


def summarize_shell(result: ShellResult) -> str:
    out = result.stdout.strip()[:500]
    err = result.stderr.strip()[:500]
    if result.exit_code == 0:
        return f"Command succeeded with exit code 0. Output: {out}"
    return f"Command failed with exit code {result.exit_code}. stdout: {out} stderr: {err}"

