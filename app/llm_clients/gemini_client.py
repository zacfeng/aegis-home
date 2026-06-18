import logging
import os
from typing import Any, Callable, Dict, List

import google.generativeai as genai

from .base import LLMClient

logger = logging.getLogger(__name__)


class GeminiClient(LLMClient):
    def __init__(self, model_name: str = "gemini-2.0-flash"):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set")
        genai.configure(api_key=api_key)
        self._model_name = model_name

    def _make_model(self, system_prompt: str = "", tools=None):
        kwargs: dict = {}
        if system_prompt:
            kwargs["system_instruction"] = system_prompt
        if tools:
            kwargs["tools"] = tools
        return genai.GenerativeModel(model_name=self._model_name, **kwargs)

    @staticmethod
    def _to_gemini_history(history: List[Dict[str, str]]) -> list:
        return [
            {
                "role": "user" if turn["role"] == "user" else "model",
                "parts": [turn["content"]],
            }
            for turn in history
        ]

    async def generate_response(
        self,
        user_message: str,
        history: List[Dict[str, str]],
        system_prompt: str = "",
    ) -> str:
        model = self._make_model(system_prompt)
        chat = model.start_chat(history=self._to_gemini_history(history))
        response = await chat.send_message_async(user_message)
        return response.text

    async def generate_with_tools(
        self,
        user_message: str,
        history: List[Dict[str, str]],
        system_prompt: str,
        tool_declarations: List[Dict],
        tool_executor: Callable[[str, dict], Any],
        max_rounds: int = 5,
    ) -> str:
        """
        Full function-calling loop:
        1. Send message → Gemini may return function_call parts
        2. Execute all requested tools
        3. Send results back → repeat until Gemini returns plain text
        """
        model = self._make_model(
            system_prompt,
            tools=[{"function_declarations": tool_declarations}],
        )
        chat = model.start_chat(history=self._to_gemini_history(history))
        response = await chat.send_message_async(user_message)

        for _ in range(max_rounds):
            fc_parts = [
                p for p in response.parts
                if hasattr(p, "function_call") and p.function_call.name
            ]

            if not fc_parts:
                logger.warning(
                    "Gemini returned plain text without calling any tool. "
                    "Reply (first 200 chars): %.200s", response.text
                )
                return response.text

            # Execute every tool the model requested (may be >1 in one turn)
            tool_responses = []
            for part in fc_parts:
                from ..tools import is_tool_error, strip_err
                fc = part.function_call
                result = await tool_executor(fc.name, dict(fc.args))
                logger.info("Tool %s → %.120s", fc.name, result)

                # Short-circuit: if the tool failed, return the error message
                # directly WITHOUT going back to Gemini (prevents hallucination).
                if is_tool_error(result):
                    return strip_err(result)

                tool_responses.append(
                    genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=fc.name,
                            response={"result": result},
                        )
                    )
                )

            response = await chat.send_message_async(tool_responses)

        return response.text
