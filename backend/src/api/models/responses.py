from typing import Literal

from pydantic import BaseModel


class BookingConfirmation(BaseModel):
    """Booking confirmation response based on booking mode."""

    mode: Literal["search_recommend", "sandbox"]
    confirmation_id: str | None = None
    message: str
    booking_links: list[dict] | None = None
    price_disclaimer: str | None = None


class RunMetrics(BaseModel):
    """Metrics collected during a plan execution run."""

    latency_ms: int
    total_tokens: int
    estimated_cost_sgd: float
    llm_call_count: int
    conflicts_detected: int


class PlanResponse(BaseModel):
    """Response body for POST /plan endpoint."""

    itinerary: dict | None
    mode: str
    booking_mode: str
    thread_id: str
    plan_id: str | None = None
    status: str = "pending_approval"
    metrics: RunMetrics | None = None
    booking: BookingConfirmation | None = None
    needs_clarification: bool = False
    clarification_questions: list[str] | None = None
    is_feasible: bool = True
    feasibility_rejection_reason: str | None = None
