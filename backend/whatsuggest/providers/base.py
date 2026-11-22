"""LLM provider interface.

`generate` returns the model's final message as text. Callers parse that
text into suggestions. Providers must not be given tools that send messages.
"""

from __future__ import annotations

from typing import Protocol


class LLMProvider(Protocol):
    def generate(self, prompt: str) -> str:
        """Return the raw final message. Expected to be JSON text."""
