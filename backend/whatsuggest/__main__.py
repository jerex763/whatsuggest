"""Start the suggestion server on the Tailscale address."""

from __future__ import annotations

import logging
import subprocess
import sys

from waitress import serve

from whatsuggest.config import default_config_path, load_settings
from whatsuggest.db import MessageDatabase
from whatsuggest.providers.codex_cli import CodexCLIProvider
from whatsuggest.providers.openai_api import OpenAIAPIProvider
from whatsuggest.server import create_app
from whatsuggest.service import SuggestionService
from whatsuggest.watcher import MessageWatcher


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("whatsuggest")
    try:
        settings = load_settings()
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"WhatSuggest config error: {exc}", file=sys.stderr)
        sys.exit(1)
    if not settings.api_key:
        print(
            "SUGGEST_API_KEY is not set. Refusing to start. "
            "Set it in the environment; do not put it in config.yaml.",
            file=sys.stderr,
        )
        sys.exit(1)
    if not settings.database_path:
        print("database.path is empty in the config.", file=sys.stderr)
        sys.exit(1)
    if settings.provider == "codex":
        provider = CodexCLIProvider(settings.codex)
    elif settings.provider == "openai":
        provider = OpenAIAPIProvider(settings.openai)
    else:
        print(f"Unknown llm.provider {settings.provider!r}. Use codex or openai.", file=sys.stderr)
        sys.exit(1)

    database = MessageDatabase(settings.database_path)
    service = SuggestionService(settings, database, provider)
    app = create_app(settings, service)
    if settings.watcher_enabled:
        watcher = MessageWatcher(database, service, settings)
        import threading

        threading.Thread(target=watcher.run, name="whatsuggest-watcher", daemon=True).start()
        log.info("message watcher started (poll %.1fs, debounce %.1fs)", settings.poll_interval_seconds, settings.debounce_seconds)
    host = settings.host.strip() or detect_tailscale_ip()
    log.info("provider=%s db=%s", settings.provider, settings.database_path)
    print(f"Serving on http://{host}:{settings.port}")
    serve(app, host=host, port=settings.port, threads=8)


def detect_tailscale_ip() -> str:
    """Bind to this PC's Tailscale IPv4. Fall back to loopback if Tailscale is down."""
    try:
        result = subprocess.run(
            ["tailscale", "ip", "--4"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        print("tailscale ip failed; binding to 127.0.0.1", file=sys.stderr)
        return "127.0.0.1"
    ip = (result.stdout or "").strip().splitlines()
    if result.returncode == 0 and ip and ip[0]:
        return ip[0].strip()
    print("no Tailscale IPv4; binding to 127.0.0.1", file=sys.stderr)
    return "127.0.0.1"


if __name__ == "__main__":
    main()
