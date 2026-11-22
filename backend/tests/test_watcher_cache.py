import sqlite3
from datetime import datetime, timezone

from whatsuggest.watcher import MessageWatcher

NOW = datetime(2026, 11, 22, 10, 6, tzinfo=timezone.utc)


def _watcher(settings, service, clock_box, spawn):
    settings.debounce_seconds = 8
    settings.pregenerate_max_age_seconds = 600
    return MessageWatcher(
        service.db,
        service,
        settings,
        clock=lambda: clock_box[0],
        now=lambda: NOW,
        spawn=spawn,
    )


def test_debounce_burst_generates_once(settings, service, provider, db_path):
    clock = [0.0]
    calls = []
    watcher = _watcher(settings, service, clock, spawn=lambda fn: calls.append(fn))
    watcher.start_watermark()
    _insert(
        db_path,
        "m4",
        "8613800138000@s.whatsapp.net",
        "在吗",
        "2026-11-22 10:05:30.000000000+00:00",
        0,
    )
    _insert(
        db_path,
        "m5",
        "8613800138000@s.whatsapp.net",
        "看到回我",
        "2026-11-22 10:05:40.000000000+00:00",
        0,
    )
    watcher.poll_once()
    assert calls == []
    assert watcher.pending() == {"8613800138000@s.whatsapp.net"}
    clock[0] = 8
    due = watcher.fire_due()
    assert due == ["8613800138000@s.whatsapp.net"]
    calls[0]()
    assert provider.calls == 1
    cached = service.cache.get("8613800138000@s.whatsapp.net", "m5")
    assert cached is not None
    assert cached.suggestions == ["one", "two", "three"]


def test_outgoing_invalidates_and_cancels(settings, service, provider, db_path):
    clock = [0.0]
    watcher = _watcher(settings, service, clock, spawn=lambda fn: fn())
    watcher.start_watermark()
    _insert(
        db_path,
        "m4",
        "8613800138000@s.whatsapp.net",
        "在吗",
        "2026-11-22 10:05:30.000000000+00:00",
        0,
    )
    watcher.poll_once()
    assert watcher.pending()
    service.cache.put("8613800138000@s.whatsapp.net", "妈妈", ["old"], "m3")
    _insert(
        db_path,
        "m6",
        "8613800138000@s.whatsapp.net",
        "马上回",
        "2026-11-22 10:05:50.000000000+00:00",
        1,
    )
    watcher.poll_once()
    assert watcher.pending() == set()
    assert service.cache.get_any("8613800138000@s.whatsapp.net") is None
    assert provider.calls == 0


def test_skips_groups_and_old_rows_and_muted(settings, service, provider, db_path):
    clock = [0.0]
    watcher = _watcher(settings, service, clock, spawn=lambda fn: fn())
    watcher.start_watermark()
    _insert(
        db_path,
        "g2",
        "120363000000000000@g.us",
        "hello group",
        "2026-11-22 10:05:30.000000000+00:00",
        0,
    )
    _insert(
        db_path,
        "old",
        "14155550100@s.whatsapp.net",
        "ancient",
        "2026-11-20 10:05:30.000000000+00:00",
        0,
    )
    _insert(
        db_path,
        "promo",
        "447700900000@s.whatsapp.net",
        "sale",
        "2026-11-22 10:05:30.000000000+00:00",
        0,
    )
    watcher.poll_once()
    clock[0] = 100
    assert watcher.fire_due() == []
    assert provider.calls == 0


def test_cache_hit_skips_second_model_call(service, provider):
    first = service.suggest("妈妈")
    assert first.status == "ready"
    assert first.cached is False
    assert provider.calls == 1
    second = service.suggest("Mom")  # pinned JID on the same rule
    assert second.cached is True
    assert second.suggestions == first.suggestions
    assert provider.calls == 1
    refreshed = service.suggest("妈妈", refresh=True)
    assert refreshed.cached is False
    assert provider.calls == 2


def test_group_skipped_unless_asked(service, provider):
    skipped = service.suggest("Family Group")
    assert skipped.status == "skipped"
    assert skipped.reason == "group"
    assert provider.calls == 0
    allowed = service.suggest("Family Group", include_groups=True)
    assert allowed.status == "ready"
    assert provider.calls == 1
    # A manual group refresh stays visible to the phone's cache poll.
    assert service.cached("Family Group").status == "hit"


def test_muted_and_missing(service, provider):
    muted = service.suggest("Promotions")
    assert muted.status == "muted"
    missing = service.suggest("Nobody Special")
    assert missing.status == "not_found"
    assert provider.calls == 0


def test_cached_lookup_reasons(service, provider, db_path):
    assert service.cached("妈妈").reason == "stale"
    service.suggest("妈妈")
    hit = service.cached("妈妈")
    assert hit.status == "hit"
    assert hit.revision == "m3"
    _insert(
        db_path,
        "m9",
        "8613800138000@s.whatsapp.net",
        "我回了",
        "2026-11-22 10:06:00.000000000+00:00",
        1,
    )
    service.cache.invalidate("8613800138000@s.whatsapp.net")
    miss = service.cached("妈妈")
    assert miss.status == "miss"
    assert miss.reason == "outgoing"
    assert miss.revision == "m9"


def _insert(path, mid, jid, content, timestamp, is_from_me):
    conn = sqlite3.connect(path)
    conn.execute(
        """
        INSERT INTO messages (
            id, chat_jid, sender, content, timestamp, is_from_me,
            media_type, filename, url, media_key, file_sha256, file_enc_sha256, file_length
        ) VALUES (?, ?, ?, ?, ?, ?, '', '', '', NULL, NULL, NULL, NULL)
        """,
        (mid, jid, "sender", content, timestamp, is_from_me),
    )
    conn.commit()
    conn.close()
