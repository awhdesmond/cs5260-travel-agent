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
from src.agents.swarm.state import SwarmState
from src.agents.workers import (
    activities_search_node,
    flight_search_node,
    hotel_search_node,
    intercity_transport_node,
)

SWARM_RECURSION_LIMIT: int = 50


async def parallel_workers_node(state: dict) -> dict:
    results = await asyncio.gather(
        flight_search_node(state),
        hotel_search_node(state),
        activities_search_node(state),
        intercity_transport_node(state),
        return_exceptions=True,
    )

    merged: dict = {}
    worker_names = ["flight_search", "hotel_search", "activities_search", "intercity_transport"]
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error("Swarm worker %s FAILED: %s", worker_names[i], result)
        elif isinstance(result, dict):
            logger.info("Swarm worker %s returned keys: %s", worker_names[i], list(result.keys()))
            merged.update(result)
        else:
            logger.warning("Swarm worker %s returned unexpected type: %s", worker_names[i], type(result))
    logger.info("Swarm parallel_workers merged keys: %s", list(merged.keys()))
    return merged


def build_swarm_graph() -> StateGraph:
    builder = StateGraph(SwarmState)

    builder.add_node("ingestion", ingestion_node)
    builder.add_node("cache_check", cache_check_node)
    builder.add_node("parallel_workers", parallel_workers_node)
    builder.add_node("critic", critic_node)
    builder.add_node("cache_write", cache_write_node)

    builder.add_edge(START, "ingestion")
    builder.add_conditional_edges(
        "ingestion",
        _after_ingestion,
        {"end": END, "cache_check": "cache_check"},
    )
    builder.add_edge("cache_check", "parallel_workers")
    builder.add_edge("parallel_workers", "critic")
    builder.add_edge("critic", "cache_write")
    builder.add_edge("cache_write", END)

    return builder
