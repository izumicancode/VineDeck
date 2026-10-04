"""Schema migrations, tracked with SQLite's ``PRAGMA user_version``.

To change the schema, append a new ``(version, statements)`` entry. Never edit an
existing entry once released.
"""

from __future__ import annotations

import sqlite3

from ..utils.logging import get_logger

log = get_logger("db.migrations")

DEFAULT_CATEGORIES = ("Games", "Applications", "Utilities", "Tools", "Other")

_V1 = [
    """CREATE TABLE categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE COLLATE NOCASE,
        sort_order INTEGER NOT NULL DEFAULT 0
    )""",
    """CREATE TABLE applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        executable_path TEXT NOT NULL,
        wine_prefix TEXT NOT NULL DEFAULT '',
        working_directory TEXT NOT NULL DEFAULT '',
        launch_arguments TEXT NOT NULL DEFAULT '',
        env_vars TEXT NOT NULL DEFAULT '{}',
        description TEXT NOT NULL DEFAULT '',
        category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
        cover_path TEXT NOT NULL DEFAULT '',
        icon_path TEXT NOT NULL DEFAULT '',
        favorite INTEGER NOT NULL DEFAULT 0,
        sort_order INTEGER NOT NULL DEFAULT 0,
        launch_count INTEGER NOT NULL DEFAULT 0,
        last_played TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE launch_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
        started_at TEXT NOT NULL,
        ended_at TEXT,
        exit_code INTEGER
    )""",
    "CREATE INDEX idx_apps_name ON applications(name COLLATE NOCASE)",
    "CREATE INDEX idx_apps_category ON applications(category_id)",
    "CREATE INDEX idx_apps_favorite ON applications(favorite)",
    "CREATE INDEX idx_apps_last_played ON applications(last_played)",
    "CREATE INDEX idx_apps_sort_order ON applications(sort_order)",
    "CREATE INDEX idx_history_app ON launch_history(application_id)",
]

_V2 = [f"ALTER TABLE applications ADD COLUMN {col} TEXT NOT NULL DEFAULT ''"
       for col in ("developer", "publisher", "version", "genre", "release_year", "website")]

MIGRATIONS: list[tuple[int, list[str]]] = [(1, _V1), (2, _V2)]
LATEST_VERSION = MIGRATIONS[-1][0]


def current_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def migrate(conn: sqlite3.Connection, target: int | None = None) -> int:
    """Apply pending migrations (each atomically). Returns the resulting version.

    The connection must be in autocommit mode (``isolation_level=None``).
    """
    target = LATEST_VERSION if target is None else target
    version = current_version(conn)
    if version > LATEST_VERSION:
        raise RuntimeError(
            f"Database schema v{version} is newer than this application supports "
            f"(v{LATEST_VERSION}). Please update the application.")
    for number, statements in MIGRATIONS:
        if number <= version or number > target:
            continue
        log.info("Applying database migration v%d", number)
        conn.execute("BEGIN IMMEDIATE")
        try:
            for stmt in statements:
                conn.execute(stmt)
            if number == 1:
                conn.executemany(
                    "INSERT INTO categories(name, sort_order) VALUES (?, ?)",
                    [(name, i) for i, name in enumerate(DEFAULT_CATEGORIES)])
            conn.execute(f"PRAGMA user_version = {int(number)}")
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return current_version(conn)
