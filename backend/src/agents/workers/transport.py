import json

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from src.agents.llm import get_gemini_model, extract_json_from_response
from src.prompts.transport import INTERCITY_TRANSPORT_PROMPT
from src.state.models import InterCityTransportPlan
from src.tools.grounding import get_search_grounding_tool
from src.state.blackboard import TravelBlackboard


async def intercity_transport_node(state: "TravelBlackboard") -> dict:
    """Search inter-city transport options for all consecutive city hops."""
    destinations = sorted(
        state.get("destinations") or [], key=lambda d: d.get("order", 0)
    )

    if len(destinations) <= 1:
        return {"intercity_transport_plan": InterCityTransportPlan(hops=[]).model_dump()}

    hops = [
        (destinations[i], destinations[i + 1])
        for i in range(len(destinations) - 1)
    ]

    planning_mode = state.get("planning_mode", "auto")
    max_options = state.get("planning_mode_max_options", 3)
    travel_dates = state.get("travel_dates") or {}
    traveler_count = state.get("traveler_count", 1)

    hop_descriptions = "\n".join(
        f"  - {src['city']} -> {dst['city']}" for src, dst in hops
    )
    prompt = (
        f"Search for inter-city transport options for this multi-city trip:\n\n"
        f"City hops (find transport for each):\n{hop_descriptions}\n\n"
        f"Trip details:\n"
        f"- Travel dates: {travel_dates.get('start', 'unknown')} to {travel_dates.get('end', 'unknown')}\n"
        f"- Travelers: {traveler_count}\n"
        f"- Return up to {max_options} option(s) per hop\n"
        f"- Planning mode: {planning_mode}\n\n"
        f"Use Google Search to find real transport options (trains, buses, ferries, domestic flights)."
    )

    # Use replace() to avoid KeyError from JSON examples in the template
    system_prompt = INTERCITY_TRANSPORT_PROMPT.replace("{max_options}", str(max_options))

    llm = get_gemini_model()
    llm_with_search = llm.bind_tools([get_search_grounding_tool()])

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=prompt)]

    try:
        response = await llm_with_search.ainvoke(messages)
        response_text = response.content
    except Exception as e:
        return {
            "intercity_transport_plan": None,
            "critic_feedback": f"Inter-city transport search failed: {e}",
        }

    try:
        parsed = extract_json_from_response(response_text)
    except json.JSONDecodeError as e:
        return {
            "intercity_transport_plan": None,
            "critic_feedback": f"Inter-city transport search validation failed: Could not parse JSON - {e}",
        }

    try:
        plan = InterCityTransportPlan.model_validate(parsed)
    except ValidationError as e:
        return {
            "intercity_transport_plan": None,
            "critic_feedback": f"Inter-city transport search failed: {e}",
        }

    return {"intercity_transport_plan": plan.model_dump()}
