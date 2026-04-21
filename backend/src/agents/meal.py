import json
import logging

from src.agents.llm import get_gemini_model
from src.db.repository import meal_cache_lookup, meal_cache_save
from src.prompts.meal import MEAL_SEARCH_PROMPT
from src.state.models import MealOption, MealSlotOptions
from src.tools.grounding import extract_json_from_response, get_maps_grounding_tool
from src.tools.places import enrich_with_places_api, get_place_photo_url
from src.utils import haversine

logger = logging.getLogger(__name__)

# Minimum cached meals per slot to skip LLM
_MIN_CACHED_MEALS_PER_SLOT = 4

# Minimum proximity score for a cached meal to be usable
_MIN_PROXIMITY_SCORE = 0.15


def _proximity_score(
    restaurant_lat: float | None,
    restaurant_lng: float | None,
    activity_coords: list[tuple[float, float]],
) -> float:
    """
    Score a restaurant by proximity to the nearest activity.

    Uses hyperbolic decay: score = 1 / (1 + distance_km / 2).
    If restaurant or all activities lack coords, returns 0.5 (neutral).
    """
    if restaurant_lat is None or restaurant_lng is None or not activity_coords:
        return 0.5  # neutral — let it through but don't prioritise

    min_dist = min(
        haversine(restaurant_lat, restaurant_lng, alat, alng)
        for alat, alng in activity_coords
    )
    return 1.0 / (1.0 + min_dist / 2.0)


def _get_activity_coords_for_day(state: dict, day_number: int) -> list[tuple[float, float]]:
    """
    Extract (lat, lng) pairs from activities on a given day.
    """
    activities_plan = state.get("activities_plan") or {}
    coords: list[tuple[float, float]] = []
    day_counter = 0
    for city_data in activities_plan.get("cities", []):
        for day_options in city_data.get("options_per_day", []):
            day_counter += 1
            if day_counter != day_number:
                continue
            for act in day_options if isinstance(day_options, list) else []:
                if isinstance(act, dict) and act.get("lat") and act.get("lng"):
                    coords.append((act["lat"], act["lng"]))
    return coords


def _try_cached_meals(
    state: dict,
    city: str,
    day_number: int,
    meal_type: str,
    meal_preferences: str,
) -> list[dict] | None:
    """
    Attempt to serve a meal slot from cache. Returns scored options or None if insufficient.
    """
    candidates = meal_cache_lookup(city, meal_type, meal_preferences)
    if not candidates:
        return None

    activity_coords = _get_activity_coords_for_day(state, day_number)

    scored: list[tuple[float, dict]] = []
    for entry in candidates:
        score = _proximity_score(entry["lat"], entry["lng"], activity_coords)
        if score >= _MIN_PROXIMITY_SCORE:
            opt = entry["meal_option"]
            opt["worth_the_travel"] = (
                score < 0.5
                and entry["lat"] is not None
                and len(activity_coords) > 0
            )
            scored.append((score, opt))

    scored.sort(key=lambda x: x[0], reverse=True)

    if len(scored) < _MIN_CACHED_MEALS_PER_SLOT:
        return None

    return [opt for _, opt in scored[:5]]


def _normalize_preferences(prefs: str) -> str:
    """
    Normalize meal preferences for consistent cache keys.

    Lowercases, splits on comma, strips whitespace, sorts alphabetically.
    "halal, no pork, vegetarian" and "No Pork, Halal, Vegetarian" -> "halal,no pork,vegetarian"
    """
    keywords = sorted(k.strip().lower() for k in prefs.split(",") if k.strip())
    return ",".join(keywords) if keywords else ""


def _build_activities_by_day(state: dict) -> str:
    """
    Build a per-day activity summary for meal proximity context.
    """
    activities_plan = state.get("activities_plan") or {}
    days_summary = []

    for city_data in activities_plan.get("cities", []):
        city = city_data.get("city", "Unknown")
        for day_idx, day_options in enumerate(
            city_data.get("options_per_day", [])
        ):
            day_num = day_idx + 1
            names = [
                a.get("name", "") for a in day_options if isinstance(a, dict)
            ]
            areas = [
                a.get("address", "")
                for a in day_options
                if isinstance(a, dict) and a.get("address")
            ]
            days_summary.append(
                f"Day {day_num} ({city}): {', '.join(names[:5])}"
                + (f" | Area: {areas[0]}" if areas else "")
            )

    return "\n".join(days_summary) if days_summary else "No activities planned"


def _get_city_for_day(state: dict, day_number: int) -> str:
    """Get the city name for a given day number from activities_plan."""
    activities_plan = state.get("activities_plan") or {}
    day_counter = 0
    for city_data in activities_plan.get("cities", []):
        city = city_data.get("city", "Unknown")
        for _ in city_data.get("options_per_day", []):
            day_counter += 1
            if day_counter == day_number:
                return city
    return ""


async def meal_generation_node(state: dict) -> dict:
    """
    Generate location-aware meal options grouped by day.

    First checks the meal cache for proximity-scored matches. For any slot
    with enough cached options (>= 4 above score threshold), skips the LLM.
    Remaining slots are filled via Gemini + Maps grounding, then cached.
    Fail-open: returns empty on error.
    """
    destinations = state.get("destinations") or []
    meal_preferences_list = state.get("meal_preferences") or []
    meal_preferences_raw = ", ".join(meal_preferences_list) if meal_preferences_list else "local cuisine"
    meal_preferences_str = _normalize_preferences(meal_preferences_raw)
    traveler_count = state.get("traveler_count") or 1

    # Determine how many days and which meal types we need
    activities_plan = state.get("activities_plan") or {}
    total_days = sum(
        len(city_data.get("options_per_day", []))
        for city_data in activities_plan.get("cities", [])
    )
    if total_days == 0:
        return {"meal_options": []}

    # Build list of (day_number, meal_type, city) slots needed
    slots_needed: list[tuple[int, str, str]] = []
    day_counter = 0
    for city_data in activities_plan.get("cities", []):
        city = city_data.get("city", "Unknown")
        for _ in city_data.get("options_per_day", []):
            day_counter += 1
            slots_needed.append((day_counter, "lunch", city))
            slots_needed.append((day_counter, "dinner", city))

    # Phase 1: Try cache for each slot
    cached_slots: list[dict] = []
    uncached_slots: list[tuple[int, str, str]] = []

    for day_num, meal_type, city in slots_needed:
        cached_options = _try_cached_meals(
            state, city, day_num, meal_type, meal_preferences_str,
        )
        if cached_options:
            logger.info("Meal cache HIT: day=%d %s in %s (%d options)", day_num, meal_type, city, len(cached_options))
            cached_slots.append(
                MealSlotOptions(
                    day_number=day_num,
                    meal_type=meal_type,
                    options=cached_options,
                ).model_dump()
            )
        else:
            uncached_slots.append((day_num, meal_type, city))

    # Phase 2: If all slots served from cache, skip LLM entirely
    if not uncached_slots:
        logger.info("All meal slots served from cache — skipping LLM")
        return {"meal_options": cached_slots}

    # Phase 3: Run LLM for remaining slots
    logger.info("Meal cache: %d slots cached, %d slots need LLM",len(cached_slots), len(uncached_slots),)

    prompt = (
        MEAL_SEARCH_PROMPT
        .replace("{DESTINATIONS}", json.dumps(destinations))
        .replace("{ACTIVITIES_BY_DAY}", _build_activities_by_day(state))
        .replace("{MEAL_PREFERENCES}", meal_preferences_raw)
        .replace("{TRAVELER_COUNT}", str(traveler_count))
    )

    try:
        llm = get_gemini_model()
        llm_with_maps = llm.bind_tools([get_maps_grounding_tool()])
        response = await llm_with_maps.ainvoke(prompt)
        raw = extract_json_from_response(response.content)
    except Exception:
        logger.warning("Meal generation: LLM call failed", exc_info=True)
        return {"meal_options": cached_slots}  # return whatever we got from cache

    # Validate and enrich LLM results
    llm_slots: list[dict] = []
    _bad_names = {"unknown", "unknown restaurant", "tbd", "n/a", ""}
    for slot_data in raw.get("meal_slots", []):
        try:
            options = []
            for opt in slot_data.get("options", []):
                name = (opt.get("name") or "").strip()
                if name.lower() in _bad_names:
                    continue  # Skip placeholder names
                options.append(MealOption(**opt).model_dump())
            slot = MealSlotOptions(
                day_number=slot_data.get("day_number", 0),
                meal_type=slot_data.get("meal_type", "lunch"),
                options=options,
            )
            llm_slots.append(slot.model_dump())
        except Exception:
            continue  # Skip malformed slots

    # Enrich with Places API: place_id, address, lat/lng, photos
    for slot in llm_slots:
        city = _get_city_for_day(state, slot.get("day_number", 0))
        for opt in slot.get("options", []):
            name = opt.get("name", "")
            if name and not opt.get("place_id"):
                enrichment = await enrich_with_places_api(name, city)
                if enrichment:
                    opt.update(enrichment)

            if opt.get("place_id") and not opt.get("image_url"):
                try:
                    photo_url = await get_place_photo_url(opt["place_id"])
                    if photo_url:
                        opt["image_url"] = photo_url
                except Exception:
                    pass

        # Save enriched LLM results to cache
        meal_cache_save(
            city=city,
            day_number=slot.get("day_number", 0),
            meal_type=slot.get("meal_type", "lunch"),
            meal_preferences=meal_preferences_str,
            meal_options=slot.get("options", []),
        )

    # Filter LLM slots to only those not already served from cache
    cached_keys = {(s["day_number"], s["meal_type"]) for s in cached_slots}
    new_llm_slots = [
        s for s in llm_slots
        if (s["day_number"], s["meal_type"]) not in cached_keys
    ]

    return {"meal_options": cached_slots + new_llm_slots}
