from langgraph.prebuilt.chat_agent_executor import RemainingSteps

from src.state.blackboard import TravelBlackboard


class SupervisorState(TravelBlackboard):
    remaining_steps: RemainingSteps
