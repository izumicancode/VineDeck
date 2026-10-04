"""Pure filtering and sorting of the application list (no Qt, no SQL)."""

from __future__ import annotations

from dataclasses import dataclass

from ..database.models import Application

SORT_LABELS = {
    "name": "Name",
    "added": "Recently Added",
    "played": "Recently Played",
    "count": "Most Played",
    "category": "Category",
    "custom": "Custom Order",
}

# Keys whose natural order is "largest/newest first".
_DESC_BY_DEFAULT = {"added", "played", "count"}


@dataclass(frozen=True)
class LibraryQuery:
    section: str = "all"            # all | favorites | recent | most_played | category
    category_id: int | None = None
    text: str = ""
    sort_key: str = "name"
    reverse: bool = False


def matches_text(app: Application, text: str) -> bool:
    """Case-insensitive; every word must appear in name, category or description."""
    words = text.casefold().split()
    if not words:
        return True
    haystack = f"{app.name}\n{app.category_name}\n{app.description}".casefold()
    return all(w in haystack for w in words)


def filter_and_sort(apps: list[Application], q: LibraryQuery) -> list[Application]:
    items = apps
    if q.section == "favorites":
        items = [a for a in items if a.favorite]
    elif q.section == "recent":
        items = [a for a in items if a.last_played]
    elif q.section == "most_played":
        items = [a for a in items if a.launch_count > 0]
    elif q.section == "category":
        items = [a for a in items if a.category_id == q.category_id]
    if q.text.strip():
        items = [a for a in items if matches_text(a, q.text)]

    if q.section == "recent":
        return sorted(items, key=lambda a: a.last_played or "", reverse=True)
    if q.section == "most_played":
        return sorted(items, key=lambda a: (a.launch_count, a.last_played or ""), reverse=True)

    key = q.sort_key
    name_key = lambda a: (a.name.casefold(), a.id or 0)       # noqa: E731
    if key == "name":
        result = sorted(items, key=name_key)
    elif key == "added":
        result = sorted(items, key=lambda a: (a.created_at, a.id or 0), reverse=True)
    elif key == "played":
        played = sorted((a for a in items if a.last_played), key=lambda a: a.last_played, reverse=True)
        result = played + sorted((a for a in items if not a.last_played), key=name_key)
    elif key == "count":
        result = sorted(items, key=lambda a: (-a.launch_count, a.name.casefold()))
    elif key == "category":
        result = sorted(items, key=lambda a: (a.category_name == "", a.category_name.casefold(),
                                              a.name.casefold()))
    else:   # custom
        result = sorted(items, key=lambda a: (a.sort_order, a.id or 0))
    return list(reversed(result)) if q.reverse else result
