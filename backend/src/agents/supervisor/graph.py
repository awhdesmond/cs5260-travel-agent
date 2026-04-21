import asyncio
import logging

from langgraph.graph import END, START, StateGraph

logger = logging.getLogger(__name__)

from src.agents.critic import critic_node
from src.agents.ingestion import ingestion_node
from src.agents.shared import (
    _after_ingestion,
    cache_check_node,
    cache_write_node,
)
from src.agents.supervisor.root_concierge import root_dispatch_node
from src.agents.supervisor.state import SupervisorState
from src.agents.supervisor.sub_coordinators import (
    accommodation_coordinator_node,
    experiences_coordinator_node,
    intercity_coordinator_node,
    transport_coordinator_node,
)

SUPERVISOR_RECURSION_LIMIT: int = 100


async def _parallel_coordinators(state: dict) -> dict:
    """
    Run all three L2 coordinators in parallel via asyncio.gather.

    This avoids INVALID_CONCURRENT_GRAPH_UPDATE that occurs with edge-based
    fan-out/fan-in on shared state fields.
    """
    results = await asyncio.gather(
        transport_coordinator_node(state),
        accommodation_coordinator_node(state),
        experiences_coordinator_node(state),
        intercity_coordinator_node(state),
        return_exceptions=True,
    )

    merged: dict = {}
    coordinator_names = ["transport", "accommodation", "experiences", "intercity"]
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error("Supervisor coordinator %s FAILED: %s", coordinator_names[i], result)
        elif isinstance(result, dict):
            logger.info("Supervisor coordinator %s returned keys: %s", coordinator_names[i], list(result.keys()))
            merged.update(result)
        else:
            logger.warning("Supervisor coordinator %s returned unexpected type: %s", coordinator_names[i], type(result))
    logger.info("Supervisor parallel_coordinators merged keys: %s", list(merged.keys()))
    return merged


def build_supervisor_graph() -> StateGraph:
    """
    Build the full Supervisor-mode flow. Returns StateGraph (not compiled).
    """
    builder = StateGraph(SupervisorState)

    builder.add_node("ingestion", ingestion_node)
    builder.add_node("cache_check", cache_check_node)
    builder.add_node("root_dispatch", root_dispatch_node)
    builder.add_node("supervisor", _parallel_coordinators)
    builder.add_node("critic", critic_node)
    builder.add_node("cache_write", cache_write_node)

    builder.add_edge(START, "ingestion")
    builder.add_conditional_edges(
        "ingestion",
        _after_ingestion,
        {"end": END, "cache_check": "cache_check"},
    )
    builder.add_edge("cache_check", "root_dispatch")
    builder.add_edge("root_dispatch", "supervisor")
    builder.add_edge("supervisor", "critic")
    builder.add_edge("critic", "cache_write")
    builder.add_edge("cache_write", END)

    return builder
