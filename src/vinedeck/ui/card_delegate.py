"""Paints library items in the four view modes (grid, compact, list, large)."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetrics, QLinearGradient, QPainter,
                           QPainterPath, QPen, QTextLayout)
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from ..core.process_manager import LaunchState
from ..utils.config import Settings
from . import icons
from .artwork import Artwork
from .formatting import format_last_played
from .library_model import AppRole, StateRole
from .theme import ThemeManager

LIST_ROW_H = 60
LARGE_H = 170
STAR = "#f5c542"


def list_columns(width: int) -> tuple[int, int, int]:
    """x offsets (name, category, last played) inside a list row of *width*."""
    name_x = 12 + 40 + 14
    usable = max(width - name_x - 150, 240)
    return name_x, name_x + int(usable * 0.50), name_x + int(usable * 0.78)


def wrapped_lines(text: str, font: QFont, width: int, max_lines: int) -> list[str]:
    fm = QFontMetrics(font)
    layout = QTextLayout(text, font)
    layout.beginLayout()
    lines: list[str] = []
    while True:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(width)
        start, length = line.textStart(), line.textLength()
        lines.append(text[start:start + length].strip())
        if len(lines) == max_lines:
            rest = text[start:]
            if len(rest.strip()) > length:
                lines[-1] = fm.elidedText(rest.replace("\n", " "), Qt.ElideRight, width)
            break
    layout.endLayout()
    return lines


class CardDelegate(QStyledItemDelegate):
    def __init__(self, settings: Settings, theme: ThemeManager, artwork: Artwork, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.theme = theme
        self.artwork = artwork
        self.mode = "grid"
        self.gap_h = 20
        self.gap_v = 20
        self.cell = QSize(220, 320)
        self.hover_row = -1
        self.hover_button: str | None = None

    # -- geometry ----------------------------------------------------------------
    def sizeHint(self, option, index):
        return self.cell

    def radius(self) -> int:
        return 0 if self.settings["card_style"] == "square" else self.settings["corner_radius"]

    def card_rect(self, cell: QRect, hovered: bool = False) -> QRect:
        gh, gv = self.gap_h, self.gap_v
        r = cell.adjusted(gh // 2, gv // 2, -(gh - gh // 2), -(gv - gv // 2))
        if hovered and self.settings["animations"] and self.mode in ("grid", "compact", "large"):
            r.translate(0, -3)
        return r

    def info_height(self) -> int:
        s, compact = self.settings, self.mode == "compact"
        h = 0
        if s["show_title"]:
            h += 20 if compact else 24
        if s["show_category"]:
            h += 16 if compact else 18
        return h + (10 if compact else 14) if h else 0

    def button_rects(self, card: QRect) -> dict[str, QRect]:
        s, out = self.settings, {}
        if self.mode in ("grid", "compact"):
            small = 30 if self.mode == "grid" else 26
            big = 48 if self.mode == "grid" else 38
            cover_h = card.height() - self.info_height()
            if s["show_launch"]:
                out["launch"] = QRect(card.center().x() - big // 2, card.y() + cover_h // 2 - big // 2, big, big)
            if s["show_favorite"]:
                out["favorite"] = QRect(card.right() - small - 7, card.y() + 8, small, small)
            out["more"] = QRect(card.x() + 8, card.y() + 8, small, small)
        else:
            size, gap = (34, 6) if self.mode == "list" else (40, 8)
            y = card.center().y() - size // 2 if self.mode == "list" else card.bottom() - size - 14
            x = card.right() - (14 if self.mode == "list" else 16) - size
            order = ["more", "favorite", "launch"]
            if not s["show_favorite"]:
                order.remove("favorite")
            if not s["show_launch"]:
                order.remove("launch")
            for name in order:
                out[name] = QRect(x, y, size, size)
                x -= size + gap
        return out

    def visible_buttons(self, rects: dict[str, QRect], hovered: bool, app) -> dict[str, QRect]:
        if hovered:
            return rects
        if app is not None and app.favorite and "favorite" in rects:
            return {"favorite": rects["favorite"]}
        return {}

    def button_at(self, cell: QRect, hovered: bool, app, pos) -> str | None:
        rects = self.visible_buttons(self.button_rects(self.card_rect(cell, hovered)), hovered, app)
        for name, r in rects.items():
            if r.contains(pos):
                return name
        return None

    # -- painting -----------------------------------------------------------------
    def paint(self, p: QPainter, option, index):
        app = index.data(AppRole)
        if app is None:
            return
        state = index.data(StateRole)
        hovered = index.row() == self.hover_row
        selected = bool(option.state & QStyle.State_Selected)
        focused = bool(option.state & QStyle.State_HasFocus)
        card = self.card_rect(option.rect, hovered)
        p.save()
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
        pal = self.theme.palette
        radius = self.radius()
        path = QPainterPath()
        path.addRoundedRect(QRectF(card), radius, radius)
        p.fillPath(path, pal.q("surface"))

        if self.mode in ("grid", "compact"):
            self._paint_tile(p, card, path, app, state, hovered)
        elif self.mode == "list":
            self._paint_row(p, card, app, state, hovered)
        else:
            self._paint_large(p, card, path, app, state, hovered)

        # border / focus ring (state is conveyed by thickness, not by colour alone)
        if selected or focused:
            pen = QPen(pal.q("accent"), 2.5)
        elif hovered:
            pen = QPen(pal.q("muted"), 1)
        else:
            pen = QPen(pal.q("border"), 1)
        p.setBrush(Qt.NoBrush)
        p.setPen(pen)
        p.drawRoundedRect(QRectF(card).adjusted(.5, .5, -.5, -.5), radius, radius)

        rects = self.visible_buttons(self.button_rects(card), hovered, app)
        over_cover = self.mode in ("grid", "compact", "large")
        for name, r in rects.items():
            self._paint_button(p, name, r, app, over_cover, hovered and name == self.hover_button)
        p.restore()

    # cover / placeholder -----------------------------------------------------------
    def _paint_cover(self, p: QPainter, rect: QRect, app):
        pm = self.artwork.cover(app)
        if pm is not None:
            scale = max(rect.width() / pm.width(), rect.height() / pm.height())
            sw, sh = rect.width() / scale, rect.height() / scale
            p.drawPixmap(QRectF(rect), pm, QRectF((pm.width() - sw) / 2, (pm.height() - sh) / 2, sw, sh))
            return
        hue = self.artwork.placeholder_hue(app)
        dark = self.theme.palette.dark
        g = QLinearGradient(QPointF(rect.topLeft()), QPointF(rect.bottomRight()))
        g.setColorAt(0, QColor.fromHsl(hue, 120, 140 if not dark else 86))
        g.setColorAt(1, QColor.fromHsl((hue + 40) % 360, 120, 96 if not dark else 48))
        p.fillRect(rect, QBrush(g))
        icon = self.artwork.icon(app)
        side = int(min(rect.width(), rect.height()) * 0.42)
        if icon is not None and side > 12:
            p.drawPixmap(QRect(rect.center().x() - side // 2, rect.center().y() - side // 2, side, side),
                         icon.scaled(side * 2, side * 2, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            f = QFont(p.font())
            f.setPixelSize(max(int(min(rect.width(), rect.height()) * 0.38), 10))
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor(255, 255, 255, 190))
            p.drawText(rect, Qt.AlignCenter, (app.name.strip()[:1] or "?").upper())

    # tiles ------------------------------------------------------------------------------
    def _paint_tile(self, p, card, path, app, state, hovered):
        pal, compact = self.theme.palette, self.mode == "compact"
        info_h = self.info_height()
        cover = QRect(card.x(), card.y(), card.width(), card.height() - info_h)
        p.save()
        p.setClipPath(path)
        self._paint_cover(p, cover, app)
        if hovered:
            p.fillRect(cover, QColor(0, 0, 0, 105))
        p.restore()
        if info_h:
            f = QFont(p.font())
            f.setPointSizeF(p.font().pointSizeF() - (1.5 if compact else 0))
            tx = card.x() + 12
            tw = card.width() - 24
            y = cover.bottom() + (6 if compact else 8)
            if self.settings["show_title"]:
                f.setBold(True)
                p.setFont(f)
                p.setPen(pal.q("text"))
                fm = QFontMetrics(f)
                p.drawText(QRect(tx, y, tw, fm.height()), Qt.AlignVCenter,
                           fm.elidedText(app.name, Qt.ElideRight, tw))
                y += fm.height() + 1
            if self.settings["show_category"]:
                f.setBold(False)
                f.setPointSizeF(f.pointSizeF() - 1)
                p.setFont(f)
                p.setPen(pal.q("muted"))
                fm = QFontMetrics(f)
                p.drawText(QRect(tx, y, tw, fm.height()), Qt.AlignVCenter,
                           fm.elidedText(app.category_name or "Uncategorised", Qt.ElideRight, tw))
        if state:
            self._paint_state(p, state, QPointF(card.x() + 8, cover.bottom() - 8), anchor_bottom=True)

    # list rows ----------------------------------------------------------------------------
    def _paint_row(self, p, card, app, state, hovered):
        pal = self.theme.palette
        name_x, cat_x, played_x = list_columns(card.width())
        icon_rect = QRect(card.x() + 12, card.center().y() - 20, 40, 40)
        p.save()
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(icon_rect), 8, 8)
        p.setClipPath(clip)
        self._paint_cover(p, icon_rect, _IconFirst(app, self.artwork))
        p.restore()
        f = QFont(p.font())
        fm = QFontMetrics(f)
        right_limit = card.x() + cat_x - 12
        p.setFont(self._bold(f))
        p.setPen(pal.q("text"))
        name_w = right_limit - (card.x() + name_x) - (100 if state else 0)
        name_rect = QRect(card.x() + name_x, card.y(), name_w, card.height())
        p.drawText(name_rect, Qt.AlignVCenter, QFontMetrics(self._bold(f)).elidedText(app.name, Qt.ElideRight, name_w))
        p.setFont(f)
        p.setPen(pal.q("muted"))
        if self.settings["show_category"]:
            w = played_x - cat_x - 10
            p.drawText(QRect(card.x() + cat_x, card.y(), w, card.height()), Qt.AlignVCenter,
                       fm.elidedText(app.category_name or "Uncategorised", Qt.ElideRight, w))
        p.drawText(QRect(card.x() + played_x, card.y(), 130, card.height()), Qt.AlignVCenter,
                   format_last_played(app.last_played))
        if state:
            self._paint_state(p, state, QPointF(card.x() + cat_x - 12 - 90, card.center().y() - 11))

    # large cards ------------------------------------------------------------------------------
    def _paint_large(self, p, card, path, app, state, hovered):
        pal = self.theme.palette
        cover = QRect(card.x(), card.y(), int(card.height() * 0.68), card.height())
        p.save()
        p.setClipPath(path)
        self._paint_cover(p, cover, app)
        p.restore()
        x = cover.right() + 18
        w = card.right() - x - 16
        f = QFont(p.font())
        title_f = QFont(f)
        title_f.setPointSizeF(f.pointSizeF() + 3)
        title_f.setBold(True)
        p.setFont(title_f)
        p.setPen(pal.q("text"))
        fm = QFontMetrics(title_f)
        y = card.y() + 14
        p.drawText(QRect(x, y, w, fm.height()), Qt.AlignVCenter, fm.elidedText(app.name, Qt.ElideRight, w))
        y += fm.height() + 2
        small = QFont(f)
        small.setPointSizeF(f.pointSizeF() - 1)
        p.setFont(small)
        p.setPen(pal.q("muted"))
        fm = QFontMetrics(small)
        if self.settings["show_category"]:
            p.drawText(QRect(x, y, w, fm.height()), Qt.AlignVCenter, app.category_name or "Uncategorised")
            y += fm.height() + 6
        if self.settings["show_description"] and app.description.strip():
            p.setFont(f)
            p.setPen(pal.q("text"))
            line_h = QFontMetrics(f).lineSpacing()
            for line in wrapped_lines(app.description, f, w, 3):
                p.drawText(QRect(x, y, w, line_h), Qt.AlignVCenter, line)
                y += line_h
        p.setFont(small)
        p.setPen(pal.q("muted"))
        plays = f"{app.launch_count} play{'s' if app.launch_count != 1 else ''}"
        played = f"{plays} · {format_last_played(app.last_played)}"
        p.drawText(QRect(x, card.bottom() - 32, max(w - 150, 60), fm.height() + 4), Qt.AlignVCenter,
                   fm.elidedText(played, Qt.ElideRight, max(w - 150, 60)))
        if state:
            self._paint_state(p, state, QPointF(x, card.bottom() - 62))

    # pieces ------------------------------------------------------------------------------------------------
    @staticmethod
    def _bold(f: QFont) -> QFont:
        b = QFont(f)
        b.setBold(True)
        return b

    def _paint_state(self, p: QPainter, state: str, pos: QPointF, anchor_bottom: bool = False):
        pal = self.theme.palette
        colors = {LaunchState.RUNNING.value: (pal.accent, pal.accent_text),
                  LaunchState.FAILED.value: (pal.danger, "#ffffff"),
                  LaunchState.LAUNCHING.value: ("#2a2d36" if pal.dark else "#dfe2ea", pal.text),
                  LaunchState.CLOSED.value: ("#2a2d36" if pal.dark else "#dfe2ea", pal.muted)}
        bg, fg = colors.get(state, (pal.surface2, pal.text))
        f = QFont(p.font())
        f.setPointSizeF(max(f.pointSizeF(), 9) - 1)
        f.setBold(True)
        p.setFont(f)
        fm = QFontMetrics(f)
        mark = {"Running": "● ", "Failed": "✕ ", "Closed": "○ "}.get(state, "◌ ")
        text = mark + state
        w, h = fm.horizontalAdvance(text) + 16, fm.height() + 6
        r = QRectF(pos.x(), pos.y() - (h if anchor_bottom else 0), w, h)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(bg))
        p.drawRoundedRect(r, h / 2, h / 2)
        p.setPen(QColor(fg))
        p.drawText(r, Qt.AlignCenter, text)

    def _paint_button(self, p: QPainter, name: str, r: QRect, app, over_cover: bool, hot: bool):
        pal = self.theme.palette
        p.setPen(Qt.NoPen)
        if name == "launch":
            bg = QColor(pal.accent)
            if hot:
                bg = bg.lighter(118)
            fg = pal.accent_text
        else:
            if over_cover:
                bg = QColor(0, 0, 0, 190 if hot else 140)
                fg = "#ffffff"
            else:
                bg = QColor(pal.border if hot else pal.surface2)
                fg = pal.text
        p.setBrush(bg)
        p.drawEllipse(r)
        icon_name = {"launch": "play", "more": "more",
                     "favorite": "star-filled" if app.favorite else "star"}[name]
        if name == "favorite" and app.favorite:
            fg = STAR
        side = int(r.width() * (0.5 if name == "launch" else 0.56))
        pm = icons.pixmap(icon_name, fg, side)
        p.drawPixmap(r.center().x() - side // 2 + (1 if name == "launch" else 0), r.center().y() - side // 2, pm)


class _IconFirst:
    """Adapter so list rows prefer the app's icon, falling back to its cover."""

    def __init__(self, app, artwork: Artwork):
        self._app = app
        self.name = app.name
        self.cover_path = "" if artwork.icon(app) is not None else app.cover_path
        self.icon_path = app.icon_path
        self.id = app.id
