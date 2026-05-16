from __future__ import annotations

from restater.graph.nodes.helpers import compact_json, load_prompt
from restater.graph.state import ProjectCheckState
from restater.llm import DeepSeekChatClient
from restater.models import CompletionEstimate, FindingItem, RequirementItem, RunError


def make_judge_status_node(client: DeepSeekChatClient, progress=None):
    system_prompt = load_prompt("judge_status.md")

    def judge_status(state: ProjectCheckState) -> dict:
        reasoning_log = list(state.get("reasoning_log", []))
        reasoning_log.append("judge_status: compare requirements with evidence and estimate completion.")
        errors = list(state.get("errors", []))
        try:
            user_prompt = compact_json(
                {
                    "requirements": state.get("requirements", []),
                    "evidence": state.get("evidence", []),
                    "errors": state.get("errors", []),
                },
                limit=50000,
            )
            if progress:
                progress(
                    "judge_status",
                    "trace",
                    "model call: status judgement, "
                    f"requirements={len(state.get('requirements', []))}, "
                    f"evidence={len(state.get('evidence', []))}, input_chars={len(user_prompt)}",
                )
            response = client.complete_json(
                system_prompt,
                user_prompt,
            )
            findings = [FindingItem(**item) for item in response.get("findings", [])]
            if progress:
                progress("judge_status", "trace", f"model returned findings={len(findings)}")
        except Exception as exc:
            errors.append(
                RunError(
                    stage="judge_status",
                    message="Model status judgement failed; marked repo-verifiable requirements as unknown.",
                    detail=str(exc),
                )
            )
            findings = []
        existing = {finding.requirement_id for finding in findings}
        for requirement in state.get("requirements", []):
            if requirement.id not in existing:
                findings.append(
                    FindingItem(
                        requirement_id=requirement.id,
                        status="unknown",
                        reason="The model did not return a judgement for this requirement in Phase 1.",
                        evidence_ids=[],
                    )
                )
        completion = compute_completion(state.get("requirements", []), findings)
        return {"findings": findings, "completion_estimate": completion, "errors": errors, "reasoning_log": reasoning_log}

    return judge_status


def compute_completion(requirements: list[RequirementItem], findings: list[FindingItem]) -> CompletionEstimate:
    requirement_by_id = {item.id: item for item in requirements}
    finding_by_id = {item.requirement_id: item for item in findings}
    done = partial = missing = unknown = excluded = 0
    score = 0.0
    total = 0
    for requirement in requirements:
        if not requirement.verifiable_in_repo:
            excluded += 1
            continue
        total += 1
        finding = finding_by_id.get(requirement.id)
        status = finding.status if finding else "unknown"
        if status == "done":
            done += 1
            score += 1
        elif status == "partial":
            partial += 1
            score += 0.5
        elif status == "missing":
            missing += 1
        else:
            unknown += 1
    percent = (score / total * 100) if total else 0.0
    return CompletionEstimate(
        percent=percent,
        basis="done=1, partial=0.5, missing/unknown=0; non-repo-verifiable requirements excluded in Phase 1.",
        done=done,
        partial=partial,
        missing=missing,
        unknown=unknown,
        excluded=excluded,
    )
