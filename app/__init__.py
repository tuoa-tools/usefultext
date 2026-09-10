"""UsefulText's local app: FastAPI on localhost around the `usefultext` pipeline.

Step 0 of PLAN_M2.md brought in paths, desktop and launcher, adapted from
adam-tuoa/media_downloader. main.py, library.py and worker.py arrive in step 2.
"""

from usefultext import __version__

__all__ = ["__version__"]
