import os
import json
import hmac
import hashlib
import base64
import subprocess
import logging
import sys
import asyncio
import httpx
from fastapi import FastAPI, HTTPException, Header, Request, Response
from pydantic import BaseModel
import uvicorn

# Setup logging
logging.basicConfig(stream=sys.stdout, level=logging.INFO)
logger = logging.getLogger("api")

app = FastAPI()

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
HERMES_API_KEY = os.environ.get("SHORTCUT_API_KEY")

@app.get("/health")
async def health():
    return {"status": "ok"}

class ShortcutPayload(BaseModel):
    message: str = None
    Body: str = None       # iOS 捷徑預設會用大寫 Body
    user_id: str = "apple_shortcut_user"

    def get_message(self):
        """優先用 message，沒有的話就用 Body"""
        return self.message or self.Body or ""

# 1. 專屬給 iOS 捷徑的 API
@app.post("/v1/shortcut")
async def handle_shortcut(payload: ShortcutPayload, x_api_key: str = Header(None)):
    # 只在有設定 SHORTCUT_API_KEY 環境變數時才驗證
    if HERMES_API_KEY and x_api_key != HERMES_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        msg = payload.get_message()
        if not msg:
            raise HTTPException(status_code=400, detail="message is required")
        cmd = ["hermes", "chat", "-q", msg, "-Q"]
        result = subprocess.run(cmd, capture_output=True, text=True)

        reply = result.stdout.strip()
        if not reply:
            reply = result.stderr.strip()

        return {"reply": reply}
    except Exception as e:
        logger.error(f"Error handling shortcut: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 2. 直接處理 LINE Webhook 並回覆
async def reply_to_line(reply_token: str, text: str):
    if not LINE_CHANNEL_ACCESS_TOKEN:
        logger.error("LINE_CHANNEL_ACCESS_TOKEN is not set, cannot reply")
        return

    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    payload = {
        "replyToken": reply_token,
        "messages": [
            {
                "type": "text",
                "text": text[:5000]  # LINE 限制單則訊息 5000 字
            }
        ]
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
            logger.info(f"Replied to LINE. Status: {resp.status_code}, Response: {resp.text}")
        except Exception as e:
            logger.error(f"Failed to post reply to LINE: {e}")

@app.post("/line/webhook")
async def handle_line_webhook(request: Request, x_line_signature: str = Header(None)):
    body = await request.body()
    body_str = body.decode("utf-8")
    
    # 驗證 LINE Webhook 簽名
    if LINE_CHANNEL_SECRET:
        hash = hmac.new(LINE_CHANNEL_SECRET.encode('utf-8'), body, hashlib.sha256).digest()
        expected_signature = base64.b64encode(hash).decode('utf-8')
        if not hmac.compare_digest(expected_signature, x_line_signature or ""):
            logger.warning("Invalid LINE webhook signature")
            raise HTTPException(status_code=401, detail="Invalid signature")
    else:
        logger.warning("LINE_CHANNEL_SECRET not set, signature verification skipped")

    try:
        data = json.loads(body_str)
    except Exception as e:
        logger.error(f"Failed to parse body JSON: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    events = data.get("events", [])
    for event in events:
        if event.get("type") != "message":
            continue
        
        reply_token = event.get("replyToken")
        message = event.get("message", {})
        
        if not reply_token or message.get("type") != "text":
            continue

        text = message.get("text", "").strip()
        is_group = event.get("source", {}).get("type") in ("group", "room")

        trigger_words = ["小恆恆", "橫隔膜"]
        should_reply = False
        matched_trigger = None

        if not is_group:
            # 1對1私訊：一律回覆
            should_reply = True
        else:
            # 群組對話：需要檢查觸發詞
            for trigger in trigger_words:
                if trigger in text:
                    should_reply = True
                    matched_trigger = trigger
                    break

        if should_reply:
            # 清理文字，移除觸發詞以獲取更精準的 AI 提示詞
            clean_text = text
            if matched_trigger:
                clean_text = text.replace(matched_trigger, "", 1).strip()
                clean_text = clean_text.lstrip(" ,，:：")
            
            logger.info(f"Processing message for AI: {clean_text}")

            try:
                # 呼叫與捷徑相同、已驗證可運作的 hermes CLI 產生回覆
                cmd = ["hermes", "chat", "-q", clean_text, "-Q"]
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                reply = result.stdout.strip()
                if not reply:
                    reply = result.stderr.strip()
                
                if reply:
                    logger.info(f"Replying: {reply}")
                    # 使用非同步發送回覆
                    asyncio.create_task(reply_to_line(reply_token, reply))
                else:
                    logger.warning("Hermes CLI returned empty reply")
            except Exception as e:
                logger.error(f"Error executing hermes CLI: {e}")

    return "ok"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
