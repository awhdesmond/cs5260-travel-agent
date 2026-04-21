def root_dispatch_node(state: dict) -> dict:
    """
    No-op node enabling edge-based fan-out.

    LangGraph fan-out requires a source node. This node passes through
    without modification; the fan-out edges from graph.py handle dispatch.
    """
    return {}
