import logging
import os
import sys

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse

load_dotenv()

from .line_handler import extract_chat_id, reply_message, verify_signature
from .llm_factory import LLMFactory
from .memory_manager import MemoryManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s – %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Startup validation
# ---------------------------------------------------------------------------
_REQUIRED_ENV = [
    "LINE_CHANNEL_ACCESS_TOKEN",
    "LINE_CHANNEL_SECRET",
]
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
# Persona: 家庭排程助理
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "你是橫隔膜，可愛小恆恆的化身。"
    "你有著嬰兒般純真、好奇、充滿活力的個性，說話方式可愛俏皮，偶爾會用疊字或撒嬌語氣。"
    "你同時也是這個家庭的小小排程助理，用你獨特的可愛方式幫助家人管理行程、提醒事項和日常任務。"
    "回覆時請使用繁體中文，保持可愛活潑的語氣，回答簡潔但充滿溫度。"
    "你永遠記得自己是橫隔膜，是小恆恆，不是普通的 AI。"
)

# ---------------------------------------------------------------------------
# Application-level singletons
# ---------------------------------------------------------------------------
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gemini").lower()

# BOT_TRIGGER: 群組中必須以此關鍵字開頭才會回應，留空則回應所有訊息
# 建議設定為機器人的名字，例如 "Aegis" 或 "小家"
BOT_TRIGGER = os.getenv("BOT_TRIGGER", "Aegis").strip()

factory = LLMFactory(default_model=DEFAULT_MODEL)  # type: ignore[arg-type]
memory = MemoryManager(maxlen=20)

app = FastAPI(title="AegisHome", version="0.1.0")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _is_group_source(event: dict) -> bool:
    source_type = event.get("source", {}).get("type", "")
    return source_type in ("group", "room")


def _should_respond(text: str, event: dict) -> tuple[bool, str]:
    """
    Returns (should_respond, cleaned_message).
    - 1:1 chat: always respond, return text as-is.
    - Group/room: only respond if BOT_TRIGGER prefix found, strip it from message.
    """
    if not _is_group_source(event):
        return True, text

    if not BOT_TRIGGER:
        return True, text

    lower = text.lower()
    trigger_lower = BOT_TRIGGER.lower()
    if lower.startswith(trigger_lower):
        cleaned = text[len(BOT_TRIGGER):].strip()
        return True, cleaned

    return False, text


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({
        "status": "ok",
        "active_model": factory.active_model,
        "trigger": BOT_TRIGGER or "(all messages)",
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

        # ----------------------------------------------------------------
        # Built-in command: /reset  (clear conversation history)
        # ----------------------------------------------------------------
        if text.lower() == "/reset":
            memory.clear_history(chat_id)
            await reply_message(reply_token, "對話記憶已清除。")
            continue

        # ----------------------------------------------------------------
        # Normal message → LLM
        # ----------------------------------------------------------------
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

    return Response(status_code=200)
