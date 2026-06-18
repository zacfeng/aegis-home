import logging
import os

import httpx

logger = logging.getLogger(__name__)
_LINE_CONTENT_URL = "https://api-data.line.me/v2/bot/message/{message_id}/content"


async def download_line_content(message_id: str) -> bytes:
    """Download binary content (image / audio) from LINE's content endpoint."""
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    url = _LINE_CONTENT_URL.format(message_id=message_id)
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        resp.raise_for_status()
        return resp.content


async def analyze_image(message_id: str) -> str:
    """Describe a LINE image using Gemini Vision."""
    try:
        import google.generativeai as genai  # type: ignore

        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            return "小恆恆現在看不到圖片欸... 需要設定 Gemini API key 才行！"

        genai.configure(api_key=api_key)
        image_bytes = await download_line_content(message_id)

        model = genai.GenerativeModel("gemini-1.5-flash")
        response = await model.generate_content_async(
            [
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": image_bytes,
                    }
                },
                "請用繁體中文可愛活潑地描述這張圖片，就像可愛的小恆恆在看圖一樣！如果圖裡有文字，也幫忙讀出來喔。",
            ]
        )
        return response.text
    except Exception:
        logger.exception("Image analysis failed for message %s", message_id)
        return "哎呀！小恆恆看圖片的時候出了點小問題... 可以再傳一次嗎？"
