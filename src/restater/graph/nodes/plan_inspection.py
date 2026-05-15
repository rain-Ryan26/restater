from __future__ import annotations

from restater.graph.nodes.helpers import compact_json, load_prompt
from restater.graph.state import ProjectCheckState
from restater.llm import DeepSeekChatClient
from restater.models import InspectionStep


def make_plan_inspection_node(client: DeepSeekChatClient):
    system_prompt = load_prompt("plan_inspection.md")

    def plan_inspection(state: ProjectCheckState) -> dict:
        reasoning_log = list(state.get("reasoning_log", []))
        reasoning_log.append("plan_inspection: plan repo-verifiable checks from requirements and context index.")
        response = client.complete_json(
            system_prompt,
            compact_json(
                {
                    "project_path": state["project_path"],
                    "user_note": state.get("user_note", ""),
                    "requirements": state.get("requirements", []),
                    "context_index": state.get("context_index", []),
                },
                limit=50000,
            ),
        )
        plan = [InspectionStep(**item) for item in response.get("plan", [])]
        return {"plan": plan, "reasoning_log": reasoning_log}

    return plan_inspection

