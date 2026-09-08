# PhotoText — Milestone 1 (CLI)

Turns a folder of photographed document pages (and PDFs) into text and
markdown, entirely on your machine. OCR is RapidOCR on ONNX Runtime (CPU);
the models ship inside the `rapidocr` wheel, so nothing is downloaded or
uploaded at run time. See `PROJECT_DOCS/BRIEF.md` for the full specification.

```
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python doc_reader.py Documents/ --out output/
```

## What you get in `--out`

| File | Contents |
|---|---|
| `pages/page_NNN.txt` | plain text per page in reading order; low-quality or blurry pages carry a bracketed note on the first line |
| `document.md` | all pages with `## Page N` markers, best-effort `##` headings, paragraph breaks, and a `> ⚠` note on pages that read poorly |
| `document.jsonl` | one line per text region: `page, source, line, order, text, conf, bbox, clipped, low_conf_page` (bbox in full-resolution pixels of the upright page) |
| `report.csv` | per page: `filename, regions, mean_conf, low_conf, sharpness, blurry, rotation, dropped_regions, clipped_regions, elapsed_s, status, error` |
| `state.json` | job state; a re-run skips pages already read (use `--force` to redo) |

Every file is rewritten after each page, so an interrupted run leaves a
complete, consistent output for the pages finished so far. Re-run the same
command to resume.

"Read quality" (`mean_conf`) is the OCR engine's own certainty, never a
measure of accuracy. A page with mean quality below 0.70, or with nothing
readable, is flagged `low_conf` and its text is never shown without that flag.

## Inputs and page order

jpg/jpeg, png, heic/heif, tif, bmp, webp and pdf (rendered at `--dpi`,
default 200, clamped to ~9 MP per page). Pages are ordered by natural
filename sort (`img2` before `img10`); if the names look random (UUIDs,
hashes, no digits) the EXIF DateTimeOriginal is used instead. `--sort
name|time` overrides this. The ordered list is printed before OCR starts.

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

## Using the pipeline from code (Milestone 2)

```python
from phototext import Settings, discover_sources, run_job, sharpness_precheck

sources, sort_mode = discover_sources(["Documents"], sort="auto")
summary = run_job(sources, "output", Settings(),
                  on_page=lambda rec, i, n, resumed: print(rec.page, rec.mean_conf),
                  should_stop=lambda: False)      # pause = return True
```

`run_job` is synchronous and CPU-bound; call it from a worker thread.

## Development

```
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python tools/make_fixtures.py     # HEIC / PDF / EXIF / upside-down fixtures from Documents/
```

Known v1 gaps (see the brief's v2 list): no deskew or perspective correction,
no two-column detection, born-digital PDFs are OCR'd rather than read from
their text layer, and page order cannot be recovered when files have random
names and identical timestamps.
