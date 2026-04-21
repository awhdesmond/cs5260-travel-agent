CRITIC_LLM_PROMPT = """You are a travel plan critic reviewing a trip itinerary.

## Deterministic Violations Found
{VIOLATIONS}

## Travel Plan Summary
- Destination(s): {DESTINATIONS}
- Travel dates: {TRAVEL_DATES}
- Total scheduled cost: SGD {DAILY_SCHEDULE_COST}
- Traveler count: {TRAVELER_COUNT}

## Itinerary Overview
{ITINERARY_SUMMARY}

## Your Task

{TASK_INSTRUCTIONS}

## Output Format
Return ONLY a JSON object:
{OUTPUT_SCHEMA}
"""

# Mode A: violations exist — produce actionable suggestions
TASK_INSTRUCTIONS_VIOLATIONS = (
    "For each violation, provide a specific, actionable suggestion. "
    "Be concrete: name specific alternatives, identify which activities "
    "to move or remove."
)

OUTPUT_SCHEMA_VIOLATIONS = """{
  "summary": "<human-readable summary of all issues>",
  "quality_suggestions": [
    {
      "category": "geographic | time_conflict | logistics",
      "suggestion": "<specific actionable suggestion>",
      "day_number": "<int or null if general>"
    }
  ]
}"""

# Mode B: no violations — produce quality_suggestions
TASK_INSTRUCTIONS_CLEAN = (
    "The plan passed all validation checks. Provide a brief quality review with "
    "soft suggestions for improvement. Focus on: schedule pacing (is any day too "
    "packed?), activity diversity, meal variety, and overall flow. These are "
    "suggestions only and will NOT trigger re-planning."
)

OUTPUT_SCHEMA_CLEAN = """{
  "summary": "<brief quality assessment>",
  "quality_suggestions": [
    {
      "category": "pacing | diversity | meals | logistics | experience",
      "suggestion": "<specific suggestion>",
      "day_number": "<int or null if general>"
    }
  ]
}"""
