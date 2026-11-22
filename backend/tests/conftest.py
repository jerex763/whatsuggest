"""Shared fixtures: a whatsapp-mcp-shaped SQLite file and a fake model."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from whatsuggest.cache import SuggestionCache
from whatsuggest.config import ContactRule, MuteEntry, Settings
from whatsuggest.db import SCHEMA_SQL, MessageDatabase
from whatsuggest.server import create_app
from whatsuggest.service import SuggestionService


class FakeProvider:
    def __init__(self, payload: str = '{"suggestions":["one","two","three"]}') -> None:
        self.payload = payload
        self.prompts: list[str] = []
        self.calls = 0

    def generate(self, prompt: str) -> str:
        self.calls += 1
        self.prompts.append(prompt)
        return self.payload


def write_db(path: Path, chats: list[tuple], messages: list[tuple]) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_SQL)
    conn.executemany(
        "INSERT INTO chats (jid, name, last_message_time) VALUES (?, ?, ?)",
        chats,
    )
    conn.executemany(
        """
        INSERT INTO messages (
            id, chat_jid, sender, content, timestamp, is_from_me,
            media_type, filename, url, media_key, file_sha256, file_enc_sha256, file_length
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', NULL, NULL, NULL, NULL)
        """,
        messages,
    )
    conn.commit()
    conn.close()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "messages.db"
    write_db(
        path,
        chats=[
            ("8613800138000@s.whatsapp.net", "妈妈", "2026-11-22 10:05:00.000000000+00:00"),
            ("14155550100@s.whatsapp.net", "Alice Smith", "2026-11-22 09:00:00.000000000+00:00"),
            ("120363000000000000@g.us", "Family Group", "2026-11-22 08:00:00.000000000+00:00"),
            ("447700900000@s.whatsapp.net", "Promotions", "2026-11-21 08:00:00.000000000+00:00"),
        ],
        messages=[
            (
                "m1",
                "8613800138000@s.whatsapp.net",
                "8613800138000",
                "吃饭了吗",
                "2026-11-22 10:00:00.000000000+00:00",
                0,
                "",
                "",
            ),
            (
                "m2",
                "8613800138000@s.whatsapp.net",
                "me",
                "还没",
                "2026-11-22 10:02:00.000000000+00:00",
                1,
                "",
                "",
            ),
            (
                "m3",
                "8613800138000@s.whatsapp.net",
                "8613800138000",
                "早点回来",
                "2026-11-22 10:05:00.000000000+00:00",
                0,
                "",
                "",
            ),
            (
                "a1",
                "14155550100@s.whatsapp.net",
                "14155550100",
                "Can you send the invoice today?",
                "2026-11-22 09:00:00.000000000+00:00",
                0,
                "",
                "",
            ),
            (
                "g1",
                "120363000000000000@g.us",
                "8613800138000",
                "今晚几点",
                "2026-11-22 08:00:00.000000000+00:00",
                0,
                "",
                "",
            ),
        ],
    )
    return path


@pytest.fixture
def settings(db_path: Path) -> Settings:
    return Settings(
        api_key="test-key",
        database_path=str(db_path),
        persona_name="Florence",
        persona_voice="Warm and brief. Sound like a person texting.",
        persona_never_say=["As an AI", "Certainly"],
        contacts=[
            ContactRule(
                names=["妈妈", "Mom"],
                jids=["8613800138000@s.whatsapp.net"],
                tone="亲一点，短句",
                language="zh",
                never_say=["亲"],
                examples=["好的妈，我知道了"],
            ),
            ContactRule(
                names=["Alice Smith", "Acme"],
                tone="professional and brief",
                language="en",
                examples=["Thanks, I'll send it today."],
            ),
        ],
        muted=[MuteEntry(name="Promotions", jid="447700900000@s.whatsapp.net")],
        debounce_seconds=8,
        pregenerate_max_age_seconds=600,
        skip_groups=True,
        history_limit=30,
    )


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def service(settings: Settings, provider: FakeProvider) -> SuggestionService:
    return SuggestionService(settings, MessageDatabase(settings.database_path), provider, SuggestionCache())


@pytest.fixture
def client(settings: Settings, service: SuggestionService):
    app = create_app(settings, service)
    app.config["TESTING"] = True
    return app.test_client()
