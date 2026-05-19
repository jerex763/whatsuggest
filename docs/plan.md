# WhatSuggest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a WhatsApp AI reply suggestion app — Android floating button triggers PC-side Claude to fetch chat history via whatsapp-mcp and return 3 reply suggestions.

**Architecture:** Android AccessibilityService reads the current WhatsApp contact name and sends it over Tailscale to a Flask server on the PC. The server calls `claude -p` with whatsapp-mcp MCP tools, which fetches the last 30 messages and generates 3 reply suggestions returned as JSON.

**Tech Stack:** Python 3.11 + Flask + waitress (PC), Kotlin + OkHttp + Coroutines (Android), lharries/whatsapp-mcp (Go/Whatsmeow), Claude Code Pro (`claude -p`), Tailscale, NSSM

**Spec:** `docs/superpowers/specs/2026-05-13-whatsuggest-design.md`

---

## File Map

### PC Backend
```
C:\whatsuggest\
  suggest_server.py       # Flask server — /suggest, /health, /version
  requirements.txt        # flask, waitress
  install-services.bat    # NSSM registration (run as admin)
  firewall.bat            # Windows Firewall rules (run as admin)
  logs\                   # Created by install script
C:\whatsapp-mcp\          # Cloned from lharries/whatsapp-mcp
  whatsapp-bridge\
    whatsapp-bridge.exe   # Pre-compiled Go binary
  whatsapp-mcp-server\
    main.py               # Python MCP server (run by Claude Code)
```

### Android APK (Android Studio project at `D:\cc\whatsuggest-android\`)
```
app/src/main/
  AndroidManifest.xml
  java/com/whatsuggest/
    WhatsAppContactWatcher.kt   # AccessibilityService — reads contact name, manages overlay
    OverlayManager.kt           # Floating button + suggestion popup UI
    SuggestRepository.kt        # OkHttp HTTP client → /suggest
    SetupWizardActivity.kt      # First-run permission + config wizard
    MainActivity.kt             # Entry point, redirects to SetupWizard if not configured
    Config.kt                   # SharedPreferences wrapper for serverUrl + apiKey
  res/
    xml/accessibility_service_config.xml
    xml/network_security_config.xml
    layout/overlay_button.xml
    layout/suggestion_popup.xml
    layout/activity_setup_wizard.xml
```

---

## Phase 1: PC Backend

---

### Task 1: Install whatsapp-mcp (Go bridge)

**Prerequisites:** Go 1.24+, MSYS2 + GCC installed, Tailscale installed

**Files:**
- Create: `C:\whatsapp-mcp\` (cloned repo)
- Create: `C:\whatsapp-mcp\whatsapp-bridge\whatsapp-bridge.exe`

- [ ] **Step 1: Install MSYS2 dependencies**

```bat
:: Run in regular CMD (not PowerShell)
pacman -S mingw-w64-ucrt-x86_64-gcc
```

Add `C:\msys64\ucrt64\bin` to Windows PATH via:
System Properties → Environment Variables → System variables → Path → New

- [ ] **Step 2: Enable CGO**

```bat
go env -w CGO_ENABLED=1
```

Verify: `go env CGO_ENABLED` should print `1`

- [ ] **Step 3: Clone and build**

```bat
git clone https://github.com/lharries/whatsapp-mcp C:\whatsapp-mcp
cd C:\whatsapp-mcp\whatsapp-bridge
set CGO_ENABLED=1
go build -o whatsapp-bridge.exe .
```

Expected: `whatsapp-bridge.exe` appears in the directory (~30-90 seconds compile time).
If you see `cgo: C compiler "gcc" not found`: re-check PATH includes `C:\msys64\ucrt64\bin`, then open a new CMD window.

- [ ] **Step 4: First-time QR pairing**

```bat
cd C:\whatsapp-mcp\whatsapp-bridge
.\whatsapp-bridge.exe
```

A QR code appears in the terminal. Open WhatsApp on your phone → Settings → Linked Devices → Link a Device → scan the QR code.

Wait for log output like `"Connected to WhatsApp"`. Leave it running for 30 minutes for message history to sync (watch the `whatsapp-bridge\store\` folder grow). Then `Ctrl+C`.

- [ ] **Step 5: Configure Claude Code MCP**

Edit `C:\Users\<your-username>\.claude\settings.json`. Add the `mcpServers` section (merge with existing content, don't replace):

```json
{
  "mcpServers": {
    "whatsapp": {
      "command": "uv",
      "args": [
        "--directory", "C:/whatsapp-mcp/whatsapp-mcp-server",
        "run", "main.py"
      ]
    }
  }
}
```

Install uv if needed: `pip install uv`

- [ ] **Step 6: Install Python MCP server dependencies**

```bat
cd C:\whatsapp-mcp\whatsapp-mcp-server
uv sync
```

- [ ] **Step 7: Verify MCP works in Claude Code**

Start `whatsapp-bridge.exe` in a terminal (keep it running). Then in a NEW Claude Code session, type:

```
Use whatsapp-mcp to list my recent chats
```

If Claude responds with actual chat names → MCP is working. If it says the tool isn't available → check the settings.json path and restart Claude Code.

- [ ] **Step 8: Commit nothing (external dependency, no git)**

Note: whatsapp-mcp is an external tool, not committed to your repo.

---

### Task 2: Create PC server skeleton

**Files:**
- Create: `C:\whatsuggest\suggest_server.py`
- Create: `C:\whatsuggest\requirements.txt`

- [ ] **Step 1: Create requirements.txt**

```
C:\whatsuggest\requirements.txt
```

```
flask==3.1.0
waitress==3.0.1
```

- [ ] **Step 2: Install dependencies**

```bat
pip install flask==3.1.0 waitress==3.0.1
```

- [ ] **Step 3: Create suggest_server.py with health + version only**

```python
# C:\whatsuggest\suggest_server.py
import os
import subprocess
from waitress import serve
from flask import Flask, jsonify

app = Flask(__name__)
API_KEY = os.environ.get("SUGGEST_API_KEY", "")
APP_VERSION = "1.0.0"


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/version")
def version():
    return jsonify({"version": APP_VERSION})


if __name__ == "__main__":
    result = subprocess.run(
        ["tailscale", "ip", "--4"],
        capture_output=True, text=True, timeout=5
    )
    ip = result.stdout.strip() if result.returncode == 0 else "127.0.0.1"
    print(f"Serving on http://{ip}:8000")
    serve(app, host=ip, port=8000, threads=8)
```

- [ ] **Step 4: Set API key environment variable**

```bat
:: In an admin CMD:
setx SUGGEST_API_KEY "change-this-to-a-random-secret" /M
```

Close and reopen CMD after this.

- [ ] **Step 5: Run the server and test health endpoint**

```bat
cd C:\whatsuggest
set SUGGEST_API_KEY=change-this-to-a-random-secret
python suggest_server.py
```

In a second terminal:
```bat
curl http://127.0.0.1:8000/health
```

Expected output: `{"status":"ok"}`

```bat
curl http://127.0.0.1:8000/version
```

Expected output: `{"version":"1.0.0"}`

- [ ] **Step 6: Stop the server (Ctrl+C)**

---

### Task 3: Add /suggest endpoint

**Files:**
- Modify: `C:\whatsuggest\suggest_server.py`

- [ ] **Step 1: Replace suggest_server.py with full implementation**

```python
# C:\whatsuggest\suggest_server.py
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
CLAUDE_EXE = shutil.which("claude") or r"C:\Users\<your-username>\.local\bin\claude.exe"
APP_VERSION = "1.0.0"
_semaphore = threading.Semaphore(2)


def extract_suggestions(text: str) -> list:
    """Parse Claude output: strip markdown fences, parse JSON array."""
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    data = json.loads(text)
    if isinstance(data, list):
        return [str(s) for s in data[:3]]
    if isinstance(data, dict) and "suggestions" in data:
        return data["suggestions"][:3]
    raise ValueError(f"Unexpected JSON shape: {data}")


def find_result(stdout: str) -> dict:
    """Find the type=result line in claude -p JSONL output."""
    for line in stdout.strip().split("\n"):
        try:
            obj = json.loads(line)
            if obj.get("type") == "result":
                return obj
        except Exception:
            continue
    return None


@app.post("/suggest")
def suggest():
    if request.headers.get("X-API-Key") != API_KEY:
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
        env["PYTHONIOENCODING"] = "utf-8"

        result = subprocess.run(
            [
                CLAUDE_EXE, "-p", prompt,
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
            return jsonify({"error": "no result from claude", "stderr": result.stderr[:500]}), 500

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
    result = subprocess.run(
        ["tailscale", "ip", "--4"],
        capture_output=True, text=True, timeout=5
    )
    ip = result.stdout.strip() if result.returncode == 0 else "127.0.0.1"
    print(f"Serving on http://{ip}:8000")
    serve(app, host=ip, port=8000, threads=8)
```

**Important:** Replace `<your-username>` in `CLAUDE_EXE` with your actual Windows username, or run `where claude` in CMD to find the correct path.

- [ ] **Step 2: Start whatsapp-bridge.exe in a separate terminal**

```bat
cd C:\whatsapp-mcp\whatsapp-bridge
.\whatsapp-bridge.exe
```

Keep this running.

- [ ] **Step 3: Start suggest_server.py**

```bat
cd C:\whatsuggest
set SUGGEST_API_KEY=change-this-to-a-random-secret
python suggest_server.py
```

- [ ] **Step 4: Test /suggest with a real contact name**

Replace `YourContactName` with someone in your WhatsApp:

```bat
curl -X POST http://127.0.0.1:8000/suggest ^
  -H "Content-Type: application/json" ^
  -H "X-API-Key: change-this-to-a-random-secret" ^
  -d "{\"contact\": \"YourContactName\"}"
```

Expected (after 10-25 seconds):
```json
{"suggestions": ["Hey! What's up?", "Sure, sounds good!", "Let me check and get back to you"]}
```

If you get `{"error": "no result from claude"}`: check that whatsapp-bridge is running AND Claude Code MCP is configured (Task 1 Step 5).

- [ ] **Step 5: Test auth rejection**

```bat
curl -X POST http://127.0.0.1:8000/suggest ^
  -H "Content-Type: application/json" ^
  -H "X-API-Key: wrong-key" ^
  -d "{\"contact\": \"test\"}"
```

Expected: `{"error":"unauthorized"}` with HTTP 401.

- [ ] **Step 6: Stop both processes (Ctrl+C each terminal)**

---

### Task 4: NSSM Windows Services

**Files:**
- Create: `C:\whatsuggest\install-services.bat`
- Create: `C:\whatsuggest\firewall.bat`
- Create: `C:\whatsuggest\logs\` (directory)

- [ ] **Step 1: Download NSSM**

Download from https://nssm.cc/download → extract → copy `nssm.exe` to `C:\Windows\System32\` (so it's in PATH).

Verify: `nssm version` in CMD should print the version.

- [ ] **Step 2: Create install-services.bat**

```bat
@echo off
:: Run this as Administrator

mkdir C:\whatsuggest\logs 2>nul

:: === WhatsApp Bridge ===
nssm install WhatsAppBridge "C:\whatsapp-mcp\whatsapp-bridge\whatsapp-bridge.exe"
nssm set WhatsAppBridge AppDirectory "C:\whatsapp-mcp\whatsapp-bridge"
nssm set WhatsAppBridge AppStdout "C:\whatsuggest\logs\bridge.log"
nssm set WhatsAppBridge AppStderr "C:\whatsuggest\logs\bridge-err.log"
nssm set WhatsAppBridge Start SERVICE_AUTO_START
nssm set WhatsAppBridge AppRestartDelay 5000

:: === Suggest Server ===
nssm install SuggestServer python "C:\whatsuggest\suggest_server.py"
nssm set SuggestServer AppDirectory "C:\whatsuggest"
nssm set SuggestServer AppEnvironmentExtra "SUGGEST_API_KEY=change-this-to-a-random-secret"
nssm set SuggestServer AppEnvironmentExtra+ "MCP_SERVER_NAME=whatsapp"
nssm set SuggestServer AppStdout "C:\whatsuggest\logs\server.log"
nssm set SuggestServer AppStderr "C:\whatsuggest\logs\server-err.log"
nssm set SuggestServer DependOnService WhatsAppBridge
nssm set SuggestServer Start SERVICE_AUTO_START
nssm set SuggestServer AppRestartDelay 3000

echo Starting services...
nssm start WhatsAppBridge
timeout /t 5 /nobreak
nssm start SuggestServer

echo Done. Check logs at C:\whatsuggest\logs\
```

**Replace** `change-this-to-a-random-secret` with your actual API key.

- [ ] **Step 3: Create firewall.bat**

```bat
@echo off
:: Run as Administrator
:: Allow Tailscale IPs (100.64.0.0/10) to reach port 8000
netsh advfirewall firewall add rule ^
    name="WhatSuggest Allow Tailscale" ^
    dir=in action=allow protocol=TCP ^
    localport=8000 remoteip=100.64.0.0/10

:: Block all other IPs from port 8000
netsh advfirewall firewall add rule ^
    name="WhatSuggest Block Others" ^
    dir=in action=block protocol=TCP localport=8000

echo Firewall rules added.
```

- [ ] **Step 4: Run both scripts as Administrator**

Right-click `install-services.bat` → Run as administrator.
Right-click `firewall.bat` → Run as administrator.

- [ ] **Step 5: Verify services are running**

```bat
nssm status WhatsAppBridge
nssm status SuggestServer
```

Both should show `SERVICE_RUNNING`.

Check logs:
```bat
type C:\whatsuggest\logs\server.log
```

Should show `Serving on http://100.x.x.x:8000`

- [ ] **Step 6: Test the running service**

Find your Tailscale IP: `tailscale ip --4`

```bat
curl -X POST http://<tailscale-ip>:8000/health
```

Expected: `{"status":"ok"}`

- [ ] **Step 7: Test auto-restart by rebooting**

Restart your PC. After boot, wait 30 seconds, then:

```bat
curl http://<tailscale-ip>:8000/health
```

Should still respond without manual intervention.

---

### Task 5: Tailscale node sharing

- [ ] **Step 1: Share your PC with friends**

Go to https://login.tailscale.com/admin/machines → find your PC → click `...` → `Share...` → copy the invite link.

Send this link to each friend. They:
1. Install Tailscale on their Android phone (Play Store)
2. Open the invite link → accept
3. Their Tailscale will now show your PC as `100.x.x.x`

- [ ] **Step 2: Verify friend can reach your server**

Ask a friend (or test from your own phone on mobile data with Tailscale running):

```
curl http://<tailscale-ip>:8000/health
```

Expected: `{"status":"ok"}`

---

## Phase 2: Android APK

**Prerequisites:** Android Studio installed (download from developer.android.com/studio). This guide assumes no prior Android knowledge.

---

### Task 6: Create Android project

**Files:**
- Create: `D:\cc\whatsuggest-android\` (new Android Studio project)

- [ ] **Step 1: Create new project in Android Studio**

Open Android Studio → New Project → Empty Views Activity

Settings:
- Name: `WhatSuggest`
- Package name: `com.whatsuggest`
- Save location: `D:\cc\whatsuggest-android`
- Language: Kotlin
- Minimum SDK: API 26 (Android 8.0)

Click Finish. Wait for Gradle sync to complete (may take 2-5 minutes on first run).

- [ ] **Step 2: Add OkHttp dependency**

Open `app/build.gradle` (the one inside the `app/` folder, not the root one).

Find the `dependencies { }` block and add:

```groovy
dependencies {
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
    // ... existing dependencies stay as-is
}
```

Click the "Sync Now" banner that appears.

- [ ] **Step 3: Verify build works**

Build → Make Project (Ctrl+F9). Should complete with "BUILD SUCCESSFUL".

---

### Task 7: AndroidManifest.xml + config files

**Files:**
- Modify: `app/src/main/AndroidManifest.xml`
- Create: `app/src/main/res/xml/accessibility_service_config.xml`
- Create: `app/src/main/res/xml/network_security_config.xml`

- [ ] **Step 1: Create res/xml/ directory**

In Android Studio's Project panel (left side), right-click `app/src/main/res` → New → Android Resource Directory → Resource type: `xml` → OK.

- [ ] **Step 2: Create accessibility_service_config.xml**

Right-click `res/xml/` → New → XML Resource File → name: `accessibility_service_config` → OK.

Replace all content with:

```xml
<?xml version="1.0" encoding="utf-8"?>
<accessibility-service
    xmlns:android="http://schemas.android.com/apk/res/android"
    android:accessibilityEventTypes="typeWindowStateChanged|typeWindowContentChanged"
    android:packageNames="com.whatsapp,com.whatsapp.w4b"
    android:canRetrieveWindowContent="true"
    android:accessibilityFeedbackType="feedbackGeneric"
    android:accessibilityFlags="flagReportViewIds"
    android:description="@string/accessibility_description" />
```

- [ ] **Step 3: Create network_security_config.xml**

Right-click `res/xml/` → New → XML Resource File → name: `network_security_config` → OK.

```xml
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <base-config cleartextTrafficPermitted="false" />
    <domain-config cleartextTrafficPermitted="true">
        <!-- Allow HTTP to your specific Tailscale PC IP, e.g. 100.94.12.34 -->
        <domain includeSubdomains="false">100.94.12.34</domain>
    </domain-config>
</network-security-config>
```

**Replace `100.94.12.34`** with your actual Tailscale IP (run `tailscale ip --4` on your PC).

- [ ] **Step 4: Add string resource**

Open `app/src/main/res/values/strings.xml`. Add inside `<resources>`:

```xml
<string name="accessibility_description">WhatSuggest reads the current WhatsApp contact name to generate AI reply suggestions</string>
```

- [ ] **Step 5: Replace AndroidManifest.xml**

```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">

    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_SPECIAL_USE" />
    <uses-permission android:name="android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS" />

    <application
        android:allowBackup="false"
        android:networkSecurityConfig="@xml/network_security_config"
        android:label="@string/app_name"
        android:theme="@style/Theme.WhatSuggest">

        <activity
            android:name=".MainActivity"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>

        <activity android:name=".SetupWizardActivity" />

        <service
            android:name=".WhatsAppContactWatcher"
            android:permission="android.permission.BIND_ACCESSIBILITY_SERVICE"
            android:exported="true"
            android:label="WhatSuggest">
            <intent-filter>
                <action android:name="android.accessibilityservice.AccessibilityService" />
            </intent-filter>
            <meta-data
                android:name="android.accessibilityservice"
                android:resource="@xml/accessibility_service_config" />
        </service>

    </application>
</manifest>
```

- [ ] **Step 6: Build to verify no errors**

Build → Make Project. Fix any red underlines before continuing.

---

### Task 8: Config.kt — SharedPreferences wrapper

**Files:**
- Create: `app/src/main/java/com/whatsuggest/Config.kt`

- [ ] **Step 1: Create Config.kt**

```kotlin
// app/src/main/java/com/whatsuggest/Config.kt
package com.whatsuggest

import android.content.Context

object Config {
    private const val PREFS = "whatsuggest_prefs"
    private const val KEY_SERVER_URL = "server_url"
    private const val KEY_API_KEY = "api_key"
    private const val KEY_NODE_ID = "wa_node_id"
    private const val DEFAULT_NODE_ID = "com.whatsapp:id/conversation_contact_name"

    fun getServerUrl(ctx: Context): String =
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_SERVER_URL, "") ?: ""

    fun getApiKey(ctx: Context): String =
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_API_KEY, "") ?: ""

    fun getNodeId(ctx: Context): String =
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_NODE_ID, DEFAULT_NODE_ID) ?: DEFAULT_NODE_ID

    fun saveServerConfig(ctx: Context, serverUrl: String, apiKey: String) {
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putString(KEY_SERVER_URL, serverUrl.trimEnd('/'))
            .putString(KEY_API_KEY, apiKey)
            .apply()
    }

    fun isConfigured(ctx: Context): Boolean {
        val url = getServerUrl(ctx)
        val key = getApiKey(ctx)
        return url.isNotEmpty() && key.isNotEmpty()
    }
}
```

- [ ] **Step 2: Build to verify no errors**

Build → Make Project.

---

### Task 9: SuggestRepository.kt — HTTP client

**Files:**
- Create: `app/src/main/java/com/whatsuggest/SuggestRepository.kt`

- [ ] **Step 1: Create SuggestRepository.kt**

```kotlin
// app/src/main/java/com/whatsuggest/SuggestRepository.kt
package com.whatsuggest

import android.content.Context
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

sealed class SuggestResult {
    data class Success(val suggestions: List<String>) : SuggestResult()
    data class Error(val message: String) : SuggestResult()
}

object SuggestRepository {
    private val client = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(90, TimeUnit.SECONDS)
        .build()

    suspend fun getSuggestions(context: Context, contactName: String): SuggestResult {
        val serverUrl = Config.getServerUrl(context)
        val apiKey = Config.getApiKey(context)

        if (serverUrl.isEmpty() || apiKey.isEmpty()) {
            return SuggestResult.Error("服务器未配置，请检查设置")
        }

        val body = JSONObject().put("contact", contactName).toString()
            .toRequestBody("application/json".toMediaType())

        val request = Request.Builder()
            .url("$serverUrl/suggest")
            .addHeader("X-API-Key", apiKey)
            .post(body)
            .build()

        return try {
            val response = client.newCall(request).execute()
            when (response.code) {
                200 -> {
                    val json = JSONObject(response.body!!.string())
                    val arr = json.getJSONArray("suggestions")
                    val list = (0 until arr.length()).map { arr.getString(it) }
                    SuggestResult.Success(list)
                }
                401 -> SuggestResult.Error("认证失败，请检查 API Key")
                429 -> SuggestResult.Error("服务繁忙，请稍等后重试")
                504 -> SuggestResult.Error("生成超时，请重试")
                else -> SuggestResult.Error("服务器错误 (${response.code})")
            }
        } catch (e: java.net.ConnectException) {
            SuggestResult.Error("无法连接，请检查 Tailscale 是否开启")
        } catch (e: java.net.SocketTimeoutException) {
            SuggestResult.Error("响应超时，请重试")
        } catch (e: IOException) {
            SuggestResult.Error("网络错误：${e.message}")
        }
    }

    fun testConnection(serverUrl: String, apiKey: String): Boolean {
        val request = Request.Builder()
            .url("$serverUrl/health")
            .addHeader("X-API-Key", apiKey)
            .get()
            .build()
        return try {
            val response = client.newCall(request).execute()
            response.isSuccessful
        } catch (e: Exception) {
            false
        }
    }
}
```

- [ ] **Step 2: Build to verify no errors**

Build → Make Project.

---

### Task 10: Layout files

**Files:**
- Create: `app/src/main/res/layout/overlay_button.xml`
- Create: `app/src/main/res/layout/suggestion_popup.xml`
- Create: `app/src/main/res/layout/activity_setup_wizard.xml`

- [ ] **Step 1: Create overlay_button.xml**

Right-click `res/layout/` → New → Layout Resource File → `overlay_button` → OK.

```xml
<?xml version="1.0" encoding="utf-8"?>
<FrameLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="56dp"
    android:layout_height="56dp">

    <Button
        android:id="@+id/btnSuggest"
        android:layout_width="56dp"
        android:layout_height="56dp"
        android:background="@drawable/ic_launcher_background"
        android:text="AI"
        android:textColor="#FFFFFF"
        android:textSize="12sp"
        android:alpha="0.85" />
</FrameLayout>
```

- [ ] **Step 2: Create suggestion_popup.xml**

```xml
<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="280dp"
    android:layout_height="wrap_content"
    android:orientation="vertical"
    android:background="#FF1B5E20"
    android:padding="12dp"
    android:elevation="8dp">

    <TextView
        android:id="@+id/tvLoading"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:text="生成中..."
        android:textColor="#FFFFFF"
        android:visibility="visible" />

    <TextView
        android:id="@+id/tvError"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:textColor="#FFFF5252"
        android:visibility="gone" />

    <LinearLayout
        android:id="@+id/llSuggestions"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:orientation="vertical"
        android:visibility="gone">

        <Button
            android:id="@+id/btnSuggestion1"
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:textColor="#FFFFFF"
            android:background="@android:color/transparent"
            android:gravity="start"
            android:paddingStart="0dp" />

        <Button
            android:id="@+id/btnSuggestion2"
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:textColor="#FFFFFF"
            android:background="@android:color/transparent"
            android:gravity="start"
            android:paddingStart="0dp" />

        <Button
            android:id="@+id/btnSuggestion3"
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:textColor="#FFFFFF"
            android:background="@android:color/transparent"
            android:gravity="start"
            android:paddingStart="0dp" />
    </LinearLayout>
</LinearLayout>
```

- [ ] **Step 3: Create activity_setup_wizard.xml**

```xml
<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:orientation="vertical"
    android:padding="24dp">

    <TextView
        android:id="@+id/tvStep"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:text="步骤 1 / 2"
        android:textSize="14sp" />

    <TextView
        android:id="@+id/tvTitle"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:textSize="22sp"
        android:layout_marginTop="8dp" />

    <TextView
        android:id="@+id/tvDescription"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:layout_marginTop="16dp"
        android:textSize="15sp" />

    <!-- Step 2 only: server config -->
    <EditText
        android:id="@+id/etServerUrl"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:layout_marginTop="24dp"
        android:hint="服务器地址（如 http://100.94.12.34:8000）"
        android:inputType="textUri"
        android:visibility="gone" />

    <EditText
        android:id="@+id/etApiKey"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:layout_marginTop="8dp"
        android:hint="API Key"
        android:inputType="textPassword"
        android:visibility="gone" />

    <TextView
        android:id="@+id/tvTestResult"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:layout_marginTop="8dp"
        android:visibility="gone" />

    <Button
        android:id="@+id/btnAction"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:layout_marginTop="32dp"
        android:text="继续" />
</LinearLayout>
```

- [ ] **Step 4: Build to verify no errors**

Build → Make Project.

---

### Task 11: OverlayManager.kt

**Files:**
- Create: `app/src/main/java/com/whatsuggest/OverlayManager.kt`

- [ ] **Step 1: Create OverlayManager.kt**

```kotlin
// app/src/main/java/com/whatsuggest/OverlayManager.kt
package com.whatsuggest

import android.accessibilityservice.AccessibilityService
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.graphics.PixelFormat
import android.view.Gravity
import android.view.LayoutInflater
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast

class OverlayManager(private val service: AccessibilityService) {

    private val wm = service.getSystemService(Context.WINDOW_SERVICE) as WindowManager
    private var buttonView: View? = null
    private var popupView: View? = null

    private fun overlayParams(w: Int, h: Int) = WindowManager.LayoutParams(
        w, h,
        WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
        WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
        PixelFormat.TRANSLUCENT
    )

    fun showButton(onTap: () -> Unit) {
        if (buttonView != null) return
        val view = LayoutInflater.from(service).inflate(R.layout.overlay_button, null)
        val params = overlayParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT
        ).apply {
            gravity = Gravity.BOTTOM or Gravity.END
            x = 24; y = 200
        }
        view.findViewById<Button>(R.id.btnSuggest).setOnClickListener { onTap() }
        wm.addView(view, params)
        buttonView = view
    }

    fun hideButton() {
        buttonView?.let { wm.removeView(it); buttonView = null }
        hidePopup()
    }

    fun showLoading() {
        dismissPopupView()
        val view = LayoutInflater.from(service).inflate(R.layout.suggestion_popup, null)
        view.findViewById<TextView>(R.id.tvLoading).visibility = View.VISIBLE
        view.findViewById<LinearLayout>(R.id.llSuggestions).visibility = View.GONE
        view.findViewById<TextView>(R.id.tvError).visibility = View.GONE
        val params = overlayParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT
        ).apply { gravity = Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL; y = 280 }
        wm.addView(view, params)
        popupView = view
    }

    fun showSuggestions(suggestions: List<String>) {
        val view = popupView ?: return
        view.findViewById<TextView>(R.id.tvLoading).visibility = View.GONE
        view.findViewById<TextView>(R.id.tvError).visibility = View.GONE
        val ll = view.findViewById<LinearLayout>(R.id.llSuggestions)
        ll.visibility = View.VISIBLE
        val btns = listOf(R.id.btnSuggestion1, R.id.btnSuggestion2, R.id.btnSuggestion3)
        btns.forEachIndexed { i, id ->
            val text = suggestions.getOrElse(i) { "" }
            val btn = view.findViewById<Button>(id)
            if (text.isBlank()) { btn.visibility = View.GONE; return@forEachIndexed }
            btn.text = text
            btn.setOnClickListener {
                val cm = service.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                cm.setPrimaryClip(ClipData.newPlainText("suggestion", text))
                Toast.makeText(service, "已复制", Toast.LENGTH_SHORT).show()
                hidePopup()
            }
        }
    }

    fun showError(message: String) {
        val view = popupView ?: return
        view.findViewById<TextView>(R.id.tvLoading).visibility = View.GONE
        view.findViewById<LinearLayout>(R.id.llSuggestions).visibility = View.GONE
        val tvError = view.findViewById<TextView>(R.id.tvError)
        tvError.text = message
        tvError.visibility = View.VISIBLE
    }

    fun hidePopup() = dismissPopupView()

    private fun dismissPopupView() {
        popupView?.let { wm.removeView(it); popupView = null }
    }
}
```

- [ ] **Step 2: Build to verify no errors**

Build → Make Project.

---

### Task 12: WhatsAppContactWatcher.kt (AccessibilityService)

**Files:**
- Create: `app/src/main/java/com/whatsuggest/WhatsAppContactWatcher.kt`

- [ ] **Step 1: Create WhatsAppContactWatcher.kt**

```kotlin
// app/src/main/java/com/whatsuggest/WhatsAppContactWatcher.kt
package com.whatsuggest

import android.accessibilityservice.AccessibilityService
import android.view.accessibility.AccessibilityEvent
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class WhatsAppContactWatcher : AccessibilityService() {

    private lateinit var overlayManager: OverlayManager
    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())
    private var currentJob: Job? = null

    override fun onServiceConnected() {
        overlayManager = OverlayManager(this)
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent) {
        val pkg = event.packageName?.toString() ?: return
        if (pkg != "com.whatsapp" && pkg != "com.whatsapp.w4b") {
            overlayManager.hideButton()
            return
        }

        val contactName = readContactName()
        if (contactName != null) {
            overlayManager.showButton { onSuggestTapped() }
        } else {
            overlayManager.hideButton()
        }
    }

    private fun readContactName(): String? {
        val root = rootInActiveWindow ?: return null
        val nodeId = Config.getNodeId(this)
        return try {
            val nodes = root.findAccessibilityNodeInfosByViewId(nodeId)
            val name = nodes.firstOrNull()?.text?.toString()?.takeIf { it.isNotBlank() }
            nodes.forEach { it.recycle() }
            root.recycle()
            name
        } catch (e: Exception) {
            null
        }
    }

    private fun onSuggestTapped() {
        val contactName = readContactName()
        if (contactName == null) {
            overlayManager.showLoading()
            overlayManager.showError("请先打开一个对话")
            return
        }

        currentJob?.cancel()
        overlayManager.showLoading()

        currentJob = scope.launch {
            val result = withContext(Dispatchers.IO) {
                SuggestRepository.getSuggestions(this@WhatsAppContactWatcher, contactName)
            }
            when (result) {
                is SuggestResult.Success -> overlayManager.showSuggestions(result.suggestions)
                is SuggestResult.Error -> overlayManager.showError(result.message)
            }
        }
    }

    override fun onInterrupt() {}

    override fun onDestroy() {
        super.onDestroy()
        overlayManager.hideButton()
        currentJob?.cancel()
    }
}
```

- [ ] **Step 2: Build to verify no errors**

Build → Make Project.

---

### Task 13: SetupWizardActivity.kt + MainActivity.kt

**Files:**
- Create: `app/src/main/java/com/whatsuggest/SetupWizardActivity.kt`
- Modify: `app/src/main/java/com/whatsuggest/MainActivity.kt`

- [ ] **Step 1: Create SetupWizardActivity.kt**

```kotlin
// app/src/main/java/com/whatsuggest/SetupWizardActivity.kt
package com.whatsuggest

import android.content.ComponentName
import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class SetupWizardActivity : AppCompatActivity() {

    private var step = 1

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_setup_wizard)
        showStep(1)
    }

    override fun onResume() {
        super.onResume()
        // Auto-advance when Accessibility is enabled
        if (step == 1 && isAccessibilityEnabled()) {
            showStep(2)
        }
    }

    private fun showStep(s: Int) {
        step = s
        val tvStep = findViewById<TextView>(R.id.tvStep)
        val tvTitle = findViewById<TextView>(R.id.tvTitle)
        val tvDesc = findViewById<TextView>(R.id.tvDescription)
        val etUrl = findViewById<EditText>(R.id.etServerUrl)
        val etKey = findViewById<EditText>(R.id.etApiKey)
        val tvTest = findViewById<TextView>(R.id.tvTestResult)
        val btnAction = findViewById<Button>(R.id.btnAction)

        tvTest.visibility = View.GONE

        when (s) {
            1 -> {
                tvStep.text = "步骤 1 / 2"
                tvTitle.text = "开启无障碍权限"
                tvDesc.text = "WhatSuggest 需要无障碍权限来检测当前打开的 WhatsApp 对话。\n\n" +
                        "点击下方按钮，找到 WhatSuggest，开启开关。\n\n" +
                        "注意：Android 13+ 可能需要先点「允许受限设置」。"
                etUrl.visibility = View.GONE
                etKey.visibility = View.GONE
                btnAction.text = "去开启权限"
                btnAction.setOnClickListener {
                    startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
                }
            }
            2 -> {
                tvStep.text = "步骤 2 / 2"
                tvTitle.text = "配置服务器"
                tvDesc.text = "输入你的 PC 服务器地址和 API Key。"
                etUrl.visibility = View.VISIBLE
                etKey.visibility = View.VISIBLE
                etUrl.setText(Config.getServerUrl(this))
                etKey.setText(Config.getApiKey(this))
                btnAction.text = "测试并保存"
                btnAction.setOnClickListener {
                    val url = etUrl.text.toString().trim()
                    val key = etKey.text.toString().trim()
                    if (url.isEmpty() || key.isEmpty()) {
                        tvTest.text = "请填写所有字段"
                        tvTest.visibility = View.VISIBLE
                        return@setOnClickListener
                    }
                    btnAction.isEnabled = false
                    tvTest.text = "测试中..."
                    tvTest.visibility = View.VISIBLE
                    CoroutineScope(Dispatchers.IO).launch {
                        val ok = SuggestRepository.testConnection(url, key)
                        withContext(Dispatchers.Main) {
                            btnAction.isEnabled = true
                            if (ok) {
                                Config.saveServerConfig(this@SetupWizardActivity, url, key)
                                tvTest.text = "✓ 连接成功！"
                                // Finish setup after brief delay
                                btnAction.text = "完成"
                                btnAction.setOnClickListener {
                                    startActivity(Intent(this@SetupWizardActivity, MainActivity::class.java))
                                    finish()
                                }
                            } else {
                                tvTest.text = "✗ 连接失败。检查服务器地址、API Key 和 Tailscale 是否开启。"
                            }
                        }
                    }
                }
            }
        }
    }

    private fun isAccessibilityEnabled(): Boolean {
        val enabled = Settings.Secure.getString(
            contentResolver,
            Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES
        ) ?: return false
        val component = ComponentName(this, WhatsAppContactWatcher::class.java)
        return enabled.split(":").any {
            ComponentName.unflattenFromString(it) == component
        }
    }
}
```

- [ ] **Step 2: Replace MainActivity.kt**

```kotlin
// app/src/main/java/com/whatsuggest/MainActivity.kt
package com.whatsuggest

import android.content.Intent
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!Config.isConfigured(this)) {
            startActivity(Intent(this, SetupWizardActivity::class.java))
        }
        finish() // MainActivity has no UI — it just routes
    }
}
```

- [ ] **Step 3: Build to verify no errors**

Build → Make Project. Fix any red underlines.

---

### Task 14: Build, sign, and sideload APK

- [ ] **Step 1: Create a release keystore (one-time)**

In Android Studio: Build → Generate Signed Bundle / APK → APK → Next → Create new...

- Key store path: `D:\cc\whatsuggest.jks` (save this file somewhere safe!)
- Password: choose a strong password
- Key alias: `whatsuggest`
- Key password: same or different
- Fill in at least "First and Last Name"

Click OK → Next → select `release` → Finish.

The APK is generated at:
`D:\cc\whatsuggest-android\app\release\app-release.apk`

- [ ] **Step 2: Enable unknown sources on your Android phone**

Settings → Apps → Special app access → Install unknown apps → find your file manager → Allow.

- [ ] **Step 3: Transfer APK to phone**

Send the APK file to your phone via WhatsApp, Telegram, USB, or email. Open it and install.

- [ ] **Step 4: Run SetupWizard on phone**

Open WhatSuggest → follow the 2-step wizard:
1. Enable Accessibility (Settings → Accessibility → Installed apps → WhatSuggest → Enable)
2. Enter server URL (`http://100.x.x.x:8000`) and API Key → Test → Save

- [ ] **Step 5: End-to-end test**

Open WhatsApp → open a conversation → the "AI" button should appear in the bottom-right corner → tap it → wait 10-20 seconds → 3 suggestions appear → tap one → paste into WhatsApp input → send.

- [ ] **Step 6: Send APK to friends**

Share `app-release.apk` via WhatsApp/Telegram. They follow the same install steps. Give them:
- The Tailscale invite link (from Task 5)
- The server URL and API Key

---

## Known Issues & Monitoring

- **Bridge session expires:** If suggestions stop working, follow Session Recovery in the spec (Section 6.3)
- **WhatsApp update breaks node ID:** Check `C:\whatsuggest\logs\server.log` for errors; update `wa_node_id` in SharedPreferences if needed
- **`claude -p` slow:** Normal latency is 10-25s. If consistently >60s, check GitHub issue #20527
