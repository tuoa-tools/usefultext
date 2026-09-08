"""PhotoText — local, offline OCR of photographed document pages.

Milestone 1 exposes the processing pipeline as importable functions so the
Milestone 2 FastAPI layer can drive it without touching the CLI:

    from phototext import Settings, discover_sources, run_job

Nothing here talks to the network; RapidOCR fetches its models once on first
use and runs from the local copy thereafter.
"""
from .settings import Settings
from .inputs import PageSource, discover_sources, order_files
from .pipeline import run_job, process_page, sharpness_precheck, JobSummary

__version__ = "0.1.0"

__all__ = [
    "Settings",
    "PageSource",
    "discover_sources",
    "order_files",
    "run_job",
    "process_page",
    "sharpness_precheck",
    "JobSummary",
    "__version__",
]
