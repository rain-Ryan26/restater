from __future__ import annotations

from pathlib import Path

from restater.graph.nodes.helpers import compact_json, load_prompt
from restater.graph.state import ProjectCheckState
from restater.llm import DeepSeekChatClient
from restater.models import RunError
from restater.services import render_markdown_report
from restater.tools.filesystem import write_text_no_bom


def make_generate_report_node(client: DeepSeekChatClient, progress=None):
    system_prompt = load_prompt("generate_report_summary.md")

    def generate_report(state: ProjectCheckState) -> dict:
        reasoning_log = list(state.get("reasoning_log", []))
        reasoning_log.append("generate_report: render a developer-facing markdown report from structured findings.")
        errors = list(state.get("errors", []))
        try:
            user_prompt = compact_json(
                {
                    "requirements": state.get("requirements", []),
                    "findings": state.get("findings", []),
                    "completion_estimate": state.get("completion_estimate"),
                    "errors": state.get("errors", []),
                },
                limit=40000,
            )
            if progress:
                progress(
                    "generate_report",
                    "trace",
                    "model call: report summary, "
                    f"findings={len(state.get('findings', []))}, input_chars={len(user_prompt)}",
                )
            summary_response = client.complete_json(
                system_prompt,
                user_prompt,
            )
            model_summary = summary_response.get("summary", "")
            if progress:
                progress("generate_report", "trace", f"model returned summary_chars={len(model_summary)}")
        except Exception as exc:
            errors.append(
                RunError(
                    stage="generate_report",
                    message="Model report summary failed; rendered report without model summary.",
                    detail=str(exc),
                )
            )
            model_summary = ""
        report = render_markdown_report(
            project_path=state["project_path"],
            user_note=state.get("user_note", ""),
            requirements=state.get("requirements", []),
            findings=state.get("findings", []),
            evidence=state.get("evidence", []),
            completion=state["completion_estimate"],
            shell_results=state.get("shell_results", []),
            model_summary=model_summary,
        )
        report_path = Path(state["output_dir"]) / "report.md"
        if progress:
            progress("generate_report", "trace", f"write report: {report_path}")
        write_text_no_bom(report_path, report)
        return {"report_path": str(report_path), "errors": errors, "reasoning_log": reasoning_log}

    return generate_report
