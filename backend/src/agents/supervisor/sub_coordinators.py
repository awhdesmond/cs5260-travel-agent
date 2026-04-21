from src.agents.workers.activities import activities_search_node
from src.agents.workers.flight import flight_search_node
from src.agents.workers.hotel import hotel_search_node
from src.agents.workers.transport import intercity_transport_node


async def transport_coordinator_node(state: dict) -> dict:
    """Level 2 sub-coordinator wrapping the flight worker."""
    return await flight_search_node(state)


async def intercity_coordinator_node(state: dict) -> dict:
    """Level 2 sub-coordinator wrapping the intercity transport worker."""
    return await intercity_transport_node(state)


async def accommodation_coordinator_node(state: dict) -> dict:
    """Level 2 sub-coordinator wrapping the hotel worker."""
    return await hotel_search_node(state)


async def experiences_coordinator_node(state: dict) -> dict:
    """Level 2 sub-coordinator wrapping the activities worker."""
    return await activities_search_node(state)
