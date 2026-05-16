from __future__ import annotations

from pathlib import Path

from restater.config import RestaterConfig
from restater.graph.nodes.execute_inspection import execute_steps, normalize_steps
from restater.graph.nodes.helpers import compact_json, load_prompt
from restater.graph.nodes.plan_inspection import context_for_planning, fallback_plan
from restater.graph.state import ProjectCheckState
from restater.llm import DeepSeekChatClient
from restater.models import EvidenceItem, InspectionProgress, InspectionStep, RunError, ShellResult, ValidationAttempt


def make_inspect_node(config: RestaterConfig, client: DeepSeekChatClient, progress=None):
    system_prompt = load_prompt("inspect_next.md")

    def inspect(state: ProjectCheckState) -> dict:
        project_path = Path(state["project_path"])
        iteration = int(state.get("inspection_iteration", 0)) + 1
        evidence = normalize_evidence(state.get("evidence", []))
        errors = list(state.get("errors", []))
        shell_results = normalize_shell_results(state.get("shell_results", []))
        validation_attempts = normalize_validation_attempts(state.get("validation_attempts", []))
        accumulated_plan = normalize_steps(state.get("plan", []))
        inspection_progress = normalize_inspection_progress(state.get("inspection_progress", {}))
        reasoning_log = list(state.get("reasoning_log", []))
        reasoning_log.append(f"inspect: 第 {iteration} 轮规划并执行下一小批检查。")

        if progress:
            progress(
                "inspect",
                "trace",
                f"iteration {iteration}/{config.inspection_max_iterations}: evidence={len(evidence)}, prior_steps={len(accumulated_plan)}",
            )

        try:
            user_prompt = inspection_payload(state, iteration, accumulated_plan, evidence)
            if progress:
                progress("inspect", "trace", f"model call: next inspection decision, input_chars={len(user_prompt)}")
            response = client.complete_json(system_prompt, user_prompt)
            ready = bool(response.get("ready_for_judgement", False) or response.get("inspect_over", False))
            decision = str(response.get("decision_summary", "")).strip()
            inspection_progress = update_progress_from_response(inspection_progress, response)
            next_steps = normalize_next_steps(response.get("next_steps", [])[:3], iteration)
            if progress:
                if decision:
                    progress("inspect", "trace", f"model summary: {decision[:300]}")
                progress("inspect", "trace", f"model decision: ready={ready}, next_steps={len(next_steps)}")
        except Exception as exc:
            errors.append(
                RunError(
                    stage="inspect",
                    message="模型检查决策失败；改用本地文件系统兜底检查步骤。",
                    detail=str(exc),
                )
            )
            ready = False
            decision = "模型检查决策失败，改用本地兜底检查步骤。"
            inspection_progress.open_questions.append("模型未返回有效 inspect 决策，本轮使用兜底文件检查。")
            next_steps = fallback_plan(state)[:3]
            next_steps = normalize_next_steps([step.model_dump() for step in next_steps], iteration)
            if progress:
                progress("inspect", "trace", f"fallback next_steps={len(next_steps)}")

        reached_limit = iteration >= config.inspection_max_iterations
        if ready or not next_steps:
            return {
                "inspection_iteration": iteration,
                "inspection_complete": True,
                "inspection_decision": decision or "检查证据已足够进入最终判断。",
                "inspection_progress": inspection_progress,
                "errors": errors,
                "validation_attempts": validation_attempts,
                "reasoning_log": reasoning_log,
            }

        prior_validation_count = len(validation_attempts)
        execute_steps(
            project_path=project_path,
            steps=next_steps,
            evidence=evidence,
            errors=errors,
            shell_results=shell_results,
            config=config,
            validation_attempts=validation_attempts,
            progress=progress,
            stage="inspect",
        )
        accumulated_plan.extend(next_steps)
        inspection_progress = update_progress_after_execution(
            inspection_progress,
            next_steps,
            validation_attempts,
            prior_validation_count,
        )

        if reached_limit:
            decision = f"{decision} 已达到检查轮数上限，进入最终判断。"
            if progress:
                progress("inspect", "trace", "iteration limit reached; next node is judge_status")

        return {
            "plan": accumulated_plan,
            "inspection_iteration": iteration,
            "inspection_complete": reached_limit,
            "inspection_decision": decision,
            "inspection_progress": inspection_progress,
            "evidence": evidence,
            "errors": errors,
            "shell_results": shell_results,
            "validation_attempts": validation_attempts,
            "reasoning_log": reasoning_log,
        }

    return inspect


def inspection_payload(
    state: ProjectCheckState,
    iteration: int,
    accumulated_plan: list[InspectionStep],
    evidence: list[EvidenceItem],
) -> str:
    planning_context = context_for_planning(state.get("context_index", []))
    payload = {
        "project_path": state["project_path"],
        "user_note": state.get("user_note", ""),
        "iteration": iteration,
        "requirements": state.get("requirements", []),
        "context_index": planning_context,
        "prior_steps": [step.model_dump() for step in accumulated_plan[-12:]],
        "evidence": [item.model_dump() for item in evidence[-30:]],
        "inspection_progress": normalize_inspection_progress(state.get("inspection_progress", {})).model_dump(),
        "validation_attempts": [
            item.model_dump() for item in normalize_validation_attempts(state.get("validation_attempts", []))[-10:]
        ],
        "errors": state.get("errors", []),
    }
    return compact_json(payload, limit=25000)


def should_continue_inspection(state: ProjectCheckState) -> str:
    return "judge_status" if state.get("inspection_complete") else "inspect"


def normalize_next_steps(items: list[dict], iteration: int) -> list[InspectionStep]:
    steps: list[InspectionStep] = []
    for index, item in enumerate(items, start=1):
        normalized = dict(item)
        normalized["id"] = f"inspect-{iteration}-{index}"
        steps.append(InspectionStep(**normalized))
    return steps


def normalize_evidence(items: list[EvidenceItem | dict]) -> list[EvidenceItem]:
    return [item if isinstance(item, EvidenceItem) else EvidenceItem(**item) for item in items]


def normalize_shell_results(items: list[ShellResult | dict]) -> list[ShellResult]:
    return [item if isinstance(item, ShellResult) else ShellResult(**item) for item in items]


def normalize_validation_attempts(items: list[ValidationAttempt | dict]) -> list[ValidationAttempt]:
    return [item if isinstance(item, ValidationAttempt) else ValidationAttempt(**item) for item in items]


def normalize_inspection_progress(item: InspectionProgress | dict | None) -> InspectionProgress:
    if isinstance(item, InspectionProgress):
        return item
    if isinstance(item, dict):
        return InspectionProgress(**item)
    return InspectionProgress()


def update_progress_from_response(progress: InspectionProgress, response: dict) -> InspectionProgress:
    updates = response.get("inspection_progress", {})
    if not isinstance(updates, dict):
        updates = {}
    coverage_summary = str(updates.get("coverage_summary") or response.get("coverage_summary") or "").strip()
    automation = str(
        updates.get("automation_test_assessment") or response.get("automation_test_assessment") or ""
    ).strip()
    next_action = str(updates.get("next_action_type") or response.get("next_action_type") or "").strip()
    missing_parts = list_of_strings(updates.get("missing_parts") or response.get("missing_parts") or [])
    open_questions = list_of_strings(updates.get("open_questions") or response.get("open_questions") or [])
    stop_reason = str(updates.get("stop_reason") or response.get("stop_reason") or "").strip()

    if coverage_summary:
        progress.coverage_summary = coverage_summary
    if automation:
        progress.automation_test_assessment = automation
    if next_action in {"filesystem", "search", "read", "validation", "pdf", "report", "finish", "unknown"}:
        progress.next_action_type = next_action
    if missing_parts:
        progress.missing_parts = missing_parts
    if open_questions:
        progress.open_questions = open_questions
    if stop_reason:
        progress.stop_reason = stop_reason
    elif response.get("inspect_over") or response.get("ready_for_judgement"):
        progress.stop_reason = "inspect_over"
    return progress


def update_progress_after_execution(
    progress: InspectionProgress,
    steps: list[InspectionStep],
    validation_attempts: list[ValidationAttempt],
    prior_validation_count: int,
) -> InspectionProgress:
    refs = list(progress.inspected_refs)
    for step in steps:
        refs.append(f"{step.id}: {step.tool_hint}: {step.action[:120]}")
        for pattern in step.file_patterns[:6]:
            refs.append(f"file_pattern: {pattern}")
        for term in step.search_terms[:6]:
            refs.append(f"search_term: {term}")
        for command in step.commands:
            refs.append(f"command: {command}")
    progress.inspected_refs = dedupe_keep_order(refs)[-80:]

    attempt_refs = list(progress.validation_attempts)
    for attempt in validation_attempts[prior_validation_count:]:
        if attempt.purpose or attempt.runnable is False:
            status = "ok" if attempt.success else "failed"
            reason = attempt.summary or attempt.blocked_reason
            attempt_refs.append(f"{status}: {attempt.command[:160]} :: {reason[:240]}")
    progress.validation_attempts = dedupe_keep_order(attempt_refs)[-40:]
    return progress


def list_of_strings(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
