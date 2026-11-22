def test_auth_required(client):
    denied = client.post("/suggest", json={"contact": "妈妈"})
    assert denied.status_code == 401
    health = client.get("/health", headers={"X-API-Key": "test-key"})
    assert health.status_code == 200
    assert health.get_json()["provider"] == "codex"


def test_suggest_and_cache_routes(client, provider):
    created = client.post(
        "/suggest",
        json={"contact": "妈妈"},
        headers={"X-API-Key": "test-key"},
    )
    body = created.get_json()
    assert created.status_code == 200
    assert body["suggestions"] == ["one", "two", "three"]
    assert body["cached"] is False
    assert provider.calls == 1

    again = client.post(
        "/suggest",
        json={"contact": "妈妈"},
        headers={"X-API-Key": "test-key"},
    )
    assert again.get_json()["cached"] is True
    assert provider.calls == 1

    cached = client.get(
        "/suggest/cached",
        query_string={"contact": "妈妈"},
        headers={"X-API-Key": "test-key"},
    )
    assert cached.get_json()["status"] == "hit"


def test_no_send_route(client):
    rules = {rule.rule for rule in client.application.url_map.iter_rules()}
    assert not any("send" in rule for rule in rules)


def test_chat_search_has_no_message_body(client):
    found = client.get("/chats", query_string={"q": "Alice"}, headers={"X-API-Key": "test-key"})
    payload = found.get_json()
    assert payload["matches"][0]["name"] == "Alice Smith"
    assert "content" not in payload["matches"][0]
    dumped = str(payload)
    assert "invoice" not in dumped


def test_example_config_loads():
    from pathlib import Path

    from whatsuggest.config import load_settings

    example = Path(__file__).resolve().parents[1] / "config.example.yaml"
    settings = load_settings(example, api_key="local-test")
    assert settings.provider == "codex"
    assert settings.skip_groups is True
    assert settings.persona_name == "Florence"
    assert settings.codex.use_api_key is False
    assert settings.codex.sandbox == "read-only"
    assert any("妈妈" in rule.names for rule in settings.contacts)
    assert settings.api_key == "local-test"
