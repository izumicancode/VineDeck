"""Lazy, cached access to cover and icon pixmaps for painting."""

from __future__ import annotations

import zlib

from PySide6.QtGui import QPixmap, QPixmapCache

from ..database.models import Application
from ..services.image_service import CARD_THUMB_SIDE, ImageService

QPixmapCache.setCacheLimit(96 * 1024)       # KB; thumbnails are decoded lazily as cards scroll into view


class Artwork:
    def __init__(self, images: ImageService):
        self.images = images

    def cover(self, app: Application, side: int = CARD_THUMB_SIDE) -> QPixmap | None:
        if not app.cover_path:
            return None
        key = f"cover:{app.cover_path}:{side}"
        pm = QPixmapCache.find(key)
        if pm is None or pm.isNull():
            thumb = self.images.thumbnail(app.cover_path, side)
            if thumb is None:
                return None
            pm = QPixmap(str(thumb))
            if pm.isNull():
                return None
            QPixmapCache.insert(key, pm)
        return pm

    def icon(self, app: Application) -> QPixmap | None:
        if not app.icon_path:
            return None
        key = f"icon:{app.icon_path}"
        pm = QPixmapCache.find(key)
        if pm is None or pm.isNull():
            f = self.images.icon_file(app.icon_path)
            if f is None:
                return None
            pm = QPixmap(str(f))
            if pm.isNull():
                return None
            QPixmapCache.insert(key, pm)
        return pm

    @staticmethod
    def placeholder_hue(app: Application) -> int:
        return zlib.crc32(app.name.encode("utf-8")) % 360
