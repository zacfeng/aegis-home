import os
from typing import List, Dict

from openai import AsyncOpenAI

from .base import LLMClient

# Supported model names on common providers:
#   Ollama local  → "nous-hermes2" or "nous-hermes2:10.7b"
#   OpenRouter    → "nousresearch/nous-hermes-2-mistral-7b-dpo"
#   Together AI   → "NousResearch/Nous-Hermes-2-Mistral-7B-DPO"
_DEFAULT_MODEL = os.getenv(
    "HERMES_MODEL_NAME", "nousresearch/nous-hermes-2-mistral-7b-dpo"
)
_SYSTEM_PROMPT = (
    "You are Hermes, a knowledgeable and helpful AI assistant. "
    "Answer concisely and accurately."
)


class HermesClient(LLMClient):
    """
    NousResearch Hermes via any OpenAI-compatible endpoint.

    Local (Ollama):
        HERMES_BASE_URL=http://localhost:11434/v1
        HERMES_API_KEY=ollama          # arbitrary non-empty string
        HERMES_MODEL_NAME=nous-hermes2

    Cloud (OpenRouter):
        HERMES_BASE_URL=https://openrouter.ai/api/v1
        HERMES_API_KEY=<your openrouter key>
        HERMES_MODEL_NAME=nousresearch/nous-hermes-2-mistral-7b-dpo
    """

    def __init__(self) -> None:
        base_url = os.getenv("HERMES_BASE_URL")
        api_key = os.getenv("HERMES_API_KEY")
        if not base_url:
            raise ValueError("HERMES_BASE_URL is not set")
        if not api_key:
            raise ValueError("HERMES_API_KEY is not set")

        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self._model = os.getenv("HERMES_MODEL_NAME", _DEFAULT_MODEL)

    async def generate_response(
        self,
        user_message: str,
        history: List[Dict[str, str]],
        system_prompt: str = "",
    ) -> str:
        messages = [{"role": "system", "content": system_prompt or _SYSTEM_PROMPT}]
        messages += [
            {"role": turn["role"], "content": turn["content"]}
            for turn in history
        ]
        messages.append({"role": "user", "content": user_message})

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=1024,
            temperature=0.7,
        )
        return response.choices[0].message.content or ""
