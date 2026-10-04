"""Library export / import.

* without artwork: a single ``.json`` file
* with artwork: a ``.zip`` containing ``library.json`` and an ``artwork/`` folder

Application files themselves are never copied.
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

from ..database.database import Database
from ..database.models import Application
from ..utils.logging import get_logger
from ..utils.paths import AppPaths

log = get_logger("export")

FORMAT_VERSION = 1
_EXPORT_FIELDS = (
    "name", "executable_path", "wine_prefix", "working_directory", "launch_arguments",
    "env_vars", "description", "favorite", "sort_order", "launch_count", "last_played",
    "created_at", "developer", "publisher", "version", "genre", "release_year", "website",
)


class ExportError(Exception):
    pass


@dataclass
class ImportResult:
    added: int = 0
    skipped: int = 0
    categories_added: int = 0


def export_library(db: Database, paths: AppPaths, target: Path, include_artwork: bool) -> int:
    apps = db.list_applications()
    entries = []
    artwork: list[tuple[Path, str]] = []
    for a in apps:
        entry = {f: getattr(a, f) for f in _EXPORT_FIELDS}
        entry["category"] = a.category_name
        for kind, name, folder in (("cover", a.cover_path, paths.covers_dir),
                                   ("icon", a.icon_path, paths.icons_dir)):
            src = folder / name if name else None
            if include_artwork and src and src.is_file():
                arc = f"artwork/{kind}s/{src.name}"
                artwork.append((src, arc))
                entry[f"{kind}_file"] = arc
        entries.append(entry)
    doc = {"format": "library-export", "version": FORMAT_VERSION,
           "categories": [c.name for c in db.list_categories()], "applications": entries}
    text = json.dumps(doc, indent=2, ensure_ascii=False)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if include_artwork:
            with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("library.json", text)
                for src, arc in artwork:
                    zf.write(src, arc)
        else:
            target.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise ExportError(f"Could not write the export file: {exc.strerror or exc}") from exc
    return len(apps)


def import_library(db: Database, paths: AppPaths, source: Path, images=None) -> ImportResult:
    """Merge an export into the library. Existing entries are never overwritten."""
    zf = None
    try:
        if zipfile.is_zipfile(source):
            zf = zipfile.ZipFile(source)
            doc = json.loads(zf.read("library.json").decode("utf-8"))
        else:
            doc = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        raise ExportError("That file is not a valid library export.") from exc
    if not isinstance(doc, dict) or doc.get("format") != "library-export" \
            or not isinstance(doc.get("applications"), list):
        raise ExportError("That file is not a valid library export.")
    if int(doc.get("version", 0)) > FORMAT_VERSION:
        raise ExportError("That export was created by a newer version of the application.")

    result = ImportResult()
    try:
        for name in doc.get("categories", []):
            if isinstance(name, str) and name.strip() and not db.get_category_by_name(name):
                db.add_category(name)
                result.categories_added += 1
        existing = {(a.name.casefold(), a.executable_path) for a in db.list_applications()}
        for entry in doc["applications"]:
            if not isinstance(entry, dict) or not entry.get("name") or not entry.get("executable_path"):
                result.skipped += 1
                continue
            key = (str(entry["name"]).casefold(), str(entry["executable_path"]))
            if key in existing:
                result.skipped += 1
                continue
            app = Application()
            for f in _EXPORT_FIELDS:
                if f in entry and f not in ("sort_order",):
                    value = entry[f]
                    if f == "env_vars":
                        value = {str(k): str(v) for k, v in value.items()} if isinstance(value, dict) else {}
                    elif f == "favorite":
                        value = bool(value)
                    elif f == "launch_count":
                        value = int(value) if isinstance(value, int) else 0
                    elif f in ("last_played", "created_at"):
                        value = value if isinstance(value, str) else ("" if f == "created_at" else None)
                    else:
                        value = str(value)
                    setattr(app, f, value)
            cat = entry.get("category")
            if isinstance(cat, str) and cat.strip():
                found = db.get_category_by_name(cat)
                app.category_id = found.id if found else db.add_category(cat).id
            if zf is not None and images is not None:
                for kind, importer in (("cover", images.import_cover), ("icon", images.import_icon)):
                    arc = entry.get(f"{kind}_file")
                    if isinstance(arc, str) and arc.startswith("artwork/") and ".." not in arc:
                        try:
                            tmp = paths.cache_dir / f"import_{Path(arc).name}"
                            tmp.write_bytes(zf.read(arc))
                            setattr(app, f"{kind}_path", importer(tmp))
                            tmp.unlink(missing_ok=True)
                        except Exception as exc:    # artwork is optional
                            log.warning("Skipping artwork %s: %s", arc, exc)
            db.add_application(app)
            existing.add(key)
            result.added += 1
    finally:
        if zf is not None:
            zf.close()
    return result
