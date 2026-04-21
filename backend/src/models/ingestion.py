import re
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

class InputType(str, Enum):
    TEXT = "TEXT"


class IngestionResult(BaseModel):
    """Unified ingestion output schema for all input types."""

    destination: Optional[str] = Field(
        default=None,
        description="Primary travel destination (city, country, or region). Be specific: 'Tokyo, Japan' not just 'Japan'."
    )

    destinations: Optional[list[dict]] = Field(
        default=None,
        description="Ordered list of destinations: [{'city': 'Tokyo', 'country': 'Japan', 'order': 1}, ...]. If only one city, return a single-element list. Preserve travel order as stated by user."
    )

    travel_dates: Optional[dict] = Field(
        default=None,
        description="Travel date range: {'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD'}. Always use ISO 8601 format. Infer year as 2026 if not specified.",
    )

    traveler_count: Optional[int] = Field(
        default=None,
        ge=1,
        description="Number of travelers. Default to 1 if unspecified.",
    )

    preferences: Optional[list[str]] = Field(
        default=None,
        description="Travel preferences: e.g., ['beach', 'hiking', 'food tours', 'budget-friendly']",
    )

    trip_style: Optional[Literal["relaxation", "adventure", "cultural", "mixed"]] = Field(
        default=None,
        description="Overall trip vibe: relaxation, adventure, cultural, or mixed.",
    )

    trip_style_notes: Optional[str] = Field(
        default=None,
        description="Additional nuance about trip style not captured by the enum.",
    )

    activity_intensity: Optional[Literal["low", "moderate", "high"]] = Field(
        default=None,
        description="Preferred activity pace: low (relaxed), moderate (balanced), high (packed schedule).",
    )

    accommodation_tier: Optional[Literal["budget", "mid-range", "luxury"]] = Field(
        default=None,
        description="Accommodation price tier preference.",
    )

    accommodation_type: Optional[Literal["hotel", "hostel", "resort", "apartment"]] = Field(
        default=None,
        description="Preferred accommodation type.",
    )

    room_sharing: Optional[Literal["shared", "separate"]] = Field(
        default=None,
        description="Room sharing preference for multi-traveler trips.",
    )

    bed_type_preference: Optional[str] = Field(
        default=None,
        description="Bed type preference (e.g., 'twin beds', 'double bed', 'adjoining rooms').",
    )

    additional_preferences: Optional[list[str]] = Field(
        default=None,
        description="Free-text preferences that don't fit predefined categories.",
    )

    origin: Optional[str] = Field(
        default=None,
        description="City of origin for flights, extracted from user input (e.g., 'flying from KL'). Defaults to 'Singapore' if not specified.",
    )

    needs_clarification: bool = Field(
        default=False,
        description="Set True only when critical fields (destination or dates) cannot be extracted.",
    )

    clarification_questions: Optional[list[str]] = Field(
        default=None,
        description="Questions to ask the user when needs_clarification=True.",
    )

    is_feasible: bool = Field(
        default=True,
        description="Set False when the request fails feasibility checks.",
    )

    feasibility_rejection_reason: Optional[str] = Field(
        default=None,
        description="Human-readable explanation when is_feasible=False, with constructive suggestion.",
    )

    low_confidence_fields: list[str] = Field(
        default_factory=list,
        description="List field names where extraction confidence is low.",
    )

    extraction_notes: Optional[str] = Field(
        default=None,
        description="Notes about extraction quality, currency conversions applied, or missing info.",
    )

    @field_validator("travel_dates", mode="before")
    @classmethod
    def validate_travel_dates(cls, v: Optional[dict]) -> Optional[dict]:
        """
        Validate travel_dates has ISO 8601 start/end keys.
        """
        if v is None:
            return None

        if not isinstance(v, dict):
            return None

        if "start" not in v or "end" not in v:
            return None

        iso_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")

        start = v.get("start")
        end = v.get("end")

        if not isinstance(start, str) or not isinstance(end, str):
            return None

        if not iso_pattern.match(start) or not iso_pattern.match(end):
            return None

        return v
