from typing import Annotated, Optional, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

class TravelBlackboard(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]

    # Ingestion metadata
    raw_input: str              # Original user input text/URL/image path
    input_type: str             # TEXT, IMAGE, or URL
    low_confidence_fields: list[str]  # Field names with uncertain extractions
    preferences: list[str]      # Extracted travel preferences

    # Core user constraints
    travel_dates: dict          # {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}
    destination: str            # Primary destination string (backward compat)
    traveler_count: int

    # Multi-city destinations
    destinations: list[dict]    # [{"city": str, "country": str, "order": int}]

    # Structured preferences
    trip_style: Optional[str]           # "relaxation" | "adventure" | "cultural" | "mixed"
    trip_style_notes: Optional[str]
    activity_intensity: Optional[str]   # "low" | "moderate" | "high"
    accommodation_tier: Optional[str]   # "budget" | "mid-range" | "luxury"
    accommodation_type: Optional[str]   # "hotel" | "hostel" | "resort" | "apartment"
    room_sharing: Optional[str]         # "shared" | "separate"
    bed_type_preference: Optional[str]
    additional_preferences: list[str]

    # Clarification flow
    needs_clarification: bool
    clarification_questions: Optional[list[str]]
    clarification_round: int

    # Feasibility gate
    is_feasible: bool
    feasibility_rejection_reason: Optional[str]

    # Origin city
    origin: Optional[str]

    # Planning mode
    planning_mode: str                  # "auto" | "choose"
    planning_mode_max_options: int      # Default 3, max 10

    # Per-domain plan outputs (None until respective agent writes)
    transport_plan: Optional[dict]
    accommodation_plan: Optional[dict]
    activities_plan: Optional[dict]
    intercity_transport_plan: Optional[dict]

    # Critic Agent outputs
    critic_feedback: Optional[dict | str]
    itinerary: Optional[dict]

    retry_count: int
    daily_schedule_cost: Optional[float]
    quality_suggestions: Optional[list[dict]]

    cache_hit: bool
    cached_activities: Optional[dict]

    # Meal pipeline fields (Pass 2 Stage A/B) -- must be declared here so pass2_graph
    # (compiled with TravelBlackboard) preserves them through LangGraph state initialization.
    # Without these declarations, LangGraph drops them as unknown keys, causing Day Planner
    # to run without meal context and produce null itinerary.
    meal_preferences: Optional[list[str]]   # User meal preferences extracted by ingestion
    meal_options: Optional[list[dict]]      # Generated meal options per day/slot (Stage A)
    selected_meals: Optional[list[dict]]    # User's meal selections (Stage B -> Day Planner)

    # Read-back confirmation (user reviews extracted params before pipeline starts)
    awaiting_confirmation: Optional[bool]
    confirmation_summary: Optional[list[str]]
