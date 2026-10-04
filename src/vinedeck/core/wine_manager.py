"""Detection of the active runner (system Wine or a Steam Proton build)."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..utils.logging import get_logger
from .runners import WINE_ID, is_proton_id, proton_script_from_id, steam_root_for

log = get_logger("wine")


@dataclass(frozen=True)
class WineInfo:
    found: bool
    path: str | None = None       # resolved absolute path
    version: str | None = None
    error: str | None = None
    kind: str = "wine"            # "wine" | "proton"
    steam_root: str = ""          # Proton only: Steam client dir for STEAM_COMPAT_CLIENT_INSTALL_PATH

    @property
    def runner_label(self) -> str:
        return "Proton" if self.kind == "proton" else "Wine"

    @property
    def summary(self) -> str:
        if self.found:
            return f"{self.version or self.runner_label} ({self.path})"
        return self.error or f"{self.runner_label} not found"


def detect_wine(binary: str = "wine", *, runner: Callable = subprocess.run,
                which: Callable = shutil.which) -> WineInfo:
    """Equivalent of ``which wine`` followed by ``wine --version``."""
    binary = (binary or "wine").strip()
    resolved = which(binary)
    if not resolved:
        return WineInfo(False, error=f"“{binary}” was not found. Install Wine "
                                     f"(sudo pacman -S wine) or set its path in Settings → Wine.")
    try:
        result = runner([resolved, "--version"], capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired:
        return WineInfo(False, resolved, error="Wine did not answer “--version” in time.")
    except OSError as exc:
        return WineInfo(False, resolved, error=f"Wine could not be executed: {exc.strerror or exc}")
    version = (result.stdout or "").strip()
    if result.returncode != 0 or not version:
        detail = (result.stderr or "").strip().splitlines()
        return WineInfo(False, resolved,
                        error="Wine returned an error for “--version”" + (f": {detail[0]}" if detail else "."))
    log.info("Detected %s at %s", version, resolved)
    return WineInfo(True, resolved, version)


def detect_proton(script: str, *, home: Path | None = None) -> WineInfo:
    """Check a Proton build. Proton has no ``--version``; it is validated by its launcher script."""
    p = Path(os.path.expanduser(script))
    if p.is_dir():
        p = p / "proton"
    if not p.is_file():
        return WineInfo(False, str(p), kind="proton",
                        error=f"The Proton build at “{p.parent}” was not found. It may have been uninstalled; "
                              f"pick another runner in Settings → Wine.")
    if not os.access(p, os.X_OK):
        return WineInfo(False, str(p), kind="proton",
                        error=f"“{p}” is not executable. Check the file permissions of this Proton build.")
    name = p.parent.name
    try:                                   # "<timestamp> <build name>"
        parts = (p.parent / "version").read_text(encoding="utf-8").split(None, 1)
        if len(parts) == 2:
            name = parts[1].strip() or name
    except OSError:
        pass
    root = steam_root_for(p, home)
    log.info("Detected Proton %s at %s", name, p)
    return WineInfo(True, str(p), name, kind="proton", steam_root=root)


def detect_runner(runner_id: str = WINE_ID, binary: str = "wine") -> WineInfo:
    if is_proton_id(runner_id):
        return detect_proton(proton_script_from_id(runner_id))
    return detect_wine(binary)


class WineManager:
    """Holds the currently selected runner (system Wine or Proton) and its detection result."""

    def __init__(self, binary: str = "wine", runner: str = WINE_ID):
        self.binary = binary
        self.runner = runner
        self.info = WineInfo(False, error="Not checked yet")

    def refresh(self, binary: str | None = None, runner: str | None = None) -> WineInfo:
        if binary is not None:
            self.binary = binary
        if runner is not None:
            self.runner = runner
        self.info = detect_runner(self.runner, self.binary)
        return self.info
