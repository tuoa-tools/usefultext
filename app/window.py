"""The desktop window: pywebview (WKWebView on macOS, WebView2 on Windows,
WebKitGTK on Linux) around the launch URL. When pywebview or its engine is
missing the launcher falls back to a browser tab.

The window is also where native dialogs come from: the page calls
`window.pywebview.api.pick_folder()` and gets a path back, which is how
"move into the library" becomes a dialog rather than a typed path.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

TITLE = "UsefulText"
SIZE = (1280, 860)
MIN_SIZE = (900, 600)
FILE_TYPES = ("Photos and PDFs (*.jpg;*.jpeg;*.png;*.heic;*.heif;*.tif;*.tiff;*.bmp;*.webp;*.pdf)",)


def available() -> bool:
    """pywebview can be imported (its engine is only proved by starting it)."""
    try:
        import webview  # noqa: F401
    except Exception:  # noqa: BLE001 - not installed, or its platform bridge is missing
        return False
    return True


def first_path(chosen) -> str | None:
    """pywebview returns a tuple of paths, a single path, or None."""
    if not chosen:
        return None
    if isinstance(chosen, (list, tuple)):
        return str(chosen[0]) if chosen else None
    return str(chosen)


class Bridge:
    """What the page can call through window.pywebview.api."""

    def __init__(self) -> None:
        self.window = None

    def pick_folder(self) -> str | None:
        import webview

        return first_path(self.window.create_file_dialog(webview.FOLDER_DIALOG))

    def pick_files(self) -> list[str]:
        import webview

        chosen = self.window.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=True, file_types=FILE_TYPES
        )
        return [str(p) for p in (chosen or [])]


class DesktopWindow:
    """One window around the app. `open()` runs the GUI loop on the calling
    (main) thread and returns when the window closes; `close()` may be
    called from any thread (the API's quit)."""

    def __init__(self, url: str, storage_dir: Path) -> None:
        self.url = url
        self.storage_dir = Path(storage_dir)
        self.window = None
        self.bridge = Bridge()

    def open(self) -> bool:
        try:
            import webview
        except Exception as exc:  # noqa: BLE001
            log.warning("no desktop window (%s); using the browser instead", exc)
            return False
        webview.settings["ALLOW_DOWNLOADS"] = True  # the Export buttons save files
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.window = webview.create_window(
                TITLE,
                self.url,
                js_api=self.bridge,
                width=SIZE[0],
                height=SIZE[1],
                min_size=MIN_SIZE,
                text_select=True,
            )
            self.bridge.window = self.window
            # Not private: the page's own choices (zoom, presets) survive a restart.
            webview.start(private_mode=False, storage_path=str(self.storage_dir))
        except Exception as exc:  # noqa: BLE001 - no GUI engine on this machine
            log.warning("the desktop window could not start (%s); using the browser instead", exc)
            self.window = None
            return False
        return True

    def close(self) -> None:
        window, self.window = self.window, None
        if window is not None:
            try:
                window.destroy()
            except Exception:  # noqa: BLE001 - already closing
                pass
