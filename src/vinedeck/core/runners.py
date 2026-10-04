"""Discovery of the compatibility runners VineDeck can use: system Wine and Steam's Proton.

Proton is found in every place Steam keeps it:

* ``<steam>/steamapps/common/Proton*``      official Valve builds installed through Steam
* ``<steam>/compatibilitytools.d/*``         custom builds such as GE-Proton, or ones from ProtonUp-Qt
* ``/usr/share/steam/compatibilitytools.d``  system-wide installs (e.g. AUR ``proton-ge-custom``)
* extra Steam library folders listed in ``steamapps/libraryfolders.vdf``

Native, Flatpak and Snap Steam installs are all checked. Nothing here executes anything.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from ..utils.logging import get_logger

log = get_logger("runners")

WINE_ID = "wine"
PROTON_PREFIX = "proton:"

_LIBRARY_PATH = re.compile(r'"path"\s+"((?:[^"\\]|\\.)*)"')
_DISPLAY_NAME = re.compile(r'"display_name"\s+"([^"]+)"')


@dataclass(frozen=True)
class Runner:
    id: str                 # "wine" or "proton:<absolute path to the proton script>"
    kind: str               # "wine" | "proton"
    name: str
    path: str = ""          # the proton script (empty for system Wine)
    source: str = ""        # e.g. "Steam", "Custom (compatibilitytools.d)"
    steam_root: str = ""    # Steam client install dir to hand to Proton

    @property
    def label(self) -> str:
        return f"{self.name}  ·  {self.source}" if self.source else self.name


def proton_id(script: str | Path) -> str:
    return f"{PROTON_PREFIX}{script}"


def is_proton_id(runner_id: str) -> bool:
    return runner_id.startswith(PROTON_PREFIX) and len(runner_id) > len(PROTON_PREFIX)


def proton_script_from_id(runner_id: str) -> str:
    return runner_id[len(PROTON_PREFIX):]


def system_wine_runner() -> Runner:
    return Runner(WINE_ID, "wine", "System Wine", source="wine binary from the field below")


# -- Steam locations -------------------------------------------------------------------------
def steam_root_candidates(home: Path | None = None, env: dict | None = None) -> list[Path]:
    home = home or Path.home()
    env = os.environ if env is None else env
    data_home = Path(env["XDG_DATA_HOME"]) if env.get("XDG_DATA_HOME", "").startswith("/") else home / ".local/share"
    flatpak = home / ".var/app/com.valvesoftware.Steam"
    return [
        home / ".steam/steam",
        home / ".steam/root",
        data_home / "Steam",
        home / ".local/share/Steam",
        home / ".steam/debian-installation",
        flatpak / ".local/share/Steam",
        flatpak / "data/Steam",
        home / "snap/steam/common/.local/share/Steam",
    ]


def discover_steam_roots(home: Path | None = None, env: dict | None = None) -> list[Path]:
    """Existing Steam installs, de-duplicated by real path (``~/.steam/steam`` is usually a symlink)."""
    seen: set[Path] = set()
    roots: list[Path] = []
    for cand in steam_root_candidates(home, env):
        try:
            real = cand.resolve()
        except OSError:
            continue
        has_steam = (real / "steamapps").is_dir() or (real / "compatibilitytools.d").is_dir()
        if real in seen or not has_steam:
            continue
        seen.add(real)
        roots.append(real)
    return roots


def library_folders(root: Path) -> list[Path]:
    """Extra Steam library folders (other drives) from ``libraryfolders.vdf``."""
    vdf = root / "steamapps" / "libraryfolders.vdf"
    try:
        text = vdf.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out: list[Path] = []
    for raw in _LIBRARY_PATH.findall(text):
        p = Path(raw.replace("\\\\", "\\").replace('\\"', '"'))
        if p.is_dir():
            out.append(p)
    return out


# -- Proton discovery -------------------------------------------------------------------------
def _is_proton_dir(d: Path) -> bool:
    script = d / "proton"
    return script.is_file() and os.access(script, os.X_OK)


def _display_name(d: Path) -> str:
    """GE-Proton and friends ship a ``compatibilitytool.vdf`` with a nicer name."""
    try:
        m = _DISPLAY_NAME.search((d / "compatibilitytool.vdf").read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return d.name
    return m.group(1).strip() if m else d.name


def _natural_key(name: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def discover_proton(home: Path | None = None, env: dict | None = None,
                    extra_tool_dirs: list[Path] | None = None) -> list[Runner]:
    roots = discover_steam_roots(home, env)
    main_root = str(roots[0]) if roots else ""
    found: dict[Path, Runner] = {}

    def add(d: Path, source: str) -> None:
        if not _is_proton_dir(d):
            return
        try:
            real = d.resolve()
        except OSError:
            return
        if real in found:
            return
        # keep the path the user would recognise (not a resolved symlink) in the id
        found[real] = Runner(proton_id(d / "proton"), "proton", _display_name(d), str(d / "proton"),
                             source, main_root)

    libraries: list[Path] = []
    tool_dirs: list[Path] = []
    for root in roots:
        libraries.append(root)
        libraries.extend(library_folders(root))
        tool_dirs.append(root / "compatibilitytools.d")
    tool_dirs += [Path("/usr/share/steam/compatibilitytools.d"),
                  Path("/usr/local/share/steam/compatibilitytools.d")]
    tool_dirs += list(extra_tool_dirs or [])

    seen_libs: set[Path] = set()
    for lib in libraries:
        try:
            real = lib.resolve()
        except OSError:
            continue
        if real in seen_libs:
            continue
        seen_libs.add(real)
        common = lib / "steamapps" / "common"
        try:
            entries = sorted(common.iterdir())
        except OSError:
            continue
        for d in entries:
            if d.name.lower().startswith("proton") and d.is_dir():
                add(d, "Steam")
    for td in tool_dirs:
        try:
            entries = sorted(td.iterdir())
        except OSError:
            continue
        for d in entries:
            if d.is_dir():
                add(d, "Custom" if not str(td).startswith("/usr/") else "System")

    runners = sorted(found.values(), key=lambda r: _natural_key(r.name), reverse=True)
    log.info("Found %d Proton build(s) in %d Steam install(s)", len(runners), len(roots))
    return runners


def discover_runners(home: Path | None = None, env: dict | None = None,
                     extra_tool_dirs: list[Path] | None = None) -> list[Runner]:
    """System Wine first, then every Proton build found."""
    return [system_wine_runner(), *discover_proton(home, env, extra_tool_dirs)]


def steam_root_for(script: str | Path, home: Path | None = None, env: dict | None = None) -> str:
    """The Steam client dir to pass as ``STEAM_COMPAT_CLIENT_INSTALL_PATH`` for a given Proton."""
    roots = discover_steam_roots(home, env)
    try:
        real = Path(script).resolve()
    except OSError:
        real = Path(script)
    for r in roots:
        if r in real.parents:
            return str(r)
    return str(roots[0]) if roots else ""
