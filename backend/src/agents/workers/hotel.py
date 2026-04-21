from datetime import date, timedelta

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from src.agents.llm import get_gemini_model
from src.prompts.hotel import HOTEL_SEARCH_PROMPT
from src.state.models import AccommodationPlan, CityAccommodation, HotelOption
from src.tools.grounding import extract_json_from_response, get_grounding_tool
from src.tools.places import USE_GOOGLE_PLACES, enrich_with_places_api, get_place_photo_url


def _calculate_total_nights(travel_dates: dict) -> int:
    """Calculate total nights from travel_dates dict with start/end keys."""
    start = date.fromisoformat(travel_dates["start"])
    end = date.fromisoformat(travel_dates["end"])
    return (end - start).days


async def _search_hotels_for_city(
    state: dict, dest: dict, llm_with_search, *, city_nights: int | None = None, checkin_date: str | None = None
) -> dict:
    """Search hotels for a single city. Returns CityAccommodation dict or empty options on failure."""
    city = dest.get("city") or "Unknown"
    country = dest.get("country") or ""
    city_label = f"{city}, {country}" if country else city

    travel_dates = state.get("travel_dates") or {}
    total_nights = city_nights or (_calculate_total_nights(travel_dates) if travel_dates else 7)
    checkin = checkin_date or travel_dates.get("start", "TBD")
    checkout = travel_dates.get("end", "TBD")
    traveler_count = state.get("traveler_count", 1)
    room_sharing = state.get("room_sharing") or "not specified"
    bed_type_preference = state.get("bed_type_preference") or "not specified"
    max_options = state.get("planning_mode_max_options") or 3
    planning_mode = state.get("planning_mode") or "auto"

    # auto: 1 best option; choose: max_options
    num_options = max_options if planning_mode == "choose" else 1

    user_prompt = f"""Search for hotels in {city_label}:
- Check-in: {checkin}
- Check-out: {checkout}
- Total nights: {total_nights}
- Travelers: {traveler_count}
- Room sharing preference: {room_sharing}
- Bed type preference: {bed_type_preference}
- Return {num_options} hotel option(s)

Find real hotels matching these parameters. Respond with JSON only."""

    messages = [
        SystemMessage(content=HOTEL_SEARCH_PROMPT),
        HumanMessage(content=user_prompt),
    ]
    result = await llm_with_search.ainvoke(messages)
    response_text = result.content

    parsed = extract_json_from_response(response_text)
    parsed["nights"] = city_nights
    city_accommodation = CityAccommodation.model_validate(parsed)
    result = city_accommodation.model_dump()

    # Enrich with Places API: place_id, address, lat/lng, photos
    if USE_GOOGLE_PLACES:
        for opt in result.get("options", []):
            name = opt.get("name", "")
            if name and not opt.get("place_id"):
                enrichment = await enrich_with_places_api(name, city)
                if enrichment:
                    opt.update(enrichment)
            if opt.get("place_id") and not opt.get("image_url"):
                photo = await get_place_photo_url(opt["place_id"])
                if photo:
                    opt["image_url"] = photo

    return result


async def hotel_search_node(state: dict) -> dict:
    """
    Search hotels for all destinations, return AccommodationPlan.
    """
    llm = get_gemini_model()
    llm_with_search = llm.bind_tools([get_grounding_tool()])

    # Backward compat: support single destination field
    destinations = state.get("destinations") or []
    if not destinations and state.get("destination"):
        destinations = [{"city": state["destination"], "country": "", "order": 1}]

    destinations = sorted(destinations, key=lambda d: d.get("order", 0))

    # Allocate nights per city for multi-city trips
    travel_dates = state.get("travel_dates") or {}
    total_nights = _calculate_total_nights(travel_dates) if travel_dates else 7
    num_cities = len(destinations) or 1
    base_nights = total_nights // num_cities
    remainder = total_nights % num_cities
    # Distribute remainder to earlier cities
    nights_per_city = [base_nights + (1 if i < remainder else 0) for i in range(num_cities)]

    # Calculate per-city check-in dates
    checkin_dates: list[str] = []
    if travel_dates.get("start"):
        current = date.fromisoformat(travel_dates["start"])
        for n in nights_per_city:
            checkin_dates.append(current.isoformat())
            current = current + timedelta(days=n)
    else:
        checkin_dates = ["TBD"] * num_cities

    try:
        cities_list = []
        for i, dest in enumerate(destinations):
            city_dict = await _search_hotels_for_city(
                state, dest, llm_with_search,
                city_nights=nights_per_city[i] if i < len(nights_per_city) else base_nights,
                checkin_date=checkin_dates[i] if i < len(checkin_dates) else None,
            )
            cities_list.append(city_dict)

        accommodation_plan = AccommodationPlan(
            cities=[CityAccommodation.model_validate(c) for c in cities_list]
        )
        return {"accommodation_plan": accommodation_plan.model_dump()}

    except (ValidationError, Exception) as e:
        return {
            "accommodation_plan": None,
            "critic_feedback": f"Hotel search validation failed: {e}",
        }
