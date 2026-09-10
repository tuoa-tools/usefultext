"""App-level settings: where the library is, and the pipeline defaults a
person can change. Stored as settings.json in the app-data folder
(paths.data_dir()); per-document overrides live in each job.json."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from usefultext.fileio import read_text, write_text

SETTINGS_FILE = "settings.json"
ADD_MODES = ("copy", "move")


@dataclass
class AppConfig:
    library_dir: str | None = None  # chosen on first start; None = first run
    add_mode: str = "copy"  # what "add from a folder" does with the originals
    pdf_dpi: int = 200
    min_page_conf: float = 0.70
    blur_threshold: float = 65.0
    columns: str = "auto"  # auto = split a page at a clear gutter; "1" = always one column

    def pipeline_overrides(self) -> dict:
        """The subset that maps onto usefultext.Settings."""
        return {
            "pdf_dpi": self.pdf_dpi,
            "min_page_conf": self.min_page_conf,
            "blur_threshold": self.blur_threshold,
            "columns": self.columns,
        }

    @classmethod
    def load(cls, folder: Path) -> AppConfig:
        text = read_text(Path(folder) / SETTINGS_FILE)
        if text is None:
            return cls()
        try:
            raw = json.loads(text)
            known = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
            return cls(**known)
        except Exception:
            return cls()

    def save(self, folder: Path) -> None:
        write_text(Path(folder) / SETTINGS_FILE, json.dumps(asdict(self), indent=1))
