import json
import logging
from datetime import date as _date, timedelta as _timedelta

from pydantic import ValidationError

from src.agents.llm import get_gemini_model
from src.db.repository import cache_lookup, cache_save
from src.prompts.day_planner_single_day import SINGLE_DAY_PLANNER_PROMPT
from src.state.models import DayPlan
from src.tools.grounding import extract_json_from_response
from src.utils import haversine
from src.tools.grounding import normalize_content

logger = logging.getLogger(__name__)


def _build_coord_lookup(state: dict) -> dict[str, dict]:
    """Build name->coords lookup from state (activities, hotels, meals).

    Used to enrich each day's time_slots during progressive streaming so the
    map has pins before the complete event.
    """
    lookup: dict[str, dict] = {}

    ap = state.get("activities_plan")
    if isinstance(ap, dict):
        for city_data in ap.get("cities", []):
            if not isinstance(city_data, dict):
                continue
            for day_opts in city_data.get("options_per_day", []):
                if not isinstance(day_opts, list):
                    continue
                for act in day_opts:
                    if not isinstance(act, dict):
                        continue
                    name = (act.get("name") or "").lower().strip()
                    if name and act.get("lat") and act.get("lng"):
                        lookup[name] = {
                            "lat": act["lat"], "lng": act["lng"],
                            "image_url": act.get("image_url"),
                            "place_id": act.get("place_id"),
                            "address": act.get("address"),
                        }

    acc = state.get("accommodation_plan")
    if isinstance(acc, dict):
        for city_data in acc.get("cities", []):
            if not isinstance(city_data, dict):
                continue
            for h in city_data.get("options", []):
                if not isinstance(h, dict):
                    continue
                name = (h.get("name") or "").lower().strip()
                if name and h.get("lat") and h.get("lng") and name not in lookup:
                    lookup[name] = {
                        "lat": h["lat"], "lng": h["lng"],
                        "image_url": h.get("image_url"),
                        "place_id": h.get("place_id"),
                        "address": h.get("address"),
                    }

    for meal_slot in (state.get("meal_options") or []):
        if not isinstance(meal_slot, dict):
            continue
        for opt in meal_slot.get("options", []):
            if not isinstance(opt, dict):
                continue
            name = (opt.get("name") or "").lower().strip()
            if name and opt.get("lat") and opt.get("lng") and name not in lookup:
                lookup[name] = {
                    "lat": opt["lat"], "lng": opt["lng"],
                    "image_url": opt.get("image_url"),
                    "place_id": opt.get("place_id"),
                    "address": opt.get("address"),
                }

    for sel in (state.get("selected_meals") or []):
        if not isinstance(sel, dict):
            continue
        s = sel.get("selected")
        if isinstance(s, dict):
            name = (s.get("name") or "").lower().strip()
            if name and s.get("lat") and s.get("lng") and name not in lookup:
                lookup[name] = {
                    "lat": s["lat"], "lng": s["lng"],
                    "image_url": s.get("image_url"),
                    "place_id": s.get("place_id"),
                    "address": s.get("address"),
                }

    return lookup


def _fuzzy_lookup(name: str, lookup: dict[str, dict]) -> dict | None:
    """Return coords from lookup for name, using exact then substring matching.

    Exact match is tried first. If that fails, we check whether any lookup key
    is a substring of name or vice-versa (covers LLM paraphrasing like
    "Senso-ji Temple" vs "Sensoji" or "teamLab Borderless" vs "teamLab").
    Returns the matched coords dict or None.
    """
    if name in lookup:
        return lookup[name]
    for key, coords in lookup.items():
        if key and (key in name or name in key):
            return coords
    return None


def _enrich_day_coords(day_dict: dict, lookup: dict[str, dict]) -> None:
    """Enrich a single day's time_slots with coords from lookup (in-place).

    After enrichment, strips any coord that is > 200 km from the day's median
    (catches Places API returning wrong-country results).
    """
    import math as _math

    for slot in day_dict.get("time_slots", []):
        if slot.get("lat") and slot.get("lng"):
            continue
        name = (slot.get("activity_name") or slot.get("label") or "").lower().strip()
        if not name:
            continue
        d = _fuzzy_lookup(name, lookup)
        if d:
            slot["lat"] = d["lat"]
            slot["lng"] = d["lng"]
            if d.get("image_url") and not slot.get("image_url"):
                slot["image_url"] = d["image_url"]
            if d.get("place_id") and not slot.get("place_id"):
                slot["place_id"] = d["place_id"]
            if d.get("address") and not slot.get("address"):
                slot["address"] = d["address"]

    # Outlier rejection
    coords = [(s["lat"], s["lng"]) for s in day_dict.get("time_slots", [])
              if s.get("lat") and s.get("lng")]
    if len(coords) >= 3:
        # Use simple centroid instead of independent medians which can land far from all points
        med_lat = sum(c[0] for c in coords) / len(coords)
        med_lng = sum(c[1] for c in coords) / len(coords)
        for slot in day_dict.get("time_slots", []):
            if slot.get("lat") and slot.get("lng"):
                dlat = _math.radians(slot["lat"] - med_lat)
                dlng = _math.radians(slot["lng"] - med_lng)
                a = (_math.sin(dlat / 2) ** 2
                     + _math.cos(_math.radians(slot["lat"])) * _math.cos(_math.radians(med_lat))
                     * _math.sin(dlng / 2) ** 2)
                dist = 6371.0 * 2 * _math.atan2(_math.sqrt(a), _math.sqrt(1 - a))
                if dist > 2000:
                    slot.pop("lat", None)
                    slot.pop("lng", None)


def enrich_itinerary_coords(itinerary_data: dict, state: dict | None = None) -> dict:
    """Enrich time_slots with lat/lng from embedded plans, state, or meal_cache DB.

    Looks up activity/meal coordinates from:
    1. itinerary_data["plans"]["activities_plan"] (embedded in saved itineraries)
    2. itinerary_data["plans"]["accommodation_plan"] (hotels)
    3. state["activities_plan"] and state["meal_options"] (live pipeline)
    4. meal_cache DB table (fallback for meals not in embedded plans or state)

    Modifies itinerary_data in-place and returns it.
    """
    if not itinerary_data or not isinstance(itinerary_data, dict):
        return itinerary_data

    days = itinerary_data.get("days", [])
    if not days:
        return itinerary_data

    # Build name -> coords lookup
    lookup: dict[str, dict] = {}

    # From embedded plans
    plans = itinerary_data.get("plans", {})
    if isinstance(plans, dict):
        ap = plans.get("activities_plan")
        if isinstance(ap, dict):
            for city_data in ap.get("cities", []):
                if not isinstance(city_data, dict):
                    continue
                for day_opts in city_data.get("options_per_day", []):
                    if not isinstance(day_opts, list):
                        continue
                    for act in day_opts:
                        if not isinstance(act, dict):
                            continue
                        name = (act.get("name") or "").lower().strip()
                        if name and act.get("lat") and act.get("lng"):
                            lookup[name] = {
                                "lat": act["lat"], "lng": act["lng"],
                                "image_url": act.get("image_url"),
                                "place_id": act.get("place_id"),
                                "address": act.get("address"),
                            }

        acc = plans.get("accommodation_plan")
        if isinstance(acc, dict):
            for city_data in acc.get("cities", []):
                if not isinstance(city_data, dict):
                    continue
                for h in city_data.get("options", []):
                    if not isinstance(h, dict):
                        continue
                    name = (h.get("name") or "").lower().strip()
                    if name and h.get("lat") and h.get("lng"):
                        lookup[name] = {
                            "lat": h["lat"], "lng": h["lng"],
                            "image_url": h.get("image_url"),
                            "place_id": h.get("place_id"),
                            "address": h.get("address"),
                        }

    # From live state (when plans aren't embedded yet)
    if state:
        ap = state.get("activities_plan")
        if isinstance(ap, dict):
            for city_data in ap.get("cities", []):
                if not isinstance(city_data, dict):
                    continue
                for day_opts in city_data.get("options_per_day", []):
                    if not isinstance(day_opts, list):
                        continue
                    for act in day_opts:
                        if not isinstance(act, dict):
                            continue
                        name = (act.get("name") or "").lower().strip()
                        if name and act.get("lat") and act.get("lng") and name not in lookup:
                            lookup[name] = {
                                "lat": act["lat"], "lng": act["lng"],
                                "image_url": act.get("image_url"),
                                "place_id": act.get("place_id"),
                                "address": act.get("address"),
                            }

        for meal_slot in (state.get("meal_options") or []):
            if not isinstance(meal_slot, dict):
                continue
            for opt in meal_slot.get("options", []):
                if not isinstance(opt, dict):
                    continue
                name = (opt.get("name") or "").lower().strip()
                if name and opt.get("lat") and opt.get("lng") and name not in lookup:
                    lookup[name] = {
                        "lat": opt["lat"], "lng": opt["lng"],
                        "image_url": opt.get("image_url"),
                        "place_id": opt.get("place_id"),
                        "address": opt.get("address"),
                    }

        for sel in (state.get("selected_meals") or []):
            if not isinstance(sel, dict):
                continue
            s = sel.get("selected")
            if isinstance(s, dict):
                name = (s.get("name") or "").lower().strip()
                if name and s.get("lat") and s.get("lng") and name not in lookup:
                    lookup[name] = {
                        "lat": s["lat"], "lng": s["lng"],
                        "image_url": s.get("image_url"),
                        "place_id": s.get("place_id"),
                        "address": s.get("address"),
                    }

    # Fallback: query meal_cache DB for meal slots still missing coords
    try:
        meal_names_needed = set()
        for day in days:
            for slot in day.get("time_slots", []):
                if slot.get("lat") and slot.get("lng"):
                    continue
                name = (slot.get("activity_name") or slot.get("label") or "").lower().strip()
                if name and name not in lookup and slot.get("slot_type") == "meal":
                    meal_names_needed.add(name)

        if meal_names_needed:
            import os
            import psycopg
            db_url = os.environ.get("DATABASE_URL", "")
            if db_url:
                with psycopg.connect(db_url) as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT meal_option, lat, lng FROM meal_cache "
                        "WHERE lat IS NOT NULL AND lng IS NOT NULL "
                        "AND lower(trim(meal_option->>'name')) = ANY(%s)",
                        (list(meal_names_needed),),
                    )
                    for row in cur.fetchall():
                        opt = row[0]
                        if isinstance(opt, str):
                            opt = json.loads(opt)
                        mname = (opt.get("name") or "").lower().strip()
                        if mname in meal_names_needed:
                            lookup[mname] = {
                                "lat": row[1], "lng": row[2],
                                "image_url": opt.get("image_url"),
                                "place_id": opt.get("place_id"),
                                "address": opt.get("address"),
                            }
    except Exception:
        pass  # DB fallback is non-fatal

    if not lookup:
        return itinerary_data

    # Apply to time_slots
    for day in days:
        for slot in day.get("time_slots", []):
            if slot.get("lat") and slot.get("lng"):
                continue
            name = (slot.get("activity_name") or slot.get("label") or "").lower().strip()
            if not name:
                continue
            d = _fuzzy_lookup(name, lookup)
            if d:
                slot["lat"] = d["lat"]
                slot["lng"] = d["lng"]
                if d.get("image_url") and not slot.get("image_url"):
                    slot["image_url"] = d["image_url"]
                if d.get("place_id") and not slot.get("place_id"):
                    slot["place_id"] = d["place_id"]
                if d.get("address") and not slot.get("address"):
                    slot["address"] = d["address"]

    # Outlier rejection: strip coords that are > 200km from the day's median
    # (catches Places API returning Singapore coords for China venues, etc.)

    for day in days:
        coords_in_day = [
            (s["lat"], s["lng"])
            for s in day.get("time_slots", [])
            if s.get("lat") and s.get("lng")
        ]
        if len(coords_in_day) < 3:
            continue
        # Use centroid to avoid independent median landing in the ocean
        med_lat = sum(c[0] for c in coords_in_day) / len(coords_in_day)
        med_lng = sum(c[1] for c in coords_in_day) / len(coords_in_day)
        for slot in day.get("time_slots", []):
            if slot.get("lat") and slot.get("lng"):
                dist = haversine(slot["lat"], slot["lng"], med_lat, med_lng)
                if dist > 2000:
                    slot.pop("lat", None)
                    slot.pop("lng", None)

    return itinerary_data


def _after_ingestion(state: dict) -> str:
    """
    Conditional edge after ingestion: short-circuit to END on infeasible/clarification.
    """
    if not state.get("is_feasible", True):
        return "end"
    if state.get("needs_clarification", False):
        return "end"
    if state.get("awaiting_confirmation", False):
        return "end"
    return "cache_check"


async def cache_check_node(state: dict) -> dict:
    city = state.get("destination", "")
    trip_style = state.get("trip_style") or ""
    activity_intensity = state.get("activity_intensity") or ""

    result = cache_lookup(
        city=city,
        trip_style=trip_style,
        activity_intensity=activity_intensity,
    )

    if result is not None:
        logger.info("Cache HIT for city=%s trip_style=%s activity_intensity=%s", city, trip_style, activity_intensity)
        return {"cache_hit": True, "cached_activities": result}

    logger.info("Cache MISS for city=%s trip_style=%s activity_intensity=%s", city, trip_style, activity_intensity)
    return {"cache_hit": False}


async def cache_write_node(state: dict) -> dict:
    activities_plan = state.get("activities_plan")
    if not activities_plan:
        return {}

    destination = state.get("destination", "")
    trip_style = state.get("trip_style") or ""
    activity_intensity = state.get("activity_intensity") or ""

    cache_save(
        city=destination,
        trip_style=trip_style,
        activity_intensity=activity_intensity,
        activities_plan=activities_plan,
    )

    return {}


def _recalculate_costs(schedule_dict: dict, state: dict) -> dict:
    """
    Recalculate daily_subtotal and grand_total from actual slot costs + hotel.

    LLM-generated arithmetic is unreliable. This post-processes the schedule
    to ensure cost fields are consistent with individual slot costs.
    """
    grand_total = 0.0
    accommodation = state.get("accommodation_plan")
    traveler_count = state.get("traveler_count") or 1
    room_sharing = state.get("room_sharing") or "shared"
    if room_sharing == "separate":
        rooms_needed = traveler_count
    else:
        rooms_needed = max(1, -(-traveler_count // 2))  # 2 per room, rounded up

    for day in schedule_dict.get("days", []):
        slot_total = sum(
            slot.get("cost_sgd", 0.0) for slot in day.get("time_slots", [])
        )
        day["daily_subtotal_sgd"] = round(slot_total, 2)
        grand_total += slot_total

    # Add hotel costs (scaled by rooms needed)
    if accommodation and isinstance(accommodation, dict):
        travel_dates = state.get("travel_dates") or {}
        start_str = travel_dates.get("start", "")
        end_str = travel_dates.get("end", "")
        total_nights = 1
        if start_str and end_str:
            try:
                total_nights = max(
                    1,
                    (_date.fromisoformat(end_str)
                     - _date.fromisoformat(start_str)).days,
                )
            except ValueError:
                pass

        for city in accommodation.get("cities", []):
            if not isinstance(city, dict):
                continue
            options = city.get("options", [])
            if options and isinstance(options[0], dict):
                price = options[0].get("price_per_night_sgd", 0.0)
                grand_total += price * total_nights * rooms_needed

    # Add flight costs (per traveler)
    transport = state.get("transport_plan")
    if transport and isinstance(transport, dict):
        for direction in ("outbound_flights", "inbound_flights"):
            flights = transport.get(direction, [])
            if flights and isinstance(flights[0], dict):
                grand_total += flights[0].get("price_sgd", 0.0) * traveler_count

    schedule_dict["grand_total_sgd"] = round(grand_total, 2)
    return schedule_dict


async def day_planner_node_per_day(state: dict,emit_event,thread_id: str = "") -> dict:
    """
    Day Planner: per-day LLM generation with progressive SSE streaming.

    Generates one DayPlan per LLM call, emitting a day_ready SSE event after
    each day validates. Fixes 14-day truncation and enables progressive
    frontend loading.

    Args:
        state: TravelBlackboard-compatible dict.
        emit_event: async callable(event: dict) -> None for SSE emission.
        thread_id: SSE thread identifier included in event payloads.

    Returns:
        {"itinerary": schedule_dict} or {"itinerary": None} on total failure.
    """
    activities_plan = state.get("activities_plan")
    if activities_plan is None:
        cached = state.get("cached_activities")
        if cached and isinstance(cached, dict) and cached.get("cities"):
            logger.warning("day_planner_node_per_day: activities_plan is None but cached_activities available, using cache as fallback")
            state = {**state, "activities_plan": cached}
            activities_plan = cached
        else:
            logger.warning("day_planner_node_per_day: activities_plan is None and no cached_activities, cannot generate itinerary")
            return {"itinerary": None}

    # Compute total_days from travel_dates
    travel_dates = state.get("travel_dates") or {}
    start_str = travel_dates.get("start", "")
    end_str = travel_dates.get("end", "")
    total_days = None
    if start_str and end_str:
        try:
            total_days = (_date.fromisoformat(end_str) - _date.fromisoformat(start_str)).days
        except ValueError:
            pass
    if not total_days or total_days < 1:
        # Fallback: sum trip_days from city activities
        cities_list = activities_plan.get("cities", []) if isinstance(activities_plan, dict) else []
        total_days = sum(c.get("trip_days", 3) for c in cities_list) if cities_list else 3
        logger.warning("day_planner_node_per_day: could not compute total_days from dates, fallback=%d", total_days)

    # Build day-to-city mapping. Distribute days across destinations in order.
    destinations = state.get("destinations") or []
    accommodation_plan = state.get("accommodation_plan") or {}
    transport_plan = state.get("transport_plan") or {}
    selected_meals = state.get("selected_meals") or []

    # Map day_num -> city name using city activity trip_days counts
    day_city_map: dict[int, str] = {}
    cities_list = activities_plan.get("cities", []) if isinstance(activities_plan, dict) else []
    day_cursor = 1
    for city_data in cities_list:
        city_name = city_data.get("city", "Unknown")
        trip_days = city_data.get("trip_days", 1)
        for _ in range(trip_days):
            if day_cursor <= total_days:
                day_city_map[day_cursor] = city_name
                day_cursor += 1
    # Fill any remaining days with the last city (or Unknown)
    last_city = (cities_list[-1].get("city", "Unknown") if cities_list else "Unknown")
    for d in range(day_cursor, total_days + 1):
        day_city_map[d] = last_city

    # Helper: get hotel name for a city from accommodation_plan
    def _hotel_for_city(city: str) -> str:
        accom_cities = accommodation_plan.get("cities", []) if isinstance(accommodation_plan, dict) else []
        for accom_city in accom_cities:
            if not isinstance(accom_city, dict):
                continue
            if accom_city.get("city", "").lower() == city.lower():
                options = accom_city.get("options", [])
                if options and isinstance(options[0], dict):
                    return options[0].get("name", "")
        return ""

    # Helper: get activities for a specific day within a city's allocation
    def _activities_for_day(city: str, day_within_city: int) -> list:
        for city_data in cities_list:
            if city_data.get("city", "").lower() != city.lower():
                continue
            options_per_day = city_data.get("options_per_day", [])
            idx = day_within_city - 1  # 0-based
            if 0 <= idx < len(options_per_day):
                return options_per_day[idx]
            # If index out of bounds, return last available day's activities
            if options_per_day:
                return options_per_day[-1]
        return []

    # Helper: get selected meals for a specific day
    def _meals_for_day(day_num: int) -> list:
        return [m for m in selected_meals if m.get("day_number") == day_num]

    # Extract flight times for transport notes
    outbound_flights = transport_plan.get("outbound_flights", [])
    inbound_flights = transport_plan.get("inbound_flights", [])
    arrival_time = ""
    departure_time = ""
    if outbound_flights and isinstance(outbound_flights[0], dict):
        arrival_time = outbound_flights[0].get("arrival_time", "")
    if inbound_flights and isinstance(inbound_flights[0], dict):
        departure_time = inbound_flights[0].get("departure_time", "")

    # Compute start date for day -> date mapping
    start_date = None
    if start_str:
        try:
            start_date = _date.fromisoformat(start_str)
        except ValueError:
            pass

    # Emit itinerary_meta before the loop
    await emit_event({
        "event": "itinerary_meta",
        "data": json.dumps({"total_days": total_days, "thread_id": thread_id}),
    })

    # Build coord lookup ONCE before day loop so each day_ready has pins
    _coord_lookup = _build_coord_lookup(state)

    llm = get_gemini_model()
    days: list[dict] = []
    previous_day_summary: str = "First day"
    city_day_counters: dict[str, int] = {}  # tracks day-within-city index per city

    trip_style = state.get("trip_style") or "mixed"
    activity_intensity = state.get("activity_intensity") or "moderate"
    preferences = state.get("preferences") or []
    additional_preferences = state.get("additional_preferences") or []
    all_prefs = preferences + additional_preferences
    prefs_str = ", ".join(all_prefs) if all_prefs else "general sightseeing"

    for day_num in range(1, total_days + 1):
        city = day_city_map.get(day_num, last_city)

        # Track how many days we've scheduled for this city
        city_day_counters[city] = city_day_counters.get(city, 0) + 1
        day_within_city = city_day_counters[city]

        hotel_name = _hotel_for_city(city)

        # Determine day type
        if day_num == 1:
            day_type = "arrival_day"
            transport_note = f"Outbound flight arrival time: {arrival_time}" if arrival_time else ""
        elif day_num == total_days:
            day_type = "departure_day"
            transport_note = f"Inbound flight departure time: {departure_time}" if departure_time else ""
        else:
            day_type = "full_day"
            transport_note = ""

        # Compute date string
        if start_date is not None:
            day_date = (start_date + _timedelta(days=day_num - 1)).isoformat()
        else:
            day_date = ""

        day_activities = _activities_for_day(city, day_within_city)
        day_meals = _meals_for_day(day_num)

        # Format meals for prompt
        if day_meals:
            meal_lines = [
                "SELECTED MEALS for this day (DO NOT replace or generate alternatives):"
            ]
            for meal in day_meals:
                meal_type = meal.get("meal_type", "meal")
                sel = meal.get("selected", {})
                name = sel.get("name", "Unknown") if isinstance(sel, dict) else str(sel)
                cuisine = sel.get("cuisine_type", "") if isinstance(sel, dict) else ""
                price = sel.get("price_range", "") if isinstance(sel, dict) else ""
                addr = sel.get("address", "") if isinstance(sel, dict) else ""
                parts = [name]
                if cuisine:
                    parts.append(cuisine)
                if price:
                    parts.append(price)
                if addr:
                    parts.append(addr)
                meal_lines.append(f"{meal_type.title()}: {', '.join(parts)}")
            day_meals_str = "\n".join(meal_lines)
        else:
            day_meals_str = "No pre-selected meals. Generate 2-3 restaurant options per meal slot."

        prompt = (
            SINGLE_DAY_PLANNER_PROMPT
            .replace("{DAY_NUMBER}", str(day_num))
            .replace("{TOTAL_DAYS}", str(total_days))
            .replace("{DATE}", day_date)
            .replace("{CITY}", city)
            .replace("{HOTEL_NAME}", hotel_name or f"Hotel in {city}")
            .replace("{DAY_TYPE}", day_type)
            .replace("{TRANSPORT_NOTE}", transport_note or "N/A")
            .replace("{PREVIOUS_DAY_SUMMARY}", previous_day_summary)
            .replace("{DAY_ACTIVITIES}", json.dumps(day_activities))
            .replace("{DAY_MEALS}", day_meals_str)
            .replace("{TRIP_STYLE}", trip_style)
            .replace("{ACTIVITY_INTENSITY}", activity_intensity)
            .replace("{TRAVELER_PREFERENCES}", prefs_str)
        )

        # LLM call with 3-attempt retry
        raw = None
        last_content = ""
        for attempt in range(3):
            try:
                response = await llm.ainvoke(prompt)
                content = response.content
                if content:
                    last_content = content
                raw = extract_json_from_response(content)
                break
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                logger.warning("day_planner_node_per_day: day %d attempt %d parse failed: %s", day_num, attempt + 1, str(exc)[:200])
                continue
            except Exception as exc:
                logger.warning("day_planner_node_per_day: day %d attempt %d LLM error: %s",day_num, attempt + 1, str(exc)[:200])
                break

        # Attempt repair on last response if all parse attempts failed
        if raw is None and last_content:

            normalized = normalize_content(last_content)
            try:
                raw = extract_json_from_response(normalized)
            except (json.JSONDecodeError, TypeError, ValueError):
                logger.warning("day_planner_node_per_day: day %d repair failed", day_num)

        if raw is None:
            logger.warning("day_planner_node_per_day: day %d all attempts failed, skipping", day_num)
            continue

        # Validate DayPlan (T-16-01: validate before emitting)
        try:
            day_plan = DayPlan.model_validate(raw)
        except ValidationError as exc:
            logger.warning("day_planner_node_per_day: day %d validation failed: %s", day_num, str(exc)[:400])
            continue

        # Enrich this day's time_slots with coords so map has pins immediately
        day_dump = day_plan.model_dump()
        _enrich_day_coords(day_dump, _coord_lookup)

        # Emit day_ready SSE event
        await emit_event({
            "event": "day_ready",
            "data": json.dumps({
                "day_number": day_plan.day_number,
                "day": day_dump,
                "thread_id": thread_id,
            }),
        })

        days.append(day_dump)

        # Update previous_day_summary for next iteration
        last_slot = day_plan.time_slots[-1] if day_plan.time_slots else None
        last_end = last_slot.end_time if last_slot and last_slot.end_time else "22:00"
        previous_day_summary = json.dumps({
            "city": city,
            "hotel_name": hotel_name or f"Hotel in {city}",
            "last_activity_end_time": last_end,
        })

    # validate that we generated the expected number of days
    if len(days) != total_days:
        logger.warning("day_planner_node_per_day: expected %d days but generated %d",total_days, len(days))

    if not days:
        return {"itinerary": None}

    # Assemble DailySchedule and recalculate costs
    schedule_dict = {
        "total_days": total_days,
        "days": days,
        "grand_total_sgd": 0.0,
    }
    schedule_dict = _recalculate_costs(schedule_dict, state)
    return {"itinerary": schedule_dict}
