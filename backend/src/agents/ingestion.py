import asyncio
import json
import re as re_module
from datetime import date, timedelta
from typing import Optional

from src.agents.llm import get_gemini_model
from src.models.ingestion import IngestionResult, InputType
from src.prompts.ingestion import IMAGE_EXTRACTION_PROMPT, TEXT_EXTRACTION_PROMPT, URL_EXTRACTION_PROMPT
from src.scraper import scrape_url
from src.tools.grounding import normalize_content
from src.state.blackboard import TravelBlackboard

def get_ingestion_llm():
    return get_gemini_model().with_structured_output(IngestionResult)


# Core fields to mark as low confidence when scraping is partial
LOW_CONFIDENCE_CORE_FIELDS = [
    "destination",
    "travel_dates",
    "traveler_count",
    "preferences",
]

# Mainland China blocked: Google Search grounding unavailable
BLOCKED_DESTINATIONS = {
    "china", "beijing", "shanghai", "shenzhen", "guangzhou",
    "chengdu", "nanjing", "wuhan", "xi'an", "xian", "chongqing",
    "hangzhou", "tianjin", "suzhou", "dalian", "kunming",
}


def process_text_input(text: str) -> IngestionResult:
    llm = get_ingestion_llm()
    prompt = TEXT_EXTRACTION_PROMPT.format(text=text)
    return llm.invoke(prompt)


def _check_rule_based_feasibility(result: IngestionResult) -> Optional[str]:
    """
    Apply rule-based feasibility checks: blocked destinations, past dates, extreme values.

    Returns a human-readable rejection string on failure, None otherwise.
    """
    if result.travel_dates:
        start_str = result.travel_dates.get("start")
        end_str = result.travel_dates.get("end")
        if start_str and end_str:
            try:
                start = date.fromisoformat(start_str)
                end = date.fromisoformat(end_str)
                if start < date.today():
                    return f"Travel start date {start_str} is in the past."
                duration = (end - start).days
                if duration <= 0:
                    return "Trip end date must be after start date."
                if duration >= 365:
                    return f"A {duration}-day trip is unusually long."
            except ValueError:
                pass  # Invalid date format caught by model validator

    if result.traveler_count is not None and result.traveler_count >= 50:
        return f"{result.traveler_count} travelers is unusually large."

    return None


_SKIP_CLARIFICATION_PHRASES = {
    "you decide", "just decide", "pick for me", "your choice", "decide for me",
    "up to you", "whatever", "default", "defaults", "surprise me", "don't care",
    "dont care", "anything", "no preference", "skip", "just plan", "go ahead",
}


def _user_wants_skip(raw_input: str) -> bool:
    lower = raw_input.lower().strip()
    return any(phrase in lower for phrase in _SKIP_CLARIFICATION_PHRASES)


_CONFIRM_PHRASES = {
    "confirm", "confirmed", "yes", "yep", "yeah", "looks good",
    "go ahead", "proceed", "lgtm", "go", "ok", "okay", "correct",
    "that's right", "thats right", "perfect", "let's go", "lets go",
    "start", "do it",
}


def _user_confirms(raw_input: str) -> bool:
    return raw_input.strip().lower() in _CONFIRM_PHRASES


def _build_confirmation_summary(state: dict) -> list[str]:
    lines: list[str] = []

    # Destinations
    dests = state.get("destinations") or []
    dest_str = ", ".join(
        f"{d.get('city', '?')}, {d.get('country', '?')}" for d in dests
    )
    lines.append(f"Destinations: {dest_str}")

    # Dates + duration
    dates = state.get("travel_dates") or {}
    start, end = dates.get("start", "?"), dates.get("end", "?")
    try:
        days = (date.fromisoformat(end) - date.fromisoformat(start)).days
        lines.append(f"Dates: {start} to {end} ({days} days)")
    except (ValueError, TypeError):
        lines.append(f"Dates: {start} to {end}")

    # Travelers + room
    count = state.get("traveler_count") or 1
    room = state.get("room_sharing")
    if count > 1 and room is not None:
        room_label = "shared" if room == "shared" else "separate"
        lines.append(f"Travelers: {count} ({room_label} room)")
    else:
        lines.append(f"Travelers: {count}")

    # Accommodation
    tier = state.get("accommodation_tier")
    tier_display = tier.capitalize() if tier else "Mid-range (Default)"
    lines.append(f"Accommodation: {tier_display}")

    # Activity intensity
    intensity = state.get("activity_intensity")
    intensity_display = intensity.capitalize() if intensity else "Moderate (Default)"
    lines.append(f"Activity pace: {intensity_display}")

    # Food/dining preferences
    prefs = state.get("preferences") or []
    _MEAL_KW = {
        "food", "dining", "restaurant", "street food", "vegan", "halal",
        "vegetarian", "kosher", "gluten-free", "seafood", "local cuisine",
        "fine dining", "cafe", "dim sum", "ramen", "sushi", "curry",
    }
    meal_prefs = [p for p in prefs if any(kw in p.lower() for kw in _MEAL_KW)]
    if meal_prefs:
        lines.append(f"Food preferences: {', '.join(meal_prefs)}")
    else:
        lines.append("Food preferences: No specific preference (Default)")

    return lines


async def _generate_natural_questions(
    missing_fields: list[str], user_query: str, result: IngestionResult
) -> list[str]:
    """
    Generate natural, context-aware clarification questions using LLM.

    Takes rule-based questions and rewrites them to reference what the user already said.
    Falls back to the original rule-based questions on any failure.

    Args:
        missing_fields: Rule-based question strings to rewrite.
        user_query: The user's raw input for context.
        result: Current extraction result.

    Returns:
        List of natural question strings (same count as missing_fields).
    """
    prompt = (
        f'The user said: "{user_query}"\n\n'
        f"We need to ask about these missing details: {'; '.join(missing_fields)}\n\n"
        "Generate natural, context-aware clarification questions that reference "
        "what the user already told us.\n"
        "Return a JSON array of strings, one question per missing field, in the same order.\n"
        "Keep questions conversational and brief (1 sentence each).\n"
        'Example: Instead of "What are your travel dates?" say '
        '"You mentioned Bangkok — when are you planning to go?"'
    )

    try:
        llm = get_gemini_model()
        response = await asyncio.to_thread(llm.invoke, prompt)
        content = normalize_content(response.content) if hasattr(response, "content") else str(response)
        # Extract JSON array from response
        json_match = re_module.search(r"\[.*\]", content, re_module.DOTALL)
        if not json_match:
            return missing_fields
        questions = json.loads(json_match.group())
        if not isinstance(questions, list) or len(questions) != len(missing_fields):
            return missing_fields
        return [str(q) for q in questions]
    except Exception:
        return missing_fields


async def _generate_optional_questions(
    missing_hints: list[str], user_query: str, result: IngestionResult
) -> list[str]:
    """
    Generate natural clarification questions for optional fields using LLM.

    Unlike _generate_natural_questions (which rewrites existing questions 1:1),
    this asks the LLM to produce sensible, context-aware questions from scratch.
    The LLM may combine or skip hints if they don't make sense to ask separately.
    """
    already_known: list[str] = []
    if result.destinations:
        cities = [d.get("city", "") for d in result.destinations if isinstance(d, dict)]
        already_known.append(f"Destinations: {', '.join(c for c in cities if c)}")
    if result.travel_dates:
        already_known.append(f"Dates: {result.travel_dates}")
    if result.traveler_count:
        already_known.append(f"Travelers: {result.traveler_count}")
    if result.trip_style:
        already_known.append(f"Style: {result.trip_style}")

    prompt = (
        f'The user said: "{user_query}"\n\n'
        f"Already extracted: {'; '.join(already_known) if already_known else 'minimal info'}\n\n"
        f"We still need: {'; '.join(missing_hints)}\n\n"
        "Generate 1-3 brief, natural clarification questions that make sense given "
        "what the user already told us. Combine related topics into one question if natural. "
        "Skip any question that would feel forced or irrelevant given the context.\n"
        "Return a JSON array of strings.\n"
        'Example: ["What kind of accommodation are you looking for — budget hostels or something more upscale?", '
        '"Any food preferences or dietary needs?"]'
    )

    try:
        llm = get_gemini_model()
        response = await asyncio.to_thread(llm.invoke, prompt)
        content = normalize_content(response.content) if hasattr(response, "content") else str(response)
        json_match = re_module.search(r"\[.*\]", content, re_module.DOTALL)
        if not json_match:
            return [f"Any preference for {h}?" for h in missing_hints]
        questions = json.loads(json_match.group())
        if not isinstance(questions, list) or not questions:
            return [f"Any preference for {h}?" for h in missing_hints]
        return [str(q) for q in questions]
    except Exception:
        return [f"Any preference for {h}?" for h in missing_hints]


async def _build_clarification_response(
    result: IngestionResult, clarification_round: int, raw_input: str = ""
) -> dict:
    """
    Build clarification response for unanswered fields.

    Keeps re-asking until answered or user says "you decide" / "skip".
    After 3+ rounds, applies defaults (abuse detection).
    Uses LLM to generate natural, context-aware questions when raw_input is provided.
    """
    questions: list[str] = []

    # Critical fields — must have for planning
    if not result.destinations:
        questions.append(
            "Where would you like to travel? Please specify the city and country."
        )
    elif any(not d.get("city") for d in result.destinations if isinstance(d, dict)):
        # Country specified but no city — ask which cities
        countries = [d.get("country", "there") for d in result.destinations
                     if isinstance(d, dict) and not d.get("city")]
        questions.append(
            f"Which cities in {countries[0]} would you like to visit?"
        )

    if not result.travel_dates:
        questions.append(
            "What are your travel dates? (e.g., '1st April to 8th April 2026')"
        )

    # Collect missing optional field hints for LLM-based question generation
    missing_hints: list[str] = []
    count = result.traveler_count or 1
    if count > 1 and result.room_sharing is None:
        missing_hints.append("room sharing preference (shared or separate rooms)")
    if result.accommodation_tier is None:
        missing_hints.append("accommodation tier (budget / mid-range / luxury)")
    if result.activity_intensity is None:
        missing_hints.append("activity intensity (relaxed / moderate / packed)")

    _MEAL_KEYWORDS = [
        "food", "dining", "restaurant", "street food", "vegan", "halal",
        "vegetarian", "kosher", "gluten-free", "seafood", "local cuisine",
        "fine dining", "cafe", "coffee", "dessert", "brunch", "buffet",
        "meat", "bbq", "sushi", "ramen", "pizza", "pasta", "noodle",
        "curry", "dim sum", "tapas", "bistro", "gastropub", "bakery",
        "breakfast", "lunch", "dinner", "snack", "drink", "bar", "pub",
        "wine", "beer", "cocktail", "michelin", "hawker", "food court",
        "organic", "farm-to-table", "pescatarian", "dairy-free",
    ]
    has_meal_pref = any(
        kw in " ".join(result.preferences or []).lower()
        for kw in _MEAL_KEYWORDS
    )
    if not has_meal_pref:
        missing_hints.append("food/dining preferences or dietary restrictions")

    # Generate natural questions for optional fields via LLM
    if missing_hints and raw_input:
        llm_questions = await _generate_optional_questions(missing_hints, raw_input, result)
        questions.extend(llm_questions)
    elif missing_hints:
        # Fallback: basic template questions if no raw_input
        for hint in missing_hints:
            questions.append(f"Any preference for {hint}?")

    if not questions:
        return {"needs_clarification": False, "clarification_questions": None}

    if clarification_round >= 3:
        notes = result.extraction_notes or ""
        notes = notes + " [Defaults applied after repeated clarification]"
        # Dynamic default dates: ~30 days from today, 7-day trip

        today = date.today()
        default_start = today + timedelta(days=30)
        default_end_date = default_start + timedelta(days=6)
        return {
            "needs_clarification": False,
            "clarification_questions": None,
            "destinations": [{"city": "undecided", "country": "TBD", "order": 1}],
            "travel_dates": {
                "start": default_start.isoformat(),
                "end": default_end_date.isoformat(),
            },
            "traveler_count": 1,
            "extraction_notes": notes,
        }

    # Rewrite critical questions (destination, dates) to be more natural
    if raw_input:
        questions = await _generate_natural_questions(questions, raw_input, result)

    # Add skip hint on round 1+ (user has already answered once)
    if clarification_round >= 1:
        questions.append('(Say "you decide" to let me pick defaults for the rest)')

    return {
        "needs_clarification": True,
        "clarification_questions": questions,
    }


async def ingestion_node(state: TravelBlackboard) -> dict:
    """
    Ingestion node
    """
    raw_input = state.get("raw_input", "")
    input_type = state.get("input_type", InputType.TEXT.value)

    # Read-back confirmation: user confirms -> clear flag, proceed to pipeline
    if state.get("awaiting_confirmation") and _user_confirms(raw_input):
        return {
            "awaiting_confirmation": False,
            "confirmation_summary": None,
            "needs_clarification": False,
        }

    # Read-back confirmation: user typed changes -> enrich input with prior context
    # so the LLM can extract the change correctly from a short message like "change to 2 travelers"
    if state.get("awaiting_confirmation"):
        dests = state.get("destinations") or []
        dest_str = ", ".join(f"{d.get('city')}, {d.get('country')}" for d in dests)
        dates = state.get("travel_dates") or {}
        # Frame as a fresh travel request with the user's change applied,
        # so the LLM extracts the updated values naturally.
        raw_input = (
            f"I want to travel to {dest_str} "
            f"from {dates.get('start')} to {dates.get('end')}. "
            f"Additional detail: {raw_input}"
        )

    if input_type == InputType.TEXT.value:
        result = process_text_input(raw_input)
    else:
        result = IngestionResult()

    # merge with prior state so multi-turn clarification keeps previously extracted fields
    clarification_round = state.get("clarification_round", 0)
    is_followup = clarification_round > 0

    def _pick(new_val, state_key, fallback=None):
        """
        Use newly extracted value if non-empty, else fall back to prior state.
        """
        if new_val:
            return new_val
        prior = state.get(state_key)
        return prior if prior else fallback

    def _pick_numeric(new_val, state_key, default):
        """
        Merge numeric fields across clarification turns.

        On follow-up turns the LLM re-extracts from a short reply that often
        lacks the original detail (e.g. "shared room" has no traveler count),
        so it falls back to the schema default (1).  Prefer the prior state
        value in that case to avoid overwriting a real extraction.
        """
        prior = state.get(state_key)
        if is_followup and prior and prior != default:
            # Prior turn extracted a non-default value; keep it unless
            # the new extraction is also non-default (user explicitly restated).
            if new_val is None or new_val == default:
                return prior
        # First turn or new value is explicitly non-default
        if new_val is not None:
            return new_val
        return prior if prior else default

    base_fields: dict = {
        "destinations": _pick(result.destinations, "destinations", []),
        "destination": (  # backward compat
            f"{result.destinations[0]['city']}, {result.destinations[0]['country']}"
            if result.destinations
            else (
                state.get("destination")
                or result.destination
                or ""
            )
        ),
        "travel_dates": _pick(result.travel_dates, "travel_dates", {}),
        "traveler_count": _pick_numeric(result.traveler_count, "traveler_count", 1),
        "low_confidence_fields": result.low_confidence_fields or [],
        "preferences": _pick(result.preferences, "preferences", []),
        "additional_preferences": _pick(
            result.additional_preferences, "additional_preferences", []
        ),
        "trip_style": result.trip_style or state.get("trip_style"),
        "trip_style_notes": result.trip_style_notes or state.get("trip_style_notes"),
        "activity_intensity": result.activity_intensity or state.get("activity_intensity"),
        "accommodation_tier": result.accommodation_tier or state.get("accommodation_tier"),
        "accommodation_type": result.accommodation_type or state.get("accommodation_type"),
        "room_sharing": result.room_sharing if result.room_sharing is not None else state.get("room_sharing"),
        "bed_type_preference": result.bed_type_preference or state.get("bed_type_preference"),
        "extraction_notes": result.extraction_notes,
        "is_feasible": True,
        "feasibility_rejection_reason": None,
        "needs_clarification": False,
        "clarification_questions": None,
        "origin": result.origin or state.get("origin") or "Singapore",
        "planning_mode": "choose",  # default is always "choose"
        "planning_mode_max_options": 5,
    }

    # Use merged base_fields for checks (not raw result) so multi-turn state is preserved
    merged_destinations = base_fields["destinations"]
    merged_travel_dates = base_fields["travel_dates"]
    merged_traveler_count = base_fields["traveler_count"]
    merged_room_sharing = base_fields["room_sharing"]

    # Check if user wants the system to decide remaining preferences
    skip_prefs = _user_wants_skip(raw_input)

    # Build merged result for clarification check
    merged_result = IngestionResult(
        destinations=merged_destinations or None,
        travel_dates=merged_travel_dates or None,
        traveler_count=merged_traveler_count,
        preferences=base_fields.get("preferences"),
        room_sharing=merged_room_sharing,
        bed_type_preference=base_fields.get("bed_type_preference"),
        accommodation_tier=base_fields.get("accommodation_tier"),
        accommodation_type=base_fields.get("accommodation_type"),
        activity_intensity=base_fields.get("activity_intensity"),
    )
    clarification = await _build_clarification_response(
        merged_result, clarification_round, raw_input=raw_input
    )

    if clarification.get("needs_clarification"):
        # If user said "you decide" but critical fields are present, skip preferences
        if skip_prefs and merged_destinations and merged_travel_dates:
            pass  # fall through to feasibility checks
        else:
            # Clear confirmation flags so frontend shows clarification, not read-back
            base_fields["awaiting_confirmation"] = False
            base_fields["confirmation_summary"] = None
            return {**base_fields, **clarification, "clarification_round": clarification_round + 1}

    # Build merged IngestionResult for feasibility checks
    merged_for_checks = IngestionResult(
        destinations=merged_destinations or None,
        travel_dates=merged_travel_dates or None,
        traveler_count=merged_traveler_count,
        preferences=base_fields.get("preferences"),
        origin=base_fields.get("origin"),
    )
    rejection = _check_rule_based_feasibility(merged_for_checks)
    if rejection:
        return {**base_fields, "is_feasible": False, "feasibility_rejection_reason": rejection}

    # Soft warning for mainland China destinations (Google Search grounding may be limited)
    if merged_destinations:
        for dest in merged_destinations:
            city = (dest.get("city") or "").lower()
            country = (dest.get("country") or "").lower()
            if city in BLOCKED_DESTINATIONS or country == "china":
                display_name = dest.get("city") or dest.get("country") or "That destination"
                warning = (
                    f" [Warning: {display_name} is in mainland China — "
                    "Google Search grounding may be unavailable, "
                    "so flight/hotel results may be less accurate]"
                )
                base_fields["extraction_notes"] = (
                    (base_fields.get("extraction_notes") or "") + warning
                )
                break  # one warning is enough

    # soft warning when there are many destinations squeezed into a short trip
    if merged_destinations and len(merged_destinations) >= 4 and merged_travel_dates:
        try:
            start = date.fromisoformat(merged_travel_dates.get("start", ""))
            end = date.fromisoformat(merged_travel_dates.get("end", ""))
            duration = (end - start).days
            if duration < 7:
                warning = (
                    f" [Note: {len(merged_destinations)} destinations in {duration} days "
                    "may be ambitious]"
                )
                base_fields["extraction_notes"] = (
                    (base_fields.get("extraction_notes") or "") + warning
                )
        except (ValueError, TypeError):
            pass

    # Read-back confirmation: apply defaults (lowercase to match IngestionResult literals)
    if not base_fields.get("accommodation_tier"):
        base_fields["accommodation_tier"] = "mid-range"
    if not base_fields.get("activity_intensity"):
        base_fields["activity_intensity"] = "moderate"

    summary = _build_confirmation_summary(base_fields)
    return {
        **base_fields,
        "awaiting_confirmation": True,
        "confirmation_summary": summary,
    }
