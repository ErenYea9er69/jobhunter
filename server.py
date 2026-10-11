#!/usr/bin/env python3
"""JobHunter entry point.
Run headless server: python server.py
Run desktop app:     python desktop.py (or python server.py --desktop)
"""
import sys

if __name__ == "__main__":
    if "--desktop" in sys.argv:
        from desktop import main
        main()
    else:
        from jh.httpd import run
        run()
