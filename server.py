#!/usr/bin/env python3
"""JobHunter Detached Web Server & Daemon Worker (V3).

Runs independently of the MCP process or agent console session.
Serves the web UI and REST API on 127.0.0.1:PORT.
Manages PID and lock files in jobmcp/run.
"""
from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jh import config, db, httpd, util

RUN_DIR = ROOT / "jobmcp" / "run"


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="JobHunter Detached HTTP Daemon")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind (default: 8080)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--ws-dir", type=str, default="", help="Workspace directory")
    return parser.parse_args(args)


def write_pid_and_lock(port: int) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    pid = os.getpid()
    pid_file = RUN_DIR / "server.pid"
    lock_file = RUN_DIR / "server.lock"
    port_file = RUN_DIR / "server.port"

    pid_file.write_text(str(pid), encoding="utf-8")
    lock_file.write_text(f"pid={pid}\ntime={time.time()}\nport={port}\n", encoding="utf-8")
    port_file.write_text(str(port), encoding="utf-8")


def clean_pid_and_lock() -> None:
    try:
        (RUN_DIR / "server.pid").unlink(missing_ok=True)
        (RUN_DIR / "server.lock").unlink(missing_ok=True)
        (RUN_DIR / "server.port").unlink(missing_ok=True)
    except Exception:
        pass


def main() -> None:
    args = parse_args()
    ws_dir = Path(args.ws_dir).resolve() if args.ws_dir else ROOT
    
    # Configure paths
    config.WORKSPACE_DIR = str(ws_dir)
    config.configure_mcp_environment(str(ws_dir))
    db.init_db()

    write_pid_and_lock(args.port)

    sys.stderr.write(f"[server.py] Starting JobHunter HTTP daemon on http://{args.host}:{args.port} (PID: {os.getpid()})\n")
    sys.stderr.flush()

    server = httpd.start_server(host=args.host, port=args.port, ws_dir=ws_dir)

    def shutdown_handler(signum, frame):
        sys.stderr.write(f"\n[server.py] Received signal {signum}. Shutting down...\n")
        try:
            server.shutdown()
            server.server_close()
        except Exception:
            pass
        clean_pid_and_lock()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    try:
        signal.signal(signal.SIGTERM, shutdown_handler)
    except (AttributeError, ValueError):
        pass

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown_handler(signal.SIGINT, None)


if __name__ == "__main__":
    main()
