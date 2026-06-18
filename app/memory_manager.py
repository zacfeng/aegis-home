from collections import deque
from typing import List, Dict, Protocol, runtime_checkable


@runtime_checkable
class MessageStore(Protocol):
    """
    Interface contract for backing stores.
    Swap out the deque-based default for Redis (or any other store)
    by implementing this protocol — no changes to MemoryManager needed.
    """

    def get(self, chat_id: str) -> List[Dict[str, str]]: ...
    def append(self, chat_id: str, message: Dict[str, str]) -> None: ...
    def clear(self, chat_id: str) -> None: ...


class DequeStore:
    """In-process deque store. Replace with RedisStore for persistence."""

    def __init__(self, maxlen: int = 20):
        self._maxlen = maxlen
        self._data: Dict[str, deque] = {}

    def _bucket(self, chat_id: str) -> deque:
        if chat_id not in self._data:
            self._data[chat_id] = deque(maxlen=self._maxlen)
        return self._data[chat_id]

    def get(self, chat_id: str) -> List[Dict[str, str]]:
        return list(self._bucket(chat_id))

    def append(self, chat_id: str, message: Dict[str, str]) -> None:
        self._bucket(chat_id).append(message)

    def clear(self, chat_id: str) -> None:
        self._data.pop(chat_id, None)


class MemoryManager:
    """
    Decoupled memory layer keyed by chat_id (LINE group/user ID).

    The backing store is injected so it can be swapped without touching
    this class — pass a RedisStore instance in production.
    """

    def __init__(self, store: MessageStore | None = None, maxlen: int = 20):
        self._store: MessageStore = store or DequeStore(maxlen=maxlen)

    def get_history(self, chat_id: str) -> List[Dict[str, str]]:
        """Return the conversation history for a given chat."""
        return self._store.get(chat_id)

    def save_message(
        self, chat_id: str, role: str, content: str
    ) -> None:
        """Persist a single turn (role: 'user' | 'assistant')."""
        self._store.append(chat_id, {"role": role, "content": content})

    def clear_history(self, chat_id: str) -> None:
        """Wipe the history for a given chat (useful for /reset commands)."""
        self._store.clear(chat_id)
