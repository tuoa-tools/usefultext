#!/usr/bin/env python3
"""UsefulText CLI — a folder of page photos (and PDFs) → text, markdown, JSONL, CSV.

    usefultext Documents/ --out output/

All processing is local and offline. The heavy lifting lives in the
`usefultext` package; this file only parses arguments and prints progress.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from usefultext import Settings, __version__, discover_sources, ocr, run_job, sharpness_precheck
from usefultext.inputs import SORT_MODES
from usefultext.preprocess import HEIF_EXTS, heif_error, register_heif


def build_parser() -> argparse.ArgumentParser:
    d = Settings()
    p = argparse.ArgumentParser(
        prog="usefultext", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("inputs", nargs="+", type=Path, help="image/PDF files or folders")
    p.add_argument("--out", required=True, type=Path, help="output folder (created if missing)")
    p.add_argument(
        "--sort",
        choices=SORT_MODES,
        default=d.sort,
        help="page order: name (natural sort), time (EXIF DateTimeOriginal), "
        "auto = name unless the names look random (default), "
        "printed = by page numbers found in running headers/footers",
    )
    p.add_argument("--recursive", action="store_true", help="also search sub-folders")
    p.add_argument("--force", action="store_true", help="re-read pages already completed in --out")
    p.add_argument(
        "--dpi", type=int, default=d.pdf_dpi, help=f"PDF render resolution (default {d.pdf_dpi})"
    )
    p.add_argument(
        "--min-conf",
        type=float,
        default=d.min_page_conf,
        help=f"page read-quality gate (default {d.min_page_conf})",
    )
    p.add_argument(
        "--region-conf",
        type=float,
        default=d.min_region_conf,
        help=f"drop text regions below this read quality (default {d.min_region_conf})",
    )
    p.add_argument(
        "--blur-threshold",
        type=float,
        default=d.blur_threshold,
        help=f"sharpness below this is flagged blurry (default {d.blur_threshold:g})",
    )
    p.add_argument(
        "--max-edge",
        type=int,
        default=d.max_long_edge,
        help=f"downscale photos to this long edge before OCR (default {d.max_long_edge})",
    )
    p.add_argument("--no-rotate", action="store_true", help="disable the 0°/90° orientation trial")
    p.add_argument(
        "--heading-ratio",
        type=float,
        default=d.heading_height_ratio,
        help=f"line height ÷ body line height above which a short line is a heading "
        f"(default {d.heading_height_ratio})",
    )
    p.add_argument(
        "--keep-clipped",
        action="store_true",
        help="keep narrow text cut off at the photo's left/right edge (facing page)",
    )
    p.add_argument(
        "--keep-furniture",
        action="store_true",
        help="keep running headers/footers in the text (they stay in the JSONL either way)",
    )
    p.add_argument(
        "--box-thresh",
        type=float,
        default=d.det_box_thresh,
        help=f"RapidOCR detector box threshold (default {d.det_box_thresh}; engine default 0.5)",
    )
    p.add_argument("--title", help="document title for document.md (default: input folder name)")
    p.add_argument("--quiet", "-q", action="store_true", help="only print the summary")
    p.add_argument("--version", action="version", version=f"UsefulText {__version__}")
    return p


def settings_from_args(args) -> Settings:
    return Settings(
        pdf_dpi=args.dpi,
        sort=args.sort,
        max_long_edge=args.max_edge,
        blur_threshold=args.blur_threshold,
        auto_rotate=not args.no_rotate,
        min_page_conf=args.min_conf,
        min_region_conf=args.region_conf,
        heading_height_ratio=args.heading_ratio,
        drop_clipped=not args.keep_clipped,
        det_box_thresh=args.box_thresh,
        strip_furniture=not args.keep_furniture,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = settings_from_args(args)
    say = (lambda *a, **k: None) if args.quiet else print

    for p in args.inputs:
        if not p.exists():
            print(f"error: {p} does not exist", file=sys.stderr)
            return 2

    register_heif()
    sources, sort_used = discover_sources(args.inputs, sort=args.sort, recursive=args.recursive)
    if not sources:
        print(
            "error: no supported files found (jpg/jpeg/png/heic/heif/tif/bmp/webp/pdf)",
            file=sys.stderr,
        )
        return 2
    if any(s.path.suffix.lower() in HEIF_EXTS for s in sources) and not register_heif():
        print(
            f"warning: HEIC/HEIF files present but pillow-heif is not working: {heif_error()}",
            file=sys.stderr,
        )

    title = args.title or (args.inputs[0].name if args.inputs[0].is_dir() else args.inputs[0].stem)

    say(f"UsefulText {__version__} — {len(sources)} page(s), ordered by {sort_used}")
    say("Checking sharpness…")
    precheck = sharpness_precheck(sources, settings)
    for i, s in enumerate(sources, 1):
        score = precheck.get(s.key)
        flag = ""
        if score is not None and score < settings.blur_threshold:
            flag = "  ← looks blurry, consider retaking"
        shown = f"{score:6.1f}" if score is not None else "   pdf"
        say(f"  {i:3d}. {s.label:<45} sharpness {shown}{flag}")

    say("Loading OCR models…")
    t0 = time.perf_counter()
    if not ocr.available():
        print(f"error: OCR engine unavailable: {ocr.import_error()}", file=sys.stderr)
        return 3
    say(f"  ready in {time.perf_counter() - t0:.1f}s\n")

    def on_page(rec, i, total, resumed):
        if resumed:
            say(f"[{i}/{total}] {rec.label}: already read, skipped")
            return
        if rec.status == "error":
            say(f"[{i}/{total}] {rec.label}: ERROR {rec.error}")
            return
        flags = []
        if rec.rotation:
            flags.append(f"rotated {rec.rotation}°")
        if rec.low_conf:
            flags.append("LOW READ QUALITY")
        if rec.blurry:
            flags.append("blurry")
        say(
            f"[{i}/{total}] {rec.label}: {rec.n_regions} regions, "
            f"read quality {rec.mean_conf:.2f}, "
            f"{rec.elapsed:.1f}s" + (f"  [{', '.join(flags)}]" if flags else "")
        )

    try:
        summary = run_job(
            sources,
            args.out,
            settings,
            on_page=on_page,
            force=args.force,
            precheck=precheck,
            title=title,
        )
    except KeyboardInterrupt:
        print("\nInterrupted. Completed pages are saved; re-run the same command to resume.")
        return 130

    print(
        f"\nDone: {summary.processed} read, {summary.resumed} skipped (already read), "
        f"{summary.failed} failed, {summary.elapsed:.1f}s"
    )
    if settings.sort == "printed":
        print("Order by printed page number:")
        for r in summary.records:
            shown = r.printed_page if r.printed_page is not None else "?"
            print(f"  page {r.page:3d} = printed {shown!s:>4}  {r.label}")
        for n in summary.order_notes:
            print(f"  note: {n}")
    furniture = sum(len(r.furniture) for r in summary.records if r.status == "done")
    if furniture:
        verb = "removed from the text" if settings.strip_furniture else "kept in the text"
        print(f"{furniture} running header/footer line(s) detected across pages, {verb}.")
    low = summary.low_conf_pages
    if low:
        print(f"{len(low)} page(s) read poorly — consider re-photographing:")
        for r in low:
            print(
                f"  page {r.page}: {r.label} "
                f"(read quality {r.mean_conf:.2f}, {r.n_regions} regions)"
            )
    for r in summary.error_pages:
        print(f"  page {r.page}: {r.label} FAILED: {r.error}")
    print(f"Outputs in {args.out}/: pages/*.txt, document.md, document.jsonl, report.csv")
    return 1 if summary.failed else 0


if __name__ == "__main__":
    sys.exit(main())
