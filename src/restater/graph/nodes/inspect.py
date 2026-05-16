from __future__ import annotations

from pathlib import Path

from restater.config import RestaterConfig
from restater.graph.nodes.execute_inspection import execute_steps, normalize_steps
from restater.graph.nodes.helpers import compact_json, load_prompt
from restater.graph.nodes.plan_inspection import context_for_planning, fallback_plan
from restater.graph.state import ProjectCheckState
from restater.llm import DeepSeekChatClient
from restater.models import EvidenceItem, InspectionStep, RunError, ShellResult


def make_inspect_node(config: RestaterConfig, client: DeepSeekChatClient, progress=None):
    system_prompt = load_prompt("inspect_next.md")

    def inspect(state: ProjectCheckState) -> dict:
        project_path = Path(state["project_path"])
        iteration = int(state.get("inspection_iteration", 0)) + 1
        evidence = normalize_evidence(state.get("evidence", []))
        errors = list(state.get("errors", []))
        shell_results = normalize_shell_results(state.get("shell_results", []))
        accumulated_plan = normalize_steps(state.get("plan", []))
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
            ready = bool(response.get("ready_for_judgement", False))
            decision = str(response.get("decision_summary", "")).strip()
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
                "errors": errors,
                "reasoning_log": reasoning_log,
            }

        execute_steps(
            project_path=project_path,
            steps=next_steps,
            evidence=evidence,
            errors=errors,
            shell_results=shell_results,
            config=config,
            progress=progress,
            stage="inspect",
        )
        accumulated_plan.extend(next_steps)

        if reached_limit:
            decision = f"{decision} 已达到检查轮数上限，进入最终判断。"
            if progress:
                progress("inspect", "trace", "iteration limit reached; next node is judge_status")

        return {
            "plan": accumulated_plan,
            "inspection_iteration": iteration,
            "inspection_complete": reached_limit,
            "inspection_decision": decision,
            "evidence": evidence,
            "errors": errors,
            "shell_results": shell_results,
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
