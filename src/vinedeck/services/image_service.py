"""Imports, validates, resizes and caches artwork with Pillow.

Managed artwork is stored in the application's own data directory and referenced from
the database by *bare file name*, so the data directory can move without breaking
the library. Thumbnails live in the cache directory and can be deleted at any time.
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from ..utils.logging import get_logger
from ..utils.paths import AppPaths

log = get_logger("images")

ALLOWED_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
COVER_MAX_SIDE = 2000          # stored size cap (keeps files small)
CARD_THUMB_SIDE = 480          # thumbnails used by library cards
LARGE_THUMB_SIDE = 1200        # details page
ICON_SIZE = 256
MAX_SOURCE_BYTES = 60 * 1024 * 1024


class ImageError(Exception):
    """User-presentable image problem."""


class ImageService:
    def __init__(self, paths: AppPaths):
        self.paths = paths

    # -- loading / validation --------------------------------------------------
    @staticmethod
    def load(src: str | Path) -> Image.Image:
        p = Path(src).expanduser()
        if p.suffix.lower() not in ALLOWED_SUFFIXES:
            raise ImageError("Please choose a PNG, JPG or WEBP image.")
        try:
            if not p.is_file():
                raise ImageError("That image file does not exist.")
            if p.stat().st_size > MAX_SOURCE_BYTES:
                raise ImageError("That image is too large (limit 60 MB).")
            with Image.open(p) as probe:
                probe.verify()                       # detects truncated / corrupt data
            img = Image.open(p)
            img.load()
        except ImageError:
            raise
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError) as exc:
            raise ImageError("That file is not a valid image.") from exc
        return ImageOps.exif_transpose(img)

    # -- covers ----------------------------------------------------------------
    def import_cover(self, src: str | Path) -> str:
        """Validate, downscale and store a cover. Returns the managed file name."""
        img = self.load(src)
        img = img if img.mode in ("RGB", "RGBA") else img.convert("RGBA" if "A" in img.getbands() else "RGB")
        img.thumbnail((COVER_MAX_SIDE, COVER_MAX_SIDE), Image.LANCZOS)
        name = f"{uuid.uuid4().hex}.webp"
        self.paths.covers_dir.mkdir(parents=True, exist_ok=True)
        img.save(self.paths.covers_dir / name, "WEBP", quality=88, method=4)
        self.thumbnail(name, CARD_THUMB_SIDE)          # warm the cache
        return name

    def cover_file(self, name: str) -> Path | None:
        if not name:
            return None
        p = self.paths.covers_dir / Path(name).name
        return p if p.is_file() else None

    def thumbnail(self, cover_name: str, side: int = CARD_THUMB_SIDE) -> Path | None:
        """Path of a PNG thumbnail (aspect ratio preserved), generated on demand."""
        src = self.cover_file(cover_name)
        if src is None:
            return None
        thumb = self.paths.thumbs_dir / f"{src.stem}_{side}.png"
        if thumb.is_file() and thumb.stat().st_mtime >= src.stat().st_mtime:
            return thumb
        try:
            with Image.open(src) as img:
                img = img.convert("RGBA")
                img.thumbnail((side, side), Image.LANCZOS)
                self.paths.thumbs_dir.mkdir(parents=True, exist_ok=True)
                img.save(thumb, "PNG", optimize=False)
        except (OSError, UnidentifiedImageError) as exc:
            log.warning("Could not create thumbnail for %s: %s", cover_name, exc)
            return None
        return thumb

    # -- icons -----------------------------------------------------------------
    def import_icon(self, src: str | Path | Image.Image) -> str:
        img = src if isinstance(src, Image.Image) else self.load(src)
        img = img.convert("RGBA")
        img.thumbnail((ICON_SIZE, ICON_SIZE), Image.LANCZOS)
        canvas = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
        canvas.paste(img, ((ICON_SIZE - img.width) // 2, (ICON_SIZE - img.height) // 2))
        name = f"{uuid.uuid4().hex}.png"
        self.paths.icons_dir.mkdir(parents=True, exist_ok=True)
        canvas.save(self.paths.icons_dir / name, "PNG")
        return name

    def icon_file(self, name: str) -> Path | None:
        if not name:
            return None
        p = self.paths.icons_dir / Path(name).name
        return p if p.is_file() else None

    # -- background ------------------------------------------------------------
    def prepare_background(self, src: str | Path, blur: bool) -> Path | None:
        """Return a screen-sized (optionally blurred) copy of the background image."""
        from PIL import ImageFilter
        try:
            img = self.load(src).convert("RGB")
        except ImageError:
            return None
        img.thumbnail((1920, 1080), Image.LANCZOS)
        if blur:
            img = img.filter(ImageFilter.GaussianBlur(14))
        key = "bg_" + hashlib.sha1(f"{src}|{blur}|{Path(src).stat().st_mtime_ns}".encode()).hexdigest()[:16] + ".jpg"
        out = self.paths.theme_cache_dir / key
        self.paths.theme_cache_dir.mkdir(parents=True, exist_ok=True)
        if not out.exists():
            img.save(out, "JPEG", quality=85)
        return out

    # -- housekeeping ----------------------------------------------------------
    def delete_cover(self, name: str) -> None:
        if not name:
            return
        base = Path(name).name
        (self.paths.covers_dir / base).unlink(missing_ok=True)
        for t in self.paths.thumbs_dir.glob(f"{Path(base).stem}_*.png"):
            t.unlink(missing_ok=True)

    def delete_icon(self, name: str) -> None:
        if name:
            (self.paths.icons_dir / Path(name).name).unlink(missing_ok=True)

    def clear_thumbnail_cache(self) -> int:
        count = 0
        for f in list(self.paths.thumbs_dir.glob("*")) + list(self.paths.theme_cache_dir.glob("bg_*")):
            try:
                f.unlink()
                count += 1
            except OSError:
                pass
        return count
