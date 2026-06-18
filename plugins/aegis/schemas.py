GET_CALENDAR_EVENTS = {
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
}

ADD_CALENDAR_EVENT = {
    "name": "add_calendar_event",
    "description": (
        "新增行程到 Apple 家人行事曆。"
        "若使用者未指定時間，預設台灣時間 09:00。"
        "必須呼叫此工具，不可自行回覆成功。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "行程名稱"},
            "datetime_iso": {
                "type": "string",
                "description": "台灣時間 ISO 8601，例如 2026-06-25T14:00:00+08:00。若未指定時間，預設 09:00。",
            },
            "duration_minutes": {
                "type": "integer",
                "description": "時長（分鐘），預設 60",
            },
        },
        "required": ["title", "datetime_iso"],
    },
}

GET_SHOPPING_LIST = {
    "name": "get_shopping_list",
    "description": "查看家庭購物清單",
    "parameters": {"type": "object", "properties": {}},
}

ADD_SHOPPING_ITEM = {
    "name": "add_shopping_item",
    "description": "新增項目到購物清單",
    "parameters": {
        "type": "object",
        "properties": {
            "item": {"type": "string", "description": "要購買的東西"}
        },
        "required": ["item"],
    },
}

REMOVE_SHOPPING_ITEM = {
    "name": "remove_shopping_item",
    "description": "從購物清單移除已購買的項目",
    "parameters": {
        "type": "object",
        "properties": {
            "item": {"type": "string", "description": "已買完的東西"}
        },
        "required": ["item"],
    },
}

CLEAR_SHOPPING_LIST = {
    "name": "clear_shopping_list",
    "description": "清空整個購物清單",
    "parameters": {"type": "object", "properties": {}},
}

ADD_EXPENSE = {
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
            "who": {
                "type": "string",
                "description": "誰花的（選填，從對話中推斷）",
            },
        },
        "required": ["amount", "description"],
    },
}

GET_EXPENSE_SUMMARY = {
    "name": "get_expense_summary",
    "description": "查看本月支出記錄和總金額",
    "parameters": {"type": "object", "properties": {}},
}

# ---------------------------------------------------------------------------
# Chores
# ---------------------------------------------------------------------------
GET_CHORES = {
    "name": "get_chores",
    "description": "查看目前的家事清單與負責人",
    "parameters": {"type": "object", "properties": {}},
}

ADD_CHORE = {
    "name": "add_chore",
    "description": "新增待辦家事",
    "parameters": {
        "type": "object",
        "properties": {
            "chore": {"type": "string", "description": "家事內容"},
            "assignee": {"type": "string", "description": "負責人（選填）"}
        },
        "required": ["chore"]
    }
}

REMOVE_CHORE = {
    "name": "remove_chore",
    "description": "標記家事已完成並移除",
    "parameters": {
        "type": "object",
        "properties": {
            "chore": {"type": "string", "description": "完成的家事"}
        },
        "required": ["chore"]
    }
}

# ---------------------------------------------------------------------------
# Family Memo
# ---------------------------------------------------------------------------
LEAVE_MESSAGE = {
    "name": "leave_message",
    "description": "留言給家人",
    "parameters": {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "留言內容"}
        },
        "required": ["message"]
    }
}

GET_MESSAGES = {
    "name": "get_messages",
    "description": "讀取目前的家庭留言板",
    "parameters": {"type": "object", "properties": {}},
}

CLEAR_MESSAGES = {
    "name": "clear_messages",
    "description": "清空留言板",
    "parameters": {"type": "object", "properties": {}},
}

# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------
GET_INVENTORY = {
    "name": "get_inventory",
    "description": "查詢生活用品或食材的庫存狀態",
    "parameters": {"type": "object", "properties": {}},
}

UPDATE_INVENTORY = {
    "name": "update_inventory",
    "description": "更新特定物品的庫存狀態",
    "parameters": {
        "type": "object",
        "properties": {
            "item": {"type": "string", "description": "物品名稱"},
            "status": {"type": "string", "description": "庫存狀態（例如：充足、快用完、已空）"}
        },
        "required": ["item", "status"]
    }
}

# ---------------------------------------------------------------------------
# Pet & Plant Care Tracker
# ---------------------------------------------------------------------------
LOG_CARE_ACTIVITY = {
    "name": "log_care_activity",
    "description": "紀錄已完成的照顧項目（例如：已餵貓、已澆花）",
    "parameters": {
        "type": "object",
        "properties": {
            "activity": {"type": "string", "description": "照顧項目"}
        },
        "required": ["activity"]
    }
}

GET_CARE_STATUS = {
    "name": "get_care_status",
    "description": "查詢今天是否已經做過某項照顧（例如：貓今天餵了嗎？）",
    "parameters": {"type": "object", "properties": {}},
}

# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------
GET_WEATHER = {
    "name": "get_weather",
    "description": "查詢目前天氣（使用 OpenWeather API）",
    "parameters": {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "城市名稱（英文，例如 Taipei, Taichung），預設為 Taipei"
            }
        }
    }
}
