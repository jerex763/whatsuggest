"""HTTP API. Suggestions only: there is no send endpoint."""

from __future__ import annotations

import hmac
import logging

from flask import Flask, jsonify, request

from whatsuggest import __version__
from whatsuggest.service import SuggestionService

log = logging.getLogger(__name__)


def create_app(settings, service: SuggestionService) -> Flask:
    app = Flask(__name__)
    app.config["JSON_AS_ASCII"] = False

    def authorized() -> bool:
        return _keys_match(request.headers.get("X-API-Key"), settings.api_key)

    @app.errorhandler(404)
    def not_found(_exc):
        return jsonify({"error": "not found"}), 404

    @app.errorhandler(Exception)
    def server_error(exc):
        log.exception("unhandled error")
        return jsonify({"error": "internal server error"}), 500

    @app.get("/health")
    def health():
        if not authorized():
            return jsonify({"error": "unauthorized"}), 401
        db_ok = service.db.ping()
        return jsonify(
            {
                "status": "ok" if db_ok else "degraded",
                "db": db_ok,
                "provider": settings.provider,
                "version": __version__,
            }
        )

    @app.get("/version")
    def version():
        if not authorized():
            return jsonify({"error": "unauthorized"}), 401
        return jsonify({"version": __version__})

    @app.get("/chats")
    def chats():
        if not authorized():
            return jsonify({"error": "unauthorized"}), 401
        from whatsuggest.db import search_chats

        query = (request.args.get("q") or "").strip()
        try:
            found = search_chats(service.db.list_chats(), query)
        except Exception as exc:  # noqa: BLE001 - surface a short DB error, not a stack
            return jsonify({"error": "database error", "detail": str(exc)}), 500
        return jsonify(
            {
                "matches": [
                    {
                        "jid": item.chat.jid,
                        "name": item.chat.name,
                        "score": round(item.score, 3),
                        "is_group": item.chat.is_group,
                        "last_message_time": (
                            item.chat.last_message_time.isoformat()
                            if item.chat.last_message_time
                            else None
                        ),
                    }
                    for item in found
                ]
            }
        )

    @app.get("/suggest/cached")
    def suggest_cached():
        if not authorized():
            return jsonify({"error": "unauthorized"}), 401
        contact = (request.args.get("contact") or "").strip()
        jid = (request.args.get("jid") or "").strip() or None
        if not contact and not jid:
            return jsonify({"error": "invalid contact"}), 400
        if contact and len(contact) > 100:
            return jsonify({"error": "invalid contact"}), 400
        result = service.cached(contact, jid=jid)
        return jsonify(result.as_dict()), result.http_status

    @app.post("/suggest")
    def suggest():
        if not authorized():
            return jsonify({"error": "unauthorized"}), 401
        data = request.get_json(silent=True) or {}
        contact = str(data.get("contact") or "").strip()
        jid = str(data.get("jid") or "").strip() or None
        if not contact and not jid:
            return jsonify({"error": "invalid contact"}), 400
        if len(contact) > 100:
            return jsonify({"error": "invalid contact"}), 400
        refresh = bool(data.get("refresh"))
        include_groups = bool(data.get("include_groups"))
        result = service.suggest(contact, jid=jid, refresh=refresh, include_groups=include_groups)
        return jsonify(result.as_dict()), result.http_status

    return app


def _keys_match(header: str | None, expected: str) -> bool:
    if not expected or not header:
        return False
    try:
        return hmac.compare_digest(header, expected)
    except (TypeError, ValueError):
        return False
