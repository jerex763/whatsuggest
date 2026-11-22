@echo off
:: Run as Administrator.
:: Allow the Tailscale range 100.64.0.0/10 to reach the suggestion port, and block everyone else.
set "PORT=8000"

netsh advfirewall firewall delete rule name="WhatSuggest Allow Tailscale" >nul 2>&1
netsh advfirewall firewall delete rule name="WhatSuggest Block Others" >nul 2>&1
netsh advfirewall firewall delete rule name="WhatSuggest API Allow Tailscale" >nul 2>&1
netsh advfirewall firewall delete rule name="WhatSuggest API Block Others" >nul 2>&1

netsh advfirewall firewall add rule ^
    name="WhatSuggest Allow Tailscale" ^
    dir=in action=allow protocol=TCP ^
    localport=%PORT% remoteip=100.64.0.0/10

netsh advfirewall firewall add rule ^
    name="WhatSuggest Block Others" ^
    dir=in action=block protocol=TCP localport=%PORT%

echo Firewall rules added for TCP %PORT%.
echo Only Tailscale addresses (100.64.0.0/10) can connect.
