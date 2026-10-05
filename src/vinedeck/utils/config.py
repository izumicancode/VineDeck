"""User preferences, persisted as JSON in the XDG config directory."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable

from .logging import get_logger

log = get_logger("config")

DEFAULTS: dict[str, Any] = {
    # appearance
    "theme": "dark",                  # dark | light | system
    "accent": "#3ecf8e",
    "background_mode": "default",     # default | custom
    "background_image": "",
    "card_style": "rounded",          # rounded | square
    "animations": True,
    "blur": True,
    # library
    "view_mode": "grid",              # grid | compact | list | large
    "sort_key": "name",
    "sort_reverse": False,
    "grid_columns": 0,                # 0 = fit to window
    "card_width": 200,
    "card_height": 300,
    "gap_h": 20,
    "gap_v": 20,
    "corner_radius": 12,
    "show_title": True,
    "show_category": True,
    "show_favorite": True,
    "show_launch": True,
    "show_description": True,
    # wine
    "runner": "wine",                 # "wine" (system Wine) | "proton:<path to a proton script>"
    "wine_binary": "wine",
    "default_prefix": "",
    # general / state
    "confirm_remove": True,
    "restore_geometry": True,
    "sidebar_collapsed": False,
    "window_geometry": "",
    "first_run_done": False,
}

CHOICES: dict[str, tuple] = {
    "theme": ("dark", "light", "system"),
    "background_mode": ("default", "custom"),
    "card_style": ("rounded", "square"),
    "view_mode": ("grid", "compact", "list", "large"),
    "sort_key": ("name", "added", "played", "count", "category", "custom"),
}

RANGES: dict[str, tuple[int, int]] = {
    "grid_columns": (0, 12),
    "card_width": (120, 420),
    "card_height": (160, 640),
    "gap_h": (0, 60),
    "gap_v": (0, 60),
    "corner_radius": (0, 32),
}


def sanitize(key: str, value: Any) -> Any:
    """Coerce *value* to the type of the default; fall back to the default."""
    default = DEFAULTS[key]
    try:
        if isinstance(default, bool):
            if not isinstance(value, bool):
                raise TypeError
        elif isinstance(default, int):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError
            value = int(value)
            lo, hi = RANGES.get(key, (-(10 ** 9), 10 ** 9))
            value = max(lo, min(hi, value))
        elif isinstance(default, str):
            if not isinstance(value, str):
                raise TypeError
            value = value.strip()
        if key in CHOICES and value not in CHOICES[key]:
            raise ValueError
        if key == "accent" and not (len(value) == 7 and value.startswith("#")):
            raise ValueError
        if key == "runner" and value != "wine" and not (value.startswith("proton:") and len(value) > 7):
            raise ValueError
    except (TypeError, ValueError):
        return default
    return value


def validate_key(key: str) -> str:
    """Return a known config key or raise `KeyError` for unsupported names."""
    if key not in DEFAULTS:
        raise KeyError(key)
    return key


class Settings:
    def __init__(self, path: Path | None = None):
        self._path = path
        self._values: dict[str, Any] = dict(DEFAULTS)
        self._listeners: list[Callable[[str, Any], None]] = []
        if path is not None:
            self.load()

    @classmethod
    def from_file(cls, path: Path | str) -> "Settings":
        return cls(Path(path))

    def load(self) -> None:
        if self._path is None or not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("config root must be an object")
        except (OSError, ValueError) as exc:
            log.warning("Could not read config (%s); using defaults", exc)
            return
        for key in DEFAULTS:
            if key in raw:
                self._values[key] = sanitize(key, raw[key])

    def save(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self._path.parent, prefix=".config-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._values, fh, indent=2, sort_keys=True)
            os.replace(tmp, self._path)
        except OSError as exc:
            log.error("Could not save config: %s", exc)
            try:
                os.unlink(tmp)
            except OSError:
                pass

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

    def __contains__(self, key: str) -> bool:
        return key in self._values

    def __len__(self) -> int:
        return len(self._values)

    def __iter__(self):
        return iter(self._values)

    def __getitem__(self, key: str) -> Any:
        return self._values[key]

    def set(self, key: str, value: Any, *, save: bool = True) -> None:
        key = validate_key(key)
        value = sanitize(key, value)
        if self._values[key] == value:
            return
        self._values[key] = value
        if save:
            self.save()
        for cb in list(self._listeners):
            cb(key, value)

    def keys(self) -> list[str]:
        return list(self._values)

    def items(self) -> list[tuple[str, Any]]:
        return list(self._values.items())

    def update(self, values: dict[str, Any], *, save: bool = True) -> None:
        for key, value in values.items():
            self.set(key, value, save=False)
        if save:
            self.save()

    def subscribe(self, callback: Callable[[str, Any], None]) -> None:
        self._listeners.append(callback)

    def reset(self, keys: list[str] | None = None) -> None:
        for key in keys or list(DEFAULTS):
            self.set(key, DEFAULTS[key], save=False)
        self.save()

    def copy(self) -> dict[str, Any]:
        return dict(self._values)

    def as_dict(self) -> dict[str, Any]:
        return self.copy()
