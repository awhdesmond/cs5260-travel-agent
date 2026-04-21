EDIT_ITINERARY_PROMPT = """CRITICAL RULES (read these first):
1. You are editing an EXISTING travel itinerary based on a user request
2. Make ONLY the specific change requested -- do not modify other parts
3. If swapping a restaurant, find a REAL restaurant nearby using Google Search
4. If adjusting times, ensure no time block overlaps are created
5. Return the COMPLETE updated itinerary JSON (not just the changed part)
6. Preserve all existing fields and structure exactly

CURRENT ITINERARY:
{ITINERARY_JSON}

USER EDIT REQUEST:
{EDIT_REQUEST}

Return the complete updated itinerary JSON with the requested change applied.
Keep all existing days, time slots, costs, and notes that are not affected by the edit.
"""
