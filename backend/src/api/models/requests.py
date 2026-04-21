from typing import Literal, Optional
from pydantic import BaseModel

class PlanRequest(BaseModel):
    user_input: str
    mode: Literal["supervisor", "swarm"]
    booking_mode: Literal["search_recommend", "sandbox"] = "search_recommend"
    thread_id: Optional[str] = None


class ConfirmRequest(BaseModel):
    booking_mode: Literal["search_recommend", "sandbox"]


class PlanSelectRequest(BaseModel):
    selected_outbound_flight_id: Optional[str] = None
    selected_inbound_flight_id: Optional[str] = None
    selected_hotel_ids: dict[str, str] = {}  # city -> hotel option id
    selected_activity_ids: list[str] = []
    selected_intercity_ids: dict[str, str] = {}  # "CityA->CityB" -> option identifier


class MealSelectRequest(BaseModel):
    selected_meals: list[dict] = []  # [{day_number, meal_type, selected_name}]
    auto_select: bool = False  # True = "just pick for me"
