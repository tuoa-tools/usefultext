"""App-level settings: where the library is, and the pipeline defaults a
person can change. Stored as settings.json in the app-data folder
(paths.data_dir()); per-document overrides live in each job.json."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

SETTINGS_FILE = "settings.json"
ADD_MODES = ("copy", "move")


@dataclass
class AppConfig:
    library_dir: str | None = None  # chosen on first start; None = first run
    add_mode: str = "copy"  # what "add from a folder" does with the originals
    pdf_dpi: int = 200
    min_page_conf: float = 0.70
    blur_threshold: float = 65.0

    def pipeline_overrides(self) -> dict:
        """The subset that maps onto usefultext.Settings."""
        return {
            "pdf_dpi": self.pdf_dpi,
            "min_page_conf": self.min_page_conf,
            "blur_threshold": self.blur_threshold,
        }

    @classmethod
    def load(cls, folder: Path) -> AppConfig:
        p = Path(folder) / SETTINGS_FILE
        if not p.exists():
            return cls()
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            known = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
            return cls(**known)
        except Exception:
            return cls()

    def save(self, folder: Path) -> None:
        p = Path(folder) / SETTINGS_FILE
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=1), encoding="utf-8")
        os.replace(tmp, p)
