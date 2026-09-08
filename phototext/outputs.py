"""Output writers. Everything is regenerated from state.json after each page,
so a crash mid-batch leaves a complete, consistent output set for the pages
already read.

  state.json          job state — source of truth for resume
  pages/page_NNN.txt  plain text per page, reading order
  document.md         combined markdown, "## Page N" markers, best-effort headings
  document.jsonl      one line per text region: {page, text, conf, bbox, ...}
  report.csv          per page: filename, regions, mean confidence, low_conf ...

Wording: confidence is the engine's certainty. Human-facing text says
"read quality", never "accuracy".
"""
from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .inputs import PageSource
from .settings import Settings

STATE_FILE = "state.json"
STATE_VERSION = 1


def _atomic_write(path: Path, data: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(data, encoding="utf-8")
    os.replace(tmp, path)


@dataclass
class JobState:
    version: int = STATE_VERSION
    title: str = ""
    settings: dict = field(default_factory=dict)
    pages: dict = field(default_factory=dict)      # key → PageRecord

    @classmethod
    def load(cls, out_dir: Path) -> "JobState":
        from .pipeline import PageRecord
        p = out_dir / STATE_FILE
        if not p.exists():
            return cls()
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            state = cls(version=raw.get("version", STATE_VERSION), title=raw.get("title", ""),
                        settings=raw.get("settings", {}))
            state.pages = {k: PageRecord.from_dict(v) for k, v in raw.get("pages", {}).items()}
            return state
        except Exception:
            # A corrupt state file must not block a run; start fresh.
            return cls()

    def save(self, out_dir: Path) -> None:
        raw = {"version": self.version, "title": self.title, "settings": self.settings,
               "pages": {k: v.to_dict() for k, v in self.pages.items()}}
        _atomic_write(out_dir / STATE_FILE, json.dumps(raw, ensure_ascii=False, indent=1))


# --------------------------------------------------------------------------- #
# Human-facing wording
# --------------------------------------------------------------------------- #
def quality_note(rec) -> list[str]:
    """Warnings for one page, in plain words. Empty when nothing is wrong."""
    notes = []
    if rec.status == "error":
        notes.append(f"Could not read this page: {rec.error}")
        return notes
    if rec.n_regions == 0:
        notes.append("Nothing readable was found on this page.")
    elif rec.low_conf:
        notes.append(f"Low read quality ({rec.mean_conf:.2f}): this page may be misread. "
                     "Consider re-photographing it.")
    if rec.blurry:
        notes.append(f"The photo looks blurry (sharpness {rec.sharpness:.0f}). Consider retaking it.")
    return notes


def page_stem(page: int, total: int) -> str:
    width = max(3, len(str(total)))
    return f"page_{page:0{width}d}"


# --------------------------------------------------------------------------- #
# Writers
# --------------------------------------------------------------------------- #
def write_outputs(out_dir: Path, state: JobState, sources: list[PageSource], settings: Settings) -> None:
    records = [state.pages[s.key] for s in sources if s.key in state.pages]
    records.sort(key=lambda r: r.page)
    total = len(sources)
    pages_dir = out_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    for rec in records:
        _atomic_write(pages_dir / f"{page_stem(rec.page, total)}.txt", page_text(rec))
    _atomic_write(out_dir / "document.md", document_markdown(state, records, total, settings))
    _atomic_write(out_dir / "document.jsonl", document_jsonl(records))
    _atomic_write(out_dir / "report.csv", report_csv(records))


def page_text(rec) -> str:
    """Never present a low-quality page's text without its flag."""
    notes = quality_note(rec)
    header = "".join(f"[{n}]\n" for n in notes)
    if notes:
        header += "\n"
    body = rec.text if rec.status == "done" else ""
    return header + body + ("\n" if body else "")


def document_markdown(state: JobState, records, total: int, settings: Settings) -> str:
    from . import __version__
    parts = [f"# {state.title}", "",
             f"_Transcribed locally by PhotoText {__version__} (RapidOCR). "
             "Read quality is the OCR engine's own certainty, not a measure of accuracy. "
             f"{len(records)} of {total} pages read._", ""]
    for rec in records:
        parts.append(f"## Page {rec.page}")
        meta = [rec.label]
        if rec.status == "done":
            meta.append(f"read quality {rec.mean_conf:.2f}")
            meta.append(f"{rec.n_regions} regions")
            if rec.rotation:
                meta.append(f"rotated {rec.rotation}°")
        parts.append(f"<!-- {' · '.join(meta)} -->")
        for n in quality_note(rec):
            parts.append(f"> ⚠ {n}")
        parts.append("")
        if rec.status == "done" and rec.lines:
            parts.append(rec.markdown_body(settings.heading_level))
            parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def document_jsonl(records) -> str:
    lines = []
    for rec in records:
        if rec.status != "done":
            continue
        line_of = {}
        for li, ln in enumerate(rec.lines):
            for ri in ln["regions"]:
                line_of[ri] = li
        for order, r in enumerate(rec.regions):
            row = {"page": rec.page, "source": rec.label, "line": line_of.get(order, -1),
                   "order": order, "text": r["text"], "conf": r["conf"], "bbox": r["bbox"],
                   "clipped": bool(r.get("clipped", False)), "low_conf_page": rec.low_conf}
            lines.append(json.dumps(row, ensure_ascii=False))
    return "\n".join(lines) + ("\n" if lines else "")


REPORT_COLUMNS = ["page", "filename", "regions", "mean_conf", "low_conf",
                  "sharpness", "blurry", "rotation", "dropped_regions", "clipped_regions",
                  "elapsed_s", "status", "error"]


def report_csv(records) -> str:
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=REPORT_COLUMNS, lineterminator="\n")
    w.writeheader()
    for rec in records:
        w.writerow({
            "page": rec.page, "filename": rec.label, "regions": rec.n_regions,
            "mean_conf": f"{rec.mean_conf:.3f}", "low_conf": str(rec.low_conf).lower(),
            "sharpness": f"{rec.sharpness:.1f}", "blurry": str(rec.blurry).lower(),
            "rotation": rec.rotation, "dropped_regions": rec.dropped_regions,
            "clipped_regions": rec.clipped_regions,
            "elapsed_s": f"{rec.elapsed:.2f}", "status": rec.status, "error": rec.error or "",
        })
    return buf.getvalue()
