from typing import Literal, Optional, Union
from pydantic import BaseModel

class FlightOption(BaseModel):
    airline: str
    price_sgd: float                    # Per person, per leg
    departure_time: str                 # ISO 8601
    arrival_time: str                   # ISO 8601
    booking_link: Optional[str] = None
    verified: bool = False
    stops: int = 0
    duration: Optional[str] = None     # ISO 8601 duration, e.g. "PT7H30M"
    cabin_class: Optional[str] = None  # "economy" | "business" | "first"
    carrier_code: Optional[str] = None  # IATA, e.g. "SQ"
    flight_number: Optional[str] = None  # e.g. "SQ317"
    source: str = "gemini_grounding"    # "gemini_grounding" | "serpapi"
    image_url: Optional[str] = None     # Airline logo or destination image


class TransportPlan(BaseModel):
    """International flight plan"""

    outbound_flights: list[FlightOption] = []
    inbound_flights: list[FlightOption] = []


class HotelOption(BaseModel):
    """Single hotel option"""

    name: str
    price_per_night_sgd: float
    address: str
    star_rating: Optional[float] = None  # e.g. 4.0, 4.5
    booking_link: Optional[str] = None
    verified: bool = False
    room_config: Optional[str] = None   # e.g. "2 twin rooms"
    lat: Optional[float] = None
    lng: Optional[float] = None
    place_id: Optional[str] = None      # For photo lookup
    image_url: Optional[str] = None


class CityAccommodation(BaseModel):
    """Hotel options for a single city"""

    city: str
    nights: Optional[int] = None
    options: list[HotelOption] = []


class AccommodationPlan(BaseModel):
    """Per-city accommodation plan"""

    cities: list[CityAccommodation] = []


class ActivityOption(BaseModel):
    """Single activity or POI option"""

    name: str
    estimated_cost_sgd: float
    opening_hours: Optional[str] = None
    address: Optional[str] = None
    verified: bool = False
    lat: Optional[float] = None
    lng: Optional[float] = None
    place_id: Optional[str] = None
    image_url: Optional[str] = None
    category: Optional[str] = None      # "attraction" | "restaurant" | "experience"
    estimated_duration_minutes: Optional[int] = None
    booking_required: bool = False
    recommended_time_of_day: Optional[str] = None  # "morning" | "afternoon" | "evening"


class CityActivities(BaseModel):
    """Per-day activity options for a single city"""

    city: str
    trip_days: int
    options_per_day: list[list[ActivityOption]] = []  # outer: days, inner: options per slot


class ActivitiesPlan(BaseModel):
    """Per-city activities plan"""

    cities: list[CityActivities] = []


class MealOption(BaseModel):
    """Single restaurant option for a meal slot."""

    name: str
    cuisine_type: Optional[str] = None
    price_range: Optional[str] = None       # e.g. "$", "$$", "$$$"
    address: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    place_id: Optional[str] = None
    image_url: Optional[str] = None
    proximity_note: Optional[str] = None    # e.g. "5 min walk from Sensoji Temple"
    worth_the_travel: bool = False           # Far but proximity-scored above threshold


class MealSlotOptions(BaseModel):
    """Meal options for a single meal slot (lunch/dinner) on a specific day."""

    day_number: int
    meal_type: str                          # "lunch" | "dinner"
    options: list[MealOption] = []


class TimeSlot(BaseModel):
    """One scheduled block within a day."""

    slot_type: Literal["activity", "meal", "buffer", "transit"]
    label: str
    start_time: str             # "HH:MM"
    end_time: Optional[str] = None  # "HH:MM" — optional, LLM may omit for meals
    cost_sgd: float = 0.0
    notes: Optional[str] = None
    activity_name: Optional[str] = None
    address: Optional[str] = None
    booking_required: bool = False
    is_runner_up: bool = False  # For choose mode
    lat: Optional[float] = None
    lng: Optional[float] = None
    image_url: Optional[str] = None
    place_id: Optional[str] = None


class DayPlan(BaseModel):
    """One day in the trip."""

    day_number: int             # 1-based
    date: str                   # "YYYY-MM-DD"
    city: str
    time_slots: list[TimeSlot] = []
    hotel_name: Optional[str] = None
    daily_subtotal_sgd: float = 0.0


class DailySchedule(BaseModel):
    """Complete day-by-day trip schedule."""

    total_days: int
    days: list[DayPlan] = []
    grand_total_sgd: float = 0.0


class InterCityTransportOption(BaseModel):
    """Transport option between consecutive cities"""

    mode: str                               # "train" | "bus" | "domestic_flight" | "ferry"
    price_sgd: float
    duration: Optional[str] = None          # ISO 8601 duration
    operator: Optional[str] = None
    booking_link: Optional[str] = None
    verified: bool = False
    source: str = "gemini_grounding"        # Always gemini_grounding


class InterCityHop(BaseModel):
    """All transport options for a single city-to-city hop."""

    from_city: str
    to_city: str
    options: list[InterCityTransportOption] = []


class InterCityTransportPlan(BaseModel):
    """Inter-city transport plan covering all consecutive city hops"""

    hops: list[InterCityHop] = []


class GeographicViolation(BaseModel):
    """Violation when activity is geographically implausible."""

    type: Literal["geographic_impossibility"] = "geographic_impossibility"
    from_venue: str
    to_venue: str
    reason: str


class TimeBlockViolation(BaseModel):
    """Violation when activities have overlapping time blocks."""

    type: Literal["time_block_conflict"] = "time_block_conflict"
    activity_1: str
    activity_2: str
    overlap_description: str


class EmptyDayViolation(BaseModel):
    """Violation when a non-transit day has < 60% time coverage"""

    type: Literal["empty_day"] = "empty_day"
    day_number: int
    date: str
    coverage_pct: float
    reason: str


class MissingRestaurantViolation(BaseModel):
    """Violation when a meal slot lacks specific restaurant names"""

    type: Literal["missing_restaurant"] = "missing_restaurant"
    day_number: int
    slot_label: str


Violation = Union[
    GeographicViolation,
    TimeBlockViolation,
    EmptyDayViolation,
    MissingRestaurantViolation,
]


class RelaxationSuggestion(BaseModel):
    """Actionable suggestion to resolve a violation."""

    violation_type: str
    action: str
    alternative: str


class CriticFeedback(BaseModel):
    """Summary of all violations and suggestions from Critic Agent."""

    violations: list[dict] = []                  # List of Violation.model_dump() dicts
    relaxation_suggestions: list[dict] = []      # List of RelaxationSuggestion.model_dump()
    is_feasible: bool = True
