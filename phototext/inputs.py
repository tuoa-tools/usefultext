"""Finding input files and putting them in page order.

Order rules (brief): natural sort by filename (img2 < img10) by default;
fall back to EXIF DateTimeOriginal (then file mtime) when the names are
unhelpful — random UUID/hash exports, or names with no numbers at all.
PDFs expand to one PageSource per page, in document order.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from PIL import Image

from .preprocess import SUPPORTED_EXTS, SUPPORTED_PDF_EXTS

SORT_MODES = ("auto", "name", "time", "printed")


@dataclass(frozen=True)
class PageSource:
    """One page to read: an image file, or one page of a PDF."""
    path: Path
    page_index: int = 0     # 0-based page within a PDF; 0 for images
    n_pages: int = 1

    @property
    def is_pdf(self) -> bool:
        return self.path.suffix.lower() in SUPPORTED_PDF_EXTS

    @property
    def key(self) -> str:
        return f"{self.path.resolve()}::{self.page_index}"

    @property
    def label(self) -> str:
        if self.is_pdf and self.n_pages > 1:
            return f"{self.path.name}#p{self.page_index + 1}"
        return self.path.name


# --------------------------------------------------------------------------- #
# Ordering
# --------------------------------------------------------------------------- #
_NUM = re.compile(r"(\d+)")
_HEXISH = re.compile(r"^[0-9a-f]{8,}([-_][0-9a-f]{4,})*$", re.IGNORECASE)


def natural_key(name: str) -> list:
    """'page_10' sorts after 'page_9', not after 'page_1'."""
    return [int(tok) if tok.isdigit() else tok.lower() for tok in _NUM.split(name)]


def name_looks_unhelpful(stem: str) -> bool:
    """UUID/hash-style names, or names without any number, carry no order."""
    s = stem.strip()
    if not any(ch.isdigit() for ch in s):
        return True
    return bool(_HEXISH.match(s))


def exif_datetime(path: Path) -> datetime | None:
    try:
        with Image.open(path) as im:
            exif = im.getexif()
            ifd = exif.get_ifd(0x8769)
            raw = ifd.get(36867) or exif.get(306)      # DateTimeOriginal, else DateTime
            if not raw:
                return None
            dt = datetime.strptime(str(raw).strip(), "%Y:%m:%d %H:%M:%S")
            subsec = str(ifd.get(37521) or "").strip()  # SubSecTimeOriginal
            if subsec.isdigit():
                dt = dt.replace(microsecond=int(subsec.ljust(6, "0")[:6]))
            return dt
    except Exception:
        return None


def file_time(path: Path) -> datetime:
    return exif_datetime(path) or datetime.fromtimestamp(path.stat().st_mtime)


def order_files(files: Iterable[Path], mode: str = "auto") -> tuple[list[Path], str]:
    """Return (ordered files, mode actually used)."""
    files = list(files)
    if mode not in SORT_MODES:
        raise ValueError(f"sort must be one of {SORT_MODES}, got {mode!r}")
    if mode == "printed":       # printed numbers are only known after OCR; start from auto
        mode = "auto"
    if mode == "auto":
        unhelpful = sum(name_looks_unhelpful(f.stem) for f in files)
        mode = "time" if len(files) > 1 and unhelpful * 2 >= len(files) else "name"
    if mode == "time":
        ordered = sorted(files, key=lambda f: (file_time(f), natural_key(f.name)))
    else:
        ordered = sorted(files, key=lambda f: natural_key(f.name))
    return ordered, mode


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
def discover_files(inputs: Iterable[str | Path], recursive: bool = False) -> list[Path]:
    """Collect supported files from files/folders. Unordered, de-duplicated."""
    seen: dict[Path, None] = {}
    for raw in inputs:
        p = Path(raw)
        if p.is_dir():
            it = p.rglob("*") if recursive else p.iterdir()
            for f in it:
                if f.is_file() and f.suffix.lower() in SUPPORTED_EXTS and not f.name.startswith("."):
                    seen.setdefault(f.resolve(), None)
        elif p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
            seen.setdefault(p.resolve(), None)
    return list(seen)


def pdf_page_count(path: Path) -> int:
    import pymupdf
    with pymupdf.open(path) as doc:
        return doc.page_count


def expand_sources(files: Iterable[Path]) -> list[PageSource]:
    sources: list[PageSource] = []
    for f in files:
        if f.suffix.lower() in SUPPORTED_PDF_EXTS:
            n = pdf_page_count(f)
            sources.extend(PageSource(f, i, n) for i in range(n))
        else:
            sources.append(PageSource(f))
    return sources


def discover_sources(inputs: Iterable[str | Path], sort: str = "auto",
                     recursive: bool = False) -> tuple[list[PageSource], str]:
    """Files/folders → ordered list of pages, plus the sort mode used."""
    files = discover_files(inputs, recursive)
    ordered, mode = order_files(files, sort)
    return expand_sources(ordered), mode
