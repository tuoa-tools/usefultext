"""Job-level warnings: what a person should look at before trusting the text.

  duplicate          two pages read as nearly the same text — a page photographed twice
  printed_duplicate  two pages carry the same printed page number
  printed_gap        a printed number between the lowest and highest seen is on no page
  retake             a page that read poorly, looks blurry, or could not be read

Computed from the records in state.json, so the CLI prints them at the end
of a run and the app shows them live in the ordering view. Plain words that
say what to do; "read quality" is the engine's certainty, never "accuracy".
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher

_NONWORD = re.compile(r"[^a-z0-9]+")


@dataclass
class JobWarning:
    kind: str
    message: str
    pages: list = field(default_factory=list)  # 1-based positions involved, in job order

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Per-page notes (also the first lines of the per-page text files)
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
        notes.append(
            f"Low read quality ({rec.mean_conf:.2f}): this page may be misread. "
            "Consider re-photographing it."
        )
    if rec.blurry:
        notes.append(
            f"The photo looks blurry (sharpness {rec.sharpness:.0f}). Consider retaking it."
        )
    return notes


def _where(rec, capital: bool = False) -> str:
    return f"{'Page' if capital else 'page'} {rec.page} ({rec.label})"


def retake_warnings(records) -> list[JobWarning]:
    out = []
    for rec in records:
        notes = quality_note(rec)
        if notes:
            out.append(
                JobWarning("retake", f"{_where(rec, capital=True)}: {' '.join(notes)}", [rec.page])
            )
    return out


# --------------------------------------------------------------------------- #
# Duplicate pages
# --------------------------------------------------------------------------- #
def normalise(text: str) -> str:
    return _NONWORD.sub(" ", text.lower()).strip()


def similarity(a: str, b: str) -> float:
    """0–1, how alike two normalised texts are. A cheap token-overlap check
    first, so eighty pages compare in milliseconds, then the real ratio."""
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0.0
    if len(ta & tb) / len(ta | tb) < 0.5:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def find_duplicates(records, threshold: float = 0.9, min_chars: int = 40) -> list[JobWarning]:
    done = [r for r in records if r.status == "done"]
    texts = {r.page: normalise(r.body_text()) for r in done}
    texts = {p: t for p, t in texts.items() if len(t) >= min_chars}
    by_page = {r.page: r for r in done}
    out = []
    pages = sorted(texts)
    for i, a in enumerate(pages):
        for b in pages[i + 1 :]:
            if similarity(texts[a], texts[b]) >= threshold:
                out.append(
                    JobWarning(
                        "duplicate",
                        f"Pages {a} and {b} read as the same text ({by_page[a].label}, "
                        f"{by_page[b].label}) — one may be a repeat photo.",
                        [a, b],
                    )
                )
    return out


# --------------------------------------------------------------------------- #
# Printed page numbers
# --------------------------------------------------------------------------- #
def printed_number_warnings(records) -> list[JobWarning]:
    done = [r for r in records if r.status == "done"]
    numbered: dict[int, list] = {}
    for r in done:
        if r.printed_page is not None:
            numbered.setdefault(r.printed_page, []).append(r)
    if not numbered:
        return []
    out = []
    for n, recs in sorted(numbered.items()):
        if len(recs) > 1:
            where = ", ".join(_where(r) for r in recs)
            out.append(
                JobWarning(
                    "printed_duplicate",
                    f"Printed page {n} appears on {where}.",
                    [r.page for r in recs],
                )
            )
    unnumbered = [r for r in done if r.printed_page is None]
    for n in range(min(numbered), max(numbered) + 1):
        if n in numbered:
            continue
        if unnumbered:
            names = ", ".join(_where(r) for r in unnumbered[:3])
            more = f" (and {len(unnumbered) - 3} more)" if len(unnumbered) > 3 else ""
            verb = "has" if len(unnumbered) == 1 else "have"
            msg = (
                f"No page carries printed number {n}; {names}{more} {verb} no number and may be it."
            )
            out.append(JobWarning("printed_gap", msg, [r.page for r in unnumbered]))
        else:
            out.append(
                JobWarning(
                    "printed_gap",
                    f"No page carries printed number {n} — a page may be missing.",
                    [],
                )
            )
    return out


# --------------------------------------------------------------------------- #
# Everything
# --------------------------------------------------------------------------- #
def job_warnings(records, settings=None) -> list[JobWarning]:
    threshold = settings.duplicate_similarity if settings else 0.9
    return (
        retake_warnings(records)
        + find_duplicates(records, threshold)
        + printed_number_warnings(records)
    )
