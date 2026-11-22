"""Read-only access to the whatsapp-mcp bridge message database.

Schema verified from lharries/whatsapp-mcp `whatsapp-bridge/main.go`
(`NewMessageStore`). The bridge creates `store/messages.db` with:

    chats(jid TEXT PRIMARY KEY, name TEXT, last_message_time TIMESTAMP)
    messages(
        id TEXT, chat_jid TEXT, sender TEXT, content TEXT, timestamp TIMESTAMP,
        is_from_me BOOLEAN, media_type TEXT, filename TEXT, url TEXT,
        media_key BLOB, file_sha256 BLOB, file_enc_sha256 BLOB, file_length INTEGER,
        PRIMARY KEY (id, chat_jid),
        FOREIGN KEY (chat_jid) REFERENCES chats(jid)
    )

Individual JIDs look like ``123@s.whatsapp.net``. Group JIDs end with ``@g.us``.
Go's sqlite driver stores ``time.Time`` as text, often with a nanosecond
fraction and a numeric timezone offset.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

# Kept in sync with the bridge CREATE TABLE so tests can build a fixture.
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS chats (
    jid TEXT PRIMARY KEY,
    name TEXT,
    last_message_time TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT,
    chat_jid TEXT,
    sender TEXT,
    content TEXT,
    timestamp TIMESTAMP,
    is_from_me BOOLEAN,
    media_type TEXT,
    filename TEXT,
    url TEXT,
    media_key BLOB,
    file_sha256 BLOB,
    file_enc_sha256 BLOB,
    file_length INTEGER,
    PRIMARY KEY (id, chat_jid),
    FOREIGN KEY (chat_jid) REFERENCES chats(jid)
);
"""

_FRACTION = re.compile(r"(\.\d{6})\d+")
_TIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%d %H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M",
)


@dataclass(frozen=True)
class Chat:
    jid: str
    name: str
    last_message_time: datetime | None

    @property
    def is_group(self) -> bool:
        return self.jid.endswith("@g.us")


@dataclass(frozen=True)
class Message:
    rowid: int
    id: str
    chat_jid: str
    sender: str
    content: str
    timestamp: datetime | None
    is_from_me: bool
    media_type: str = ""
    filename: str = ""


@dataclass(frozen=True)
class ResolvedChat:
    chat: Chat
    score: float
    reason: str


class MessageDatabase:
    def __init__(self, path: str) -> None:
        self.path = path

    def ping(self) -> bool:
        try:
            with self.connect() as conn:
                conn.execute("SELECT 1")
            return True
        except (sqlite3.Error, OSError):
            return False

    def connect(self) -> sqlite3.Connection:
        uri = Path(self.path).resolve().as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    def max_rowid(self) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT COALESCE(MAX(rowid), 0) AS max_id FROM messages").fetchone()
        return int(row["max_id"] or 0)

    def list_chats(self) -> list[Chat]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT jid, name, last_message_time FROM chats"
            ).fetchall()
        return [
            Chat(
                jid=str(row["jid"] or ""),
                name=str(row["name"] or ""),
                last_message_time=parse_timestamp(row["last_message_time"]),
            )
            for row in rows
            if row["jid"]
        ]

    def messages_for(self, jid: str, limit: int) -> list[Message]:
        """Recent messages, oldest first."""
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT rowid, id, chat_jid, sender, content, timestamp,
                       is_from_me, media_type, filename
                FROM messages
                WHERE chat_jid = ?
                ORDER BY timestamp DESC, rowid DESC
                LIMIT ?
                """,
                (jid, limit),
            ).fetchall()
        return [_message(row) for row in reversed(rows)]

    def latest_message(self, jid: str) -> Message | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT rowid, id, chat_jid, sender, content, timestamp,
                       is_from_me, media_type, filename
                FROM messages
                WHERE chat_jid = ?
                ORDER BY timestamp DESC, rowid DESC
                LIMIT 1
                """,
                (jid,),
            ).fetchone()
        return _message(row) if row else None

    def messages_after(self, rowid: int) -> list[Message]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT rowid, id, chat_jid, sender, content, timestamp,
                       is_from_me, media_type, filename
                FROM messages
                WHERE rowid > ?
                ORDER BY rowid ASC
                """,
                (rowid,),
            ).fetchall()
        return [_message(row) for row in rows]


def parse_timestamp(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+0000"
    text = _FRACTION.sub(r"\1", text)
    # %z wants +0000 or +00:00. Both work on Python 3.12 for colon form
    # when the rest of the string matches. Normalize a trailing offset colon.
    for fmt in _TIME_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    return None


def parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value) != 0
    text = str(value or "").strip().lower()
    return text in {"1", "true", "t", "yes"}


def resolve_chat(
    chats: list[Chat],
    name: str,
    jid: str | None = None,
    pinned_jids: list[str] | None = None,
    threshold: float = 0.84,
) -> ResolvedChat | None:
    """Pick the chat for a phone-side display name.

    A known JID wins. Otherwise an exact normalized name wins. Short names
    (three characters or fewer, typical for Chinese given names) only match
    exactly, so fuzzy matching cannot pair the wrong relative.
    """
    by_jid = {chat.jid: chat for chat in chats if chat.jid}
    if jid and jid in by_jid:
        return ResolvedChat(by_jid[jid], 1.0, "jid")
    for pinned in pinned_jids or []:
        if pinned in by_jid:
            return ResolvedChat(by_jid[pinned], 1.0, "pinned-jid")

    query = _norm(name)
    if not query:
        return None

    ranked: list[tuple[float, Chat]] = []
    for chat in chats:
        score = _name_score(query, _norm(chat.name))
        if score > 0:
            ranked.append((score, chat))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (item[0], _recency(item[1])), reverse=True)
    best_score, best = ranked[0]
    if best_score < threshold and best_score < 1.0:
        return None
    reason = "exact" if best_score >= 1.0 else "fuzzy"
    return ResolvedChat(best, best_score, reason)


def search_chats(chats: list[Chat], query: str, limit: int = 8) -> list[ResolvedChat]:
    needle = _norm(query)
    if not needle:
        ordered = sorted(chats, key=_recency, reverse=True)
        return [ResolvedChat(chat, 0.0, "recent") for chat in ordered[:limit]]
    ranked: list[ResolvedChat] = []
    for chat in chats:
        score = _name_score(needle, _norm(chat.name))
        if chat.jid.lower().startswith(needle) or needle in chat.jid.lower():
            score = max(score, 0.9)
        if score >= 0.5:
            ranked.append(ResolvedChat(chat, score, "search"))
    ranked.sort(key=lambda item: (item.score, _recency(item.chat)), reverse=True)
    return ranked[:limit]


def _message(row: sqlite3.Row) -> Message:
    return Message(
        rowid=int(row["rowid"]),
        id=str(row["id"] or ""),
        chat_jid=str(row["chat_jid"] or ""),
        sender=str(row["sender"] or ""),
        content=str(row["content"] or ""),
        timestamp=parse_timestamp(row["timestamp"]),
        is_from_me=parse_bool(row["is_from_me"]),
        media_type=str(row["media_type"] or ""),
        filename=str(row["filename"] or ""),
    )


def _norm(value: str) -> str:
    return " ".join((value or "").casefold().split())


def _name_score(query: str, candidate: str) -> float:
    if not query or not candidate:
        return 0.0
    if query == candidate:
        return 1.0
    q_tokens = query.split()
    c_tokens = candidate.split()
    if len(q_tokens) == 1 and q_tokens[0] in c_tokens and len(q_tokens[0]) >= 3:
        return 0.93
    if len(c_tokens) == 1 and c_tokens[0] in q_tokens and len(c_tokens[0]) >= 3:
        return 0.93
    if len(query) <= 3 or len(candidate) <= 3:
        return 0.0
    return SequenceMatcher(None, query, candidate).ratio()


def _recency(chat: Chat) -> float:
    if chat.last_message_time is None:
        return 0.0
    return chat.last_message_time.timestamp()
