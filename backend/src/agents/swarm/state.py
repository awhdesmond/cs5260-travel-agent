
from typing import Optional
from langgraph.prebuilt.chat_agent_executor import RemainingSteps

from src.state.blackboard import TravelBlackboard


class SwarmState(TravelBlackboard):
    active_agent: Optional[str]  # Tracks active agent in swarm mode
    remaining_steps: RemainingSteps
