import asyncio
import json
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sse_starlette.sse import EventSourceResponse
from langchain_core.messages import HumanMessage

from src.agents.critic import critic_node
from src.agents.meal import meal_generation_node
from src.agents.shared import cache_write_node, day_planner_node_per_day, enrich_itinerary_coords
from src.api.models.requests import MealSelectRequest, PlanSelectRequest
from src.auth.jwt import get_current_user
from src.db.repository import get_plan_options, save_itinerary, save_plan_options, save_thread_state


router = APIRouter()

_AGENT_SUMMARIES: dict[str, str] = {
    "day_planner_node_per_day": "Assembling your itinerary day by day...",
    "critic": "Validating your itinerary...",
    "cache_write": "Saving your itinerary...",
}


def _build_selection_summary(state: dict) -> dict:
    """
    Build a thinking event summarizing what was selected for Pass 2.
    """
    parts: list[str] = []

    transport = state.get("transport_plan")
    if transport and isinstance(transport, dict):
        outbound = transport.get("outbound_flights", [])
        if outbound and isinstance(outbound[0], dict):
            f = outbound[0]
            parts.append(
                f"Flight: {f.get('airline', 'Unknown')} {f.get('flight_number', '')}"
                f" -- SGD {f.get('price_sgd', 0):.0f}"
            )
        inbound = transport.get("inbound_flights", [])
        if inbound and isinstance(inbound[0], dict):
            f = inbound[0]
            parts.append(
                f"Return: {f.get('airline', 'Unknown')} {f.get('flight_number', '')}"
                f" -- SGD {f.get('price_sgd', 0):.0f}"
            )

    accommodation = state.get("accommodation_plan")
    if accommodation and isinstance(accommodation, dict):
        for city in accommodation.get("cities", []):
            if not isinstance(city, dict):
                continue
            options = city.get("options", [])
            if options and isinstance(options[0], dict):
                h = options[0]
                parts.append(
                    f"Hotel in {city.get('city', '?')}: {h.get('name', 'Unknown')}"
                    f" -- SGD {h.get('price_per_night_sgd', 0):.0f}/night"
                )

    intercity = state.get("intercity_transport_plan")
    if intercity and isinstance(intercity, dict):
        for hop in intercity.get("hops", []):
            if not isinstance(hop, dict):
                continue
            options = hop.get("options", [])
            if options and isinstance(options[0], dict):
                opt = options[0]
                parts.append(
                    f"{hop.get('from_city', '?')} -> {hop.get('to_city', '?')}:"
                    f" {opt.get('mode', 'transport')}"
                    f" -- SGD {opt.get('price_sgd', 0):.0f}"
                )

    if not parts:
        return {}

    return {
        "event": "thinking",
        "data": json.dumps({
            "agent": "selections",
            "message": "Building your itinerary with:\n"
            + "\n".join(f"  - {p}" for p in parts),
            "thread_id": "",  # Will be filled by caller
        }),
    }


def _apply_selections(plan_state: dict, selections: PlanSelectRequest) -> dict:
    """
    Apply user selections to the Pass 1 snapshot.

    Filters transport_plan, accommodation_plan to only the selected options.
    If no selection made for a category, auto-selects the first/cheapest option.
    """
    state = {**plan_state}

    # Filter flights, auto-select first option if user didn't choose
    transport = state.get("transport_plan")
    if transport and isinstance(transport, dict):
        outbound = transport.get("outbound_flights", [])
        if selections.selected_outbound_flight_id:
            selected = [
                f for f in outbound
                if f.get("flight_number") == selections.selected_outbound_flight_id
                or f.get("airline") == selections.selected_outbound_flight_id
            ]
            transport["outbound_flights"] = selected if selected else outbound[:1]
        elif outbound:
            transport["outbound_flights"] = [
                min(outbound, key=lambda f: f.get("price_sgd") or float("inf"))
            ]

        inbound = transport.get("inbound_flights", [])
        if selections.selected_inbound_flight_id:
            selected = [
                f for f in inbound
                if f.get("flight_number") == selections.selected_inbound_flight_id
                or f.get("airline") == selections.selected_inbound_flight_id
            ]
            transport["inbound_flights"] = selected if selected else inbound[:1]
        elif inbound:
            transport["inbound_flights"] = [
                min(inbound, key=lambda f: f.get("price_sgd") or float("inf"))
            ]
        state["transport_plan"] = transport

    # Filter hotels, auto-select first option per city if user didn't choose
    accommodation = state.get("accommodation_plan")
    if accommodation and isinstance(accommodation, dict):
        for city_acc in accommodation.get("cities", []):
            if not isinstance(city_acc, dict):
                continue
            city_name = city_acc.get("city", "")
            options = city_acc.get("options", [])
            selected_id = (selections.selected_hotel_ids or {}).get(city_name)
            if selected_id:
                matched = [h for h in options if h.get("name") == selected_id]
                city_acc["options"] = matched if matched else options[:1]
            elif options:
                city_acc["options"] = [options[0]]
        state["accommodation_plan"] = accommodation

    # Mark activities with priority flag based on selected_activity_ids
    if selections.selected_activity_ids:
        activities = state.get("activities_plan")
        if activities and isinstance(activities, dict) and "cities" in activities:
            for city_act in activities["cities"]:
                if not isinstance(city_act, dict):
                    continue
                for day_options in city_act.get("options_per_day", []):
                    if not isinstance(day_options, list):
                        continue
                    for activity in day_options:
                        if isinstance(activity, dict):
                            activity["priority"] = (
                                activity.get("name") in selections.selected_activity_ids
                            )
            state["activities_plan"] = activities

    # Filter intercity transport -- auto-select cheapest per hop if user didn't choose
    intercity = state.get("intercity_transport_plan")
    if intercity and isinstance(intercity, dict):
        for hop in intercity.get("hops", []):
            if not isinstance(hop, dict):
                continue
            hop_key = f"{hop.get('from_city', '')}>{hop.get('to_city', '')}"
            # Normalise: user sends "CityA->CityB", we also check "CityA>CityB"
            options = hop.get("options", [])
            selected_id = None
            for k, v in (selections.selected_intercity_ids or {}).items():
                if k.replace("->", ">") == hop_key:
                    selected_id = v
                    break
            if selected_id:
                matched = [
                    o for o in options
                    if o.get("mode") == selected_id
                    or o.get("operator") == selected_id
                ]
                hop["options"] = matched if matched else options[:1]
            elif options:
                hop["options"] = [
                    min(options, key=lambda o: o.get("price_sgd", float("inf")))
                ]
        state["intercity_transport_plan"] = intercity

    # Set planning_mode to "auto" for Pass 2
    state["planning_mode"] = "auto"
    state["critic_feedback"] = None
    state["itinerary"] = None

    return state


@router.post("/plan/{plan_id}/select")
async def select_plan(
    plan_id: str,
    request: Request,
    selections: PlanSelectRequest,
    user: dict = Depends(get_current_user),
):
    """
    Pass 2 Stage A: apply selections, generate meal options.

    Loads Pass 1 snapshot, applies flight/hotel/activity selections,
    runs meal_generation_node, saves state, emits meal_options SSE event.
    Does NOT run Day Planner -- waits for POST /plan/{id}/meals.
    """
    user_id = user["sub"]

    plan_state = get_plan_options(plan_id, user_id)
    if plan_state is None:
        raise HTTPException(
            status_code=404, detail="Plan options not found or expired"
        )

    initial_state = _apply_selections(plan_state, selections)
    thread_id = str(uuid.uuid4())

    async def event_generator():
        # Emit selection summary
        sel_summary = _build_selection_summary(initial_state)
        if sel_summary:
            sel_data = json.loads(sel_summary["data"])
            sel_data["thread_id"] = thread_id
            sel_summary["data"] = json.dumps(sel_data)
            yield sel_summary

        # Run meal generation
        yield {
            "event": "agent_active",
            "data": json.dumps({
                "agent": "meal_generation",
                "summary": "Finding restaurants near your activities...",
                "thread_id": thread_id,
            }),
        }

        try:
            meal_result = await meal_generation_node(initial_state)
            meal_options = meal_result.get("meal_options", [])
        except Exception:
            meal_options = []

        # Merge into state and save for the meals endpoint
        initial_state["meal_options"] = meal_options
        meal_plan_id = save_plan_options(user_id, initial_state)

        yield {
            "event": "meal_options",
            "data": json.dumps(
                {
                    "plan_id": meal_plan_id,
                    "thread_id": thread_id,
                    "meal_options": meal_options,
                },
                default=str,
            ),
        }

    return EventSourceResponse(event_generator())


@router.post("/plan/{plan_id}/meals")
async def select_meals(
    plan_id: str,
    request: Request,
    meal_selections: MealSelectRequest,
    user: dict = Depends(get_current_user),
):
    """Pass 2 Stage B: apply meal selections and run Day Planner.

    If auto_select=True, picks the first option for each meal slot.
    Otherwise, uses the selections provided.
    Returns SSE stream with agent_active events during Day Planner execution
    and a complete event with the final itinerary.
    """
    user_id = user["sub"]
    plan_state = get_plan_options(plan_id, user_id)
    if plan_state is None:
        raise HTTPException(
            status_code=404, detail="Plan not found or expired"
        )

    # Apply meal selections
    if meal_selections.auto_select:
        meal_options = plan_state.get("meal_options") or []
        selected = []
        for slot in meal_options:
            options = slot.get("options", [])
            if options:
                selected.append({
                    "day_number": slot["day_number"],
                    "meal_type": slot["meal_type"],
                    "selected": options[0],
                })
        plan_state["selected_meals"] = selected
    else:
        plan_state["selected_meals"] = meal_selections.selected_meals

    # Prepare state for Day Planner
    plan_state["planning_mode"] = "auto"
    plan_state["critic_feedback"] = None
    plan_state["itinerary"] = None


    plan_state["messages"] = [
        HumanMessage(content="Generate itinerary with selected meals")
    ]

    thread_id = str(uuid.uuid4())

    async def event_generator():
        start_time = time.perf_counter()

        # Emit agent_active for day planner
        yield {
            "event": "agent_active",
            "data": json.dumps({
                "agent": "day_planner_node_per_day",
                "summary": _AGENT_SUMMARIES["day_planner_node_per_day"],
                "thread_id": thread_id,
            }),
        }

        # Queue-based emit callback so day_planner_node_per_day can yield SSE events
        # back to the generator without LangGraph node constraints (Pitfall 4).
        event_queue: asyncio.Queue = asyncio.Queue()

        async def emit_event(event: dict) -> None:
            await event_queue.put(event)

        async def run_day_planner() -> dict:
            try:
                return await day_planner_node_per_day(plan_state, emit_event, thread_id)
            except asyncio.CancelledError:
                raise  # re-raise so task propagates cleanly; finally puts sentinel
            except Exception as e:
                await event_queue.put({
                    "event": "error",
                    "data": json.dumps({"error": str(e)}),
                })
                return {"itinerary": None}
            finally:
                await event_queue.put(None)  # sentinel to end the drain loop

        task = asyncio.create_task(run_day_planner())

        # Drain SSE events from the queue as day_planner_node_per_day emits them
        while True:
            event = await event_queue.get()
            if event is None:
                break
            yield event

        try:
            day_planner_result = await task
        except Exception:
            day_planner_result = {"itinerary": None}
        plan_state.update(day_planner_result)

        # Run critic
        yield {
            "event": "agent_active",
            "data": json.dumps({
                "agent": "critic",
                "summary": _AGENT_SUMMARIES["critic"],
                "thread_id": thread_id,
            }),
        }
        try:
            critic_result = await critic_node(plan_state)
            plan_state.update(critic_result)
            feedback = critic_result.get("critic_feedback")
            if feedback and isinstance(feedback, dict):
                violations = feedback.get("violations", [])
                msg = (
                    "Itinerary validated -- looks good!"
                    if feedback.get("is_feasible", True)
                    else f"Found {len(violations)} issue(s)..."
                )
                yield {
                    "event": "thinking",
                    "data": json.dumps({
                        "agent": "critic",
                        "message": msg,
                        "thread_id": thread_id,
                    }),
                }
        except Exception:
            pass  # critic is non-fatal

        # Run cache_write
        yield {
            "event": "agent_active",
            "data": json.dumps({
                "agent": "cache_write",
                "summary": _AGENT_SUMMARIES["cache_write"],
                "thread_id": thread_id,
            }),
        }
        try:
            await cache_write_node(plan_state)
        except Exception:
            pass  # cache write is non-fatal

        latency_ms = int((time.perf_counter() - start_time) * 1000)

        # Enrich time_slots with lat/lng before saving and sending to frontend
        itinerary_plan_id = None
        itinerary_with_plans = None
        itinerary_data = plan_state.get("itinerary")
        if itinerary_data is not None:

            enrich_itinerary_coords(itinerary_data, state=plan_state)
            itinerary_with_plans = {
                **(itinerary_data if isinstance(itinerary_data, dict) else {}),
                "traveler_count": plan_state.get("traveler_count", 1),
                "room_sharing": plan_state.get("room_sharing") or "shared",
                "plans": {
                    "transport_plan": plan_state.get("transport_plan"),
                    "accommodation_plan": plan_state.get("accommodation_plan"),
                    "activities_plan": plan_state.get("activities_plan"),
                },
            }
            try:
                itinerary_plan_id = save_itinerary(
                    user_id=user_id,
                    destination=plan_state.get("destination", ""),
                    travel_dates=plan_state.get("travel_dates"),
                    architecture=plan_state.get("_architecture", "supervisor"),
                    itinerary=itinerary_with_plans,
                )
            except Exception:
                pass

        # Persist thread state so the edit endpoint can load itinerary by thread_id.
        try:
            save_thread_state(thread_id, user_id, plan_state)
        except Exception:
            pass  # non-fatal

        yield {
            "event": "complete",
            "data": json.dumps({
                "status": "done",
                "itinerary": itinerary_with_plans if itinerary_data is not None else None,
                "plan_id": itinerary_plan_id,
                "plan_status": "pending_approval" if itinerary_data else None,
                "thread_id": thread_id,
                "critic_feedback": plan_state.get("critic_feedback"),
                "selected_meals": plan_state.get("selected_meals"),
                "metrics": {"latency_ms": latency_ms},
            }),
        }

    return EventSourceResponse(event_generator())
