"""Builds the Wine or Proton command line and environment for an application.

Nothing here executes anything (the only side effect is creating VineDeck's own Proton compatdata
folder); see :mod:`vinedeck.core.process_manager`.
"""

from __future__ import annotations

import hashlib
import os
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from ..database.models import Application
from ..utils.platform import is_root
from .wine_manager import WineInfo

_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class LaunchError(Exception):
    """A user-presentable launch failure."""

    def __init__(self, message: str, causes: list[str] | None = None, details: str = ""):
        super().__init__(message)
        self.message = message
        self.causes = causes or []
        self.details = details


@dataclass(frozen=True)
class LaunchSpec:
    app_id: int | None
    name: str
    argv: list[str]
    env: dict[str, str]
    cwd: str
    wine_prefix: str = ""
    env_overrides: tuple[str, ...] = field(default_factory=tuple)   # names only (no values in logs)
    compat_data: str = ""        # Proton only: STEAM_COMPAT_DATA_PATH (the prefix lives in <compat_data>/pfx)

    def describe(self) -> str:
        """Human-readable summary for logs. Environment *values* are omitted."""
        shown = " ".join(shlex.quote(a) for a in self.argv)
        extras = f" [env: {', '.join(self.env_overrides)}]" if self.env_overrides else ""
        if self.compat_data:
            prefix = f"STEAM_COMPAT_DATA_PATH={shlex.quote(self.compat_data)} "
        else:
            prefix = f"WINEPREFIX={shlex.quote(self.wine_prefix)} " if self.wine_prefix else ""
        return f"{prefix}{shown} (cwd={self.cwd}){extras}"


def parse_arguments(text: str) -> list[str]:
    try:
        return shlex.split(text or "")
    except ValueError as exc:
        raise LaunchError(
            "The launch arguments could not be understood.",
            ["An opening quote has no matching closing quote."], str(exc)) from exc


def validate_env_name(name: str) -> bool:
    return bool(_ENV_NAME.match(name))


def proton_compat_location(app: Application, proton_root: Path) -> tuple[Path, Path | None]:
    """Where Proton keeps this application's prefix.

    Proton always uses ``$STEAM_COMPAT_DATA_PATH/pfx`` as ``WINEPREFIX``. Returns
    ``(compat_data_dir, link_target)``; *link_target* is set when the application's prefix is a plain
    Wine prefix that has to be reached through a ``pfx`` symlink inside a VineDeck-owned folder.
    """
    raw = app.wine_prefix.strip()
    if not raw:
        return proton_root / (f"app-{app.id}" if app.id is not None else "default"), None
    pfx = Path(os.path.expanduser(raw))
    if pfx.name == "pfx":                       # already a compatdata/pfx folder
        return pfx.parent, None
    if (pfx / "pfx").is_dir():                  # the compatdata folder itself (e.g. steamapps/compatdata/123)
        return pfx, None
    digest = hashlib.sha1(str(pfx.resolve()).encode()).hexdigest()[:12]
    return proton_root / "linked" / digest, pfx


def _prepare_proton_compat(compat: Path, link_target: Path | None) -> None:
    try:
        compat.mkdir(parents=True, exist_ok=True)
        if link_target is None:
            return
        link = compat / "pfx"
        if link.is_symlink():
            if Path(os.readlink(link)) == link_target:
                return
            link.unlink()
        elif link.exists():
            raise LaunchError("VineDeck’s Proton folder for this prefix is in an unexpected state.",
                              ["Delete the folder and launch again"], f"Folder: {compat}")
        link.symlink_to(link_target, target_is_directory=True)
    except OSError as exc:
        raise LaunchError("VineDeck could not prepare the Proton prefix folder.",
                          ["The data folder is not writable"], f"{compat}: {exc}") from exc


def build_launch_spec(app: Application, wine_path: str | None, *,
                      base_env: Mapping[str, str] | None = None,
                      runner: WineInfo | None = None,
                      proton_root: Path | None = None) -> LaunchSpec:
    """Validate *app* and construct the argument array and environment.

    With a Proton *runner* the command is ``proton run <exe>`` and the prefix is handled through
    ``STEAM_COMPAT_DATA_PATH`` (under *proton_root* unless the application's own prefix is a
    compatdata folder). Otherwise it is ``wine <exe>`` with ``WINEPREFIX``.
    """
    use_proton = runner is not None and runner.kind == "proton"
    name = "Proton" if use_proton else "Wine"
    if is_root():
        raise LaunchError("Refusing to run applications as root.",
                          ["Start the launcher as a normal user."])
    if not wine_path:
        raise LaunchError(
            f"{name} could not be started.",
            [f"{name} is not installed", f"The {name} executable is invalid",
             "The runner selected in Settings → Wine is wrong"])
    if use_proton and proton_root is None:
        raise LaunchError("Proton could not be started.", ["No folder is available for Proton prefixes"])

    exe = Path(os.path.expanduser(app.executable_path))
    if not app.executable_path.strip() or not exe.is_file():
        raise LaunchError(
            "The application’s executable could not be found.",
            ["The file was moved, renamed or deleted",
             "The drive or folder containing it is not mounted",
             "You do not have permission to read it"],
            f"Executable: {app.executable_path}")
    if not os.access(exe, os.R_OK):
        raise LaunchError("The executable cannot be accessed.",
                          ["You do not have permission to read it"], f"Executable: {exe}")

    prefix = ""
    if app.wine_prefix.strip():
        pfx = Path(os.path.expanduser(app.wine_prefix.strip()))
        if not pfx.is_dir():
            raise LaunchError(
                "The selected Wine prefix does not exist.",
                ["The folder was moved or deleted",
                 "The prefix has not been created yet (create it with “WINEPREFIX=… wineboot”)"],
                f"Prefix: {app.wine_prefix}")
        prefix = str(pfx)

    if app.working_directory.strip():
        cwd_path = Path(os.path.expanduser(app.working_directory.strip()))
        if not cwd_path.is_dir():
            raise LaunchError("The working directory does not exist.",
                              ["The folder was moved or deleted"],
                              f"Working directory: {app.working_directory}")
        cwd = str(cwd_path)
    else:
        cwd = str(exe.parent)

    args = parse_arguments(app.launch_arguments)
    # `.lnk` shortcuts have to go through `start /unix`; Proton's `run` hands its arguments to wine.
    target = ["start", "/unix", str(exe)] if exe.suffix.lower() == ".lnk" else [str(exe)]
    if use_proton:
        argv = [wine_path, "run", *target, *args]
    else:
        argv = [wine_path, *target, *args]

    env = dict(os.environ if base_env is None else base_env)
    compat = ""
    if use_proton:
        compat_dir, link_target = proton_compat_location(app, Path(proton_root))
        _prepare_proton_compat(compat_dir, link_target)
        compat = str(compat_dir)
        env.pop("WINEPREFIX", None)               # Proton derives it from the compat data path
        env["STEAM_COMPAT_DATA_PATH"] = compat
        env["STEAM_COMPAT_INSTALL_PATH"] = str(exe.parent)
        if runner.steam_root:
            env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = runner.steam_root
    elif prefix:
        env["WINEPREFIX"] = prefix
    overrides: list[str] = []
    for name_, value in app.env_vars.items():
        name_ = name_.strip()
        if not validate_env_name(name_):
            raise LaunchError("An environment variable has an invalid name.",
                              ["Names may only contain letters, digits and underscores, "
                               "and cannot start with a digit"], f"Variable: {name_!r}")
        env[name_] = value
        overrides.append(name_)

    return LaunchSpec(app.id, app.name, argv, env, cwd, "" if use_proton else prefix,
                      tuple(overrides), compat)
