from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from src.agents.llm import get_gemini_model
from src.prompts.activities import ACTIVITIES_SEARCH_PROMPT
from src.state.models import ActivitiesPlan, ActivityOption, CityActivities
from src.tools.grounding import (
    extract_json_from_response,
    get_maps_grounding_tool,
)
from src.tools.places import USE_GOOGLE_PLACES, enrich_with_places_api, get_place_photo_url

import logging
logger = logging.getLogger(__name__)

# Minimum activities per day per city to consider cache sufficient
_MIN_ACTIVITIES_PER_DAY = 5


def _cache_sufficient(
    cached: dict | None,
    destinations: list[dict],
    day_allocation: list[int],
    min_per_day: int = _MIN_ACTIVITIES_PER_DAY,
) -> bool:
    """
    Check if cached activities cover every city/day with at least min_per_day activities.
    """
    if not cached or not isinstance(cached, dict):
        return False

    cached_by_city: dict[str, list] = {}
    for city_data in cached.get("cities", []):
        if not isinstance(city_data, dict):
            continue
        city_key = city_data.get("city", "").lower().strip()
        if city_key:
            cached_by_city[city_key] = city_data.get("options_per_day", [])

    for i, dest in enumerate(destinations):
        city_key = (dest.get("city") or "").lower().strip()
        if not city_key:
            return False
        cached_days = cached_by_city.get(city_key)
        if not cached_days:
            return False
        needed_days = day_allocation[i] if i < len(day_allocation) else 1
        if len(cached_days) < needed_days:
            return False
        for day_idx in range(needed_days):
            day_opts = cached_days[day_idx]
            if not isinstance(day_opts, list) or len(day_opts) < min_per_day:
                return False

    return True


def _calculate_trip_days(travel_dates: dict) -> int:
    """
    Calculate trip duration in days. Returns 5 as default if dates absent.
    """
    start_str = travel_dates.get("start")
    end_str = travel_dates.get("end")
    if not start_str or not end_str:
        return 5
    return (date.fromisoformat(end_str) - date.fromisoformat(start_str)).days


async def _search_activities_for_city(
    state: dict, dest: dict, city_trip_days: int, llm_with_search
) -> dict:
    """
    Search activities for a single city.
    Returns CityActivities dict or empty options on failure.
    """
    city = dest.get("city") or "Unknown"
    country = dest.get("country") or ""
    city_label = f"{city}, {country}" if country else city

    activity_intensity = state.get("activity_intensity") or "moderate"
    trip_style = state.get("trip_style") or "mixed"
    preferences = state.get("preferences") or []
    additional_preferences = state.get("additional_preferences") or []
    max_options = state.get("planning_mode_max_options") or 3
    planning_mode = state.get("planning_mode") or "auto"

    # auto: 1 best option per slot; choose: max_options
    num_options = max_options if planning_mode == "choose" else 1

    prefs_str = ", ".join(preferences + additional_preferences) or "general sightseeing"

    # Build cached activities dedup instruction if available
    cached_activities = state.get("cached_activities")
    cached_names: list[str] = []
    if cached_activities and isinstance(cached_activities, dict):
        for city_data in cached_activities.get("cities", []):
            if not isinstance(city_data, dict):
                continue
            if city_data.get("city", "").lower().strip() != city.lower().strip():
                continue
            for day_options in city_data.get("options_per_day", []):
                if isinstance(day_options, list):
                    for act in day_options:
                        name = act.get("name") if isinstance(act, dict) else None
                        if name:
                            cached_names.append(name)

    cached_section = ""
    if cached_names:
        names_list = ", ".join(cached_names)
        cached_section = (
            f"\n\nThe following activities are already known from a previous search "
            f"and MUST NOT appear in your results. Find DIFFERENT alternatives instead:\n"
            f"{names_list}"
        )

    user_prompt = f"""Search for activities in {city_label}:
- Trip duration: {city_trip_days} day(s)
- Trip style: {trip_style}
- Activity intensity: {activity_intensity}
- Preferences: {prefs_str}
- Return {num_options} option(s) per day slot

Find real attractions and experiences (NO restaurants — meals are separate). Respond with JSON only.{cached_section}"""

    messages = [
        SystemMessage(content=ACTIVITIES_SEARCH_PROMPT),
        HumanMessage(content=user_prompt),
    ]
    result = await llm_with_search.ainvoke(messages)
    response_text = result.content

    parsed = extract_json_from_response(response_text)

    # grounding audit logging
    _raw_activities = parsed.get("options_per_day", [])
    _flat_activities = [a for day in _raw_activities if isinstance(day, list) for a in day]

    parsed["trip_days"] = city_trip_days  # Enforce correct value (LLM may return wrong)

    # Filter out restaurants/dining that LLM or cache may have included
    _RESTAURANT_KEYWORDS = {"restaurant", "cafe", "café", "food court", "eatery", "dining", "bistro", "hawker"}
    for day_opts in parsed.get("options_per_day", []):
        if isinstance(day_opts, list):
            day_opts[:] = [
                a for a in day_opts
                if not (isinstance(a, dict) and (
                    a.get("category", "").lower() in ("restaurant", "food", "dining")
                    or any(kw in (a.get("name") or "").lower() for kw in _RESTAURANT_KEYWORDS)
                ))
            ]

    city_activities = CityActivities.model_validate(parsed)

    if USE_GOOGLE_PLACES:
        enriched_options_per_day = []
        for day_options in city_activities.options_per_day:
            enriched_day = []
            for activity in day_options:
                activity_dict = activity.model_dump()
                enrichment = await enrich_with_places_api(activity.name, city)
                if enrichment:
                    activity_dict.update(enrichment)
                # Fetch photo if we got a place_id
                pid = activity_dict.get("place_id")
                if pid and not activity_dict.get("image_url"):
                    photo = await get_place_photo_url(pid)
                    if photo:
                        activity_dict["image_url"] = photo
                enriched_day.append(activity_dict)
            enriched_options_per_day.append(enriched_day)
        city_activities = CityActivities(
            city=city_activities.city,
            trip_days=city_activities.trip_days,
            options_per_day=[
                [type(a)(**a) if not isinstance(a, dict) else a for a in day]
                for day in enriched_options_per_day
            ],
        )
        return {
            "city": city_activities.city,
            "trip_days": city_activities.trip_days,
            "options_per_day": enriched_options_per_day,
        }

    return city_activities.model_dump()


# Capital / major hub cities typically have more attractions and warrant extra days
_MAJOR_DESTINATION_CITIES = {
    "tokyo", "paris", "london", "new york", "rome", "barcelona",
    "istanbul", "bangkok", "dubai", "sydney", "hong kong", "singapore",
    "berlin", "amsterdam", "prague", "vienna", "seoul", "taipei",
    "los angeles", "san francisco", "chicago", "mumbai", "delhi",
    "cairo", "marrakech", "rio de janeiro", "buenos aires",
}


def _allocate_days_weighted(destinations: list[dict], total_trip_days: int) -> list[int]:
    """Weighted day allocation across cities based on destination characteristics.

    Major cities get a 1.5x weight. Remaining days distributed proportionally.
    Ensures every city gets at least 1 day. Transit days (1 per city transition)
    are subtracted from the pool first.
    """
    num_cities = len(destinations)
    if num_cities == 0:
        return []
    if num_cities == 1:
        return [total_trip_days]

    # Reserve transit days (1 day per city transition for multi-city trips)
    transit_days = num_cities - 1
    available_days = max(num_cities, total_trip_days - transit_days)

    # Compute weights: major cities get 1.5x, others get 1.0x
    weights: list[float] = []
    for dest in destinations:
        city_lower = (dest.get("city") or "").lower().strip()
        weight = 1.5 if city_lower in _MAJOR_DESTINATION_CITIES else 1.0
        weights.append(weight)

    # First and last cities get a small boost (arrival/departure buffer)
    weights[0] *= 1.1
    weights[-1] *= 1.1

    total_weight = sum(weights)
    # Floor allocation first, then distribute remainder by highest fractional part
    raw_fractions = [available_days * w / total_weight for w in weights]
    raw_alloc = [max(1, int(f)) for f in raw_fractions]

    # Distribute remaining days to cities with highest fractional part
    remainder = available_days - sum(raw_alloc)
    if remainder > 0:
        fractional_parts = [(raw_fractions[i] - raw_alloc[i], i) for i in range(num_cities)]
        fractional_parts.sort(reverse=True)
        for _, idx in fractional_parts[:remainder]:
            raw_alloc[idx] += 1

    return raw_alloc


def _merge_cached_activities(cached: dict | None, fresh: ActivitiesPlan) -> ActivitiesPlan:
    """Merge cached activities into fresh search results.

    For each city present in both cached and fresh plans, prepend cached options
    to each day's options list (cached first, then fresh). This ensures cached
    activities are preserved while fresh results fill any gaps.
    """
    if not cached or not isinstance(cached, dict):
        return fresh

    cached_by_city: dict[str, list[list[dict]]] = {}
    for city_data in cached.get("cities", []):
        if not isinstance(city_data, dict):
            continue
        city_key = city_data.get("city", "").lower().strip()
        if city_key:
            cached_by_city[city_key] = city_data.get("options_per_day", [])

    if not cached_by_city:
        return fresh

    merged_cities: list[CityActivities] = []
    for city_act in fresh.cities:
        city_key = city_act.city.lower().strip()
        cached_days = cached_by_city.get(city_key)
        if not cached_days:
            merged_cities.append(city_act)
            continue

        merged_days: list[list[ActivityOption]] = []
        for day_idx in range(city_act.trip_days):
            fresh_opts = city_act.options_per_day[day_idx] if day_idx < len(
                city_act.options_per_day
            ) else []
            cached_opts_raw = cached_days[day_idx] if day_idx < len(cached_days) else []

            # Parse cached options into ActivityOption
            cached_opts: list[ActivityOption] = []
            for opt in cached_opts_raw:
                if isinstance(opt, dict):
                    try:
                        cached_opts.append(ActivityOption.model_validate(opt))
                    except Exception:
                        continue

            # Cached first, then fresh (dedup by name)
            seen_names: set[str] = set()
            combined: list[ActivityOption] = []
            for opt in cached_opts:
                key = opt.name.lower().strip()
                if key not in seen_names:
                    seen_names.add(key)
                    combined.append(opt)
            for opt in fresh_opts:
                key = opt.name.lower().strip()
                if key not in seen_names:
                    seen_names.add(key)
                    combined.append(opt)

            merged_days.append(combined)

        merged_cities.append(CityActivities(
            city=city_act.city,
            trip_days=city_act.trip_days,
            options_per_day=merged_days,
        ))

    return ActivitiesPlan(cities=merged_cities)


async def activities_search_node(state: dict) -> dict:
    """
    Search activities for all destinations, return ActivitiesPlan.

    Days allocated using weighted scheme — major cities get proportionally more days.
    Returns activities_plan on success, None + critic_feedback on failure.
    """
    # Backward compat: support single destination field
    destinations = state.get("destinations") or []
    if not destinations and state.get("destination"):
        destinations = [{"city": state["destination"], "country": "", "order": 1}]

    destinations = sorted(destinations, key=lambda d: d.get("order", 0))

    travel_dates = state.get("travel_dates") or {}
    total_trip_days = _calculate_trip_days(travel_dates)
    activity_intensity = state.get("activity_intensity") or "moderate"

    day_allocation = _allocate_days_weighted(destinations, total_trip_days, activity_intensity)

    # Short-circuit: skip LLM if cache has enough activities for every city/day
    cached = state.get("cached_activities")
    if cached and _cache_sufficient(cached, destinations, day_allocation):
        logger.info("Cache sufficient, skipping activities LLM call")
        return {"activities_plan": cached}

    llm = get_gemini_model()
    llm_with_search = llm.bind_tools([get_maps_grounding_tool()])

    try:
        cities_list = []
        for i, dest in enumerate(destinations):
            city_days = day_allocation[i] if i < len(day_allocation) else 1

            city_dict = await _search_activities_for_city(state, dest, city_days, llm_with_search)
            cities_list.append(city_dict)

        activities_plan = ActivitiesPlan(
            cities=[CityActivities.model_validate(c) for c in cities_list]
        )
        merged = _merge_cached_activities(state.get("cached_activities"), activities_plan)
        return {"activities_plan": merged.model_dump()}

    except (ValidationError, Exception) as e:
        return {
            "activities_plan": None,
            "critic_feedback": f"Activities search failed: {e}",
        }
