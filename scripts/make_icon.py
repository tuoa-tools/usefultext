#!/usr/bin/env python3
"""A placeholder app icon until there is art: a blue rounded square with a page
and three lines of text. Writes packaging/icon.png (1024²), icon.ico, and on
macOS icon.icns (via iconutil).

    python scripts/make_icon.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "packaging"
BLUE = (37, 99, 235)  # Tailwind blue-600, the UI's accent
PAPER = (255, 255, 255)
INK = (148, 163, 184)  # slate-400


def draw(size: int = 1024) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = size * 0.22
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=r, fill=BLUE)
    # A page with a folded corner.
    left, top, right, bottom = size * 0.27, size * 0.18, size * 0.73, size * 0.82
    fold = size * 0.12
    page = [
        (left, top),
        (right - fold, top),
        (right, top + fold),
        (right, bottom),
        (left, bottom),
    ]
    d.polygon(page, fill=PAPER)
    d.polygon([(right - fold, top), (right - fold, top + fold), (right, top + fold)], fill=INK)
    # Three text lines, the last one short.
    x0, x1 = left + size * 0.08, right - size * 0.08
    h = size * 0.045
    for i, frac in enumerate((1.0, 1.0, 0.55)):
        y = top + size * 0.24 + i * size * 0.13
        d.rounded_rectangle((x0, y, x0 + (x1 - x0) * frac, y + h), radius=h / 2, fill=INK)
    return img


def main() -> int:
    OUT.mkdir(exist_ok=True)
    icon = draw()
    icon.save(OUT / "icon.png")
    icon.save(
        OUT / "icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    )
    made = ["icon.png", "icon.ico"]
    if sys.platform == "darwin" and shutil.which("iconutil"):
        with tempfile.TemporaryDirectory() as tmp:
            iconset = Path(tmp) / "icon.iconset"
            iconset.mkdir()
            for px in (16, 32, 64, 128, 256, 512):
                icon.resize((px, px), Image.LANCZOS).save(iconset / f"icon_{px}x{px}.png")
                icon.resize((px * 2, px * 2), Image.LANCZOS).save(
                    iconset / f"icon_{px}x{px}@2x.png"
                )
            subprocess.run(
                ["iconutil", "-c", "icns", str(iconset), "-o", str(OUT / "icon.icns")], check=True
            )
        made.append("icon.icns")
    print("wrote", ", ".join(made), "->", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
