import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.agents.edit import (
    _detect_transport_changes,
    _extract_itinerary_shape,
    _rerun_transport,
    edit_itinerary_node,
)
from src.utils.jwt import get_current_user
from src.db.repository import get_plan_options, save_thread_state, update_itinerary_data

router = APIRouter()
logger = logging.getLogger(__name__)


def _patch_flight_times(itinerary: dict, transport_updates: dict) -> None:
    """
    Patch the day schedule's arrival/departure slots with new flight times.

    After transport re-search, Day 1's first slot should reflect the new arrival
    time, and the last day's departure slot should reflect the new departure time.
    Modifies itinerary in-place.
    """
    tp = transport_updates.get("transport_plan")
    if not tp or not isinstance(tp, dict):
        return

    days = itinerary.get("days")
    if not days or not isinstance(days, list):
        return

    # Patch Day 1 arrival from outbound flight
    outbound = (tp.get("outbound_flights") or [None])[0]
    if outbound and isinstance(outbound, dict) and outbound.get("arrival_time"):
        arrival = outbound["arrival_time"]  # ISO: "2026-04-07T06:40:00"
        arrival_hhmm = arrival[11:16] if len(arrival) >= 16 else None
        if arrival_hhmm and isinstance(days[0], dict):
            slots = days[0].get("time_slots", [])
            for slot in slots:
                if not isinstance(slot, dict):
                    continue
                label = (slot.get("label") or "").lower()
                stype = (slot.get("slot_type") or "").lower()
                if "arrival" in label or (stype == "activity" and "airport" in label):
                    slot["start_time"] = arrival_hhmm
                    # Set end_time ~1hr after arrival for customs/baggage
                    h, m = int(arrival_hhmm[:2]), int(arrival_hhmm[3:5])
                    m += 60
                    h += m // 60
                    m = m % 60
                    slot["end_time"] = f"{h:02d}:{m:02d}"

                    logger.info("Patched Day 1 arrival to %s", arrival_hhmm)
                    # Shift subsequent slots on Day 1
                    _shift_slots_after(slots, slots.index(slot))
                    break

    # Patch last day departure from inbound flight
    # Must arrive at airport 2 hours before flight for check-in/baggage
    inbound = (tp.get("inbound_flights") or [None])[0]
    if inbound and isinstance(inbound, dict) and inbound.get("departure_time"):
        departure = inbound["departure_time"]  # ISO: "2026-04-13T03:00:00"
        dep_hhmm = departure[11:16] if len(departure) >= 16 else None
        if dep_hhmm and isinstance(days[-1], dict):
            # Calculate airport check-in time (2 hours before flight)
            fh, fm = int(dep_hhmm[:2]), int(dep_hhmm[3:5])
            checkin_min = fh * 60 + fm - 120  # 2 hours before
            if checkin_min < 0:
                checkin_min += 24 * 60  # overnight flight
            checkin_hhmm = f"{(checkin_min // 60) % 24:02d}:{checkin_min % 60:02d}"

            slots = days[-1].get("time_slots", [])
            for slot in slots:
                if not isinstance(slot, dict):
                    continue
                label = (slot.get("label") or "").lower()
                stype = (slot.get("slot_type") or "").lower()
                if "departure" in label or "depart" in label or (stype == "activity" and "airport" in label):
                    # Departure slot = airport check-in time (2h before flight)
                    slot["start_time"] = checkin_hhmm
                    slot["end_time"] = dep_hhmm
                    slot["notes"] = f"Arrive at airport by {checkin_hhmm} for check-in. Flight departs {dep_hhmm}."
                    logger.info("Patched last day departure: check-in %s, flight %s", checkin_hhmm, dep_hhmm)
                    # Also adjust the transit-to-airport slot before it
                    dep_idx = slots.index(slot)
                    if dep_idx > 0:
                        prev = slots[dep_idx - 1]
                        if isinstance(prev, dict) and "airport" in (prev.get("label") or "").lower():
                            prev["end_time"] = checkin_hhmm
                            # Transit starts ~60-90 min before check-in
                            transit_dur = 60
                            transit_start = checkin_min - transit_dur
                            if transit_start < 0:
                                transit_start += 24 * 60
                            prev["start_time"] = f"{(transit_start // 60) % 24:02d}:{transit_start % 60:02d}"
                    break


def _shift_slots_after(slots: list, anchor_idx: int) -> None:
    """
    Shift time slots after the anchor to avoid overlap.

    Simple approach: walk forward, if a slot starts before the previous ends,
    push it forward by the overlap.
    """
    for i in range(anchor_idx, len(slots) - 1):
        current = slots[i]
        nxt = slots[i + 1]
        if not isinstance(current, dict) or not isinstance(nxt, dict):
            continue
        cur_end = current.get("end_time") or ""
        nxt_start = nxt.get("start_time") or ""
        if not cur_end or not nxt_start:
            continue
        try:
            ce_min = int(cur_end[:2]) * 60 + int(cur_end[3:5])
            ns_min = int(nxt_start[:2]) * 60 + int(nxt_start[3:5])
        except (ValueError, IndexError):
            continue
        if ns_min < ce_min:
            # Compute this slot's duration, shift it forward
            nxt_end = nxt.get("end_time") or ""
            try:
                ne_min = int(nxt_end[:2]) * 60 + int(nxt_end[3:5])
                duration = max(ne_min - ns_min, 30)  # preserve duration, min 30m
            except (ValueError, IndexError):
                duration = 30
            new_start = ce_min
            new_end = new_start + duration
            nxt["start_time"] = f"{(new_start // 60) % 24:02d}:{new_start % 60:02d}"
            nxt["end_time"] = f"{(new_end // 60) % 24:02d}:{new_end % 60:02d}"


class EditRequest(BaseModel):
    """User's edit request for an existing itinerary."""

    edit_text: str  # Natural language edit instruction
    thread_id: str  # Thread ID from the original plan


@router.post("/plan/{plan_id}/edit")
async def edit_plan(
    plan_id: str,
    edit_request: EditRequest,
    user: dict = Depends(get_current_user),
):
    """Apply a minor edit to an assembled itinerary.

    Loads the itinerary from thread state, applies the edit via LLM,
    detects transport-affecting changes, re-runs workers if needed,
    saves the updated state, and returns the modified itinerary.
    """
    user_id = user["sub"]

    # Load existing state from thread
    plan_state = get_plan_options(edit_request.thread_id, user_id)
    if plan_state is None:
        raise HTTPException(
            status_code=404,
            detail="Thread state not found -- itinerary may have expired",
        )

    itinerary = plan_state.get("itinerary")
    if itinerary is None:
        raise HTTPException(
            status_code=400,
            detail="No itinerary found in thread state -- run the full pipeline first",
        )

    # Capture old shape before edit
    old_shape = _extract_itinerary_shape(itinerary)

    # Apply LLM edit
    updated_itinerary = await edit_itinerary_node(itinerary, edit_request.edit_text)

    # Detect transport-affecting changes
    new_shape = _extract_itinerary_shape(updated_itinerary)
    changes = _detect_transport_changes(old_shape, new_shape)
    transport_notes: list[str] = []

    if changes["rerun_flights"] or changes["rerun_intercity"]:
        logger.info("Transport re-search triggered: flights=%s, intercity=%s", changes["rerun_flights"], changes["rerun_intercity"])
        transport_updates = await _rerun_transport(plan_state, new_shape, changes)

        # Merge transport updates into plan_state
        for key, value in transport_updates.items():
            plan_state[key] = value

        if "transport_plan" in transport_updates:
            tp = transport_updates["transport_plan"]
            out = (tp.get("outbound_flights") or [{}])[0]
            inb = (tp.get("inbound_flights") or [{}])[0]
            if out:
                transport_notes.append(
                    f"Flights updated: {out.get('airline', '?')} "
                    f"({out.get('flight_number', '?')}) outbound"
                )
            if inb:
                transport_notes.append(
                    f"{inb.get('airline', '?')} "
                    f"({inb.get('flight_number', '?')}) inbound"
                )

        if "intercity_transport_plan" in transport_updates:
            hops = transport_updates["intercity_transport_plan"].get("hops", [])
            for hop in hops:
                opts = hop.get("options", [])
                if opts:
                    transport_notes.append(
                        f"{hop.get('from_city')} -> {hop.get('to_city')}: "
                        f"{opts[0].get('mode', 'transport')} updated"
                    )

        # Patch Day 1 arrival and last day departure times from new flights
        _patch_flight_times(updated_itinerary, transport_updates)

    # Save updated state
    plan_state["itinerary"] = updated_itinerary
    try:
        save_thread_state(edit_request.thread_id, user_id, plan_state)
    except Exception:
        pass  # Non-fatal

    # Persist updated itinerary + plans to itineraries table so /confirm has fresh data
    try:
        itinerary_with_plans = {
            **(updated_itinerary if isinstance(updated_itinerary, dict) else {}),
            "plans": {
                "transport_plan": plan_state.get("transport_plan"),
                "accommodation_plan": plan_state.get("accommodation_plan"),
                "activities_plan": plan_state.get("activities_plan"),
            },
        }
        update_itinerary_data(plan_id, itinerary_with_plans)
    except Exception:
        pass  # Non-fatal

    return {
        "status": "edited",
        "itinerary": updated_itinerary,
        "thread_id": edit_request.thread_id,
        "edit_applied": edit_request.edit_text,
        "transport_updated": bool(transport_notes),
        "transport_notes": transport_notes,
    }
