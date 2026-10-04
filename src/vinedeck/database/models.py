"""Plain data classes shared between the database, core and UI layers."""

from __future__ import annotations

from dataclasses import dataclass, field, fields


@dataclass
class Category:
    id: int
    name: str
    sort_order: int = 0


@dataclass
class Application:
    id: int | None = None
    name: str = ""
    executable_path: str = ""
    wine_prefix: str = ""
    working_directory: str = ""
    launch_arguments: str = ""
    env_vars: dict[str, str] = field(default_factory=dict)
    description: str = ""
    category_id: int | None = None
    cover_path: str = ""          # bare file name inside the covers directory
    icon_path: str = ""           # bare file name inside the icons directory
    favorite: bool = False
    sort_order: int = 0
    launch_count: int = 0
    last_played: str | None = None   # ISO-8601 UTC
    created_at: str = ""
    updated_at: str = ""
    developer: str = ""
    publisher: str = ""
    version: str = ""
    genre: str = ""
    release_year: str = ""
    website: str = ""
    # Joined in by queries, not stored on the applications table.
    category_name: str = ""

    @property
    def is_shortcut(self) -> bool:
        return self.executable_path.lower().endswith(".lnk")


APPLICATION_COLUMNS = [
    f.name for f in fields(Application) if f.name not in ("id", "category_name")
]
