from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.routes.plan import process_booking_mode_from_plans
from src.agents.shared import enrich_itinerary_coords
from src.utils.jwt import get_current_user
from src.db.repository import get_itinerary_by_id, get_user_itineraries, save_itinerary

router = APIRouter()


class SaveItineraryRequest(BaseModel):
    destination: str
    travel_dates: dict | None = None
    architecture: str
    itinerary: dict[str, Any]


class SaveItineraryResponse(BaseModel):
    id: str


class ItineraryListItem(BaseModel):
    id: str
    destination: str
    travel_dates: dict | None = None
    architecture: str
    status: str = "pending_approval"
    created_at: str


class ItineraryDetail(BaseModel):
    id: str
    destination: str
    travel_dates: dict | None = None
    architecture: str
    itinerary: dict[str, Any]
    status: str = "pending_approval"
    booking_confirmation_id: str | None = None
    created_at: str
    booking_links: list[dict] | None = None


@router.get("", response_model=list[ItineraryListItem])
async def list_itineraries(user: dict = Depends(get_current_user)):
    user_id = user["sub"]
    items = get_user_itineraries(user_id)
    return items


@router.post("", response_model=SaveItineraryResponse, status_code=201)
async def create_itinerary(
    body: SaveItineraryRequest, user: dict = Depends(get_current_user)
):
    user_id = user["sub"]
    itinerary_id = save_itinerary(
        user_id=user_id,
        destination=body.destination,
        travel_dates=body.travel_dates,
        architecture=body.architecture,
        itinerary=body.itinerary,
    )
    if itinerary_id is None:
        raise HTTPException(status_code=503, detail="Database not available")
    return SaveItineraryResponse(id=itinerary_id)


@router.get("/{itinerary_id}", response_model=ItineraryDetail)
async def get_itinerary(
    itinerary_id: str, user: dict = Depends(get_current_user)
):
    user_id = user["sub"]
    record = get_itinerary_by_id(itinerary_id, user_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Itinerary not found")

    # Enrich time_slots with lat/lng from embedded plans before returning
    if isinstance(record, dict) and record.get("itinerary"):
        enrich_itinerary_coords(record["itinerary"])

    # Generate booking links for confirmed itineraries from stored plans
    status = record.get("status", "")
    if status in ("confirmed", "sandbox_confirmed") and isinstance(record.get("itinerary"), dict):

        itin = record["itinerary"]
        plans = itin.get("plans") or {}
        mode = "sandbox" if status == "sandbox_confirmed" else "search_recommend"
        confirmation = process_booking_mode_from_plans(plans, mode, record.get("booking_confirmation_id"), itinerary_data=itin)
        record["booking_links"] = confirmation.booking_links

    return record
