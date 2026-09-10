"""Suspect words for a document, computed on the text as shown (corrections
applied, headers and footers left out) and cached against the files that
feed it, so polling the document view while it is read stays cheap."""

from __future__ import annotations

import threading
from pathlib import Path

from app.library import DICTIONARY_FILE, Job, Library
from usefultext.corrections import Corrections
from usefultext.spellcheck import Spellchecker, Suspect

_cache: dict[str, tuple[tuple, dict]] = {}
_lock = threading.Lock()


def shown_lines(record, corrections: Corrections) -> list[tuple[int, str]]:
    """(line index, the text the editor shows) for every non-furniture line."""
    live = corrections.live(record)
    out = []
    for i, ln in enumerate(record.lines):
        if ln.get("furniture"):
            continue
        out.append((i, live[i].text if i in live else ln.get("text", "")))
    return out


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0.0


def document_suspects(
    lib: Library, job: Job, records: dict, corrections: Corrections
) -> dict[str, dict[int, list[Suspect]]]:
    """page id → {line index → suspects}, for the document's included pages.
    Recomputed only when state.json, corrections.json or the ignore list change."""
    key = (
        _mtime(job.folder / "state.json"),
        _mtime(job.folder / "corrections.json"),
        _mtime(lib.root / DICTIONARY_FILE),
        tuple(e.id for e in job.included()),
    )
    with _lock:
        hit = _cache.get(job.id)
        if hit and hit[0] == key:
            return hit[1]
    checker = Spellchecker(ignore=lib.dictionary())
    ids, pages, indexes = [], [], []
    for e in job.included():
        rec = records.get(e.id)
        if rec is None or rec.status != "done":
            continue
        lines = shown_lines(rec, corrections)
        ids.append(e.id)
        indexes.append([i for i, _ in lines])
        pages.append([t for _, t in lines])
    result: dict[str, dict[int, list[Suspect]]] = {}
    for page_id, idx, found in zip(ids, indexes, checker.check_pages(pages), strict=True):
        result[page_id] = {i: s for i, s in zip(idx, found, strict=True) if s}
    with _lock:
        _cache[job.id] = (key, result)
    return result
