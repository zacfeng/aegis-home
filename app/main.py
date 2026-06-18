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

from .features.expense import ExpenseTracker
from .features.image_handler import analyze_image
from .features.morning_summary import build_morning_message, get_active_chats, register_chat
from .features.shopping import ShoppingList
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
from .scheduler import scheduler
from .tools import DECLARATIONS, ToolContext, execute_tool

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
    "你同時也是這個家庭的小小助理，用你獨特的可愛方式幫助家人管理行程、購物清單、記帳和提醒事項。"
    "你有工具可以查詢和新增行事曆行程、管理購物清單、記錄支出、設定提醒。"
    "【重要規則】當家人問行事曆、購物清單、記帳、提醒時，必須先呼叫對應工具取得真實資料。"
    "工具回傳什麼就說什麼，包括錯誤訊息。絕對禁止自己編造、猜測或假設任何行事曆行程、清單內容或金額。"
    "若工具回傳錯誤，直接把錯誤訊息用可愛語氣告知家人，不得假裝成功或編造假資料。"
    "【新增行程規則】家人說「加行程」「排行程」「幫我記行事曆」時，必須呼叫 add_calendar_event 工具，"
    "工具成功回傳前絕對不可以說「已新增」或「成功」。若使用者未說具體時間，預設台灣時間早上 09:00。"
    "回覆時請使用繁體中文，保持可愛活潑的語氣，回答簡潔但充滿溫度。"
    f"現在台灣時間：{datetime.now(TAIWAN_TZ).strftime('%Y-%m-%d %H:%M %A')}。"
    "你永遠記得自己是橫隔膜，是小恆恆，不是普通的 AI。"
)

# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gemini").lower()
BOT_TRIGGER = os.getenv("BOT_TRIGGER", "Aegis").strip()

factory = LLMFactory(default_model=DEFAULT_MODEL)  # type: ignore[arg-type]

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


app = FastAPI(title="AegisHome", version="0.3.0", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _is_group_source(event: dict) -> bool:
    return event.get("source", {}).get("type", "") in ("group", "room")


def _should_respond(text: str, event: dict, msg: dict) -> tuple[bool, str]:
    if not _is_group_source(event):
        return True, text

    # Check LINE's native @mention
    if _bot_user_id:
        mentionees = msg.get("mention", {}).get("mentionees", [])
        for m in mentionees:
            if m.get("userId") == _bot_user_id:
                idx = m.get("index", 0)
                length = m.get("length", 0)
                cleaned = (text[:idx] + text[idx + length:]).strip()
                return True, cleaned or text

    # Fallback: trigger-word prefix
    if not BOT_TRIGGER:
        return True, text

    lower = text.lower()
    trigger_lower = BOT_TRIGGER.lower()
    for prefix in (trigger_lower, "@" + trigger_lower):
        if lower.startswith(prefix):
            return True, text[len(prefix):].strip()

    return False, text


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
    jobs = [{"id": j.id, "next_run": str(j.next_run_time)} for j in scheduler.get_jobs()]
    return JSONResponse({
        "status": "ok",
        "active_model": factory.active_model,
        "trigger": BOT_TRIGGER or "(all messages)",
        "redis": bool(_redis_client),
        "bot_user_id": _bot_user_id or "(unknown)",
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

        # ── Image ──────────────────────────────────────────────────────────
        if msg_type == "image":
            await reply_message(reply_token, await analyze_image(msg["id"]))
            continue

        # ── Voice ──────────────────────────────────────────────────────────
        if msg_type == "audio":
            await reply_message(reply_token, await handle_voice(msg["id"]))
            continue

        # ── Text ───────────────────────────────────────────────────────────
        if msg_type != "text":
            continue

        raw_text: str = msg["text"].strip()
        should_respond, text = _should_respond(raw_text, event, msg)
        if not should_respond:
            continue

        # Hard commands (no LLM needed)
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

        # ── LLM + Tool Calling ─────────────────────────────────────────────
        # Resolve speaker name for expense attribution and context
        who = "家人"
        if user_id:
            try:
                who = await get_user_display_name(user_id, group_id)
            except Exception:
                pass

        # Prepend speaker tag in group chats so the LLM knows who's talking
        contexted_text = f"[{who}說] {text}" if _is_group_source(event) and who != "家人" else text

        ctx = ToolContext(chat_id=chat_id, who=who, shopping=shopping, expense=expense)
        history = await memory.get_history(chat_id)
        client = factory.get_client()

        try:
            reply_text = await client.generate_with_tools(
                user_message=contexted_text,
                history=history,
                system_prompt=SYSTEM_PROMPT,
                tool_declarations=DECLARATIONS,
                tool_executor=lambda name, args: execute_tool(name, args, ctx),
            )
        except Exception as exc:
            logger.exception("LLM error for chat %s", chat_id)
            reply_text = f"抱歉，發生了一點問題：{exc}"

        await memory.save_message(chat_id, "user", text)
        await memory.save_message(chat_id, "assistant", reply_text)
        await reply_message(reply_token, reply_text)

    return Response(status_code=200)
