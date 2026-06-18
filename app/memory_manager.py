import json
from collections import deque
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Store protocol
# ---------------------------------------------------------------------------

class MessageStore:
    """
    Interface for backing stores.
    Implement get / append / clear to swap DequeStore for RedisStore
    without touching MemoryManager.
    """

    async def get(self, chat_id: str) -> List[Dict[str, str]]:
        raise NotImplementedError

    async def append(self, chat_id: str, message: Dict[str, str]) -> None:
        raise NotImplementedError

    async def clear(self, chat_id: str) -> None:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# In-process deque store (default, no persistence)
# ---------------------------------------------------------------------------

class DequeStore(MessageStore):
    def __init__(self, maxlen: int = 20):
        self._maxlen = maxlen
        self._data: Dict[str, deque] = {}

    def _bucket(self, chat_id: str) -> deque:
        if chat_id not in self._data:
            self._data[chat_id] = deque(maxlen=self._maxlen)
        return self._data[chat_id]

    async def get(self, chat_id: str) -> List[Dict[str, str]]:
        return list(self._bucket(chat_id))

    async def append(self, chat_id: str, message: Dict[str, str]) -> None:
        self._bucket(chat_id).append(message)

    async def clear(self, chat_id: str) -> None:
        self._data.pop(chat_id, None)


# ---------------------------------------------------------------------------
# Redis store (persistent)
# ---------------------------------------------------------------------------

class RedisStore(MessageStore):
    """
    Persists conversation history in Redis lists.
    Keys: aegis:memory:{chat_id}  — TTL 30 days
    """

    _TTL = 30 * 24 * 3600  # 30 days in seconds

    def __init__(self, redis_url: str, maxlen: int = 20):
        import redis.asyncio as aioredis
        self._redis: Any = aioredis.from_url(redis_url, decode_responses=True)
        self._maxlen = maxlen

    def _key(self, chat_id: str) -> str:
        return f"aegis:memory:{chat_id}"

    async def get(self, chat_id: str) -> List[Dict[str, str]]:
        items = await self._redis.lrange(self._key(chat_id), 0, -1)
        return [json.loads(item) for item in items]

    async def append(self, chat_id: str, message: Dict[str, str]) -> None:
        key = self._key(chat_id)
        await self._redis.rpush(key, json.dumps(message, ensure_ascii=False))
        await self._redis.ltrim(key, -self._maxlen, -1)
        await self._redis.expire(key, self._TTL)

    async def clear(self, chat_id: str) -> None:
        await self._redis.delete(self._key(chat_id))


# ---------------------------------------------------------------------------
# MemoryManager
# ---------------------------------------------------------------------------

class MemoryManager:
    """
    Decoupled async memory layer keyed by chat_id.
    Pass a RedisStore for persistence, or leave blank for in-process deque.
    """

    def __init__(self, store: MessageStore | None = None, maxlen: int = 20):
        self._store: MessageStore = store or DequeStore(maxlen=maxlen)

    async def get_history(self, chat_id: str) -> List[Dict[str, str]]:
        return await self._store.get(chat_id)

    async def save_message(self, chat_id: str, role: str, content: str) -> None:
        await self._store.append(chat_id, {"role": role, "content": content})

    async def clear_history(self, chat_id: str) -> None:
        await self._store.clear(chat_id)
