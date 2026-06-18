from typing import Literal

from .llm_clients.base import LLMClient
from .llm_clients.gemini_client import GeminiClient
from .llm_clients.claude_client import ClaudeClient
from .llm_clients.hermes_client import HermesClient

ModelName = Literal["gemini", "claude", "hermes"]

_REGISTRY: dict[ModelName, type[LLMClient]] = {
    "gemini": GeminiClient,
    "claude": ClaudeClient,
    "hermes": HermesClient,
}


class LLMFactory:
    """
    Holds the currently active LLM client and allows hot-swapping it
    at runtime (e.g. via the /model command) without restarting the server.
    """

    def __init__(self, default_model: ModelName = "gemini"):
        self._active_model_name: ModelName = default_model
        self._client: LLMClient = self._build(default_model)

    def _build(self, model_name: ModelName) -> LLMClient:
        cls = _REGISTRY.get(model_name)
        if cls is None:
            raise ValueError(
                f"Unknown model '{model_name}'. "
                f"Available: {list(_REGISTRY.keys())}"
            )
        return cls()

    def switch_model(self, model_name: str) -> str:
        """
        Switch the active model. Returns a status string suitable for
        sending back to the LINE chat.
        """
        model_name = model_name.strip().lower()
        if model_name not in _REGISTRY:
            available = ", ".join(_REGISTRY.keys())
            return f"Unknown model '{model_name}'. Available: {available}"

        self._client = self._build(model_name)  # type: ignore[arg-type]
        self._active_model_name = model_name  # type: ignore[assignment]
        return f"Model switched to '{model_name}' successfully."

    def get_client(self) -> LLMClient:
        return self._client

    @property
    def active_model(self) -> str:
        return self._active_model_name
