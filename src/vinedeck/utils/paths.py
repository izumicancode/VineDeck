"""XDG-aware filesystem locations."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from ..branding import APP_SLUG


def _xdg(env: Mapping[str, str], var: str, fallback: str) -> Path:
    value = env.get(var, "")
    if value is None:
        value = ""
    value = str(value).strip()
    # The XDG spec says relative paths must be ignored.
    if value and os.path.isabs(value):
        return Path(value)
    return Path.home() / fallback


@dataclass(frozen=True)
class AppPaths:
    config_dir: Path
    data_dir: Path
    cache_dir: Path

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "AppPaths":
        env = os.environ if env is None else env
        return cls(
            config_dir=_xdg(env, "XDG_CONFIG_HOME", ".config") / APP_SLUG,
            data_dir=_xdg(env, "XDG_DATA_HOME", ".local/share") / APP_SLUG,
            cache_dir=_xdg(env, "XDG_CACHE_HOME", ".cache") / APP_SLUG,
        )

    @classmethod
    def under(cls, root: Path) -> "AppPaths":
        """Self-contained layout, used by tests."""
        return cls(root / "config", root / "data", root / "cache")

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.json"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "library.db"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def covers_dir(self) -> Path:
        return self.data_dir / "artwork" / "covers"

    @property
    def icons_dir(self) -> Path:
        return self.data_dir / "artwork" / "icons"

    @property
    def backgrounds_dir(self) -> Path:
        return self.data_dir / "artwork" / "backgrounds"

    @property
    def proton_dir(self) -> Path:
        """Per-application Proton compatdata folders (VineDeck-owned; never inside a game folder)."""
        return self.data_dir / "proton"

    @property
    def thumbs_dir(self) -> Path:
        return self.cache_dir / "thumbnails"

    @property
    def theme_cache_dir(self) -> Path:
        return self.cache_dir / "theme"

    def ensure(self) -> "AppPaths":
        for d in (self.config_dir, self.data_dir, self.cache_dir, self.logs_dir,
                  self.covers_dir, self.icons_dir, self.backgrounds_dir, self.proton_dir,
                  self.thumbs_dir, self.theme_cache_dir):
            d.mkdir(parents=True, exist_ok=True)
        return self
