"""The per-page processing pipeline and the resumable job runner.

process_page()  image/PDF page → PageRecord (regions, lines, flags)
run_job()       ordered pages → output folder, writing results per page and
                skipping pages already completed in that folder on re-run.

Nothing here is tied to the CLI: the Milestone 2 web layer calls run_job()
from a worker thread with its own on_page / should_stop callbacks.
"""
from __future__ import annotations

import math
import time
import traceback
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from PIL import Image

from . import ocr
from .inputs import PageSource
from .layout import layout_page, render_text, render_markdown, tall_area_fraction, clipped_at_edge, Line
from .ocr import OcrRegion, OcrPageResult
from .preprocess import load_image, downscale, sharpness_score, rotate, rotated_size
from .settings import Settings


# --------------------------------------------------------------------------- #
# Records
# --------------------------------------------------------------------------- #
@dataclass
class PageRecord:
    key: str
    source: str                 # file path
    label: str                  # file name (+ #pN for PDFs)
    page_index: int = 0
    page: int = 0               # 1-based position in the job; reassigned on resume
    status: str = "done"        # done | error
    error: str | None = None
    fingerprint: str = ""
    processed_at: str = ""
    elapsed: float = 0.0

    width: int = 0              # oriented page size at full resolution
    height: int = 0
    rotation: int = 0           # degrees CCW applied on top of EXIF orientation
    scale: float = 1.0          # inference size / full size
    trials: dict = field(default_factory=dict)   # rotation → score, when tried
    weak_reason: str = ""

    sharpness: float = 0.0
    blurry: bool = False
    n_regions: int = 0
    dropped_regions: int = 0    # below the region confidence filter
    clipped_regions: int = 0    # cut off at the photo edge (kept in JSONL, out of the text)
    mean_conf: float = 0.0
    low_conf: bool = True

    text: str = ""
    lines: list = field(default_factory=list)      # [{"text", "heading", "regions": [idx...]}]
    regions: list = field(default_factory=list)    # [OcrRegion.to_dict() + "clipped"] full-res coords

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PageRecord":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def region_objects(self) -> list[OcrRegion]:
        return [OcrRegion.from_dict(r) for r in self.regions]

    def line_objects(self) -> list[Line]:
        regs = self.region_objects()
        out = []
        for ln in self.lines:
            line = Line([regs[i] for i in ln["regions"]], heading=ln.get("heading", False),
                        para_break_before=ln.get("para_break_before", False))
            out.append(line)
        return out

    def markdown_body(self, heading_level: int = 2) -> str:
        return render_markdown(self.line_objects(), heading_level)


def fingerprint(path: Path) -> str:
    st = path.stat()
    return f"{st.st_size}:{st.st_mtime_ns}"


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def render_pdf_page(path: Path, index: int, dpi: int, max_pixels: int) -> Image.Image:
    """Render one PDF page at `dpi`, lowering it if the page would exceed
    max_pixels (oversized media boxes exist in the wild)."""
    import pymupdf
    with pymupdf.open(path) as doc:
        page = doc[index]
        w_in, h_in = page.rect.width / 72.0, page.rect.height / 72.0
        pixels = (w_in * dpi) * (h_in * dpi)
        if pixels > max_pixels:
            dpi = max(36, int(dpi * math.sqrt(max_pixels / pixels)))
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def load_source(source: PageSource, settings: Settings) -> Image.Image:
    if source.is_pdf:
        return render_pdf_page(source.path, source.page_index, settings.pdf_dpi, settings.pdf_max_pixels)
    return load_image(source.path)


# --------------------------------------------------------------------------- #
# Pre-check (cheap, before OCR starts)
# --------------------------------------------------------------------------- #
def sharpness_precheck(sources: list[PageSource], settings: Settings) -> dict[str, float]:
    """Sharpness per image page (PDF pages are checked during processing, since
    rendering them just for this would cost as much as the read itself)."""
    scores: dict[str, float] = {}
    for src in sources:
        if src.is_pdf:
            continue
        try:
            img = load_image(src.path)
            img, _ = downscale(img, settings.max_long_edge)
            scores[src.key] = sharpness_score(img)
        except Exception:
            continue
    return scores


# --------------------------------------------------------------------------- #
# Orientation
# --------------------------------------------------------------------------- #
def looks_weak(result: OcrPageResult, settings: Settings) -> str:
    """Why the first read looks weak ('' if it doesn't)."""
    if result.n_regions == 0:
        return "no regions"
    if result.n_regions < settings.weak_min_regions:
        return f"only {result.n_regions} regions"
    if result.mean_conf < settings.min_page_conf:
        return f"read quality {result.mean_conf:.2f}"
    tall = tall_area_fraction(result.regions)
    if tall >= settings.tall_region_fraction:
        return f"{tall:.0%} of text area in tall boxes (sideways?)"
    return ""


def choose_orientation(img: Image.Image, first: OcrPageResult, settings: Settings
                       ) -> tuple[int, dict[str, float]]:
    """Trial 90° (then 270° if needed) on a reduced copy with the line
    classifier OFF, so an upside-down candidate scores honestly low. With it
    on, the classifier silently fixes flipped lines and both directions look
    equally good — only the reading order would come out reversed.
    Returns (rotation to apply, trial scores)."""
    trials = {"0": round(first.score, 2)}
    trial_img, _ = downscale(img, settings.trial_long_edge)
    sideways = first.n_regions > 0 and tall_area_fraction(first.regions) >= settings.tall_region_fraction
    results: dict[int, OcrPageResult] = {}
    for rot in (90, 270):
        r = ocr.ocr_image(rotate(trial_img, rot), use_cls=False,
                          min_region_conf=settings.min_region_conf, box_thresh=settings.det_box_thresh)
        results[rot] = r
        trials[str(rot)] = round(r.score, 2)
        if (sideways and r.mean_conf >= settings.trial_accept_conf
                and r.n_regions >= settings.weak_min_regions):
            break                       # clear winner; skip the other direction
    best_rot = max(results, key=lambda k: results[k].score)
    best_score = results[best_rot].score
    if best_score <= 0:
        return 0, trials
    if sideways or best_score >= settings.rotate_margin * first.score:
        return best_rot, trials
    return 0, trials


# --------------------------------------------------------------------------- #
# One page
# --------------------------------------------------------------------------- #
def process_page(source: PageSource, settings: Settings, *, sharpness: float | None = None
                 ) -> PageRecord:
    t0 = time.perf_counter()
    rec = PageRecord(key=source.key, source=str(source.path), label=source.label,
                     page_index=source.page_index, fingerprint=fingerprint(source.path),
                     processed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))

    img = load_source(source, settings)
    full_w, full_h = img.size
    img_d, scale = downscale(img, settings.max_long_edge)
    rec.scale = scale

    rec.sharpness = sharpness if sharpness is not None else sharpness_score(img_d)
    rec.blurry = rec.sharpness < settings.blur_threshold

    read = lambda im: ocr.ocr_image(im, use_cls=True, min_region_conf=settings.min_region_conf,
                                    box_thresh=settings.det_box_thresh)
    result = read(img_d)
    rotation = 0
    if settings.auto_rotate:
        reason = looks_weak(result, settings)
        if reason:
            rec.weak_reason = reason
            rotation, rec.trials = choose_orientation(img_d, result, settings)
            if rotation:
                result = read(rotate(img_d, rotation))
        elif result.flipped_fraction >= settings.flip_fraction:
            # The read looks strong only because the classifier turned each
            # line the right way up; the page itself is upside down and its
            # reading order would come out reversed. Re-read it rotated.
            rec.weak_reason = f"classifier flipped {result.flipped_fraction:.0%} of lines (upside down?)"
            rec.trials = {"0": round(result.score, 2)}
            flipped = read(rotate(img_d, 180))
            rec.trials["180"] = round(flipped.score, 2)
            if flipped.n_regions > 0 and flipped.flipped_fraction < settings.flip_fraction:
                result, rotation = flipped, 180
    rec.rotation = rotation
    rec.width, rec.height = rotated_size((full_w, full_h), rotation)

    # Regions back to full-resolution coordinates of the upright page.
    regions = [r.scaled(1.0 / scale) for r in result.regions]
    clipped: set[int] = set()
    if settings.drop_clipped:
        clipped = clipped_at_edge(regions, rec.width, edge_margin_frac=settings.edge_margin_frac,
                                  max_width_frac=settings.clipped_max_width_frac)
    kept = [r for i, r in enumerate(regions) if i not in clipped]
    lines = layout_page(kept, band_factor=settings.line_band_factor,
                        heading_height_ratio=settings.heading_height_ratio,
                        heading_max_chars=settings.heading_max_chars,
                        heading_max_width_ratio=settings.heading_max_width_ratio,
                        paragraph_gap_factor=settings.paragraph_gap_factor)

    index_of = {id(r): i for i, r in enumerate(regions)}
    rec.regions = [dict(r.to_dict(), clipped=(i in clipped)) for i, r in enumerate(regions)]
    rec.lines = [{"text": ln.text, "heading": ln.heading, "para_break_before": ln.para_break_before,
                  "regions": [index_of[id(r)] for r in ln.regions]} for ln in lines]
    rec.text = render_text(lines)
    rec.clipped_regions = len(clipped)
    rec.n_regions = len(kept)
    rec.dropped_regions = result.dropped_regions
    rec.mean_conf = round(sum(r.conf for r in kept) / len(kept), 4) if kept else 0.0
    # Brief: mean confidence < gate, or zero regions, → low read quality.
    rec.low_conf = not kept or rec.mean_conf < settings.min_page_conf
    rec.elapsed = round(time.perf_counter() - t0, 2)
    return rec


# --------------------------------------------------------------------------- #
# The job
# --------------------------------------------------------------------------- #
@dataclass
class JobSummary:
    out_dir: str
    total: int = 0
    processed: int = 0
    resumed: int = 0
    failed: int = 0
    stopped_early: bool = False
    elapsed: float = 0.0
    records: list = field(default_factory=list)   # PageRecord, in page order

    @property
    def low_conf_pages(self) -> list[PageRecord]:
        return [r for r in self.records if r.status == "done" and r.low_conf]

    @property
    def blurry_pages(self) -> list[PageRecord]:
        return [r for r in self.records if r.status == "done" and r.blurry]

    @property
    def error_pages(self) -> list[PageRecord]:
        return [r for r in self.records if r.status == "error"]


OnPage = Callable[[PageRecord, int, int, bool], None]


def run_job(sources: list[PageSource], out_dir: str | Path, settings: Settings | None = None, *,
            on_page: OnPage | None = None, should_stop: Callable[[], bool] | None = None,
            force: bool = False, precheck: dict[str, float] | None = None,
            title: str | None = None) -> JobSummary:
    """Read every page in order, writing results as each one completes.

    Resumable: `state.json` in out_dir records every finished page; a re-run
    skips pages whose file is unchanged (use force=True to redo them).
    Pausable: should_stop() is polled before each page; a True stops pulling
    from the queue and the outputs so far stay valid.
    """
    from .outputs import JobState, write_outputs

    settings = settings or Settings()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    state = JobState.load(out)
    state.settings = settings.to_dict()
    state.title = title or state.title or out.name
    precheck = precheck or {}

    summary = JobSummary(out_dir=str(out), total=len(sources))
    t0 = time.perf_counter()
    for i, src in enumerate(sources, start=1):
        if should_stop and should_stop():
            summary.stopped_early = True
            break
        prior = state.pages.get(src.key)
        resumed = (prior is not None and prior.status == "done" and not force
                   and prior.fingerprint == fingerprint(src.path))
        if resumed:
            rec = prior
            summary.resumed += 1
        else:
            try:
                rec = process_page(src, settings, sharpness=precheck.get(src.key))
            except Exception as exc:
                rec = PageRecord(key=src.key, source=str(src.path), label=src.label,
                                 page_index=src.page_index, status="error",
                                 error=f"{type(exc).__name__}: {exc}",
                                 fingerprint=fingerprint(src.path) if src.path.exists() else "",
                                 processed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
                rec.error_detail = traceback.format_exc()  # type: ignore[attr-defined]
                summary.failed += 1
            else:
                summary.processed += 1
        rec.page = i
        state.pages[src.key] = rec
        state.save(out)
        write_outputs(out, state, sources, settings)
        if on_page:
            on_page(rec, i, len(sources), resumed)

    write_outputs(out, state, sources, settings)
    summary.records = [state.pages[s.key] for s in sources if s.key in state.pages]
    summary.elapsed = round(time.perf_counter() - t0, 2)
    return summary
