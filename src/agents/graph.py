from langgraph.graph import END, StateGraph

from src.agents.nodes.triage_nodes import patient_safe_response_node, run_triage_pipeline_node
from src.agents.state import AgentState


def should_continue(state: AgentState) -> str:
    """Route based on whether an error occurred during pipeline processing."""
    if state.get("error"):
        return END
    return "respond"


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("triage_pipeline", run_triage_pipeline_node)
    graph.add_node("respond", patient_safe_response_node)

    graph.set_entry_point("triage_pipeline")
    graph.add_conditional_edges("triage_pipeline", should_continue)
    graph.add_edge("respond", END)

    return graph.compile()


agent = build_graph()
