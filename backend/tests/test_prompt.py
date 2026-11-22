from datetime import datetime, timezone

from whatsuggest.db import MessageDatabase
from whatsuggest.prompt import build_prompt, format_gap


def test_gap_words():
    now = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)
    assert format_gap(datetime(2026, 11, 22, 11, 56, tzinfo=timezone.utc), now) == "4 minutes"
    assert format_gap(datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc), now) == "2 hours"
    assert format_gap(None, now) == "unknown"


def test_prompt_includes_persona_rule_gap_and_last_speaker(settings, db_path):
    db = MessageDatabase(str(db_path))
    chat = next(c for c in db.list_chats() if c.name == "妈妈")
    messages = db.messages_for(chat.jid, 30)
    rule = settings.rule_for("妈妈", chat.name, chat.jid)
    text = build_prompt(
        settings,
        chat,
        messages,
        phone_name="妈妈",
        rule=rule,
        now=datetime(2026, 11, 22, 10, 9, tzinfo=timezone.utc),
    )
    assert "Warm and brief" in text
    assert "As an AI" in text
    assert "亲一点" in text
    assert "Chinese (zh)" in text
    assert "好的妈，我知道了" in text
    assert "the contact spoke last" in text
    assert "4 minutes" in text
    assert "吃饭了吗" in text
    assert "早点回来" in text
    assert "[2026-11-22 10:02] Florence: 还没" in text
    assert "never send" in text.lower()
    assert "Do not translate" not in text  # language rule overrides the default


def test_prompt_uses_conversation_language_without_a_rule(settings, db_path):
    db = MessageDatabase(str(db_path))
    chat = next(c for c in db.list_chats() if c.name == "Alice Smith")
    # Drop her English rule so this case exercises the default.
    settings.contacts = [rule for rule in settings.contacts if "Alice Smith" not in rule.names]
    messages = db.messages_for(chat.jid, 30)
    text = build_prompt(
        settings,
        chat,
        messages,
        now=datetime(2026, 11, 22, 11, 0, tzinfo=timezone.utc),
    )
    assert "language of the conversation" in text
    assert "Can you send the invoice today?" in text
    assert "the contact spoke last" in text


def test_prompt_notes_when_she_spoke_last(settings, db_path):
    db = MessageDatabase(str(db_path))
    chat = next(c for c in db.list_chats() if c.name == "妈妈")
    messages = db.messages_for(chat.jid, 30)[:-1]
    text = build_prompt(settings, chat, messages, rule=settings.contacts[0])
    assert "she spoke last" in text
    assert "follow-up" in text
