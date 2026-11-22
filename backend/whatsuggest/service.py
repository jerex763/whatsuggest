"""Resolve a chat, reuse a cached draft, or make one model call."""

from __future__ import annotations

import logging
import sqlite3
import threading
from dataclasses import dataclass, field

from whatsuggest.cache import SuggestionCache
from whatsuggest.config import Settings
from whatsuggest.db import MessageDatabase, resolve_chat
from whatsuggest.parse import SuggestionParseError, extract_suggestions
from whatsuggest.prompt import build_prompt

log = logging.getLogger(__name__)


@dataclass
class SuggestionResult:
    status: str
    suggestions: list[str] = field(default_factory=list)
    cached: bool = False
    jid: str | None = None
    contact: str | None = None
    revision: str | None = None
    reason: str | None = None
    http_status: int = 200

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "suggestions": self.suggestions,
            "cached": self.cached,
            "jid": self.jid,
            "contact": self.contact,
            "revision": self.revision,
            "muted": self.status == "muted",
            "skipped": self.reason if self.status == "skipped" else None,
            "reason": self.reason,
            "error": self.reason if self.status in {"error", "not_found", "empty"} else None,
        }


class SuggestionService:
    def __init__(self, settings: Settings, database: MessageDatabase, provider, cache: SuggestionCache | None = None) -> None:
        self.settings = settings
        self.db = database
        self.provider = provider
        self.cache = cache or SuggestionCache()
        self._lock = threading.Lock()
        self._inflight: dict[str, dict] = {}
        self._slots = threading.Semaphore(max(1, settings.max_concurrent))

    def suggest(
        self,
        contact: str,
        *,
        jid: str | None = None,
        refresh: bool = False,
        include_groups: bool = False,
    ) -> SuggestionResult:
        if self.settings.is_muted(contact, jid or ""):
            return SuggestionResult(status="muted", contact=contact or None, jid=jid, reason="muted")
        try:
            chats = self.db.list_chats()
        except (OSError, sqlite3.Error) as exc:
            log.exception("failed to read chats")
            return SuggestionResult(status="error", reason=f"database error: {exc}", http_status=500)
        rule_guess = self.settings.rule_for_phone_name(contact) if contact else None
        pinned = list(rule_guess.jids) if rule_guess else []
        resolved = resolve_chat(chats, contact, jid=jid, pinned_jids=pinned)
        if resolved is None:
            return SuggestionResult(
                status="not_found",
                contact=contact or None,
                reason="contact not found",
                http_status=404,
            )
        chat = resolved.chat
        log.info("resolved %r -> %s (%s, score=%.2f)", contact or jid, chat.jid, resolved.reason, resolved.score)
        if self.settings.is_muted(contact, chat.jid) or self.settings.is_muted(chat.name, chat.jid):
            return SuggestionResult(status="muted", contact=chat.name, jid=chat.jid, reason="muted")
        if chat.is_group and self.settings.skip_groups and not include_groups:
            return SuggestionResult(
                status="skipped",
                contact=chat.name,
                jid=chat.jid,
                reason="group",
            )
        latest = self.db.latest_message(chat.jid)
        if latest is None:
            return SuggestionResult(
                status="empty",
                contact=chat.name,
                jid=chat.jid,
                reason="no messages",
            )
        if not refresh and not latest.is_from_me:
            hit = self.cache.get(chat.jid, latest.id)
            if hit is not None:
                return SuggestionResult(
                    status="ready",
                    suggestions=list(hit.suggestions),
                    cached=True,
                    jid=chat.jid,
                    contact=contact or chat.name,
                    revision=hit.revision,
                )
        return self._generate(chat.jid, contact or chat.name, refresh)

    def cached(self, contact: str, jid: str | None = None) -> SuggestionResult:
        """Lookup only. Does not call the model."""
        if self.settings.is_muted(contact, jid or ""):
            return SuggestionResult(status="muted", contact=contact or None, jid=jid, reason="muted")
        try:
            chats = self.db.list_chats()
        except (OSError, sqlite3.Error) as exc:
            return SuggestionResult(status="error", reason=f"database error: {exc}", http_status=500)
        rule_guess = self.settings.rule_for_phone_name(contact) if contact else None
        pinned = list(rule_guess.jids) if rule_guess else []
        resolved = resolve_chat(chats, contact, jid=jid, pinned_jids=pinned)
        if resolved is None:
            return SuggestionResult(status="not_found", contact=contact or None, reason="contact not found")
        chat = resolved.chat
        if self.settings.is_muted(contact, chat.jid) or self.settings.is_muted(chat.name, chat.jid):
            return SuggestionResult(status="muted", contact=chat.name, jid=chat.jid, reason="muted")
        if chat.is_group and self.settings.skip_groups:
            latest = self.db.latest_message(chat.jid)
            if latest and not latest.is_from_me:
                hit = self.cache.get(chat.jid, latest.id)
                if hit is not None:
                    return SuggestionResult(
                        status="hit",
                        suggestions=list(hit.suggestions),
                        cached=True,
                        jid=chat.jid,
                        contact=contact or chat.name,
                        revision=hit.revision,
                    )
            if latest and latest.is_from_me:
                return SuggestionResult(
                    status="miss",
                    contact=chat.name,
                    jid=chat.jid,
                    revision=latest.id,
                    reason="outgoing",
                )
            return SuggestionResult(status="skipped", contact=chat.name, jid=chat.jid, reason="group")
        latest = self.db.latest_message(chat.jid)
        if latest is None:
            return SuggestionResult(status="miss", contact=chat.name, jid=chat.jid, reason="empty")
        if latest.is_from_me:
            return SuggestionResult(
                status="miss",
                contact=chat.name,
                jid=chat.jid,
                revision=latest.id,
                reason="outgoing",
            )
        hit = self.cache.get(chat.jid, latest.id)
        if hit is None:
            return SuggestionResult(status="miss", contact=chat.name, jid=chat.jid, reason="stale")
        return SuggestionResult(
            status="hit",
            suggestions=list(hit.suggestions),
            cached=True,
            jid=chat.jid,
            contact=contact or chat.name,
            revision=hit.revision,
        )

    def pregenerate(self, jid: str) -> SuggestionResult:
        return self.suggest("", jid=jid, refresh=False, include_groups=False)

    def _generate(self, jid: str, contact: str, refresh: bool) -> SuggestionResult:
        with self._lock:
            holder = self._inflight.get(jid)
            if holder is None:
                holder = {"event": threading.Event(), "result": None}
                self._inflight[jid] = holder
                owner = True
            else:
                owner = False
        if not owner:
            holder["event"].wait(self.settings.codex.timeout_seconds + 5)
            result = holder.get("result")
            if result is None:
                return SuggestionResult(status="error", reason="busy", jid=jid, http_status=429)
            return result
        try:
            if not self._slots.acquire(timeout=20):
                result = SuggestionResult(status="error", reason="busy", jid=jid, contact=contact, http_status=429)
            else:
                try:
                    result = self._generate_unlocked(jid, contact, refresh)
                finally:
                    self._slots.release()
        except Exception as exc:  # noqa: BLE001 - last-resort guard so waiters are released
            log.exception("suggestion generation failed")
            result = SuggestionResult(status="error", reason=str(exc), jid=jid, contact=contact, http_status=500)
        with self._lock:
            holder["result"] = result
            self._inflight.pop(jid, None)
        holder["event"].set()
        return result

    def _generate_unlocked(self, jid: str, contact: str, refresh: bool) -> SuggestionResult:
        chats = self.db.list_chats()
        chat = next((item for item in chats if item.jid == jid), None)
        if chat is None:
            return SuggestionResult(status="not_found", reason="contact not found", jid=jid, http_status=404)
        latest = self.db.latest_message(jid)
        if latest is None:
            return SuggestionResult(status="empty", contact=chat.name, jid=jid, reason="no messages")
        if not refresh and not latest.is_from_me:
            hit = self.cache.get(jid, latest.id)
            if hit is not None:
                return SuggestionResult(
                    status="ready",
                    suggestions=list(hit.suggestions),
                    cached=True,
                    jid=jid,
                    contact=contact or chat.name,
                    revision=hit.revision,
                )
        messages = self.db.messages_for(jid, self.settings.history_limit)
        if not messages:
            return SuggestionResult(status="empty", contact=chat.name, jid=jid, reason="no messages")
        revision = messages[-1].id
        rule = self.settings.rule_for(contact, chat.name, jid)
        prompt = build_prompt(
            self.settings,
            chat,
            messages,
            phone_name=contact if contact != chat.name else "",
            rule=rule,
        )
        try:
            raw = self.provider.generate(prompt)
            suggestions = extract_suggestions(raw)
        except SuggestionParseError as exc:
            return SuggestionResult(
                status="error",
                reason=f"parse error: {exc}",
                jid=jid,
                contact=chat.name,
                http_status=500,
            )
        except Exception as exc:  # provider errors stay as 500/504-ish
            text = str(exc)
            status = 504 if "timed out" in text.lower() else 500
            return SuggestionResult(status="error", reason=text, jid=jid, contact=chat.name, http_status=status)
        current = self.db.latest_message(jid)
        if current is not None and current.id == revision and not current.is_from_me:
            self.cache.put(jid, contact or chat.name, suggestions, revision)
        elif current is not None and current.id == revision and current.is_from_me:
            # Follow-ups after her own message are returned, but not kept for the auto bar.
            self.cache.invalidate(jid)
        else:
            self.cache.invalidate(jid)
        return SuggestionResult(
            status="ready",
            suggestions=suggestions,
            cached=False,
            jid=jid,
            contact=contact or chat.name,
            revision=revision,
        )
