# WhatSuggest

WhatsApp AI reply suggestion assistant — floating button on Android triggers PC-side Claude to generate 3 reply suggestions from your chat history.

## How it works

1. Android app reads the current WhatsApp contact via AccessibilityService
2. Sends contact name to PC backend over Tailscale
3. PC backend calls `claude -p` with whatsapp-mcp tools to fetch last 30 messages
4. Returns 3 reply suggestions as JSON
5. Tap a suggestion → copies to clipboard → paste and send

## Architecture

```
Android (AccessibilityService + Overlay)
    └─ Tailscale ──► PC Backend (Flask/Python)
                          └─ claude -p + whatsapp-mcp (Go/Whatsmeow)
                                └─ WhatsApp Web protocol
```

## Repo structure

```
backend/    # Python Flask server (runs on PC)
android/    # Kotlin Android app
docs/       # Design docs and implementation plan
```

## Status

- [x] Design complete
- [ ] Phase 1: PC backend
- [ ] Phase 2: Android APK
