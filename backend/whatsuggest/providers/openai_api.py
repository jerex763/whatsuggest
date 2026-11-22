"""OpenAI API provider, selected with `llm.provider: openai`.

Uses Chat Completions structured outputs (`response_format: json_schema`).
The API key is read from the environment variable named in config
(`OPENAI_API_KEY` by default) and is never written to the config file.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from whatsuggest.config import OpenAISettings
from whatsuggest.providers.codex_cli import load_schema


class OpenAIAPIError(RuntimeError):
    pass


class OpenAIAPIProvider:
    def __init__(self, settings: OpenAISettings, transport=None) -> None:
        self.settings = settings
        self._transport = transport or _urllib_transport

    def build_body(self, prompt: str) -> dict:
        schema = load_schema()
        return {
            "model": self.settings.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Reply with JSON only. Do not call tools. Do not send messages. "
                        "The suggestions are drafts for a person to edit and send herself."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "reply_suggestions",
                    "strict": True,
                    "schema": schema,
                },
            },
        }

    def generate(self, prompt: str) -> str:
        key = os.environ.get(self.settings.api_key_env, "").strip()
        if not key:
            raise OpenAIAPIError(
                f"{self.settings.api_key_env} is not set. The openai provider needs an API key."
            )
        body = self.build_body(prompt)
        url = f"{self.settings.base_url}/chat/completions"
        raw = self._transport(url, body, key, self.settings.timeout_seconds)
        try:
            payload = json.loads(raw)
            return payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise OpenAIAPIError(f"unexpected OpenAI response: {raw[:300]}") from exc


def _urllib_transport(url: str, body: dict, api_key: str, timeout: int) -> str:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise OpenAIAPIError(f"OpenAI HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise OpenAIAPIError(f"OpenAI request failed: {exc.reason}") from exc
