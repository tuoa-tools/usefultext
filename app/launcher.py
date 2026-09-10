"""Desktop entry point: start the server on a free localhost port and open the browser.

Security model for a local app: the API only answers requests carrying this launch's secret,
delivered once via /launch?token=... which sets an HttpOnly SameSite=Strict cookie. Other
websites can't send that cookie, and CORS blocks them from reading anything anyway.

Copied from media_downloader; the pywebview window (PLAN_M2.md step 5) wraps this later.
"""

from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import os
import secrets
import socket
import sys
import threading
import urllib.request
import webbrowser
from pathlib import Path

from app.paths import data_dir

log = logging.getLogger(__name__)
INSTANCE_FILE = "instance.json"


def setup_logging(folder: Path) -> None:
    """A windowed app has no console; everything goes to app.log (rotated)."""
    handler = logging.handlers.RotatingFileHandler(
        folder / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    if sys.stderr is not None and sys.stderr.fileno() >= 0:  # a real terminal: mirror there too
        root.addHandler(logging.StreamHandler())


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def running_instance(folder: Path) -> dict | None:
    """The {port, token} of an already-running copy, if its health endpoint answers."""
    path = folder / INSTANCE_FILE
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
        with urllib.request.urlopen(
            f"http://127.0.0.1:{info['port']}/api/health", timeout=1.5
        ) as response:
            health = json.load(response)
        if health.get("desktop"):
            return info
    except Exception:  # noqa: BLE001 - no file, stale file, nothing listening
        pass
    return None


def write_instance(folder: Path, port: int, token: str) -> Path:
    path = folder / INSTANCE_FILE
    path.write_text(
        json.dumps({"port": port, "token": token, "pid": os.getpid()}), encoding="utf-8"
    )
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def launch_url(port: int, token: str) -> str:
    return f"http://127.0.0.1:{port}/launch?token={token}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="UsefulText")
    parser.add_argument("--port", type=int, default=0, help="listen port (default: any free one)")
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    args = parser.parse_args(argv)

    if sys.stdout is None or sys.stderr is None:  # pythonw.exe / windowed app: no console streams
        sys.stdout = sys.stdout or open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
        sys.stderr = sys.stderr or open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    folder = data_dir()
    setup_logging(folder)

    existing = running_instance(folder)
    if existing:
        log.info("already running on port %s - opening it", existing["port"])
        if not args.no_browser:
            webbrowser.open(launch_url(existing["port"], existing["token"]))
        return 0

    port = args.port or free_port()
    token = secrets.token_urlsafe(32)
    os.environ["USEFULTEXT_TOKEN"] = token
    os.environ["USEFULTEXT_DESKTOP"] = "1"
    os.environ["USEFULTEXT_CORS_ORIGINS"] = f"http://127.0.0.1:{port}"

    import uvicorn

    from app.main import app  # after the environment is set

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None, log_level="info")
    server = uvicorn.Server(config)
    app.state.on_quit = lambda: setattr(server, "should_exit", True)
    instance = write_instance(folder, port, token)
    log.info("UsefulText starting on http://127.0.0.1:%s", port)

    if not args.no_browser:

        def open_when_ready() -> None:
            while not server.started:
                threading.Event().wait(0.1)
            webbrowser.open(launch_url(port, token))

        threading.Thread(target=open_when_ready, daemon=True).start()

    try:
        server.run()
    finally:
        instance.unlink(missing_ok=True)
        log.info("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
