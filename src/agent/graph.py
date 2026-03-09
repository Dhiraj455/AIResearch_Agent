from langgraph.graph import StateGraph, END

from src.schemes import RunState
from src.agent.nodes import (
    plan_node,
    search_node,
    fetch_node,
    extract_node,
    coverage_check_node,
    write_node,
    verify_node,
    revise_node,
)
from src.config import settings


def should_loop(state: RunState) -> str:
    """Decide whether to perform another search/fetch iteration based on coverage gaps."""
    if state.coverage.gaps and state.iter < settings.MAX_ITERS - 1:
        return "loop"
    return "write"


def build_graph():
    """
    Build the LangGraph state machine over RunState.

    Node names are suffixed with `_step` to avoid clashing with RunState field
    names (e.g. `plan`, `coverage`), which LangGraph reserves for state keys.
    """
    g = StateGraph(RunState)

    g.add_node("plan_step", plan_node)
    g.add_node("search_step", search_node)
    g.add_node("fetch_step", fetch_node)
    g.add_node("extract_step", extract_node)
    g.add_node("coverage_step", coverage_check_node)
    g.add_node("write_step", write_node)
    g.add_node("verify_step", verify_node)
    g.add_node("revise_step", revise_node)

    g.set_entry_point("plan_step")
    g.add_edge("plan_step", "search_step")
    g.add_edge("search_step", "fetch_step")
    g.add_edge("fetch_step", "extract_step")
    g.add_edge("extract_step", "coverage_step")

    g.add_conditional_edges(
        "coverage_step",
        should_loop,
        {
            "loop": "search_step",
            "write": "write_step",
        },
    )

    g.add_edge("write_step", "verify_step")
    g.add_edge("verify_step", "revise_step")
    g.add_edge("revise_step", END)

    return g.compile()