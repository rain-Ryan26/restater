from __future__ import annotations

from pathlib import Path

from restater.config import RestaterConfig
from restater.graph.nodes.helpers import compact_json, load_prompt
from restater.graph.state import ProjectCheckState
from restater.llm import DeepSeekChatClient
from restater.models import RequirementItem, RunError
from restater.tools.filesystem import read_text_preview
from restater.tools.pdf import extract_pdf_text


def make_extract_requirements_node(config: RestaterConfig, client: DeepSeekChatClient):
    system_prompt = load_prompt("extract_requirements.md")

    def extract_requirements(state: ProjectCheckState) -> dict:
        project_path = Path(state["project_path"])
        errors = list(state.get("errors", []))
        reasoning_log = list(state.get("reasoning_log", []))
        reasoning_log.append("extract_requirements: read likely requirement sources and ask the model for a structured list.")
        sources_payload = []
        for source in state.get("requirement_sources", []):
            path = project_path / source.path
            try:
                if source.source_type == "pdf":
                    content = extract_pdf_text(path, page_limit=config.pdf_page_limit, char_limit=config.text_read_limit)
                else:
                    content = read_text_preview(path, limit=config.text_read_limit)
            except Exception as exc:
                errors.append(RunError(stage="extract_requirements", message=f"Failed to read {source.path}.", detail=str(exc)))
                content = source.summary
            sources_payload.append({"source": source.model_dump(), "content": content})

        if not sources_payload:
            return {
                "requirements": [],
                "errors": errors
                + [RunError(stage="extract_requirements", message="No requirement sources were identified.")],
                "reasoning_log": reasoning_log,
            }

        response = client.complete_json(
            system_prompt,
            compact_json(
                {
                    "project_path": state["project_path"],
                    "user_note": state.get("user_note", ""),
                    "sources": sources_payload,
                }
            ),
        )
        requirements = [RequirementItem(**item) for item in response.get("requirements", [])]
        return {"requirements": requirements, "errors": errors, "reasoning_log": reasoning_log}

    return extract_requirements

