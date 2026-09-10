"""UsefulText — local, offline OCR of photographed document pages.

Milestone 1 exposes the processing pipeline as importable functions so the
Milestone 2 FastAPI layer can drive it without touching the CLI:

    from usefultext import Settings, discover_sources, run_job

Nothing here talks to the network; RapidOCR fetches its models once on first
use and runs from the local copy thereafter.
"""

from .checks import JobWarning, job_warnings
from .corrections import Corrections
from .inputs import PageSource, discover_sources, order_files
from .pipeline import JobSummary, process_page, run_job, sharpness_precheck
from .settings import Settings

__version__ = "0.2.0"

__all__ = [
    "Settings",
    "PageSource",
    "discover_sources",
    "order_files",
    "run_job",
    "process_page",
    "sharpness_precheck",
    "JobSummary",
    "Corrections",
    "JobWarning",
    "job_warnings",
    "__version__",
]
