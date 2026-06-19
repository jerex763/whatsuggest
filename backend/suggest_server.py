import os
import re
import json
import shutil
import subprocess
import threading
from waitress import serve
from flask import Flask, request, jsonify

app = Flask(__name__)
API_KEY = os.environ.get("SUGGEST_API_KEY", "")
MCP_SERVER_NAME = os.environ.get("MCP_SERVER_NAME", "whatsapp")
CLAUDE_CMD = [shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")]
APP_VERSION = "1.0.0"
_semaphore = threading.Semaphore(2)


def extract_suggestions(text: str) -> list:
    """Parse Claude output: strip markdown fences, parse JSON array."""
    start = next((i for i, c in enumerate(text) if c in "[{"), 0)
    text = text[start:]
    if text.endswith("```"):
        text = text[:-3].strip()
    data = json.loads(text)
    if isinstance(data, list):
        return [str(s) for s in data[:3]]
    if isinstance(data, dict) and "suggestions" in data:
        return [str(s) for s in data["suggestions"][:3]]
    raise ValueError(f"Unexpected JSON shape: {data}")


def find_result(stdout: str) -> dict:
    """Find the type=result entry in claude -p output (JSONL or JSON array)."""
    stripped = stdout.strip()
    if stripped.startswith("["):
        try:
            for obj in json.loads(stripped):
                if obj.get("type") == "result":
                    return obj
        except Exception:
            pass
    for line in stripped.split("\n"):
        try:
            obj = json.loads(line)
            if obj.get("type") == "result":
                return obj
        except Exception:
            continue
    return None


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "not found"}), 404


@app.errorhandler(Exception)
def server_error(e):
    return jsonify({"error": "internal server error"}), 500


@app.post("/suggest")
def suggest():
    if not API_KEY or request.headers.get("X-API-Key") != API_KEY:
        return jsonify({"error": "unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    contact = data.get("contact", "").strip()
    if not contact or len(contact) > 100:
        return jsonify({"error": "invalid contact"}), 400

    if not _semaphore.acquire(blocking=False):
        return jsonify({"error": "busy"}), 429

    try:
        prompt = (
            f'Use whatsapp-mcp tools to find the WhatsApp contact named "{contact}". '
            f'Call search_contacts with that name to get their JID. '
            f'If not found, try list_chats to find a matching chat. '
            f'Then call list_messages with the JID, limit=30. '
            f'If messages are empty, return ["消息同步中，请稍后重试", "", ""] and stop. '
            f'Otherwise suggest exactly 3 natural reply messages in the same language '
            f'as the conversation. '
            f'Return ONLY a JSON array of exactly 3 strings. No explanation, no markdown.'
        )

        env = os.environ.copy()

        result = subprocess.run(
            CLAUDE_CMD + [
                "-p", prompt,
                "--output-format", "json",
                "--allowedTools",
                f"mcp__{MCP_SERVER_NAME}__search_contacts,"
                f"mcp__{MCP_SERVER_NAME}__list_messages,"
                f"mcp__{MCP_SERVER_NAME}__list_chats",
            ],
            capture_output=True,
            text=True,
            timeout=85,
            encoding="utf-8",
            env=env,
        )

        output = find_result(result.stdout)
        if output is None:
            return jsonify({"error": "no result from claude", "stderr": result.stderr[:300], "stdout": result.stdout[:300]}), 500

        if output.get("is_error"):
            return jsonify({"error": "claude error", "detail": output.get("result", "")}), 500

        suggestions = extract_suggestions(output.get("result", ""))
        return jsonify({"suggestions": suggestions})

    except subprocess.TimeoutExpired:
        return jsonify({"error": "timeout"}), 504
    except (json.JSONDecodeError, ValueError) as e:
        return jsonify({"error": "parse error", "detail": str(e)}), 500
    finally:
        _semaphore.release()


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/version")
def version():
    return jsonify({"version": APP_VERSION})


if __name__ == "__main__":
    if not API_KEY:
        print("WARNING: SUGGEST_API_KEY not set — all requests will be rejected")
    try:
        result = subprocess.run(
            ["tailscale", "ip", "--4"],
            capture_output=True, text=True, timeout=5
        )
        ip = result.stdout.strip() if result.returncode == 0 else "0.0.0.0"
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        ip = "0.0.0.0"
    print(f"Serving on http://{ip}:8000")
    serve(app, host=ip, port=8000, threads=8)
