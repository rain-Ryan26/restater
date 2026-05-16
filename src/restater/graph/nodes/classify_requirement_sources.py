from __future__ import annotations

from restater.graph.state import ProjectCheckState
from restater.models import RequirementSource, RequirementSourceReview


ROUTING_FILE_NAMES = {"agent.md", "agents.md", "readme.md"}
AUTHORITATIVE_PARTS = {"requirement", "requirements", "rubric", "assignment", "spec", "specs"}
IMPLEMENTATION_PARTS = {"modules", "design", "architecture", "implementation"}
STATUS_PARTS = {"test_report", "stage", "history", "status", "state", "report"}


def make_classify_requirement_sources_node(progress=None):
    def classify_requirement_sources(state: ProjectCheckState) -> dict:
        reasoning_log = list(state.get("reasoning_log", []))
        reasoning_log.append("classify_requirement_sources: assign roles to candidate requirement source files.")
        sources = normalize_sources(state.get("requirement_sources", []))
        reviews = [classify_source(source) for source in sources]
        if progress:
            role_counts: dict[str, int] = {}
            for review in reviews:
                role_counts[review.role] = role_counts.get(review.role, 0) + 1
            progress("classify_requirement_sources", "trace", f"source roles: {role_counts}")
        return {"requirement_source_reviews": reviews, "reasoning_log": reasoning_log}

    return classify_requirement_sources


def normalize_sources(items: list[RequirementSource | dict]) -> list[RequirementSource]:
    return [item if isinstance(item, RequirementSource) else RequirementSource(**item) for item in items]


def classify_source(source: RequirementSource) -> RequirementSourceReview:
    normalized = source.path.replace("\\", "/").lower()
    parts = {part for part in normalized.split("/") if part}
    name = normalized.rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0]
    summary = source.summary.lower()

    if name in ROUTING_FILE_NAMES:
        return RequirementSourceReview(
            path=source.path,
            role="routing_hint",
            reason="README/AGENT files are treated as routing or repository guidance unless later requirements quote authoritative sources.",
            confidence=min(source.confidence, 0.65),
        )

    if parts.intersection(AUTHORITATIVE_PARTS):
        return RequirementSourceReview(
            path=source.path,
            role="authoritative_requirement",
            reason="Path is under a requirements/spec/rubric/assignment area.",
            confidence=max(source.confidence, 0.8),
        )

    if parts.intersection(STATUS_PARTS):
        return RequirementSourceReview(
            path=source.path,
            role="status_or_test_evidence",
            reason="Path points to test reports, status records, history, or generated reports.",
            confidence=max(min(source.confidence, 0.75), 0.55),
        )

    if parts.intersection(IMPLEMENTATION_PARTS):
        return RequirementSourceReview(
            path=source.path,
            role="implementation_doc",
            reason="Path points to module, design, architecture, or implementation documentation.",
            confidence=max(min(source.confidence, 0.75), 0.55),
        )

    if contains_authoritative_language(stem, summary):
        return RequirementSourceReview(
            path=source.path,
            role="authoritative_requirement",
            reason="Filename or summary contains requirement, rubric, grading, assignment, or submission language.",
            confidence=max(source.confidence, 0.7),
        )

    if contains_status_language(summary):
        return RequirementSourceReview(
            path=source.path,
            role="status_or_test_evidence",
            reason="Summary describes current status, tests, regression, or evidence rather than requirements.",
            confidence=max(min(source.confidence, 0.7), 0.5),
        )

    return RequirementSourceReview(
        path=source.path,
        role="low_confidence",
        reason="No strong signal that this candidate can produce authoritative project requirements.",
        confidence=min(source.confidence, 0.45),
    )


def contains_authoritative_language(stem: str, summary: str) -> bool:
    keywords = [
        "requirement",
        "requirements",
        "rubric",
        "assignment",
        "spec",
        "grading",
        "评分",
        "要求",
        "提交",
        "验收",
    ]
    text = f"{stem} {summary}"
    return any(keyword in text for keyword in keywords)


def contains_status_language(summary: str) -> bool:
    keywords = ["当前状态", "测试结论", "回归", "coverage", "testbench", "status", "stage", "history"]
    return any(keyword in summary for keyword in keywords)
