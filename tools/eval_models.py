#!/usr/bin/env python3
"""Measure OCR configurations against hand-checked transcripts.

    python tools/eval_models.py [--configs default,v6-medium,...] [--pages Documents]

For every page in Documents/ that has a reference in fixtures/reference/
(<filename stem>.txt), run the full pipeline (rotation, clipping, layout)
under each configuration and report character and word error rates against
the reference. Non-default configurations download their model on first
use (development only — the packaged app bundles whatever wins here).
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import ImageFilter  # noqa: E402

from usefultext import Settings, discover_sources, ocr, pipeline  # noqa: E402

CONFIGS: dict[str, dict] = {
    "default (v6 small)": {},
    "v6 medium rec": {"Rec.model_type": "medium"},
    "v6 medium det+rec": {"Det.model_type": "medium", "Rec.model_type": "medium"},
    "v5 en mobile rec": {
        "Rec.ocr_version": "PP-OCRv5",
        "Rec.lang_type": "en",
        "Rec.model_type": "mobile",
    },
    "v5 ch server rec": {
        "Rec.ocr_version": "PP-OCRv5",
        "Rec.lang_type": "ch",
        "Rec.model_type": "server",
    },
    "v4 en mobile rec": {
        "Rec.ocr_version": "PP-OCRv4",
        "Rec.lang_type": "en",
        "Rec.model_type": "mobile",
    },
    "default + unsharp": {"_unsharp": True},
}

_QUOTES = {"“": '"', "”": '"', "‘": "'", "’": "'", "—": "-", "–": "-"}


def normalise(text: str) -> str:
    for k, v in _QUOTES.items():
        text = text.replace(k, v)
    text = text.lower()
    return re.sub(r"\s+", " ", text).strip()


def levenshtein(a, b) -> int:
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def rates(hyp: str, ref: str) -> tuple[float, float]:
    h, r = normalise(hyp), normalise(ref)
    cer = levenshtein(h, r) / max(1, len(r))
    wer = levenshtein(h.split(), r.split()) / max(1, len(r.split()))
    return cer, wer


_ENUM_KEYS = {"model_type": "ModelType", "ocr_version": "OCRVersion", "lang_type": "LangRec"}


def _typed(key: str, value):
    """RapidOCR validates these settings as enums, not strings."""
    from rapidocr.utils import typings

    field = key.split(".")[-1]
    if field in _ENUM_KEYS:
        return getattr(typings, _ENUM_KEYS[field])(value)
    return value


def swap_engine(params: dict) -> None:
    from rapidocr import RapidOCR

    full = dict(ocr._engine_params())
    full.update({k: _typed(k, v) for k, v in params.items() if not k.startswith("_")})
    ocr._engine = RapidOCR(params=full)
    ocr._import_error = None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", default=str(ROOT / "Documents"))
    ap.add_argument("--configs", default=",".join(CONFIGS))
    args = ap.parse_args()

    ref_dir = ROOT / "fixtures" / "reference"
    sources, _ = discover_sources([args.pages])
    sources = [s for s in sources if (ref_dir / f"{s.path.stem}.txt").exists()]
    if not sources:
        print("no pages with references found", file=sys.stderr)
        return 1
    refs = {s.key: (ref_dir / f"{s.path.stem}.txt").read_text() for s in sources}

    original_load = pipeline.load_source
    settings = Settings()
    rows = []
    for wanted in [c.strip() for c in args.configs.split(",") if c.strip()]:
        # Exact name, else a unique prefix, else the name minus its parenthetical
        # ("default" → "default (v6 small)", not "default + unsharp").
        matches = [k for k in CONFIGS if k == wanted] or [
            k for k in CONFIGS if k.startswith(wanted)
        ]
        if len(matches) > 1:
            matches = [k for k in matches if k[len(wanted) :].startswith(" (")]
        if len(matches) != 1:
            print(f"--configs {wanted!r}: expected one of {', '.join(CONFIGS)}", file=sys.stderr)
            return 2
        name = matches[0]
        params = CONFIGS[name]
        pipeline.load_source = original_load
        if params.get("_unsharp"):

            def sharpened(src, st, _orig=original_load):
                return _orig(src, st).filter(
                    ImageFilter.UnsharpMask(radius=2, percent=120, threshold=2)
                )

            pipeline.load_source = sharpened
        t0 = time.perf_counter()
        try:
            swap_engine(params)
        except Exception as exc:
            print(f"{name}: could not load ({exc})")
            continue
        load_t = time.perf_counter() - t0
        per_page, t_pages, confs = [], 0.0, []
        for s in sources:
            t = time.perf_counter()
            rec = pipeline.process_page(s, settings)
            t_pages += time.perf_counter() - t
            hyp = "\n".join(ln["text"] for ln in rec.lines)
            cer, wer = rates(hyp, refs[s.key])
            per_page.append((s.path.stem[:8], cer, wer))
            confs.append(rec.mean_conf)
        all_hyp_chars = sum(len(normalise(refs[s.key])) for s in sources)
        tot_cer = (
            sum(
                c * len(normalise(refs[s.key]))
                for (_, c, _), s in zip(per_page, sources, strict=True)
            )
            / all_hyp_chars
        )
        tot_words = sum(len(normalise(refs[s.key]).split()) for s in sources)
        tot_wer = (
            sum(
                w * len(normalise(refs[s.key]).split())
                for (_, _, w), s in zip(per_page, sources, strict=True)
            )
            / tot_words
        )
        rows.append(
            (
                name,
                tot_cer,
                tot_wer,
                sum(confs) / len(confs),
                t_pages / len(sources),
                load_t,
                per_page,
            )
        )
        print(
            f"{name:22} CER {tot_cer:6.2%}  WER {tot_wer:6.2%}  "
            f"quality {sum(confs) / len(confs):.3f}  "
            f"{t_pages / len(sources):4.1f}s/page  (load {load_t:.1f}s)"
        )
        print("    per page CER: " + "  ".join(f"{n}={c:.1%}" for n, c, _ in per_page))
    pipeline.load_source = original_load

    print("\n| config | CER | WER | mean read quality | s/page |")
    print("|---|---|---|---|---|")
    for name, cer, wer, q, tp, _, _ in rows:
        print(f"| {name} | {cer:.2%} | {wer:.2%} | {q:.3f} | {tp:.1f} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
