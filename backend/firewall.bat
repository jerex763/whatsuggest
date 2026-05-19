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
