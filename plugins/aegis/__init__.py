from . import schemas, tools

_TOOLS = [
    ("get_calendar_events",  schemas.GET_CALENDAR_EVENTS,  tools.get_calendar_events),
    ("add_calendar_event",   schemas.ADD_CALENDAR_EVENT,   tools.add_calendar_event),
    ("get_shopping_list",    schemas.GET_SHOPPING_LIST,    tools.get_shopping_list),
    ("add_shopping_item",    schemas.ADD_SHOPPING_ITEM,    tools.add_shopping_item),
    ("remove_shopping_item", schemas.REMOVE_SHOPPING_ITEM, tools.remove_shopping_item),
    ("clear_shopping_list",  schemas.CLEAR_SHOPPING_LIST,  tools.clear_shopping_list),
    ("add_expense",          schemas.ADD_EXPENSE,          tools.add_expense),
    ("get_expense_summary",  schemas.GET_EXPENSE_SUMMARY,  tools.get_expense_summary),
    ("get_chores",           schemas.GET_CHORES,           tools.get_chores),
    ("add_chore",            schemas.ADD_CHORE,            tools.add_chore),
    ("remove_chore",         schemas.REMOVE_CHORE,         tools.remove_chore),
    ("get_inventory",        schemas.GET_INVENTORY,        tools.get_inventory),
    ("update_inventory",     schemas.UPDATE_INVENTORY,     tools.update_inventory),
    ("get_consumption_queue", schemas.GET_CONSUMPTION_QUEUE, tools.get_consumption_queue),
]


def register(ctx) -> None:
    for name, schema, handler in _TOOLS:
        ctx.register_tool(
            name=name,
            toolset="aegis",
            schema=schema,
            handler=handler,
        )
