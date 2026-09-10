# UsefulText (was PhotoText) — Milestone 2 plan: the local app

_Written 2026-09-10 from `HANDOVER.md` §5–6 and a fresh read of
`adam-tuoa/media_downloader` at v0.6.1. The reference has moved on since the
brief named v0.4.1, in UsefulText's favour: same launcher / worker / static-UI
shape, plus a Library view, Settings and Help dialogs, and a settled
"pywebview first, browser fallback" decision — all things this design already
assumes. `BRIEF.md` and `HANDOVER.md` stay authoritative for **what**; this
file is **how, in what order, and what the handover left out**._

## 0. What the handover review turned up

Things the M2 design assumes but the code or the browser does not yet allow.
Each is folded into a step below.

1. **`state.json` keys are absolute paths** (`PageSource.key` calls
   `resolve()`). Moving or renaming the library folder — "changeable in
   settings" — would invalidate every page and re-read the lot. Keys must be
   relative to the document folder before the app writes its first state file.
2. **A browser cannot hand the server a file path.** Drag-and-drop delivers
   bytes, so "add" is always a copy. "Move instead" is only possible for files
   named by path: a typed folder in the add view now, a native dialog once the
   pywebview window exists. The UI must offer both routes and say so.
3. **Outputs are named by position and never cleaned up.** `write_outputs`
   only writes, so reordering or excluding a page leaves stale
   `pages/page_NNN.txt` files behind. The writer needs to remove what it did
   not just write.
4. **`--sort printed` reorders inside `run_job`** and reassigns `page`. With
   an explicit, job-owned page list that must move out to the app: "Sort by
   printed number" rewrites the page list from the furniture results already
   in `state.json`; the app never passes `sort="printed"`.
5. **Pause and cancel are the same operation** on a per-page resumable job:
   stop pulling from the queue, keep what is done. The brief lists both, and
   "Cancel" reads as "throw it away", which nothing here does. One button
   that behaves like a media player's play/pause (Start → Pause → Resume)
   plus a secondary "Read again" (= `force`).
6. **Two writers of the output files.** The worker regenerates every output
   after each page; saving a correction regenerates them too. Both use atomic
   writes, but they need a per-document lock so a save during a run cannot
   interleave with `finalize()`.
7. **Previews need the rotation**, which is only known after OCR, so the
   upright preview is written by the pipeline; the thumbnails for the ordering
   view (before any OCR) are the app's job and can be lazy.
8. **Spellcheck is flags only.** The 2026-09-09 decision (no word-list
   correction, zero-shot reading) and the 2026-09-10 design (suspect counts,
   Next/Previous cycling, ignore list) agree. Written down here so it is not
   re-litigated: the app never changes text; a person does.

## 1. Decisions — confirmed 2026-09-10

All nine confirmed by Adam on 2026-09-10; items 3 and 7 changed in the
confirming. The plan below assumes them.

1. **UI stack: React 19 / TypeScript / Vite / Tailwind 4 / TanStack Query**,
   copied from media_downloader (`api.ts`, polling, `Modal`, `IconButton`,
   Library and Settings components carry over). The editor — preview with
   box overlay, line list, click sync, flagged-page cycling, autosave — is
   the most stateful UI in either project; plain HTML/JS would cost more
   than the Node toolchain saves. Node 24 is already on the Mac.
2. **The document folder is the job's output folder.** Photos go in
   `photos/`, previews in `previews/`, the CLI's outputs stay at the top
   level next to `state.json`. One folder = one document = one `run_job`
   call, no database.
3. **No Cancel** (item 5 above). One play/pause-style button whose label
   follows the state — Start, Pause, Resume — and a secondary "Read again"
   that asks first when the document has corrections.
4. **Corrections are per line**, keyed by page id + line index, and carry
   the OCR text they replaced so a re-read can re-attach or discard them.
   A corrected line may contain newlines (how a missed line is added); no
   separate insert/delete operations in v1.
5. **Per-page `.txt` provenance is a first bracketed line**, the same
   convention the quality notes already use, not a sidecar file. The UI's
   copy-all strips it.
6. **JSONL stays one row per OCR region**, raw text unchanged, plus
   `corrected: bool` and `corrected_line` when a person edited that line.
7. **"Remove from library" moves the folder to the OS trash** (`send2trash`)
   after a confirmation that names the folder and says it can be recovered
   from the trash. The app never deletes a photo any other way.
8. **The pywebview window is step 5**, after everything works in a browser
   tab, exactly as media_downloader sequenced it.
9. **Server package is `app/`** at the repo root, mirroring
   media_downloader's `backend/app/` file for file so its patterns copy
   across by name.
10. **The name is UsefulText** ("Useful" is the family prefix for Adam's
    tools; media_downloader becomes UsefulMedia). The pipeline package,
    env vars, app-data folder, window title and bundle id all take it; the
    rename is the first item of step 0, before any app code exists.
11. **Hosted on GitHub, public, under the `tuoa-tools` organisation**, as
    `tuoa-tools/usefultext` (lowercase: PyPI convention, and the package,
    distribution and console script share the name). Nothing exists on
    GitHub yet, so there is nothing to migrate later. MIT licence; a sponsor link is a
    `FUNDING.yml` that can be added any time and decides nothing now.
12. **All three platforms, Mac tested first.** The friend is probably on a
    Mac; Adam tests on Mac and Windows. The pywebview window (step 5) is
    proved on the Mac; Milestone 3 builds Mac, Windows and Linux as
    media_downloader does.

## 2. Shape of the app

### Repo layout

```
usefultext/          the pipeline (M1) — grows by corrections.py, checks.py, previews.py, spellcheck.py
app/                FastAPI + launcher (media_downloader names)
  main.py           routes and pydantic models
  library.py        the library folder: documents, job.json, page list, add/copy/move, trash
  worker.py         one worker thread, queue, pause/resume, progress, engine warm-up
  paths.py          app-data dir (platformdirs), settings.json
  desktop.py        reveal a folder in Finder/Explorer — verbatim copy
  launcher.py       free port, launch token, open browser, single instance — copy, env vars renamed USEFULTEXT_*
  static/           built UI (gitignored)
frontend/           Vite + React + TS + Tailwind, seeded from media_downloader
tests/              pytest: pipeline tests (as now) + API tests with a fake run_job
usefultext/cli.py   was doc_reader.py; still logic-free; `usefultext` console script, `python -m usefultext`
pyproject.toml      replaces requirements*.txt: distribution `usefultext`, packages usefultext + app; extras [dev], [build]
```

### The library on disk

```
<library>/                       chosen on first start; path in app-data settings.json
  dictionary.txt                 spellcheck "ignore" words, one per line
  <Document title>/              one document = one job = run_job's out_dir
    job.json                     app-owned: page list, status, summary counts, settings overrides
    photos/                      the files as added (copied or moved), original names kept
    previews/<page id>.jpg       upright preview after OCR (1600 px long edge, q80)
    previews/<page id>.thumb.jpg EXIF-oriented thumbnail (320 px), made lazily on first request
    state.json                   pipeline-owned OCR results, as now (keys now relative)
    corrections.json             human edits; the pipeline never reads or writes it
    pages/page_003_IMG_0042.txt  per-page text, first line = provenance
    document.md  document.txt  document.jsonl  report.csv
```

`job.json`:

```json
{"version": 1, "id": "k3f9a2", "title": "Our Iceberg Is Melting",
 "created_at": "…", "updated_at": "…", "status": "new|paused|done|error",
 "settings": {"pdf_dpi": 200},
 "summary": {"pages": 12, "read": 9, "low_conf": 1, "blurry": 2, "errors": 0, "corrected_lines": 4},
 "pages": [
   {"id": "p1", "file": "photos/IMG_0042.jpg", "page_index": 0, "excluded": false,
    "added_at": "…", "replaced_from": null}
 ]}
```

Order is array order. Excluded pages keep their entry so they can come
back. A retake replaces `file` on the same entry and records
`replaced_from`; the old photo stays in `photos/` untouched. Files in
`photos/` that are not in the list are shown as "not part of the document —
add them?" rather than picked up silently. `queued` and `running` are
in-memory states owned by the worker, never written to disk, so a crash
leaves `paused` and a plain Resume.

### Identity

- `PageSource` gains `base: Path | None` (key becomes `relative path::index`
  when set) and `id: str | None` (the job's page id; the pipeline names
  previews by it). The CLI passes neither and behaves as today.
- `PageRecord` carries `id`. Everything the UI addresses — previews,
  corrections, suspects — is keyed by page id, never by position, so
  reordering renames only the output files.

### The worker

One `threading.Thread` pulling document ids from a `queue.Queue`; OCR is
CPU-bound and one engine instance keeps the machine usable. Per run a
`threading.Event` is the `should_stop` callback; Pause sets it, `run_job`
returns `stopped_early`, status becomes `paused`. There is no cancel: the
pages already read are the result so far. Resume re-queues; the
existing fingerprint skip makes it continue. `on_page` updates an in-memory
`Progress` (done/total, current label, per-page seconds → ETA after two
pages, last record's quality flags) and the `summary` block in `job.json`.
The thread calls `ocr.available()` first thing so the models are warm before
the first job; `/api/health` reports `engine: loading | ready | failed`.
Exactly media_downloader's `Manager` shape, with a thread instead of asyncio
tasks because there is no subprocess and only ever one job at a time.

### API

```
GET  /launch?token=…                        cookie + redirect (verbatim)
GET  /api/health                            version, desktop, engine state, library set?
GET/PUT /api/settings                       library_dir, add_mode copy|move, pdf_dpi, min_page_conf, blur_threshold
GET  /api/library                           documents with summary counts and dates
POST /api/library {title}                   create the folder
DELETE /api/library/{doc}                   to the OS trash (the UI confirms first)
POST /api/library/{doc}/reveal              open the folder
GET  /api/documents/{doc}                   job.json + progress + per-page flags + warnings
POST /api/documents/{doc}/files             multipart add (drop zone) → photos/, sharpness precheck
POST /api/documents/{doc}/add-path {path, move}   files or a folder named by path
PUT  /api/documents/{doc}/pages             the whole page list (reorder, exclude, replace)
POST /api/documents/{doc}/pages/sort {by}   name | time | printed → rewrites the list
POST /api/documents/{doc}/start|pause|resume  (start accepts force)
GET  /api/documents/{doc}/pages/{pid}       lines (OCR + correction + origin), regions, preview size, suspects
PUT  /api/documents/{doc}/pages/{pid}/lines/{n} {text}     save a correction
DELETE /api/documents/{doc}/pages/{pid}/lines/{n}          revert to OCR
GET  /api/documents/{doc}/previews/{pid}(.thumb).jpg
GET  /api/documents/{doc}/export/{md|txt|jsonl|csv|pages.zip|docx}
GET/PUT /api/dictionary                     the ignore list
POST /api/quit
```

Bounding boxes come back in full-resolution upright coordinates with
`width`/`height`, and the UI scales them to the preview it rendered.

### UI

- **Library**: cards/rows — title, status, "9 of 12 read", flagged counts,
  dates; New document; Settings and Help as dialogs (from media_downloader).
- **Document → Pages**: drop zone and "add from a folder", thumbnail list
  with drag reorder, sort menu (name / time / printed number), exclude,
  replace with a retake, blur chips from the precheck; warnings panel
  (duplicates, printed-number gaps, retake list). One Start/Pause/Resume
  button, "Read again" in a secondary menu, progress bar with ETA and
  per-page read-quality chips.
- **Document → Editor**: preview left with region boxes (SVG overlay), lines
  right; click either side to highlight the other; Next/Previous flagged
  page and Next/Previous suspect word; browser-native spellcheck underlines
  on the editable lines; per-line "revert to OCR"; autosave 500 ms after the
  last keystroke; a corrected line shows its origin.
- **Document → Export**: copy-all (headers stripped), download `.md`,
  `.txt`, pages zip, JSONL, CSV, `.docx`; Open folder.
- Polling once a second while a job is running, otherwise every ten
  (TanStack Query `refetchInterval`).

### Security and launch

Copied from media_downloader: bind 127.0.0.1 on a free port, per-launch
token delivered by `/launch` as an `HttpOnly; SameSite=Strict` cookie, CORS
limited to the app's own origin, `instance.json` single-instance check,
`app.log` in the app-data folder, `POST /api/quit`.

### Names

| Where | Name |
|---|---|
| distribution / pipeline package | `usefultext` |
| CLI | `usefultext` (console script), `python -m usefultext` |
| env vars | `USEFULTEXT_MODEL_DIR`, `USEFULTEXT_TOKEN`, `USEFULTEXT_DESKTOP`, `USEFULTEXT_DATA_DIR`, `USEFULTEXT_CORS_ORIGINS` |
| app-data folder (platformdirs) | `UsefulText` |
| window title, UI, README | UsefulText |
| macOS bundle id (M3) | `au.com.tuoa.usefultext` |
| GitHub | `tuoa-tools/usefultext`, public, MIT |

### Wording (unchanged rules)

"Read quality", never "accuracy". "Added to your library", never
"uploaded". Warnings say what to do ("consider re-photographing"), not what
went wrong inside the engine.

## 3. Steps

Each step leaves `pytest` green and the CLI working. Estimates are working
days for one person; the UI is the long pole.

### Step 0 — scaffold (½ day) — done 2026-09-10

- [x] Rename: `phototext/` → `usefultext/`, `PHOTOTEXT_MODEL_DIR` →
      `USEFULTEXT_MODEL_DIR`, `doc_reader.py` → `usefultext/cli.py` plus
      `__main__.py`; every import, test, tool, doc and the README follow.
      `BRIEF.md` keeps its "PhotoText (working title)" line as history.
- [x] `LICENSE` (MIT). `.github/FUNDING.yml` not added; any time later.
- [x] `pyproject.toml` (packages `usefultext`, `app`; deps as
      `requirements.txt` + fastapi, uvicorn, pydantic, python-multipart,
      platformdirs, send2trash; `[dev]` pytest, httpx, ruff; `[build]`
      pyinstaller, pywebview; version read from `usefultext.__version__`).
      `requirements*.txt` removed; README setup rewritten. The `usefultext`
      console script exists; the app's entry point is added in step 2 when
      `app/main.py` exists.
- [x] `ruff.toml` from media_downloader (line length 100; `settings.py`
      excluded from the formatter to keep its aligned calibration notes);
      the Milestone 1 code reformatted once and lint-clean.
      `.github/workflows/ci.yml` (pytest + ruff on ubuntu and windows;
      frontend job added in step 3).
- [x] `app/paths.py`, `app/desktop.py`, `app/launcher.py` copied, env vars
      renamed `USEFULTEXT_TOKEN / DESKTOP / DATA_DIR / CORS_ORIGINS`;
      `paths.default_library_dir()` is `Documents/UsefulText`.
- Done: `pip install -e ".[dev]"` in a fresh venv, 23 tests pass there, the
  CLI read the six sample photos (24 s, printed order recovered, 4 furniture
  lines stripped). CI runs once the repo is on GitHub.

### Step 1 — pipeline prep (1–2 days)

All inside `usefultext/`; the CLI gains nothing but keeps working.

- [ ] `PageSource.base` and `.id`; `PageRecord.id`; relative keys when
      `base` is set. Test: the same job from two folder locations resumes.
- [ ] `run_job(..., preview_dir=…)`: `process_page` writes
      `previews/<id>.jpg` from the rotated 2500 px working image (1600 px,
      q80). PDF pages the same path. Test: a rotated fixture's preview is
      upright and its size matches `rec.width/height` scaled.
- [ ] `usefultext/corrections.py`: `Corrections.load/save`, `apply(record)`,
      `stale` list (OCR text no longer matches), counts. `write_outputs`,
      `page_text`, `document_markdown`, `document_jsonl`, `report_csv` take
      an optional `Corrections`; a corrected line's newlines become separate
      lines. Test: overlay, revert, stale detection, JSONL fields.
- [ ] Output naming and cleanup: `pages/page_003_IMG_0042.txt`
      (`page_003_scan_p2.txt` for PDF pages), first-line provenance
      `[page 3 of 12 · IMG_0042.jpg · read quality 0.98 · rotated 90° · 2 lines corrected]`,
      combined `document.txt` with `--- page 3 ---` separators; the writer
      deletes `pages/*.txt` it did not just write. Test: reorder leaves no
      stale files.
- [ ] `usefultext/checks.py`: `warnings(records) -> list[Warning]` with kinds
      `duplicate` (normalised body text, token-Jaccard prefilter then
      `SequenceMatcher` ≥ 0.9), `printed_gap` / `printed_duplicate` (from
      the furniture numbers; `order_by_printed_page`'s notes become
      structured), `retake` (blurry, low read quality, error). `JobSummary`
      exposes them; the CLI prints them at the end. Test: synthetic records
      as in `test_furniture.py`.
- [ ] `order_by_printed_page` callable without running OCR again (it already
      is; add a thin `printed_order(records)` helper the app can use on the
      page list).
- Done when: the six sample photos run through the CLI produce the new
  file names, a preview per page, `document.txt`, and warnings; CER on the
  eval harness unchanged at 0.67%.

### Step 2 — backend (2–3 days)

- [ ] `app/library.py`: scan `<library>/*/job.json`; create document; page
      list read/write with validation (ids unique, files exist); add files
      from an upload (write to `photos/`, de-duplicate names with ` (1)`)
      or from a path (copy or move); replace; sort by name/time/printed;
      thumbnails on demand with pillow-heif and pymupdf; trash (the
      confirmation lives in the UI; the API call is the irreversible step).
- [ ] `app/worker.py`: thread, queue, `Progress`, pause/resume/force,
      engine warm-up, per-document lock shared with correction saves,
      `summary` written into `job.json` after each page.
- [ ] `app/main.py`: every route in §2; `Settings` overrides per document
      merged over the app settings; exports streamed from the files on disk
      (`pages.zip` built in memory); `docx` returns 501 until step 4.
- [ ] Startup: `register_heif()`, settings load, first-run flag when no
      library folder is set (`/api/health` says so; the UI shows the picker).
- [ ] Tests (`tests/test_api.py`, httpx `TestClient`, `USEFULTEXT_DATA_DIR`
      and a temp library): a fake `run_job` that writes a synthetic
      `state.json` page by page and honours `should_stop`; add → order →
      start → pause → resume → correct → export; relative keys survive a
      library move; two clients saving corrections during a run.
- Done when: the whole flow above runs from `curl` against the six sample
  photos, and a kill -9 mid-job resumes cleanly.

### Step 3 — UI (4–6 days)

- [ ] `frontend/` seeded from media_downloader (Vite, React, TS, Tailwind,
      TanStack Query, eslint/prettier/vitest, `api.ts` typed against §2);
      dev proxy to :8000; `npm run build` → `app/static/`; CI frontend job.
- [ ] Library view; first-run library picker; Settings and Help dialogs.
- [ ] Pages view: drop zone, add-from-folder, thumbnails, drag reorder,
      sort menu, exclude/replace, blur chips, warnings panel, the
      Start/Pause/Resume button, "Read again" with its confirmation, and
      progress with ETA and quality chips.
- [ ] Editor: preview + SVG boxes, line list, click sync, flagged and
      suspect cycling, autosave, revert, origin marker, keyboard nav.
- [ ] Export view: copy-all, downloads, Open folder. Quit in desktop mode.
- [ ] vitest for the pure helpers (line/box mapping, ETA, page-list
      reorder); one render test per view as media_downloader does.
- Done when: a friend-test on the Mac with the six photos plus a retake:
  add, reorder by printed number, read, fix page 7's four misreads, export
  `.md` — with no terminal open.

### Step 4 — spellcheck and docx (1 day)

- [ ] `usefultext/spellcheck.py` on `pyspellchecker` (bundled English
      frequency list, pure Python, offline): per line, unknown words with
      character offsets; skips tokens with digits, single letters and words
      in `<library>/dictionary.txt`. Per-page counts cached against the
      `state.json` and dictionary mtimes. Flags only. Check British
      spellings are not flagged before shipping.
- [ ] `/api/dictionary` and "ignore" in the editor.
- [ ] `.docx` export with `python-docx`: headings → Heading 2, paragraphs,
      a page break between pages, provenance in the core properties.
- Done when: page 7's misreads show as suspects and one "ignore" survives
  a restart.

### Step 5 — window and shutdown (½–1 day)

- [ ] `pywebview` window around the launch URL (WKWebView on the Mac),
      close-to-quit, native folder picker for Settings and add-from-folder
      (this is where "move instead" becomes a dialog rather than a typed
      path). Falls back to the browser tab when pywebview cannot start.
- [ ] Idle shutdown as media_downloader planned it: the UI pings
      `/api/health` each minute; no ping for two minutes and no job running
      → exit. Only in desktop mode.
- [ ] Version 0.2.0; README rewritten around the app; `HANDOVER.md` updated.
- Done when: `python -m app.launcher` opens a window on the Mac and the
  whole step-3 friend-test passes inside it. Windows/Linux WebView2/webkit
  checks are Milestone 3 work on real machines.

## 4. Taken from media_downloader

Verbatim: `launcher.py` (token, port, single instance, logging),
`desktop.py`, `paths.py`, the `/launch` route and token middleware, CORS
setup, static mount, `ci.yml` and `release.yml` shapes, `ruff.toml`,
frontend tooling and `Modal` / `IconButton` / `ActionButton` / `StatusBar`.

Adapted: `worker.py` (thread + `queue.Queue` instead of asyncio tasks; one
job at a time; `should_stop` event instead of process kill), `store.py`
replaced by `library.py` over JSON files in the library folder (no SQLite:
the folder is the record, and it survives being moved or copied), Library
and Settings components re-shaped for documents.

Not taken: yt-dlp/ffmpeg binary handling, the self-update flow, the
embeddable-Python Windows build (M3 decides; onnxruntime DLLs are the new
variable there).

## 5. Risks and gotchas found while planning

- **Uploads of 80 phone photos** are ~400 MB of multipart on localhost;
  `UploadFile` spools to disk, fine. Show per-file progress from the
  browser's own upload events, not the server.
- **PDF thumbnails**: a 200-page PDF at add time would take a minute;
  hence lazy thumbnails, and the precheck already skips PDFs.
- **Furniture detection is job-wide** and re-runs per page over the
  current page list, so excluding pages changes what counts as a running
  header. Expected; the warnings panel makes it visible.
- **Corrections after "Read again"**: `force` re-reads every page; the
  stale-correction rule re-attaches lines whose OCR text is identical and
  reports the rest. The UI must warn before a forced re-read of a document
  with corrections.
- **Two `write_outputs` writers** (item 6 above): one lock per document,
  held by the worker's `finalize()` and by correction saves.
- **HEIC in the browser** is solved by previews and thumbnails; the
  original is never served to the page.
- **Windows path length**: `<library>/<title>/pages/page_003_<photo>.txt`
  with a long title and a long photo name can pass 260 characters; clamp
  the photo stem in the output name to 40 characters.

## 6. Not in Milestone 2

Milestone 3 (packaging: PyInstaller with onnxruntime and pillow-heif
collected on macOS and Linux, models bundled via `USEFULTEXT_MODEL_DIR`,
Actions matrix, a machine without Python). Windows takes
media_downloader's embeddable-Python route again because of Defender, and
that route pip-installs the onnxruntime and pillow-heif wheels, so their
DLLs arrive without any collection step — the Mac PyInstaller build is the
one that needs hooks. Test order: Mac first, then Windows, then Linux. The parking lot is
unchanged: deskew, two-column, born-digital PDF text layer, search across
the library, tables, local RAG.
