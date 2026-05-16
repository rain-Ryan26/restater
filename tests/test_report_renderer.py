from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from restater.models import CompletionEstimate, EvidenceItem, FindingItem, RequirementItem
from restater.services.report_renderer import render_markdown_report


class ReportRendererTest(unittest.TestCase):
    def test_report_uses_short_summaries_instead_of_long_source_text(self) -> None:
        long_requirement_text = "原始需求正文" * 120
        long_evidence_text = "证据原文片段" * 120

        report = render_markdown_report(
            project_path="E:\\example",
            user_note="整理项目进度",
            requirements=[
                RequirementItem(
                    id="REQ-001",
                    title="Review requirement source docs/requirements/proj_requirement.md",
                    description=long_requirement_text,
                    source_path="docs/requirements/proj_requirement.md",
                    category="document",
                    verifiable_in_repo=True,
                    confidence=0.8,
                )
            ],
            findings=[
                FindingItem(
                    requirement_id="REQ-001",
                    status="partial",
                    reason="当前只完成了需求源识别，尚未完成逐项内容核对。",
                    evidence_ids=["evidence-001"],
                )
            ],
            evidence=[
                EvidenceItem(
                    id="evidence-001",
                    requirement_id="REQ-001",
                    source="file",
                    content_summary=long_evidence_text,
                    raw_ref="docs/requirements/proj_requirement.md",
                )
            ],
            completion=CompletionEstimate(
                percent=50.0,
                basis="test basis",
                done=0,
                partial=1,
                missing=0,
                unknown=0,
                excluded=0,
            ),
            shell_results=[],
            model_summary="存在结构化抽取缺口。",
        )

        self.assertIn("需求源：`docs/requirements/proj_requirement.md`", report)
        self.assertIn("检查主题：", report)
        self.assertIn("判断：当前只完成了需求源识别，尚未完成逐项内容核对。", report)
        self.assertIn("（`docs/requirements/proj_requirement.md`）", report)
        self.assertNotIn(long_requirement_text, report)
        self.assertNotIn(long_evidence_text, report)
        self.assertLess(report.count("原始需求正文"), 20)
        self.assertLess(report.count("证据原文片段"), 20)


if __name__ == "__main__":
    unittest.main()
