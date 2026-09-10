"""`python -m usefultext` — the same as the `usefultext` console script."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
