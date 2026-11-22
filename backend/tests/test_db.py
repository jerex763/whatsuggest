from datetime import datetime, timezone

from whatsuggest.db import MessageDatabase, parse_timestamp, resolve_chat, search_chats


def test_parse_go_sqlite_timestamp():
    parsed = parse_timestamp("2026-11-22 10:05:00.000000000+00:00")
    assert parsed == datetime(2026, 11, 22, 10, 5, tzinfo=timezone.utc)


def test_parse_naive_and_zulu():
    naive = parse_timestamp("2026-11-22 10:05:00")
    assert naive is not None and naive.tzinfo == timezone.utc
    zulu = parse_timestamp("2026-11-22T10:05:00Z")
    assert zulu == datetime(2026, 11, 22, 10, 5, tzinfo=timezone.utc)


def test_reads_fixture_history_oldest_first(db_path):
    db = MessageDatabase(str(db_path))
    assert db.ping()
    messages = db.messages_for("8613800138000@s.whatsapp.net", 30)
    assert [m.id for m in messages] == ["m1", "m2", "m3"]
    assert messages[0].content == "吃饭了吗"
    assert messages[0].is_from_me is False
    assert messages[1].is_from_me is True
    assert messages[-1].timestamp == datetime(2026, 11, 22, 10, 5, tzinfo=timezone.utc)


def test_rowid_watermark(db_path):
    db = MessageDatabase(str(db_path))
    watermark = db.max_rowid()
    assert watermark >= 5
    assert db.messages_after(watermark) == []
    newest = db.messages_after(watermark - 1)
    assert len(newest) == 1
    assert newest[0].rowid == watermark


def test_resolve_exact_chinese_and_pinned_jid(db_path):
    db = MessageDatabase(str(db_path))
    chats = db.list_chats()
    mom = resolve_chat(chats, "妈妈")
    assert mom is not None
    assert mom.chat.jid.endswith("@s.whatsapp.net")
    assert mom.reason == "exact"
    pinned = resolve_chat(chats, "老妈", pinned_jids=["8613800138000@s.whatsapp.net"])
    assert pinned is not None and pinned.reason == "pinned-jid"
    explicit = resolve_chat(chats, "whatever", jid="14155550100@s.whatsapp.net")
    assert explicit is not None and explicit.chat.name == "Alice Smith"


def test_fuzzy_does_not_confuse_short_names(db_path):
    db = MessageDatabase(str(db_path))
    chats = db.list_chats()
    assert resolve_chat(chats, "妈") is None
    alice = resolve_chat(chats, "Alice")
    assert alice is not None
    assert alice.chat.name == "Alice Smith"
    assert alice.reason == "fuzzy"


def test_group_flag_and_search(db_path):
    db = MessageDatabase(str(db_path))
    chats = db.list_chats()
    group = next(chat for chat in chats if chat.name == "Family Group")
    assert group.is_group
    found = search_chats(chats, "family")
    assert found[0].chat.jid.endswith("@g.us")
