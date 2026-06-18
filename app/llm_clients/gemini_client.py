import os
from typing import List, Dict

import google.generativeai as genai

from .base import LLMClient


class GeminiClient(LLMClient):
    def __init__(self, model_name: str = "gemini-1.5-flash"):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set")
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model_name)

    async def generate_response(
        self,
        user_message: str,
        history: List[Dict[str, str]],
    ) -> str:
        # Gemini SDK uses 'model' instead of 'assistant' for the role
        gemini_history = [
            {
                "role": "user" if turn["role"] == "user" else "model",
                "parts": [turn["content"]],
            }
            for turn in history
        ]

        chat = self._model.start_chat(history=gemini_history)
        response = await chat.send_message_async(user_message)
        return response.text
