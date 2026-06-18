import hashlib
import hmac
import os
import base64
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

LINE_API_BASE = "https://api.line.me/v2/bot"


def verify_signature(body: bytes, signature: str) -> bool:
    """
    Validate the X-Line-Signature header using HMAC-SHA256.
    Returns False (instead of raising) so the caller can reply 400.
    """
    secret = os.getenv("LINE_CHANNEL_SECRET", "")
    if not secret:
        logger.error("LINE_CHANNEL_SECRET is not configured")
        return False

    expected = base64.b64encode(
        hmac.new(secret.encode(), body, hashlib.sha256).digest()
    ).decode()
    return hmac.compare_digest(expected, signature)


async def reply_message(reply_token: str, text: str) -> None:
    """Send a text reply back to LINE."""
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text}],
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{LINE_API_BASE}/message/reply",
            json=payload,
            headers=headers,
            timeout=10,
        )
        if resp.status_code != 200:
            logger.error(
                "LINE reply failed: %s %s", resp.status_code, resp.text
            )


def extract_chat_id(event: dict[str, Any]) -> str:
    """
    Derive a stable chat identifier:
    - group events  → group ID
    - room events   → room ID
    - 1:1 events    → user ID
    """
    source = event.get("source", {})
    return (
        source.get("groupId")
        or source.get("roomId")
        or source.get("userId")
        or "unknown"
    )
