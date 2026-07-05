# WhatSuggest — 设计文档

**日期：** 2026-05-13  
**状态：** 草稿，待用户审批  
**项目：** WhatsApp AI 回复建议助手（小范围侧载分发）

> **⚠️ 范围变更（2026-07-05）：** 多朋友共享后端的设计已废弃。后端只连接一个 WhatsApp 账号，
> 建议内容来自该账号的消息历史——朋友手机上读到的是他们自己的联系人名，拿到你的后端查询
> 只会查无此人，或在撞名时把你的私聊内容泄露给朋友。本项目定位为单用户个人工具；
> 朋友要用需各自部署一套 bridge + backend。下文中 Tailscale 节点分享给朋友、共享 API Key
> 等相关章节（2.1、6.1、6.2 等）仅作历史记录保留，不再实施。
>
> **架构变更（2026-07-05）：** 后端不再让 Claude 通过 MCP 工具查消息（4.1/4.2 的
> `--allowedTools mcp__whatsapp__*` 方案已废弃），改为 Flask 直接只读查询 bridge 的
> messages.db，单次 `claude -p` 调用内联消息记录。延迟从 ~30s 降至 ~11s，
> 同时消除了联系人名 prompt 注入的工具面。见 `backend/suggest_server.py`。

---

## 1. 项目概述

WhatSuggest 是一个 Android 应用，当用户打开 WhatsApp 对话时，通过浮窗按钮触发 AI 生成 3 条回复建议，用户点击即复制到剪贴板，手动粘贴发送。

**核心约束：**
- 侧载 APK，不上 Play Store
- 不需要单独 Anthropic API Key，使用 Claude Code Pro 订阅（`claude -p`）
- 电脑常开，Tailscale 节点分享给朋友
- 备用 WhatsApp 号连接 MCP（测试阶段），验证后可换主号

---

## 2. 整体架构

### 2.1 系统图

```
┌──────────────────────────────────────────────────────┐
│                   用户手机（Android）                   │
│                                                      │
│  WhatsApp（官方 app，主号）                             │
│                                                      │
│  WhatSuggest APK：                                   │
│  ┌──────────────────────────────────────────────┐   │
│  │ WhatsAppContactWatcher（AccessibilityService）│   │
│  │  typeWindowStateChanged → 读 contact_name    │   │
│  ├──────────────────────────────────────────────┤   │
│  │ 浮窗按钮（TYPE_ACCESSIBILITY_OVERLAY）        │   │
│  │  点击 → 实时读当前联系人名                    │   │
│  │  → POST /suggest over Tailscale              │   │
│  ├──────────────────────────────────────────────┤   │
│  │ 建议 Popup：3 条建议 → 点击复制剪贴板         │   │
│  └──────────────────────────────────────────────┘   │
└───────────────────────┬──────────────────────────────┘
                        │ Tailscale（节点分享，100.x.x.x:8000）
                        │ POST /suggest + X-API-Key header
┌───────────────────────▼──────────────────────────────┐
│                   用户电脑（Windows，常开）              │
│                                                      │
│  whatsapp-bridge.exe（lharries/whatsapp-mcp）         │
│  → 以伴侣设备连接 WhatsApp（初始用备用号）              │
│  → 实时同步消息到 messages.db（SQLite）               │
│  → 注册为 Windows 服务（NSSM）                        │
│                                                      │
│  Python MCP Server（stdio，Claude Code 配置）          │
│  → search_contacts, list_messages, list_chats        │
│                                                      │
│  suggest_server.py（Flask + waitress，port 8000）     │
│  → 验证 X-API-Key                                    │
│  → subprocess: claude -p + --allowedTools            │
│  → Claude Code 调用 whatsapp MCP 工具                │
│  → 返回 {"suggestions": ["...", "...", "..."]}       │
│                                                      │
│  Tailscale daemon（节点分享模式）                      │
└─────────────────────────────────────────────────────┘
```

### 2.2 技术选型

| 层 | 技术 | 理由 |
|---|---|---|
| WhatsApp 接入 | lharries/whatsapp-mcp（Whatsmeow/Go） | 5600+ stars，最成熟，中等封号风险 |
| AI 引擎 | `claude -p`（Claude Code Pro 订阅） | 无需单独 API Key |
| Android 联系人检测 | AccessibilityService（typeWindowStateChanged） | 100% 准确，低频触发 |
| Android 浮窗 | TYPE_ACCESSIBILITY_OVERLAY | 无需 SYSTEM_ALERT_WINDOW 额外权限 |
| Android HTTP | OkHttp + Kotlin Coroutines | 成熟，支持超时控制 |
| 网络隧道 | Tailscale 节点分享 | 朋友只见 PC，看不到其他设备 |
| PC 后端 | Flask + waitress | 轻量，单文件 |
| 进程管理 | NSSM（Windows 服务） | 自动重启，开机自启 |

---

## 3. Android 端设计

### 3.1 权限清单

```xml
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_SPECIAL_USE" />
<uses-permission android:name="android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS" />
android:allowBackup="false"
android:networkSecurityConfig="@xml/network_security_config"
```

### 3.2 AccessibilityService 配置

```xml
<!-- res/xml/accessibility_service_config.xml -->
<accessibility-service
    android:accessibilityEventTypes="typeWindowStateChanged|typeWindowContentChanged"
    android:packageNames="com.whatsapp,com.whatsapp.w4b"
    android:canRetrieveWindowContent="true"
    android:accessibilityFeedbackType="feedbackGeneric"
    android:accessibilityFlags="flagReportViewIds"
    android:description="@string/accessibility_description" />
```

**关键决策：**
- `typeWindowStateChanged` + `typeWindowContentChanged` 组合——捕获所有导航方式（Activity 切换 + Fragment 切换）
- `canRetrieveWindowContent="true"` 必须，否则无法查询节点
- `flagReportViewIds` 必须，否则 `getViewIdResourceName()` 返回 null

### 3.3 核心逻辑：WhatsAppContactWatcher

- OverlayManager 作为辅助类，在 AccessibilityService 上下文内实例化
- 点击浮窗按钮时，**实时**调用 `rootInActiveWindow.findAccessibilityNodeInfosByViewId()` 读联系人名，不使用缓存
- 资源 ID 从 SharedPreferences 读取（默认值 `com.whatsapp:id/conversation_contact_name`），支持远端更新
- 节点读取后必须调用 `recycle()`（API < 33 兼容性）
- 浮窗按钮仅当节点存在时显示（即用户在对话内）

**资源 ID 容错：**
```kotlin
val nodeId = prefs.getString("wa_node_id", "com.whatsapp:id/conversation_contact_name")
val nodes = root.findAccessibilityNodeInfosByViewId(nodeId)
// 回退：位置启发式（toolbar 内的 TextView）
```

### 3.4 网络层

```
OkHttp 配置：
  connectTimeout = 5s
  readTimeout = 90s
  
Threading：
  tap handler → coroutineScope.launch(Dispatchers.IO)
  响应处理 → withContext(Dispatchers.Main)
  popup 关闭时 → currentJob?.cancel()
  scope 用 SupervisorJob()
```

**Network Security Config（HTTP 白名单）：**
```xml
<!-- res/xml/network_security_config.xml -->
<network-security-config>
    <base-config cleartextTrafficPermitted="false" />
    <domain-config cleartextTrafficPermitted="true">
        <!-- Tailscale CGNAT 范围 100.64.0.0 - 100.127.255.255 -->
        <domain includeSubdomains="true">100.64.0.0</domain>
        <domain includeSubdomains="true">100.100.0.0</domain>
        <!-- 实际部署时替换为具体的 Tailscale IP，如 100.x.x.x -->
    </domain-config>
</network-security-config>
```

### 3.5 SetupWizard

```
Step 1：Accessibility 权限
  → 引导 Settings.ACTION_ACCESSIBILITY_SETTINGS
  → onResume() 检测 isAccessibilityServiceEnabled()，自动进下一步
  → 额外引导：关闭电池优化（REQUEST_IGNORE_BATTERY_OPTIMIZATIONS）
  → Android 13+ 需要先 "Allow restricted settings"（约11步，一次性）

Step 2：服务器配置
  → 输入服务器地址（Tailscale 100.x.x.x:8000）
  → 输入 API Key
  → GET /health 测试连通性

Step 3：完成
  → 使用说明
  → 说明 Android 13+ 复制时系统 toast 属正常现象
```

### 3.6 APK 分发

- 用专用 release keystore 签名并**备份 keystore 文件**
- 通过 WhatsApp/Telegram 发 APK，同 keystore 可直接覆盖安装
- 启动时 `GET /version` 检查更新，有新版弹提示
- `/version` 响应格式：`{"version": "1.0.0"}`，客户端对任何异常静默跳过

---

## 4. PC 后端设计

### 4.1 suggest_server.py

```python
import re, json, os, shutil, subprocess, threading
from flask import Flask, request, jsonify
from waitress import serve

app = Flask(__name__)
API_KEY = os.environ["SUGGEST_API_KEY"]
MCP_SERVER_NAME = os.environ.get("MCP_SERVER_NAME", "whatsapp")
CLAUDE_EXE = shutil.which("claude") or r"C:\Users\用户名\.local\bin\claude.exe"
APP_VERSION = "1.0.0"
_semaphore = threading.Semaphore(2)

def extract_suggestions(text):
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    data = json.loads(text)
    if isinstance(data, list):
        return [str(s) for s in data[:3]]
    if isinstance(data, dict) and "suggestions" in data:
        return data["suggestions"][:3]
    raise ValueError(f"Unexpected shape: {data}")

@app.post("/suggest")
def suggest():
    if request.headers.get("X-API-Key") != API_KEY:
        return jsonify({"error": "unauthorized"}), 401
    contact = request.json.get("contact", "").strip()
    if not contact or len(contact) > 100:
        return jsonify({"error": "invalid contact"}), 400
    if not _semaphore.acquire(blocking=False):   # 立即返回，不阻塞线程
        return jsonify({"error": "busy"}), 429
    try:
        prompt = (
            f'Use whatsapp-mcp tools to find the WhatsApp contact named "{contact}". '
            f'Call search_contacts with that name to get their JID. '
            f'If not found, try list_chats to find a matching chat. '
            f'Then call list_messages with the JID, limit=30. '
            f'If messages are empty, return ["消息同步中，请稍后重试", "", ""] '
            f'and stop. Otherwise suggest exactly 3 natural reply messages '
            f'in the same language as the conversation. '
            f'Return ONLY a JSON array of exactly 3 strings. No explanation, no markdown.'
        )
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            [CLAUDE_EXE, "-p", prompt,
             "--output-format", "json",
             "--allowedTools",
             f"mcp__{MCP_SERVER_NAME}__search_contacts,"
             f"mcp__{MCP_SERVER_NAME}__list_messages,"
             f"mcp__{MCP_SERVER_NAME}__list_chats"],
            capture_output=True, text=True,
            timeout=85, encoding="utf-8", env=env   # 85s < Android 90s
        )
        # stdout 是 JSONL（多行），找 type=result 那行
        output = None
        for line in result.stdout.strip().split('\n'):
            try:
                obj = json.loads(line)
                if obj.get("type") == "result":
                    output = obj
                    break
            except Exception:
                continue
        if output is None:
            return jsonify({"error": "no result from claude"}), 500
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
    import subprocess as sp
    ip = sp.run(["tailscale", "ip", "--4"],
                capture_output=True, text=True).stdout.strip() or "127.0.0.1"
    print(f"Serving on {ip}:8000")
    serve(app, host=ip, port=8000, threads=8)
```

### 4.2 Claude Code MCP 配置

在 `C:\Users\用户名\.claude\settings.json` 加入：
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

MCP server name = `"whatsapp"`，对应 `--allowedTools` 前缀 `mcp__whatsapp__*`。

### 4.3 NSSM 服务注册

```bat
:: 管理员 CMD 运行

:: WhatsApp Bridge
nssm install WhatsAppBridge "C:\whatsapp-mcp\whatsapp-bridge\whatsapp-bridge.exe"
nssm set WhatsAppBridge AppDirectory "C:\whatsapp-mcp\whatsapp-bridge"
nssm set WhatsAppBridge AppStdout "C:\whatsuggest\logs\bridge.log"
nssm set WhatsAppBridge AppStderr "C:\whatsuggest\logs\bridge-err.log"
nssm set WhatsAppBridge Start SERVICE_AUTO_START
nssm set WhatsAppBridge AppRestartDelay 5000

:: Suggest Server
nssm install SuggestServer python "C:\whatsuggest\suggest_server.py"
nssm set SuggestServer AppEnvironmentExtra "SUGGEST_API_KEY=your-secret"
nssm set SuggestServer AppEnvironmentExtra+ "MCP_SERVER_NAME=whatsapp"
nssm set SuggestServer AppStdout "C:\whatsuggest\logs\server.log"
nssm set SuggestServer AppStderr "C:\whatsuggest\logs\server-err.log"
nssm set SuggestServer DependOnService WhatsAppBridge
nssm set SuggestServer Start SERVICE_AUTO_START
nssm set SuggestServer AppRestartDelay 3000

nssm start WhatsAppBridge
nssm start SuggestServer
```

### 4.4 Windows 防火墙

```bat
:: 只允许 Tailscale IP 段（100.64.0.0/10）访问 8000 端口
netsh advfirewall firewall add rule ^
    name="WhatSuggest API Allow Tailscale" ^
    dir=in action=allow protocol=TCP ^
    localport=8000 remoteip=100.64.0.0/10

netsh advfirewall firewall add rule ^
    name="WhatSuggest API Block Others" ^
    dir=in action=block protocol=TCP localport=8000
```

---

## 5. 数据流与错误处理

### 5.1 正常请求流程

```
用户进入 WhatsApp 对话
  → AccessibilityService 检测 typeWindowStateChanged/ContentChanged
  → 读 com.whatsapp:id/conversation_contact_name
  → 浮窗按钮显示

用户点击浮窗按钮
  → 实时重读节点 → "Alice"
  → showLoading()
  → coroutine IO: POST /suggest {contact: "Alice"} X-API-Key: xxx

suggest_server.py
  → 验证 Key / 检查 contact / semaphore.acquire(blocking=False)
  → subprocess: claude -p [prompt] --allowedTools mcp__whatsapp__*
  → Claude: search_contacts("Alice") → JID → list_messages(JID,30) → 3条建议
  → is_error 检查 → extract_suggestions() → {"suggestions":[...]}

Android
  → Dispatchers.Main: hideLoading() → showCards()
  → 用户点卡片 → ClipboardManager.setPrimaryClip() → Toast "已复制"
```

### 5.2 完整错误矩阵

| 错误位置 | 错误类型 | HTTP | Android 显示 |
|---|---|---|---|
| Android | 节点为空（在聊天列表） | — | "请先打开一个对话" |
| Android | ConnectException | — | "无法连接，请检查 Tailscale" |
| Android | SocketTimeoutException（90s） | — | "响应超时，请重试" |
| Server | 401 | 401 | "认证失败，检查 API Key" |
| Server | Semaphore 满 | 429 | "服务繁忙，请稍等" |
| Server | claude timeout（85s） | 504 | "生成超时，请重试" |
| Server | is_error=true | 500 | "Claude 出错，请重试" |
| Server | JSON 解析失败 | 500 | "解析失败，请重试" |
| Server | 消息为空（sync 未完成） | 200* | "消息同步中，请几分钟后重试" |
| Server | 找不到联系人 | 500 | "找不到该联系人" |
| Server | Bridge session 失效 | 200* | "无法读取消息，请重启 bridge" |
| Server | WhatsApp 伴侣设备数已满 | 500 | "服务器错误，见日志" |

*消息为空时 Claude 仍返回 200，但 suggestions[0] 包含提示语。

### 5.3 超时层级

```
Android read timeout:    90s  （最外层）
subprocess timeout:      85s  （留 5s 给 server 返回错误）
claude 内部 API timeout: ~60s （Anthropic 控制）
```

---

## 6. 安装与分发

### 6.1 PC 端安装（一次性，约45分钟）

**前置依赖安装：**
```
1. Go 1.24+      → go.dev/dl
2. MSYS2 + GCC   → msys2.org
   → 安装后：pacman -S mingw-w64-ucrt-x86_64-gcc
   → 将 C:\msys64\ucrt64\bin 加入 PATH
3. go env -w CGO_ENABLED=1
4. Python 3.11+  → python.org
5. uv            → pip install uv
6. NSSM          → nssm.cc/download
7. Tailscale     → tailscale.com/download
```

**安装 whatsapp-mcp：**
```bat
git clone https://github.com/lharries/whatsapp-mcp C:\whatsapp-mcp
cd C:\whatsapp-mcp\whatsapp-bridge
set CGO_ENABLED=1
go build -o whatsapp-bridge.exe .     ← 预编译，不用 go run
```

**首次配对（必须在终端运行，不能通过 NSSM）：**
```bat
cd C:\whatsapp-mcp\whatsapp-bridge
.\whatsapp-bridge.exe
:: → 终端显示二维码，用手机 WhatsApp 扫描
:: → 等待消息同步完成（30分钟，看日志文件大小增长停止）
:: → Ctrl+C 停止，再通过 NSSM 启动服务
```

**配置 Claude Code MCP：**
```
编辑 C:\Users\用户名\.claude\settings.json
添加 "whatsapp" MCP server（见 Section 4.2）
```

**安装 Python 依赖 + 注册服务：**
```bat
pip install flask waitress
mkdir C:\whatsuggest\logs

:: 管理员 CMD
setx SUGGEST_API_KEY "your-random-secret" /M
:: 执行 NSSM 注册命令（见 Section 4.3）

:: 配置防火墙（见 Section 4.4）
```

**Tailscale 节点分享：**
```
Tailscale 管理后台 → Machines → 你的 PC → Share
→ 生成链接发给朋友
→ 朋友接受后可在其 Tailscale 中看到你的 PC（100.x.x.x）
```

### 6.2 Android 安装（朋友，约10分钟）

```
1. Play Store 安装 Tailscale → 点击你分享的邀请链接加入
2. 开启 Android Tailscale split tunnel：
   → 只路由 WhatSuggest app 的流量（节省电量）
3. 安装 APK → 允许未知来源
4. SetupWizard：
   a. Accessibility 权限（需先 Allow restricted settings，约11步）
   b. 关闭电池优化（可选但推荐）
   c. 输入服务器地址（100.x.x.x:8000）+ API Key → 测试连接
5. 完成
```

### 6.3 Session 失效恢复

```
症状：建议内容奇怪或提示"无法读取消息"

恢复步骤：
1. Services → 停止 WhatsAppBridge 服务
2. 删除 C:\whatsapp-mcp\whatsapp-bridge\store\ 内的 .db 文件
3. 终端手动运行：.\whatsapp-bridge.exe（显示二维码）
4. 手机 WhatsApp 扫码
5. 等待重新同步（30分钟）
6. 停止手动运行，Services → 启动 WhatsAppBridge
```

### 6.4 APK 更新分发

```
1. 用固定 release keystore 签名（备份 keystore 到安全位置）
2. 构建新版本 APK，递增 versionCode
3. 发 APK 给朋友（WhatsApp/Telegram）
4. 朋友直接安装覆盖（同 keystore，设置保留）
```

---

## 7. 未来扩展路径

| 功能 | 说明 |
|---|---|
| 云端迁移 | 将 whatsapp-bridge 和 suggest_server 部署到 VPS，Android 改用 HTTPS 域名，去掉 Tailscale |
| 主号切换 | 备用号验证稳定后，重新扫码配对主号 |
| 多语言 prompt | 在 server 端检测联系人消息语言，优化 prompt |
| Webhook 触发 | 配置 whatsapp-mcp webhook，收到新消息自动推送建议（需要 ntfy.sh 等推送服务） |

---

## 8. 已知风险

| 风险 | 严重程度 | 缓解方案 |
|---|---|---|
| WhatsApp 封号（Whatsmeow 协议指纹） | 中 | 先用备用号测试；只读不发消息降低行为信号 |
| WhatsApp 更新导致 contact_name 节点 ID 变化 | 中 | 远端配置节点 ID，app 启动时拉取最新值 |
| `claude -p` 在 Pro 订阅下 60s timeout bug | 中 | 监控 issue #20527；如触发可切换到 API Key |
| Android 15 Enhanced Confirmation Mode 阻断权限 | 低 | 目前未大规模部署；SetupWizard 有引导 |
| bridge session 失效（约20天不活跃） | 中 | 文档化恢复流程（Section 6.3） |
