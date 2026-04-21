MEAL_SEARCH_PROMPT = """CRITICAL RULES (read these first):
1. Find REAL restaurants that currently exist — use Google Search to verify
2. Restaurants MUST be IN THE SAME CITY as that day's activities (reachable within 10-15 min)
   NEVER suggest restaurants in a different city or country from the day's activities.
3. Include cuisine type, approximate price per person in SGD, and full address
4. For each restaurant, provide the Google Maps place name so it can be looked up
5. Return 4-5 options per meal slot — prioritise places that are popular with
   food reviewers, highly rated on Google Maps, or famous local specialities.
   Include a mix of budget and mid-range options.
6. Every restaurant MUST have a real, verifiable name. Do NOT return "Unknown" or
   placeholder names. If you cannot find enough restaurants, return fewer options.

TASK:
Find restaurant options for each day of this trip.

TRIP CONTEXT:
- Destinations: {DESTINATIONS}
- Activities by day: {ACTIVITIES_BY_DAY}
- Meal preferences: {MEAL_PREFERENCES}
- Traveler count: {TRAVELER_COUNT}

For each day, suggest 4-5 restaurants for LUNCH and DINNER that are:
- Located IN THE SAME CITY as that day's activities (check the city in parentheses)
- Near that day's planned activities (within 10-15 min by foot or transit)
- Popular with food reviewers or well-known local favourites
- Matching the traveler's cuisine preferences
- Currently operating (verify via Google Search)

OUTPUT FORMAT (strict JSON):
{{
  "meal_slots": [
    {{
      "day_number": 1,
      "meal_type": "lunch",
      "options": [
        {{
          "name": "Restaurant Name",
          "cuisine_type": "Japanese",
          "price_range": "$$",
          "address": "Full address",
          "proximity_note": "5 min walk from Sensoji Temple"
        }}
      ]
    }}
  ]
}}
"""
