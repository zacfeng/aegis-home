import logging
import os

logger = logging.getLogger(__name__)


async def handle_voice(message_id: str) -> str:
    """Transcribe and respond to a LINE audio message using Gemini."""
    try:
        import google.generativeai as genai  # type: ignore
        from .image_handler import download_line_content

        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            return "小恆恆現在聽不到聲音欸... 需要設定 Gemini API key！"

        genai.configure(api_key=api_key)
        audio_bytes = await download_line_content(message_id)

        model = genai.GenerativeModel("gemini-1.5-flash")
        response = await model.generate_content_async(
            [
                {
                    "inline_data": {
                        "mime_type": "audio/m4a",
                        "data": audio_bytes,
                    }
                },
                (
                    "請先將這段音訊轉成文字（在回覆開頭加上「🎙️ 你說：」和轉錄文字），"
                    "然後用繁體中文可愛活潑地回應，就像可愛的小恆恆！"
                ),
            ]
        )
        return response.text
    except Exception:
        logger.exception("Voice handling failed for message %s", message_id)
        return "哎呀！小恆恆沒聽清楚... 可以再說一次嗎？(›´ω`‹ )"
