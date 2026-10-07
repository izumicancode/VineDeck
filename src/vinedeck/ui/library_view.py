"""The scrollable library: responsive grid, list and large-card layouts."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QAbstractItemView, QListView, QToolTip

from ..utils.config import Settings
from .artwork import Artwork
from .card_delegate import LARGE_H, LIST_ROW_H, CardDelegate
from .formatting import short_path
from .library_model import AppRole, IdRole, LibraryModel
from .theme import ThemeManager

MIN_CARD_W = 100
_TOOLTIPS = {"launch": "Launch", "more": "More actions"}


class LibraryView(QListView):
    launch_requested = Signal(int)
    favorite_toggled = Signal(int)
    menu_requested = Signal(int, QPoint)
    open_requested = Signal(int)
    remove_requested = Signal(int)

    def __init__(self, model: LibraryModel, settings: Settings, theme: ThemeManager,
                 artwork: Artwork, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._model = model
        self.setModel(model)
        self.delegate = CardDelegate(settings, theme, artwork, self)
        self.setItemDelegate(self.delegate)
        self.setViewMode(QListView.ListMode)
        self.setFlow(QListView.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListView.Adjust)
        self.setUniformItemSizes(True)
        self.setMovement(QListView.Static)
        self.setSpacing(0)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(32)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setMouseTracking(True)
        self.setFrameShape(QListView.NoFrame)
        self.viewport().setAutoFillBackground(False)
        self.setViewportMargins(0, 0, 0, 0)
        self.setAccessibleName("Application library")
        self.setAccessibleDescription("Use the arrow keys to move, Enter to launch, F to toggle favorite, Delete to remove.")
        self._pressed: tuple[int, str] | None = None
        self.setDefaultDropAction(Qt.CopyAction)
        self.set_reorder_enabled(False)
        model.modelReset.connect(self._on_reset)
        theme.changed.connect(self.viewport().update)

    # -- layout --------------------------------------------------------------------
    def apply_settings(self) -> None:
        self._relayout()
        self.viewport().update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._relayout()

    def _relayout(self) -> None:
        s, d = self.settings, self.delegate
        mode = s["view_mode"]
        margin_l, margin_r = 14, self.verticalScrollBar().sizeHint().width() + 4
        avail = max(self.width() - margin_l - margin_r, MIN_CARD_W)
        self.setViewportMargins(0, 0, 0, 0)
        self.setContentsMargins(margin_l, 4, 0, 8)
        d.mode = mode
        if mode == "list":
            d.gap_h, d.gap_v = 0, 8
            d.cell = QSize(avail, LIST_ROW_H + d.gap_v)
        else:
            if mode == "compact":
                base_w = max(int(s["card_width"] * 0.72), MIN_CARD_W)
                base_h = max(int(s["card_height"] * 0.72), 140)
                gh, gv = min(s["gap_h"], 14), min(s["gap_v"], 14)
            elif mode == "large":
                base_w, base_h, gh, gv = 440, LARGE_H, s["gap_h"], s["gap_v"]
            else:
                base_w, base_h, gh, gv = s["card_width"], s["card_height"], s["gap_h"], s["gap_v"]
            fixed = s["grid_columns"]
            if fixed > 0 and mode != "large":
                cols = max(1, min(fixed, avail // (MIN_CARD_W + gh)))
            else:
                cols = max(1, avail // (base_w + gh))
            card_w = max(avail // cols - gh, MIN_CARD_W)
            card_h = base_h if mode == "large" else round(base_h * card_w / base_w)
            d.gap_h, d.gap_v = gh, gv
            d.cell = QSize(card_w + gh, card_h + gv)
        self.setGridSize(d.cell)
        self.scheduleDelayedItemsLayout()

    def columns(self) -> int:
        avail = max(self.viewport().width(), 1)
        return max(1, avail // max(self.delegate.cell.width(), 1))

    def _on_reset(self) -> None:
        self.delegate.hover_row = -1
        self.delegate.hover_button = None

    def set_reorder_enabled(self, enabled: bool) -> None:
        self.setDragEnabled(enabled)
        self.setAcceptDrops(enabled)
        self.setDropIndicatorShown(enabled)
        self.setDragDropMode(QAbstractItemView.DragDrop if enabled else QAbstractItemView.NoDragDrop)

    # -- hover & buttons --------------------------------------------------------------------------
    def _button_under(self, pos: QPoint):
        idx = self.indexAt(pos)
        if not idx.isValid():
            return idx, None
        app = idx.data(AppRole)
        hovered = idx.row() == self.delegate.hover_row
        return idx, self.delegate.button_at(self.visualRect(idx), hovered, app, pos)

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        idx = self.indexAt(pos)
        row = idx.row() if idx.isValid() else -1
        d = self.delegate
        old_row, old_btn = d.hover_row, d.hover_button
        d.hover_row = row
        _, btn = self._button_under(pos) if row >= 0 else (None, None)
        d.hover_button = btn
        if (row, btn) != (old_row, old_btn):
            for r in {old_row, row}:
                if r >= 0:
                    self.viewport().update(self.visualRect(self._model.index(r)).adjusted(-6, -12, 6, 8))
        self.viewport().setCursor(Qt.PointingHandCursor if row >= 0 else Qt.ArrowCursor)
        super().mouseMoveEvent(e)

    def leaveEvent(self, e):
        d = self.delegate
        if d.hover_row >= 0:
            r = d.hover_row
            d.hover_row, d.hover_button = -1, None
            self.viewport().update(self.visualRect(self._model.index(r)).adjusted(-6, -12, 6, 8))
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            idx, btn = self._button_under(e.position().toPoint())
            if btn:
                self._pressed = (idx.data(IdRole), btn)
                self.setCurrentIndex(idx)
                return
        self._pressed = None
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if self._pressed and e.button() == Qt.LeftButton:
            app_id, btn = self._pressed
            self._pressed = None
            idx, now = self._button_under(e.position().toPoint())
            if idx.isValid() and idx.data(IdRole) == app_id and now == btn:
                if btn == "launch":
                    self.launch_requested.emit(app_id)
                elif btn == "favorite":
                    self.favorite_toggled.emit(app_id)
                elif btn == "more":
                    self.menu_requested.emit(app_id, e.globalPosition().toPoint())
            return
        idx = self.indexAt(e.position().toPoint())
        super().mouseReleaseEvent(e)
        if e.button() == Qt.LeftButton and idx.isValid():
            self.open_requested.emit(idx.data(IdRole))

    def contextMenuEvent(self, e):
        idx = self.indexAt(e.pos())
        if idx.isValid():
            self.setCurrentIndex(idx)
            self.menu_requested.emit(idx.data(IdRole), e.globalPos())

    def keyPressEvent(self, e):
        idx = self.currentIndex()
        if idx.isValid() and e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.launch_requested.emit(idx.data(IdRole))
            return
        if idx.isValid() and e.key() == Qt.Key_Delete:
            self.remove_requested.emit(idx.data(IdRole))
            return
        if idx.isValid() and e.key() == Qt.Key_F:
            self.favorite_toggled.emit(idx.data(IdRole))
            return
        super().keyPressEvent(e)

    def viewportEvent(self, e):
        if e.type() == QEvent.ToolTip:
            pos = e.pos()
            idx, btn = self._button_under(pos)
            if idx.isValid():
                app = idx.data(AppRole)
                if btn == "favorite":
                    text = "Remove from favorites" if app.favorite else "Add to favorites"
                elif btn:
                    text = _TOOLTIPS[btn] + f" {app.name}" if btn == "launch" else _TOOLTIPS[btn]
                else:
                    text = f"{app.name}\n{short_path(app.executable_path, 70)}"
                QToolTip.showText(e.globalPos(), text, self)
            else:
                QToolTip.hideText()
            return True
        return super().viewportEvent(e)

    def select_app(self, app_id: int) -> None:
        row = self._model.row_of(app_id)
        if row >= 0:
            self.setCurrentIndex(self._model.index(row))
