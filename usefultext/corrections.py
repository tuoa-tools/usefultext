"""A person's corrections to OCR lines, kept apart from the machine's results.

`corrections.json` sits beside `state.json`, but the pipeline never writes
it: a re-read replaces state.json wholesale and the corrections survive.
Each correction remembers the OCR text it replaced, so after a re-read it is
re-attached only if the line still reads the same, and is otherwise reported
as stale rather than silently applied to different text.

Rules (PLAN_M2.md §1, decision 4): corrections are per line, keyed by page id
and line index; a corrected line may contain newlines (how a line the OCR
missed is added); an empty correction drops the line from the text. Nothing
here changes text on its own — a person does.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

CORRECTIONS_FILE = "corrections.json"
CORRECTIONS_VERSION = 1


@dataclass
class Correction:
    text: str  # the person's text; "" drops the line; a "\n" inside adds lines
    ocr: str  # the OCR line it replaced, for re-attaching after a re-read
    at: str = ""  # when, ISO 8601 UTC


@dataclass
class TextLine:
    """A line of the page as it should be shown: the OCR's text or a person's."""

    text: str
    heading: bool = False
    para_break_before: bool = False
    origin: str = "ocr"  # "ocr" | "human"
    index: int = -1  # index into PageRecord.lines (the same for lines a correction added)


@dataclass
class Corrections:
    pages: dict = field(default_factory=dict)  # page id → {line index → Correction}

    # --- file ---

    @classmethod
    def load(cls, folder: Path | str) -> Corrections:
        """The corrections in `folder`, or none: a missing or unreadable file
        must never stop a run or an export."""
        p = Path(folder) / CORRECTIONS_FILE
        if not p.exists():
            return cls()
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            out = cls()
            for page_id, lines in raw.get("pages", {}).items():
                out.pages[page_id] = {
                    int(i): Correction(c["text"], c.get("ocr", ""), c.get("at", ""))
                    for i, c in lines.items()
                }
            return out
        except Exception:
            return cls()

    def save(self, folder: Path | str) -> None:
        raw = {
            "version": CORRECTIONS_VERSION,
            "pages": {
                page_id: {str(i): asdict(c) for i, c in sorted(lines.items())}
                for page_id, lines in self.pages.items()
                if lines
            },
        }
        path = Path(folder) / CORRECTIONS_FILE
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, path)

    # --- editing ---

    def set(self, page_id: str, line_index: int, text: str, ocr: str) -> Correction:
        at = datetime.now(UTC).isoformat(timespec="seconds")
        corr = Correction(text=text, ocr=ocr, at=at)
        self.pages.setdefault(page_id, {})[line_index] = corr
        return corr

    def revert(self, page_id: str, line_index: int) -> bool:
        """Back to the OCR text. True if there was a correction to remove."""
        lines = self.pages.get(page_id, {})
        if line_index not in lines:
            return False
        del lines[line_index]
        if not lines:
            self.pages.pop(page_id, None)
        return True

    # --- reading ---

    def for_page(self, page_id: str) -> dict[int, Correction]:
        return dict(self.pages.get(page_id, {}))

    def live(self, rec) -> dict[int, Correction]:
        """The corrections that still apply to `rec`: the line exists and
        its OCR text is what the person corrected."""
        lines = rec.lines
        return {
            i: c
            for i, c in self.pages.get(rec.id, {}).items()
            if 0 <= i < len(lines) and lines[i].get("text", "") == c.ocr
        }

    def stale(self, rec) -> list[tuple[int, Correction]]:
        """Corrections made against text the page no longer contains (the page
        was read again and that line came out differently, or is gone)."""
        live = self.live(rec)
        return [(i, c) for i, c in sorted(self.pages.get(rec.id, {}).items()) if i not in live]

    def count(self, rec) -> int:
        return len(self.live(rec))

    def total(self) -> int:
        return sum(len(lines) for lines in self.pages.values())


def overlay(rec, *, skip_furniture: bool = True, corrections: Corrections | None = None):
    """The page's lines with the live corrections applied. A correction with
    newlines becomes several lines (the first keeps the heading and paragraph
    marks); an empty one drops the line."""
    live = corrections.live(rec) if corrections else {}
    out: list[TextLine] = []
    inherited: bool | None = None  # a stripped column-top line's break, for the next line
    for i, ln in enumerate(rec.lines):
        if skip_furniture and ln.get("furniture"):
            # A page number at the top of a column, stripped: the line after it now
            # starts the column, so it takes the column's own break (none between the
            # columns of one band) rather than the gap-based one it got from the number.
            if i == 0 or rec.lines[i - 1].get("column", 0) != ln.get("column", 0):
                inherited = bool(ln.get("para_break_before", False))
            continue
        heading = bool(ln.get("heading", False))
        brk = bool(ln.get("para_break_before", False))
        if inherited is not None:
            brk, inherited = inherited, None
        corr = live.get(i)
        if corr is None:
            out.append(TextLine(ln.get("text", ""), heading, brk, "ocr", i))
            continue
        pieces = [piece.strip() for piece in corr.text.split("\n")]
        for j, piece in enumerate(piece for piece in pieces if piece):
            first = j == 0
            out.append(TextLine(piece, heading and first, brk and first, "human", i))
    return out
