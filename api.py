import os
import httpx
from fastapi import FastAPI, HTTPException, Header, Request, Response
from pydantic import BaseModel
import uvicorn



app = FastAPI()

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

# 這裡的密鑰可以自己改，iOS 捷徑裡面也要設成一樣的
HERMES_API_KEY = os.environ.get("SHORTCUT_API_KEY", "my_secret_key")
# 內部 Hermes Gateway 跑在 8646
GATEWAY_URL = "http://127.0.0.1:8646"

# 1. 專屬給 iOS 捷徑的 API
import subprocess

@app.post("/v1/shortcut")
async def handle_shortcut(payload: ShortcutPayload, x_api_key: str = Header(None)):
    if x_api_key != HERMES_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    try:
        # 使用 subprocess 呼叫 hermes CLI 的單次回覆模式
        msg = payload.get_message()
        if not msg:
            raise HTTPException(status_code=400, detail="message is required")
        cmd = ["hermes", "chat", "-q", msg, "-Q"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # 將標準輸出作為回覆，若為空則嘗試回傳標準錯誤
        reply = result.stdout.strip()
        if not reply:
            reply = result.stderr.strip()
            
        return {"reply": reply}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 2. 將其他所有請求（包含 LINE Webhook）轉發給背景的 Hermes Gateway
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
async def proxy_to_gateway(request: Request, path: str):
    async with httpx.AsyncClient() as client:
        # 準備轉發的網址與標頭
        url = f"{GATEWAY_URL}/{path}"
        headers = dict(request.headers)
        headers.pop("host", None)
        
        # 讀取原本的 body
        body = await request.body()
        
        try:
            # 呼叫背景的 Hermes Gateway
            proxy_req = client.build_request(
                request.method,
                url,
                headers=headers,
                content=body,
                params=request.query_params
            )
            proxy_resp = await client.send(proxy_req)
            
            # 將結果原封不動回傳給 LINE
            return Response(
                content=proxy_resp.content,
                status_code=proxy_resp.status_code,
                headers=dict(proxy_resp.headers)
            )
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Gateway proxy error: {str(e)}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
