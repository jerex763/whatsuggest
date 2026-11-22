"""Build one prompt from history, persona, and the contact rule."""

from __future__ import annotations

from datetime import datetime, timezone

from whatsuggest.config import ContactRule, Settings
from whatsuggest.db import Chat, Message

_LANG_NAMES = {
    "zh": "Chinese",
    "zh-cn": "Simplified Chinese",
    "zh-hans": "Simplified Chinese",
    "zh-tw": "Traditional Chinese",
    "zh-hk": "Traditional Chinese",
    "yue": "Cantonese",
    "en": "English",
    "en-us": "English",
    "en-gb": "English",
}


def build_prompt(
    settings: Settings,
    chat: Chat,
    messages: list[Message],
    *,
    phone_name: str = "",
    rule: ContactRule | None = None,
    now: datetime | None = None,
) -> str:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    last = messages[-1] if messages else None
    lines: list[str] = [
        "You draft WhatsApp replies for "
        f"{settings.persona_name}. You only suggest text. You never send messages, "
        "never claim a message was sent, and never use tools.",
        "",
        "Return JSON only, matching the schema: "
        '{"suggestions": ["...", "...", "..."]} with exactly three strings.',
        "Each suggestion is one message she could send, in her voice, usually one or two short sentences.",
        "The three suggestions should be meaningfully different, not paraphrases of each other.",
        "No numbering, no quotes around the message, no explanation.",
        "",
        f"Her name in the transcript: {settings.persona_name}",
    ]
    if settings.persona_voice:
        lines.extend(["", "How she writes:", settings.persona_voice.strip()])
    never = list(settings.persona_never_say)
    if rule is not None:
        never.extend(rule.never_say)
    if never:
        lines.extend(["", "Never say any of these:"])
        lines.extend(f"- {item}" for item in never)
    if rule is not None and (rule.tone or rule.language or rule.examples):
        label = ", ".join(rule.names) or chat.name
        lines.extend(["", f"Rules for this contact ({label}):"])
        if rule.tone:
            lines.append(f"Tone: {rule.tone}")
        if rule.language:
            lines.append(f"Language: write every suggestion in {_language_label(rule.language)}.")
        if rule.examples:
            lines.append("Examples of replies that sound like her with this contact:")
            lines.extend(f"- {example}" for example in rule.examples)
    if rule is None or not rule.language:
        lines.extend(
            [
                "",
                "Write every suggestion in the language of the conversation. "
                "If both people mix languages, use the language of the contact's latest message. "
                "Do not translate unless a contact rule above names a language.",
            ]
        )
    shown = phone_name.strip()
    lines.extend(["", f"Chat name in the message database: {chat.name or chat.jid}"])
    if shown and _norm(shown) != _norm(chat.name):
        lines.append(f"Name shown in WhatsApp on her phone: {shown}")
    lines.append(f"Chat id: {chat.jid}")
    lines.append("This is a group chat." if chat.is_group else "This is a one-to-one chat.")
    if last is None:
        lines.append("There are no stored messages yet.")
    else:
        speaker = settings.persona_name if last.is_from_me else (chat.name or "the contact")
        side = "she spoke last" if last.is_from_me else "the contact spoke last"
        lines.append(f"Who spoke last: {speaker} ({side}).")
        lines.append(f"Time since that message: {format_gap(last.timestamp, moment)}.")
        if last.is_from_me:
            lines.append(
                "She already sent the last message. Only suggest a follow-up if one would feel natural; "
                "otherwise suggest short replies she might send if they have not answered yet."
            )
        else:
            lines.append("Suggest replies to the contact's latest message.")
    lines.extend(["", "Recent messages, oldest first:"])
    if not messages:
        lines.append("(none)")
    else:
        for message in messages:
            lines.append(_format_message(settings.persona_name, chat, message))
    return "\n".join(lines).strip() + "\n"


def format_gap(when: datetime | None, now: datetime) -> str:
    if when is None:
        return "unknown"
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    seconds = int((now - when).total_seconds())
    if seconds < 0:
        seconds = 0
    if seconds < 60:
        return "under a minute"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute" if minutes == 1 else f"{minutes} minutes"
    hours = minutes // 60
    if hours < 48:
        return f"{hours} hour" if hours == 1 else f"{hours} hours"
    days = hours // 24
    return f"{days} day" if days == 1 else f"{days} days"


def _format_message(persona: str, chat: Chat, message: Message) -> str:
    who = persona if message.is_from_me else (chat.name or message.sender or "contact")
    stamp = message.timestamp.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M") if message.timestamp else "?"
    body = (message.content or "").strip()
    if not body:
        kind = message.media_type or "media"
        label = message.filename or kind
        body = f"[{label}]"
    body = " ".join(body.split())
    return f"[{stamp}] {who}: {body}"


def _language_label(code: str) -> str:
    key = code.strip().lower()
    name = _LANG_NAMES.get(key)
    if name and name.lower() != key:
        return f"{name} ({code.strip()})"
    return code.strip()


def _norm(value: str) -> str:
    return " ".join((value or "").casefold().split())
