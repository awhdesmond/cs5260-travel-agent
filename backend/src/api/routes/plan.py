import logging
import time
import uuid
from datetime import date as _date

from fastapi import APIRouter, Depends, HTTPException, Request
from langchain_core.callbacks.usage import UsageMetadataCallbackHandler
from langchain_core.messages import HumanMessage

from src.api.models.requests import ConfirmRequest, PlanRequest
from src.api.models.responses import BookingConfirmation, PlanResponse, RunMetrics
from src.utils.jwt import get_current_user
from src.db.repository import insert_run, save_itinerary, get_itinerary_by_id, update_itinerary_status
from src.utils.guards import check_token_budget

router = APIRouter()


def make_initial_state(user_input: str) -> dict:
    """
    Create initial TravelBlackboard state for graph invocation.
    """
    return {
        "messages": [HumanMessage(content=user_input)],
        "raw_input": user_input,
        "input_type": "TEXT",
        "low_confidence_fields": [],
        "preferences": [],
        "additional_preferences": [],
        "travel_dates": None,
        "destination": "",
        "destinations": [],
        "traveler_count": 1,
        "trip_style": None,
        "trip_style_notes": None,
        "activity_intensity": None,
        "accommodation_tier": None,
        "accommodation_type": None,
        "room_sharing": None,
        "bed_type_preference": None,
        "needs_clarification": False,
        "clarification_questions": None,
        "clarification_round": 0,
        "is_feasible": True,
        "feasibility_rejection_reason": None,
        "planning_mode": "choose",
        "planning_mode_max_options": 5,
        "origin": "Singapore",
        "retry_count": 0,
        "cache_hit": False,
        "intercity_transport_plan": None,
        "daily_schedule_cost": None,
        "quality_suggestions": None,
        "transport_plan": None,
        "accommodation_plan": None,
        "activities_plan": None,
        "critic_feedback": None,
        "itinerary": None,
        # Meal pipeline fields (Pass 2)
        "meal_preferences": None,
        "meal_options": None,
        "selected_meals": None,
        # Read-back confirmation
        "awaiting_confirmation": False,
        "confirmation_summary": None,
    }


def process_booking_mode(itinerary: dict | None, booking_mode: str) -> BookingConfirmation:
    """
    Generate BookingConfirmation from final itinerary dict.

    search_recommend: extract booking links from itinerary components.
    sandbox: return simulated confirmation with SANDBOX prefix.
    """
    if itinerary is None:
        return BookingConfirmation(
            mode=booking_mode,  # type: ignore[arg-type]
            message="No itinerary generated.",
            booking_links=None,
        )

    if booking_mode == "search_recommend":
        booking_links: list[dict] = []

        transport = itinerary.get("transport") or {}
        if transport.get("outbound_flight", {}).get("booking_link"):
            booking_links.append({
                "type": "flight_outbound",
                "description": f"Outbound flight - {transport['outbound_flight'].get('airline', 'Unknown')}",
                "url": transport["outbound_flight"]["booking_link"],
            })
        if transport.get("return_flight", {}).get("booking_link"):
            booking_links.append({
                "type": "flight_return",
                "description": f"Return flight - {transport['return_flight'].get('airline', 'Unknown')}",
                "url": transport["return_flight"]["booking_link"],
            })

        accommodation = itinerary.get("accommodation") or {}
        if accommodation.get("hotel", {}).get("booking_link"):
            booking_links.append({
                "type": "hotel",
                "description": f"Hotel - {accommodation['hotel'].get('name', 'Unknown')}",
                "url": accommodation["hotel"]["booking_link"],
            })

        activities = itinerary.get("activities") or {}
        for activity in activities.get("items", []):
            if activity.get("booking_link"):
                booking_links.append({
                    "type": "activity",
                    "description": f"Activity - {activity.get('name', 'Unknown')}",
                    "url": activity["booking_link"],
                })

        return BookingConfirmation(
            mode="search_recommend",
            message="Your itinerary is ready. Use the booking links below to complete your reservations.",
            booking_links=booking_links if booking_links else None,
        )

    else:  # sandbox
        confirmation_id = f"SANDBOX-{uuid.uuid4().hex[:8].upper()}"
        return BookingConfirmation(
            mode="sandbox",
            confirmation_id=confirmation_id,
            message=f"[SANDBOX] Booking simulation complete. Confirmation: {confirmation_id}. No real transactions were processed.",
            booking_links=None,
        )


def _ticket_search_url(name: str, city: str) -> str:
    """Generate a Klook search URL for an activity that may require tickets."""
    from urllib.parse import quote
    return f"https://www.klook.com/search/?query={quote(name + ' ' + city)}"


def _flight_search_url(origin: str, destination: str, date_str: str | None) -> str:
    """Generate a Google Flights natural-language search URL.

    Google Flights reliably parses: flights from Singapore to Hong Kong on 2026-04-13
    """
    from urllib.parse import quote
    query = f"flights from {origin} to {destination}"
    if date_str:
        query += f" on {date_str}"
    return f"https://www.google.com/travel/flights?q={quote(query)}"


def process_booking_mode_from_plans(
    plans: dict | None, booking_mode: str, confirmation_id: str | None = None,
    itinerary_data: dict | None = None,
) -> BookingConfirmation:
    """Generate BookingConfirmation from domain plan dicts (TransportPlan/AccommodationPlan shapes).

    Walks outbound_flights, cities[].options[], cities[].options_per_day[][] to extract booking links.
    Enriches each link with image_url, price, city for card-style frontend rendering.
    itinerary_data: full itinerary dict (includes days[]) for extracting origin/destination.
    """
    if plans is None:
        return BookingConfirmation(
            mode=booking_mode,  # type: ignore[arg-type]
            message="No plans available for booking.",
            booking_links=None,
        )

    # Extract origin and destination cities from the day schedule
    origin = "Singapore"  # default
    first_city = ""
    last_city = ""
    first_date = ""
    last_date = ""
    if itinerary_data:
        days = itinerary_data.get("days") or []
        if days:
            first_city = days[0].get("city", "") if isinstance(days[0], dict) else ""
            last_city = days[-1].get("city", "") if isinstance(days[-1], dict) else ""
            first_date = days[0].get("date", "") if isinstance(days[0], dict) else ""
            last_date = days[-1].get("date", "") if isinstance(days[-1], dict) else ""

    booking_links: list[dict] = []
    seen_activities: set[str] = set()  # dedupe across days

    transport = plans.get("transport_plan") or {}
    for flight in transport.get("outbound_flights", []):
        if not isinstance(flight, dict):
            continue
        airline = flight.get("airline", "Unknown")
        dep_date = (flight.get("departure_time") or "")[:10] or first_date
        url = flight.get("booking_link") or _flight_search_url(origin, first_city or "destination", dep_date or None)
        booking_links.append({
            "type": "flight_outbound",
            "description": f"Outbound — {airline}",
            "subtitle": f"{origin} -> {first_city}" if first_city else (flight.get("flight_number") or ""),
            "url": url,
            "image_url": flight.get("image_url"),
            "price_label": f"SGD {flight['price_sgd']:.0f}" if flight.get("price_sgd") else None,
        })
    for flight in transport.get("inbound_flights", []):
        if not isinstance(flight, dict):
            continue
        airline = flight.get("airline", "Unknown")
        dep_date = (flight.get("departure_time") or "")[:10] or last_date
        url = flight.get("booking_link") or _flight_search_url(last_city or "destination", origin, dep_date or None)
        booking_links.append({
            "type": "flight_return",
            "description": f"Return — {airline}",
            "subtitle": f"{last_city} -> {origin}" if last_city else (flight.get("flight_number") or ""),
            "url": url,
            "image_url": flight.get("image_url"),
            "price_label": f"SGD {flight['price_sgd']:.0f}" if flight.get("price_sgd") else None,
        })

    accommodation = plans.get("accommodation_plan") or {}
    for city_obj in accommodation.get("cities", []):
        if not isinstance(city_obj, dict):
            continue
        city_name = city_obj.get("city", "")
        for option in city_obj.get("options", []):
            if not isinstance(option, dict):
                continue
            if option.get("booking_link"):
                booking_links.append({
                    "type": "hotel",
                    "description": option.get("name", "Hotel"),
                    "subtitle": city_name,
                    "url": option["booking_link"],
                    "image_url": option.get("image_url"),
                    "price_label": (
                        f"SGD {option['price_per_night_sgd']:.0f}/night"
                        if option.get("price_per_night_sgd") else None
                    ),
                })

    activities = plans.get("activities_plan") or {}
    for city_obj in activities.get("cities", []):
        if not isinstance(city_obj, dict):
            continue
        city_name = city_obj.get("city", "")
        for day_options in city_obj.get("options_per_day", []):
            if not isinstance(day_options, list):
                continue
            for activity in day_options:
                if not isinstance(activity, dict):
                    continue
                name = activity.get("name", "")
                if not name or name in seen_activities:
                    continue
                seen_activities.add(name)
                needs_ticket = activity.get("booking_required", False)
                url = activity.get("booking_link") or (
                    _ticket_search_url(name, city_name) if needs_ticket else None
                )
                if url:
                    booking_links.append({
                        "type": "activity",
                        "description": name,
                        "subtitle": city_name,
                        "url": url,
                        "image_url": activity.get("image_url"),
                        "price_label": (
                            f"SGD {activity['estimated_cost_sgd']:.0f}"
                            if activity.get("estimated_cost_sgd") else None
                        ),
                    })

    intercity = plans.get("intercity_transport_plan") or {}
    for hop in intercity.get("hops", []):
        if not isinstance(hop, dict):
            continue
        for option in hop.get("options", []):
            if isinstance(option, dict) and option.get("booking_link"):
                booking_links.append({
                    "type": "intercity",
                    "description": f"{hop.get('from_city', '')} -> {hop.get('to_city', '')}",
                    "subtitle": f"{option.get('mode', 'Transport')} — {option.get('operator', '')}".strip(" —"),
                    "url": option["booking_link"],
                    "price_label": f"SGD {option['price_sgd']:.0f}" if option.get("price_sgd") else None,
                })

    if booking_mode == "sandbox" and confirmation_id:
        return BookingConfirmation(
            mode="sandbox",
            confirmation_id=confirmation_id,
            message=(
                f"SANDBOX MODE — no real transactions were processed. "
                f"Confirmation: {confirmation_id}"
            ),
            booking_links=booking_links if booking_links else None,
            price_disclaimer="Prices are indicative, verified at search time. Actual prices may vary.",
        )

    return BookingConfirmation(
        mode="search_recommend",  # type: ignore[arg-type]
        message="Your itinerary is ready. Use the booking links below to complete your reservations.",
        booking_links=booking_links if booking_links else None,
        price_disclaimer="Prices are indicative, verified at search time. Actual prices may vary.",
    )


@router.post("/plan", response_model=PlanResponse)
async def create_plan(
    request: Request, plan_request: PlanRequest, user: dict = Depends(get_current_user)
):
    """
    Create a travel plan using Supervisor or Swarm orchestration.
    """
    user_id = user["sub"]
    mode = plan_request.mode
    if mode == "supervisor":
        graph = getattr(request.app.state, "supervisor_graph", None)
        rec_limit = getattr(request.app.state, "supervisor_recursion_limit", 100)
    else:
        graph = getattr(request.app.state, "swarm_graph", None)
        rec_limit = getattr(request.app.state, "swarm_recursion_limit", 50)
    if graph is None:
        raise HTTPException(
            status_code=503,
            detail="Planning service unavailable — graph not initialized",
        )

    ok, tokens = check_token_budget(plan_request.user_input)
    if not ok:
        raise HTTPException(
            status_code=400, detail=f"Request too large ({tokens} tokens)"
        )

    initial_state = make_initial_state(plan_request.user_input)
    thread_id = str(uuid.uuid4())

    callback = UsageMetadataCallbackHandler()
    config = {
        "configurable": {"thread_id": thread_id},
        "callbacks": [callback],
        "recursion_limit": rec_limit,
    }

    start_time = time.perf_counter()
    result: dict = {}
    async for chunk in graph.astream(initial_state, config=config, stream_mode="values"):
        result = chunk  # Each chunk is full accumulated state; last is final
    latency_ms = int((time.perf_counter() - start_time) * 1000)

    if not result.get("is_feasible", True):
        return PlanResponse(
            itinerary=None,
            mode=plan_request.mode,
            booking_mode=plan_request.booking_mode,
            thread_id=thread_id,
            is_feasible=False,
            feasibility_rejection_reason=result.get("feasibility_rejection_reason"),
            metrics=RunMetrics(
                latency_ms=latency_ms,
                total_tokens=0,
                estimated_cost_sgd=0.0,
                llm_call_count=0,
                conflicts_detected=0,
            ),
            booking=BookingConfirmation(
                mode=plan_request.booking_mode,
                message="Request not feasible.",
            ),
        )

    if result.get("needs_clarification"):
        return PlanResponse(
            itinerary=None,
            mode=plan_request.mode,
            booking_mode=plan_request.booking_mode,
            thread_id=thread_id,
            needs_clarification=True,
            clarification_questions=result.get("clarification_questions", []),
            metrics=RunMetrics(
                latency_ms=latency_ms,
                total_tokens=0,
                estimated_cost_sgd=0.0,
                llm_call_count=0,
                conflicts_detected=0,
            ),
            booking=BookingConfirmation(
                mode=plan_request.booking_mode,
                message="Clarification needed.",
            ),
        )

    usage = callback.usage_metadata
    total_tokens = (
        sum(m.get("total_tokens", 0) for m in usage.values()) if usage else 0
    )
    llm_call_count = len(usage) if usage else 0

    # Gemini 2.0 Flash avg $0.25/1M tokens, 1.35 USD->SGD
    estimated_cost_sgd = (total_tokens / 1_000_000) * 0.25 * 1.35

    critic_feedback = result.get("critic_feedback")
    if isinstance(critic_feedback, dict):
        conflicts_detected = len(critic_feedback.get("violations", []))
    else:
        conflicts_detected = 0

    cache_hit = result.get("cache_hit", False)
    retry_count = result.get("retry_count", 0)
    success = result.get("itinerary") is not None
    traveler_count = result.get("traveler_count", 1)

    travel_dates_val = result.get("travel_dates") or {}
    trip_days = None
    if travel_dates_val.get("start") and travel_dates_val.get("end"):
        try:
            trip_days = (
                _date.fromisoformat(travel_dates_val["end"])
                - _date.fromisoformat(travel_dates_val["start"])
            ).days
        except ValueError:
            pass

    destinations_list = result.get("destinations") or []
    num_cities = len(destinations_list) if destinations_list else None

    try:
        insert_run(
            {
                "user_id": user_id,
                "architecture": plan_request.mode,
                "booking_mode": plan_request.booking_mode,
                "latency_ms": latency_ms,
                "total_tokens": total_tokens,
                "estimated_cost_sgd": float(estimated_cost_sgd),
                "llm_call_count": llm_call_count,
                "conflicts_detected": conflicts_detected,
                "destination": (
                    result.get("destination")
                    or (
                        f"{result['destinations'][0]['city']}, {result['destinations'][0]['country']}"
                        if result.get("destinations") else ""
                    )
                ),
                "travel_dates": result.get("travel_dates"),
                "cache_hit": cache_hit,
                "retry_count": retry_count,
                "success": success,
                "traveler_count": traveler_count,
                "trip_days": trip_days,
                "num_cities": num_cities,
            }
        )
    except Exception as db_err:
        logging.getLogger(__name__).warning("DB insert_run failed (non-fatal): %s", db_err)

    # Embed domain plans in itinerary JSONB for booking link recovery at confirm time
    itinerary_data = result.get("itinerary")
    plan_id = None
    if itinerary_data is not None:
        itinerary_with_plans = {
            **(itinerary_data if isinstance(itinerary_data, dict) else {}),
            "plans": {
                "transport_plan": result.get("transport_plan"),
                "accommodation_plan": result.get("accommodation_plan"),
                "activities_plan": result.get("activities_plan"),
            },
        }
        try:
            plan_id = save_itinerary(
                user_id=user_id,
                destination=result.get("destination", ""),
                travel_dates=result.get("travel_dates"),
                architecture=plan_request.mode,
                itinerary=itinerary_with_plans,
            )
        except Exception as save_err:
            logging.getLogger(__name__).warning("save_itinerary failed (non-fatal): %s", save_err)

    metrics = RunMetrics(
        latency_ms=latency_ms,
        total_tokens=total_tokens,
        estimated_cost_sgd=estimated_cost_sgd,
        llm_call_count=llm_call_count,
        conflicts_detected=conflicts_detected,
    )

    booking = process_booking_mode(result.get("itinerary"), plan_request.booking_mode)
    booking.price_disclaimer = "Prices are indicative, verified at search time. Actual prices may vary."

    return PlanResponse(
        itinerary=result.get("itinerary"),
        mode=plan_request.mode,
        booking_mode=plan_request.booking_mode,
        thread_id=thread_id,
        plan_id=plan_id,
        status="pending_approval",
        metrics=metrics,
        booking=booking,
    )


@router.post("/plan/{plan_id}/confirm", response_model=BookingConfirmation)
async def confirm_plan(
    plan_id: str,
    confirm_request: ConfirmRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Confirm a pending plan with chosen booking mode.

    Two-step flow: POST /plan returns itinerary with status 'pending_approval';
    this endpoint confirms it. JWT-protected and user-scoped.

    booking_mode='search_recommend': extracts booking links from plans.
    booking_mode='sandbox': simulates booking with a confirmation ID.

    Raises 404 if plan not found or belongs to different user.
    Raises 409 if plan already confirmed.
    """
    user_id = user["sub"]
    booking_mode = confirm_request.booking_mode

    itinerary_row = get_itinerary_by_id(plan_id, user_id)
    if itinerary_row is None:
        raise HTTPException(status_code=404, detail="Plan not found")

    if itinerary_row.get("status") in ("sandbox_confirmed", "confirmed"):
        raise HTTPException(
            status_code=409,
            detail=f"Plan already confirmed: {itinerary_row.get('booking_confirmation_id', '')}",
        )

    itinerary_data = itinerary_row.get("itinerary") or {}
    plans = itinerary_data.get("plans") or {}

    if booking_mode == "sandbox":
        confirmation_id = f"SBX-{uuid.uuid4().hex[:8].upper()}"
        update_itinerary_status(plan_id, "sandbox_confirmed", confirmation_id)
        return process_booking_mode_from_plans(plans, "sandbox", confirmation_id, itinerary_data=itinerary_data)
    else:
        update_itinerary_status(plan_id, "confirmed", None)
        return process_booking_mode_from_plans(plans, "search_recommend", itinerary_data=itinerary_data)
