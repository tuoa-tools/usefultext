"""UsefulText's local API: a library of documents, one worker reading them,
side-by-side corrections, exports. The UI polls /api/documents/{id} while a
document is being read.

The desktop security model (launch token, cookie, CORS), the static UI mount
and /api/quit are media_downloader's — see launcher.py.
"""

from __future__ import annotations

import asyncio
import io
import os
import shutil
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import desktop
from app.config import ADD_MODES, AppConfig
from app.library import (
    PHOTOS_DIR,
    Job,
    Library,
    LibraryError,
    PageEntry,
    safe_name,
    unique_path,
)
from app.paths import data_dir, default_library_dir
from app.spell import document_suspects
from app.worker import Worker
from usefultext import Settings, __version__
from usefultext.corrections import Corrections
from usefultext.docx_export import build_docx
from usefultext.preprocess import heif_error, register_heif

COOKIE = "usefultext_token"
HEADER = "x-usefultext-token"


def merged_settings(config: AppConfig, job: Job | None = None) -> Settings:
    """Pipeline settings: the calibrated defaults, the app's choices, then
    the document's own overrides."""
    return Settings.from_dict({**config.pipeline_overrides(), **(job.settings if job else {})})


def open_library(path: str | None) -> tuple[Library | None, str | None]:
    if not path:
        return None, None
    try:
        return Library(path), None
    except OSError as exc:
        return None, f"Can't open the library folder {path}: {exc.strerror or exc}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    register_heif()
    folder = data_dir()
    config = AppConfig.load(folder)
    app.state.data_dir = folder
    app.state.config = config
    app.state.library, app.state.library_error = open_library(config.library_dir)
    app.state.token = os.environ.get("USEFULTEXT_TOKEN") or None
    app.state.desktop = os.environ.get("USEFULTEXT_DESKTOP") == "1"
    app.state.quit_requested = False
    if not hasattr(app.state, "on_quit"):
        app.state.on_quit = None
    worker = Worker(lambda: app.state.library, lambda job: merged_settings(app.state.config, job))
    app.state.worker = worker
    worker.start()
    try:
        yield
    finally:
        worker.stop()


app = FastAPI(title="UsefulText", version=__version__, lifespan=lifespan)


@app.middleware("http")
async def require_launch_token(request: Request, call_next):
    """In desktop mode every /api call must carry this launch's secret (cookie or header)."""
    token = getattr(request.app.state, "token", None)
    path = request.url.path
    if token and path.startswith("/api/") and path != "/api/health":
        supplied = request.cookies.get(COOKIE) or request.headers.get(HEADER)
        if supplied != token:
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "This tab isn't connected to the app - open UsefulText from its icon."
                },
            )
    return await call_next(request)


_origins = os.environ.get("USEFULTEXT_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(LibraryError)
async def _library_error(_: Request, exc: LibraryError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #
class SettingsUpdate(BaseModel):
    library_dir: str | None = None
    add_mode: Literal["copy", "move"] | None = None
    pdf_dpi: int | None = Field(default=None, ge=72, le=600)
    min_page_conf: float | None = Field(default=None, ge=0.0, le=1.0)
    blur_threshold: float | None = Field(default=None, ge=0.0)


class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class DocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    pdf_dpi: int | None = Field(default=None, ge=72, le=600)
    min_page_conf: float | None = Field(default=None, ge=0.0, le=1.0)
    blur_threshold: float | None = Field(default=None, ge=0.0)


class AddPathRequest(BaseModel):
    path: str = Field(min_length=1)
    move: bool | None = None  # None = the app setting
    replace: str | None = None  # a page id: this file takes its place


class PageItem(BaseModel):
    id: str
    excluded: bool = False


class PagesUpdate(BaseModel):
    pages: list[PageItem]


class AdoptRequest(BaseModel):
    files: list[str] = Field(min_length=1, max_length=1000)


class SortRequest(BaseModel):
    by: Literal["name", "time", "printed"]


class StartRequest(BaseModel):
    force: bool = False  # read every page again


class LineUpdate(BaseModel):
    text: str = Field(max_length=10_000)


class DictionaryUpdate(BaseModel):
    words: list[str] = Field(max_length=10_000)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _config(request: Request) -> AppConfig:
    return request.app.state.config


def _worker(request: Request) -> Worker:
    return request.app.state.worker


def _lib(request: Request) -> Library:
    lib = request.app.state.library
    if lib is None:
        raise HTTPException(409, request.app.state.library_error or "Choose a library folder first")
    return lib


def _job(request: Request, doc_id: str) -> tuple[Library, Job]:
    lib = _lib(request)
    job = lib.get(doc_id)
    if job is None:
        raise HTTPException(404, "No such document")
    return lib, job


def _settings(request: Request, job: Job | None = None) -> Settings:
    return merged_settings(_config(request), job)


def _not_active(request: Request, job: Job) -> None:
    if _worker(request).active(job.id):
        raise HTTPException(409, "Pause the document before changing its pages")


def _entry(job: Job, page_id: str) -> PageEntry:
    entry = job.entry(page_id)
    if entry is None:
        raise HTTPException(404, "No such page")
    return entry


def _summary_view(lib: Library, job: Job, worker: Worker, settings: Settings) -> dict:
    prog = worker.active(job.id)
    counts = job.summary or lib.refresh_summary(job, settings)
    return {
        "id": job.id,
        "title": job.title,
        "folder": str(job.folder),
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "status": prog.status if prog else lib.status(job),
        **counts,
        "last_run": job.last_run,
        "progress": prog.to_dict() if prog else None,
    }


def _page_view(
    job: Job,
    entry: PageEntry,
    position: int | None,
    record,
    corrections: Corrections,
    settings: Settings,
    suspects: dict | None = None,
) -> dict:
    blurry = (entry.sharpness < settings.blur_threshold) if entry.sharpness is not None else None
    view = {
        "id": entry.id,
        "file": entry.file,
        "label": entry.label(job.folder),
        "page_index": entry.page_index,
        "excluded": entry.excluded,
        "position": position,
        "added_at": entry.added_at,
        "replaced_from": entry.replaced_from,
        "sharpness": entry.sharpness,
        "blurry": blurry,
        "thumb": f"/api/documents/{job.id}/previews/{entry.id}.thumb.jpg",
        "read": None,
    }
    if record is not None:
        done = record.status == "done"
        view["blurry"] = record.blurry if done else blurry
        view["read"] = {
            "status": record.status,
            "error": record.error,
            "mean_conf": record.mean_conf,
            "low_conf": record.low_conf,
            "blurry": record.blurry,
            "sharpness": record.sharpness,
            "rotation": record.rotation,
            "printed_page": record.printed_page,
            "n_regions": record.n_regions,
            "n_lines": len(record.lines),
            "corrected": corrections.count(record),
            "stale": len(corrections.stale(record)),
            "suspects": sum(len(v) for v in (suspects or {}).values()),
            "elapsed": record.elapsed,
            "preview": {
                "url": f"/api/documents/{job.id}/previews/{entry.id}.jpg",
                "width": record.preview_width,
                "height": record.preview_height,
            }
            if record.preview
            else None,
        }
    return view


def _document_view(request: Request, lib: Library, job: Job) -> dict:
    settings = _settings(request, job)
    corrections = Corrections.load(job.folder)
    records = lib.records(job)
    suspects = document_suspects(lib, job, records, corrections)
    pages, position = [], 0
    for entry in job.pages:
        if not entry.excluded:
            position += 1
        pages.append(
            _page_view(
                job,
                entry,
                None if entry.excluded else position,
                records.get(entry.id),
                corrections,
                settings,
                suspects.get(entry.id),
            )
        )
    return {
        **_summary_view(lib, job, _worker(request), settings),
        "settings": job.settings,
        "pages": pages,
        "warnings": lib.warnings(job, settings),
        "stray_files": lib.stray_files(job),
    }


def _prepare_folder(raw: str) -> tuple[Path | None, str | None]:
    """Resolve, create and check a folder the user typed; returns (path, error)."""
    path = Path(raw).expanduser()
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return None, f"Can't use that folder: {exc.strerror or exc}"
    if not os.access(path, os.W_OK):
        return None, "Can't write to that folder"
    return path.resolve(), None


# --------------------------------------------------------------------------- #
# App: launch, health, settings, quit
# --------------------------------------------------------------------------- #
@app.get("/launch")
async def launch(token: str, request: Request) -> RedirectResponse:
    """Where the launcher points the browser: remember the launch secret, then show the app."""
    if not request.app.state.token or token != request.app.state.token:
        raise HTTPException(403, "Wrong launch token")
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(COOKIE, token, httponly=True, samesite="strict", max_age=365 * 24 * 3600)
    return response


@app.get("/api/health")
async def health(request: Request) -> dict:
    state = request.app.state
    return {
        "status": "ok",
        "version": __version__,
        "desktop": bool(getattr(state, "desktop", False)),
        "engine": _worker(request).engine,
        "library_dir": state.config.library_dir,
        "library_error": state.library_error,
        "first_run": state.library is None and not state.library_error,
        "heif": register_heif(),
        "heif_error": heif_error(),
        "quit_requested": bool(getattr(state, "quit_requested", False)),
    }


def _settings_view(request: Request) -> dict:
    c = _config(request)
    return {
        "library_dir": c.library_dir,
        "add_mode": c.add_mode,
        "add_modes": list(ADD_MODES),
        "pdf_dpi": c.pdf_dpi,
        "min_page_conf": c.min_page_conf,
        "blur_threshold": c.blur_threshold,
        "default_library_dir": str(default_library_dir()),
        "defaults": Settings().to_dict(),
    }


@app.get("/api/settings")
async def get_settings(request: Request) -> dict:
    return _settings_view(request)


@app.put("/api/settings")
async def update_settings(req: SettingsUpdate, request: Request) -> dict:
    state = request.app.state
    c: AppConfig = state.config
    if req.library_dir is not None:
        path, error = await asyncio.to_thread(_prepare_folder, req.library_dir)
        if error or path is None:
            raise HTTPException(422, error or "Can't use that folder")
        library, lib_error = await asyncio.to_thread(open_library, str(path))
        if lib_error:
            raise HTTPException(422, lib_error)
        c.library_dir = str(path)
        state.library, state.library_error = library, None
    for key in ("add_mode", "pdf_dpi", "min_page_conf", "blur_threshold"):
        value = getattr(req, key)
        if value is not None:
            setattr(c, key, value)
    await asyncio.to_thread(c.save, state.data_dir)
    return _settings_view(request)


@app.post("/api/quit")
async def quit_app(request: Request) -> dict:
    """Desktop mode: stop the server (the launcher process then exits)."""
    state = request.app.state
    if not state.desktop:
        raise HTTPException(400, "Not running as the desktop app")
    state.quit_requested = True
    if state.on_quit:
        state.on_quit()
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Library
# --------------------------------------------------------------------------- #
@app.get("/api/library")
async def library(request: Request) -> dict:
    lib = _lib(request)
    worker = _worker(request)
    jobs = await asyncio.to_thread(lib.documents)
    return {
        "library_dir": str(lib.root),
        "documents": [_summary_view(lib, job, worker, _settings(request, job)) for job in jobs],
    }


@app.post("/api/library", status_code=201)
async def create_document(req: DocumentCreate, request: Request) -> dict:
    lib = _lib(request)
    job = await asyncio.to_thread(lib.create, req.title)
    return _summary_view(lib, job, _worker(request), _settings(request, job))


@app.delete("/api/library/{doc_id}")
async def remove_document(doc_id: str, request: Request) -> dict:
    """The document's folder goes to the OS trash. The UI confirms first."""
    lib, job = _job(request, doc_id)
    if _worker(request).active(job.id):
        raise HTTPException(409, "Pause the document before removing it")
    await asyncio.to_thread(lib.trash, job)
    return {"ok": True, "trashed": str(job.folder)}


@app.post("/api/library/{doc_id}/reveal")
async def reveal_document(doc_id: str, request: Request) -> dict:
    _, job = _job(request, doc_id)
    await asyncio.to_thread(desktop.reveal, job.folder)
    return {"ok": True, "path": str(job.folder)}


# --------------------------------------------------------------------------- #
# A document: pages, order, reading
# --------------------------------------------------------------------------- #
@app.get("/api/documents/{doc_id}")
async def get_document(doc_id: str, request: Request) -> dict:
    lib, job = _job(request, doc_id)
    return await asyncio.to_thread(_document_view, request, lib, job)


@app.put("/api/documents/{doc_id}")
async def update_document(doc_id: str, req: DocumentUpdate, request: Request) -> dict:
    lib, job = _job(request, doc_id)
    if req.title is not None:
        job.title = req.title.strip()
    for key in ("pdf_dpi", "min_page_conf", "blur_threshold"):
        value = getattr(req, key)
        if value is not None:
            job.settings[key] = value
    await asyncio.to_thread(job.save)
    return await asyncio.to_thread(_document_view, request, lib, job)


def _save_upload(upload: UploadFile, folder: Path) -> tuple[Path, str]:
    name = safe_name(Path(upload.filename or "photo").name, "photo")
    dest = unique_path(folder, name)  # two "a.jpg" in one batch must not collide here
    with dest.open("wb") as out:
        shutil.copyfileobj(upload.file, out)
    return dest, name


@app.post("/api/documents/{doc_id}/files", status_code=201)
async def add_files(
    doc_id: str,
    request: Request,
    files: Annotated[list[UploadFile], File()],
    replace: Annotated[str | None, Form()] = None,
) -> dict:
    """The drop zone: the browser sends the bytes, so this is always a copy
    into photos/. "Added to your library", never "uploaded", in the UI."""
    lib, job = _job(request, doc_id)
    _not_active(request, job)
    settings = _settings(request, job)
    incoming = job.folder / PHOTOS_DIR / f".incoming-{os.getpid()}-{id(request)}"
    incoming.mkdir(parents=True, exist_ok=True)
    try:
        items = [await asyncio.to_thread(_save_upload, f, incoming) for f in files]
        added = await asyncio.to_thread(
            lib.add_files, job, items, settings, move=True, replace=replace
        )
    finally:
        shutil.rmtree(incoming, ignore_errors=True)
    await asyncio.to_thread(lib.refresh, job, settings, _worker(request).lock(job.id))
    return {
        "added": [e.id for e in added],
        **await asyncio.to_thread(_document_view, request, lib, job),
    }


@app.post("/api/documents/{doc_id}/add-path", status_code=201)
async def add_path(doc_id: str, req: AddPathRequest, request: Request) -> dict:
    """Files or a folder named by path: copied by default, moved when asked
    (the only route where "move instead" is possible)."""
    lib, job = _job(request, doc_id)
    _not_active(request, job)
    settings = _settings(request, job)
    move = req.move if req.move is not None else _config(request).add_mode == "move"
    added = await asyncio.to_thread(
        lib.add_path, job, Path(req.path), settings, move=move, replace=req.replace
    )
    await asyncio.to_thread(lib.refresh, job, settings, _worker(request).lock(job.id))
    return {
        "added": [e.id for e in added],
        **await asyncio.to_thread(_document_view, request, lib, job),
    }


@app.put("/api/documents/{doc_id}/pages")
async def set_pages(doc_id: str, req: PagesUpdate, request: Request) -> dict:
    """Reorder, exclude, or drop pages: the whole list, in order."""
    lib, job = _job(request, doc_id)
    _not_active(request, job)
    settings = _settings(request, job)
    removed = await asyncio.to_thread(lib.set_pages, job, [p.model_dump() for p in req.pages])
    await asyncio.to_thread(lib.refresh, job, settings, _worker(request).lock(job.id))
    return {"removed": removed, **await asyncio.to_thread(_document_view, request, lib, job)}


@app.post("/api/documents/{doc_id}/pages/adopt", status_code=201)
async def adopt_files(doc_id: str, req: AdoptRequest, request: Request) -> dict:
    """Photos already in the folder but not in the document become pages."""
    lib, job = _job(request, doc_id)
    _not_active(request, job)
    settings = _settings(request, job)
    added = await asyncio.to_thread(lib.adopt, job, req.files, settings)
    await asyncio.to_thread(lib.refresh, job, settings, _worker(request).lock(job.id))
    return {
        "added": [e.id for e in added],
        **await asyncio.to_thread(_document_view, request, lib, job),
    }


@app.post("/api/documents/{doc_id}/pages/sort")
async def sort_pages(doc_id: str, req: SortRequest, request: Request) -> dict:
    lib, job = _job(request, doc_id)
    _not_active(request, job)
    settings = _settings(request, job)
    notes = await asyncio.to_thread(lib.sort_pages, job, req.by)
    await asyncio.to_thread(lib.refresh, job, settings, _worker(request).lock(job.id))
    return {"notes": notes, **await asyncio.to_thread(_document_view, request, lib, job)}


@app.post("/api/documents/{doc_id}/start")
async def start_document(doc_id: str, request: Request, req: StartRequest | None = None) -> dict:
    lib, job = _job(request, doc_id)
    if not job.included():
        raise HTTPException(409, "Add some pages first")
    worker = _worker(request)
    if worker.engine.get("state") == "failed":
        raise HTTPException(503, f"The OCR engine isn't working: {worker.engine.get('error')}")
    if not worker.enqueue(job.id, force=bool(req and req.force)):
        raise HTTPException(409, "Already reading this document")
    return {"ok": True, "status": "queued"}


@app.post("/api/documents/{doc_id}/resume")
async def resume_document(doc_id: str, request: Request) -> dict:
    return await start_document(doc_id, request, StartRequest(force=False))


@app.post("/api/documents/{doc_id}/pause")
async def pause_document(doc_id: str, request: Request) -> dict:
    _, job = _job(request, doc_id)
    if not _worker(request).pause(job.id):
        raise HTTPException(409, "This document isn't being read")
    return {"ok": True}


# --------------------------------------------------------------------------- #
# A page: the editor's view and corrections
# --------------------------------------------------------------------------- #
def _line_views(record, corrections: Corrections, suspects: dict | None = None) -> list[dict]:
    live = corrections.live(record)
    suspects = suspects or {}
    return [
        {
            "index": i,
            "text": ln.get("text", ""),
            "heading": bool(ln.get("heading")),
            "para_break_before": bool(ln.get("para_break_before")),
            "furniture": bool(ln.get("furniture")),
            "regions": ln.get("regions", []),
            "corrected": live[i].text if i in live else None,
            "corrected_at": live[i].at if i in live else None,
            "origin": "human" if i in live else "ocr",
            "suspects": [s.to_dict() for s in suspects.get(i, [])],
        }
        for i, ln in enumerate(record.lines)
    ]


def _page_detail(lib: Library, job: Job, entry: PageEntry, settings: Settings) -> dict:
    corrections = Corrections.load(job.folder)
    records = lib.records(job)
    record = records.get(entry.id)
    position = next((i for i, e in enumerate(job.included(), 1) if e.id == entry.id), None)
    suspects = document_suspects(lib, job, records, corrections).get(entry.id, {})
    view = _page_view(job, entry, position, record, corrections, settings, suspects)
    view["lines"], view["regions"], view["stale"] = [], [], []
    view["suspects"] = sum(len(v) for v in suspects.values())
    if record is not None and record.status == "done":
        view["width"], view["height"] = record.width, record.height
        view["lines"] = _line_views(record, corrections, suspects)
        view["regions"] = [
            {
                "text": r["text"],
                "conf": r["conf"],
                "bbox": r["bbox"],
                "clipped": bool(r.get("clipped")),
            }
            for r in record.regions
        ]
        view["stale"] = [
            {"index": i, "text": c.text, "ocr": c.ocr, "at": c.at}
            for i, c in corrections.stale(record)
        ]
    return view


@app.get("/api/documents/{doc_id}/pages/{page_id}")
async def get_page(doc_id: str, page_id: str, request: Request) -> dict:
    lib, job = _job(request, doc_id)
    entry = _entry(job, page_id)
    return await asyncio.to_thread(_page_detail, lib, job, entry, _settings(request, job))


def _edit_line(
    lib: Library, job: Job, entry: PageEntry, index: int, text: str | None, settings: Settings, lock
) -> dict:
    """Save (text) or revert (None) one line's correction, then refresh the
    outputs. Under the document's lock, so a running read takes turns."""
    with lock:
        record = lib.records(job).get(entry.id)
        if record is None or record.status != "done":
            raise HTTPException(409, "This page hasn't been read yet")
        if not 0 <= index < len(record.lines):
            raise HTTPException(404, "No such line")
        corrections = Corrections.load(job.folder)
        if text is None:
            corrections.revert(entry.id, index)
        else:
            corrections.set(entry.id, index, text, record.lines[index].get("text", ""))
        corrections.save(job.folder)
        lib.refresh(job, settings, lock)
        suspects = document_suspects(lib, job, lib.records(job), corrections).get(entry.id, {})
        return _line_views(record, corrections, suspects)[index]


@app.put("/api/documents/{doc_id}/pages/{page_id}/lines/{index}")
async def correct_line(
    doc_id: str, page_id: str, index: int, req: LineUpdate, request: Request
) -> dict:
    lib, job = _job(request, doc_id)
    entry = _entry(job, page_id)
    lock = _worker(request).lock(job.id)
    return await asyncio.to_thread(
        _edit_line, lib, job, entry, index, req.text, _settings(request, job), lock
    )


@app.delete("/api/documents/{doc_id}/pages/{page_id}/lines/{index}")
async def revert_line(doc_id: str, page_id: str, index: int, request: Request) -> dict:
    """Back to what the OCR read."""
    lib, job = _job(request, doc_id)
    entry = _entry(job, page_id)
    lock = _worker(request).lock(job.id)
    return await asyncio.to_thread(
        _edit_line, lib, job, entry, index, None, _settings(request, job), lock
    )


@app.get("/api/documents/{doc_id}/previews/{name}")
async def preview(doc_id: str, name: str, request: Request) -> FileResponse:
    lib, job = _job(request, doc_id)
    if name.endswith(".thumb.jpg"):
        entry = _entry(job, name[: -len(".thumb.jpg")])
        path = await asyncio.to_thread(lib.thumbnail, job, entry, _settings(request, job))
    elif name.endswith(".jpg"):
        entry = _entry(job, name[: -len(".jpg")])
        path = lib.preview(job, entry)
        if path is None:
            raise HTTPException(404, "This page hasn't been read yet")
    else:
        raise HTTPException(404, "No such preview")
    return FileResponse(path, media_type="image/jpeg")


# --------------------------------------------------------------------------- #
# Exports
# --------------------------------------------------------------------------- #
EXPORTS = {
    "md": ("document.md", "text/markdown; charset=utf-8", ".md"),
    "txt": ("document.txt", "text/plain; charset=utf-8", ".txt"),
    "jsonl": ("document.jsonl", "application/x-ndjson", ".jsonl"),
    "csv": ("report.csv", "text/csv; charset=utf-8", ".csv"),
}


def _plain_text(lib: Library, job: Job, settings: Settings) -> str:
    """Copy-all: the pages' text with nothing else, corrections applied."""
    corrections = Corrections.load(job.folder)
    records = lib.records(job)
    parts = []
    for e in job.included():
        rec = records.get(e.id)
        if rec is not None and rec.status == "done":
            body = rec.body_text(settings.strip_furniture, corrections)
            if body:
                parts.append(body)
    return "\n\n".join(parts) + ("\n" if parts else "")


def _docx(lib: Library, job: Job, settings: Settings) -> bytes:
    records = lib.records(job)
    recs = [records[e.id] for e in job.included() if records.get(e.id) is not None]
    recs.sort(key=lambda r: r.page)
    return build_docx(job.title, recs, len(job.included()), settings, Corrections.load(job.folder))


def _pages_zip(job: Job) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted((job.folder / "pages").glob("page_*.txt")):
            z.write(p, f"pages/{p.name}")
    return buf.getvalue()


@app.get("/api/documents/{doc_id}/export/{kind}")
async def export(doc_id: str, kind: str, request: Request, plain: bool = False) -> Response:
    lib, job = _job(request, doc_id)
    stem = safe_name(job.title, "document")
    if kind == "docx":
        data = await asyncio.to_thread(_docx, lib, job, _settings(request, job))
        headers = {"Content-Disposition": f'attachment; filename="{stem}.docx"'}
        return Response(
            data,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers=headers,
        )
    if kind == "txt" and plain:
        text = await asyncio.to_thread(_plain_text, lib, job, _settings(request, job))
        return Response(text, media_type="text/plain; charset=utf-8")
    if kind == "pages.zip":
        if not (job.folder / "pages").is_dir():
            raise HTTPException(404, "Nothing has been read yet")
        data = await asyncio.to_thread(_pages_zip, job)
        headers = {"Content-Disposition": f'attachment; filename="{stem} pages.zip"'}
        return Response(data, media_type="application/zip", headers=headers)
    if kind not in EXPORTS:
        raise HTTPException(404, "No such export")
    name, media, suffix = EXPORTS[kind]
    path = job.folder / name
    if not path.exists():
        raise HTTPException(404, "Nothing has been read yet")
    return FileResponse(path, media_type=media, filename=f"{stem}{suffix}")


# --------------------------------------------------------------------------- #
# The spellcheck ignore list
# --------------------------------------------------------------------------- #
@app.get("/api/dictionary")
async def get_dictionary(request: Request) -> dict:
    return {"words": await asyncio.to_thread(_lib(request).dictionary)}


@app.put("/api/dictionary")
async def set_dictionary(req: DictionaryUpdate, request: Request) -> dict:
    return {"words": await asyncio.to_thread(_lib(request).set_dictionary, req.words)}


@app.post("/api/dictionary")
async def add_to_dictionary(req: DictionaryUpdate, request: Request) -> dict:
    """ "Ignore" in the editor: these words are fine, in every document of this library."""
    lib = _lib(request)
    current = await asyncio.to_thread(lib.dictionary)
    return {"words": await asyncio.to_thread(lib.set_dictionary, current + req.words)}


# The desktop app serves the built UI from here (step 3). In dev the
# directory is absent and Vite serves the UI instead; until the UI exists,
# a placeholder page points at the interactive API docs.
_static = Path(__file__).parent / "static"
if _static.is_dir():
    app.mount("/", StaticFiles(directory=_static, html=True), name="ui")
else:

    @app.get("/", include_in_schema=False)
    async def placeholder() -> HTMLResponse:
        return HTMLResponse(
            "<title>UsefulText</title><body style='font-family:system-ui;margin:3em'>"
            f"<h1>UsefulText {__version__}</h1><p>The API is running. The browser UI arrives "
            "in step 3 of the plan; until then, try the endpoints at "
            "<a href='/docs'>/docs</a> (choose a library folder with PUT /api/settings first)."
            "</p></body>"
        )
