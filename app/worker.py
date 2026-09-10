"""One worker thread reading documents one at a time.

OCR is CPU-bound and one engine instance keeps the machine usable, so the
queue is a plain FIFO of document ids and a single thread pulls from it.
Pause sets the document's stop event; run_job returns after the current
page and the pages already read are the result so far. Resume re-queues;
run_job's own resume skips what is done. There is no cancel.

The thread loads the OCR models first thing, so they are warm before the
first job; /api/health reports the engine state meanwhile.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

from app.library import Job, Library
from usefultext import Settings, ocr, run_job

log = logging.getLogger(__name__)


@dataclass
class Progress:
    doc_id: str
    status: str = "queued"  # queued | running
    done: int = 0
    total: int = 0
    current: str | None = None  # label of the page being read
    started_at: float | None = None
    page_seconds: list = field(default_factory=list)
    eta_seconds: float | None = None
    last_page: dict | None = None  # what the last page came out as
    force: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("page_seconds")
        return d


class Worker:
    def __init__(
        self,
        get_library: Callable[[], Library | None],
        get_settings: Callable[[Job], Settings],
    ) -> None:
        self.get_library = get_library
        self.get_settings = get_settings
        self.queue: queue.Queue = queue.Queue()
        self.progress: dict[str, Progress] = {}
        self.engine: dict = {"state": "idle", "error": None}
        self._stops: dict[str, threading.Event] = {}
        self._skip: set[str] = set()
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()
        self._shutdown = threading.Event()
        self.thread = threading.Thread(target=self._run, name="usefultext-worker", daemon=True)

    # --- lifecycle ---

    def start(self) -> None:
        self.thread.start()

    def stop(self, timeout: float = 30.0) -> None:
        self._shutdown.set()
        for ev in self._stops.values():
            ev.set()
        if self.thread.is_alive():
            self.thread.join(timeout)

    def lock(self, doc_id: str) -> threading.RLock:
        """The per-document lock every writer of that folder takes: the
        worker while it rewrites outputs, the API while it saves a correction."""
        with self._locks_guard:
            return self._locks.setdefault(doc_id, threading.RLock())

    # --- user actions ---

    def active(self, doc_id: str) -> Progress | None:
        return self.progress.get(doc_id)

    def enqueue(self, doc_id: str, force: bool = False) -> bool:
        """Start or resume. False if the document is already queued or running."""
        if doc_id in self.progress:
            return False
        self._skip.discard(doc_id)
        self.progress[doc_id] = Progress(doc_id=doc_id, force=force)
        self.queue.put((doc_id, force))
        return True

    def pause(self, doc_id: str) -> bool:
        """Stop after the current page (running) or take it off the queue
        (queued). False if it was doing nothing."""
        prog = self.progress.get(doc_id)
        if prog is None:
            return False
        if prog.status == "running":
            self._stops[doc_id].set()
        else:
            self._skip.add(doc_id)
            self.progress.pop(doc_id, None)
        return True

    # --- the thread ---

    def _run(self) -> None:
        self.engine = {"state": "loading", "error": None}
        t0 = time.perf_counter()
        if ocr.available():
            self.engine = {
                "state": "ready",
                "error": None,
                "load_seconds": round(time.perf_counter() - t0, 1),
            }
            log.info("OCR engine ready in %.1fs", time.perf_counter() - t0)
        else:
            self.engine = {"state": "failed", "error": ocr.import_error()}
            log.error("OCR engine unavailable: %s", ocr.import_error())
        while not self._shutdown.is_set():
            try:
                doc_id, force = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if doc_id in self._skip:
                self._skip.discard(doc_id)
                continue
            try:
                self._run_document(doc_id, force)
            except Exception:  # noqa: BLE001 - never let one document take the worker down
                log.exception("document %s failed unexpectedly", doc_id)
            finally:
                self.progress.pop(doc_id, None)
                self._stops.pop(doc_id, None)

    def _run_document(self, doc_id: str, force: bool) -> None:
        library = self.get_library()
        job = library.get(doc_id) if library else None
        prog = self.progress.get(doc_id)
        if job is None or prog is None:
            return
        if self.engine.get("state") != "ready":
            self._finish(library, job, error=f"OCR engine unavailable: {self.engine.get('error')}")
            return
        stop = threading.Event()
        self._stops[doc_id] = stop
        lock = self.lock(doc_id)
        settings = self.get_settings(job)
        sources = job.sources()
        prog.status, prog.started_at, prog.total = "running", time.time(), len(sources)
        prog.current = sources[0].label if sources else None
        precheck = {
            e.source(job.folder).key: e.sharpness for e in job.included() if e.sharpness is not None
        }

        def on_page(rec, i, n, resumed):
            prog.done = i
            prog.current = sources[i].label if i < n else None
            if not resumed and rec.status == "done":
                prog.page_seconds.append(rec.elapsed)
            if prog.page_seconds:
                prog.eta_seconds = round(
                    sum(prog.page_seconds) / len(prog.page_seconds) * (n - i), 1
                )
            prog.last_page = {
                "id": rec.id,
                "label": rec.label,
                "status": rec.status,
                "resumed": resumed,
                "mean_conf": rec.mean_conf,
                "low_conf": rec.low_conf,
                "blurry": rec.blurry,
                "rotation": rec.rotation,
                "error": rec.error,
            }
            with lock:
                library.refresh_summary(job, settings)

        try:
            summary = run_job(
                sources,
                job.folder,
                settings,
                on_page=on_page,
                should_stop=stop.is_set,
                force=force,
                precheck=precheck,
                title=job.title,
                finalize_lock=lock,
            )
        except Exception as exc:  # noqa: BLE001 - reported on the document, not raised
            log.exception("run_job failed for %s", doc_id)
            self._finish(library, job, error=f"{type(exc).__name__}: {exc}")
            return
        self._finish(
            library,
            job,
            processed=summary.processed,
            resumed=summary.resumed,
            failed=summary.failed,
            stopped_early=summary.stopped_early,
            elapsed=summary.elapsed,
        )

    def _finish(self, library: Library, job: Job, **result) -> None:
        with self.lock(job.id):
            fresh = library.get(job.id) or job
            fresh.last_run = {"finished_at": time.time(), "error": None, **result}
            fresh.save()
            library.refresh_summary(fresh, self.get_settings(fresh))
