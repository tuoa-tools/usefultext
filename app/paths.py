"""Where the app keeps its own data, and where a library goes by default."""

from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_data_dir, user_documents_dir

APP_NAME = "UsefulText"


def data_dir() -> Path:
    """Per-user app data: settings.json, app.log, instance.json.
    Override with USEFULTEXT_DATA_DIR (tests, portable use)."""
    path = Path(os.environ.get("USEFULTEXT_DATA_DIR") or user_data_dir(APP_NAME, appauthor=False))
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_library_dir() -> Path:
    """What the first-run picker is pre-filled with. Nothing is created until
    the user confirms it; the library is theirs to place."""
    return Path(user_documents_dir()) / APP_NAME
