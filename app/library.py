"""The library folder: one sub-folder per document, each its own job.

<library>/<Document>/job.json   the app's record: page list, settings, last run
                     photos/    the files as added (copied or moved), names kept
                     previews/  <id>.jpg from the pipeline; <id>.thumb.jpg made here on demand
                     state.json, corrections.json, pages/, document.* — the pipeline's

The page list is explicit and owned by the job (PLAN_M2.md): order is array
order, an excluded page keeps its entry, a retake replaces `file` on the same
entry. Files in photos/ that are not in the list are reported, never picked
up silently. The app never deletes a photo; removing a document sends its
whole folder to the OS trash.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageOps

from usefultext import Settings
from usefultext.checks import job_warnings
from usefultext.corrections import Corrections
from usefultext.furniture import printed_order
from usefultext.inputs import PageSource, discover_files, file_time, natural_key, pdf_page_count
from usefultext.outputs import JobState
from usefultext.pipeline import PREVIEW_DIR, refresh_outputs, render_pdf_page, sharpness_precheck
from usefultext.preprocess import SUPPORTED_EXTS, SUPPORTED_PDF_EXTS

JOB_FILE = "job.json"
JOB_VERSION = 1
PHOTOS_DIR = "photos"
DICTIONARY_FILE = "dictionary.txt"
THUMB_LONG_EDGE = 320
THUMB_SUFFIX = ".thumb.jpg"
SORT_BY = ("name", "time", "printed")

_ILLEGAL_NAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


class LibraryError(Exception):
    """A request the library cannot honour, with a message for the person."""


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def new_id(prefix: str = "") -> str:
    return prefix + uuid.uuid4().hex[:8]


def safe_name(text: str | None, fallback: str = "Untitled") -> str:
    """A folder/file name that is legal on Windows, macOS and Linux."""
    cleaned = _ILLEGAL_NAME_CHARS.sub("_", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned[:120] or fallback


def unique_path(folder: Path, name: str) -> Path:
    """`name`, else `name (1)`, `name (2)`… — nothing is ever overwritten."""
    target = folder / name
    stem, suffix = Path(name).stem, Path(name).suffix
    n = 1
    while target.exists():
        target = folder / f"{stem} ({n}){suffix}"
        n += 1
    return target


# --------------------------------------------------------------------------- #
# The job record
# --------------------------------------------------------------------------- #
@dataclass
class PageEntry:
    id: str
    file: str  # relative to the document folder, posix ("photos/IMG_0042.jpg")
    page_index: int = 0  # page within a PDF
    n_pages: int = 1
    excluded: bool = False
    added_at: str = ""
    replaced_from: str | None = None  # the photo this one replaced (kept in photos/)
    sharpness: float | None = None  # from the pre-check when it was added

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> PageEntry:
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def source(self, folder: Path) -> PageSource:
        return PageSource(
            folder / self.file, self.page_index, self.n_pages, base=folder, id=self.id
        )

    def label(self, folder: Path) -> str:
        return self.source(folder).label


@dataclass
class Job:
    folder: Path
    id: str = ""
    title: str = ""
    created_at: str = ""
    updated_at: str = ""
    settings: dict = field(default_factory=dict)  # per-document overrides of usefultext.Settings
    summary: dict = field(default_factory=dict)  # cached counts for the library view
    last_run: dict | None = None  # {finished_at, processed, resumed, failed, stopped_early, error}
    pages: list = field(default_factory=list)  # PageEntry, in reading order

    @classmethod
    def load(cls, folder: Path) -> Job | None:
        p = folder / JOB_FILE
        if not p.exists():
            return None
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
        job = cls(folder=folder)
        for k in ("id", "title", "created_at", "updated_at", "settings", "summary", "last_run"):
            if k in raw:
                setattr(job, k, raw[k])
        job.pages = [PageEntry.from_dict(e) for e in raw.get("pages", [])]
        return job

    def save(self) -> None:
        self.updated_at = now()
        raw = {
            "version": JOB_VERSION,
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "settings": self.settings,
            "summary": self.summary,
            "last_run": self.last_run,
            "pages": [e.to_dict() for e in self.pages],
        }
        p = self.folder / JOB_FILE
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, p)

    def entry(self, page_id: str) -> PageEntry | None:
        return next((e for e in self.pages if e.id == page_id), None)

    def included(self) -> list[PageEntry]:
        return [e for e in self.pages if not e.excluded]

    def sources(self) -> list[PageSource]:
        """What run_job reads: the included pages, in order."""
        return [e.source(self.folder) for e in self.included()]

    def key_of(self, entry: PageEntry) -> str:
        return entry.source(self.folder).key


# --------------------------------------------------------------------------- #
# The library
# --------------------------------------------------------------------------- #
class Library:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # --- documents ---

    def documents(self) -> list[Job]:
        jobs = []
        for child in sorted(self.root.iterdir(), key=lambda p: natural_key(p.name)):
            if child.is_dir():
                job = Job.load(child)
                if job is not None:
                    jobs.append(job)
        return jobs

    def get(self, doc_id: str) -> Job | None:
        return next((j for j in self.documents() if j.id == doc_id), None)

    def create(self, title: str) -> Job:
        title = (title or "").strip()
        if not title:
            raise LibraryError("Give the document a name")
        folder = unique_path(self.root, safe_name(title))
        folder.mkdir()
        (folder / PHOTOS_DIR).mkdir()
        job = Job(folder=folder, id=new_id(), title=title, created_at=now())
        job.save()
        return job

    def trash(self, job: Job) -> None:
        """The whole folder to the OS trash — recoverable, never a delete."""
        from send2trash import send2trash

        send2trash(str(job.folder))

    # --- pages ---

    def add_files(
        self,
        job: Job,
        items: list[tuple[Path, str]],
        settings: Settings,
        *,
        move: bool = False,
        replace: str | None = None,
    ) -> list[PageEntry]:
        """Bring files into photos/ (copied, or moved when asked) and append a
        page for each — one per PDF page. `items` are (path, name to keep).
        With `replace`, the first new page takes over that entry: same id and
        position, the old photo kept and remembered as `replaced_from`."""
        photos = job.folder / PHOTOS_DIR
        photos.mkdir(exist_ok=True)
        rejected = [name for _, name in items if Path(name).suffix.lower() not in SUPPORTED_EXTS]
        if rejected:
            kinds = ", ".join(sorted(e.lstrip(".") for e in SUPPORTED_EXTS))
            raise LibraryError(
                f"Not a page image or PDF: {', '.join(rejected[:5])} (accepted: {kinds})"
            )
        target_entry = job.entry(replace) if replace else None
        if replace and target_entry is None:
            raise LibraryError("No such page to replace")

        new: list[PageEntry] = []
        for path, name in items:
            dest = unique_path(photos, safe_name(name, "photo"))
            if move:
                shutil.move(str(path), str(dest))
            else:
                shutil.copy2(path, dest)
            rel = dest.relative_to(job.folder).as_posix()
            n = pdf_page_count(dest) if dest.suffix.lower() in SUPPORTED_PDF_EXTS else 1
            for i in range(n):
                new.append(
                    PageEntry(id=new_id("p"), file=rel, page_index=i, n_pages=n, added_at=now())
                )

        scores = sharpness_precheck([e.source(job.folder) for e in new], settings)
        for e in new:
            e.sharpness = scores.get(e.source(job.folder).key)

        if target_entry is not None and new:
            retake, rest = new[0], new[1:]
            old_key = job.key_of(target_entry)
            target_entry.replaced_from = target_entry.file
            target_entry.file, target_entry.page_index, target_entry.n_pages = (
                retake.file,
                retake.page_index,
                retake.n_pages,
            )
            target_entry.sharpness, target_entry.added_at = retake.sharpness, retake.added_at
            self._forget_record(job, old_key)
            pos = job.pages.index(target_entry) + 1
            job.pages[pos:pos] = rest
            new = [target_entry] + rest
        else:
            job.pages.extend(new)
        job.save()
        return new

    def add_path(
        self,
        job: Job,
        path: Path,
        settings: Settings,
        *,
        move: bool = False,
        replace: str | None = None,
    ) -> list[PageEntry]:
        """Files or a folder named by path (typed, or from a native dialog)."""
        path = Path(path).expanduser()
        if not path.exists():
            raise LibraryError(f"{path} does not exist")
        files = discover_files([path]) if path.is_dir() else [path]
        if not files:
            raise LibraryError("No page images or PDFs found there")
        files.sort(key=lambda f: natural_key(f.name))
        return self.add_files(
            job, [(f, f.name) for f in files], settings, move=move, replace=replace
        )

    def set_pages(self, job: Job, ordered: list[dict]) -> list[str]:
        """The whole list, in order: {id, excluded}. Pages left out are removed
        from the document (their photos stay in photos/). Returns the ids removed."""
        by_id = {e.id: e for e in job.pages}
        seen: set[str] = set()
        new_list = []
        for item in ordered:
            pid = item.get("id")
            if pid not in by_id:
                raise LibraryError(f"No such page: {pid}")
            if pid in seen:
                raise LibraryError(f"Page {pid} is listed twice")
            seen.add(pid)
            entry = by_id[pid]
            entry.excluded = bool(item.get("excluded", entry.excluded))
            new_list.append(entry)
        removed = [pid for pid in by_id if pid not in seen]
        job.pages = new_list
        job.save()
        return removed

    def sort_pages(self, job: Job, by: str) -> list[str]:
        """Reorder the included pages; excluded ones stay at the end in their
        current order. Returns notes (for 'printed': where the guesses went)."""
        if by not in SORT_BY:
            raise LibraryError(f"sort must be one of {', '.join(SORT_BY)}")
        included, excluded = job.included(), [e for e in job.pages if e.excluded]
        notes: list[str] = []
        if by == "name":
            included.sort(key=lambda e: (natural_key(Path(e.file).name), e.page_index))
        elif by == "time":
            included.sort(
                key=lambda e: (
                    file_time(job.folder / e.file),
                    natural_key(Path(e.file).name),
                    e.page_index,
                )
            )
        else:
            records = self.records(job)
            recs = [records[e.id] for e in included if records.get(e.id) is not None]
            ordered, notes = printed_order(recs)
            by_key = {job.key_of(e): e for e in included}
            done = [by_key[r.key] for r in ordered if r.key in by_key]
            unread = [e for e in included if e not in done]
            if unread:
                notes.append(f"{len(unread)} page(s) not read yet were left at the end")
            included = done + unread
        job.pages = included + excluded
        job.save()
        return notes

    def stray_files(self, job: Job) -> list[str]:
        """Photos in the folder that are not part of the document."""
        photos = job.folder / PHOTOS_DIR
        if not photos.is_dir():
            return []
        listed = {e.file for e in job.pages} | {
            e.replaced_from for e in job.pages if e.replaced_from
        }
        out = []
        for f in sorted(photos.iterdir(), key=lambda p: natural_key(p.name)):
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTS and not f.name.startswith("."):
                rel = f.relative_to(job.folder).as_posix()
                if rel not in listed:
                    out.append(rel)
        return out

    # --- state ---

    def state(self, job: Job) -> JobState:
        return JobState.load(job.folder)

    def records(self, job: Job, state: JobState | None = None) -> dict:
        """page id → PageRecord (or None if not read yet), for every entry."""
        state = state or self.state(job)
        return {e.id: state.pages.get(job.key_of(e)) for e in job.pages}

    def _forget_record(self, job: Job, key: str) -> None:
        state = self.state(job)
        if key in state.pages:
            del state.pages[key]
            state.save(job.folder)

    def refresh(self, job: Job, settings: Settings, lock=None) -> None:
        """After a reorder, exclusion or correction: outputs and cached counts."""
        if (job.folder / "state.json").exists():
            refresh_outputs(job.folder, job.sources(), settings, lock=lock)
        self.refresh_summary(job, settings)

    def refresh_summary(self, job: Job, settings: Settings) -> dict:
        state = self.state(job)
        corrections = Corrections.load(job.folder)
        included = job.included()
        recs = [state.pages.get(job.key_of(e)) for e in included]
        done = [r for r in recs if r is not None and r.status == "done"]
        job.summary = {
            "pages": len(job.pages),
            "included": len(included),
            "read": len(done),
            "errors": sum(1 for r in recs if r is not None and r.status == "error"),
            "low_conf": sum(1 for r in done if r.low_conf),
            "blurry": sum(1 for r in done if r.blurry),
            "corrected_lines": sum(corrections.count(r) for r in done),
            "stale_corrections": sum(len(corrections.stale(r)) for r in done),
        }
        job.save()
        return job.summary

    def status(self, job: Job) -> str:
        """new | paused | done | error, from what is on disk (the worker adds
        queued and running for the document it holds)."""
        if job.last_run and job.last_run.get("error"):
            return "error"
        s = job.summary or {}
        included, read, errors = s.get("included", 0), s.get("read", 0), s.get("errors", 0)
        if included and read + errors >= included:
            return "done"
        if read or errors:
            return "paused"
        return "new"

    def warnings(self, job: Job, settings: Settings) -> list[dict]:
        records = self.records(job)
        recs = [records[e.id] for e in job.included() if records.get(e.id) is not None]
        return [w.to_dict() for w in job_warnings(recs, settings)]

    # --- previews ---

    def thumbnail(self, job: Job, entry: PageEntry, settings: Settings) -> Path:
        """A small EXIF-oriented JPEG of the page as added (before any read),
        made on first request and kept beside the pipeline's previews."""
        path = job.folder / PREVIEW_DIR / f"{entry.id}{THUMB_SUFFIX}"
        src = job.folder / entry.file
        if path.exists() and path.stat().st_mtime >= src.stat().st_mtime:
            return path
        if src.suffix.lower() in SUPPORTED_PDF_EXTS:
            img = render_pdf_page(src, entry.page_index, 40, settings.pdf_max_pixels)
        else:
            with Image.open(src) as im:
                if im.format == "JPEG":
                    im.draft("RGB", (2 * THUMB_LONG_EDGE, 2 * THUMB_LONG_EDGE))
                img = ImageOps.exif_transpose(im).convert("RGB")
        img.thumbnail((THUMB_LONG_EDGE, THUMB_LONG_EDGE))
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        img.save(tmp, "JPEG", quality=70, optimize=True)
        os.replace(tmp, path)
        return path

    def preview(self, job: Job, entry: PageEntry) -> Path | None:
        path = job.folder / PREVIEW_DIR / f"{entry.id}.jpg"
        return path if path.exists() else None

    # --- the spellcheck ignore list ---

    def dictionary(self) -> list[str]:
        p = self.root / DICTIONARY_FILE
        if not p.exists():
            return []
        return [w for w in p.read_text(encoding="utf-8").splitlines() if w.strip()]

    def set_dictionary(self, words: list[str]) -> list[str]:
        cleaned = sorted({w.strip() for w in words if w.strip()}, key=str.lower)
        p = self.root / DICTIONARY_FILE
        tmp = p.with_suffix(".tmp")
        tmp.write_text("\n".join(cleaned) + ("\n" if cleaned else ""), encoding="utf-8")
        os.replace(tmp, p)
        return cleaned
