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
    "description": "新增項目到購物清單。可指定購買的地點、商場或類別（例如：Costco、全聯、傳統市場，選填，預設為「一般」）。",
    "parameters": {
        "type": "object",
        "properties": {
            "item": {"type": "string", "description": "要購買的東西"},
            "category": {"type": "string", "description": "商場、超市、市場或分類名稱（例如：Costco、全聯，選填）"}
        },
        "required": ["item"],
    },
}

REMOVE_SHOPPING_ITEM = {
    "name": "remove_shopping_item",
    "description": "從購物清單移除已購買的項目。可指定特定的商場或分類以精準移除。",
    "parameters": {
        "type": "object",
        "properties": {
            "item": {"type": "string", "description": "已買完的東西"},
            "category": {"type": "string", "description": "商場或分類名稱，選填"}
        },
        "required": ["item"],
    },
}

CLEAR_SHOPPING_LIST = {
    "name": "clear_shopping_list",
    "description": "清空購物清單。可指定商場或分類名稱以僅清空該商場的項目，未指定則清空整個清單。",
    "parameters": {
        "type": "object",
        "properties": {
            "category": {"type": "string", "description": "商場或分類名稱，選填"}
        },
    },
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
# Inventory
# ---------------------------------------------------------------------------
GET_INVENTORY = {
    "name": "get_inventory",
    "description": "查詢生活用品或食材的庫存狀態",
    "parameters": {"type": "object", "properties": {}},
}

UPDATE_INVENTORY = {
    "name": "update_inventory",
    "description": "新增或更新物品的庫存狀態、到期日及預期消耗時間（天數）",
    "parameters": {
        "type": "object",
        "properties": {
            "item": {"type": "string", "description": "物品名稱"},
            "status": {"type": "string", "description": "庫存狀態（例如：充足、快用完、已空，選填，預設為「充足」）"},
            "expiry_date": {"type": "string", "description": "到期日期，格式為 YYYY-MM-DD（例如：2026-06-25，選填）"},
            "consume_within_days": {"type": "integer", "description": "預計要在幾天內消耗完畢（填寫天數整數，例如：5，選填）"}
        },
        "required": ["item"]
    }
}

GET_CONSUMPTION_QUEUE = {
    "name": "get_consumption_queue",
    "description": "查詢待消耗清單，將會列出即將過期或需要儘快消耗的物品，並依照到期或剩餘消耗時間由近到遠（即將過期優先）排序。",
    "parameters": {"type": "object", "properties": {}},
}

ADD_ACTIVITY_LOG = {
    "name": "add_activity_log",
    "description": "記錄一筆家庭活動或備忘錄，以便未來回顧。",
    "parameters": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "活動或事件內容（例如：「全家今天去奧利家烤肉」、「大掃除完成」）"},
            "date": {"type": "string", "description": "活動發生的日期，格式為 YYYY-MM-DD（例如：2026-06-20，選填，預設為今天）"}
        },
        "required": ["content"]
    }
}

GET_ACTIVITY_LOGS = {
    "name": "get_activity_logs",
    "description": "查詢並回顧過去的家庭活動記錄與備忘錄。",
    "parameters": {
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "關鍵字過濾，僅回傳包含此關鍵字的活動記錄（選填）"},
            "limit": {"type": "integer", "description": "回傳紀錄的最大筆數，預設為 50（選填）"}
        }
    }
}



