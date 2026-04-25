
from pydantic import BaseModel
from typing import Union, Literal

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
