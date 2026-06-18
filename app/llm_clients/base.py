from abc import ABC, abstractmethod
from typing import List, Dict


class LLMClient(ABC):
    """Abstract base class for all LLM client implementations."""

    @abstractmethod
    async def generate_response(
        self,
        user_message: str,
        history: List[Dict[str, str]],
    ) -> str:
        """
        Generate a response given the current message and conversation history.

        Args:
            user_message: The latest message from the user.
            history: List of previous turns, each a dict with 'role' and 'content'.
                     Roles should be 'user' or 'assistant'.

        Returns:
            The model's reply as a plain string.
        """
        ...
