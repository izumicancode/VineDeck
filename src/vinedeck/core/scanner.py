"""Finds existing Wine prefixes to suggest in the UI. Never executes anything."""

from __future__ import annotations

import os
from pathlib import Path


def default_prefix() -> Path:
    env = os.environ.get("WINEPREFIX", "")
    return Path(env) if env else Path.home() / ".wine"


def is_prefix(path: Path) -> bool:
    return (path / "system.reg").is_file() or (path / "drive_c").is_dir()


def discover_prefixes(extra_roots: list[Path] | None = None, limit: int = 50) -> list[Path]:
    home = Path.home()
    found: list[Path] = []
    seen: set[Path] = set()

    def consider(p: Path) -> None:
        try:
            rp = p.resolve()
            if rp not in seen and p.is_dir() and is_prefix(p):
                seen.add(rp)
                found.append(p)
        except OSError:
            pass

    consider(default_prefix())
    roots = [home / "Games", home / "WinePrefixes", home / ".local/share/wineprefixes",
             home / ".local/share/bottles/bottles", home / "Wine", *(extra_roots or [])]
    for root in roots:
        consider(root)
        try:
            for child in sorted(root.iterdir()):
                if len(found) >= limit:
                    return found
                consider(child)
        except OSError:
            continue
    return found
