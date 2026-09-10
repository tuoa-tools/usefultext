"""Tunable knobs for the pipeline, with defaults calibrated on real photos.

Every threshold lives here (or in ocr.py for the engine-level constants) so
the CLI, the future web UI and tests all share one source of truth.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .ocr import OCR_DPI, OCR_MIN_CONF, OCR_REGION_MIN_CONF


@dataclass
class Settings:
    # --- inputs -------------------------------------------------------------
    pdf_dpi: int = OCR_DPI              # render resolution for PDF pages
    pdf_max_pixels: int = 9_000_000     # clamp oversized media boxes (~9 MP)
    sort: str = "auto"                  # auto | name | time | printed (by detected page numbers)

    # --- preprocessing --------------------------------------------------------
    max_long_edge: int = 2500           # downscale phone photos before inference
    blur_threshold: float = 65.0        # edge-restricted Laplacian RMS (preprocess.sharpness_score)
    auto_rotate: bool = True            # 0°/90° trial when the first read looks weak
    trial_long_edge: int = 1000         # reduced size for orientation trials (speed)
    weak_min_regions: int = 4           # fewer kept regions than this = "looks weak"
    rotate_margin: float = 1.2          # a trial must beat the 0° score by this factor
    tall_region_fraction: float = 0.5   # area share of tall boxes that says "sideways page"
    trial_accept_conf: float = 0.85     # a sideways trial this confident wins outright
                                        # (the wrong direction reads at ~0.6 with the
                                        # line classifier off)
    flip_fraction: float = 0.6          # share of lines the angle classifier flipped
                                        # above which the whole page is upside down
                                        # (real pages: ≤0.05 upright, ≥0.7 flipped)

    # --- engine -----------------------------------------------------------------
    det_box_thresh: float = 0.4         # RapidOCR detector box threshold (engine default
                                        # 0.5 misses strongly curved lines near the top
                                        # of a photographed book page)

    # --- confidence gates (engine certainty = read quality — never "accuracy")
    min_page_conf: float = OCR_MIN_CONF           # page-level gate (0.70)
    min_region_conf: float = OCR_REGION_MIN_CONF  # region-level filter (0.5)

    # --- clipped text at the photo's left/right edge (facing page peeking in)
    drop_clipped: bool = True
    edge_margin_frac: float = 0.02      # "touches the edge" = within 2% of image width
    clipped_max_width_frac: float = 0.4 # ...and narrower than 40% of the median region

    # --- running headers/footers (detected across pages, see furniture.py)
    strip_furniture: bool = True        # keep them out of the text/markdown (kept in JSONL)
    furniture_band: float = 0.12        # only lines within this fraction of the page top/bottom
    furniture_min_pages: int = 2        # a pattern must recur on this many pages

    # --- layout -----------------------------------------------------------------
    line_band_factor: float = 0.6       # vertical-centre tolerance, × median line height
    heading_height_ratio: float = 1.2   # line height above this × median body line → heading…
    heading_max_chars: int = 60         # …if also short in characters…
    heading_max_width_ratio: float = 0.8  # …and narrower than this × median body line width
    heading_level: int = 2              # brief: headings → "##"
    paragraph_gap_factor: float = 1.6   # line gap above this × median gap → blank line

    extra: dict = field(default_factory=dict)  # room for the UI to stash things

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Settings:
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)
