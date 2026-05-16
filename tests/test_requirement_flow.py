from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from restater.config import RestaterConfig
from restater.graph.nodes.classify_requirement_sources import classify_source
from restater.graph.nodes.curate_requirements import make_curate_requirements_node
from restater.graph.nodes.extract_requirements import make_extract_requirements_node
from restater.llm import ChatMessage, DeepSeekChatClient
from restater.models import RequirementItem, RequirementSource, RequirementSourceReview


class RequirementFlowTest(unittest.TestCase):
    def test_classify_source_separates_routing_and_authoritative_sources(self) -> None:
        cases = {
            "README.md": "routing_hint",
            "AGENT.md": "routing_hint",
            "docs/modules/README.md": "routing_hint",
            "docs/test_report/README.md": "routing_hint",
            "docs/requirements/proj_requirement.md": "authoritative_requirement",
            "docs/requirements/Verification Tutorial.pdf": "authoritative_requirement",
        }

        for path, expected_role in cases.items():
            with self.subTest(path=path):
                review = classify_source(
                    RequirementSource(
                        path=path,
                        source_type="pdf" if path.lower().endswith(".pdf") else "text",
                        summary="项目文档入口和要求说明",
                        confidence=0.8,
                    )
                )
                self.assertEqual(expected_role, review.role)

    def test_curate_requirements_drops_source_level_and_non_authoritative_items(self) -> None:
        node = make_curate_requirements_node()
        result = node(
            {
                "requirements": [
                    RequirementItem(
                        id="req-001",
                        title="Review requirement source README.md",
                        description="Inspect this text requirement source for repository-verifiable project requirements.",
                        source_path="README.md",
                        category="unknown",
                        verifiable_in_repo=True,
                        confidence=0.2,
                    ),
                    RequirementItem(
                        id="REQ-002",
                        title="Implement RV32I single-cycle CPU",
                        description="Implement the required single-cycle RV32I CPU baseline.",
                        source_path="docs/requirements/proj_requirement.md",
                        category="function",
                        verifiable_in_repo=True,
                        confidence=0.9,
                    ),
                ],
                "requirement_source_reviews": [
                    RequirementSourceReview(
                        path="README.md",
                        role="routing_hint",
                        reason="routing",
                        confidence=0.6,
                    ),
                    RequirementSourceReview(
                        path="docs/requirements/proj_requirement.md",
                        role="authoritative_requirement",
                        reason="requirements dir",
                        confidence=0.9,
                    ),
                ],
                "errors": [],
                "reasoning_log": [],
            }
        )

        requirements = result["requirements"]
        self.assertEqual(1, len(requirements))
        self.assertEqual("REQ-002", requirements[0].id)
        self.assertEqual([], result["errors"])

    def test_extract_requirements_failure_does_not_create_source_level_requirements(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("see docs/requirements", encoding="utf-8")
            req_path = root / "docs" / "requirements" / "proj_requirement.md"
            req_path.parent.mkdir(parents=True)
            req_path.write_text("基础功能：实现单周期 RV32I CPU。", encoding="utf-8")

            node = make_extract_requirements_node(test_config(), FailingClient())
            result = node(
                {
                    "project_path": str(root),
                    "user_note": "",
                    "requirement_sources": [
                        RequirementSource(path="README.md", source_type="text", summary="", confidence=0.8),
                        RequirementSource(
                            path="docs/requirements/proj_requirement.md",
                            source_type="text",
                            summary="基础功能",
                            confidence=0.8,
                        ),
                    ],
                    "requirement_source_reviews": [
                        RequirementSourceReview(
                            path="README.md",
                            role="routing_hint",
                            reason="routing",
                            confidence=0.6,
                        ),
                        RequirementSourceReview(
                            path="docs/requirements/proj_requirement.md",
                            role="authoritative_requirement",
                            reason="requirements dir",
                            confidence=0.9,
                        ),
                    ],
                    "errors": [],
                    "reasoning_log": [],
                }
            )

        self.assertEqual([], result["requirements"])
        self.assertIn("未生成来源级兜底需求项", result["errors"][0].message)

    def test_json_model_calls_prepend_default_chinese_language_policy(self) -> None:
        client = RecordingClient()

        client.complete_json("system body", "{}")

        self.assertIn("所有面向用户可见的自然语言输出默认使用简体中文", client.messages[0].content)
        self.assertIn("system body", client.messages[0].content)


class FailingClient:
    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        raise RuntimeError("invalid model json")


class RecordingClient(DeepSeekChatClient):
    def __init__(self) -> None:
        self.messages: list[ChatMessage] = []

    def complete(self, messages: list[ChatMessage], *, temperature: float | None = None) -> str:
        self.messages = messages
        return "{}"


def test_config() -> RestaterConfig:
    return RestaterConfig(
        api_key="test",
        api_base="https://example.invalid",
        model="test-model",
        default_project_path="",
        temperature=0.0,
        max_tokens=1000,
        context_file_limit=100,
        text_read_limit=2000,
        pdf_page_limit=1,
        model_timeout_seconds=1,
        inspection_max_iterations=2,
    )


if __name__ == "__main__":
    unittest.main()
