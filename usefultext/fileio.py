"""Atomic file writes that survive Windows.

Every file the pipeline and the app write goes to `<name>.tmp` first and is
then swapped into place, so a reader never sees a half-written file. On
Windows the swap is refused ("access is denied", "sharing violation") while
any other handle has the destination open — the app reading it, an editor,
a sync client, the antivirus — and such handles are held for milliseconds,
so the swap is retried for a moment before giving up. Reads get the same
courtesy for a file that is being swapped at that instant.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

RETRY_SECONDS = 3.0
_FIRST_DELAY = 0.01
_MAX_DELAY = 0.2


def tmp_path(path: Path | str) -> Path:
    path = Path(path)
    return path.with_name(path.name + ".tmp")


def replace(tmp: Path | str, path: Path | str, retry_seconds: float = RETRY_SECONDS) -> None:
    """os.replace, retried while Windows refuses it because the destination is open."""
    deadline = time.monotonic() + retry_seconds
    delay = _FIRST_DELAY
    while True:
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(delay)
            delay = min(delay * 2, _MAX_DELAY)


def write_text(path: Path | str, text: str) -> None:
    tmp = tmp_path(path)
    tmp.write_text(text, encoding="utf-8")
    replace(tmp, path)


def write_bytes(path: Path | str, data: bytes) -> None:
    tmp = tmp_path(path)
    tmp.write_bytes(data)
    replace(tmp, path)


def read_text(path: Path | str, retry_seconds: float = RETRY_SECONDS) -> str | None:
    """The file's text as UTF-8, or None when there is no such file. A read
    refused while the file is being swapped into place is retried for a moment."""
    deadline = time.monotonic() + retry_seconds
    delay = _FIRST_DELAY
    while True:
        try:
            return Path(path).read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(delay)
            delay = min(delay * 2, _MAX_DELAY)
