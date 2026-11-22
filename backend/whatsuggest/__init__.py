"""WhatSuggest PC backend.

Reads the whatsapp-mcp bridge SQLite database and asks Codex (or a
swap-in OpenAI provider) for three reply drafts. Nothing in this package
sends a WhatsApp message.
"""

__version__ = "2.0.0"
