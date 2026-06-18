import os
from typing import List, Dict

import anthropic

from .base import LLMClient


class ClaudeClient(LLMClient):
    def __init__(self, model_name: str = "claude-haiku-4-5-20251001"):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set")
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model_name = model_name

    async def generate_response(
        self,
        user_message: str,
        history: List[Dict[str, str]],
        system_prompt: str = "",
    ) -> str:
        messages = [
            {"role": turn["role"], "content": turn["content"]}
            for turn in history
        ]
        messages.append({"role": "user", "content": user_message})

        kwargs = dict(
            model=self._model_name,
            max_tokens=1024,
            messages=messages,
        )
        if system_prompt:
            kwargs["system"] = system_prompt

        response = await self._client.messages.create(**kwargs)
        return response.content[0].text
