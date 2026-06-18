from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List


class LLMClient(ABC):
    """Abstract base class for all LLM client implementations."""

    @abstractmethod
    async def generate_response(
        self,
        user_message: str,
        history: List[Dict[str, str]],
        system_prompt: str = "",
    ) -> str:
        """
        Generate a response given the current message and conversation history.

        Args:
            user_message: The latest message from the user.
            history: Previous turns, each a dict with 'role' and 'content'.
                     Roles are 'user' or 'assistant'.
            system_prompt: Persona / instruction injected before history.

        Returns:
            The model's reply as a plain string.
        """
        ...

    async def generate_with_tools(
        self,
        user_message: str,
        history: List[Dict[str, str]],
        system_prompt: str,
        tool_declarations: List[Dict],  # noqa: ARG002
        tool_executor: Callable[[str, dict], Any],  # noqa: ARG002
        max_rounds: int = 5,  # noqa: ARG002
    ) -> str:
        """
        Generate a response with function-calling support.

        Default implementation ignores tools and falls back to generate_response.
        Override in clients that support native function calling.
        """
        return await self.generate_response(user_message, history, system_prompt)
