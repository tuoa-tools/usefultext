# BRIEF.md — PhotoText (working title): bulk image → text OCR app

## What this is

A self-contained, local web app that converts photos of document pages (and
PDFs) into text/markdown. Modelled directly on `adam-tuoa/media_downloader`
(v0.4.1): FastAPI backend, browser UI, packaged per-platform installers via
GitHub Actions. Built to hand to a non-technical friend.

Primary use case: a person photographs a document (e.g. ~80 pages, JPEG from
an Android phone), bulk-uploads the images, and gets back a combined
transcript plus per-page text.

## Non-negotiable design decisions (settled — do not re-derive)

1. **OCR engine: RapidOCR (onnxruntime, CPU).** The wrapper already exists —
   `ocr.py` in this repo, proven in production on real scanned documents.
   Reuse it; extend rather than replace. No cloud OCR, no LLM-decoder OCR
   (hallucination risk for a transcription tool).
2. **Models bundled at build time.** RapidOCR downloads models on first use
   by default. The packaged app must ship them inside the installer and point
   RapidOCR at the bundled path when frozen. First run on the friend's
   machine must need zero network.
3. **Local only.** Files never leave the machine. No telemetry.
4. **Incremental results + resumable queue.** Results write per-page as
   processed (JSON state file per job). Pause = stop pulling from queue;
   resume = skip completed pages. A crash mid-batch must not lose completed
   pages. (Hard-won lesson from a prior 40-minute batch run with end-only
   writes.)
5. **CPU-bound OCR runs OFF the event loop** — `run_in_executor` /
   ThreadPoolExecutor (RapidOCR releases the GIL during ONNX inference;
   threads are fine). The UI must stay responsive during an 80-image batch.
6. **Windows asyncio:** if any subprocess use appears, remember the
   media_downloader lesson — Proactor event loop policy on Windows. Prefer
   in-process calls; RapidOCR needs no subprocess.

## Inputs

- Images: .jpg/.jpeg, .png, **.heic/.heif** (via `pillow-heif`, registered at
  startup), .tif, .bmp, .webp
- PDFs: render pages at 200 dpi via PyMuPDF (`fitz`), clamp renders to ~9MP
  per page (oversized media boxes exist in the wild)
- Bulk upload (multi-select and/or drag-drop of many files)
- **Page order:** default sort by filename (natural sort: img2 < img10),
  fall back to EXIF DateTimeOriginal when names are unhelpful; show the
  ordered list in the UI before processing starts, with drag-to-reorder if
  cheap, or at minimum a "sort by name / by time" toggle.

## Preprocessing (v1) — calibrated against real sample photos

Two real samples (book pages, Android JPEGs ~4000px) established these as
required, not optional:

- **Sharpness pre-check at upload:** variance-of-Laplacian per image;
  below-threshold images flagged "looks blurry — consider retaking" in the
  UI *before* processing starts. Cheap (ms per image), huge UX win for an
  80-image batch.
- **Whole-page rotation handling:** respect EXIF orientation first
  (`PIL.ImageOps.exif_transpose`); when EXIF is absent/wrong, detect
  sideways pages by trying OCR at 0° and 90° and keeping the orientation
  with the higher (regions × mean confidence) score. Only trigger the
  second pass when the first looks weak. Real photos WILL arrive rotated
  90° — this is a main path.
- Enable RapidOCR's angle classifier (per-line 180° flips)
- **Region-level confidence filter:** drop individual text regions below
  ~0.5 confidence (bleed-through ghost text from the page's reverse side
  reads as low-conf garbage). This is separate from the page-level 0.70
  gate.
- Downscale very large phone photos to a sane long edge (~2500px) before
  inference — speeds up with negligible accuracy cost
- No deskew/perspective correction in v1 (v2 candidate). Fingers holding
  pages, page curl: no mitigation — the confidence gate labels the damage
  honestly.
- Book-specific noise (running headers/footers like "TITLE | 7"): kept in
  v1 output (honest transcription); optional strip is a v2 candidate.

## Output (shaped for future RAG reuse — structure now, no RAG features)

Per job, an output folder containing:
- `pages/page_NNN.txt` — plain text per page, reading order
- `document.md` — combined markdown: `## Page N` markers between pages;
  best-effort headings (see below)
- `document.jsonl` — one line per text region: `{page, text, conf, bbox}`
- `report.csv` — per page: filename, regions, mean confidence, low_conf flag
- UI surfaces the low-confidence pages prominently: "these N pages read
  poorly — consider re-photographing"

**Markdown headings (best effort, v1):** RapidOCR emits no style info — bold/
italic are OUT of scope. Headings only, by heuristic: region height notably
above the page median line height (e.g. >1.5×) and short line length →
`##`; be conservative (false headings are worse than missed ones).

**Reading order:** sort regions top-to-bottom, then left-to-right within a
line band (regions whose vertical centres fall within ~0.6× median line
height of each other are one line; join with spaces). Single-column
assumption for v1; note two-column detection as v2.

**Confidence gate:** per-page mean confidence < 0.70, or zero regions, →
flag low_conf (reuse the constant/idea from `ocr.py`). Never present a
low-conf page's text without its flag.

## UI (mirror media_downloader's feel)

- Single page: drop zone → ordered file list → Start / Pause / Cancel →
  per-page progress with confidence chips → results panel with download
  buttons (txt zip / md / jsonl) and a copy-all button
- Progress via polling or SSE (match whatever media_downloader uses)
- Settings: output folder, DPI for PDFs, confidence threshold

## Packaging & distribution

- Same pattern as media_downloader v0.4.1: GitHub Actions building
  Windows setup.exe, macOS zip, Linux tar.gz; app opens in browser; Quit
  button stops the server
- PyInstaller notes: onnxruntime needs its DLLs collected; bundle RapidOCR
  model files as data and set the model-path config when
  `sys._MEIPASS`/frozen; pillow-heif native libs must be collected
- Verify the packaged app on a machine without Python before releasing

## Milestones

1. **Core CLI** (no UI): folder of images → outputs above. Prove reading
   order, headings heuristic, HEIC, PDF path. Testable in a day.
2. **FastAPI + web UI** with queue/pause/resume, wrapping milestone 1.
3. **Packaging** via the media_downloader Actions pattern; test installers.
4. v2 candidates parking lot: deskew/perspective, two-column, reorder UI,
   drag-in of a whole folder, table detection (big jump — resist).

## Known gotchas file (carry forward)

- HEIC without pillow-heif fails at open, not at upload — register early,
  error clearly
- OneDrive-synced input folders may hydrate on first read (slow first run)
- Natural sort matters: page_10 after page_9, not after page_1
- Confidence means "engine certainty", not correctness — wording in UI
  should say "read quality", never "accuracy"
