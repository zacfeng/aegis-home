import asyncio
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Optional

import pytz

logger = logging.getLogger(__name__)
TAIWAN_TZ = pytz.timezone("Asia/Taipei")
_ICAL_URL = "https://caldav.icloud.com"


def _get_credentials() -> tuple[str, str]:
    return os.getenv("APPLE_ID", ""), os.getenv("APPLE_APP_PASSWORD", "")


def _sync_get_events(days_ahead: int) -> str:
    try:
        import caldav  # type: ignore

        username, password = _get_credentials()
        if not username or not password:
            return "需要先設定 APPLE_ID 和 APPLE_APP_PASSWORD 才能讀取行事曆喔！"

        client = caldav.DAVClient(url=_ICAL_URL, username=username, password=password)
        principal = client.principal()
        calendars = principal.calendars()

        now = datetime.now(TAIWAN_TZ)
        target = now + timedelta(days=days_ahead)
        start = target.replace(hour=0, minute=0, second=0, microsecond=0)
        end = target.replace(hour=23, minute=59, second=59, microsecond=999999)

        if days_ahead == 0:
            day_label = "今天"
        elif days_ahead == 1:
            day_label = "明天"
        else:
            day_label = target.strftime("%-m月%-d日")

        events: list[tuple[str, str]] = []
        for cal in calendars:
            try:
                results = cal.date_search(start=start, end=end, expand=True)
                for event in results:
                    vevent = event.vobject_instance.vevent
                    summary = str(vevent.summary.value) if hasattr(vevent, "summary") else "未命名"
                    dtstart = vevent.dtstart.value
                    if isinstance(dtstart, datetime):
                        if dtstart.tzinfo:
                            dtstart = dtstart.astimezone(TAIWAN_TZ)
                        time_str = dtstart.strftime("%H:%M")
                    else:
                        time_str = "全天"
                    events.append((time_str, summary))
            except Exception:
                logger.exception("Error reading calendar")

        if not events:
            return f"📅 {day_label}沒有行程喔！可以好好放鬆～"

        events.sort()
        lines = [f"• {t} {s}" for t, s in events]
        return f"📅 {day_label}的行程：\n" + "\n".join(lines)

    except ImportError:
        return "需要安裝 caldav 套件才能使用行事曆功能喔！"
    except Exception as e:
        logger.exception("get_events failed")
        return f"讀取行事曆時出錯了... 請確認帳號設定正確！（{e}）"


def _sync_add_event(title: str, dt: datetime, duration_minutes: int = 60) -> str:
    try:
        import caldav  # type: ignore

        username, password = _get_credentials()
        if not username or not password:
            return "需要先設定 APPLE_ID 和 APPLE_APP_PASSWORD 才能新增行程喔！"

        client = caldav.DAVClient(url=_ICAL_URL, username=username, password=password)
        principal = client.principal()
        calendars = principal.calendars()
        if not calendars:
            return "找不到任何行事曆..."

        dt_local = dt if dt.tzinfo else TAIWAN_TZ.localize(dt)
        dt_utc = dt_local.astimezone(pytz.utc)
        dtend_utc = dt_utc + timedelta(minutes=duration_minutes)

        ical = (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//AegisHome//橫隔膜//EN\r\n"
            "BEGIN:VEVENT\r\n"
            f"SUMMARY:{title}\r\n"
            f"DTSTART:{dt_utc.strftime('%Y%m%dT%H%M%SZ')}\r\n"
            f"DTEND:{dtend_utc.strftime('%Y%m%dT%H%M%SZ')}\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )

        calendars[0].add_event(ical)
        return (
            f"📅 好的！小恆恆幫你把「{title}」加到行事曆了～\n"
            f"時間：{dt_local.strftime('%m/%d（%A）%H:%M')}"
        )

    except ImportError:
        return "需要安裝 caldav 套件才能使用行事曆功能喔！"
    except Exception as e:
        logger.exception("add_event failed")
        return f"新增行程失敗了... 請確認設定正確！（{e}）"


async def get_events(days_ahead: int = 0) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_get_events, days_ahead)


async def add_event(title: str, dt: datetime, duration_minutes: int = 60) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_add_event, title, dt, duration_minutes)


# ---------------------------------------------------------------------------
# Intent parsing
# ---------------------------------------------------------------------------

def parse_calendar_intent(text: str) -> tuple[str, int, str]:
    """
    Return (intent, days_ahead, raw_event_text).
    Intents: show | add | none
    """
    t = text.strip()

    # Show schedule
    if re.search(r"今天.*(行程|行事曆|有什麼|幹嘛|要做)", t) or re.match(r"^(今天行程|行程|今天有啥|今天有什麼)\s*$", t):
        return "show", 0, ""
    if re.search(r"明天.*(行程|行事曆|有什麼|幹嘛)", t) or re.match(r"^明天行程\s*$", t):
        return "show", 1, ""
    m = re.search(r"(\d+)\s*天後.*(行程|行事曆)", t)
    if m:
        return "show", int(m.group(1)), ""

    # Add event
    if re.search(r"(加行程|新增行程|幫我排|加到行事曆|加.*行事曆|加.*行程)", t):
        return "add", 0, t

    return "none", 0, ""
