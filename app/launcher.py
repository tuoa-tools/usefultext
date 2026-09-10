"""Desktop entry point: start the server on a free localhost port and show the app —
in its own window (pywebview) when that works, otherwise in a browser tab.

Security model for a local app: the API only answers requests carrying this launch's secret,
delivered once via /launch?token=... which sets an HttpOnly SameSite=Strict cookie. Other
websites can't send that cookie, and CORS blocks them from reading anything anyway.

Shutdown: closing the window quits. With a browser tab there is no window to close, so
the server exits by itself once the page has stopped pinging /api/health for two minutes
and no document is being read (app.main's idle watch). /api/quit does both.

The launcher, token and single-instance parts are media_downloader's; the window is ours.
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
import time
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


def bundled_models_dir() -> Path | None:
    """Where a packaged app keeps the OCR models: `models/` inside a PyInstaller
    bundle, or beside the `app` package in the Windows layout (Lib/site-packages/models).
    None in a development install, where the rapidocr wheel's own models are used."""
    candidates = []
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / "models")
    candidates.append(Path(__file__).resolve().parents[1] / "models")
    for folder in candidates:
        if (folder / "PP-OCRv6_det_small.onnx").exists():
            return folder
    return None


def point_at_bundled_models() -> None:
    """Packaged builds ship three models (scripts/prepare_bundle.py) rather than the
    rapidocr wheel's 260 MB; tell the engine where they are unless the person did."""
    if os.environ.get("USEFULTEXT_MODEL_DIR"):
        return
    folder = bundled_models_dir()
    if folder is not None:
        os.environ["USEFULTEXT_MODEL_DIR"] = str(folder)


def wait_until_started(server, thread: threading.Thread, timeout: float = 30.0) -> bool:
    """True once uvicorn is accepting connections; False if it died or timed out."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if server.started:
            return True
        if not thread.is_alive():
            return False
        time.sleep(0.05)
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="UsefulText")
    parser.add_argument("--port", type=int, default=0, help="listen port (default: any free one)")
    parser.add_argument(
        "--browser", action="store_true", help="open a browser tab instead of the app's window"
    )
    parser.add_argument(
        "--window",
        action="store_true",
        help="open the app's own window even on Windows (the default elsewhere; on Windows the "
        "WebView2 bridge misbehaved on a real machine, so a browser tab is the default there)",
    )
    parser.add_argument(
        "--no-browser", action="store_true", help="only run the server; open nothing"
    )
    args = parser.parse_args(argv)

    if sys.stdout is None or sys.stderr is None:  # pythonw.exe / windowed app: no console streams
        sys.stdout = sys.stdout or open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
        sys.stderr = sys.stderr or open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    folder = data_dir()
    setup_logging(folder)
    point_at_bundled_models()

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

    from app import window
    from app.main import app  # after the environment is set

    url = launch_url(port, token)
    use_window = (
        not args.browser
        and not args.no_browser
        and window.available()
        and (sys.platform != "win32" or args.window)
    )
    win = window.DesktopWindow(url, folder / "webview", token) if use_window else None

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None, log_level="info")
    server = uvicorn.Server(config)

    def quit_all() -> None:
        server.should_exit = True
        if win is not None:
            win.close()

    app.state.on_quit = quit_all
    # A browser tab can be closed without telling us; the window cannot.
    app.state.idle_shutdown = win is None and not args.no_browser
    instance = write_instance(folder, port, token)
    log.info("UsefulText %s starting on http://127.0.0.1:%s", app.version, port)

    thread = threading.Thread(target=server.run, name="usefultext-server", daemon=True)
    thread.start()
    try:
        if not wait_until_started(server, thread):
            log.error("the server did not start; see app.log")
            return 1
        if win is not None and win.open():  # the window's loop runs here until it closes
            log.info("window closed")
        else:
            if win is not None:  # the window could not start: the tab it is, with idle shutdown
                app.state.idle_shutdown = True
            if not args.no_browser:
                webbrowser.open(url)
            while thread.is_alive():
                thread.join(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        instance.unlink(missing_ok=True)
        log.info("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
