"""Display formatting helpers."""

from __future__ import annotations

from datetime import datetime, timezone


def _parse(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def format_last_played(iso: str | None, now: datetime | None = None) -> str:
    dt = _parse(iso)
    if dt is None:
        return "Never"
    now = (now or datetime.now().astimezone())
    days = (now.astimezone().date() - dt.astimezone().date()).days
    if days <= 0:
        return "Today"
    if days == 1:
        return "Yesterday"
    if days < 7:
        return f"{days} days ago"
    return dt.astimezone().strftime("%b %d, %Y")


def format_datetime(iso: str | None) -> str:
    dt = _parse(iso)
    return dt.astimezone().strftime("%b %d, %Y %H:%M") if dt else "—"


def short_path(path: str, limit: int = 60) -> str:
    import os
    home = os.path.expanduser("~")
    if path.startswith(home):
        path = "~" + path[len(home):]
    if len(path) <= limit:
        return path
    return path[: limit // 3] + "…" + path[-(limit * 2 // 3):]
