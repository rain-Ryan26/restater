from __future__ import annotations

import re

from restater.models import CompletionEstimate, EvidenceItem, FindingItem, RequirementItem, ShellResult

REQUIREMENT_SUMMARY_LIMIT = 120
EVIDENCE_SUMMARY_LIMIT = 120


def render_markdown_report(
    *,
    project_path: str,
    user_note: str,
    requirements: list[RequirementItem],
    findings: list[FindingItem],
    evidence: list[EvidenceItem],
    completion: CompletionEstimate,
    shell_results: list[ShellResult],
    model_summary: str | None = None,
) -> str:
    requirement_by_id = {item.id: item for item in requirements}
    evidence_by_id = {item.id: item for item in evidence}
    lines: list[str] = [
        "# 项目检查报告",
        "",
        "## 概览",
        "",
        f"- 项目路径：`{project_path}`",
        f"- 完成度估算：{completion.percent:.1f}%",
        f"- 估算依据：{completion.basis}",
    ]
    if user_note:
        lines.append(f"- 用户初始说明：{user_note}")
    lines.extend(
        [
            "",
            "## 状态汇总",
            "",
            f"- 已完成：{completion.done}",
            f"- 部分完成：{completion.partial}",
            f"- 未完成：{completion.missing}",
            f"- 不确定：{completion.unknown}",
            f"- 暂不纳入仓库完成度：{completion.excluded}",
            "",
        ]
    )
    if model_summary:
        lines.extend(["## 总体判断", "", model_summary.strip(), ""])

    for status, title in [
        ("done", "已完成项"),
        ("partial", "部分完成项"),
        ("missing", "未完成项"),
        ("unknown", "不确定项"),
    ]:
        lines.extend([f"## {title}", ""])
        group = [finding for finding in findings if finding.status == status]
        if not group:
            lines.extend(["无。", ""])
            continue
        for finding in group:
            requirement = requirement_by_id.get(finding.requirement_id)
            title_text = requirement.title if requirement else finding.requirement_id
            lines.append(f"### {title_text}")
            if requirement:
                lines.append(f"- 需求源：`{requirement.source_path}`")
                lines.append(f"- 检查主题：{summarize_requirement(requirement)}")
            lines.append(f"- 判断：{finding.reason}")
            refs = [evidence_by_id.get(eid) for eid in finding.evidence_ids]
            refs = [ref for ref in refs if ref is not None]
            if refs:
                lines.append("- 证据：")
                for ref in refs:
                    raw = f"（`{ref.raw_ref}`）" if ref.raw_ref else ""
                    lines.append(f"  - {summarize_evidence(ref)}{raw}")
            lines.append("")

    if shell_results:
        lines.extend(["## 命令执行摘要", ""])
        for result in shell_results:
            lines.append(f"### `{result.command}`")
            lines.append(f"- 工作目录：`{result.cwd}`")
            lines.append(f"- 退出码：{result.exit_code}")
            if result.stdout.strip():
                lines.append("- stdout：")
                lines.append("```text")
                lines.append(result.stdout.strip()[:2000])
                lines.append("```")
            if result.stderr.strip():
                lines.append("- stderr：")
                lines.append("```text")
                lines.append(result.stderr.strip()[:2000])
                lines.append("```")
            lines.append("")

    lines.extend(
        [
            "## 下一步建议",
            "",
            "- 优先处理未完成项和不确定项。",
            "- 对命令失败或缺少证据的项目补充可复现验证方式。",
            "- 非仓库产物类要求在第二阶段单独维护确认清单。",
            "",
        ]
    )
    return "\n".join(lines)


def summarize_requirement(requirement: RequirementItem) -> str:
    summary = compact_text(requirement.description)
    if not summary:
        summary = requirement.title
    return truncate_text(summary, REQUIREMENT_SUMMARY_LIMIT)


def summarize_evidence(evidence: EvidenceItem) -> str:
    summary = compact_text(evidence.content_summary)
    if evidence.source == "file" and evidence.raw_ref:
        path_refs = extract_path_refs(summary)
        if path_refs:
            summary = "文件匹配：" + "；".join(path_refs[:3])
        elif summary.startswith("No direct text matches found"):
            summary = "未找到直接文本匹配"
    elif evidence.source == "pdf":
        summary = "PDF 文本已解析，详见引用位置" if summary else "PDF 未提取到文本"
    return truncate_text(summary, EVIDENCE_SUMMARY_LIMIT)


def compact_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def extract_path_refs(text: str) -> list[str]:
    refs: list[str] = []
    for match in re.finditer(r"([A-Za-z0-9_.\-/\\]+):\d+", text):
        ref = match.group(1)
        if "/" in ref or "\\" in ref:
            refs.append(ref)
    return refs
