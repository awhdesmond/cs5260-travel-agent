_COMMON_FIELDS = """Fields to extract (all optional unless stated):
- destinations (REQUIRED if identifiable): [{{"city": "...", "country": "...", "order": N}}]
  IMPORTANT: "city" must be an actual city, NOT a province/state/region (e.g. Yunnan, Hokkaido, Bavaria).
  If user names a region/province, break it into popular cities (e.g. "Yunnan" -> Kunming, Dali, Lijiang).
  If unsure which cities, leave "city" empty and set the "country" so clarification is triggered.
- travel_dates: {{"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}} (Infer year as 2026. If dates are ambiguous like "summer" or "next week", MAKE A REASONABLE GUESS for the exact dates that are later than today, and add "travel_dates" to low_confidence_fields)
- traveler_count: number of travelers
- trip_style: "relaxation" | "adventure" | "cultural" | "mixed"
- trip_style_notes: context if enum insufficient
- activity_intensity: "low" | "moderate" | "high"
- accommodation_tier: "budget" | "mid-range" | "luxury"
- accommodation_type: "hotel" | "hostel" | "resort" | "apartment"
- room_sharing: "shared" | "separate" (only if traveler_count > 1 and stated)
- bed_type_preference: free text
- additional_preferences: anything not captured above
- preferences: tags (e.g. ["food", "culture", "nightlife"])
- origin: departure city (null if not mentioned, defaults to Singapore)"""

TEXT_EXTRACTION_PROMPT: str = (
    "Extract travel planning information from this text.\n\n"
    "CRITICAL: Set needs_clarification=true only if destination OR travel dates are COMPLETELY missing.\n"
    "If dates are ambiguous, make a reasonable guess, add them to low_confidence_fields, and DO NOT set needs_clarification=true.\n"
    "Mark uncertain fields in low_confidence_fields. Note currency conversions in extraction_notes.\n\n"
    "Text: {text}\n\n"
    + _COMMON_FIELDS
)

IMAGE_EXTRACTION_PROMPT: str = (
    "Analyze this image for travel intent.\n\n"
    "CRITICAL: Set needs_clarification=true if not travel-related.\n"
    "Mark ALL uncertain fields in low_confidence_fields (images are inherently uncertain).\n"
    "travel_dates is typically null for images.\n\n"
    + _COMMON_FIELDS
    + "\n\nIf not travel-related, set destinations to null and note in extraction_notes."
)

URL_EXTRACTION_PROMPT: str = (
    "Extract travel planning information from this scraped web page.\n\n"
    "CRITICAL: Set needs_clarification=true if no extractable travel information.\n"
    "Mark uncertain fields in low_confidence_fields. Note currency conversions in extraction_notes.\n\n"
    "Page URL: {url}\nPage Title: {title}\nContent:\n{content}\n\n{partial_warning}\n\n"
    + _COMMON_FIELDS
)
