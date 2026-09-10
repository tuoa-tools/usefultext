"""Reading order, line grouping, columns, heading and paragraph heuristics.

RapidOCR returns one region per detected text line with no style info, so
everything here is geometry:

- Columns: a vertical gap in the middle of the page (a gutter) that almost
  no region crosses, with a few lines of text on either side, splits the
  page into columns read left to right. A region that does cross it — a
  headline over both columns — is full width and splits the columns into
  the part above it and the part below. Photographed book pages have no
  such gap and stay one column; `columns="1"` turns the search off.
- Reading order: sort regions top-to-bottom, then left-to-right within a
  line band. Regions whose vertical centres fall within `band_factor` × the
  median region height of each other are one line; joined with spaces.
  A second rule rejoins a line that page curl split into two side-by-side
  pieces at different heights. On a multi-column page each column is
  grouped on its own, so a line never runs across the gutter.
- Headings (best effort, conservative — false headings are worse than missed
  ones): notably taller than the page's body lines AND short AND narrower
  than a body line. Calibrated on real book photos, where a chapter heading
  was only ~1.2× body height while curled body lines reached 1.3× — height
  alone cannot separate them; the width rule can. A full-width line over
  columns is wide by definition, so only its height counts there.
- Paragraph breaks: a vertical gap notably larger than the median line gap,
  and the boundary between full-width text and the columns beside it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

from .ocr import OcrRegion


@dataclass
class Line:
    regions: list[OcrRegion] = field(default_factory=list)
    heading: bool = False
    para_break_before: bool = False
    column: int = 0  # 1-based column on a multi-column page; 0 = full width

    @property
    def text(self) -> str:
        return " ".join(r.text for r in self.regions)

    @property
    def cy(self) -> float:
        return sum(r.cy for r in self.regions) / len(self.regions)

    @property
    def height(self) -> float:
        return max(r.height for r in self.regions)

    @property
    def x0(self) -> float:
        return min(r.bbox[0] for r in self.regions)

    @property
    def x1(self) -> float:
        return max(r.bbox[2] for r in self.regions)

    @property
    def y0(self) -> float:
        return min(r.bbox[1] for r in self.regions)

    @property
    def y1(self) -> float:
        return max(r.bbox[3] for r in self.regions)

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def mean_conf(self) -> float:
        return sum(r.conf for r in self.regions) / len(self.regions)


def _same_line(line: Line, r: OcrRegion, tol: float) -> bool:
    if abs(r.cy - line.cy) <= tol:
        return True
    # Side-by-side pieces of one line whose vertical extents overlap: page
    # curl lifts the right half of a top line above the left half.
    rx0, ry0, rx1, ry1 = r.bbox
    v_overlap = min(line.y1, ry1) - max(line.y0, ry0)
    if v_overlap < 0.4 * min(line.y1 - line.y0, ry1 - ry0):
        return False
    h_overlap = min(line.x1, rx1) - max(line.x0, rx0)
    return h_overlap < 0.2 * min(line.width, rx1 - rx0)


def group_lines(regions: list[OcrRegion], band_factor: float = 0.6) -> list[Line]:
    """Top-to-bottom, then left-to-right within a band of similar vertical centre."""
    if not regions:
        return []
    h_med = median(r.height for r in regions) or 1.0
    tol = band_factor * h_med

    lines: list[Line] = []
    for r in sorted(regions, key=lambda r: r.cy):
        if lines and _same_line(lines[-1], r, tol):
            lines[-1].regions.append(r)
        else:
            lines.append(Line([r]))
    for line in lines:
        line.regions.sort(key=lambda r: r.bbox[0])
    return lines


# --------------------------------------------------------------------------- #
# Columns
# --------------------------------------------------------------------------- #
def _centre_x(r: OcrRegion) -> float:
    x0, _, x1, _ = r.bbox
    return (x0 + x1) / 2


def find_gutters(
    regions: list[OcrRegion],
    *,
    min_gap: float = 1.0,
    min_lines: int = 3,
    max_cross: float = 0.2,
    min_column_width: float = 3.0,
) -> list[tuple[float, float]]:
    """The vertical gaps that split the page into columns, left to right, as
    (x0, x1) in the regions' coordinates.

    A gutter is a run of x positions crossed by at most `max_cross` of the
    text (region heights summed, so a headline over both columns is allowed
    and thirty body lines are not), at least `min_gap` × the median region
    height wide, with at least `min_lines` regions centred on either side
    whose median width is a few words (`min_column_width` × the median
    height) — so a column of page numbers beside a table of contents, or a
    right-aligned attribution, does not make a column. Ragged right edges
    never qualify: nothing sits to their right."""
    if len(regions) < 2 * min_lines:
        return []
    h_med = median(r.height for r in regions) or 1.0
    x_min = min(r.bbox[0] for r in regions)
    x_max = max(r.bbox[2] for r in regions)
    if x_max - x_min <= 0:
        return []
    step = max(1.0, h_med / 4)
    n_bins = int((x_max - x_min) / step) + 1
    crossing = [0.0] * n_bins
    for r in regions:
        x0, _, x1, _ = r.bbox
        first, last = int((x0 - x_min) / step), int((x1 - x_min) / step)
        for i in range(max(first, 0), min(last, n_bins - 1) + 1):
            crossing[i] += r.height
    limit = max_cross * sum(r.height for r in regions)

    runs: list[tuple[float, float]] = []
    i = 0
    while i < n_bins:
        if crossing[i] > limit:
            i += 1
            continue
        j = i
        while j + 1 < n_bins and crossing[j + 1] <= limit:
            j += 1
        runs.append((x_min + i * step, x_min + (j + 1) * step))
        i = j + 1

    gutters: list[tuple[float, float]] = []
    for gx0, gx1 in runs:
        if gx1 - gx0 < min_gap * h_med:
            continue
        left = [r for r in regions if _centre_x(r) < gx0]
        right = [r for r in regions if _centre_x(r) > gx1]
        if len(left) < min_lines or len(right) < min_lines:
            continue
        if median(r.width for r in left) < min_column_width * h_med:
            continue
        if median(r.width for r in right) < min_column_width * h_med:
            continue
        gutters.append((gx0, gx1))
    return gutters


@dataclass
class Block:
    """Regions read as one unit: one column of one band, or full-width text."""

    regions: list[OcrRegion]
    column: int  # 1-based column; 0 = full width
    band: int  # top-to-bottom; full-width text always starts a new band


def split_blocks(regions: list[OcrRegion], gutters: list[tuple[float, float]]) -> list[Block]:
    """Blocks in reading order: for each band, its columns left to right. A
    region that crosses a gutter is full width and closes the band above it;
    any other region belongs to the column its centre is nearest to."""
    if not gutters:
        return [Block(list(regions), 0, 0)]

    def spans(r: OcrRegion) -> bool:
        x0, _, x1, _ = r.bbox
        return any(x0 <= g0 and x1 >= g1 for g0, g1 in gutters)

    def column_of(r: OcrRegion) -> int:
        cx = _centre_x(r)
        return 1 + sum(1 for g0, g1 in gutters if cx > (g0 + g1) / 2)

    blocks: list[Block] = []
    band = 0
    columns: dict[int, list[OcrRegion]] = {}
    full_width: list[OcrRegion] = []

    def flush_columns() -> None:
        nonlocal band
        if columns:
            for c in sorted(columns):
                blocks.append(Block(columns[c], c, band))
            columns.clear()
            band += 1

    def flush_full_width() -> None:
        nonlocal band
        if full_width:
            blocks.append(Block(list(full_width), 0, band))
            full_width.clear()
            band += 1

    for r in sorted(regions, key=lambda r: r.cy):
        if spans(r):
            flush_columns()
            full_width.append(r)
        else:
            flush_full_width()
            columns.setdefault(column_of(r), []).append(r)
    flush_columns()
    flush_full_width()
    return blocks


def _body_lines(lines: list[Line]) -> list[Line]:
    """Lines wide enough to be body text — the reference for 'normal'."""
    widest = max(line.width for line in lines)
    body = [line for line in lines if line.width >= 0.5 * widest]
    return body if len(body) >= 3 else lines


_SENTENCE_END = ".,;:"


def _heading_shaped(line: Line, max_chars: int) -> bool:
    text = line.text.strip()
    if not text or len(text) > max_chars or not any(ch.isalpha() for ch in text):
        return False
    return text[-1] not in _SENTENCE_END


def mark_headings(
    lines: list[Line],
    height_ratio: float = 1.2,
    max_chars: int = 60,
    max_width_ratio: float = 0.8,
    min_lines: int = 5,
) -> None:
    """Flag headings. A candidate must be short (chars), narrower than a body
    line, contain letters and not end like a sentence. It is then a heading if
    EITHER it is notably taller than the body median (left-aligned headings)
    OR it is centred on the body column and at least body height (book
    chapter headings, whose size gain is often too small to trust alone —
    1.15× on the real samples, where curled body lines reach 1.3×). Short
    body lines (paragraph ends) are left-aligned, so centring separates them.
    Needs a few lines on the page for the medians to mean anything."""
    if len(lines) < min_lines:
        return
    body = _body_lines(lines)
    h_med = median(line.height for line in body) or 1.0
    w_med = median(line.width for line in body) or 1.0
    body_x0 = median(line.x0 for line in body)
    body_cx = median((line.x0 + line.x1) / 2 for line in body)
    for line in lines:
        if not _heading_shaped(line, max_chars) or line.width > max_width_ratio * w_med:
            continue
        taller = line.height >= height_ratio * h_med
        centred = (
            abs((line.x0 + line.x1) / 2 - body_cx) <= 0.05 * w_med
            and line.x0 - body_x0 >= 0.08 * w_med
            and line.height >= h_med
        )
        if taller or centred:
            line.heading = True


def mark_full_width_headings(
    lines: list[Line], height_ratio: float = 1.2, max_chars: int = 60, min_lines: int = 5
) -> None:
    """On a multi-column page, a full-width line is a heading when it is
    heading-shaped and notably taller than the columns' body lines (a
    headline over the columns). Width says nothing here: it spans by
    definition, and a full-width standfirst in body size is not a heading."""
    if len(lines) < min_lines:
        return
    in_columns = [line for line in lines if line.column]
    if not in_columns:
        return
    h_med = median(line.height for line in _body_lines(in_columns)) or 1.0
    for i, line in enumerate(lines):
        if line.column or not _heading_shaped(line, max_chars):
            continue
        if line.height >= height_ratio * h_med:
            line.heading = True
            if i + 1 < len(lines):
                lines[i + 1].para_break_before = True


def mark_paragraphs(lines: list[Line], gap_factor: float = 1.6) -> None:
    """Insert a paragraph break where the vertical gap between consecutive lines
    is well above the median gap. Headings always get a break before and after."""
    if len(lines) < 2:
        return
    gaps = [lines[i].cy - lines[i - 1].cy for i in range(1, len(lines))]
    g_med = median(gaps) if len(gaps) >= 3 else None
    for i in range(1, len(lines)):
        if g_med and gaps[i - 1] > gap_factor * g_med:
            lines[i].para_break_before = True
        if lines[i].heading or lines[i - 1].heading:
            lines[i].para_break_before = True


def layout_page(
    regions: list[OcrRegion],
    *,
    columns: str = "auto",
    band_factor: float = 0.6,
    heading_height_ratio: float = 1.2,
    heading_max_chars: int = 60,
    heading_max_width_ratio: float = 0.8,
    paragraph_gap_factor: float = 1.6,
    column_min_gap: float = 1.0,
    column_min_lines: int = 3,
    column_max_cross: float = 0.2,
) -> list[Line]:
    """Lines in reading order with headings and paragraph breaks marked.
    `columns` is "auto" (split at a clear gutter) or "1" (never split)."""
    gutters = (
        []
        if str(columns) == "1"
        else find_gutters(
            regions, min_gap=column_min_gap, min_lines=column_min_lines, max_cross=column_max_cross
        )
    )
    if not gutters:
        lines = group_lines(regions, band_factor)
        mark_headings(lines, heading_height_ratio, heading_max_chars, heading_max_width_ratio)
        mark_paragraphs(lines, paragraph_gap_factor)
        return lines

    lines: list[Line] = []
    previous: Block | None = None
    for block in split_blocks(regions, gutters):
        block_lines = group_lines(block.regions, band_factor)
        for line in block_lines:
            line.column = block.column
        if block.column:  # each column is judged against its own body lines
            mark_headings(
                block_lines, heading_height_ratio, heading_max_chars, heading_max_width_ratio
            )
        mark_paragraphs(block_lines, paragraph_gap_factor)
        if previous is not None and block.band != previous.band and block_lines:
            block_lines[0].para_break_before = True
        lines.extend(block_lines)
        previous = block
    mark_full_width_headings(lines, heading_height_ratio, heading_max_chars)
    return lines


def column_count(lines: list[Line]) -> int:
    return max((line.column for line in lines), default=0) or 1


def render_text(lines: list[Line]) -> str:
    """Plain text: one OCR line per line, blank line at paragraph breaks."""
    out: list[str] = []
    for line in lines:
        if line.para_break_before and out:
            out.append("")
        out.append(line.text)
    return "\n".join(out)


def render_markdown(lines: list[Line], heading_level: int = 2) -> str:
    """Markdown body for one page: headings get '#' markers, prose keeps one
    OCR line per line (Markdown folds them into paragraphs when rendered)."""
    prefix = "#" * max(1, heading_level)
    out: list[str] = []
    for line in lines:
        if line.para_break_before and out:
            out.append("")
        out.append(f"{prefix} {line.text}" if line.heading else line.text)
    return "\n".join(out)


def tall_area_fraction(regions: list[OcrRegion], ratio: float = 1.5) -> float:
    """Share of total region area in boxes taller than they are wide. On an
    upright page this is ~0; on a sideways page the text lines are tall boxes."""
    total = sum(r.area for r in regions)
    if total <= 0:
        return 0.0
    tall = sum(r.area for r in regions if r.height >= ratio * max(r.width, 1e-6))
    return tall / total


def clipped_at_edge(
    regions: list[OcrRegion],
    image_width: float,
    *,
    edge_margin_frac: float = 0.02,
    max_width_frac: float = 0.4,
) -> set[int]:
    """Indices of regions that touch the photo's left/right edge and are much
    narrower than the page's typical region: the facing page peeking into the
    frame ("Where th", "in the co"). Such text is cut off by the photo itself,
    so it cannot be a faithful part of this page's transcript."""
    if len(regions) < 3:
        return set()
    w_med = median(r.width for r in regions) or 1.0
    margin = edge_margin_frac * image_width
    out = set()
    for i, r in enumerate(regions):
        x0, _, x1, _ = r.bbox
        touches = x0 <= margin or x1 >= image_width - margin
        if touches and r.width < max_width_frac * w_med:
            out.add(i)
    return out
