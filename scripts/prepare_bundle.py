#!/usr/bin/env python3
"""Gather what the bundle needs before PyInstaller (or the Windows layout) runs:

packaging/models/   the three default RapidOCR models, copied out of the installed
                    rapidocr wheel (which carries 260 MB of models; we ship 32 MB).
                    The frozen launcher points USEFULTEXT_MODEL_DIR at them.
app/static/         checked, not built: run `npm run build` in frontend/ first.

  python scripts/prepare_bundle.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS_OUT = ROOT / "packaging" / "models"
# The defaults usefultext/ocr.py uses: PP-OCRv6 small detector and recogniser, the
# mobile angle classifier. Calibrated in Milestone 1; see the README's evaluation table.
MODEL_FILES = (
    "PP-OCRv6_det_small.onnx",
    "PP-OCRv6_rec_small.onnx",
    "ch_ppocr_mobile_v2.0_cls_mobile.onnx",
)


def main() -> int:
    import rapidocr

    source = Path(rapidocr.__file__).resolve().parent / "models"
    MODELS_OUT.mkdir(parents=True, exist_ok=True)
    total = 0
    for name in MODEL_FILES:
        src = source / name
        if not src.exists():
            print(f"missing in the rapidocr wheel: {src}", file=sys.stderr)
            return 1
        shutil.copy2(src, MODELS_OUT / name)
        total += src.stat().st_size
    print(f"models: {len(MODEL_FILES)} files, {total / 1e6:.1f} MB -> {MODELS_OUT}")

    index = ROOT / "app" / "static" / "index.html"
    if not index.exists():
        print("app/static/index.html is missing: run `npm run build` in frontend/", file=sys.stderr)
        return 1
    print("ui: app/static present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
