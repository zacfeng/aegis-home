import logging
import os
from datetime import datetime
from typing import Any

import httpx
import pytz

logger = logging.getLogger(__name__)
TAIWAN_TZ = pytz.timezone("Asia/Taipei")
_CHATS_KEY = "aegis:active_chats"
_WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"]


async def register_chat(redis: Any, chat_id: str) -> None:
    """Add chat_id to the set that receives morning pushes."""
    await redis.sadd(_CHATS_KEY, chat_id)


async def get_active_chats(redis: Any) -> list[str]:
    members = await redis.smembers(_CHATS_KEY)
    return list(members)


async def _fetch_weather(city: str = "Taipei") -> str:
    api_key = os.getenv("OPENWEATHER_API_KEY", "")
    if not api_key:
        return ""
    try:
        url = (
            f"https://api.openweathermap.org/data/2.5/weather"
            f"?q={city}&appid={api_key}&units=metric&lang=zh_tw"
        )
        async with httpx.AsyncClient(timeout=6) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                desc = data["weather"][0]["description"]
                temp = data["main"]["temp"]
                feels = data["main"]["feels_like"]
                humidity = data["main"]["humidity"]
                return (
                    f"☁️ {city}今天{desc}，{temp:.0f}°C"
                    f"（體感{feels:.0f}°C），濕度{humidity}%"
                )
    except Exception:
        logger.exception("Weather fetch failed")
    return ""


async def build_morning_message() -> str:
    now = datetime.now(TAIWAN_TZ)
    weekday = _WEEKDAYS[now.weekday()]
    date_str = now.strftime(f"%m月%d日（週{weekday}）")

    weather = await _fetch_weather()
    parts = [
        f"🌅 早安！今天是{date_str}",
        "小恆恆在這裡陪你開始美好的一天！ (≧▽≦)",
    ]
    if weather:
        parts.append(weather)
    parts.append("今天有什麼需要小恆恆幫忙安排的嗎？")
    return "\n".join(parts)
