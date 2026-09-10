"""Output writers. Everything is regenerated from state.json (and a person's
corrections.json) after each page, so a crash mid-batch leaves a complete,
consistent output set for the pages already read.

  state.json                  job state — source of truth for resume (pipeline-owned)
  corrections.json            a person's edits, applied at export (corrections.py)
  pages/page_NNN_<photo>.txt  plain text per page; first line = provenance in brackets
  document.md                 combined markdown, "## Page N" markers, best-effort headings
  document.txt                combined plain text, "--- page N (photo) ---" separators
  document.jsonl              one line per text region: {page, text, conf, bbox, ...}
  report.csv                  per page: filename, regions, mean confidence, low_conf ...
  previews/<id>.jpg           upright preview per page (written by the pipeline)

Per-page files are named by position, so a reorder renames them; the writer
removes any page file it did not just write. Wording: confidence is the
engine's certainty. Human-facing text says "read quality", never "accuracy".
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from pathlib import Path

from .checks import quality_note
from .corrections import Corrections
from .fileio import read_text, write_text
from .inputs import PageSource, slug
from .settings import Settings

STATE_FILE = "state.json"
STATE_VERSION = 1
PAGES_DIR = "pages"
PAGE_FILE_GLOB = "page_*.txt"


def _atomic_write(path: Path, data: str) -> None:
    write_text(path, data)


@dataclass
class JobState:
    version: int = STATE_VERSION
    title: str = ""
    settings: dict = field(default_factory=dict)
    pages: dict = field(default_factory=dict)  # key → PageRecord

    @classmethod
    def load(cls, out_dir: Path) -> JobState:
        from .pipeline import PageRecord

        text = read_text(out_dir / STATE_FILE)
        if text is None:
            return cls()
        try:
            raw = json.loads(text)
            state = cls(
                version=raw.get("version", STATE_VERSION),
                title=raw.get("title", ""),
                settings=raw.get("settings", {}),
            )
            state.pages = {k: PageRecord.from_dict(v) for k, v in raw.get("pages", {}).items()}
            return state
        except Exception:
            # A corrupt state file must not block a run; start fresh.
            return cls()

    def save(self, out_dir: Path) -> None:
        raw = {
            "version": self.version,
            "title": self.title,
            "settings": self.settings,
            "pages": {k: v.to_dict() for k, v in self.pages.items()},
        }
        _atomic_write(out_dir / STATE_FILE, json.dumps(raw, ensure_ascii=False, indent=1))


# --------------------------------------------------------------------------- #
# Naming and provenance
# --------------------------------------------------------------------------- #
def page_stem(page: int, total: int) -> str:
    width = max(3, len(str(total)))
    return f"page_{page:0{width}d}"


def page_file_name(rec, total: int) -> str:
    """page_003_IMG_0042.txt: the position first, so the folder lists in
    reading order, then the photo it came from ('scan_p2' for a PDF page)."""
    return f"{page_stem(rec.page, total)}_{slug(rec.label, 40)}.txt"


def provenance(rec, total: int = 0, corrected: int = 0) -> str:
    """The first line of a per-page file, in the same bracket style as the
    quality notes: where the text came from and how well it read."""
    parts = [f"page {rec.page} of {total}" if total else f"page {rec.page}", rec.label]
    if rec.status != "done":
        parts.append("could not be read")
    else:
        parts.append(f"read quality {rec.mean_conf:.2f}")
        if rec.rotation:
            parts.append(f"rotated {rec.rotation}°")
        if rec.columns > 1:
            parts.append(f"{rec.columns} columns")
        if rec.printed_page is not None:
            parts.append(f"printed page {rec.printed_page}")
        if corrected:
            parts.append(f"{corrected} line{'s' if corrected != 1 else ''} corrected")
    return "[" + " · ".join(parts) + "]"


def _preamble(n_read: int, total: int) -> str:
    from . import __version__

    return (
        f"Transcribed locally by UsefulText {__version__} (RapidOCR). Read quality is the "
        f"OCR engine's own certainty, not a measure of accuracy. {n_read} of {total} pages read."
    )


# --------------------------------------------------------------------------- #
# Writers
# --------------------------------------------------------------------------- #
def write_outputs(
    out_dir: Path,
    state: JobState,
    sources: list[PageSource],
    settings: Settings,
    corrections: Corrections | None = None,
) -> None:
    corrections = corrections or Corrections()
    records = [state.pages[s.key] for s in sources if s.key in state.pages]
    records.sort(key=lambda r: r.page)
    total = len(sources)
    pages_dir = out_dir / PAGES_DIR
    pages_dir.mkdir(parents=True, exist_ok=True)

    written: set[str] = set()
    for rec in records:
        name = page_file_name(rec, total)
        _atomic_write(pages_dir / name, page_text(rec, settings, corrections, total))
        written.add(name)
    for stale in pages_dir.glob(PAGE_FILE_GLOB):  # a reorder or exclusion renamed it
        if stale.name not in written:
            stale.unlink(missing_ok=True)

    md = document_markdown(state, records, total, settings, corrections)
    _atomic_write(out_dir / "document.md", md)
    _atomic_write(
        out_dir / "document.txt", document_text(state, records, total, settings, corrections)
    )
    _atomic_write(out_dir / "document.jsonl", document_jsonl(records, corrections))
    _atomic_write(out_dir / "report.csv", report_csv(records, corrections))


def _body(rec, settings: Settings | None, corrections: Corrections) -> str:
    strip = settings.strip_furniture if settings else True
    return rec.body_text(strip, corrections) if rec.status == "done" else ""


def page_text(
    rec,
    settings: Settings | None = None,
    corrections: Corrections | None = None,
    total: int = 0,
    header: bool = True,
) -> str:
    """One page as plain text: the provenance line, any quality notes, a blank
    line, the text. A poorly read page is never shown without its notes."""
    corrections = corrections or Corrections()
    notes = [f"[{n}]" for n in quality_note(rec)]
    head = [provenance(rec, total, corrections.count(rec))] + notes if header else notes
    body = _body(rec, settings, corrections)
    text = ("\n".join(head) + "\n\n") if head else ""
    return text + body + ("\n" if body else "")


def document_text(
    state: JobState,
    records,
    total: int,
    settings: Settings,
    corrections: Corrections | None = None,
) -> str:
    corrections = corrections or Corrections()
    parts = [state.title, "", _preamble(len(records), total), ""]
    for rec in records:
        parts += [f"--- page {rec.page} ({rec.label}) ---", ""]
        notes = [f"[{n}]" for n in quality_note(rec)]
        if notes:
            parts += notes + [""]
        body = _body(rec, settings, corrections)
        if body:
            parts += [body, ""]
    return "\n".join(parts).rstrip() + "\n"


def document_markdown(
    state: JobState,
    records,
    total: int,
    settings: Settings,
    corrections: Corrections | None = None,
) -> str:
    corrections = corrections or Corrections()
    parts = [f"# {state.title}", "", f"_{_preamble(len(records), total)}_", ""]
    for rec in records:
        parts.append(f"## Page {rec.page}")
        meta = [rec.label]
        if rec.status == "done":
            meta.append(f"read quality {rec.mean_conf:.2f}")
            meta.append(f"{rec.n_regions} regions")
            if rec.rotation:
                meta.append(f"rotated {rec.rotation}°")
            if rec.columns > 1:
                meta.append(f"{rec.columns} columns")
            if rec.printed_page is not None:
                meta.append(f"printed page {rec.printed_page}")
            corrected = corrections.count(rec)
            if corrected:
                meta.append(f"{corrected} line{'s' if corrected != 1 else ''} corrected")
        parts.append(f"<!-- {' · '.join(meta)} -->")
        for n in quality_note(rec):
            parts.append(f"> ⚠ {n}")
        parts.append("")
        if rec.status == "done" and rec.lines:
            parts.append(
                rec.markdown_body(settings.heading_level, settings.strip_furniture, corrections)
            )
            parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def document_jsonl(records, corrections: Corrections | None = None) -> str:
    """One row per OCR region, raw text unchanged; `corrected` and
    `corrected_line` say what a person made of the line it belongs to."""
    corrections = corrections or Corrections()
    lines = []
    for rec in records:
        if rec.status != "done":
            continue
        live = corrections.live(rec)
        line_of, role_of, column_of = {}, {}, {}
        for li, ln in enumerate(rec.lines):
            role = "body"
            if ln.get("furniture"):
                role = next((f["position"] for f in rec.furniture if f["line"] == li), "footer")
                role = "header" if role == "top" else "footer"
            for ri in ln["regions"]:
                line_of[ri] = li
                role_of[ri] = role
                column_of[ri] = ln.get("column", 0)
        for order, r in enumerate(rec.regions):
            li = line_of.get(order, -1)
            row = {
                "page": rec.page,
                "page_id": rec.id,
                "printed_page": rec.printed_page,
                "source": rec.label,
                "line": li,
                "order": order,
                "role": role_of.get(order, "body"),
                "column": column_of.get(order, 0),
                "text": r["text"],
                "conf": r["conf"],
                "bbox": r["bbox"],
                "clipped": bool(r.get("clipped", False)),
                "low_conf_page": rec.low_conf,
                "corrected": li in live,
                "corrected_line": live[li].text if li in live else None,
            }
            lines.append(json.dumps(row, ensure_ascii=False))
    return "\n".join(lines) + ("\n" if lines else "")


REPORT_COLUMNS = [
    "page",
    "id",
    "filename",
    "printed_page",
    "regions",
    "mean_conf",
    "low_conf",
    "sharpness",
    "blurry",
    "rotation",
    "columns",
    "dropped_regions",
    "clipped_regions",
    "furniture_lines",
    "corrected_lines",
    "elapsed_s",
    "status",
    "error",
    "preview",
]


def report_csv(records, corrections: Corrections | None = None) -> str:
    corrections = corrections or Corrections()
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=REPORT_COLUMNS, lineterminator="\n")
    w.writeheader()
    for rec in records:
        w.writerow(
            {
                "page": rec.page,
                "id": rec.id,
                "filename": rec.label,
                "printed_page": "" if rec.printed_page is None else rec.printed_page,
                "regions": rec.n_regions,
                "mean_conf": f"{rec.mean_conf:.3f}",
                "low_conf": str(rec.low_conf).lower(),
                "sharpness": f"{rec.sharpness:.1f}",
                "blurry": str(rec.blurry).lower(),
                "rotation": rec.rotation,
                "columns": rec.columns,
                "dropped_regions": rec.dropped_regions,
                "clipped_regions": rec.clipped_regions,
                "furniture_lines": len(rec.furniture),
                "corrected_lines": corrections.count(rec),
                "elapsed_s": f"{rec.elapsed:.2f}",
                "status": rec.status,
                "error": rec.error or "",
                "preview": rec.preview,
            }
        )
    return buf.getvalue()
