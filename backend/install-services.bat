@echo off
:: Run this as Administrator.
:: Edit the variables below before running. Re-running removes and recreates the services.

set "ROOT=%~dp0"
set "BRIDGE_EXE=C:\whatsapp-mcp\whatsapp-bridge\whatsapp-bridge.exe"
set "BRIDGE_DIR=C:\whatsapp-mcp\whatsapp-bridge"
:: Use the full path to python.exe if the service cannot see `python` on PATH.
:: 如果服务里找不到 python，把下面改成 python.exe 的完整路径。
set "PYTHON_EXE=python"
set "API_KEY=REPLACE_WITH_YOUR_SECRET"
set "CONFIG=%ROOT%config.yaml"

if "%API_KEY%"=="REPLACE_WITH_YOUR_SECRET" (
    echo Edit API_KEY in this script before running.
    echo 先把脚本里的 API_KEY 改成你自己的密钥，再运行。
    exit /b 1
)

if not exist "%CONFIG%" (
    echo Missing %CONFIG%
    echo Copy config.example.yaml to config.yaml and edit it first.
    echo 先把 config.example.yaml 复制成 config.yaml 并改好数据库路径。
    exit /b 1
)

mkdir "%ROOT%logs" 2>nul

echo Removing previous services if they exist...
nssm stop SuggestServer >nul 2>&1
nssm remove SuggestServer confirm >nul 2>&1
nssm stop WhatsAppBridge >nul 2>&1
nssm remove WhatsAppBridge confirm >nul 2>&1

echo Installing WhatsApp bridge...
nssm install WhatsAppBridge "%BRIDGE_EXE%"
nssm set WhatsAppBridge AppDirectory "%BRIDGE_DIR%"
nssm set WhatsAppBridge AppStdout "%ROOT%logs\bridge.log"
nssm set WhatsAppBridge AppStderr "%ROOT%logs\bridge-err.log"
nssm set WhatsAppBridge Start SERVICE_AUTO_START
nssm set WhatsAppBridge AppRestartDelay 5000

echo Installing suggestion server...
nssm install SuggestServer "%PYTHON_EXE%"
nssm set SuggestServer AppDirectory "%ROOT%"
nssm set SuggestServer AppParameters "-m whatsuggest"
nssm set SuggestServer AppEnvironmentExtra "SUGGEST_API_KEY=%API_KEY%"
nssm set SuggestServer AppEnvironmentExtra+ "SUGGEST_CONFIG=%CONFIG%"
nssm set SuggestServer AppStdout "%ROOT%logs\server.log"
nssm set SuggestServer AppStderr "%ROOT%logs\server-err.log"
nssm set SuggestServer DependOnService WhatsAppBridge
nssm set SuggestServer Start SERVICE_AUTO_START
nssm set SuggestServer AppRestartDelay 3000

echo Starting services...
nssm start WhatsAppBridge
timeout /t 5 /nobreak
nssm start SuggestServer

echo Done. Logs: %ROOT%logs\
echo The server binds to the Tailscale IPv4 from `tailscale ip --4` unless config.yaml sets server.host.
