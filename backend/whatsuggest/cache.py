"""In-memory suggestion cache, keyed by chat JID and source message id."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class CacheEntry:
    jid: str
    contact: str
    suggestions: list[str]
    revision: str
    created_at: float


class SuggestionCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, CacheEntry] = {}

    def get(self, jid: str, revision: str) -> CacheEntry | None:
        with self._lock:
            entry = self._entries.get(jid)
            if entry is None or entry.revision != revision:
                return None
            return entry

    def get_any(self, jid: str) -> CacheEntry | None:
        with self._lock:
            return self._entries.get(jid)

    def put(
        self,
        jid: str,
        contact: str,
        suggestions: list[str],
        revision: str,
        created_at: float | None = None,
    ) -> CacheEntry:
        entry = CacheEntry(
            jid=jid,
            contact=contact,
            suggestions=list(suggestions),
            revision=revision,
            created_at=time.time() if created_at is None else created_at,
        )
        with self._lock:
            self._entries[jid] = entry
        return entry

    def invalidate(self, jid: str) -> None:
        with self._lock:
            self._entries.pop(jid, None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
