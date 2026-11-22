import json

import pytest

from whatsuggest.parse import SuggestionParseError, extract_suggestions
from whatsuggest.providers.codex_cli import load_schema


def test_object_payload():
    assert extract_suggestions('{"suggestions":["a","b","c"]}') == ["a", "b", "c"]


def test_array_payload_and_markdown_fence():
    text = 'Here you go:\n```json\n["hi", "ok", "later"]\n```\n'
    assert extract_suggestions(text) == ["hi", "ok", "later"]


def test_extra_prose_around_object():
    text = 'Sure.\n{"suggestions":["one","two","three","four"]}\nDone.'
    assert extract_suggestions(text) == ["one", "two", "three"]


def test_drops_blanks_and_coerces_scalars():
    assert extract_suggestions('{"suggestions":["  yes  ", "", 2, null]}') == ["yes", "2"]


def test_truncates_very_long_suggestion():
    huge = "x" * 800
    got = extract_suggestions(json.dumps({"suggestions": [huge, "b", "c"]}))
    assert len(got[0]) == 500
    assert got[1:] == ["b", "c"]


def test_empty_and_garbage():
    with pytest.raises(SuggestionParseError):
        extract_suggestions("   ")
    with pytest.raises(SuggestionParseError):
        extract_suggestions("no json here")
    with pytest.raises(SuggestionParseError):
        extract_suggestions('{"suggestions":["  ", ""]}')


def test_schema_is_strict():
    schema = load_schema()
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["suggestions"]
    assert "suggestions" in schema["properties"]
    assert schema["properties"]["suggestions"]["items"]["type"] == "string"
