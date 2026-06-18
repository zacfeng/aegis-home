import json
import logging
from datetime import datetime

import pytz

from .llm_clients.base import LLMClient

logger = logging.getLogger(__name__)
TAIWAN_TZ = pytz.timezone("Asia/Taipei")

_PARSE_PROMPT = """\
你是一個提醒時間解析器，請分析用戶訊息是否包含提醒請求。

現在台灣時間：{now}

只回傳 JSON，不要其他文字。

若有提醒請求：
{{"has_reminder": true, "datetime": "YYYY-MM-DDTHH:MM:00+08:00", "message": "小恆恆可愛版的提醒內容"}}

若沒有提醒請求：
{{"has_reminder": false}}

用戶訊息：「{user_message}」"""


async def parse_reminder(user_message: str, client: LLMClient) -> dict | None:
    """
    Return a dict with keys (has_reminder, datetime, message) if a reminder
    is detected, otherwise return None.
    """
    now = datetime.now(TAIWAN_TZ).strftime("%Y-%m-%d %H:%M %A")
    prompt = _PARSE_PROMPT.format(now=now, user_message=user_message)

    try:
        raw = await client.generate_response(prompt, [])
        # Strip markdown code fences if present
        clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(clean)
        if data.get("has_reminder") and data.get("datetime"):
            return data
    except Exception:
        logger.exception("reminder_parser failed")

    return None
