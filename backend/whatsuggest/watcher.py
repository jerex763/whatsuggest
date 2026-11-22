"""Watch messages.db for new incoming rows and pre-generate suggestions.

The bridge does not emit a hook this process can subscribe to. Polling
`rowid` is enough: SQLite assigns a new rowid for each inserted message,
and the bridge writes one row per stored message.

Bursts from the same chat share one timer. An outgoing message (she replied)
drops the cached draft and cancels the pending generation. Group chats are
skipped when configured. History-sync rows older than
`pregenerate_max_age_seconds` do not start a generation, so a backlog sync
cannot stampede the model.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from whatsuggest.config import Settings
from whatsuggest.db import Message, MessageDatabase
from whatsuggest.service import SuggestionService

log = logging.getLogger(__name__)


class MessageWatcher:
    def __init__(
        self,
        database: MessageDatabase,
        service: SuggestionService,
        settings: Settings,
        *,
        clock=None,
        now=None,
        spawn=None,
    ) -> None:
        self.db = database
        self.service = service
        self.settings = settings
        self._clock = clock or _monotonic
        self._now = now or _utc_now
        self._spawn = spawn or _spawn_thread
        self._watermark: int | None = None
        self._deadlines: dict[str, float] = {}
        self._stop = threading.Event()

    def start_watermark(self) -> int:
        self._watermark = self.db.max_rowid()
        log.info("watcher watermark rowid=%s", self._watermark)
        return self._watermark

    def poll_once(self) -> None:
        if self._watermark is None:
            self.start_watermark()
        assert self._watermark is not None
        rows = self.db.messages_after(self._watermark)
        for row in rows:
            if row.rowid > self._watermark:
                self._watermark = row.rowid
            self._on_message(row)
        self.fire_due()

    def fire_due(self) -> list[str]:
        now = self._clock()
        due = [jid for jid, deadline in self._deadlines.items() if deadline <= now]
        for jid in due:
            self._deadlines.pop(jid, None)
            self._spawn(lambda jid=jid: self._safe_pregenerate(jid))
        return due

    def pending(self) -> set[str]:
        return set(self._deadlines)

    def run(self) -> None:
        self.start_watermark()
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception:
                log.exception("watcher poll failed")
            self._stop.wait(self.settings.poll_interval_seconds)

    def stop(self) -> None:
        self._stop.set()

    def _on_message(self, row: Message) -> None:
        jid = row.chat_jid
        if not jid:
            return
        if self._is_muted(jid):
            self._deadlines.pop(jid, None)
            self.service.cache.invalidate(jid)
            return
        if jid.endswith("@g.us") and self.settings.skip_groups:
            return
        if row.is_from_me:
            self.service.cache.invalidate(jid)
            self._deadlines.pop(jid, None)
            log.info("outgoing message in %s, cache cleared", jid)
            return
        if not self._is_recent(row):
            log.info("skipping old incoming rowid=%s jid=%s", row.rowid, jid)
            return
        self._deadlines[jid] = self._clock() + self.settings.debounce_seconds
        log.info("scheduled suggestions for %s in %.1fs", jid, self.settings.debounce_seconds)

    def _is_muted(self, jid: str) -> bool:
        if self.settings.is_muted("", jid):
            return True
        if not any(entry.name for entry in self.settings.muted):
            return False
        name = ""
        try:
            for chat in self.db.list_chats():
                if chat.jid == jid:
                    name = chat.name
                    break
        except Exception:
            log.exception("mute lookup failed for %s", jid)
            return False
        return self.settings.is_muted(name, jid)

    def _is_recent(self, row: Message) -> bool:
        if row.timestamp is None:
            return False
        age = (self._now() - row.timestamp.astimezone(timezone.utc)).total_seconds()
        return age <= self.settings.pregenerate_max_age_seconds

    def _safe_pregenerate(self, jid: str) -> None:
        try:
            result = self.service.pregenerate(jid)
            log.info("pregenerate %s -> %s cached=%s", jid, result.status, result.cached)
        except Exception:
            log.exception("pregenerate failed for %s", jid)


def _monotonic() -> float:
    import time

    return time.monotonic()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _spawn_thread(fn) -> None:
    threading.Thread(target=fn, name="whatsuggest-pregenerate", daemon=True).start()
