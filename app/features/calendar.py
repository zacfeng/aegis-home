import asyncio
import logging
import os
import re
from datetime import datetime, timedelta

import pytz

logger = logging.getLogger(__name__)
TAIWAN_TZ = pytz.timezone("Asia/Taipei")
_ICAL_URL = "https://caldav.icloud.com"


def _get_credentials() -> tuple[str, str]:
    return os.getenv("APPLE_ID", ""), os.getenv("APPLE_APP_PASSWORD", "")


def _target_calendar_name() -> str:
    return os.getenv("APPLE_CALENDAR_NAME", "家人")


def _pick_calendar(calendars: list) -> object | None:
    """Return the calendar matching APPLE_CALENDAR_NAME (case-insensitive), or None."""
    target = _target_calendar_name().lower()
    for cal in calendars:
        try:
            name = (cal.name or "").lower()
        except Exception:
            name = ""
        if name == target:
            return cal
    # Collect available names so the error message is actionable
    names = []
    for cal in calendars:
        try:
            names.append(cal.name)
        except Exception:
            names.append("(unknown)")
    logger.warning("Calendar '%s' not found. Available: %s", _target_calendar_name(), names)
    # Store on the sentinel so callers can include it in the error reply
    _pick_calendar.available = names  # type: ignore[attr-defined]
    return None


def _sync_get_range_events(start: datetime, end: datetime, label: str) -> str:
    """Fetch events across a date range and group them by day."""
    try:
        import caldav  # type: ignore

        username, password = _get_credentials()
        if not username or not password:
            return "需要先設定 APPLE_ID 和 APPLE_APP_PASSWORD 才能讀取行事曆喔！"

        client = caldav.DAVClient(url=_ICAL_URL, username=username, password=password)
        principal = client.principal()
        cal = _pick_calendar(principal.calendars())

        if cal is None:
            return (
                f"找不到「{_target_calendar_name()}」行事曆... "
                "請確認 APPLE_CALENDAR_NAME 設定正確喔！"
            )

        results = cal.date_search(start=start, end=end, expand=True)

        # Group by date
        from collections import defaultdict
        by_day: dict = defaultdict(list)
        for event in results:
            vevent = event.vobject_instance.vevent
            summary = str(vevent.summary.value) if hasattr(vevent, "summary") else "未命名"
            dtstart = vevent.dtstart.value
            if isinstance(dtstart, datetime):
                if dtstart.tzinfo:
                    dtstart = dtstart.astimezone(TAIWAN_TZ)
                day_key = dtstart.strftime("%m/%d")
                time_str = dtstart.strftime("%H:%M")
            else:
                day_key = dtstart.strftime("%m/%d")
                time_str = "全天"
            by_day[day_key].append((time_str, summary))

        if not by_day:
            return f"📅 {label}沒有行程喔！可以好好放鬆～"

        lines = [f"📅 {label}的行程："]
        for day in sorted(by_day):
            events_that_day = sorted(by_day[day])
            lines.append(f"\n【{day}】")
            for t, s in events_that_day:
                lines.append(f"  • {t} {s}")
        return "\n".join(lines)

    except ImportError:
        return "需要安裝 caldav 套件才能使用行事曆功能喔！"
    except Exception as e:
        logger.exception("get_range_events failed")
        return f"讀取行事曆時出錯了... 請確認帳號設定正確！（{e}）"


def _sync_get_events(days_ahead: int) -> str:
    try:
        import caldav  # type: ignore

        username, password = _get_credentials()
        if not username or not password:
            return "需要先設定 APPLE_ID 和 APPLE_APP_PASSWORD 才能讀取行事曆喔！"

        client = caldav.DAVClient(url=_ICAL_URL, username=username, password=password)
        principal = client.principal()
        cal = _pick_calendar(principal.calendars())

        if cal is None:
            available = getattr(_pick_calendar, "available", [])
            hint = f"帳號裡有這些行事曆：{', '.join(available)}" if available else ""
            return (
                f"找不到「{_target_calendar_name()}」行事曆。{hint} "
                "請在 Railway Variables 設定正確的 APPLE_CALENDAR_NAME 喔！"
            )

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
        cal = _pick_calendar(principal.calendars())

        if cal is None:
            available = getattr(_pick_calendar, "available", [])
            hint = f"帳號裡有：{', '.join(available)}" if available else ""
            return (
                f"找不到「{_target_calendar_name()}」行事曆。{hint} "
                "請設定正確的 APPLE_CALENDAR_NAME 喔！"
            )

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

        cal.add_event(ical)
        return (
            f"📅 好的！小恆恆幫你把「{title}」加到{_target_calendar_name()}行事曆了～\n"
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


async def get_week_events(offset_weeks: int = 0) -> str:
    """Return events for this week (offset_weeks=0) or next week (offset_weeks=1)."""
    from datetime import date
    loop = asyncio.get_event_loop()

    now = datetime.now(TAIWAN_TZ)
    # Monday of the target week
    days_to_monday = now.weekday()  # 0=Mon
    monday = (now - timedelta(days=days_to_monday) + timedelta(weeks=offset_weeks)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    sunday = monday + timedelta(days=6, hours=23, minutes=59, seconds=59)
    label = "下週" if offset_weeks == 1 else "本週"
    return await loop.run_in_executor(None, _sync_get_range_events, monday, sunday, label)


async def add_event(title: str, dt: datetime, duration_minutes: int = 60) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_add_event, title, dt, duration_minutes)


# ---------------------------------------------------------------------------
# Intent parsing
# ---------------------------------------------------------------------------

def parse_calendar_intent(text: str) -> tuple[str, int, str]:
    """
    Return (intent, extra, raw_text).

    intent  extra  meaning
    ------  -----  -------
    show    0      today
    show    1      tomorrow
    show    N≥2    N days ahead
    week    0      this week
    week    1      next week
    add     0      add event (raw_text has full message)
    none    0      not a calendar request
    """
    t = text.strip()

    # Week view
    if re.search(r"下週.*(行程|行事曆|有什麼|幹嘛|安排)", t) or re.search(r"(行程|行事曆).*(下週|下星期)", t):
        return "week", 1, ""
    if re.search(r"(本週|這週|這星期).*(行程|行事曆|有什麼|幹嘛|安排)", t) or re.search(r"(行程|行事曆).*(本週|這週|這星期)", t):
        return "week", 0, ""

    # Single day
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
