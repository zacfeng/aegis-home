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


async def push_message(to: str, text: str) -> None:
    """Proactively push a message to a user or group (no reply token needed)."""
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    payload = {
        "to": to,
        "messages": [{"type": "text", "text": text}],
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{LINE_API_BASE}/message/push",
            json=payload,
            headers=headers,
            timeout=10,
        )
        if resp.status_code != 200:
            logger.error(
                "LINE push failed: %s %s", resp.status_code, resp.text
            )


async def get_user_display_name(user_id: str, group_id: str | None = None) -> str:
    """Fetch display name from LINE Profile API."""
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"}
    if group_id:
        url = f"{LINE_API_BASE}/group/{group_id}/member/{user_id}"
    else:
        url = f"{LINE_API_BASE}/profile/{user_id}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            return resp.json().get("displayName", "家人")
    return "家人"


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
