from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from restater.config import RestaterConfig
from restater.graph.nodes.inspect import make_inspect_node
from restater.models import InspectionProgress, RequirementItem
from restater.tools.validation import display_command, normalize_validation_command


class ValidationToolTest(unittest.TestCase):
    def test_maven_command_is_normalized_without_shell_wrapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pom.xml").write_text("<project />", encoding="utf-8")

            attempt = normalize_validation_command(
                "& 'E:\\D_C_tools2\\maven\\mvn\\bin\\mvn.cmd' -q -Dtest=FooTest,BarTest test",
                root,
            )

        self.assertTrue(attempt.runnable)
        self.assertIn("mvn.cmd", display_command(attempt.normalized_command))
        self.assertIn("-q", display_command(attempt.normalized_command))
        self.assertIn("-Dtest=FooTest,BarTest", display_command(attempt.normalized_command))
        self.assertIn("test", display_command(attempt.normalized_command))

    def test_validation_rejects_shell_chaining(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pom.xml").write_text("<project />", encoding="utf-8")

            attempt = normalize_validation_command("cd project && mvn test 2>&1", root)

        self.assertFalse(attempt.runnable)
        self.assertIn("unsupported shell syntax", attempt.blocked_reason)


class InspectProgressTest(unittest.TestCase):
    def test_inspect_over_updates_progress_and_finishes_loop(self) -> None:
        node = make_inspect_node(test_config(), InspectOverClient())
        result = node(
            {
                "project_path": str(Path.cwd()),
                "user_note": "",
                "requirements": [
                    RequirementItem(
                        id="REQ-001",
                        title="Run tests",
                        description="Automated tests should be considered.",
                        source_path="docs/requirements.md",
                        category="test",
                        verifiable_in_repo=True,
                        confidence=0.9,
                    )
                ],
                "context_index": [],
                "plan": [],
                "inspection_iteration": 0,
                "inspection_progress": InspectionProgress(),
                "evidence": [],
                "errors": [],
                "shell_results": [],
                "validation_attempts": [],
                "reasoning_log": [],
            }
        )

        self.assertTrue(result["inspection_complete"])
        self.assertEqual("inspect_over", result["inspection_progress"].stop_reason)
        self.assertEqual("finish", result["inspection_progress"].next_action_type)
        self.assertIn("测试已覆盖", result["inspection_progress"].coverage_summary)


class InspectOverClient:
    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        return {
            "ready_for_judgement": True,
            "inspect_over": True,
            "decision_summary": "证据足够，进入最终判断。",
            "inspection_progress": {
                "coverage_summary": "测试已覆盖主要需求。",
                "missing_parts": [],
                "next_action_type": "finish",
                "automation_test_assessment": "自动化测试结果已在证据中。",
                "open_questions": [],
                "stop_reason": "inspect_over",
            },
            "next_steps": [],
        }


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
