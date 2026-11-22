"""Load the YAML (or JSON) config that describes Florence's voice and chats."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


def normalize_name(value: str) -> str:
    """Casefold, strip, and collapse whitespace. Keeps CJK characters intact."""
    text = (value or "").casefold().strip()
    text = " ".join(text.split())
    return text


@dataclass
class ContactRule:
    names: list[str] = field(default_factory=list)
    jids: list[str] = field(default_factory=list)
    tone: str = ""
    language: str = ""
    never_say: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)

    def matches(self, phone_name: str, chat_name: str, jid: str) -> bool:
        if jid and jid in self.jids:
            return True
        for candidate in (phone_name, chat_name):
            if candidate and _name_listed(candidate, self.names):
                return True
        return False


@dataclass
class MuteEntry:
    name: str = ""
    jid: str = ""


@dataclass
class CodexSettings:
    command: str = ""
    model: str = ""
    timeout_seconds: int = 75
    sandbox: str = "read-only"
    ephemeral: bool = True
    skip_git_repo_check: bool = True
    ignore_user_config: bool = False
    # Drop API-key env vars so `codex exec` uses the existing ChatGPT login.
    use_api_key: bool = False
    extra_args: list[str] = field(default_factory=list)


@dataclass
class OpenAISettings:
    model: str = "gpt-4.1-mini"
    api_key_env: str = "OPENAI_API_KEY"
    base_url: str = "https://api.openai.com/v1"
    timeout_seconds: int = 60


@dataclass
class Settings:
    api_key: str
    host: str = ""
    port: int = 8000
    database_path: str = ""
    provider: str = "codex"
    codex: CodexSettings = field(default_factory=CodexSettings)
    openai: OpenAISettings = field(default_factory=OpenAISettings)
    history_limit: int = 30
    watcher_enabled: bool = True
    poll_interval_seconds: float = 2.0
    debounce_seconds: float = 8.0
    skip_groups: bool = True
    pregenerate_max_age_seconds: int = 600
    max_concurrent: int = 2
    persona_name: str = "Florence"
    persona_voice: str = ""
    persona_never_say: list[str] = field(default_factory=list)
    contacts: list[ContactRule] = field(default_factory=list)
    muted: list[MuteEntry] = field(default_factory=list)

    def rule_for(self, phone_name: str, chat_name: str, jid: str) -> ContactRule | None:
        by_jid = None
        by_name = None
        for rule in self.contacts:
            if jid and jid in rule.jids:
                by_jid = rule
                break
            if by_name is None and rule.matches(phone_name, chat_name, ""):
                by_name = rule
        return by_jid or by_name

    def rule_for_phone_name(self, phone_name: str) -> ContactRule | None:
        for rule in self.contacts:
            if phone_name and _name_listed(phone_name, rule.names):
                return rule
        return None

    def is_muted(self, name: str, jid: str = "") -> bool:
        target = normalize_name(name)
        for entry in self.muted:
            if entry.jid and jid and entry.jid == jid:
                return True
            if entry.name and target and normalize_name(entry.name) == target:
                return True
        return False


def default_config_path() -> Path:
    env = os.environ.get("SUGGEST_CONFIG", "").strip()
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent / "config.yaml"


def load_settings(path: Path | None = None, api_key: str | None = None) -> Settings:
    config_path = path or default_config_path()
    raw = _read_config(config_path)
    key = api_key if api_key is not None else os.environ.get("SUGGEST_API_KEY", "")
    server = raw.get("server") or {}
    database = raw.get("database") or {}
    llm = raw.get("llm") or {}
    history = raw.get("history") or {}
    watcher = raw.get("watcher") or {}
    persona = raw.get("persona") or {}
    return Settings(
        api_key=key or "",
        host=str(server.get("host") or ""),
        port=int(server.get("port") or 8000),
        database_path=str(database.get("path") or ""),
        provider=str(llm.get("provider") or "codex").strip().lower(),
        codex=_codex(llm.get("codex") or {}),
        openai=_openai(llm.get("openai") or {}),
        history_limit=int(history.get("limit") or 30),
        watcher_enabled=bool(watcher.get("enabled", True)),
        poll_interval_seconds=float(watcher.get("poll_interval_seconds") or 2),
        debounce_seconds=float(watcher.get("debounce_seconds") or 8),
        skip_groups=bool(watcher.get("skip_groups", True)),
        pregenerate_max_age_seconds=int(watcher.get("pregenerate_max_age_seconds") or 600),
        max_concurrent=int(raw.get("max_concurrent") or 2),
        persona_name=str(persona.get("name") or "Florence"),
        persona_voice=str(persona.get("voice") or "").strip(),
        persona_never_say=_str_list(persona.get("never_say")),
        contacts=[_contact(item) for item in (raw.get("contacts") or [])],
        muted=[_mute(item) for item in (raw.get("muted") or [])],
    )


def _read_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(
            f"Config not found at {path}. Copy backend/config.example.yaml to config.yaml."
        )
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        data = yaml.safe_load(text)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"Config root must be a mapping, got {type(data).__name__}")
    return data


def _codex(data: dict[str, Any]) -> CodexSettings:
    extra = data.get("extra_args") or []
    return CodexSettings(
        command=str(data.get("command") or ""),
        model=str(data.get("model") or ""),
        timeout_seconds=int(data.get("timeout_seconds") or 75),
        sandbox=str(data.get("sandbox") or "read-only"),
        ephemeral=bool(data.get("ephemeral", True)),
        skip_git_repo_check=bool(data.get("skip_git_repo_check", True)),
        ignore_user_config=bool(data.get("ignore_user_config", False)),
        use_api_key=bool(data.get("use_api_key", False)),
        extra_args=[str(item) for item in extra],
    )


def _openai(data: dict[str, Any]) -> OpenAISettings:
    return OpenAISettings(
        model=str(data.get("model") or "gpt-4.1-mini"),
        api_key_env=str(data.get("api_key_env") or "OPENAI_API_KEY"),
        base_url=str(data.get("base_url") or "https://api.openai.com/v1").rstrip("/"),
        timeout_seconds=int(data.get("timeout_seconds") or 60),
    )


def _contact(item: dict[str, Any]) -> ContactRule:
    match = item.get("match") or {}
    return ContactRule(
        names=_str_list(match.get("names")),
        jids=_str_list(match.get("jids")),
        tone=str(item.get("tone") or "").strip(),
        language=str(item.get("language") or "").strip(),
        never_say=_str_list(item.get("never_say")),
        examples=_str_list(item.get("examples")),
    )


def _mute(item: dict[str, Any] | str) -> MuteEntry:
    if isinstance(item, str):
        return MuteEntry(name=item)
    return MuteEntry(
        name=str(item.get("name") or ""),
        jid=str(item.get("jid") or ""),
    )


def _str_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value if str(item).strip()]


def _name_listed(candidate: str, names: list[str]) -> bool:
    query = normalize_name(candidate)
    if not query:
        return False
    tokens = query.split()
    for name in names:
        listed = normalize_name(name)
        if not listed:
            continue
        if query == listed:
            return True
        if len(listed) >= 3 and listed in tokens:
            return True
    return False
