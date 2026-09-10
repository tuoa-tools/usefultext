# PhotoText — Handover and Next Steps

_Status as of 2026-09-10. Milestone 1 (CLI) is complete and calibrated on the
sample photos; Milestone 2 (local app with web UI) is designed but not started.
`BRIEF.md` remains the specification; this document records what was built,
what was learned, and what to do next._

## 1. State of the repository

```
doc_reader.py            CLI only — argument parsing and progress printing
phototext/               the pipeline (import this from the Milestone 2 server)
  ocr.py                 RapidOCR wrapper, copied from the redaction POC and extended
  preprocess.py          load (HEIC, EXIF), downscale, blur check, rotation helpers
  inputs.py              file discovery, natural/EXIF ordering, PDF page expansion
  pipeline.py            process_page(), run_job() — resumable, per-page writes
  layout.py              reading order, headings, paragraph breaks, edge clipping
  furniture.py           running header/footer detection, printed page numbers
  outputs.py             state.json, pages/*.txt, document.md, document.jsonl, report.csv
  settings.py            every threshold, with the defaults that were calibrated
tests/                   23 unit tests (pytest), all passing
tools/make_fixtures.py   derives HEIC / EXIF-rotated / upside-down / PDF fixtures
tools/eval_models.py     CER/WER harness against fixtures/reference/
fixtures/reference/      hand-checked transcripts of the six sample pages
PROJECT_DOCS/BRIEF.md    the specification (settled decisions — do not re-derive)
README.md                usage, outputs, heuristics, evaluation results
```

Git history: four commits on `main`. `Documents/`, `output*/`,
`fixtures/derived/` and `redaction_detection_poc/` are ignored; the POC folder
is reference material only and must not be edited or committed.

Environment: Python 3.13 (x86_64 macOS), `.venv` with `requirements.txt`
(rapidocr 3.9.2, onnxruntime 1.23, pillow, pillow-heif, pymupdf, numpy).
The three default RapidOCR models ship inside the rapidocr wheel; nothing is
downloaded at run time, verified by running with all sockets blocked.

Run: `.venv/bin/python doc_reader.py Documents/ --out output/ --sort printed`
Tests: `.venv/bin/python -m pytest -q`
Evaluation: `.venv/bin/python tools/eval_models.py`

## 2. What the pipeline does per page

1. Load (HEIC via pillow-heif; PDF pages rendered at 200 dpi, clamped to 9 MP),
   apply EXIF orientation, downscale to a 2500 px long edge.
2. Blur check: Laplacian RMS over edge pixels (gradient ≥ 20), flag below 65.
3. Read at 0° with the angle classifier on, detector box threshold 0.4.
4. If the read looks weak, or most text boxes are tall (sideways page), trial
   90° and 270° on a 1000 px copy with the classifier off and re-read at the
   winner. If the classifier flipped most lines, re-read at 180°. A single
   flipped line on an upright page is re-read with the classifier off.
5. Drop regions below 0.5 confidence (counted); drop narrow regions touching
   the left/right photo edge (facing page), kept in JSONL as `clipped`.
6. Group regions into lines (0.6 × median height, plus a rule that rejoins
   lines split by page curl); mark headings (short, narrower than body, and
   either ≥ 1.2× body height or centred); mark paragraph gaps.
7. Page gate: mean confidence < 0.70 or zero regions → `low_conf`; the text is
   never written without that flag.

After every page the job re-runs header/footer detection across all pages
read so far, saves `state.json`, and regenerates every output file. A re-run
skips unchanged files; `--force` redoes them; `--sort printed` reorders by
the page numbers found in footers, filling gaps with un-numbered pages.

## 3. Results on the sample set (pages 6–11 of a book, phone JPEGs)

| page | photo | read quality | flags |
|---|---|---|---|
| 6 | a1835f29 | 0.99 | heading found, 2 curved lines recovered, 5 clipped fragments removed |
| 7 | cc36b71b | 0.98 | blurry (top half); 4 misreads |
| 8 | 5cd3aa12 | 0.99 | sideways → rotated 90°, blurry |
| 9 | c4a3385a | 0.99 | sideways → rotated 90° |
| 10 | af6310fc | 0.99 | sideways → rotated 90°, blurry |
| 11 | 8944949b | 0.99 | sideways → rotated 90° |

Character error rate against the hand-checked transcripts: **0.67%** (word
error 2.18%). Alternatives measured and rejected: PP-OCRv6 medium (1.16%, 8×
slower), PP-OCRv5/v4 English mobile (2.5% / 3.2%), PP-OCRv5 server (11.7%),
unsharp masking (1.86%). Timing on an Intel Mac: ~2–3 s per upright page,
~6–7 s per sideways page, 1–2 s model load.

## 4. Things that were learned the hard way (keep)

- RapidOCR per-call flags are sticky between calls; every flag is always
  passed explicitly.
- Box corner order flips for tilted vertical lines; width/height are chosen
  by edge direction, never by corner index.
- Whole-frame Laplacian variance measures how much text is on the page, not
  blur. Edge-restricted RMS separates soft (45–58) from sharp (70–113).
- The detector's default 0.5 box threshold silently drops strongly curved
  top lines; 0.4 recovers them with no loss elsewhere.
- The angle classifier hides upside-down pages (quality 0.94, order
  reversed). Its per-line labels are read from the first pass at no cost.
- Book chapter headings can be only 1.15× body height; centred-and-narrow
  is the reliable cue. Full-width curled body lines reach 1.3×.
- Read quality is engine certainty: page 7's blurred lines read at 0.94–0.98
  while containing errors. The blur flag exists for exactly this.
- Timestamps on exported photos can be identical to the second; printed
  page numbers recovered the order where names and times could not.

## 5. Milestone 2 — design decisions from the review

Settled:

- **Local app, browser-based UI, media_downloader pattern**: FastAPI on
  localhost, one worker thread pulling from a queue, `run_job()` unchanged.
  Target a pywebview window with an "open in browser" fallback.
- **Library folder** chosen on first start, changeable in settings. Added
  files are copied into the document's folder (default) with a "move
  instead" option. UI wording is "added to your library", never "uploaded".
- **One document per folder / subfolder; one job per document.** Library
  view lists status, page count, pages that read poorly, dates.
- **Explicit page list owned by the job** (order, excluded, replaced) rather
  than derived from the folder each run. Reorder by drag, printed number,
  name or time; remove; insert a retake in place.
- **Corrections live in their own file** (`corrections.json`), never in
  `state.json`. Exports use corrected text; each line records machine or
  human origin; "revert to OCR" per line. No automatic correction, ever.
- **Side-by-side editor**: rotated JPEG preview per page written at
  processing time (also solves HEIC in browsers), click line ↔ box
  highlight, next/previous flagged page, autosave.
- **Spellcheck**: browser-native underlines in the editor (free) plus an
  app-side word-list pass giving per-page suspect counts and Next/Previous
  cycling, with a per-library custom dictionary ("ignore"). Flags only.
- **Warnings** in the ordering view: duplicate pages (near-identical text),
  gaps in printed numbers, "needs retake" list from blur/quality flags.
- **Outputs**: per-page files named by position and photo, with a one-line
  provenance header; combined `document.md` and a combined `.txt`; JSONL and
  CSV as now.
- Warm the engine at server start; show an ETA on batches.
- "Read quality", never "accuracy", throughout the UI.

Open:

- `.docx` export (likely wanted; python-docx is a light dependency).
- Whether the per-page `.txt` header should be a comment line or a sidecar.
- pywebview spellcheck on Windows/Linux — check on a real machine in M3.
- RAG: local stack stays offline; any hosted model is a per-document opt-in.

## 6. Next steps, in order

1. **Pipeline prep for the UI** (1–2 days): per-page preview JPEGs; explicit
   job page list with exclude/replace; `corrections.json` overlay applied at
   export; per-page provenance header and file naming; combined `.txt`;
   duplicate-page and printed-number gap warnings in `JobSummary`.
2. **Backend** (2–3 days): FastAPI app, job store over the library folder,
   single worker thread, progress via polling or SSE (match
   media_downloader), endpoints for add/order/start/pause/cancel/edit/export.
3. **UI** (4–6 days): library, add-and-order view with thumbnails and
   warnings, progress with quality chips, side-by-side editor with
   spellcheck cycling, exports and copy-all, settings.
4. **Spellcheck pass** (1 day): word list or pyspellchecker, custom
   dictionary, suspect positions per line.
5. **Milestone 3 packaging**: PyInstaller with onnxruntime DLLs collected,
   rapidocr models bundled and pointed to via `PHOTOTEXT_MODEL_DIR`,
   pillow-heif native libs, pywebview; GitHub Actions per platform as in
   media_downloader v0.4.1; test on a machine without Python.

## 7. Parking lot (v2)

Deskew/perspective correction; two-column detection; reading born-digital
PDFs from their text layer instead of OCR; search across the library;
table detection (resist); local RAG over the JSONL.
