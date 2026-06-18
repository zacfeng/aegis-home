from abc import ABC, abstractmethod
from typing import List, Dict


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
            history: List of previous turns, each a dict with 'role' and 'content'.
                     Roles should be 'user' or 'assistant'.
            system_prompt: Optional persona / instruction injected before history.

        Returns:
            The model's reply as a plain string.
        """
        ...
