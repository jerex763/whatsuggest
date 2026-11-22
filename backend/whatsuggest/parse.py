"""Turn model text into exactly three suggestion strings."""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"```(?:json)?\s*", re.IGNORECASE)
_MAX_LEN = 500


class SuggestionParseError(ValueError):
    """The model output was not a usable suggestion payload."""


def extract_suggestions(text: str) -> list[str]:
    """Parse a JSON object or array, ignoring markdown fences and extra prose.

    More than three suggestions are truncated. Empty strings are dropped.
    At least one non-empty suggestion is required.
    """
    if text is None or not str(text).strip():
        raise SuggestionParseError("empty model output")
    data = _load_json(str(text))
    raw = _suggestion_list(data)
    cleaned: list[str] = []
    for item in raw:
        text_item = _as_text(item)
        if not text_item:
            continue
        if len(text_item) > _MAX_LEN:
            text_item = text_item[:_MAX_LEN].rstrip()
        cleaned.append(text_item)
        if len(cleaned) == 3:
            break
    if not cleaned:
        raise SuggestionParseError("no suggestions in model output")
    return cleaned


def _load_json(text: str) -> Any:
    stripped = _FENCE.sub("", text).strip().rstrip("`").strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    start_obj = stripped.find("{")
    start_arr = stripped.find("[")
    candidates = [i for i in (start_obj, start_arr) if i >= 0]
    if not candidates:
        raise SuggestionParseError("no JSON in model output")
    start = min(candidates)
    snippet = stripped[start:]
    decoder = json.JSONDecoder()
    try:
        data, _ = decoder.raw_decode(snippet)
    except json.JSONDecodeError as exc:
        raise SuggestionParseError(f"invalid JSON: {exc}") from exc
    return data


def _suggestion_list(data: Any) -> list[Any]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "suggestions" in data:
        value = data["suggestions"]
        if isinstance(value, list):
            return value
    raise SuggestionParseError(f"unexpected JSON shape: {type(data).__name__}")


def _as_text(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, bool) or item is None:
        return ""
    if isinstance(item, (int, float)):
        return str(item)
    return ""
