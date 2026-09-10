#!/usr/bin/env python3
"""Drive a built (or installed) UsefulText end to end through its API:

    python scripts/smoke_bundle.py dist/UsefulText.app/Contents/MacOS/UsefulText
    python scripts/smoke_bundle.py .venv/bin/usefultext-app
    python scripts/smoke_bundle.py --pages fixtures/derived -- dist/UsefulText/UsefulText
    python scripts/smoke_bundle.py --synthetic -- build/windows/python/python.exe -m app.launcher

`--synthetic` makes a two-page PDF with PyMuPDF instead of needing the sample photos (CI).

Starts it with a scratch app-data folder in server-only mode, chooses a scratch library,
makes a document from the sample pages, reads them (the real engine: models, onnxruntime,
pillow-heif and pymupdf must all work inside the bundle), checks the Markdown export,
quits, and checks the process exited. Non-zero exit on any failure.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def call(port: int, token: str, method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        method=method,
        headers={"x-usefultext-token": token, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    return (
        json.loads(raw) if r.headers.get("content-type", "").startswith("application/json") else raw
    )


def write_synthetic_pdf(path: Path) -> None:
    """Two born-digital pages of known text, so the smoke test needs no photos."""
    import pymupdf

    pdf = pymupdf.open()
    for n in (1, 2):
        page = pdf.new_page(width=595, height=842)
        body = (
            f"Chapter {n}\n\n"
            "Fred looked out at the sea. The iceberg had been there for many, many years, "
            "and everyone assumed it always would be. This page was generated for the "
            "packaged app's smoke test, so the engine, its models and the PDF renderer "
            "are all exercised inside the bundle.\n\n"
            f"Page {n} of 2."
        )
        page.insert_textbox(pymupdf.Rect(72, 72, 523, 770), body, fontsize=13, fontname="helv")
    pdf.save(path)
    pdf.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", nargs="+", help="the app's executable (and arguments)")
    ap.add_argument("--pages", default=str(ROOT / "Documents"), help="folder of page photos")
    ap.add_argument("--synthetic", action="store_true", help="make a test PDF instead")
    ap.add_argument("--timeout", type=float, default=300.0, help="seconds to wait for the read")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory(prefix="usefultext-smoke-") as tmp:
        if args.synthetic:
            pages = Path(tmp) / "pages"
            pages.mkdir()
            write_synthetic_pdf(pages / "synthetic.pdf")
        else:
            pages = Path(args.pages).resolve()
        if not any(p.is_file() for p in pages.iterdir()):
            print(f"no pages in {pages}", file=sys.stderr)
            return 2
        data_dir = Path(tmp) / "appdata"
        library = Path(tmp) / "Library"
        env = dict(os.environ, USEFULTEXT_DATA_DIR=str(data_dir))
        proc = subprocess.Popen([*args.command, "--no-browser"], env=env)
        instance = data_dir / "instance.json"
        info = None
        for _ in range(600):  # a cold bundle on a slow disk can take a while
            time.sleep(0.1)
            if proc.poll() is not None:
                break
            try:
                info = json.loads(instance.read_text(encoding="utf-8"))
                health = call(info["port"], info["token"], "GET", "/api/health")
                break
            except Exception:
                info = None
        if info is None:
            print("the app did not start; log:", file=sys.stderr)
            log = data_dir / "app.log"
            if log.exists():
                print(log.read_text(encoding="utf-8")[-3000:], file=sys.stderr)
            proc.kill()
            return 1
        port, token = info["port"], info["token"]
        print(f"started: version {health['version']}, desktop={health['desktop']}")
        ok = True
        try:
            call(port, token, "PUT", "/api/settings", {"library_dir": str(library)})
            for _ in range(600):
                if call(port, token, "GET", "/api/health")["engine"]["state"] in (
                    "ready",
                    "failed",
                ):
                    break
                time.sleep(0.1)
            engine = call(port, token, "GET", "/api/health")["engine"]
            print(f"engine: {engine['state']} ({engine.get('load_seconds', '?')} s)")
            if engine["state"] != "ready":
                print(f"FAIL: engine {engine}", file=sys.stderr)
                ok = False
            doc = call(port, token, "POST", "/api/library", {"title": "Smoke test"})
            added = call(
                port,
                token,
                "POST",
                f"/api/documents/{doc['id']}/add-path",
                {"path": str(pages), "move": False, "replace": None},
            )
            print(f"added: {len(added['added'])} pages")
            call(port, token, "POST", f"/api/documents/{doc['id']}/start", {"force": False})
            t0 = time.time()
            view = None
            while time.time() - t0 < args.timeout:
                view = call(port, token, "GET", f"/api/documents/{doc['id']}")
                if view["status"] in ("done", "error", "paused"):
                    break
                time.sleep(1)
            print(
                f"read: status {view['status']}, {view['read']} of {view['included']} pages, "
                f"{view['errors']} errors, {time.time() - t0:.0f} s"
            )
            if view["status"] != "done" or view["errors"] or view["read"] != view["included"]:
                print(f"FAIL: last_run {view.get('last_run')}", file=sys.stderr)
                for p in view["pages"]:
                    if p["read"] and p["read"]["status"] == "error":
                        print(f"  {p['label']}: {p['read']['error']}", file=sys.stderr)
                ok = False
            md = call(port, token, "GET", f"/api/documents/{doc['id']}/export/md")
            text = md.decode("utf-8") if isinstance(md, bytes) else str(md)
            print(f"export: document.md {len(text)} chars, {text.count('## Page ')} pages")
            if text.count("## Page ") != view["included"]:
                print("FAIL: export page count", file=sys.stderr)
                ok = False
            docx = call(port, token, "GET", f"/api/documents/{doc['id']}/export/docx")
            print(f"export: document.docx {len(docx)} bytes")
        finally:
            try:
                call(port, token, "POST", "/api/quit")
            except Exception as exc:  # noqa: BLE001
                print(f"quit failed: {exc}", file=sys.stderr)
                ok = False
            for _ in range(300):
                if proc.poll() is not None:
                    break
                time.sleep(0.1)
            if proc.poll() is None:
                print("FAIL: still running after quit", file=sys.stderr)
                proc.kill()
                ok = False
            else:
                print(f"quit: exit code {proc.returncode}")
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
