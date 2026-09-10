# UsefulText

Turns photos of document pages (and PDFs) into text and markdown, entirely on
your machine. A local app with its own window: drop in the photos, read them,
check the text beside the picture, correct a line where the engine slipped,
and export. OCR is RapidOCR on ONNX Runtime (CPU); the models ship inside the
`rapidocr` wheel, so nothing is downloaded or uploaded at run time. One of the
"Useful" family of tools, alongside
[media_downloader](https://github.com/adam-tuoa/media_downloader).

**Status:** version 0.3.0. Milestones 1 (the command line) and 2 (the app)
are complete; Milestone 3 packages the app for a machine without Python.
`PROJECT_DOCS/BRIEF.md` is the specification, `PROJECT_DOCS/PLAN_M2.md` the
record of how the app was built, `PROJECT_DOCS/PLAN_M3.md` the packaging.

## Install

Download from the [releases page](https://github.com/tuoa-tools/usefultext/releases):

- **macOS**: the zip for your Mac (`macos-arm64` for Apple Silicon,
  `macos-x64` for Intel); unzip and drag UsefulText to Applications. The app
  is not signed with an Apple developer certificate, so the first time macOS
  says it "cannot be opened because the developer cannot be verified":
  right-click the app, choose Open, then Open again. After that it opens
  normally.
- **Windows**: `UsefulText-windows-x64-setup.exe`, a per-user install with no
  administrator needed. SmartScreen may want "More info → Run anyway" once.
  The app opens in your browser (the app's own window is opt-in on Windows
  for now); close the tab and it exits by itself once nothing is being read.
- **Linux**: unpack the tarball and run `UsefulText/UsefulText`. With
  WebKitGTK and PyGObject installed it opens in its own window; otherwise in
  your browser.

The engine and its models are inside; nothing is downloaded or uploaded.

## Run from source

```
python3.13 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/usefultext-app
```

Windows: `.venv\Scripts\usefultext-app`. The app opens in its own window
(WKWebView on macOS, WebView2 on Windows, WebKitGTK on Linux) and asks, the
first time, where your library folder should live — `Documents/UsefulText`
is suggested. Closing the window quits; reading in progress pauses and
resumes next time. If the window cannot start on a machine, the app opens in
a browser tab instead (`--browser` asks for that outright) and exits by
itself two minutes after the tab is gone, once nothing is being read.
Settings and the log (`app.log`) live in the per-user app-data folder.

The same pipeline runs from the command line:

```
.venv/bin/usefultext Documents/ --out output/
```

## The app

- **Library.** One folder per document inside your library folder, holding
  the photos, the text and your corrections, so a document can be moved,
  copied to another machine or opened in Finder/Explorer. Drop a folder or
  photos onto the library to start a document named after them; "Remove
  from library" sends the folder to the trash, never further.
- **Pages.** Thumbnails in reading order, dragged into place or sorted by
  name, photo time or the printed page numbers found in running headers;
  leave a page out, replace it with a retake, add more. Photos are copied
  into the document's folder; in the window, "Choose a folder…" and "Choose
  photos or PDFs…" hand over paths, and Settings decides whether those are
  copied or moved. A blur check at add time and the warnings panel (pages
  that read poorly, likely repeat photos, a page number seen twice, a page
  number missing) say what to retake before and after reading.
- **Reading.** One button — Start, Pause, Resume — with progress, the time
  left and each page's read quality as it lands. Every page's result is
  written as soon as it is read, so a crash or a quit loses nothing; "Read
  again" re-reads on purpose. Read quality is the engine's own certainty,
  never a measure of accuracy; a page under the gate (0.70) is flagged.
- **Editor.** The page beside its text: one box per line on the picture,
  one editable line on the right, click either to find the other. The
  picture panel fits the whole page or the selected line, with zoom, and
  follows the selection. Corrections save as you type, show their origin,
  and can be reverted line by line; the engine's text is never changed
  behind your back. Suspect words — words the dictionary does not know — are
  highlighted with next/previous cycling across pages and an "ignore" that
  teaches the library; flags only, never automatic corrections. Two-column
  pages read column by column (see below).
- **Export.** Copy all the text; download Markdown, plain text, the per-page
  text files as a zip, JSONL, CSV or Word (`.docx`); open the folder.
- **Settings.** The library folder; copy or move for files named by path;
  columns (detect, or always one); PDF resolution; the read-quality gate;
  the blur threshold; the ignored words. A document can override the
  reading settings for itself.

Security, for a local app: the server binds to 127.0.0.1 on a free port,
answers only requests carrying this launch's secret (set once as an
HttpOnly cookie by the launch URL), and allows no other origin.

## What a document folder holds

The app's document folder and the command line's `--out` are the same
layout:

| File | Contents |
|---|---|
| `photos/` | the page photos and PDFs as added (the app only) |
| `job.json` | the app's page list, order and settings (the app only) |
| `pages/page_NNN_<photo>.txt` | plain text per page in reading order, named by position then photo; the first line is a bracketed provenance note (`[page 3 of 12 · IMG_0042.jpg · read quality 0.98 · rotated 90° · 2 columns]`), followed by any quality notes, a blank line, then the text |
| `document.md` | all pages with `## Page N` markers, best-effort `##` headings, paragraph breaks, and a `> ⚠` note on pages that read poorly |
| `document.txt` | all pages as plain text with `--- page N (photo) ---` separators |
| `document.jsonl` | one line per text region: `page, page_id, printed_page, source, line, order, role (body/header/footer), column (0 = full width), text, conf, bbox, clipped, low_conf_page, corrected, corrected_line` (bbox in full-resolution pixels of the upright page; `text` is always the raw OCR) |
| `report.csv` | per page: `id, filename, printed_page, regions, mean_conf, low_conf, sharpness, blurry, rotation, columns, dropped_regions, clipped_regions, furniture_lines, corrected_lines, elapsed_s, status, error, preview` |
| `previews/<id>.jpg` | an upright JPEG of each page (1600 px long edge), rotated as the read decided — what the editor shows; `--no-previews` skips them on the command line |
| `state.json` | the pipeline's results per page; a re-run skips pages already read (`--force` redoes them) |
| `corrections.json` | a person's edits; never written by the pipeline |
| `dictionary.txt` | in the library folder: the ignored words, one per line |

Every file is rewritten after each page, so an interrupted run leaves a
complete, consistent output for the pages finished so far.

## Corrections and warnings

Text is never changed automatically. A person's corrections live in
`corrections.json`, keyed by page id and line index, and are overlaid on the
OCR text whenever the outputs are regenerated: `document.md`, `document.txt`
and the per-page files show the corrected text, `document.jsonl` keeps the
raw OCR and marks the line `corrected` with the person's `corrected_line`,
and `report.csv` counts them. Each correction records the OCR text it
replaced, so if a page is read again a correction only re-attaches when the
line still reads the same; otherwise it is reported as stale. A correction
may contain newlines (to add a line the OCR missed); an empty one drops the
line.

Suspect words are checked on the text as shown (corrections applied,
headers and footers left out). A suspect is an OCR misread ("cight",
"me1ting"), a name, or a word the list lacks. The list is pyspellchecker's
American English plus British and Australian spellings added in
`usefultext/spellcheck.py`; a capitalised unknown word that recurs on three
or more pages of a document is taken for a name. On the six sample pages it
flags exactly the misreads.

The Word export has headings, paragraphs joined at the layout's paragraph
breaks, a page break between pages, quality notes in italics on pages that
read poorly, and the provenance in the file's properties.

Warnings, in the app's panel and at the end of a command-line run: pages
that read poorly, look blurry or failed (`retake`); two pages that read as
the same text, usually a repeat photo (`duplicate`); a printed page number
on two pages (`printed_duplicate`); and a number between the lowest and
highest seen that no page carries, naming the un-numbered pages that may be
it (`printed_gap`).

## The command line

`usefultext <inputs…> --out <folder>` (or `python -m usefultext`). Inputs
are files or folders of jpg/jpeg, png, heic/heif, tif, bmp, webp and pdf
(rendered at `--dpi`, default 200, clamped to ~9 MP per page). Pages are
ordered by natural filename sort (`img2` before `img10`); if the names look
random (UUIDs, hashes, no digits) the EXIF DateTimeOriginal is used instead.
`--sort name|time` overrides this; `--sort printed` reads the pages first,
then orders them by the page numbers found in running headers/footers,
printing the mapping with a note for every guess. Other flags: `--force`,
`--columns auto|1`, `--no-rotate`, `--keep-clipped`, `--keep-furniture`,
`--no-previews`, and the thresholds below (`--min-conf`, `--region-conf`,
`--blur-threshold`, `--heading-ratio`, `--box-thresh`, `--max-edge`).
`--help` lists them all.

## How a page is read

Calibrated on real phone photos of book pages; every threshold lives in
`usefultext/settings.py`.

- **EXIF orientation** is applied first, then a **downscale** to a 2500 px
  long edge before inference.
- **Blur check**: variance of the Laplacian over edge pixels only (a
  whole-frame variance tracked how much text was on the page rather than
  blur). Below the threshold (65) the page "looks blurry".
- **Sideways pages**: if the first read looks weak, or most text boxes are
  taller than they are wide, the page is tried at 90° and 270° with the
  line classifier off (so the wrong direction scores honestly low, ~0.6
  versus ~0.99) and re-read at the winner.
- **Upside-down pages**: the per-line angle classifier's decisions are read
  back from the first pass; if most lines were flipped, the page is re-read
  rotated 180° so the reading order is right.
- **Region filter**: regions below 0.5 confidence are dropped (counted in
  `dropped_regions`), separate from the 0.70 page gate.
- **Clipped text**: narrow regions touching the photo's left/right edge (the
  facing page peeking in) are kept out of the text but retained in the JSONL
  with `clipped: true`.
- **Detector threshold** 0.4: the engine default 0.5 missed strongly curved
  lines at the top of a book page.
- **Running headers and footers**: short lines within the top or bottom 12%
  of a page whose text, digits removed, recurs on at least two pages ("6 |
  JOHN KOTTER…", a bare page number) are removed from the text and markdown
  but kept in the JSONL with `role: header/footer`. A chapter title appears
  once, so it is never stripped. Detection is job-wide, so a single-page
  job never strips anything. Printed page numbers come from these lines.
- **Reading order**: top-to-bottom, then left-to-right within a line band
  (0.6 × median line height); side-by-side pieces of one line split by page
  curl are rejoined. Headings are short lines, narrower than a body line,
  that are either notably taller than the body (1.2×) or centred on the body
  column. A vertical gap above the median line gap (1.6×) is a paragraph
  break.
- **Columns** (`auto`, the default): a vertical gap in the middle of the
  page that almost no region crosses — at most a fifth of the text, such as
  a headline over both columns — at least a line height wide, with a few
  lines of several words on either side, splits the page into columns read
  left to right. A headline that crosses the gap is read on its own and
  splits the columns into the part above it and the part below.
  Photographed book pages have no such gap and stay one column, as do a
  contents list with its page numbers, a right-aligned attribution and
  ragged right edges; `1` turns the search off. Each column is grouped and
  judged for headings on its own; the page number at the top of each column
  of a spread is stripped like any other furniture. A photo of a two-column
  page taken at an angle falls back to one column.

## Using the pipeline from code

```python
from usefultext import Settings, discover_sources, run_job, sharpness_precheck

sources, sort_mode = discover_sources(["Documents"], sort="auto")
summary = run_job(
    sources,
    "output",
    Settings(),
    on_page=lambda rec, i, n, resumed: print(rec.page, rec.mean_conf),
    should_stop=lambda: False,
)  # pause = return True
```

`run_job` is synchronous and CPU-bound; call it from a worker thread, as
`app/worker.py` does.

## Development

```
.venv/bin/pip install -e ".[dev]"
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/python -m pytest -q
.venv/bin/uvicorn app.main:app --reload --port 8000     # the API alone; docs at /docs
cd frontend && npm install && npm run dev               # the UI at :5173, proxying /api
cd frontend && npm run build                            # -> app/static/, what usefultext-app serves
```

Frontend checks: `npm run lint`, `npm run typecheck`, `npm test`. CI
(`.github/workflows/ci.yml`) runs everything on Ubuntu, Windows and macOS.
Other tools: `tools/make_fixtures.py` (HEIC / PDF / EXIF / upside-down
fixtures from `Documents/`), `tools/eval_models.py` (CER/WER of OCR
configurations against `fixtures/reference/`), `tools/api_smoke.sh` (the
app end to end: add, read, kill -9, resume, export).

Packaging (`PROJECT_DOCS/PLAN_M3.md`): `pip install -e ".[build]"`, build the
UI, `python scripts/prepare_bundle.py` (copies the three OCR models out of
the rapidocr wheel — the app ships 32 MB of models, not the wheel's 260),
then `pyinstaller --noconfirm --clean packaging/UsefulText.spec` for
macOS/Linux or `python scripts/build_windows.py` plus Inno Setup on Windows;
`python scripts/smoke_bundle.py <executable>` reads real pages through a
built app's API. `.github/workflows/release.yml` does all of it for a `v*`
tag and publishes the artefacts.

```
usefultext/          the pipeline: ocr, preprocess, inputs, pipeline, layout, furniture, checks,
                     corrections, spellcheck, outputs, docx_export, fileio, settings; cli.py
app/                 the app: main (API), library, worker, spell, config, paths, desktop,
                     launcher, window; static/ is the built UI
frontend/            React 19, TypeScript, Vite, Tailwind, TanStack Query
tests/               pytest; frontend tests are vitest
tools/               fixture derivation, the evaluation harness, the API smoke test
PROJECT_DOCS/        BRIEF.md (spec), HANDOVER.md (record), PLAN_M2.md (the app, step by step)
```

`fixtures/reference/` holds hand-checked transcripts of the six sample
pages. The evaluation harness runs the whole pipeline under each
configuration and reports character/word error rates, so model or
preprocessing changes are measured rather than eyeballed. Results on the
six sample pages (Intel Mac, CPU), 2026-09-09:

| configuration | CER | WER | s/page |
|---|---|---|---|
| default: PP-OCRv6 small det + rec | **0.67%** | **2.18%** | 5.7 |
| PP-OCRv6 medium rec | 1.16% | 3.20% | 45.8 |
| PP-OCRv6 medium det + rec | 1.50% | 2.77% | 51.8 |
| PP-OCRv5 English mobile rec | 2.50% | 5.53% | 5.2 |
| PP-OCRv4 English mobile rec | 3.22% | 13.68% | 7.1 |
| PP-OCRv5 Chinese server rec | 11.69% | 41.19% | 67.8 |
| default + unsharp mask | 1.86% | 4.66% | 4.5 |

The bundled default stays. The English-specific models are older
generations and read worse; the medium models are 8× slower for no gain.

Known gaps (see the brief's v2 list): no deskew or perspective correction
(so a two-column page photographed at an angle reads as one column),
born-digital PDFs are OCR'd rather than read from their text layer, and page
order cannot be recovered when files have random names and identical
timestamps.
