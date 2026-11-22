"""Backward-compatible entry point.

Windows services that still launch ``python suggest_server.py`` land here.
The implementation lives in the ``whatsuggest`` package.
"""

from whatsuggest.__main__ import main

if __name__ == "__main__":
    main()
