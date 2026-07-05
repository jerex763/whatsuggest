# WhatSuggest

WhatsApp AI reply suggestion assistant — floating button on Android triggers PC-side Claude to generate 3 reply suggestions from your chat history.

**Single-user tool.** The backend is paired to one WhatsApp account and generates suggestions from that account's message history. It cannot serve other people: a friend's phone would send *their* contact names to be looked up in *your* chat database — at best finding nothing, at worst leaking your conversations on a name collision. Each user must run their own bridge + backend.

## How it works

1. Android app reads the current WhatsApp contact via AccessibilityService
2. Sends contact name to PC backend (Tailscale, or LAN during dev)
3. Backend looks up the chat and last 30 messages directly in whatsapp-mcp's SQLite, then makes one `claude -p` call with the transcript inlined
4. Returns 3 reply suggestions as JSON
5. Tap a suggestion → copies to clipboard → paste and send

## Architecture

```
Android (AccessibilityService + Overlay)
    └─ Tailscale/LAN ──► Backend (Flask/Python)
                          ├─ reads messages.db (SQLite, written by whatsapp-bridge)
                          └─ claude -p (single call, transcript inlined, no tools)

whatsapp-bridge (Go/Whatsmeow) ──► WhatsApp Web protocol ──► messages.db
```

## Repo structure

```
backend/    # Python Flask server (runs on PC)
android/    # Kotlin Android app
docs/       # Design docs and implementation plan
```

## Status

- [x] Design complete
- [x] Phase 1: Backend (validated end-to-end on Mac; Windows remains the long-term host)
- [x] Phase 2: Android APK (built, sideloaded, verified on a real device over LAN)
