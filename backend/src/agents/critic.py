
import json
import re

from src.agents.llm import get_gemini_model, extract_json_from_response
from src.prompts.critic import (
    CRITIC_LLM_PROMPT,
    OUTPUT_SCHEMA_CLEAN,
    OUTPUT_SCHEMA_VIOLATIONS,
    TASK_INSTRUCTIONS_CLEAN,
    TASK_INSTRUCTIONS_VIOLATIONS,
)
from src.state.models import (
    CriticFeedback,
    EmptyDayViolation,
    GeographicViolation,
    MissingRestaurantViolation,
    RelaxationSuggestion,
    TimeBlockViolation,
    Violation,
)
from src.state.blackboard import TravelBlackboard
from src.utils import haversine, median_latlng, parse_time

# Base threshold for geographic plausibility — adapted per destination context
_GEO_BASE_THRESHOLD_KM = 200.0

# Large metro areas where a wider threshold is warranted (sprawling cities)
_LARGE_METRO_CITIES = {
    "tokyo", "los angeles", "new york", "london", "paris", "bangkok",
    "jakarta", "mumbai", "delhi", "shanghai", "beijing", "istanbul",
    "mexico city", "cairo", "sao paulo", "buenos aires", "seoul",
    "sydney", "melbourne", "hong kong", "kuala lumpur",
}


def _get_geo_threshold(city: str, activity_intensity: str = "moderate") -> float:
    """
    Adaptive geographic threshold based on city size and trip style.

    Large metro areas get a wider threshold (250km) to account for sprawl.
    Relaxed trips get tighter threshold (150km) since activities should cluster.
    Packed/adventure trips get wider threshold (250km) for day trips.
    """
    base = _GEO_BASE_THRESHOLD_KM
    city_lower = city.lower().strip()

    # Large metros have wider acceptable range
    if city_lower in _LARGE_METRO_CITIES:
        base = 250.0

    # Adjust by activity intensity
    intensity_lower = (activity_intensity or "moderate").lower()
    if intensity_lower in ("low", "relaxed"):
        base *= 0.75  # Tighter — expect activities to cluster nearby
    elif intensity_lower in ("high", "packed"):
        base *= 1.25  # Wider — allow day trips

    return base


def _extract_city_from_address(address: str, destination: str) -> str:
    """
    Extract a city name from an address string using dynamic matching.

    Instead of a hardcoded city list, checks if the destination city appears
    in the address. If not, tries to extract a recognizable city name from
    common address patterns (comma-separated segments).
    """
    address_lower = address.lower()
    dest_lower = destination.lower()

    # If the destination is in the address, it's fine — caller handles that check
    if dest_lower in address_lower:
        return destination

    # Try to extract city from address segments (addresses are often "..., City, Country")
    segments = [s.strip() for s in address.split(",")]
    for segment in reversed(segments):
        seg_lower = segment.lower()
        # Skip common non-city segments (numbers, zip codes, short tokens)
        stripped = segment.replace(" ", "").replace("-", "").replace("–", "")
        if len(segment) < 3 or stripped.isdigit():
            continue
        # Skip postal code patterns (must contain at least one digit)
        # Matches: "160-0021", "W1U 8ED", "10001", "SW1A 1AA", "04536"
        seg_stripped = segment.strip()
        if (re.search(r"\d", seg_stripped)
                and re.match(r"^[A-Z0-9\s\-]{3,10}$", seg_stripped, re.IGNORECASE)):
            continue
        # Skip country names and common suffixes
        if seg_lower in ("japan", "thailand", "indonesia", "singapore", "malaysia",
                         "south korea", "korea", "taiwan", "uk", "usa",
                         "united kingdom", "united states", "france", "germany",
                         "australia", "italy", "spain", "india"):
            continue
        # Skip prefecture/state level
        if any(kw in seg_lower for kw in ("prefecture", "province", "state", "region")):
            continue
        # This segment is likely the city
        if seg_lower != dest_lower:
            return segment
        break

    return "another location"


def generate_relaxation_suggestions(violations: list[Violation], state: TravelBlackboard) -> list[RelaxationSuggestion]:
    suggestions: list[RelaxationSuggestion] = []

    for violation in violations:
        if isinstance(violation, GeographicViolation):
            suggestions.append(
                RelaxationSuggestion(
                    violation_type="geographic_impossibility",
                    action="replace activity with local alternative",
                    alternative=(
                        f"Find similar activities in {state.get('destination', 'destination')}"
                        f" instead of {violation.to_venue}"
                    ),
                )
            )

    return suggestions


def check_geographic_plausibility_haversine(state: TravelBlackboard) -> list[GeographicViolation]:
    """
    Check geographic plausibility using haversine distance + median cluster.
    """
    violations: list[GeographicViolation] = []
    destination = state.get("destination", "")
    activity_intensity = state.get("activity_intensity", "moderate")

    activities_plan = state.get("activities_plan")
    if activities_plan is None:
        return violations

    cities_list = activities_plan.get("cities", [])

    if cities_list:
        # New per-city format
        for city_activities in cities_list:
            city_name = city_activities.get("city", "")
            all_options: list[dict] = []
            for day_options in city_activities.get("options_per_day", []):
                all_options.extend(day_options)

            geo_threshold = _get_geo_threshold(city_name, activity_intensity)
            violations.extend(
                _check_activities_geo(
                    all_options, city_name, destination, geo_threshold_km=geo_threshold
                )
            )
    else:
        # Legacy flat format (backward compat)
        flat_activities = activities_plan.get("activities", [])
        geo_threshold = _get_geo_threshold(destination, activity_intensity)
        violations.extend(
            _check_activities_geo(
                flat_activities, destination, destination, geo_threshold_km=geo_threshold
            )
        )

    accommodation_plan = state.get("accommodation_plan")
    if accommodation_plan is not None:
        hotel_cities = accommodation_plan.get("cities", [])
        if hotel_cities:
            for city_hotels in hotel_cities:
                city_name = city_hotels.get("city", "")
                options = city_hotels.get("options", [])
                geo_threshold = _get_geo_threshold(city_name, activity_intensity)
                # Use city_name as both expected_city and destination for hotels,
                # so Florence hotels are checked against Florence, not the primary destination
                violations.extend(
                    _check_activities_geo(
                        options, city_name, city_name,
                        item_label="hotel", geo_threshold_km=geo_threshold,
                    )
                )

    return violations


def _check_activities_geo(
    items: list[dict],
    expected_city: str,
    destination: str,
    item_label: str = "activity",
    geo_threshold_km: float = _GEO_BASE_THRESHOLD_KM,
) -> list[GeographicViolation]:
    """
    Run haversine + fallback geo checks on a flat list of activity/hotel dicts.
    """
    violations: list[GeographicViolation] = []
    if not items:
        return violations

    # Compute median reference point from items with coordinates
    coords_present = [a for a in items if a.get("lat") is not None and a.get("lng") is not None]
    ref_point = median_latlng(coords_present) if len(coords_present) >= 2 else None

    for item in items:
        name = item.get("name", f"Unknown {item_label}")
        lat = item.get("lat")
        lng = item.get("lng")
        address = item.get("address")

        if lat is not None and lng is not None and ref_point is not None:
            dist_km = haversine(ref_point[0], ref_point[1], lat, lng)
            if dist_km > geo_threshold_km:
                violations.append(
                    GeographicViolation(
                        from_venue=expected_city,
                        to_venue=name,
                        reason=(
                            f"{item_label.capitalize()} is {dist_km:.0f} km from the"
                            f" {expected_city} activity cluster — likely in a different city"
                        ),
                    )
                )
        else:
            # Fallback: address string-matching
            if address is None:
                continue
            addr_lower = address.lower()
            # Extract just the city name (strip country suffix like "Tokyo, Japan" -> "Tokyo")
            city_only = expected_city.split(",")[0].strip().lower()
            dest_only = destination.split(",")[0].strip().lower()
            if (city_only not in addr_lower
                    and dest_only not in addr_lower
                    and expected_city.lower() not in addr_lower):
                detected = _extract_city_from_address(address, destination)
                violations.append(
                    GeographicViolation(
                        from_venue=destination,
                        to_venue=name,
                        reason=(
                            f"{item_label.capitalize()} located in {detected}, not {destination}"
                        ),
                    )
                )

    return violations




def check_time_blocks(state: TravelBlackboard) -> list[TimeBlockViolation]:
    """
    Detect overlapping time slots in DailySchedule.

    Algorithm: for each day, sort time slots by start_time, flag any slot that starts
    before the previous slot ends.
    """
    violations: list[TimeBlockViolation] = []

    itinerary = state.get("itinerary")
    if itinerary is None:
        return violations

    for day in itinerary.get("days", []):
        time_slots = day.get("time_slots", [])
        if len(time_slots) < 2:
            continue

        sorted_slots = sorted(time_slots, key=lambda s: parse_time(s["start_time"]))

        for i in range(1, len(sorted_slots)):
            prev = sorted_slots[i - 1]
            curr = sorted_slots[i]

            prev_end = parse_time(prev["end_time"])
            curr_start = parse_time(curr["start_time"])

            if curr_start < prev_end:
                violations.append(
                    TimeBlockViolation(
                        activity_1=prev.get("label", "Unknown slot"),
                        activity_2=curr.get("label", "Unknown slot"),
                        overlap_description=(
                            f"'{prev.get('label')}' ends at {prev['end_time']} but"
                            f" '{curr.get('label')}' starts at {curr['start_time']}"
                        ),
                    )
                )

    return violations


def _is_transit_day(day: dict) -> bool:
    """
    Check if a day contains a transit slot (inter-city travel day).
    """
    for slot in day.get("time_slots", []):
        if slot.get("slot_type") == "transit":
            return True
    return False


def _get_coverage_threshold(activity_intensity: str = "moderate") -> float:
    """
    Adaptive coverage threshold based on activity intensity.

    Relaxed trips need less scheduled time; packed trips need more.
    """
    intensity_lower = (activity_intensity or "moderate").lower()
    if intensity_lower in ("low", "relaxed"):
        return 0.40  # Relaxed: only 40% scheduled time required
    elif intensity_lower in ("high", "packed"):
        return 0.75  # Packed: 75% scheduled time required
    return 0.60  # Moderate: 60% (original default)


def check_empty_days(state: TravelBlackboard) -> list[EmptyDayViolation]:
    """
    Non-transit days with insufficient time coverage trigger violation.
    """
    USABLE_MINUTES = 600
    activity_intensity = state.get("activity_intensity", "moderate")
    THRESHOLD = _get_coverage_threshold(activity_intensity)
    violations: list[EmptyDayViolation] = []

    itinerary = state.get("itinerary")
    if itinerary is None:
        return violations

    days = itinerary.get("days", [])
    total_days = len(days)

    for day in days:
        day_num = day.get("day_number", 0)
        # Exempt first and last days (arrival/departure)
        if day_num <= 1 or day_num >= total_days:
            continue
        if _is_transit_day(day):
            continue

        scheduled_minutes = 0
        for slot in day.get("time_slots", []):
            if slot.get("slot_type") in ("activity", "meal", "buffer"):
                try:
                    start = parse_time(slot["start_time"])
                    end = parse_time(slot["end_time"])
                    delta = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
                    if delta > 0:
                        scheduled_minutes += delta
                except (KeyError, ValueError):
                    continue

        coverage = scheduled_minutes / USABLE_MINUTES if USABLE_MINUTES > 0 else 0.0
        if coverage < THRESHOLD:
            violations.append(
                EmptyDayViolation(
                    day_number=day_num,
                    date=day.get("date", ""),
                    coverage_pct=round(coverage, 2),
                    reason=(
                        f"Day {day_num} has only {scheduled_minutes} min scheduled"
                        f" ({coverage:.0%} of {USABLE_MINUTES} min usable window)"
                    ),
                )
            )

    return violations


def check_missing_restaurant_names(state: TravelBlackboard) -> list[MissingRestaurantViolation]:
    """
    Meal slots with no restaurant name in notes field trigger violation.

    A notes field passes if it contains:
    - A numbered list pattern like "1)" (e.g., "1) Ichiran Ramen")
    - A capitalized multi-word name pattern (e.g., "Ichiran Ramen")
    """
    violations: list[MissingRestaurantViolation] = []
    itinerary = state.get("itinerary")
    if itinerary is None:
        return violations

    for day in itinerary.get("days", []):
        day_num = day.get("day_number", 0)
        for slot in day.get("time_slots", []):
            if slot.get("slot_type") != "meal":
                continue
            notes = slot.get("notes") or ""
            has_restaurant = bool(
                re.search(r"\d\)", notes)  # "1) Restaurant Name"
                or re.search(r"[A-Z][a-z]+\s+[A-Z][a-z]+", notes)  # "Ichiran Ramen"
            )
            if not has_restaurant:
                violations.append(
                    MissingRestaurantViolation(
                        day_number=day_num,
                        slot_label=slot.get("label", "Unknown meal"),
                    )
                )
    return violations


async def _run_llm_review(state: TravelBlackboard, violations: list[Violation]) -> list[dict]:
    """
    LLM review: quality_suggestions for plan improvement.

    No grounding tool, critic works on structured plan data only.
    Fail-open: returns [] on any parse error.
    """
    if violations:
        violations_str = json.dumps([v.model_dump() for v in violations], indent=2)
        task_instructions = TASK_INSTRUCTIONS_VIOLATIONS
        output_schema = OUTPUT_SCHEMA_VIOLATIONS
    else:
        violations_str = "No violations found."
        task_instructions = TASK_INSTRUCTIONS_CLEAN
        output_schema = OUTPUT_SCHEMA_CLEAN

    # Truncated itinerary summary (~300 tokens)
    itinerary = state.get("itinerary") or {}
    days = itinerary.get("days", [])
    if days:
        summary_lines = []
        for day in days:
            slot_count = len(day.get("time_slots", []))
            summary_lines.append(
                f"Day {day.get('day_number', '?')}: {day.get('city', '?')} — {slot_count} slots"
            )
        itinerary_summary = "\n".join(summary_lines)
    else:
        itinerary_summary = "No detailed itinerary available yet."

    destinations = state.get("destination", "Unknown")
    travel_dates = state.get("travel_dates") or {}
    travel_dates_str = (
        f"{travel_dates.get('start', '?')} to {travel_dates.get('end', '?')}"
        if travel_dates
        else "Unknown"
    )
    daily_schedule_cost = state.get("daily_schedule_cost") or 0.0
    traveler_count = state.get("traveler_count", 1)

    # Use str.replace to avoid KeyError from JSON schema curly braces in the template
    prompt = (
        CRITIC_LLM_PROMPT
        .replace("{VIOLATIONS}", violations_str)
        .replace("{DESTINATIONS}", str(destinations))
        .replace("{TRAVEL_DATES}", travel_dates_str)
        .replace("{DAILY_SCHEDULE_COST}", f"{daily_schedule_cost:.2f}")
        .replace("{TRAVELER_COUNT}", str(traveler_count))
        .replace("{ITINERARY_SUMMARY}", itinerary_summary)
        .replace("{TASK_INSTRUCTIONS}", task_instructions)
        .replace("{OUTPUT_SCHEMA}", output_schema)
    )

    try:
        llm = get_gemini_model()
        response = await llm.ainvoke(prompt)
        raw = extract_json_from_response(response.content)
        quality_suggestions = raw.get("quality_suggestions", [])
        return quality_suggestions
    except Exception:
        return []


async def critic_node(state: TravelBlackboard) -> dict:
    """
    Critic Agent: deterministic checks + LLM quality review.

    Flow:
    1. Deterministic checks (geographic, time block).
    2. LLM review: always runs for quality_suggestions.
    3. Returns critic_feedback and quality_suggestions merged into blackboard.
    """
    violations: list[Violation] = []

    geo_violations = check_geographic_plausibility_haversine(state)
    violations.extend(geo_violations)

    time_violations = check_time_blocks(state)
    violations.extend(time_violations)

    # Empty days and missing restaurants are demoted to soft suggestions
    empty_day_violations = check_empty_days(state)
    restaurant_violations = check_missing_restaurant_names(state)

    suggestions = generate_relaxation_suggestions(violations, state)

    # Demoted checks — informational suggestions only
    for ev in empty_day_violations:
        suggestions.append(RelaxationSuggestion(
            violation_type="empty_day",
            action="informational",
            alternative=ev.reason,
        ))
    for rv in restaurant_violations:
        suggestions.append(RelaxationSuggestion(
            violation_type="missing_restaurant",
            action="informational",
            alternative=f"Day {rv.day_number} {rv.slot_label}: add specific restaurant names",
        ))

    is_feasible = len(violations) == 0

    quality_suggestions = await _run_llm_review(state, violations)

    feedback = CriticFeedback(
        violations=[v.model_dump() for v in violations],
        relaxation_suggestions=[s.model_dump() for s in suggestions],
        is_feasible=is_feasible,
    )

    current_retry = state.get("retry_count", 0)
    result: dict = {
        "critic_feedback": feedback.model_dump(),
        "quality_suggestions": quality_suggestions,
    }
    if not is_feasible:
        result["retry_count"] = current_retry + 1

    return result
