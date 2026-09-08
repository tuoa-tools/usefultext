"""ocr.py — OCR backend (RapidOCR / ONNX Runtime, CPU).

Copied from redaction_detection_poc/ocr.py (proven on real scanned documents)
and extended for PhotoText. The original API is kept intact:

  available() / import_error()      lazy singleton engine, never crashes
  OcrPageResult(text, mean_conf, n_regions) with .low_confidence
  ocr_pdf_page(page) / ocr_image_file(path)

Extensions:
  - OcrRegion: per-region text, confidence and 4-point box, so callers can
    order lines, detect headings and write JSONL.
  - ocr_image(): OCR an in-memory PIL image / ndarray, with a per-call toggle
    for the angle classifier (used by the orientation trial).
  - OCR_REGION_MIN_CONF: region-level filter. Bleed-through ghost text from the
    reverse side reads as low-confidence garbage; dropping it is separate from
    the page-level gate. Dropped regions are counted, not silently lost.

Design (unchanged):
  - Models load once per process, on first use.
  - Every result carries a mean confidence so callers can gate on quality.
    Confidence is the engine's certainty ("read quality"), never "accuracy".
  - Fully offline: the default models ship inside the rapidocr wheel; nothing
    is fetched at run time. PHOTOTEXT_MODEL_DIR overrides the model folder
    (the hook the frozen/packaged build will use).

Tuning:
  OCR_DPI              render resolution for PDF pages (200 = speed/quality
                       sweet spot; raise to 300 if small print misses)
  OCR_MIN_CONF         per-page mean confidence below which the page is treated
                       as unreliably read (silent-failure gate)
  OCR_REGION_MIN_CONF  per-region confidence below which a region is dropped
"""
from __future__ import annotations

import math
import os
import threading
from dataclasses import dataclass, field
from typing import Any

import numpy as np

OCR_DPI = 200
OCR_MIN_CONF = 0.70
OCR_REGION_MIN_CONF = 0.5

_engine = None
_import_error: str | None = None
_lock = threading.Lock()


def _engine_params() -> dict[str, Any]:
    params: dict[str, Any] = {
        "Global.use_cls": True,        # per-line 180° flips (brief: enable)
        "Global.log_level": "warning",
    }
    model_dir = os.environ.get("PHOTOTEXT_MODEL_DIR")
    if model_dir:
        params["Global.model_root_dir"] = model_dir
    return params


def available() -> bool:
    """Load the engine on first call. False (never raises) if it can't."""
    global _engine, _import_error
    if _engine is not None:
        return True
    if _import_error is not None:
        return False
    with _lock:
        if _engine is not None:
            return True
        try:
            from rapidocr import RapidOCR
            _engine = RapidOCR(params=_engine_params())
            return True
        except Exception as exc:          # not installed, or model load failed
            _import_error = repr(exc)
            return False


def import_error() -> str | None:
    return _import_error


def _ensure_engine():
    if not available():
        raise RuntimeError(f"OCR engine unavailable: {_import_error}")
    return _engine


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #
def _dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


@dataclass
class OcrRegion:
    """One detected text line. `quad` is [tl, tr, br, bl] in pixel coordinates
    of the image handed to the engine (RapidOCR maps boxes back to the input)."""
    text: str
    conf: float
    quad: list[list[float]]

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        xs = [p[0] for p in self.quad]
        ys = [p[1] for p in self.quad]
        return (min(xs), min(ys), max(xs), max(ys))

    def _edge_pair_lengths(self) -> tuple[float, float]:
        """(horizontal-ish edge length, vertical-ish edge length).

        RapidOCR's corner order is [tl, tr, br, bl] for horizontal lines but
        flips for tilted vertical ones, so width/height are chosen by which
        edge pair lies closer to the x-axis rather than by corner index."""
        q = self.quad
        a_len = (_dist(q[0], q[1]) + _dist(q[3], q[2])) / 2      # edges p0→p1, p3→p2
        b_len = (_dist(q[0], q[3]) + _dist(q[1], q[2])) / 2      # edges p0→p3, p1→p2
        a_dx = abs(q[1][0] - q[0][0]) + abs(q[2][0] - q[3][0])
        b_dx = abs(q[3][0] - q[0][0]) + abs(q[2][0] - q[1][0])
        # Compare |cos| of each edge pair with the x-axis.
        a_horiz = a_dx / (2 * a_len) if a_len else 0.0
        b_horiz = b_dx / (2 * b_len) if b_len else 0.0
        return (a_len, b_len) if a_horiz >= b_horiz else (b_len, a_len)

    @property
    def width(self) -> float:      # extent along the text direction (horizontal-ish)
        return self._edge_pair_lengths()[0]

    @property
    def height(self) -> float:     # extent across the text (vertical-ish) — tilt-tolerant
        return self._edge_pair_lengths()[1]

    @property
    def cx(self) -> float:
        return sum(p[0] for p in self.quad) / 4

    @property
    def cy(self) -> float:
        return sum(p[1] for p in self.quad) / 4

    @property
    def area(self) -> float:
        return self.width * self.height

    def scaled(self, factor: float) -> "OcrRegion":
        return OcrRegion(self.text, self.conf, [[x * factor, y * factor] for x, y in self.quad])

    def to_dict(self) -> dict:
        x0, y0, x1, y1 = self.bbox
        return {
            "text": self.text,
            "conf": round(self.conf, 4),
            "bbox": [round(x0), round(y0), round(x1), round(y1)],
            "quad": [[round(x, 1), round(y, 1)] for x, y in self.quad],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "OcrRegion":
        return cls(text=d["text"], conf=float(d["conf"]), quad=[list(map(float, p)) for p in d["quad"]])


@dataclass
class OcrPageResult:
    text: str
    mean_conf: float
    n_regions: int
    regions: list[OcrRegion] = field(default_factory=list)
    dropped_regions: int = 0        # below OCR_REGION_MIN_CONF (or caller's value)
    elapsed: float = 0.0

    @property
    def low_confidence(self) -> bool:
        # No regions on a page we believed held content is itself suspect;
        # the caller decides whether blank-is-plausible. (PhotoText's pipeline
        # treats a blank read of a photographed page as low read quality.)
        return self.n_regions > 0 and self.mean_conf < OCR_MIN_CONF

    @property
    def score(self) -> float:
        """Orientation-trial score from the brief: regions × mean confidence."""
        return self.n_regions * self.mean_conf


# --------------------------------------------------------------------------- #
# Running the engine
# --------------------------------------------------------------------------- #
def _to_engine_input(source):
    """PIL images become BGR arrays (what RapidOCR expects for ndarrays);
    ndarrays are passed through and assumed BGR; paths/bytes go straight in."""
    try:
        from PIL import Image
    except ImportError:            # pragma: no cover
        Image = None
    if Image is not None and isinstance(source, Image.Image):
        rgb = np.asarray(source.convert("RGB"))
        return np.ascontiguousarray(rgb[:, :, ::-1])
    return source


def _run(source, *, use_cls: bool = True, min_region_conf: float = OCR_REGION_MIN_CONF,
         box_thresh: float | None = None) -> OcrPageResult:
    engine = _ensure_engine()
    # Every flag is passed explicitly: RapidOCR keeps per-call flags from one
    # call to the next, so an omitted flag silently inherits the last value.
    # text_score=0 so the region filter happens here, where it can be counted.
    kwargs = dict(use_det=True, use_cls=use_cls, use_rec=True, text_score=0.0)
    if box_thresh is not None:
        kwargs["box_thresh"] = box_thresh
    result = engine(_to_engine_input(source), **kwargs)
    boxes = getattr(result, "boxes", None)
    txts = list(getattr(result, "txts", None) or [])
    scores = list(getattr(result, "scores", None) or [])
    boxes = list(boxes) if boxes is not None else [None] * len(txts)

    regions: list[OcrRegion] = []
    dropped = 0
    for box, txt, score in zip(boxes, txts, scores):
        if not txt or not txt.strip():
            continue
        if score < min_region_conf:
            dropped += 1
            continue
        quad = [[float(x), float(y)] for x, y in box] if box is not None else [[0.0, 0.0]] * 4
        regions.append(OcrRegion(text=txt.strip(), conf=float(score), quad=quad))

    text = "\n".join(r.text for r in regions)
    mean_conf = (sum(r.conf for r in regions) / len(regions)) if regions else 0.0
    elapsed = getattr(result, "elapse", 0.0) or 0.0
    return OcrPageResult(text=text, mean_conf=mean_conf, n_regions=len(regions),
                         regions=regions, dropped_regions=dropped, elapsed=float(elapsed))


def ocr_image(img, *, use_cls: bool = True, min_region_conf: float = OCR_REGION_MIN_CONF,
              box_thresh: float | None = None) -> OcrPageResult:
    """OCR an in-memory image (PIL.Image, or an ndarray in BGR order).

    box_thresh overrides the detector's box threshold (engine default 0.5);
    curved lines near a book's gutter/top need ~0.4 to be found at all."""
    return _run(img, use_cls=use_cls, min_region_conf=min_region_conf, box_thresh=box_thresh)


def ocr_pdf_page(page) -> OcrPageResult:
    """OCR a PyMuPDF page by rendering it to an image first."""
    pix = page.get_pixmap(dpi=OCR_DPI)
    return _run(pix.tobytes("png"), box_thresh=0.5)


def ocr_image_file(path) -> OcrPageResult:
    """OCR a standalone image file (png/jpg/tiff/...)."""
    return _run(str(path), box_thresh=0.5)
