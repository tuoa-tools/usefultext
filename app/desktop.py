"""Small OS integrations: open a folder, or reveal a file, in the user's file manager.

Copied from media_downloader, where the Windows /select quirk was found on a real PC.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def reveal_command(path: Path, platform: str, is_file: bool) -> list[str] | str:
    """The command that opens ``path`` (a directory) or its folder with the file selected.

    Windows Explorer's /select switch must arrive as one argument with only the path quoted -
    ``explorer /select,"C:\\dir with spaces\\file"`` - so that case is a plain string; as a
    list, Python would quote the whole argument and Explorer would open Documents instead.
    """
    if platform == "darwin":
        return ["open", "-R", str(path)] if is_file else ["open", str(path)]
    if platform == "win32":
        return f'explorer /select,"{path}"' if is_file else f'explorer "{path}"'
    return ["xdg-open", str(path.parent if is_file else path)]


def open_command(path: Path, platform: str) -> list[str]:
    """The command that opens a file with the program the OS uses for it (macOS / Linux)."""
    return ["open" if platform == "darwin" else "xdg-open", str(path)]


def open_file(path: Path) -> None:
    """Open a file with whatever the OS uses for it (an exported .md or .docx, say)."""
    path = Path(path)
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]  # the shell's "open" verb
        return
    subprocess.Popen(open_command(path, sys.platform))


def reveal(path: Path) -> None:
    path = Path(path)
    if sys.platform == "win32" and not path.is_file():
        os.startfile(path)  # type: ignore[attr-defined]
        return
    command = reveal_command(path, sys.platform, path.is_file())
    subprocess.Popen(command, shell=isinstance(command, str))
