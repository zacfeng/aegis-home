import json
import os
import uuid
from collections import defaultdict
from datetime import datetime, timedelta

import pytz

TAIWAN_TZ = pytz.timezone("Asia/Taipei")
_ICAL_URL = "https://caldav.icloud.com"
_SHOPPING_KEY = "aegis:shopping"
_EXPENSE_KEY_PREFIX = "aegis:expense"
_CHORES_KEY = "aegis:chores"
_MEMOS_KEY = "aegis:memos"
_INVENTORY_KEY = "aegis:inventory"

# ---------------------------------------------------------------------------
# Return helpers
# ---------------------------------------------------------------------------
def _ok(data: dict) -> str:
    return json.dumps({"ok": True, **data}, ensure_ascii=False)


def _err(msg: str) -> str:
    return json.dumps({"ok": False, "error": msg}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Resource helpers
# ---------------------------------------------------------------------------
def _redis():
    url = os.getenv("REDIS_URL", "")
    if not url:
        return None
    import redis  # type: ignore
    return redis.from_url(url, decode_responses=True)


def _cal_connect():
    username = os.getenv("APPLE_ID", "")
    password = os.getenv("APPLE_APP_PASSWORD", "")
    print(f"[DEBUG] _cal_connect called. APPLE_ID: {'set (' + username[:3] + '...)' if username else 'NOT SET'}, APPLE_APP_PASSWORD: {'set' if password else 'NOT SET'}", flush=True)
    if not username or not password:
        raise RuntimeError("需要設定 APPLE_ID 和 APPLE_APP_PASSWORD")
    import caldav  # type: ignore
    return caldav.DAVClient(url=_ICAL_URL, username=username, password=password)


def _pick_calendar(client):
    target = os.getenv("APPLE_CALENDAR_NAME", "家人").lower()
    principal = client.principal()
    calendars = principal.calendars()
    for cal in calendars:
        try:
            if (cal.name or "").lower() == target:
                return cal
        except Exception:
            pass
    names = []
    for cal in calendars:
        try:
            names.append(cal.name)
        except Exception:
            names.append("(unknown)")
    raise RuntimeError(
        f"找不到「{os.getenv('APPLE_CALENDAR_NAME', '家人')}」行事曆。"
        f"帳號裡有：{', '.join(names)}"
    )


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------
def get_calendar_events(args: dict, **kw) -> str:
    try:
        period = args.get("period", "today")
        client = _cal_connect()
        cal = _pick_calendar(client)
        now = datetime.now(TAIWAN_TZ)

        if period in ("today", "tomorrow"):
            offset = 0 if period == "today" else 1
            target = now + timedelta(days=offset)
            start = target.replace(hour=0, minute=0, second=0, microsecond=0)
            end = target.replace(hour=23, minute=59, second=59, microsecond=999999)
            events = []
            for event in cal.date_search(start=start, end=end, expand=True):
                vevent = event.vobject_instance.vevent
                summary = str(vevent.summary.value) if hasattr(vevent, "summary") else "未命名"
                dtstart = vevent.dtstart.value
                if isinstance(dtstart, datetime):
                    if dtstart.tzinfo:
                        dtstart = dtstart.astimezone(TAIWAN_TZ)
                    time_str = dtstart.strftime("%H:%M")
                else:
                    time_str = "全天"
                events.append({"time": time_str, "title": summary})
            events.sort(key=lambda e: e["time"])
            return _ok({"period": period, "events": events})

        else:  # this_week / next_week
            offset_weeks = 0 if period == "this_week" else 1
            monday = (now - timedelta(days=now.weekday()) + timedelta(weeks=offset_weeks)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            sunday = monday + timedelta(days=6, hours=23, minutes=59, seconds=59)
            by_day: dict = defaultdict(list)
            for event in cal.date_search(start=monday, end=sunday, expand=True):
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
                by_day[day_key].append({"time": time_str, "title": summary})
            events_by_day = {
                day: sorted(evs, key=lambda e: e["time"])
                for day, evs in sorted(by_day.items())
            }
            return _ok({"period": period, "events_by_day": events_by_day})

    except ImportError:
        return _err("需要安裝 caldav 套件")
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return _err(str(exc))


def add_calendar_event(args: dict, **kw) -> str:
    try:
        title = args["title"]
        dt = datetime.fromisoformat(args["datetime_iso"])
        if dt.tzinfo is None:
            dt = TAIWAN_TZ.localize(dt)
        dt_local = dt.astimezone(TAIWAN_TZ)
        dt_utc = dt_local.astimezone(pytz.utc)
        duration = int(args.get("duration_minutes", 60))
        dtend_utc = dt_utc + timedelta(minutes=duration)

        client = _cal_connect()
        cal = _pick_calendar(client)

        ical = (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//AegisHome//橫隔膜//EN\r\n"
            "BEGIN:VEVENT\r\n"
            f"UID:{uuid.uuid4()}@aegishome\r\n"
            f"SUMMARY:{title}\r\n"
            f"DTSTART:{dt_utc.strftime('%Y%m%dT%H%M%SZ')}\r\n"
            f"DTEND:{dtend_utc.strftime('%Y%m%dT%H%M%SZ')}\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )
        cal.add_event(ical)
        return _ok({
            "title": title,
            "datetime": dt_local.strftime("%m/%d %H:%M"),
            "duration_minutes": duration,
        })

    except ImportError:
        return _err("需要安裝 caldav 套件")
    except KeyError as exc:
        return _err(f"缺少必要參數：{exc}")
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return _err(str(exc))


# ---------------------------------------------------------------------------
# Shopping list
# ---------------------------------------------------------------------------
def get_shopping_list(args: dict, **kw) -> str:
    r = _redis()
    if not r:
        return _err("需要設定 REDIS_URL 才能使用購物清單")
    try:
        items = list(r.lrange(_SHOPPING_KEY, 0, -1))
        return _ok({"items": items})
    except Exception as exc:
        return _err(str(exc))


def add_shopping_item(args: dict, **kw) -> str:
    r = _redis()
    if not r:
        return _err("需要設定 REDIS_URL")
    try:
        item = args["item"]
        r.rpush(_SHOPPING_KEY, item)
        items = list(r.lrange(_SHOPPING_KEY, 0, -1))
        return _ok({"added": item, "items": items})
    except Exception as exc:
        return _err(str(exc))


def remove_shopping_item(args: dict, **kw) -> str:
    r = _redis()
    if not r:
        return _err("需要設定 REDIS_URL")
    try:
        item = args["item"]
        removed = r.lrem(_SHOPPING_KEY, 0, item)
        if removed == 0:
            return _err(f"清單裡找不到「{item}」")
        items = list(r.lrange(_SHOPPING_KEY, 0, -1))
        return _ok({"removed": item, "items": items})
    except Exception as exc:
        return _err(str(exc))


def clear_shopping_list(args: dict, **kw) -> str:
    r = _redis()
    if not r:
        return _err("需要設定 REDIS_URL")
    try:
        r.delete(_SHOPPING_KEY)
        return _ok({"cleared": True})
    except Exception as exc:
        return _err(str(exc))


# ---------------------------------------------------------------------------
# Expense tracker
# ---------------------------------------------------------------------------
def _expense_key() -> str:
    return f"{_EXPENSE_KEY_PREFIX}:{datetime.now(TAIWAN_TZ).strftime('%Y-%m')}"


def add_expense(args: dict, **kw) -> str:
    r = _redis()
    if not r:
        return _err("需要設定 REDIS_URL 才能使用記帳功能")
    try:
        amount = float(args["amount"])
        description = args["description"]
        who = args.get("who", "家人")
        now_str = datetime.now(TAIWAN_TZ).strftime("%m/%d %H:%M")
        entry = json.dumps(
            {"amount": amount, "description": description, "who": who, "time": now_str},
            ensure_ascii=False,
        )
        key = _expense_key()
        r.rpush(key, entry)
        r.expire(key, 60 * 60 * 24 * 90)
        return _ok({"amount": amount, "description": description, "who": who})
    except Exception as exc:
        return _err(str(exc))


def get_expense_summary(args: dict, **kw) -> str:
    r = _redis()
    if not r:
        return _err("需要設定 REDIS_URL 才能使用記帳功能")
    try:
        raw = r.lrange(_expense_key(), 0, -1)
        entries = [json.loads(e) for e in raw]
        total = sum(e["amount"] for e in entries)
        month = datetime.now(TAIWAN_TZ).strftime("%Y/%m")
        return _ok({"month": month, "total_ntd": total, "entries": entries})
    except Exception as exc:
        return _err(str(exc))


# ---------------------------------------------------------------------------
# Chores
# ---------------------------------------------------------------------------
def get_chores(args: dict, **kw) -> str:
    r = _redis()
    if not r:
        return _err("需要設定 REDIS_URL 才能使用家事追蹤")
    try:
        items = list(r.lrange(_CHORES_KEY, 0, -1))
        chores = [json.loads(i) for i in items]
        return _ok({"chores": chores})
    except Exception as exc:
        return _err(str(exc))


def add_chore(args: dict, **kw) -> str:
    r = _redis()
    if not r:
        return _err("需要設定 REDIS_URL 才能使用家事追蹤")
    try:
        chore = args["chore"]
        assignee = args.get("assignee", "未指定")
        entry = json.dumps({"chore": chore, "assignee": assignee}, ensure_ascii=False)
        r.rpush(_CHORES_KEY, entry)
        return _ok({"added": chore, "assignee": assignee})
    except Exception as exc:
        return _err(str(exc))


def remove_chore(args: dict, **kw) -> str:
    r = _redis()
    if not r:
        return _err("需要設定 REDIS_URL 才能使用家事追蹤")
    try:
        target = args["chore"]
        items = list(r.lrange(_CHORES_KEY, 0, -1))
        for item in items:
            parsed = json.loads(item)
            if parsed.get("chore") == target:
                r.lrem(_CHORES_KEY, 1, item)
                return _ok({"removed": target})
        return _err(f"找不到家事：「{target}」")
    except Exception as exc:
        return _err(str(exc))





# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------
def get_inventory(args: dict, **kw) -> str:
    r = _redis()
    if not r:
        return _err("需要設定 REDIS_URL 才能使用庫存追蹤")
    try:
        items = r.hgetall(_INVENTORY_KEY)
        return _ok({"inventory": items})
    except Exception as exc:
        return _err(str(exc))


def update_inventory(args: dict, **kw) -> str:
    r = _redis()
    if not r:
        return _err("需要設定 REDIS_URL 才能使用庫存追蹤")
    try:
        item = args["item"]
        status = args["status"]
        r.hset(_INVENTORY_KEY, item, status)
        return _ok({"item": item, "status": status})
    except Exception as exc:
        return _err(str(exc))


# ---------------------------------------------------------------------------
# Pet & Plant Care
# ---------------------------------------------------------------------------
def log_care_activity(args: dict, **kw) -> str:
    r = _redis()
    if not r:
        return _err("需要設定 REDIS_URL 才能使用照顧追蹤")
    try:
        act = args["activity"]
        now_str = datetime.now(TAIWAN_TZ).strftime("%H:%M")
        entry = f"[{now_str}] {act}"
        key = f"aegis:care:{datetime.now(TAIWAN_TZ).strftime('%Y-%m-%d')}"
        r.rpush(key, entry)
        r.expire(key, 60 * 60 * 24 * 7)  # keep for 7 days
        return _ok({"logged": entry})
    except Exception as exc:
        return _err(str(exc))


def get_care_status(args: dict, **kw) -> str:
    r = _redis()
    if not r:
        return _err("需要設定 REDIS_URL 才能使用照顧追蹤")
    try:
        key = f"aegis:care:{datetime.now(TAIWAN_TZ).strftime('%Y-%m-%d')}"
        activities = list(r.lrange(key, 0, -1))
        return _ok({"date": datetime.now(TAIWAN_TZ).strftime('%Y-%m-%d'), "activities": activities})
    except Exception as exc:
        return _err(str(exc))



