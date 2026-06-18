import json
import logging
import re
from datetime import datetime
from typing import Any

import pytz

logger = logging.getLogger(__name__)
TAIWAN_TZ = pytz.timezone("Asia/Taipei")
_KEY = "aegis:expense:{chat_id}:{month}"
_TTL = 90 * 24 * 3600  # 90 days


class ExpenseTracker:
    def __init__(self, redis: Any):
        self._r = redis

    def _key(self, chat_id: str) -> str:
        month = datetime.now(TAIWAN_TZ).strftime("%Y%m")
        return _KEY.format(chat_id=chat_id, month=month)

    async def add_expense(
        self, chat_id: str, amount: float, description: str, who: str = "家人"
    ) -> str:
        now = datetime.now(TAIWAN_TZ)
        entry = json.dumps(
            {
                "amount": amount,
                "description": description,
                "who": who,
                "time": now.strftime("%m/%d %H:%M"),
            },
            ensure_ascii=False,
        )
        key = self._key(chat_id)
        await self._r.rpush(key, entry)
        await self._r.expire(key, _TTL)
        return f"💰 記好了！{who} 花了 ${amount:.0f} 在「{description}」～小恆恆幫你記住囉！"

    async def monthly_summary(self, chat_id: str) -> str:
        items = await self._r.lrange(self._key(chat_id), 0, -1)
        if not items:
            return "本月還沒有記帳記錄喔～"

        entries = [json.loads(item) for item in items]
        total = sum(e["amount"] for e in entries)
        recent = entries[-15:]
        lines = [
            f"• {e['time']} {e.get('who', '?')} ${e['amount']:.0f} {e['description']}"
            for e in recent
        ]
        now = datetime.now(TAIWAN_TZ)
        header = f"📊 {now.strftime('%Y年%m月')}支出："
        if len(entries) > 15:
            header += f"（顯示最近15筆，共{len(entries)}筆）"
        return header + "\n" + "\n".join(lines) + f"\n\n💴 本月合計：${total:.0f}"


def parse_expense_intent(text: str) -> tuple[str, float, str]:
    """Return (intent, amount, description). Intents: add | summary | none."""
    t = text.strip()

    # Summary
    if re.search(r"(本月|這個月|上個月).*(支出|花了|記帳|消費)", t):
        return "summary", 0, ""
    if re.search(r"^(支出|記帳紀錄|消費紀錄|花了多少)\s*$", t):
        return "summary", 0, ""

    # Add: "花了 350 吃飯" / "記帳 350 晚餐" / "$350 吃飯" / "350元 午餐"
    m = re.search(r"(花了|記一下|記帳|付了)\s*(\d+(?:\.\d+)?)\s*(元|塊|$)?\s*(.+)?", t)
    if m:
        amount = float(m.group(2))
        desc = (m.group(4) or "消費").strip()
        return "add", amount, desc

    m = re.search(r"\$\s*(\d+(?:\.\d+)?)\s+(.+)", t)
    if m:
        return "add", float(m.group(1)), m.group(2).strip()

    m = re.search(r"(\d+(?:\.\d+)?)\s*(元|塊)\s+(.+)", t)
    if m:
        return "add", float(m.group(1)), m.group(3).strip()

    return "none", 0, ""
