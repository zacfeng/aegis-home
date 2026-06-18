import logging
import os
import sys

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from .line_handler import extract_chat_id, reply_message, verify_signature
from .llm_factory import LLMFactory
from .memory_manager import MemoryManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s – %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Startup validation – fail loudly rather than silently mis-behave
# ---------------------------------------------------------------------------
_REQUIRED_ENV = [
    "LINE_CHANNEL_ACCESS_TOKEN",
    "LINE_CHANNEL_SECRET",
]
_OPTIONAL_MODEL_KEYS = {
    "gemini": "GEMINI_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
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
# Application-level singletons
# ---------------------------------------------------------------------------
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gemini").lower()

factory = LLMFactory(default_model=DEFAULT_MODEL)  # type: ignore[arg-type]
memory = MemoryManager(maxlen=20)

app = FastAPI(title="AegisHome", version="0.1.0")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "active_model": factory.active_model})


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

        text: str = msg["text"].strip()
        reply_token: str = event["replyToken"]
        chat_id = extract_chat_id(event)

        # ----------------------------------------------------------------
        # Built-in command: /model <name>
        # ----------------------------------------------------------------
        if text.lower().startswith("/model "):
            model_name = text[7:].strip()
            status = factory.switch_model(model_name)
            await reply_message(reply_token, status)
            continue

        # ----------------------------------------------------------------
        # Built-in command: /reset  (clear conversation history)
        # ----------------------------------------------------------------
        if text.lower() == "/reset":
            memory.clear_history(chat_id)
            await reply_message(reply_token, "Conversation history cleared.")
            continue

        # ----------------------------------------------------------------
        # Normal message → LLM
        # ----------------------------------------------------------------
        history = memory.get_history(chat_id)
        try:
            client = factory.get_client()
            reply_text = await client.generate_response(text, history)
        except Exception as exc:
            logger.exception("LLM error for chat %s", chat_id)
            reply_text = f"Sorry, something went wrong: {exc}"

        memory.save_message(chat_id, "user", text)
        memory.save_message(chat_id, "assistant", reply_text)

        await reply_message(reply_token, reply_text)

    return Response(status_code=200)
