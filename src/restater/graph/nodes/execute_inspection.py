from __future__ import annotations

import fnmatch
from pathlib import Path

from restater.config import RestaterConfig
from restater.graph.nodes.helpers import next_id
from restater.graph.state import ProjectCheckState
from restater.models import EvidenceItem, InspectionStep, RunError, ShellResult
from restater.tools.filesystem import find_files, read_text_preview, search_text
from restater.tools.pdf import extract_pdf_text
from restater.tools.shell import run_powershell


def make_execute_inspection_node(config: RestaterConfig, progress=None):
    def execute_inspection(state: ProjectCheckState) -> dict:
        project_path = Path(state["project_path"])
        evidence = list(state.get("evidence", []))
        errors = list(state.get("errors", []))
        shell_results = list(state.get("shell_results", []))
        reasoning_log = list(state.get("reasoning_log", []))
        reasoning_log.append("execute_inspection: 执行已规划的文件系统、PDF 和 shell 检查，并记录证据。")

        plan = state.get("plan", [])
        if progress:
            progress("execute_inspection", "trace", f"execute plan steps={len(plan)}")
        execute_steps(
            project_path=project_path,
            steps=normalize_steps(plan),
            evidence=evidence,
            errors=errors,
            shell_results=shell_results,
            config=config,
            progress=progress,
            stage="execute_inspection",
        )

        return {
            "evidence": evidence,
            "errors": errors,
            "shell_results": shell_results,
            "reasoning_log": reasoning_log,
        }

    return execute_inspection


def execute_steps(
    *,
    project_path: Path,
    steps: list[InspectionStep],
    evidence: list[EvidenceItem],
    errors: list[RunError],
    shell_results: list[ShellResult],
    config: RestaterConfig,
    progress=None,
    stage: str,
) -> None:
    for index, step in enumerate(steps, start=1):
        target_ids = step.target_requirement_ids or [None]
        try:
            if progress:
                progress(
                    stage,
                    "trace",
                    f"step {index}/{len(steps)}: tool={step.tool_hint}, action={step.action[:120]}",
                )
            if step.tool_hint == "shell" or step.commands:
                for command in step.commands:
                    if progress:
                        progress(stage, "trace", f"shell: {command}")
                    result = run_powershell(command, project_path)
                    shell_results.append(result)
                    append_evidence_for_targets(
                        evidence,
                        target_ids,
                        source="shell",
                        content_summary=summarize_shell(result),
                        raw_ref=command,
                    )
            elif step.tool_hint == "pdf":
                for rel in matching_files(project_path, step.file_patterns or ["*.pdf"]):
                    if progress:
                        progress(stage, "trace", f"pdf extract: {rel.relative_to(project_path)}")
                    text = extract_pdf_text(rel, page_limit=config.pdf_page_limit, char_limit=4000)
                    append_evidence_for_targets(
                        evidence,
                        target_ids,
                        source="pdf",
                        content_summary=(text[:800] or "PDF 首轮未提取到文本。"),
                        raw_ref=str(rel.relative_to(project_path)),
                    )
            else:
                if progress:
                    progress(
                        stage,
                        "trace",
                        f"filesystem search: terms={step.search_terms[:6]}, patterns={step.file_patterns[:6]}",
                    )
                matches = search_text(project_path, step.search_terms, patterns=step.file_patterns, limit=20)
                if progress:
                    progress(stage, "trace", f"filesystem matches={len(matches)}")
                summary = "; ".join(matches) if matches else "未找到直接文本匹配。"
                append_evidence_for_targets(
                    evidence,
                    target_ids,
                    source="file",
                    content_summary=summary,
                    raw_ref=", ".join(step.search_terms),
                )
                for rel in matching_files(project_path, step.file_patterns)[:5]:
                    try:
                        if progress:
                            progress(stage, "trace", f"text preview: {rel.relative_to(project_path)}")
                        preview = read_text_preview(rel, limit=2000)
                    except Exception:
                        continue
                    append_evidence_for_targets(
                        evidence,
                        target_ids,
                        source="file",
                        content_summary=preview[:800],
                        raw_ref=str(rel.relative_to(project_path)),
                    )
        except Exception as exc:
            errors.append(RunError(stage=stage, message=f"检查步骤失败：{step.id}", detail=str(exc)))


def append_evidence_for_targets(
    evidence: list[EvidenceItem],
    target_ids: list[str | None],
    *,
    source: str,
    content_summary: str,
    raw_ref: str | None,
) -> None:
    for target_id in target_ids:
        evidence.append(
            EvidenceItem(
                id=next_id("evidence", len(evidence)),
                requirement_id=target_id,
                source=source,
                content_summary=content_summary,
                raw_ref=raw_ref,
            )
        )


def normalize_steps(steps: list[InspectionStep | dict]) -> list[InspectionStep]:
    return [step if isinstance(step, InspectionStep) else InspectionStep(**step) for step in steps]


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
        return f"命令执行成功，退出码 0。输出：{out}"
    return f"命令执行失败，退出码 {result.exit_code}。stdout：{out} stderr：{err}"
