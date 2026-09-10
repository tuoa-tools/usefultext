"""Image loading and the cheap per-image checks that run before OCR.

- HEIC/HEIF via pillow-heif, registered on first use with a clear error if
  the package is missing (it fails at open, not at upload — so check early).
- EXIF orientation is applied on load (ImageOps.exif_transpose).
- downscale(): phone photos are shrunk to a sane long edge before inference.
- sharpness_score(): variance of the Laplacian — a "looks blurry" pre-check.
- rotate(): whole-page rotation in 90° steps, used by the orientation trial.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from . import fileio

SUPPORTED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tif", ".tiff", ".bmp", ".webp"}
SUPPORTED_PDF_EXTS = {".pdf"}
SUPPORTED_EXTS = SUPPORTED_IMAGE_EXTS | SUPPORTED_PDF_EXTS
HEIF_EXTS = {".heic", ".heif"}

_heif_ok: bool | None = None
_heif_error: str | None = None


def register_heif() -> bool:
    """Register the HEIF opener once. Safe to call repeatedly."""
    global _heif_ok, _heif_error
    if _heif_ok is None:
        try:
            import pillow_heif

            pillow_heif.register_heif_opener()
            _heif_ok = True
        except Exception as exc:
            _heif_ok = False
            _heif_error = repr(exc)
    return _heif_ok


def heif_error() -> str | None:
    return _heif_error


def load_image(path: str | Path) -> Image.Image:
    """Open an image file, apply EXIF orientation, return an RGB image."""
    p = Path(path)
    if p.suffix.lower() in HEIF_EXTS and not register_heif():
        raise RuntimeError(
            f"{p.name}: HEIC/HEIF files need the 'pillow-heif' package ({heif_error()})"
        )
    with Image.open(p) as im:
        im = ImageOps.exif_transpose(im)
        return im.convert("RGB")


def downscale(img: Image.Image, max_long_edge: int) -> tuple[Image.Image, float]:
    """Shrink so the long edge is at most max_long_edge. Returns (image, scale)
    where scale = new / old (1.0 when untouched)."""
    w, h = img.size
    long_edge = max(w, h)
    if long_edge <= max_long_edge:
        return img, 1.0
    scale = max_long_edge / long_edge
    new_size = (max(1, round(w * scale)), max(1, round(h * scale)))
    return img.resize(new_size, Image.Resampling.LANCZOS), scale


def sharpness_score(
    img: Image.Image, norm_long_edge: int = 1000, edge_min_gradient: float = 20.0
) -> float:
    """Variance-of-Laplacian blur check, measured over edge pixels only.

    A plain Laplacian variance over the whole frame mostly measures how much
    text is on the page (a dense blurry page outscored a sparse sharp one on
    the real samples). Restricting it to edge pixels — gradient magnitude of
    at least `edge_min_gradient` grey levels, i.e. text strokes — measures
    how crisp the edges themselves are, independent of how many there are
    (a percentile mask failed on sparse pages: it filled up with blank paper).
    The grey copy is normalised to a fixed long edge so the number is
    comparable across cameras. Reported as the RMS (same units as pixel
    intensity); higher = sharper. Threshold: Settings.blur_threshold,
    calibrated on real photos. A page with no edges at all scores 0."""
    grey = img.convert("L")
    grey, _ = downscale(grey, norm_long_edge)
    a = np.asarray(grey, dtype=np.float32)
    if a.shape[0] < 3 or a.shape[1] < 3:
        return 0.0
    lap = a[:-2, 1:-1] + a[2:, 1:-1] + a[1:-1, :-2] + a[1:-1, 2:] - 4.0 * a[1:-1, 1:-1]
    gy, gx = np.gradient(a)
    grad = np.hypot(gx, gy)[1:-1, 1:-1]
    mask = grad >= edge_min_gradient
    if not mask.any():
        return 0.0
    return float(np.sqrt(np.mean(lap[mask] ** 2)))


_ROTATE = {
    0: None,
    90: Image.Transpose.ROTATE_90,  # counter-clockwise
    180: Image.Transpose.ROTATE_180,
    270: Image.Transpose.ROTATE_270,
}


def rotate(img: Image.Image, degrees_ccw: int) -> Image.Image:
    """Rotate by a multiple of 90° counter-clockwise (lossless)."""
    op = _ROTATE[degrees_ccw % 360]
    return img if op is None else img.transpose(op)


def rotated_size(size: tuple[int, int], degrees_ccw: int) -> tuple[int, int]:
    w, h = size
    return (h, w) if degrees_ccw % 180 == 90 else (w, h)


def write_preview(
    img: Image.Image, path: Path, rotation: int = 0, long_edge: int = 1600, quality: int = 80
) -> tuple[int, int]:
    """Save an upright JPEG preview of a page: rotate by what the read decided,
    shrink to `long_edge`, write atomically. Returns the preview's (width, height).
    Region boxes are in full-resolution upright coordinates, so a viewer
    scales them by preview width ÷ page width."""
    small, _ = downscale(rotate(img, rotation), long_edge)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = fileio.tmp_path(path)
    small.convert("RGB").save(tmp, "JPEG", quality=quality, optimize=True)
    fileio.replace(tmp, path)
    return small.size
