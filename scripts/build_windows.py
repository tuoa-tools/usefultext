#!/usr/bin/env python3
"""Assemble the Windows app folder WITHOUT PyInstaller — Windows Defender quarantines
PyInstaller exes, while python.org's pythonw.exe is signed by the PSF (media_downloader's
lesson, kept).

Layout produced under build/windows/:
    python/                 python.org "embeddable" runtime
    Lib/site-packages/      the usefultext and app packages (with the built UI) and every
                            dependency as pip installs it — onnxruntime's DLLs, pythonnet
                            for pywebview, pillow-heif's libheif all arrive on their own
    Lib/site-packages/models/  the three OCR models (the launcher finds them there)
    UsefulText.cmd          fallback launcher; the installer's shortcut runs pythonw.exe

Must run on Windows with the Python minor version we ship (wheels are platform-specific).
packaging/windows.iss then wraps the folder into an Inno Setup installer.

    python scripts/prepare_bundle.py && python scripts/build_windows.py
"""

from __future__ import annotations

import io
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build" / "windows"
EMBED_URL = "https://www.python.org/ftp/python/{v}/python-{v}-embed-amd64.zip"


def main() -> int:
    if sys.platform != "win32":
        print("this script assembles a Windows layout; run it on Windows", file=sys.stderr)
        return 1
    models = ROOT / "packaging" / "models"
    if not (models / "PP-OCRv6_det_small.onnx").exists():
        print("run scripts/prepare_bundle.py first", file=sys.stderr)
        return 1
    version = "{}.{}.{}".format(*sys.version_info[:3])
    tag = f"python{sys.version_info.major}{sys.version_info.minor}"
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)

    print(f"downloading embeddable Python {version}")
    with urllib.request.urlopen(EMBED_URL.format(v=version), timeout=300) as response:
        zipfile.ZipFile(io.BytesIO(response.read())).extractall(OUT / "python")
    # The ._pth file *is* sys.path for the embeddable runtime (relative to python/).
    (OUT / "python" / f"{tag}._pth").write_text(
        f"{tag}.zip\n.\n..\\Lib\\site-packages\n", encoding="utf-8"
    )

    site = OUT / "Lib" / "site-packages"
    print("installing usefultext and its dependencies")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--quiet",
            "--no-compile",
            "--target",
            str(site),
            str(ROOT),
        ],
        check=True,
    )
    assert (site / "app" / "static" / "index.html").exists(), "built UI missing - run npm run build"
    # pip --target drops console-script wrappers (usefultext.exe…) into <target>/bin; they
    # cannot work in this layout.
    shutil.rmtree(site / "bin", ignore_errors=True)
    shutil.copytree(models, site / "models")

    (OUT / "UsefulText.cmd").write_text(
        '@start "" "%~dp0python\\pythonw.exe" -m app.launcher\r\n', encoding="utf-8"
    )
    size = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file()) / 1e6
    print(f"assembled {OUT.relative_to(ROOT)} ({size:.0f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
