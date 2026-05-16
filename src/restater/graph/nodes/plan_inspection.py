from __future__ import annotations

from restater.graph.nodes.helpers import compact_json, load_prompt
from restater.graph.state import ProjectCheckState
from restater.llm import DeepSeekChatClient
from restater.models import ContextItem, InspectionStep, RunError


def make_plan_inspection_node(client: DeepSeekChatClient, progress=None):
    system_prompt = load_prompt("plan_inspection.md")

    def plan_inspection(state: ProjectCheckState) -> dict:
        reasoning_log = list(state.get("reasoning_log", []))
        reasoning_log.append("plan_inspection: plan repo-verifiable checks from requirements and context index.")
        errors = list(state.get("errors", []))
        try:
            planning_context = context_for_planning(state.get("context_index", []))
            user_prompt = compact_json(
                {
                    "project_path": state["project_path"],
                    "user_note": state.get("user_note", ""),
                    "requirements": state.get("requirements", []),
                    "context_index": planning_context,
                },
                limit=25000,
            )
            if progress:
                progress(
                    "plan_inspection",
                    "trace",
                    "prepare planning payload: "
                    f"requirements={len(state.get('requirements', []))}, "
                    f"context_items={len(planning_context)}, input_chars={len(user_prompt)}",
                )
                progress("plan_inspection", "trace", "model call: inspection planning")
            response = client.complete_json(
                system_prompt,
                user_prompt,
            )
            plan = [InspectionStep(**item) for item in response.get("plan", [])]
            if progress:
                summary = response.get("decision_summary")
                if isinstance(summary, str) and summary.strip():
                    progress("plan_inspection", "trace", f"model summary: {summary.strip()[:300]}")
                progress("plan_inspection", "trace", f"model returned plan_steps={len(plan)}")
        except Exception as exc:
            errors.append(
                RunError(
                    stage="plan_inspection",
                    message="Model inspection planning failed; fell back to filesystem search steps.",
                    detail=str(exc),
                )
            )
            plan = fallback_plan(state)
        return {"plan": plan, "errors": errors, "reasoning_log": reasoning_log}

    return plan_inspection


def context_for_planning(context: list[ContextItem]) -> list[dict]:
    priority = {
        "requirement": 0,
        "state": 1,
        "test": 2,
        "doc": 3,
        "code": 4,
        "artifact": 5,
        "unknown": 6,
    }
    normalized = [normalize_context_item(item) for item in context]
    filtered = [item for item in normalized if item["kind"] not in {"artifact", "unknown"}]
    filtered.sort(key=lambda item: (priority.get(item["kind"], 9), -item["confidence"], item["path"]))
    selected = filtered[:50]
    return [
        {
            "path": item["path"],
            "kind": item["kind"],
            "summary": item["summary"][:300],
            "confidence": item["confidence"],
        }
        for item in selected
    ]


def normalize_context_item(item: ContextItem | dict) -> dict:
    if isinstance(item, dict):
        return {
            "path": str(item.get("path", "")),
            "kind": str(item.get("kind", "unknown")),
            "summary": str(item.get("summary", "")),
            "confidence": float(item.get("confidence", 0.0) or 0.0),
        }
    return {
        "path": item.path,
        "kind": item.kind,
        "summary": item.summary,
        "confidence": item.confidence,
    }


def fallback_plan(state: ProjectCheckState) -> list[InspectionStep]:
    requirements = state.get("requirements", [])
    if not requirements:
        return [
            InspectionStep(
                id="step-001",
                target_requirement_ids=[],
                action="Inspect repository documents and source files for status evidence.",
                expected_evidence="File matches and source previews that indicate current implementation status.",
                tool_hint="filesystem",
                file_patterns=["*.md", "*.py", "*.java", "*.js", "*.ts", "*.tsx"],
                search_terms=["status", "TODO", "requirement", "test", "完成", "未完成", "要求"],
            )
        ]

    plan: list[InspectionStep] = []
    for index, requirement in enumerate(requirements[:20], start=1):
        terms = [term for term in requirement.title.replace("`", " ").split() if len(term) >= 2]
        if requirement.category != "unknown":
            terms.append(requirement.category)
        plan.append(
            InspectionStep(
                id=f"step-{index:03d}",
                target_requirement_ids=[requirement.id],
                action=f"Search repository evidence for {requirement.title}.",
                expected_evidence="Direct file matches, source previews, or absence of matches.",
                tool_hint="filesystem",
                file_patterns=["*.md", "*.py", "*.java", "*.js", "*.ts", "*.tsx", "*.sql", "*.json"],
                search_terms=terms[:8] or [requirement.title],
            )
        )
    return plan
