import json
import time
import uuid
from datetime import date as _date

from fastapi import APIRouter, Depends, HTTPException, Request
from langchain_core.callbacks.usage import UsageMetadataCallbackHandler
from langchain_core.messages import HumanMessage
from sse_starlette.sse import EventSourceResponse

from src.api.models.requests import PlanRequest
from src.api.routes.plan import make_initial_state  # shared factory
from src.utils.jwt import get_current_user
from src.db.repository import insert_run, save_itinerary
from src.utils.guards import check_token_budget
from src.db.repository import get_plan_options, save_thread_state, save_plan_options
router = APIRouter()

_AGENT_SUMMARIES: dict[str, str] = {
    "ingestion": "Understanding your request...",
    "ingestion_node": "Understanding your request...",
    "cache_check": "Checking for similar plans...",
    "cache_check_node": "Checking for similar plans...",
    "flight_search_node": "Searching for flights...",
    "hotel_search_node": "Finding hotels...",
    "activities_search_node": "Searching activities and restaurants...",
    "supervisor": "Coordinating your travel plan...",
    "root_dispatch": "Dispatching to workers...",
    "transport_coordinator": "Searching for flights...",
    "accommodation_coordinator": "Finding hotels...",
    "experiences_coordinator": "Searching activities and restaurants...",
    "parallel_workers": "Searching flights, hotels, and activities...",
    "critic": "Validating your plan...",
    "critic_node": "Validating your plan...",
    "day_planner": "Assembling your itinerary...",
    "day_planner_node": "Assembling your itinerary...",
    "day_planner_node_per_day": "Assembling your itinerary day by day...",
    "cache_write": "Saving results...",
    "cache_write_node": "Saving results...",
}


def _get_agent_summary(node_name: str, data: dict) -> str:
    """build a short human-readable summary for the agent_active event."""
    node_data = data.get(node_name, {})

    if node_name == "flight_search_node" and isinstance(node_data, dict):
        transport = node_data.get("transport_plan")
        if transport and isinstance(transport, dict):
            outbound = transport.get("outbound_flights", [])
            if outbound:
                prices = [f.get("price_sgd", 0) for f in outbound if isinstance(f, dict)]
                if prices:
                    return (
                        f"Found {len(outbound)} flight option(s)"
                        f" from SGD {min(prices):.0f}-{max(prices):.0f}"
                    )

    if node_name == "hotel_search_node" and isinstance(node_data, dict):
        accommodation = node_data.get("accommodation_plan")
        if accommodation and isinstance(accommodation, dict):
            total_options = sum(
                len(c.get("options", []))
                for c in accommodation.get("cities", [])
                if isinstance(c, dict)
            )
            if total_options:
                cities = [
                    c.get("city", "")
                    for c in accommodation.get("cities", [])
                    if isinstance(c, dict) and c.get("city")
                ]
                city_str = f" in {', '.join(cities)}" if cities else ""
                return f"Found {total_options} hotel option(s){city_str}"

    if node_name == "activities_search_node" and isinstance(node_data, dict):
        activities = node_data.get("activities_plan")
        if activities and isinstance(activities, dict):
            total = sum(
                sum(len(d) for d in c.get("options_per_day", []))
                for c in activities.get("cities", [])
                if isinstance(c, dict)
            )
            if total:
                return f"Found {total} activities and experiences"

    return _AGENT_SUMMARIES.get(node_name, f"Running {node_name}...")


def _build_thinking_event(node_name: str, node_data: dict, thread_id: str) -> dict | None:
    """Build a 'thinking' SSE event with conversational feedback after key stages.

    Returns an SSE event dict, or None if no thinking event is warranted.
    """
    if not isinstance(node_data, dict):
        return None

    if node_name in ("ingestion", "ingestion_node"):
        return _build_ingestion_thinking(node_data, thread_id)

    if node_name in ("critic", "critic_node"):
        return _build_critic_thinking(node_data, thread_id)

    return None


def _build_ingestion_thinking(data: dict, thread_id: str) -> dict | None:
    """Build conversational feedback after ingestion: what we understood from user input."""
    # Don't emit thinking for clarification/rejection — those have their own events
    if data.get("needs_clarification") or not data.get("is_feasible", True):
        return None

    parts: list[str] = []

    # Destinations
    destinations = data.get("destinations") or []
    if destinations:
        city_names = [d.get("city", "") for d in destinations if d.get("city")]
        if city_names:
            parts.append(f"Destination: {' -> '.join(city_names)}")

    # Travel dates
    travel_dates = data.get("travel_dates") or {}
    start = travel_dates.get("start")
    end = travel_dates.get("end")
    if start and end:
        try:
            days = (_date.fromisoformat(end) - _date.fromisoformat(start)).days
            parts.append(f"Dates: {start} to {end} ({days} days)")
        except ValueError:
            parts.append(f"Dates: {start} to {end}")

    # Travelers
    count = data.get("traveler_count")
    if count and count > 1:
        sharing = data.get("room_sharing")
        sharing_str = f", {sharing} rooms" if sharing else ""
        parts.append(f"Travelers: {count} people{sharing_str}")

    # Preferences & style
    prefs = data.get("preferences") or []
    additional = data.get("additional_preferences") or []
    all_prefs = prefs + additional
    if all_prefs:
        parts.append(f"Interests: {', '.join(all_prefs[:5])}")

    style = data.get("trip_style")
    intensity = data.get("activity_intensity")
    tier = data.get("accommodation_tier")
    style_parts = []
    if style:
        style_parts.append(style)
    if intensity:
        style_parts.append(f"{intensity} pace")
    if tier:
        style_parts.append(f"{tier} accommodation")
    if style_parts:
        parts.append(f"Style: {', '.join(style_parts)}")

    # Low confidence fields
    low_conf = data.get("low_confidence_fields") or []
    if low_conf:
        parts.append(f"(Less certain about: {', '.join(low_conf)})")

    if not parts:
        return None

    message = "Here's what I understood from your request:\n" + "\n".join(f"  • {p}" for p in parts)

    return {
        "event": "thinking",
        "data": json.dumps({
            "agent": "ingestion",
            "message": message,
            "thread_id": thread_id,
            "details": {
                "destinations": destinations,
                "travel_dates": travel_dates,
                "traveler_count": count,
                "preferences": all_prefs,
                "trip_style": style,
                "activity_intensity": intensity,
                "accommodation_tier": tier,
            },
        }),
    }


def _build_critic_thinking(data: dict, thread_id: str) -> dict | None:
    """Build conversational feedback after critic: validation results."""
    feedback = data.get("critic_feedback")
    if not feedback or not isinstance(feedback, dict):
        return None

    violations = feedback.get("violations", [])

    if not violations:
        return {
            "event": "thinking",
            "data": json.dumps({
                "agent": "critic",
                "message": "Plan looks good -- no issues found.",
                "thread_id": thread_id,
            }),
        }

    parts: list[str] = []
    parts.append(f"Found {len(violations)} issue(s) (informational):")
    for v in violations[:3]:
        reason = v.get("reason", "") if isinstance(v, dict) else str(v)
        vtype = v.get("type", "") if isinstance(v, dict) else ""
        if reason:
            parts.append(f"  - {reason}")
        elif vtype:
            parts.append(f"  - {vtype}")
    if len(violations) > 3:
        parts.append(f"  ...and {len(violations) - 3} more")

    message = "\n".join(parts)
    return {
        "event": "thinking",
        "data": json.dumps({
            "agent": "critic",
            "message": message,
            "thread_id": thread_id,
        }),
    }


def _extract_booking_links(result: dict) -> list[dict]:
    """pull booking links out of the domain plans."""
    links: list[dict] = []
    transport = result.get("transport_plan") or {}
    for f in transport.get("outbound_flights", []):
        if isinstance(f, dict) and f.get("booking_link"):
            links.append({
                "type": "flight",
                "label": f.get("airline", "Flight"),
                "url": f["booking_link"],
            })
    for f in transport.get("inbound_flights", []):
        if isinstance(f, dict) and f.get("booking_link"):
            links.append({
                "type": "flight",
                "label": f"Return - {f.get('airline', 'Flight')}",
                "url": f["booking_link"],
            })
    accommodation = result.get("accommodation_plan") or {}
    for city in accommodation.get("cities", []):
        if not isinstance(city, dict):
            continue
        for h in city.get("options", []):
            if isinstance(h, dict) and h.get("booking_link"):
                links.append({
                    "type": "hotel",
                    "label": h.get("name", "Hotel"),
                    "url": h["booking_link"],
                })
    return links


@router.post("/plan/stream")
async def create_plan_stream(
    request: Request, plan_request: PlanRequest, user: dict = Depends(get_current_user)
):
    """Stream travel plan generation with real-time agent progress events.

    Returns SSE stream:
    - agent_active events: emitted when each graph node executes
    - complete event: final event with itinerary, plan_id, and metrics

    Uses stream_mode=["updates", "values"]:
    - "updates": per-node progress for agent_active SSE events
    - "values": full accumulated state; last one is the final result

    If thread_id is provided, resumes from prior conversation state.
    """
    ok, tokens = check_token_budget(plan_request.user_input)
    if not ok:
        raise HTTPException(400, f"Request too large ({tokens} tokens)")

    if plan_request.mode == "supervisor":
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

    # thread state persistence
    thread_id = plan_request.thread_id or str(uuid.uuid4())
    user_id = user["sub"]

    # If thread_id provided, try to resume from stored state
    if plan_request.thread_id:

        prior_state = get_plan_options(plan_request.thread_id, user_id)
        if prior_state is not None:

            # Set new user input; ingestion_node merges with prior state via _pick()
            prior_state["raw_input"] = plan_request.user_input
            prior_state["messages"] = [HumanMessage(content=plan_request.user_input)]
            # Reset clarification so ingestion re-evaluates with merged state
            # Note: awaiting_confirmation is NOT reset here — ingestion_node checks it
            # to detect user confirmation vs changes
            prior_state["needs_clarification"] = False
            prior_state["clarification_questions"] = None

            # If prior state has a completed itinerary, clear stale worker outputs.
            # Without this, has_options would be True from prior worker plans, causing
            # the options event to fire again and showing selection cards on every message.
            # Clearing forces workers to re-run cleanly with the amended request.
            if prior_state.get("itinerary") is not None:
                prior_state["itinerary"] = None
                prior_state["transport_plan"] = None
                prior_state["accommodation_plan"] = None
                prior_state["activities_plan"] = None
                prior_state["meal_options"] = None
                prior_state["selected_meals"] = None
                prior_state["planning_mode"] = None
                prior_state["critic_feedback"] = None

            initial_state = prior_state
        else:
            initial_state = make_initial_state(plan_request.user_input)
    else:
        initial_state = make_initial_state(plan_request.user_input)

    callback = UsageMetadataCallbackHandler()
    config = {
        "configurable": {"thread_id": thread_id},
        "callbacks": [callback],
        "recursion_limit": rec_limit,
    }

    async def event_generator():
        final_state = None
        start_time = time.perf_counter()

        try:
            async for chunk in graph.astream(
                initial_state, config=config, stream_mode=["updates", "values"]
            ):
                mode_tag, data = chunk  # tuple when stream_mode is a list
                if mode_tag == "updates":
                    node_name = list(data.keys())[0]
                    summary = _get_agent_summary(node_name, data)
                    yield {
                        "event": "agent_active",
                        "data": json.dumps({
                            "agent": node_name,
                            "summary": summary,
                            "thread_id": thread_id,
                        }),
                    }
                    # Emit thinking event for conversational feedback
                    node_data = data.get(node_name, {})
                    thinking = _build_thinking_event(node_name, node_data, thread_id)
                    if thinking is not None:
                        yield thinking
                elif mode_tag == "values":
                    final_state = data
        except Exception as e:
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)}),
            }
            return

        latency_ms = int((time.perf_counter() - start_time) * 1000)

        usage = callback.usage_metadata
        total_tokens = (
            sum(m.get("total_tokens", 0) for m in usage.values()) if usage else 0
        )
        llm_call_count = len(usage) if usage else 0
        estimated_cost_sgd = (total_tokens / 1_000_000) * 0.25 * 1.35

        result = final_state or {}
        cache_hit = result.get("cache_hit", False)
        retry_count = 0  # No reflexion loops
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

        critic_feedback = result.get("critic_feedback")
        conflicts_detected = (
            len(critic_feedback.get("violations", []))
            if isinstance(critic_feedback, dict)
            else 0
        )

        try:
            insert_run({
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
            })
        except Exception:
            pass  # non-fatal

        # emit options event if workers produced plans (pass 1 of two-pass flow)
        transport_plan = result.get("transport_plan")
        accommodation_plan = result.get("accommodation_plan")
        activities_plan = result.get("activities_plan")
        intercity_plan = result.get("intercity_transport_plan")
        has_options = any([transport_plan, accommodation_plan, activities_plan])

        # save state for thread continuity

        try:
            save_thread_state(thread_id, user_id, result)
        except Exception:
            pass  # non-fatal

        if has_options:
            # Pass 1: emit options and STOP — user selects before Pass 2 runs day planner

            # Inject architecture so Pass 2 (plan_select.py) can save it correctly.
            # TravelBlackboard has no architecture field; this is the only place it's known.
            result["_architecture"] = plan_request.mode
            snapshot_id = save_plan_options(user_id, result)
            yield {
                "event": "options",
                "data": json.dumps({
                    "plan_id": snapshot_id,
                    "thread_id": thread_id,
                    "options": {
                        "flights": transport_plan,
                        "hotels": accommodation_plan,
                        "activities": activities_plan,
                        "intercity": intercity_plan,
                    },
                    "route_context": {
                        "origin": result.get("origin", "Singapore"),
                        "destinations": [
                            d.get("city", "") for d in
                            sorted(result.get("destinations") or [], key=lambda x: x.get("order", 0))
                        ],
                    },
                    "booking_links": _extract_booking_links(result),
                    "metrics": {
                        "latency_ms": latency_ms,
                        "total_tokens": total_tokens,
                        "estimated_cost_sgd": estimated_cost_sgd,
                        "llm_call_count": llm_call_count,
                    },
                }, default=str),
            }
            return  # Pass 1 ends here — no itinerary until user confirms selections

        # No options (cache hit or no worker plans) — emit complete with itinerary
        plan_id = None
        itinerary_data = result.get("itinerary")
        if itinerary_data is not None:
            # Enrich time_slots with lat/lng from activities/meals before sending
            from src.agents.shared import enrich_itinerary_coords
            enrich_itinerary_coords(itinerary_data, state=result)
            itinerary_with_plans = {
                **(itinerary_data if isinstance(itinerary_data, dict) else {}),
                "plans": {
                    "transport_plan": transport_plan,
                    "accommodation_plan": accommodation_plan,
                    "activities_plan": activities_plan,
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
            except Exception:
                pass  # non-fatal

        # Emit itinerary_meta + day_ready events before complete so DayView
        # loads progressively even on cache hits.
        if itinerary_data and isinstance(itinerary_data, dict):
            days = itinerary_data.get("days", [])
            total_days = itinerary_data.get("total_days", len(days))
            if days:
                yield {
                    "event": "itinerary_meta",
                    "data": json.dumps({
                        "total_days": total_days,
                        "thread_id": thread_id,
                    }),
                }
                for day in days:
                    yield {
                        "event": "day_ready",
                        "data": json.dumps({
                            "day_number": day.get("day_number", 0),
                            "day": day,
                            "thread_id": thread_id,
                        }),
                    }

        yield {
            "event": "complete",
            "data": json.dumps({
                "status": "done",
                "itinerary": itinerary_data,
                "plan_id": plan_id,
                "plan_status": "pending_approval" if itinerary_data else None,
                "mode": plan_request.mode,
                "booking_mode": plan_request.booking_mode,
                "thread_id": thread_id,
                "needs_clarification": result.get("needs_clarification", False),
                "is_feasible": result.get("is_feasible", True),
                "clarification_questions": result.get("clarification_questions"),
                "feasibility_rejection_reason": result.get("feasibility_rejection_reason"),
                "awaiting_confirmation": result.get("awaiting_confirmation", False),
                "confirmation_summary": result.get("confirmation_summary"),
                "critic_feedback": critic_feedback,
                "booking_links": _extract_booking_links(result),
                "metrics": {
                    "latency_ms": latency_ms,
                    "total_tokens": total_tokens,
                    "estimated_cost_sgd": estimated_cost_sgd,
                    "llm_call_count": llm_call_count,
                    "conflicts_detected": conflicts_detected,
                },
            }),
        }

    return EventSourceResponse(event_generator())
