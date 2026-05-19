@echo off
:: Run this as Administrator

mkdir D:\cc\whatsuggest\backend\logs 2>nul

:: === WhatsApp Bridge ===
nssm install WhatsAppBridge "C:\whatsapp-mcp\whatsapp-bridge\whatsapp-bridge.exe"
nssm set WhatsAppBridge AppDirectory "C:\whatsapp-mcp\whatsapp-bridge"
nssm set WhatsAppBridge AppStdout "D:\cc\whatsuggest\backend\logs\bridge.log"
nssm set WhatsAppBridge AppStderr "D:\cc\whatsuggest\backend\logs\bridge-err.log"
nssm set WhatsAppBridge Start SERVICE_AUTO_START
nssm set WhatsAppBridge AppRestartDelay 5000

:: === Suggest Server ===
nssm install SuggestServer python "D:\cc\whatsuggest\backend\suggest_server.py"
nssm set SuggestServer AppDirectory "D:\cc\whatsuggest\backend"
nssm set SuggestServer AppEnvironmentExtra "SUGGEST_API_KEY=REPLACE_WITH_YOUR_SECRET"
nssm set SuggestServer AppEnvironmentExtra+ "MCP_SERVER_NAME=whatsapp"
nssm set SuggestServer AppStdout "D:\cc\whatsuggest\backend\logs\server.log"
nssm set SuggestServer AppStderr "D:\cc\whatsuggest\backend\logs\server-err.log"
nssm set SuggestServer DependOnService WhatsAppBridge
nssm set SuggestServer Start SERVICE_AUTO_START
nssm set SuggestServer AppRestartDelay 3000

echo Starting services...
nssm start WhatsAppBridge
timeout /t 5 /nobreak
nssm start SuggestServer

echo Done. Check logs at D:\cc\whatsuggest\backend\logs\
