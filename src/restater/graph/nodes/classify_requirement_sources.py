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
        reasoning_log.append("classify_requirement_sources: 为候选需求来源文件分配角色。")
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
            reason="README/AGENT 文件默认作为路由或仓库指引，除非后续需求明确引用权威来源。",
            confidence=min(source.confidence, 0.65),
        )

    if parts.intersection(AUTHORITATIVE_PARTS):
        return RequirementSourceReview(
            path=source.path,
            role="authoritative_requirement",
            reason="路径位于 requirements/spec/rubric/assignment 相关区域。",
            confidence=max(source.confidence, 0.8),
        )

    if parts.intersection(STATUS_PARTS):
        return RequirementSourceReview(
            path=source.path,
            role="status_or_test_evidence",
            reason="路径指向测试报告、状态记录、历史记录或生成报告。",
            confidence=max(min(source.confidence, 0.75), 0.55),
        )

    if parts.intersection(IMPLEMENTATION_PARTS):
        return RequirementSourceReview(
            path=source.path,
            role="implementation_doc",
            reason="路径指向模块、设计、架构或实现文档。",
            confidence=max(min(source.confidence, 0.75), 0.55),
        )

    if contains_authoritative_language(stem, summary):
        return RequirementSourceReview(
            path=source.path,
            role="authoritative_requirement",
            reason="文件名或摘要包含需求、评分、作业或提交相关表述。",
            confidence=max(source.confidence, 0.7),
        )

    if contains_status_language(summary):
        return RequirementSourceReview(
            path=source.path,
            role="status_or_test_evidence",
            reason="摘要描述当前状态、测试、回归或证据，而不是权威需求。",
            confidence=max(min(source.confidence, 0.7), 0.5),
        )

    return RequirementSourceReview(
        path=source.path,
        role="low_confidence",
        reason="没有足够信号表明该候选项能产出权威项目需求。",
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
