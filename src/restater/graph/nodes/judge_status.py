from __future__ import annotations

import re
from pathlib import Path

from restater.graph.nodes.helpers import compact_json, load_prompt
from restater.graph.state import ProjectCheckState
from restater.llm import DeepSeekChatClient
from restater.models import CompletionEstimate, ContextItem, EvidenceItem, FindingItem, RequirementItem, RunError
from restater.tools.filesystem import read_text_preview


def make_judge_status_node(client: DeepSeekChatClient, progress=None):
    system_prompt = load_prompt("judge_status.md")

    def judge_status(state: ProjectCheckState) -> dict:
        reasoning_log = list(state.get("reasoning_log", []))
        reasoning_log.append("judge_status: 对照需求和证据判断状态并估算完成度。")
        errors = list(state.get("errors", []))
        evidence = normalize_evidence(state.get("evidence", []))
        added = supplement_judgement_evidence(
            project_path=Path(state["project_path"]),
            requirements=normalize_requirements(state.get("requirements", [])),
            context=normalize_context(state.get("context_index", [])),
            evidence=evidence,
        )
        if added:
            reasoning_log.append(f"judge_status: 最终判断前补充了 {added} 条上下文证据。")
            if progress:
                progress("judge_status", "trace", f"supplemental evidence added={added}")
        try:
            user_prompt = compact_json(
                {
                    "requirements": state.get("requirements", []),
                    "evidence": evidence,
                    "context_index": context_for_judgement(state.get("context_index", [])),
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
                    f"evidence={len(evidence)}, input_chars={len(user_prompt)}",
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
                    message="模型状态判断失败；仓库可验证需求已标记为不确定。",
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
                        reason="模型未返回该需求的判断结果，当前阶段按不确定处理。",
                        evidence_ids=[],
                    )
                )
        completion = compute_completion(state.get("requirements", []), findings)
        return {
            "evidence": evidence,
            "findings": findings,
            "completion_estimate": completion,
            "errors": errors,
            "reasoning_log": reasoning_log,
        }

    return judge_status


def supplement_judgement_evidence(
    *,
    project_path: Path,
    requirements: list[RequirementItem],
    context: list[ContextItem],
    evidence: list[EvidenceItem],
) -> int:
    evidence_count_by_requirement: dict[str, int] = {}
    for item in evidence:
        if item.requirement_id:
            evidence_count_by_requirement[item.requirement_id] = evidence_count_by_requirement.get(item.requirement_id, 0) + 1

    added = 0
    for requirement in requirements:
        if not requirement.verifiable_in_repo or evidence_count_by_requirement.get(requirement.id, 0) > 0:
            continue
        for item in ranked_context_matches(requirement, context)[:2]:
            path = project_path / item.path
            try:
                preview = read_text_preview(path, limit=2400)
            except Exception:
                preview = item.summary
            if not preview:
                continue
            evidence.append(
                EvidenceItem(
                    id=f"evidence-{len(evidence) + 1:03d}",
                    requirement_id=requirement.id,
                    source="file",
                    content_summary=preview[:1000],
                    raw_ref=item.path,
                )
            )
            added += 1
            if added >= 30:
                return added
    return added


def ranked_context_matches(requirement: RequirementItem, context: list[ContextItem]) -> list[ContextItem]:
    terms = requirement_terms(requirement)
    scored: list[tuple[int, ContextItem]] = []
    for item in context:
        if item.kind in {"artifact", "unknown", "requirement"}:
            continue
        haystack = f"{item.path}\n{item.summary}".lower()
        score = sum(1 for term in terms if term in haystack)
        if item.kind in {"state", "test"}:
            score += 2
        if score:
            scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], pair[1].path))
    return [item for _, item in scored]


def requirement_terms(requirement: RequirementItem) -> list[str]:
    raw = f"{requirement.title} {requirement.description}".lower()
    parts = [part for part in re.split(r"[\s,，。；;：:（）()\[\]【】/+\-]+", raw) if len(part) >= 2]
    terms: list[str] = []
    seen: set[str] = set()
    for part in parts:
        candidates = [part]
        if contains_cjk(part) and len(part) > 3:
            candidates.extend(part[index : index + 3] for index in range(0, len(part) - 2))
        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                terms.append(candidate)
    return terms[:24]


def contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def context_for_judgement(context: list[ContextItem | dict]) -> list[dict]:
    priority = {"state": 0, "test": 1, "doc": 2, "code": 3, "requirement": 4}
    items = normalize_context(context)
    items = [item for item in items if item.kind not in {"artifact", "unknown"}]
    items.sort(key=lambda item: (priority.get(item.kind, 9), -item.confidence, item.path))
    return [
        {
            "path": item.path,
            "kind": item.kind,
            "summary": item.summary[:500],
            "confidence": item.confidence,
        }
        for item in items[:80]
    ]


def normalize_evidence(items: list[EvidenceItem | dict]) -> list[EvidenceItem]:
    return [item if isinstance(item, EvidenceItem) else EvidenceItem(**item) for item in items]


def normalize_requirements(items: list[RequirementItem | dict]) -> list[RequirementItem]:
    return [item if isinstance(item, RequirementItem) else RequirementItem(**item) for item in items]


def normalize_context(items: list[ContextItem | dict]) -> list[ContextItem]:
    return [item if isinstance(item, ContextItem) else ContextItem(**item) for item in items]


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
        basis="已完成=1，部分完成=0.5，未完成/不确定=0；当前阶段不纳入非仓库可验证需求。",
        done=done,
        partial=partial,
        missing=missing,
        unknown=unknown,
        excluded=excluded,
    )
