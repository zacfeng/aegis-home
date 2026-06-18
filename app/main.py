import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import pytz
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse

load_dotenv()

from .features.calendar import add_event as cal_add_event
from .features.calendar import get_events as cal_get_events
from .features.calendar import get_week_events as cal_get_week_events
from .features.calendar import parse_calendar_intent
from .features.expense import ExpenseTracker, parse_expense_intent
from .features.image_handler import analyze_image
from .features.morning_summary import build_morning_message, get_active_chats, register_chat
from .features.shopping import ShoppingList, parse_shopping_intent
from .features.voice_handler import handle_voice
from .line_handler import (
    extract_chat_id,
    get_bot_user_id,
    get_user_display_name,
    push_message,
    reply_message,
    verify_signature,
)
from .llm_factory import LLMFactory
from .memory_manager import MemoryManager, RedisStore
from .reminder_parser import parse_reminder
from .scheduler import scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s – %(message)s",
)
logger = logging.getLogger(__name__)

TAIWAN_TZ = pytz.timezone("Asia/Taipei")

# ---------------------------------------------------------------------------
# Startup validation
# ---------------------------------------------------------------------------
_REQUIRED_ENV = ["LINE_CHANNEL_ACCESS_TOKEN", "LINE_CHANNEL_SECRET"]
_MODEL_KEY_MAP = {
    "gemini": "GEMINI_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "hermes": "HERMES_API_KEY",
}


def _check_env() -> None:
    missing = [k for k in _REQUIRED_ENV if not os.getenv(k)]
    if missing:
        logger.critical("Missing required env vars: %s", missing)
        sys.exit(1)

    default_model = os.getenv("DEFAULT_MODEL", "gemini").lower()
    key_name = _MODEL_KEY_MAP.get(default_model)
    if key_name and not os.getenv(key_name):
        logger.critical("DEFAULT_MODEL is '%s' but %s is not set", default_model, key_name)
        sys.exit(1)


_check_env()

# ---------------------------------------------------------------------------
# Persona
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "你是橫隔膜，可愛小恆恆的化身。"
    "你有著嬰兒般純真、好奇、充滿活力的個性，說話方式可愛俏皮，偶爾會用疊字或撒嬌語氣。"
    "你同時也是這個家庭的小小排程助理，用你獨特的可愛方式幫助家人管理行程、提醒事項和日常任務。"
    "若用戶設定了提醒，請在對話回覆中確認，並告知小恆恆會記得。"
    "回覆時請使用繁體中文，保持可愛活潑的語氣，回答簡潔但充滿溫度。"
    "你永遠記得自己是橫隔膜，是小恆恆，不是普通的 AI。"
)

# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gemini").lower()
BOT_TRIGGER = os.getenv("BOT_TRIGGER", "Aegis").strip()

factory = LLMFactory(default_model=DEFAULT_MODEL)  # type: ignore[arg-type]

# Redis setup (optional — falls back to in-memory deque when REDIS_URL absent)
_redis_client: Any = None
_REDIS_URL = os.getenv("REDIS_URL", "")

if _REDIS_URL:
    import redis.asyncio as _aioredis
    _redis_client = _aioredis.from_url(_REDIS_URL, decode_responses=True)
    logger.info("Redis connected: %s", _REDIS_URL.split("@")[-1])
    memory = MemoryManager(store=RedisStore(_REDIS_URL, maxlen=30), maxlen=30)
else:
    logger.warning("REDIS_URL not set — using in-memory store (non-persistent)")
    memory = MemoryManager(maxlen=30)

shopping: ShoppingList | None = ShoppingList(_redis_client) if _redis_client else None
expense: ExpenseTracker | None = ExpenseTracker(_redis_client) if _redis_client else None

_NO_REDIS_MSG = "需要先設定 Redis 才能使用這個功能喔！請聯絡管理員設定 REDIS_URL～"

# Cached at startup — used to detect @mention in group messages
_bot_user_id: str = ""


# ---------------------------------------------------------------------------
# App lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _bot_user_id
    _bot_user_id = await get_bot_user_id()
    logger.info("Bot user ID: %s", _bot_user_id or "(unknown)")

    scheduler.start()
    logger.info("Scheduler started")

    # Register morning summary cron job (8:00 AM Taiwan time, every day)
    if _redis_client:
        scheduler.add_job(
            _send_morning_summary,
            trigger="cron",
            hour=8,
            minute=0,
            timezone=TAIWAN_TZ,
            id="morning_summary",
            replace_existing=True,
        )
        logger.info("Morning summary cron registered")

    yield

    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped")
    if _redis_client:
        await _redis_client.aclose()


app = FastAPI(title="AegisHome", version="0.2.0", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _is_group_source(event: dict) -> bool:
    return event.get("source", {}).get("type", "") in ("group", "room")


def _should_respond(text: str, event: dict, msg: dict) -> tuple[bool, str]:
    if not _is_group_source(event):
        return True, text

    # Check LINE's native @mention — bot appears in mentionees list
    if _bot_user_id:
        mentionees = msg.get("mention", {}).get("mentionees", [])
        if any(m.get("userId") == _bot_user_id for m in mentionees):
            # Strip the @mention text from the message so the LLM only sees the real content
            mention_text = next(
                (m for m in mentionees if m.get("userId") == _bot_user_id), {}
            )
            idx = mention_text.get("index", 0)
            length = mention_text.get("length", 0)
            cleaned = (text[:idx] + text[idx + length:]).strip()
            return True, cleaned or text

    # Fallback: plain text prefix match (DMs or trigger-word style)
    if not BOT_TRIGGER:
        return True, text

    lower = text.lower()
    trigger_lower = BOT_TRIGGER.lower()
    for prefix in (trigger_lower, "@" + trigger_lower):
        if lower.startswith(prefix):
            return True, text[len(prefix):].strip()

    return False, text


async def _schedule_reminder(chat_id: str, reminder: dict) -> None:
    try:
        run_dt = datetime.fromisoformat(reminder["datetime"])
        if run_dt.tzinfo is None:
            run_dt = TAIWAN_TZ.localize(run_dt)

        if run_dt <= datetime.now(TAIWAN_TZ):
            logger.warning("Reminder time %s is in the past, skipping", run_dt)
            return

        message = reminder.get("message", "時間到囉！")

        async def _push():
            await push_message(chat_id, message)

        scheduler.add_job(
            _push,
            trigger="date",
            run_date=run_dt,
            id=f"{chat_id}_{run_dt.isoformat()}",
            replace_existing=True,
        )
        logger.info("Reminder scheduled for %s → %s", run_dt, chat_id)
    except Exception:
        logger.exception("Failed to schedule reminder")


async def _handle_cal_add(text: str) -> str:
    """Parse event title + datetime from natural language and add to Apple Calendar."""
    try:
        client = factory.get_client()
        reminder = await parse_reminder(text, client)
        if reminder and reminder.get("datetime"):
            from datetime import datetime as dt
            run_dt = dt.fromisoformat(reminder["datetime"])
            title = reminder.get("message", text)
            return await cal_add_event(title, run_dt)
        return "小恆恆看不懂要加什麼行程... 可以說清楚一點嗎？例如：「加行程 看牙醫 明天下午3點」"
    except Exception:
        logger.exception("_handle_cal_add error")
        return "新增行程時出了點問題，可以再試一次嗎？"


async def _try_schedule(text: str, chat_id: str) -> None:
    try:
        client = factory.get_client()
        reminder = await parse_reminder(text, client)
        if reminder:
            await _schedule_reminder(chat_id, reminder)
    except Exception:
        logger.exception("_try_schedule error")


async def _send_morning_summary() -> None:
    if not _redis_client:
        return
    try:
        msg = await build_morning_message()
        chats = await get_active_chats(_redis_client)
        for chat_id in chats:
            await push_message(chat_id, msg)
        logger.info("Morning summary sent to %d chat(s)", len(chats))
    except Exception:
        logger.exception("Morning summary failed")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health")
async def health() -> JSONResponse:
    jobs = [
        {"id": j.id, "next_run": str(j.next_run_time)}
        for j in scheduler.get_jobs()
    ]
    return JSONResponse({
        "status": "ok",
        "active_model": factory.active_model,
        "trigger": BOT_TRIGGER or "(all messages)",
        "redis": bool(_redis_client),
        "pending_reminders": len(jobs),
        "reminders": jobs,
    })


# ---------------------------------------------------------------------------
# LINE Webhook
# ---------------------------------------------------------------------------
@app.post("/webhook")
async def webhook(request: Request) -> Response:
    body = await request.body()
    signature = request.headers.get("X-Line-Signature", "")

    if not verify_signature(body, signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    for event in payload.get("events", []):
        if event.get("type") != "message":
            continue

        msg = event.get("message", {})
        msg_type = msg.get("type", "")
        reply_token: str = event["replyToken"]
        chat_id = extract_chat_id(event)
        source = event.get("source", {})
        user_id = source.get("userId", "")
        group_id = source.get("groupId")

        # Register chat for morning summaries
        if _redis_client:
            asyncio.ensure_future(register_chat(_redis_client, chat_id))

        # ── Image message ──────────────────────────────────────────────────
        if msg_type == "image":
            reply_text = await analyze_image(msg["id"])
            await reply_message(reply_token, reply_text)
            continue

        # ── Audio / voice message ──────────────────────────────────────────
        if msg_type == "audio":
            reply_text = await handle_voice(msg["id"])
            await reply_message(reply_token, reply_text)
            continue

        # ── Text message ───────────────────────────────────────────────────
        if msg_type != "text":
            continue

        raw_text: str = msg["text"].strip()
        should_respond, text = _should_respond(raw_text, event, msg)
        if not should_respond:
            continue

        # Hard commands
        if text.lower() == "/reset":
            await memory.clear_history(chat_id)
            await reply_message(reply_token, "對話記憶清除囉！小恆恆忘記之前說的了 (ﾉ>ω<)ﾉ")
            continue

        if text.lower() in ("/model", "切換模型"):
            models = list(factory._registry.keys())
            await reply_message(
                reply_token,
                f"目前模型：{factory.active_model}\n可用：{', '.join(models)}\n輸入「切換 gemini」等指令切換",
            )
            continue

        if text.lower().startswith("切換 "):
            new_model = text[3:].strip().lower()
            try:
                factory.switch_model(new_model)  # type: ignore[arg-type]
                await reply_message(reply_token, f"好的！小恆恆換成 {new_model} 了～")
            except ValueError as e:
                await reply_message(reply_token, str(e))
            continue

        # ── Structured feature intents (no LLM needed) ────────────────────
        reply_text: str | None = None

        # Shopping list
        shop_intent, shop_payload = parse_shopping_intent(text)
        if shop_intent != "none":
            if not shopping:
                reply_text = _NO_REDIS_MSG
            elif shop_intent == "show":
                reply_text = await shopping.show_list(chat_id)
            elif shop_intent == "add":
                reply_text = await shopping.add_item(chat_id, shop_payload)
            elif shop_intent == "remove":
                reply_text = await shopping.remove_item(chat_id, shop_payload)
            elif shop_intent == "clear":
                reply_text = await shopping.clear_list(chat_id)

        # Expense tracking
        if reply_text is None:
            exp_intent, amount, description = parse_expense_intent(text)
            if exp_intent != "none":
                if not expense:
                    reply_text = _NO_REDIS_MSG
                elif exp_intent == "summary":
                    reply_text = await expense.monthly_summary(chat_id)
                elif exp_intent == "add":
                    who = "家人"
                    if user_id:
                        try:
                            who = await get_user_display_name(user_id, group_id)
                        except Exception:
                            pass
                    reply_text = await expense.add_expense(chat_id, amount, description, who)

        # Apple Calendar
        if reply_text is None:
            cal_intent, extra, cal_raw = parse_calendar_intent(text)
            if cal_intent == "show":
                reply_text = await cal_get_events(extra)
            elif cal_intent == "week":
                reply_text = await cal_get_week_events(extra)
            elif cal_intent == "add":
                reply_text = await _handle_cal_add(cal_raw)

        # ── LLM fallback ──────────────────────────────────────────────────
        if reply_text is None:
            history = await memory.get_history(chat_id)

            # Prepend speaker name for group chats so the LLM knows who said what
            contexted_text = text
            if _is_group_source(event) and user_id:
                try:
                    display_name = await get_user_display_name(user_id, group_id)
                    contexted_text = f"[{display_name}說] {text}"
                except Exception:
                    pass

            try:
                client = factory.get_client()
                reply_text = await client.generate_response(
                    contexted_text, history, system_prompt=SYSTEM_PROMPT
                )
            except Exception as exc:
                logger.exception("LLM error for chat %s", chat_id)
                reply_text = f"抱歉，發生了一點問題：{exc}"

            await memory.save_message(chat_id, "user", text)
            await memory.save_message(chat_id, "assistant", reply_text)

            # Background: check for reminder intent
            asyncio.ensure_future(_try_schedule(text, chat_id))

        await reply_message(reply_token, reply_text)

    return Response(status_code=200)
