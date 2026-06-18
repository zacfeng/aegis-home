import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pytz

logger = logging.getLogger(__name__)
TAIWAN_TZ = pytz.timezone("Asia/Taipei")

# Sentinel prefix: if a tool result starts with this, the calling loop will
# short-circuit and return the message directly WITHOUT sending it back to
# Gemini — preventing hallucination when tools fail.
_ERR = "\x00ERR\x00:"


def _err(msg: str) -> str:
    return f"{_ERR}{msg}"


def is_tool_error(result: str) -> bool:
    return result.startswith(_ERR)


def strip_err(result: str) -> str:
    return result[len(_ERR):]


# ---------------------------------------------------------------------------
# Tool declarations (Gemini function_declarations JSON Schema)
# ---------------------------------------------------------------------------
DECLARATIONS = [
    {
        "name": "get_calendar_events",
        "description": "查詢 Apple 家人行事曆上的行程",
        "parameters": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["today", "tomorrow", "this_week", "next_week"],
                    "description": "today=今天, tomorrow=明天, this_week=本週, next_week=下週",
                }
            },
            "required": ["period"],
        },
    },
    {
        "name": "add_calendar_event",
        "description": "新增行程到 Apple 家人行事曆",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "行程名稱"},
                "datetime_iso": {
                    "type": "string",
                    "description": "台灣時間 ISO 8601，例如 2026-06-25T14:00:00+08:00",
                },
                "duration_minutes": {
                    "type": "integer",
                    "description": "時長（分鐘），預設 60",
                },
            },
            "required": ["title", "datetime_iso"],
        },
    },
    {
        "name": "get_shopping_list",
        "description": "查看家庭購物清單",
    },
    {
        "name": "add_shopping_item",
        "description": "新增項目到購物清單",
        "parameters": {
            "type": "object",
            "properties": {
                "item": {"type": "string", "description": "要購買的東西"}
            },
            "required": ["item"],
        },
    },
    {
        "name": "remove_shopping_item",
        "description": "從購物清單移除已購買的項目",
        "parameters": {
            "type": "object",
            "properties": {
                "item": {"type": "string", "description": "已買完的東西"}
            },
            "required": ["item"],
        },
    },
    {
        "name": "clear_shopping_list",
        "description": "清空整個購物清單",
    },
    {
        "name": "add_expense",
        "description": "記錄一筆家庭支出",
        "parameters": {
            "type": "object",
            "properties": {
                "amount": {"type": "number", "description": "金額（新台幣）"},
                "description": {
                    "type": "string",
                    "description": "消費內容，例如：午餐、買藥、停車費",
                },
            },
            "required": ["amount", "description"],
        },
    },
    {
        "name": "get_expense_summary",
        "description": "查看本月支出記錄和總金額",
    },
    {
        "name": "set_reminder",
        "description": "設定一個定時提醒，時間到了會自動發訊息",
        "parameters": {
            "type": "object",
            "properties": {
                "datetime_iso": {
                    "type": "string",
                    "description": "台灣時間 ISO 8601",
                },
                "message": {"type": "string", "description": "提醒內容"},
            },
            "required": ["datetime_iso", "message"],
        },
    },
]


@dataclass
class ToolContext:
    chat_id: str
    who: str        # speaker's display name (for expense attribution)
    shopping: Any   # ShoppingList | None
    expense: Any    # ExpenseTracker | None


# Strings that the calendar feature returns on failure — used to detect errors
_CAL_ERROR_PREFIXES = ("需要先設定", "找不到", "讀取行事曆時出錯", "需要安裝")


async def execute_tool(name: str, args: dict, ctx: ToolContext) -> str:
    """
    Dispatch a tool call to the appropriate feature module.

    Returns a plain string on success, or _err(msg) on failure.
    The caller (generate_with_tools) will short-circuit on _err results
    so Gemini never gets a chance to hallucinate around a failure.
    """
    logger.info("Tool call: %s(%s)", name, args)
    try:
        match name:
            # ── Calendar ──────────────────────────────────────────────────
            case "get_calendar_events":
                from .features.calendar import get_events, get_week_events
                period = args.get("period", "today")
                if period == "today":
                    result = await get_events(0)
                elif period == "tomorrow":
                    result = await get_events(1)
                elif period == "this_week":
                    result = await get_week_events(0)
                else:
                    result = await get_week_events(1)
                return _err(result) if result.startswith(_CAL_ERROR_PREFIXES) else result

            case "add_calendar_event":
                from .features.calendar import add_event
                dt = datetime.fromisoformat(args["datetime_iso"])
                if dt.tzinfo is None:
                    dt = TAIWAN_TZ.localize(dt)
                result = await add_event(args["title"], dt, args.get("duration_minutes", 60))
                return _err(result) if result.startswith(_CAL_ERROR_PREFIXES + ("新增行程失敗",)) else result

            # ── Shopping ──────────────────────────────────────────────────
            case "get_shopping_list":
                if not ctx.shopping:
                    return _err("需要設定 Redis 才能使用購物清單")
                return await ctx.shopping.show_list(ctx.chat_id)

            case "add_shopping_item":
                if not ctx.shopping:
                    return _err("需要設定 Redis 才能使用購物清單")
                return await ctx.shopping.add_item(ctx.chat_id, args["item"])

            case "remove_shopping_item":
                if not ctx.shopping:
                    return _err("需要設定 Redis 才能使用購物清單")
                return await ctx.shopping.remove_item(ctx.chat_id, args["item"])

            case "clear_shopping_list":
                if not ctx.shopping:
                    return _err("需要設定 Redis 才能使用購物清單")
                return await ctx.shopping.clear_list(ctx.chat_id)

            # ── Expense ───────────────────────────────────────────────────
            case "add_expense":
                if not ctx.expense:
                    return _err("需要設定 Redis 才能使用記帳功能")
                return await ctx.expense.add_expense(
                    ctx.chat_id, args["amount"], args["description"], ctx.who
                )

            case "get_expense_summary":
                if not ctx.expense:
                    return _err("需要設定 Redis 才能使用記帳功能")
                return await ctx.expense.monthly_summary(ctx.chat_id)

            # ── Reminder ──────────────────────────────────────────────────
            case "set_reminder":
                from .line_handler import push_message
                from .scheduler import scheduler

                dt = datetime.fromisoformat(args["datetime_iso"])
                if dt.tzinfo is None:
                    dt = TAIWAN_TZ.localize(dt)
                if dt <= datetime.now(TAIWAN_TZ):
                    return _err("提醒時間已經過去了喔！請改一個未來的時間")

                chat_id = ctx.chat_id
                message = args["message"]

                async def _push():
                    await push_message(chat_id, message)

                scheduler.add_job(
                    _push,
                    trigger="date",
                    run_date=dt,
                    id=f"{chat_id}_{dt.isoformat()}",
                    replace_existing=True,
                )
                return f"已設定！{dt.strftime('%m/%d %H:%M')} 小恆恆會提醒你"

            case _:
                logger.warning("Unknown tool: %s", name)
                return _err(f"不認識這個工具：{name}")

    except Exception as e:
        logger.exception("Tool %s failed with args %s", name, args)
        return _err(f"工具執行錯誤：{e}")
