from __future__ import annotations

from pathlib import Path

from restater.config import RestaterConfig
from restater.graph.nodes.helpers import compact_json, load_prompt
from restater.graph.state import ProjectCheckState
from restater.llm import DeepSeekChatClient
from restater.models import RequirementItem, RequirementSource, RequirementSourceReview, RunError
from restater.tools.filesystem import read_text_preview
from restater.tools.pdf import extract_pdf_text


def make_extract_requirements_node(config: RestaterConfig, client: DeepSeekChatClient, progress=None):
    system_prompt = load_prompt("extract_requirements.md")

    def extract_requirements(state: ProjectCheckState) -> dict:
        project_path = Path(state["project_path"])
        errors = list(state.get("errors", []))
        reasoning_log = list(state.get("reasoning_log", []))
        reasoning_log.append("extract_requirements: read authoritative requirement sources and ask the model for a structured list.")
        sources_payload = []
        sources = authoritative_sources(state)
        if progress:
            progress("extract_requirements", "trace", f"read requirement sources: {len(sources)}")
        for index, source in enumerate(sources, start=1):
            path = project_path / source.path
            try:
                if source.source_type == "pdf":
                    if progress:
                        progress("extract_requirements", "trace", f"pdf extract {index}/{len(sources)}: {source.path}")
                    content = extract_pdf_text(path, page_limit=config.pdf_page_limit, char_limit=config.text_read_limit)
                else:
                    if progress:
                        progress("extract_requirements", "trace", f"text preview {index}/{len(sources)}: {source.path}")
                    content = read_text_preview(path, limit=config.text_read_limit)
            except Exception as exc:
                errors.append(RunError(stage="extract_requirements", message=f"Failed to read {source.path}.", detail=str(exc)))
                content = source.summary
            sources_payload.append({"source": source.model_dump(), "content": content})

        if not sources_payload:
            return {
                "requirements": [],
                "errors": errors
                + [RunError(stage="extract_requirements", message="No authoritative requirement sources were identified.")],
                "reasoning_log": reasoning_log,
            }

        try:
            user_prompt = compact_json(
                {
                    "project_path": state["project_path"],
                    "user_note": state.get("user_note", ""),
                    "sources": sources_payload,
                }
            )
            if progress:
                progress("extract_requirements", "trace", f"model call: requirement extraction, input_chars={len(user_prompt)}")
            response = client.complete_json(
                system_prompt,
                user_prompt,
            )
            requirements = [RequirementItem(**item) for item in response.get("requirements", [])]
            if progress:
                summary = response.get("decision_summary")
                if isinstance(summary, str) and summary.strip():
                    progress("extract_requirements", "trace", f"model summary: {summary.strip()[:300]}")
                progress("extract_requirements", "trace", f"model returned requirements={len(requirements)}")
        except Exception as exc:
            errors.append(
                RunError(
                    stage="extract_requirements",
                    message="Model requirement extraction failed; no source-level fallback requirements were generated.",
                    detail=str(exc),
                )
            )
            requirements = []
        return {"requirements": requirements, "errors": errors, "reasoning_log": reasoning_log}

    return extract_requirements


def authoritative_sources(state: ProjectCheckState) -> list[RequirementSource]:
    sources = normalize_sources(state.get("requirement_sources", []))
    reviews = normalize_reviews(state.get("requirement_source_reviews", []))
    if not reviews:
        return sources
    authoritative_paths = {
        normalize_path(review.path)
        for review in reviews
        if review.role == "authoritative_requirement"
    }
    return [source for source in sources if normalize_path(source.path) in authoritative_paths]


def normalize_sources(items: list[RequirementSource | dict]) -> list[RequirementSource]:
    return [item if isinstance(item, RequirementSource) else RequirementSource(**item) for item in items]


def normalize_reviews(items: list[RequirementSourceReview | dict]) -> list[RequirementSourceReview]:
    return [item if isinstance(item, RequirementSourceReview) else RequirementSourceReview(**item) for item in items]


def normalize_path(path: str) -> str:
    return path.replace("\\", "/").lower()
