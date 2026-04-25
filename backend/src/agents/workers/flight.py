import logging
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from src.agents.llm import get_gemini_model, extract_json_from_response
from src.prompts.flight import FLIGHT_SEARCH_PROMPT
from src.state.models import TransportPlan
from src.tools.grounding import get_search_grounding_tool
from src.tools.serpapi_flights import get_iata_code, search_flights
from src.state.blackboard import TravelBlackboard


logger = logging.getLogger(__name__)


async def _search_via_serpapi(
    origin: str,
    outbound_city: str,
    inbound_city: str,
    departure_date: str,
    return_date: str,
    max_options: int,
) -> dict | None:
    """
    Try SerpAPI for both outbound and inbound flights.
    """
    origin_code = get_iata_code(origin)
    outbound_code = get_iata_code(outbound_city)
    inbound_code = get_iata_code(inbound_city)

    if not origin_code or not outbound_code:
        logger.info("missing IATA codes for %s(%s) or %s(%s), falling back", origin, origin_code, outbound_city, outbound_code)
        return None

    # Inbound code defaults to outbound if same city or missing
    if not inbound_code:
        inbound_code = outbound_code

    # Pass city names so search_flights can build working Google Flights booking URLs
    inbound_city_label = inbound_city or outbound_city
    outbound_results = await search_flights(
        origin_code, outbound_code, departure_date, max_options,
        origin_city=origin, dest_city=outbound_city,
    )
    inbound_results = await search_flights(
        inbound_code or outbound_code, origin_code, return_date, max_options,
        origin_city=inbound_city_label, dest_city=origin,
    )

    if not outbound_results and not inbound_results:
        return None

    plan = {
        "outbound_flights": outbound_results or [],
        "inbound_flights": inbound_results or [],
    }

    # Validate with Pydantic
    try:
        validated = TransportPlan.model_validate(plan)
        return validated.model_dump()
    except ValidationError as e:
        logger.warning("SerpAPI results failed validation: %s", e)
        return None


async def _search_via_gemini(
    origin: str,
    outbound_city: str,
    inbound_city: str,
    departure_date: str,
    return_date: str,
    traveler_count: int,
    planning_mode: str,
    max_options: int,
) -> dict | None:
    llm = get_gemini_model()
    llm_with_search = llm.bind_tools([get_search_grounding_tool()])

    prompt = (
        f"Search for flights for this trip:\n"
        f"- Origin: {origin}\n"
        f"- Outbound: {origin} -> {outbound_city} on {departure_date}\n"
        f"- Inbound: {inbound_city} -> {origin} on {return_date}\n"
        f"- Travelers: {traveler_count}\n"
        f"- Return up to {max_options} option(s) per direction\n"
        f"- Planning mode: {planning_mode}\n\n"
        f"Find real flight options using Google Search."
    )

    messages = [SystemMessage(content=FLIGHT_SEARCH_PROMPT), HumanMessage(content=prompt)]

    try:
        response = await llm_with_search.ainvoke(messages)
        parsed = extract_json_from_response(response.content)
        transport_plan = TransportPlan.model_validate(parsed)
        return transport_plan.model_dump()
    except Exception as e:
        logger.warning("Gemini flight search failed: %s", e)
        return None


async def flight_search_node(state: "TravelBlackboard") -> dict:
    """
    Search international flights (outbound + inbound).

    Tries SerpAPI Google Flights first for accurate data,
    falls back to Gemini grounding if SerpAPI unavailable or fails.
    """
    origin = state.get("origin") or "Singapore"
    destinations = sorted(
        state.get("destinations") or [], key=lambda d: d.get("order", 0)
    )
    planning_mode = state.get("planning_mode", "auto")
    max_options = state.get("planning_mode_max_options", 3)
    travel_dates = state.get("travel_dates") or {}
    traveler_count = state.get("traveler_count", 1)

    first_dest = destinations[0] if destinations else {"city": state.get("destination", ""), "country": ""}
    last_dest = destinations[-1] if destinations else first_dest

    outbound_city = first_dest.get("city") or ""
    inbound_city = last_dest.get("city") or ""
    departure_date = travel_dates.get("start", "")
    return_date = travel_dates.get("end", "")

    # Strategy 1: SerpAPI (real Google Flights data)
    result = await _search_via_serpapi(
        origin, outbound_city, inbound_city,
        departure_date, return_date, max_options,
    )
    if result:
        logger.info("Flight search: using SerpAPI results")
        return {"transport_plan": result}

    # Strategy 2: Gemini grounding fallback
    logger.info("Flight search: falling back to Gemini grounding")
    result = await _search_via_gemini(
        origin, outbound_city, inbound_city,
        departure_date, return_date, traveler_count,
        planning_mode, max_options,
    )
    if result:
        return {"transport_plan": result}

    return {
        "transport_plan": None,
        "critic_feedback": "Flight search failed with both SerpAPI and Gemini grounding",
    }
