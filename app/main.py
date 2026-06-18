import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime

import pytz
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse

load_dotenv()

from .line_handler import extract_chat_id, push_message, reply_message, verify_signature
from .llm_factory import LLMFactory
from .memory_manager import MemoryManager
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
_OPTIONAL_MODEL_KEYS = {
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
    key_name = _OPTIONAL_MODEL_KEYS.get(default_model)
    if key_name and not os.getenv(key_name):
        logger.critical(
            "DEFAULT_MODEL is '%s' but %s is not set", default_model, key_name
        )
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
memory = MemoryManager(maxlen=20)


# ---------------------------------------------------------------------------
# App lifespan (start / stop scheduler)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(_app: FastAPI):
    scheduler.start()
    logger.info("Scheduler started")
    yield
    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped")


app = FastAPI(title="AegisHome", version="0.1.0", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _is_group_source(event: dict) -> bool:
    return event.get("source", {}).get("type", "") in ("group", "room")


def _should_respond(text: str, event: dict) -> tuple[bool, str]:
    if not _is_group_source(event):
        return True, text
    if not BOT_TRIGGER:
        return True, text

    lower = text.lower()
    trigger_lower = BOT_TRIGGER.lower()
    for prefix in (trigger_lower, "@" + trigger_lower):
        if lower.startswith(prefix):
            return True, text[len(prefix):].strip()

    return False, text


async def _schedule_reminder(chat_id: str, reminder: dict) -> None:
    """Parse reminder dict and register an APScheduler job."""
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
        if msg.get("type") != "text":
            continue

        raw_text: str = msg["text"].strip()
        reply_token: str = event["replyToken"]
        chat_id = extract_chat_id(event)

        should_respond, text = _should_respond(raw_text, event)
        if not should_respond:
            continue

        if text.lower() == "/reset":
            memory.clear_history(chat_id)
            await reply_message(reply_token, "對話記憶已清除。")
            continue

        history = memory.get_history(chat_id)
        try:
            client = factory.get_client()
            reply_text = await client.generate_response(
                text, history, system_prompt=SYSTEM_PROMPT
            )
        except Exception as exc:
            logger.exception("LLM error for chat %s", chat_id)
            reply_text = f"抱歉，發生了一點問題：{exc}"

        memory.save_message(chat_id, "user", text)
        memory.save_message(chat_id, "assistant", reply_text)
        await reply_message(reply_token, reply_text)

        # Check if a reminder was embedded in the user's message
        asyncio.ensure_future(
            _try_schedule(text, chat_id)
        )

    return Response(status_code=200)


async def _try_schedule(text: str, chat_id: str) -> None:
    try:
        client = factory.get_client()
        reminder = await parse_reminder(text, client)
        if reminder:
            await _schedule_reminder(chat_id, reminder)
    except Exception:
        logger.exception("_try_schedule error")
