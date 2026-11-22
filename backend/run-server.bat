@echo off
:: Foreground run, for checking the server before installing the Windows service.
set "ROOT=%~dp0"
if "%SUGGEST_API_KEY%"=="" (
    echo Set SUGGEST_API_KEY in this window first. Do not put the key in config.yaml.
    echo 先在这个窗口设置 SUGGEST_API_KEY。不要把密钥写进 config.yaml。
    exit /b 1
)
if not exist "%ROOT%config.yaml" (
    echo Missing %ROOT%config.yaml
    echo Copy config.example.yaml to config.yaml and edit the database path.
    exit /b 1
)
set "SUGGEST_CONFIG=%ROOT%config.yaml"
cd /d "%ROOT%"
python -m whatsuggest
