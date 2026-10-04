"""SQLite access layer. All SQL lives here."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from ..utils.logging import get_logger
from .migrations import migrate
from .models import APPLICATION_COLUMNS, Application, Category

log = get_logger("db")

_SELECT_APP = """
    SELECT a.*, COALESCE(c.name, '') AS category_name
    FROM applications a LEFT JOIN categories c ON c.id = a.category_id
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path))
        self._conn.isolation_level = None      # explicit transactions (see _tx)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        if str(path) != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")
        migrate(self._conn)

    # -- infrastructure ------------------------------------------------------
    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield self._conn
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        else:
            self._conn.execute("COMMIT")

    def close(self) -> None:
        self._conn.close()

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    # -- applications --------------------------------------------------------
    @staticmethod
    def _row_to_app(row: sqlite3.Row) -> Application:
        data = dict(row)
        try:
            env = json.loads(data.pop("env_vars") or "{}")
            env = {str(k): str(v) for k, v in env.items()} if isinstance(env, dict) else {}
        except (ValueError, AttributeError):
            env = {}
        data["favorite"] = bool(data["favorite"])
        return Application(env_vars=env, **data)

    @staticmethod
    def _app_values(app: Application) -> list:
        values = []
        for col in APPLICATION_COLUMNS:
            v = getattr(app, col)
            if col == "env_vars":
                v = json.dumps(v, ensure_ascii=False)
            elif col == "favorite":
                v = int(bool(v))
            values.append(v)
        return values

    def add_application(self, app: Application) -> Application:
        now = utcnow()
        app.created_at = app.created_at or now
        app.updated_at = now
        with self._tx() as c:
            if not app.sort_order:
                row = c.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM applications").fetchone()
                app.sort_order = row[0]
            cols = ", ".join(APPLICATION_COLUMNS)
            marks = ", ".join("?" for _ in APPLICATION_COLUMNS)
            cur = c.execute(f"INSERT INTO applications ({cols}) VALUES ({marks})",
                            self._app_values(app))
            app.id = cur.lastrowid
        return self.get_application(app.id)  # type: ignore[arg-type]

    def update_application(self, app: Application) -> Application:
        if app.id is None:
            raise ValueError("Cannot update an application without an id")
        app.updated_at = utcnow()
        sets = ", ".join(f"{col} = ?" for col in APPLICATION_COLUMNS)
        with self._tx() as c:
            c.execute(f"UPDATE applications SET {sets} WHERE id = ?",
                      self._app_values(app) + [app.id])
        return self.get_application(app.id)  # type: ignore[return-value]

    def get_application(self, app_id: int) -> Application | None:
        row = self._conn.execute(_SELECT_APP + " WHERE a.id = ?", (app_id,)).fetchone()
        return self._row_to_app(row) if row else None

    def list_applications(self) -> list[Application]:
        rows = self._conn.execute(_SELECT_APP + " ORDER BY a.sort_order, a.id").fetchall()
        return [self._row_to_app(r) for r in rows]

    def count_applications(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]

    def delete_application(self, app_id: int) -> bool:
        with self._tx() as c:
            return c.execute("DELETE FROM applications WHERE id = ?", (app_id,)).rowcount > 0

    def set_favorite(self, app_id: int, favorite: bool) -> None:
        with self._tx() as c:
            c.execute("UPDATE applications SET favorite = ?, updated_at = ? WHERE id = ?",
                      (int(favorite), utcnow(), app_id))

    def reorder_application(self, dragged_id: int, target_id: int) -> None:
        """Move *dragged_id* to the position of *target_id*.

        Dragging towards the end lands after the target, towards the start before it.
        """
        if dragged_id == target_id:
            return
        with self._tx() as c:
            ids = [r[0] for r in c.execute("SELECT id FROM applications ORDER BY sort_order, id")]
            if dragged_id not in ids or target_id not in ids:
                return
            forward = ids.index(dragged_id) < ids.index(target_id)
            ids.remove(dragged_id)
            ids.insert(ids.index(target_id) + (1 if forward else 0), dragged_id)
            c.executemany("UPDATE applications SET sort_order = ? WHERE id = ?",
                          [(i + 1, app_id) for i, app_id in enumerate(ids)])

    # -- launches ------------------------------------------------------------
    def record_launch_start(self, app_id: int) -> int:
        now = utcnow()
        with self._tx() as c:
            c.execute("UPDATE applications SET launch_count = launch_count + 1, "
                      "last_played = ? WHERE id = ?", (now, app_id))
            cur = c.execute("INSERT INTO launch_history(application_id, started_at) "
                            "VALUES (?, ?)", (app_id, now))
            return cur.lastrowid

    def record_launch_end(self, history_id: int, exit_code: int | None) -> None:
        with self._tx() as c:
            c.execute("UPDATE launch_history SET ended_at = ?, exit_code = ? WHERE id = ?",
                      (utcnow(), exit_code, history_id))

    def launch_history(self, app_id: int, limit: int = 20) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM launch_history WHERE application_id = ? "
            "ORDER BY id DESC LIMIT ?", (app_id, limit)).fetchall()

    # -- categories ----------------------------------------------------------
    def list_categories(self) -> list[Category]:
        rows = self._conn.execute(
            "SELECT id, name, sort_order FROM categories ORDER BY sort_order, name COLLATE NOCASE")
        return [Category(**dict(r)) for r in rows]

    def get_category_by_name(self, name: str) -> Category | None:
        row = self._conn.execute(
            "SELECT id, name, sort_order FROM categories WHERE name = ? COLLATE NOCASE",
            (name.strip(),)).fetchone()
        return Category(**dict(row)) if row else None

    def add_category(self, name: str) -> Category:
        name = name.strip()
        if not name:
            raise ValueError("Category name cannot be empty")
        with self._tx() as c:
            nxt = c.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM categories").fetchone()[0]
            try:
                cur = c.execute("INSERT INTO categories(name, sort_order) VALUES (?, ?)", (name, nxt))
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"A category named “{name}” already exists") from exc
        return Category(cur.lastrowid, name, nxt)

    def rename_category(self, category_id: int, name: str) -> None:
        name = name.strip()
        if not name:
            raise ValueError("Category name cannot be empty")
        with self._tx() as c:
            try:
                c.execute("UPDATE categories SET name = ? WHERE id = ?", (name, category_id))
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"A category named “{name}” already exists") from exc

    def delete_category(self, category_id: int) -> None:
        """Delete a category; its applications become uncategorised (not deleted)."""
        with self._tx() as c:
            c.execute("DELETE FROM categories WHERE id = ?", (category_id,))
