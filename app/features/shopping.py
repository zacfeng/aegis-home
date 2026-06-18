import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_KEY = "aegis:shopping:{chat_id}"


class ShoppingList:
    def __init__(self, redis: Any):
        self._r = redis

    def _key(self, chat_id: str) -> str:
        return _KEY.format(chat_id=chat_id)

    async def add_item(self, chat_id: str, item: str) -> str:
        key = self._key(chat_id)
        await self._r.rpush(key, item)
        count = await self._r.llen(key)
        return f"✅ 好欸！小恆恆幫你記住了～「{item}」加到購物清單囉！（清單共 {count} 項）"

    async def show_list(self, chat_id: str) -> str:
        items = await self._r.lrange(self._key(chat_id), 0, -1)
        if not items:
            return "🛒 購物清單是空的喔～ 跟小恆恆說要加什麼吧！"
        lines = [f"{i+1}. {item}" for i, item in enumerate(items)]
        return "🛒 購物清單：\n" + "\n".join(lines)

    async def remove_item(self, chat_id: str, item: str) -> str:
        removed = await self._r.lrem(self._key(chat_id), 0, item)
        if removed:
            return f"✅ 「{item}」買完了！小恆恆幫你劃掉～"
        # Try partial match
        all_items = await self._r.lrange(self._key(chat_id), 0, -1)
        for existing in all_items:
            if item in existing or existing in item:
                await self._r.lrem(self._key(chat_id), 0, existing)
                return f"✅ 「{existing}」買完了！小恆恆幫你劃掉～"
        return f"找不到「{item}」在清單裡喔... 是不是打錯字了？"

    async def clear_list(self, chat_id: str) -> str:
        await self._r.delete(self._key(chat_id))
        return "🗑️ 購物清單清空囉！要再買什麼跟小恆恆說喔～"


def parse_shopping_intent(text: str) -> tuple[str, str]:
    """Return (intent, payload). Intents: add | show | remove | clear | none."""
    t = text.strip()

    # Clear
    if re.search(r"(清空|清除|刪光).*(清單|購物)", t) or re.search(r"(清單|購物).*(清空|清除|刪光)", t):
        return "clear", ""

    # Show
    if re.match(r"^(購物清單|清單|待買清單|買的清單)\s*$", t):
        return "show", ""
    if re.search(r"(看|顯示|列出).*(清單|購物)", t):
        return "show", ""

    # Remove / done
    m = re.search(r"^(.+?)(買完了|買好了|已購買|買到了)$", t)
    if m:
        return "remove", m.group(1).strip()
    m = re.search(r"(從清單刪掉|刪掉清單的|清單刪掉|刪掉)\s*(.+)", t)
    if m:
        return "remove", m.group(2).strip()

    # Add — "加牛奶到清單" / "把蘋果加到清單"
    m = re.search(r"(加|把)\s*(.+?)\s*(加入|加到|放到|放進|到)\s*(清單|購物)", t)
    if m:
        return "add", m.group(2).strip()
    m = re.search(r"^(加|新增|補充)\s+(.+?)(\s*(到|入|進)\s*(清單|購物))?$", t)
    if m and not re.search(r"(清單|購物)", m.group(2)):
        return "add", m.group(2).strip()
    m = re.search(r"(加|新增|補充).{0,10}(清單|購物).{0,5}[：:\s]+(.+)", t)
    if m:
        return "add", m.group(3).strip()
    m = re.search(r"(清單|購物).{0,5}(加|新增|補充).{0,5}[：:\s]+(.+)", t)
    if m:
        return "add", m.group(3).strip()
    m = re.search(r"幫我(加|買|記)\s+(.+)", t)
    if m:
        return "add", m.group(2).strip()
    m = re.search(r"要(買|加)\s+(.+)", t)
    if m:
        return "add", m.group(2).strip()

    return "none", ""
