import os
import httpx
from fastapi import FastAPI, HTTPException, Header, Request, Response
from pydantic import BaseModel
import uvicorn

# 引入 Hermes 核心代理
from agent.core import Agent

app = FastAPI()

class ShortcutPayload(BaseModel):
    message: str
    user_id: str = "apple_shortcut_user"

# 這裡的密鑰可以自己改，iOS 捷徑裡面也要設成一樣的
HERMES_API_KEY = os.environ.get("SHORTCUT_API_KEY", "my_secret_key")
# 內部 Hermes Gateway 跑在 8646
GATEWAY_URL = "http://127.0.0.1:8646"

# 1. 專屬給 iOS 捷徑的 API
@app.post("/v1/shortcut")
async def handle_shortcut(payload: ShortcutPayload, x_api_key: str = Header(None)):
    if x_api_key != HERMES_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # 建立 Agent 實例
    hermes = Agent()
    
    # 將對話傳進去，這裡會自帶記憶跟工具調用！
    try:
        response = await hermes.process_message(
            message=payload.message, 
            user_id=payload.user_id,
            platform="apple_shortcut"
        )
        return {"reply": response.text}
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
