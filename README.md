# UsefulText

Turns a folder of photographed document pages (and PDFs) into text and
markdown, entirely on your machine. OCR is RapidOCR on ONNX Runtime (CPU);
the models ship inside the `rapidocr` wheel, so nothing is downloaded or
uploaded at run time. Formerly PhotoText; one of the "Useful" family of
tools alongside [media_downloader](https://github.com/adam-tuoa/media_downloader).

**Status:** Milestone 1, the command line, is complete and calibrated on real
photos. Milestone 2, a local app with a browser UI (library, page ordering,
side-by-side editor, exports), is in progress — see
`PROJECT_DOCS/PLAN_M2.md`. `PROJECT_DOCS/BRIEF.md` is the specification.

```
python3.13 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/usefultext Documents/ --out output/
```

`python -m usefultext` does the same. Windows: `.venv\Scripts\usefultext`.

## What you get in `--out`

| File | Contents |
|---|---|
| `pages/page_NNN_<photo>.txt` | plain text per page in reading order, named by position then photo; the first line is a bracketed provenance note (`[page 3 of 12 · IMG_0042.jpg · read quality 0.98 · rotated 90°]`), followed by any quality notes, a blank line, then the text |
| `document.md` | all pages with `## Page N` markers, best-effort `##` headings, paragraph breaks, and a `> ⚠` note on pages that read poorly |
| `document.txt` | all pages as plain text with `--- page N (photo) ---` separators |
| `document.jsonl` | one line per text region: `page, page_id, printed_page, source, line, order, role (body/header/footer), text, conf, bbox, clipped, low_conf_page, corrected, corrected_line` (bbox in full-resolution pixels of the upright page; `text` is always the raw OCR) |
| `report.csv` | per page: `id, filename, printed_page, regions, mean_conf, low_conf, sharpness, blurry, rotation, dropped_regions, clipped_regions, furniture_lines, corrected_lines, elapsed_s, status, error, preview` |
| `previews/<id>.jpg` | an upright JPEG of each page (1600 px long edge), rotated as the read decided — what the app's editor shows; `--no-previews` skips them |
| `state.json` | job state; a re-run skips pages already read (use `--force` to redo) |
| `corrections.json` | a person's edits (see below); never written by the pipeline |

Every file is rewritten after each page, so an interrupted run leaves a
complete, consistent output for the pages finished so far. Re-run the same
command to resume.

"Read quality" (`mean_conf`) is the OCR engine's own certainty, never a
measure of accuracy. A page with mean quality below 0.70, or with nothing
readable, is flagged `low_conf` and its text is never shown without that flag.

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
line. The app (Milestone 2) is the editor for this file.

At the end of a run the CLI prints warnings, also available to the app:
pages that read poorly, look blurry or failed (`retake`); two pages that read
as the same text, usually a repeat photo (`duplicate`); a printed page number
on two pages (`printed_duplicate`); and a number between the lowest and
highest seen that no page carries, naming the un-numbered pages that may be
it (`printed_gap`).

## Inputs and page order

jpg/jpeg, png, heic/heif, tif, bmp, webp and pdf (rendered at `--dpi`,
default 200, clamped to ~9 MP per page). Pages are ordered by natural
filename sort (`img2` before `img10`); if the names look random (UUIDs,
hashes, no digits) the EXIF DateTimeOriginal is used instead. `--sort
name|time` overrides this. The ordered list is printed before OCR starts.

`--sort printed` reads the pages first, then orders them by the page
numbers found in running headers/footers. Pages without a number fill the
gaps in capture order (or go last), and the resulting mapping is printed
with a note for every guess, so check it. On the sample set (random file
names, identical timestamps) this recovered the true order 6–11.

## Running headers and footers

Short lines within the top or bottom 12% of a page whose text, digits
removed, recurs on at least two pages are treated as running headers or
footers ("6 | JOHN KOTTER…", "OUR ICEBERG IS MELTING | 7", a bare page
number). They are removed from the text and markdown but kept in the JSONL
with `role: header/footer`; `--keep-furniture` keeps them in the text. A
chapter title appears once, so it is never stripped. Detection is job-wide,
so a single-page job never strips anything.

## Preprocessing, as calibrated on the sample photos

- **EXIF orientation** is applied first.
- **Downscale** to a 2500 px long edge before inference.
- **Blur check**: variance of the Laplacian measured over edge pixels only
  (a whole-frame variance tracked how much text was on the page rather than
  blur). Below `--blur-threshold` (65) the page is flagged "looks blurry".
- **Sideways pages**: if the first read looks weak, or most text boxes are
  taller than they are wide, the page is tried at 90° and 270° with the
  line classifier off (so the wrong direction scores honestly low, ~0.6
  versus ~0.99) and re-read at the winner.
- **Upside-down pages**: the per-line angle classifier's decisions are read
  back from the first pass; if most lines were flipped, the page is re-read
  rotated 180° so the reading order is right. A single flipped line on an
  upright page is re-read with the classifier off and the better read kept.
- **Region filter**: regions below 0.5 confidence are dropped (counted in
  `dropped_regions`), separate from the 0.70 page gate.
- **Clipped text**: narrow regions touching the photo's left/right edge (the
  facing page peeking in) are kept out of the text but retained in the JSONL
  with `clipped: true`. `--keep-clipped` disables this.
- **Detector threshold** 0.4 (`--box-thresh`): the engine default 0.5 missed
  strongly curved lines at the top of a book page.

## Layout heuristics

Reading order is top-to-bottom, then left-to-right within a line band
(0.6 × median line height); side-by-side pieces of one line split by page
curl are rejoined. Headings are short lines, narrower than a body line, that
are either notably taller than the body (`--heading-ratio`, 1.2) or centred
on the body column. Single-column only; running headers/footers are kept.

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

`run_job` is synchronous and CPU-bound; call it from a worker thread.

## Development

```
.venv/bin/pip install -e ".[dev]"
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/python -m pytest -q
.venv/bin/python tools/make_fixtures.py     # HEIC / PDF / EXIF / upside-down fixtures from Documents/
.venv/bin/python tools/eval_models.py       # CER/WER of OCR configurations vs fixtures/reference/
```

CI (`.github/workflows/ci.yml`) runs the same checks on Ubuntu, Windows and macOS (Apple Silicon).

```
usefultext/          the pipeline: ocr, preprocess, inputs, pipeline, layout, furniture, outputs, settings; cli.py
app/                 the local app (Milestone 2): paths, desktop, launcher now; API, library, worker next
tests/               pytest
tools/               fixture derivation and the evaluation harness
PROJECT_DOCS/        BRIEF.md (spec), HANDOVER.md (Milestone 1 record), PLAN_M2.md (Milestone 2 plan)
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

Known v1 gaps (see the brief's v2 list): no deskew or perspective correction,
no two-column detection, born-digital PDFs are OCR'd rather than read from
their text layer, and page order cannot be recovered when files have random
names and identical timestamps.
