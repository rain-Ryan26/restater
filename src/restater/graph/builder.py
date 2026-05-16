from __future__ import annotations

from collections.abc import Callable

from langgraph.graph import END, START, StateGraph

from restater.config import RestaterConfig
from restater.graph.nodes.collect_context import make_collect_context_node
from restater.graph.nodes.extract_requirements import make_extract_requirements_node
from restater.graph.nodes.generate_report import make_generate_report_node
from restater.graph.nodes.inspect import make_inspect_node, should_continue_inspection
from restater.graph.nodes.judge_status import make_judge_status_node
from restater.graph.state import ProjectCheckState
from restater.llm import DeepSeekChatClient


ProgressCallback = Callable[[str, str, str | None], None]


def build_graph(config: RestaterConfig, progress: ProgressCallback | None = None):
    client = DeepSeekChatClient(config)
    graph = StateGraph(ProjectCheckState)
    graph.add_node("collect_context", with_progress("collect_context", make_collect_context_node(config, progress), progress))
    graph.add_node(
        "extract_requirements",
        with_progress("extract_requirements", make_extract_requirements_node(config, client, progress), progress),
    )
    graph.add_node("inspect", with_progress("inspect", make_inspect_node(config, client, progress), progress))
    graph.add_node("judge_status", with_progress("judge_status", make_judge_status_node(client, progress), progress))
    graph.add_node("generate_report", with_progress("generate_report", make_generate_report_node(client, progress), progress))

    graph.add_edge(START, "collect_context")
    graph.add_edge("collect_context", "extract_requirements")
    graph.add_edge("extract_requirements", "inspect")
    graph.add_conditional_edges(
        "inspect",
        should_continue_inspection,
        {
            "inspect": "inspect",
            "judge_status": "judge_status",
        },
    )
    graph.add_edge("judge_status", "generate_report")
    graph.add_edge("generate_report", END)
    return graph.compile()


def with_progress(name: str, node, progress: ProgressCallback | None):
    if progress is None:
        return node

    def wrapped(state: ProjectCheckState) -> dict:
        progress(name, "start", None)
        try:
            result = node(state)
        except Exception:
            progress(name, "failed", None)
            raise
        progress(name, "done", None)
        return result

    return wrapped
