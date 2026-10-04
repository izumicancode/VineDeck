"""Path validation and opening folders in the user's file manager."""

from __future__ import annotations

import os
from pathlib import Path

EXECUTABLE_SUFFIXES = (".exe", ".lnk")


def expand(path: str) -> Path:
    return Path(os.path.expanduser(path.strip()))


def validate_executable(path: str) -> str | None:
    """Return an error message, or None if *path* is an acceptable executable."""
    if not path.strip():
        return "Choose an executable (.exe or .lnk)."
    p = expand(path)
    if not p.exists():
        return "That file does not exist."
    if not p.is_file():
        return "That path is not a file."
    if p.suffix.lower() not in EXECUTABLE_SUFFIXES:
        return "Only .exe and .lnk files are supported."
    if not os.access(p, os.R_OK):
        return "You do not have permission to read that file."
    return None


def validate_directory(path: str, *, must_exist: bool = True) -> str | None:
    if not path.strip():
        return None
    p = expand(path)
    if must_exist and not p.is_dir():
        return "That folder does not exist."
    return None


def open_in_file_manager(path: str | Path) -> bool:
    """Open a folder (or reveal a file's folder) with the desktop's default handler."""
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices

    p = Path(path)
    target = p if p.is_dir() else p.parent
    if not target.is_dir():
        return False
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
