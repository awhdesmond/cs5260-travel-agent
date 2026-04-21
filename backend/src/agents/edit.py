import asyncio
import json
import logging

from src.agents.llm import get_gemini_model
from src.prompts.edit import EDIT_ITINERARY_PROMPT
from src.state.models import DailySchedule
from src.tools.grounding import extract_json_from_response, get_grounding_tool
from src.utils import parse_duration_minutes
from src.agents.workers.flight import flight_search_node
from src.agents.workers.transport import intercity_transport_node


logger = logging.getLogger(__name__)

# Keywords that trigger grounding (need to search for real venues)
_GROUNDING_KEYWORDS = {
    "restaurant", "cafe", "bar", "food", "eat", "meal", "lunch", "dinner",
    "breakfast", "activity", "attraction", "museum", "temple", "shrine",
    "hotel", "place", "visit", "go to", "replace", "swap", "change to",
}


def _needs_grounding(edit_request: str) -> bool:
    """
    Check if the edit request involves finding a real venue.
    """
    lower = edit_request.lower()
    return any(kw in lower for kw in _GROUNDING_KEYWORDS)


def _extract_itinerary_shape(itinerary: dict) -> dict:
    """
    Extract date/city shape from an itinerary for change detection.
    """
    days = itinerary.get("days", [])
    cities: list[str] = []
    first_date: str | None = None
    last_date: str | None = None

    for i, day in enumerate(days):
        d = day if isinstance(day, dict) else {}
        day_date = d.get("date")
        if i == 0 and day_date:
            first_date = day_date
        if day_date:
            last_date = day_date

        city = d.get("city") or d.get("location") or ""
        if city and (not cities or cities[-1] != city):
            cities.append(city)

    return {
        "day_count": len(days),
        "first_date": first_date,
        "last_date": last_date,
        "cities": cities,
        "first_city": cities[0] if cities else None,
        "last_city": cities[-1] if cities else None,
    }


def _detect_transport_changes(old_shape: dict, new_shape: dict) -> dict:
    """
    Compare old vs new itinerary shape to determine which workers to re-run.
    """
    rerun_flights = False
    rerun_intercity = False

    # Flight triggers: date or first/last city changed
    if old_shape["first_date"] != new_shape["first_date"]:
        rerun_flights = True
    if old_shape["last_date"] != new_shape["last_date"]:
        rerun_flights = True
    if old_shape["first_city"] != new_shape["first_city"]:
        rerun_flights = True
    if old_shape["last_city"] != new_shape["last_city"]:
        rerun_flights = True
    if old_shape["day_count"] != new_shape["day_count"]:
        rerun_flights = True

    # Intercity triggers: city sequence changed
    if old_shape["cities"] != new_shape["cities"]:
        rerun_intercity = True

    return {"rerun_flights": rerun_flights, "rerun_intercity": rerun_intercity}





def _pick_best_flight(new_options: list[dict], old_flight: dict | None) -> dict | None:
    """
    Pick the flight most similar to the previous selection.

    With old flight — match its character (airline, stops, duration, price).
    Without old flight — trust the input order (Google's ranking) but penalize
    excessive stops.
    """
    if not new_options:
        return None
    if not old_flight:
        # No old flight: trust Google's ranking (best_flights first),
        # but skip anything with 3+ stops
        for f in new_options:
            if f.get("stops", 0) <= 1:
                return f
        return new_options[0]  # fallback to first if all have 2+ stops

    old_airline = (old_flight.get("airline") or "").lower()
    old_price = old_flight.get("price_sgd", 0)
    old_stops = old_flight.get("stops", 0)
    old_dur = parse_duration_minutes(old_flight.get("duration"))

    def score(f: dict) -> float:
        s = 0.0
        # 1. Airline match (strongest signal)
        if (f.get("airline") or "").lower() != old_airline:
            s += 2000
        # 2. Stops difference (500 per extra stop)
        s += abs(f.get("stops", 0) - old_stops) * 500
        # 3. Duration similarity (1 point per minute difference)
        if old_dur > 0:
            s += abs(parse_duration_minutes(f.get("duration")) - old_dur)
        # 4. Price similarity (1 point per SGD difference)
        if old_price > 0:
            s += abs(f.get("price_sgd", 0) - old_price)
        return s

    return min(new_options, key=score)


def _pick_best_intercity(new_options: list[dict], old_option: dict | None) -> dict | None:
    """
    Pick the intercity option most similar to the previous selection.

    Priority: same mode > same operator > closest price.
    """
    if not new_options:
        return None
    if not old_option:
        return min(new_options, key=lambda o: o.get("price_sgd", float("inf")))

    old_mode = (old_option.get("mode") or "").lower()
    old_operator = (old_option.get("operator") or "").lower()
    old_price = old_option.get("price_sgd", 0)

    def score(o: dict) -> float:
        mode_match = 0 if (o.get("mode") or "").lower() == old_mode else 2000
        op_match = 0 if (o.get("operator") or "").lower() == old_operator else 500
        price_diff = abs(o.get("price_sgd", 0) - old_price)
        return mode_match + op_match + price_diff

    return min(new_options, key=score)


async def _rerun_transport(plan_state: dict, new_shape: dict, changes: dict) -> dict:
    """
    Re-run flight/intercity workers and auto-select best options.

    Returns dict with updated transport fields to merge into plan_state.
    """

    # Build a minimal state for workers with updated dates/destinations
    worker_state = {**plan_state}

    # Update travel dates from new itinerary
    if new_shape["first_date"] and new_shape["last_date"]:
        worker_state["travel_dates"] = {
            "start": new_shape["first_date"],
            "end": new_shape["last_date"],
        }
    elif not worker_state.get("travel_dates"):
        # Fallback: keep old dates if new itinerary has no date fields
        logger.warning("Edited itinerary missing date fields; using original travel_dates")

    # Update destinations from new city sequence, preserving country from original
    if new_shape["cities"]:
        # Build city->country lookup from original destinations
        old_dests = plan_state.get("destinations") or []
        country_map = {
            d.get("city", ""): d.get("country", "")
            for d in old_dests if isinstance(d, dict)
        }
        worker_state["destinations"] = [
            {"city": city, "country": country_map.get(city, ""), "order": i + 1}
            for i, city in enumerate(new_shape["cities"])
        ]

    # Use "choose" mode to get multiple options for best-match selection
    worker_state["planning_mode"] = "choose"
    worker_state["planning_mode_max_options"] = 5

    # Preserve old selections for similarity matching
    old_transport = plan_state.get("transport_plan") or {}
    old_outbound = (old_transport.get("outbound_flights") or [None])[0]
    old_inbound = (old_transport.get("inbound_flights") or [None])[0]
    old_intercity = plan_state.get("intercity_transport_plan") or {}

    updates: dict = {}
    tasks = []

    if changes["rerun_flights"]:
        tasks.append(("flights", flight_search_node(worker_state)))
    if changes["rerun_intercity"]:
        tasks.append(("intercity", intercity_transport_node(worker_state)))

    if not tasks:
        return updates

    logger.info("Re-running transport workers after edit: %s", [t[0] for t in tasks])

    results = await asyncio.gather(
        *[t[1] for t in tasks],
        return_exceptions=True,
    )

    for (name, _), result in zip(tasks, results):
        if isinstance(result, Exception):
            logger.error("Transport re-search %s failed: %s", name, result)
            continue

        if name == "flights" and isinstance(result, dict):
            transport = result.get("transport_plan")
            if transport and isinstance(transport, dict):
                # Auto-select best match per direction
                outbound = transport.get("outbound_flights", [])
                inbound = transport.get("inbound_flights", [])
                best_out = _pick_best_flight(outbound, old_outbound)
                best_in = _pick_best_flight(inbound, old_inbound)
                transport["outbound_flights"] = [best_out] if best_out else []
                transport["inbound_flights"] = [best_in] if best_in else []
                updates["transport_plan"] = transport
                logger.info(
                    "Flights updated: outbound=%s, inbound=%s",
                    best_out.get("airline") if best_out else None,
                    best_in.get("airline") if best_in else None,
                )

        elif name == "intercity" and isinstance(result, dict):
            intercity = result.get("intercity_transport_plan")
            if intercity and isinstance(intercity, dict):
                # Auto-select best match per hop
                for hop in intercity.get("hops", []):
                    hop_key = f"{hop.get('from_city', '')}->{hop.get('to_city', '')}"
                    options = hop.get("options", [])
                    # Find old option for this hop
                    old_hop_opt = None
                    for old_hop in old_intercity.get("hops", []):
                        old_key = f"{old_hop.get('from_city', '')}->{old_hop.get('to_city', '')}"
                        if old_key == hop_key and old_hop.get("options"):
                            old_hop_opt = old_hop["options"][0]
                            break
                    best = _pick_best_intercity(options, old_hop_opt)
                    hop["options"] = [best] if best else []
                updates["intercity_transport_plan"] = intercity
                logger.info("Intercity transport updated: %d hops", len(intercity.get("hops", [])))

    return updates


async def edit_itinerary_node(itinerary: dict, edit_request: str) -> dict:
    """
    Apply a minor edit to the existing itinerary via LLM.

    For venue-related edits (swap restaurant, change activity), uses Google Search
    grounding to find real alternatives. For time adjustments, uses plain LLM.

    Returns updated itinerary dict, or original on any error (fail-open).
    """
    prompt = (
        EDIT_ITINERARY_PROMPT
        .replace("{ITINERARY_JSON}", json.dumps(itinerary, indent=2))
        .replace("{EDIT_REQUEST}", edit_request)
    )

    try:
        llm = get_gemini_model()
        if _needs_grounding(edit_request):
            llm_bound = llm.bind_tools([get_grounding_tool()])
        else:
            llm_bound = llm

        response = await llm_bound.ainvoke(prompt)
        raw = extract_json_from_response(response.content)

        # Validate with Pydantic
        schedule = DailySchedule.model_validate(raw)

        logger.info("Itinerary edit applied: %s (grounding=%s)", edit_request[:80], _needs_grounding(edit_request))

        return schedule.model_dump()
    except Exception as e:
        logger.warning("Edit failed (keeping original): %s", str(e)[:200])
        return itinerary  # Fail-open: return original
