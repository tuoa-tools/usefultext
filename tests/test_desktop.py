"""Desktop mode: the launcher's helpers, the window's bridge, idle shutdown and quit."""

import json
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import launcher, window
from app import main as main_module
from usefultext import ocr


def test_launcher_helpers(tmp_path):
    port = launcher.free_port()
    assert 1024 < port < 65536
    assert launcher.running_instance(tmp_path) is None  # no file
    path = launcher.write_instance(tmp_path, 8123, "tok")
    assert json.loads(path.read_text(encoding="utf-8"))["port"] == 8123
    assert launcher.running_instance(tmp_path) is None  # a file, but nothing listening
    assert launcher.launch_url(8123, "tok") == "http://127.0.0.1:8123/launch?token=tok"


def test_wait_until_started_gives_up_when_the_server_dies():
    server = SimpleNamespace(started=False)
    dead = SimpleNamespace(is_alive=lambda: False)
    assert launcher.wait_until_started(server, dead, timeout=1.0) is False
    server.started = True
    assert launcher.wait_until_started(server, dead, timeout=1.0) is True


def test_window_bridge_returns_paths_from_the_dialogs():
    assert isinstance(window.available(), bool)
    assert window.first_path(None) is None
    assert window.first_path(()) is None
    assert window.first_path(("/a/b",)) == "/a/b"
    assert window.first_path("/lone") == "/lone"
    bridge = window.Bridge()
    bridge.window = SimpleNamespace(create_file_dialog=lambda *a, **k: ("/pick/one", "/pick/two"))
    if window.available():
        assert bridge.pick_folder() == "/pick/one"
        assert bridge.pick_files() == ["/pick/one", "/pick/two"]
    closed = []
    win = window.DesktopWindow("http://127.0.0.1:1/launch", "/nowhere")
    win.window = SimpleNamespace(destroy=lambda: closed.append(True))
    win.close()
    win.close()  # idempotent
    assert closed == [True] and win.window is None


def test_idle_expired_needs_desktop_tab_silence_and_no_job():
    now = 1000.0
    state = SimpleNamespace(
        desktop=True, idle_shutdown=True, last_ping=now - 200, worker=SimpleNamespace(progress={})
    )
    assert main_module.idle_expired(state, now) is True
    assert main_module.idle_expired(state, state.last_ping + 60) is False  # pinged a minute ago
    state.worker.progress = {"doc": object()}  # a document is being read
    assert main_module.idle_expired(state, now) is False
    state.worker.progress = {}
    state.idle_shutdown = False  # the window is the UI: closing it quits instead
    assert main_module.idle_expired(state, now) is False
    state.idle_shutdown, state.desktop = True, False  # a dev server never exits by itself
    assert main_module.idle_expired(state, now) is False


def test_health_is_the_keep_alive_and_quit_calls_the_launcher(tmp_path, monkeypatch):
    monkeypatch.setenv("USEFULTEXT_DATA_DIR", str(tmp_path / "appdata"))
    monkeypatch.setenv("USEFULTEXT_TOKEN", "secret")
    monkeypatch.setenv("USEFULTEXT_DESKTOP", "1")
    monkeypatch.setattr(ocr, "available", lambda: True)
    quits = []
    main_module.app.state.on_quit = lambda: quits.append(True)
    try:
        with TestClient(main_module.app) as c:
            state = main_module.app.state
            state.last_ping = time.monotonic() - 500
            assert c.get("/api/health").json()["desktop"] is True
            assert time.monotonic() - state.last_ping < 5  # the ping was recorded
            c.get("/launch", params={"token": "secret"}, follow_redirects=False)
            assert c.post("/api/quit").json() == {"ok": True}
            assert quits == [True]
            assert c.get("/api/health").json()["quit_requested"] is True
    finally:
        main_module.app.state.on_quit = None


def test_quit_is_refused_outside_desktop_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("USEFULTEXT_DATA_DIR", str(tmp_path / "appdata"))
    monkeypatch.delenv("USEFULTEXT_TOKEN", raising=False)
    monkeypatch.delenv("USEFULTEXT_DESKTOP", raising=False)
    monkeypatch.setattr(ocr, "available", lambda: True)
    with TestClient(main_module.app) as c:
        assert c.post("/api/quit").status_code == 400
        assert c.get("/api/health").json()["desktop"] is False
