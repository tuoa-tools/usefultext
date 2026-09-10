"""Running headers and footers ("page furniture") and printed page numbers.

Detected across the whole job, never per page: a short line at the very top
or bottom of a page whose text — digits removed — recurs on other pages is
furniture ("6 | JOHN KOTTER…", "OUR ICEBERG IS MELTING | 7", a bare "12").
A chapter title at the top of a page appears once, so it is never stripped;
lines already marked as headings are skipped as well.

Verso/recto books alternate two different footers, so each pattern only has
to recur on `min_pages` pages. Photos often cut a footer short ("…AND HC"),
so patterns are also compared on their common prefix.

Printed page numbers become metadata (report.csv, JSONL, the markdown page
marker) and drive `sort=printed`: pages are ordered by their printed number,
un-numbered pages fill the gaps in capture order, and the CLI prints the
resulting mapping so a person can sanity-check it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

_DIGITS = re.compile(r"\d+")
_NONALPHA = re.compile(r"[^a-z]+")
_INT = re.compile(r"(?<!\d)(\d{1,4})(?!\d)")


def signature(text: str) -> str:
    """Digit-free, lowercase, letters-only form used for cross-page matching."""
    return _NONALPHA.sub(" ", _DIGITS.sub("", text.lower())).strip()


def similar(a: str, b: str, threshold: float = 0.8) -> bool:
    if a == b:
        return True
    if not a or not b:
        return False
    n = min(len(a), len(b))
    if n < 6:
        return False
    if SequenceMatcher(None, a, b).ratio() >= threshold:
        return True
    return SequenceMatcher(None, a[:n], b[:n]).ratio() >= 0.9  # one copy cut short


def printed_number(text: str) -> int | None:
    """The page number in a furniture line: a lone integer, or one at either end."""
    nums = _INT.findall(text)
    if not nums:
        return None
    if len(nums) == 1:
        n = int(nums[0])
    else:
        stripped = text.strip()
        if re.match(r"^\d{1,4}\b", stripped):
            n = int(nums[0])
        elif re.search(r"\b\d{1,4}$", stripped):
            n = int(nums[-1])
        else:
            return None
    return n if 1 <= n <= 5000 else None


@dataclass
class Candidate:
    record: object
    line_index: int
    text: str
    position: str  # "top" | "bottom"
    sig: str


def _line_rel_y(record, line: dict) -> float | None:
    if not record.height or not line.get("regions"):
        return None
    ys = []
    for i in line["regions"]:
        if 0 <= i < len(record.regions):
            _, y0, _, y1 = record.regions[i]["bbox"]
            ys.append((y0 + y1) / 2)
    return (sum(ys) / len(ys)) / record.height if ys else None


def candidates(
    record, band: float = 0.12, max_chars: int = 60, max_lines_each_end: int = 2
) -> list[Candidate]:
    lines = record.lines
    if not lines:
        return []
    out: list[Candidate] = []
    n = len(lines)
    ends = [(i, "top") for i in range(min(max_lines_each_end, n))]
    ends += [
        (i, "bottom") for i in range(max(n - max_lines_each_end, 0), n) if (i, "top") not in ends
    ]
    for i, position in ends:
        line = lines[i]
        text = line.get("text", "").strip()
        if not text or len(text) > max_chars or line.get("heading"):
            continue
        rel = _line_rel_y(record, line)
        if rel is None:
            continue
        if (position == "top" and rel > band) or (position == "bottom" and rel < 1 - band):
            continue
        out.append(Candidate(record, i, text, position, signature(text)))
    return out


def detect_furniture(records, *, band: float = 0.12, min_pages: int = 2) -> None:
    """Annotate records in place: lines[i]["furniture"], record.furniture,
    record.printed_page. Idempotent — clears previous annotations first."""
    done = [r for r in records if r.status == "done"]
    for r in done:
        for ln in r.lines:
            ln["furniture"] = False
        r.furniture = []
        r.printed_page = None

    cands = [c for r in done for c in candidates(r, band)]
    clusters: list[list[Candidate]] = []
    for c in cands:
        for cluster in clusters:
            head = cluster[0]
            if head.position != c.position:
                continue
            if (not head.sig and not c.sig) or similar(head.sig, c.sig):
                cluster.append(c)
                break
        else:
            clusters.append([c])

    for cluster in clusters:
        pages = {id(c.record) for c in cluster}
        if len(pages) < min_pages:
            continue
        for c in cluster:
            c.record.lines[c.line_index]["furniture"] = True
            c.record.furniture.append(
                {"line": c.line_index, "text": c.text, "position": c.position}
            )
            num = printed_number(c.text)
            if num is not None and c.record.printed_page is None:
                c.record.printed_page = num


def order_by_printed_page(sources, printed: dict[str, int | None]) -> tuple[list, list[str]]:
    """Order pages by printed number. Un-numbered pages fill the gaps between
    known numbers in their existing order; any left over go at the end.
    Returns (ordered sources, human-readable notes)."""
    notes: list[str] = []
    known = [(printed[s.key], i, s) for i, s in enumerate(sources) if printed.get(s.key)]
    unknown = [s for s in sources if not printed.get(s.key)]
    if not known:
        return list(sources), ["no printed page numbers were found; order unchanged"]
    known.sort(key=lambda t: (t[0], t[1]))
    numbers = [n for n, _, _ in known]
    seen = set()
    for n in numbers:
        if n in seen:
            notes.append(
                f"printed page {n} appears more than once; capture order kept between them"
            )
        seen.add(n)
    gaps = [n for n in range(numbers[0], numbers[-1] + 1) if n not in seen]

    slots: dict[int, list] = {n: [] for n in numbers}
    for n, _, s in known:
        slots[n].append(s)
    queue = list(unknown)
    for g in gaps:
        if queue:
            s = queue.pop(0)
            slots[g] = [s]
            notes.append(f"{s.label} has no printed number; placed at page {g} (a gap)")
        else:
            notes.append(f"printed page {g} is missing from the set")
    ordered = [s for n in sorted(slots) for s in slots[n]]
    for s in queue:
        notes.append(f"{s.label} has no printed number; placed after the last numbered page")
    ordered.extend(queue)
    return ordered, notes
