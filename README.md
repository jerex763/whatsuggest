# WhatSuggest

WhatsApp reply drafts for Florence. The Android app shows three suggestions above the message box. She taps one to fill the input, edits it if she wants, and presses send herself. The app never sends a message.

## How it works

1. The whatsapp-mcp bridge (Whatsmeow) keeps chats in a local SQLite file, `whatsapp-bridge/store/messages.db`.
2. The Python server on her Windows PC reads that file directly. It does not ask the model to call WhatsApp tools.
3. A watcher notices new incoming messages, waits out bursts from the same chat, and pre-generates three drafts with the Codex CLI (`codex exec`), using her existing Codex login. No API key.
4. When she opens a chat, the phone fetches the cached drafts (or asks the server to generate them) and shows a bar just above WhatsApp's input.
5. Tapping a draft writes it into the input with the accessibility action `ACTION_SET_TEXT`. If that fails, the app pastes from the clipboard. She sends it herself.
6. The small AI button is still there. Tap it to refresh. Long-press it to mute that contact on the phone.

```
WhatsApp on the phone
  AccessibilityService reads the chat title and the message box
  suggestion bar  ── Tailscale HTTP + API key ──►  Flask server (Windows)
                                                      ├─ read messages.db
                                                      ├─ persona + per-contact rules
                                                      └─ one `codex exec` call → 3 suggestions
```

Groups are skipped unless she taps the AI button. Muted contacts (in `config.yaml`, or muted on the phone) get no automatic bar.

## Repo layout

```
backend/                 Flask server, watcher, tests
  whatsuggest/           Python package
  config.example.yaml    copy to config.yaml; no secrets in this file
  install-services.bat   NSSM services (run as Administrator)
  firewall.bat           Tailscale-only rule for port 8000
  run-server.bat         foreground run, for checking
android/                 Kotlin app
docs/                    older Claude design; the current design is this README
```

## Server design

The model sits behind a small provider interface (`whatsuggest/providers`):

- `codex` (default). Runs `codex exec -` with the prompt on stdin, so a Windows `codex.cmd` shim cannot split a multiline prompt. Flags, from the current Codex CLI docs: `--output-schema`, `--output-last-message`, `--sandbox read-only`, `--skip-git-repo-check`, `--ephemeral`, `--cd` (an empty folder), `--color never`. `OPENAI_API_KEY` is removed from the child process unless `llm.codex.use_api_key` is true, so Codex uses `codex login`.
- `openai`. Same prompt, Chat Completions `response_format: json_schema`. Set `llm.provider: openai` and the env var named by `llm.openai.api_key_env`. Not used until you switch it on.

Chat matching prefers a JID, then a JID pinned in config, then an exact name, then a fuzzy name. Names of three characters or fewer (typical Chinese names) only match exactly. The prompt includes her persona, the contact rule, who spoke last, how long ago that was, and the last 30 messages. The model must return JSON `{"suggestions": ["...", "...", "..."]}`.

The watcher polls SQLite `rowid`. Incoming messages debounce per chat (default 8 seconds). Her own reply deletes the cached drafts. Rows older than 10 minutes are not pre-generated, so a history sync cannot queue a call per old chat. The server binds to `tailscale ip --4` unless `server.host` is set, and every endpoint requires `X-API-Key`.

There is no endpoint that sends a WhatsApp message.

## What Florence needs to do on the PC

The bridge install (Go, MSYS2, QR pairing) is unchanged. If it is already paired, leave `store/messages.db` where it is.

1. Install the Codex CLI and log in with the account she already uses. In a terminal: `codex login`, then `codex exec "say hi" --skip-git-repo-check`. It should print a reply without asking for an API key.
2. From `backend/`, copy `config.example.yaml` to `config.yaml`. Set `database.path` to the real `messages.db`. Edit the persona and the contact rules. Do not put the API key in the file.
3. Pick an API key the phone will send (a long random string). In an Administrator command prompt: `setx SUGGEST_API_KEY "that-string" /M`. Close and reopen the prompt.
4. `pip install -r requirements.txt`
5. In a normal prompt, `set SUGGEST_API_KEY=that-string` and run `run-server.bat`. From another prompt: `curl -H "X-API-Key: that-string" http://127.0.0.1:8000/health` (or the Tailscale address printed by the server). Expect `"status": "ok"` and `"db": true`.
6. If a phone name does not match the name in the database, open `http://<tailscale-ip>:8000/chats?q=妈妈` with the same header. Put the phone's name and the `jid` under that contact in `config.yaml`, then restart the server.
7. Run `firewall.bat` as Administrator. Port 8000 accepts only Tailscale (`100.64.0.0/10`).
8. Run `install-services.bat` as Administrator after editing `API_KEY` in that file. It replaces the old services. The server no longer needs `MCP_SERVER_NAME` or a Claude MCP config.
9. Share the PC in the Tailscale admin console if the phone is not already on the tailnet.

`codex` on Windows is often a `codex.cmd` from npm. The server detects that and runs it through `cmd.exe`, with the prompt on stdin. If detection fails, set `llm.codex.command` to the full path of `codex.exe`.

## What Florence needs to do on the phone

1. Tailscale is connected, and this PC is visible.
2. Install the new APK (versionCode 2) over the old one, using the same signing key if she has it.
3. Accessibility for WhatSuggest stays on. Android 13+ may ask her to allow restricted settings once.
4. Open WhatSuggest. The server address is whatever she types, for example `http://100.x.x.x:8000`. It is no longer compiled into the app. Enter the API key and test the connection.
5. Open a WhatsApp chat. A green bar should appear above the input. Tap a suggestion: it fills the box. She presses send. The AI button refreshes. The × hides the bar until she leaves the chat and opens it again. Long-press AI mutes that chat on the phone; the list is in the WhatSuggest app, with a button to clear it.
6. The app only reads WhatsApp's title and message box. It does not read other apps. Seeing other windows is only so the bar disappears when she leaves WhatsApp.

## Tests

```bat
cd backend
pip install -r requirements-dev.txt
python -m pytest
```

Covers prompt building, reading a fixture SQLite database shaped like the bridge, JSON parsing, watcher debounce / invalidate / skip groups, and a mocked `codex exec` (including the Windows `.cmd` command line).

## 中文说明

这是 Florence 的 WhatsApp 回复建议助手。电脑上的程序读 WhatsApp 桥接数据库，用已经登录的 Codex 想出 3 句回复。手机打开聊天时，输入框上面自动出现这 3 句。点一句，字会填进输入框。发送要自己按。程序不会自动发送。

### 电脑上要做的

1. 安装 Codex，并在终端执行 `codex login`。再用 `codex exec "say hi" --skip-git-repo-check` 试一次，能正常回答就可以。不需要 API key。
2. 把 `backend/config.example.yaml` 复制成 `backend/config.yaml`。把数据库路径改成你的 `messages.db`。写上你平时说话的习惯，以及每个联系人（或一组联系人）的语气、语言、不要说的话、例句。家人用中文、客户用英文，就写在对应的 `language` 里。密钥不要写进这个文件。
3. 自己定一个长密钥。用管理员命令提示符执行 `setx SUGGEST_API_KEY "你的密钥" /M`，然后关掉窗口再打开。
4. 在 `backend` 目录执行 `pip install -r requirements.txt`。
5. 先双击或运行 `run-server.bat` 看能否启动。健康检查应显示数据库可读。
6. 手机上的名字和电脑数据库里的名字不一样时，用浏览器或 curl 打开 `http://电脑的Tailscale地址:8000/chats?q=名字`（加上请求头 `X-API-Key`）。把查到的 `jid` 和手机上显示的名字一起写进 `config.yaml`。
7. 用管理员身份运行 `firewall.bat`。只有 Tailscale 能访问 8000 端口。
8. 用管理员身份运行 `install-services.bat`（先改脚本里的 `API_KEY`）。它会重装 Windows 服务，开机自动启动。不再需要 Claude，也不需要配置 MCP。
9. 手机上的 Tailscale 要能看到这台电脑。

### 手机上要做的

1. 安装新的 APK（覆盖安装即可，设置还在）。
2. 无障碍里打开 WhatSuggest。
3. 打开 WhatSuggest，填写服务器地址，例如 `http://100.x.x.x:8000`，以及上面的密钥，点测试。地址不用再写死在安装包里。
4. 打开一个 WhatsApp 聊天。输入框上方会出现建议。点一条就填进输入框，自己按发送。
5. 输入框旁边的 AI 按钮是手动刷新。长按它，这个联系人就不再自动出建议。想恢复，打开 WhatSuggest，点「清除手机静音」。
6. 群聊默认不自动出建议。需要时点 AI 按钮。也可以在 `config.yaml` 里把 `skip_groups` 改成 `false`。
7. 在 `config.yaml` 的 `muted` 里写上的人或群，电脑不会为他们生成建议。

建议只是草稿。无论手机还是电脑，都没有自动发送。
