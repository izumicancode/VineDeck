"""Full-page application details."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (QBoxLayout, QFrame, QGridLayout, QHBoxLayout, QScrollArea, QSizePolicy,
                               QVBoxLayout, QWidget)

from ..core.process_manager import LaunchState
from ..core.scanner import default_prefix
from ..database.models import Application
from .formatting import format_datetime, format_last_played, short_path
from .theme import ThemeManager
from .widgets import PreviewBox, label, make_button

COVER_SIZE = QSize(230, 345)


class Hero(QWidget):
    """Backdrop: the cover, heavily down-scaled so the upscale reads as a blur, under a scrim."""

    def __init__(self, theme: ThemeManager, blur=lambda: True, parent=None):
        super().__init__(parent)
        self.theme, self._blur = theme, blur
        self._small: QPixmap | None = None

    def set_cover(self, pm: QPixmap | None) -> None:
        self._small = (pm.scaledToWidth(36, Qt.SmoothTransformation) if pm is not None and not pm.isNull() else None)
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        pal = self.theme.palette
        r = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(r, 0 if self.theme.square else 16, 0 if self.theme.square else 16)
        p.setClipPath(path)
        p.fillRect(r, pal.q("surface"))
        if self._small is not None and self._blur():
            s = max(r.width() / self._small.width(), r.height() / self._small.height())
            p.drawPixmap(r, self._small, QRectF(0, 0, r.width() / s, r.height() / s))
            p.fillRect(r, QColor(18, 19, 23, 190) if pal.dark else QColor(255, 255, 255, 200))
        g = QLinearGradient(0, r.height() * 0.4, 0, r.height())
        g.setColorAt(0, QColor(0, 0, 0, 0))
        g.setColorAt(1, QColor(pal.surface))
        p.fillRect(r, g)


class DetailsPage(QWidget):
    back_requested = Signal()
    play_requested = Signal(int)
    edit_requested = Signal(int)
    favorite_toggled = Signal(int)
    menu_requested = Signal(int, object)

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.theme = ctx.theme
        self._app: Application | None = None
        self._state: str | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)
        page = QWidget()
        scroll.setWidget(page)
        col = QVBoxLayout(page)
        col.setContentsMargins(24, 16, 24, 28)
        col.setSpacing(18)

        self.back = make_button("Library", "ghost", tooltip="Back to library (Esc)")
        self.back.clicked.connect(self.back_requested)
        col.addWidget(self.back, 0, Qt.AlignLeft)

        self.hero = Hero(self.theme, lambda: ctx.settings["blur"])
        hl = QHBoxLayout(self.hero)
        hl.setContentsMargins(30, 30, 30, 30)
        hl.setSpacing(30)
        self.cover = PreviewBox(COVER_SIZE, "No cover")
        hl.addWidget(self.cover, 0, Qt.AlignTop)
        info = QVBoxLayout()
        info.setSpacing(8)
        self.title = label(name="Title", wrap=True)
        self.category = label(name="Pill")
        self.status = label(name="Pill")
        pills = QHBoxLayout()
        pills.setSpacing(8)
        pills.addWidget(self.category)
        pills.addWidget(self.status)
        pills.addStretch(1)
        self.subtitle = label(muted=True, wrap=True)
        info.addStretch(1)
        info.addWidget(self.title)
        info.addLayout(pills)
        info.addWidget(self.subtitle)
        info.addSpacing(10)
        self.fav = make_button("Favorite", "ghost")
        self.fav.setCheckable(True)
        self.fav.clicked.connect(lambda: self._app and self.favorite_toggled.emit(self._app.id))
        info.addWidget(self.fav, 0, Qt.AlignLeft)
        btns = QHBoxLayout()
        self.action_layout = btns
        btns.setSpacing(10)
        self.play = make_button("PLAY", "primary", big=True)
        self.play.clicked.connect(lambda: self._app and self.play_requested.emit(self._app.id))
        self.edit = make_button("EDIT", big=True)
        self.edit.clicked.connect(lambda: self._app and self.edit_requested.emit(self._app.id))
        self.more = make_button("More", "ghost", big=True)
        self.more.clicked.connect(lambda: self._app and self.menu_requested.emit(self._app.id, self.more.mapToGlobal(self.more.rect().bottomLeft())))
        for b in (self.play, self.edit, self.more):
            btns.addWidget(b)
        btns.addStretch(1)
        info.addLayout(btns)
        info.addStretch(1)
        hl.addLayout(info, 1)
        col.addWidget(self.hero)

        self.desc_panel, self.desc_body = self._panel("Description")
        self.desc = label(wrap=True)
        self.desc.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.desc_body.addWidget(self.desc, 0, 0)
        self.desc_body.setColumnStretch(0, 1)
        col.addWidget(self.desc_panel)

        self.cfg_panel, self.cfg = self._panel("Configuration")
        col.addWidget(self.cfg_panel)
        self.meta_panel, self.meta = self._panel("Details")
        col.addWidget(self.meta_panel)
        self.act_panel, self.act = self._panel("Activity")
        col.addWidget(self.act_panel)
        col.addStretch(1)
        self.retheme()
        self.theme.changed.connect(self.retheme)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        compact = self.width() < 620
        self.cover.setFixedSize(QSize(150, 225) if compact else COVER_SIZE)
        self.hero.layout().setContentsMargins(*((18, 18, 18, 18) if compact else (30, 30, 30, 30)))
        self.hero.layout().setSpacing(18 if compact else 30)
        self.action_layout.setDirection(QBoxLayout.TopToBottom if compact else QBoxLayout.LeftToRight)
        self.action_layout.setSpacing(6 if compact else 10)

    def _panel(self, title: str):
        f = QFrame()
        f.setObjectName("Panel")
        lay = QVBoxLayout(f)
        lay.setContentsMargins(22, 18, 22, 20)
        lay.setSpacing(12)
        lay.addWidget(label(title, "H2"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)
        return f, grid

    @staticmethod
    def _fill(grid: QGridLayout, rows: list[tuple[str, str]]) -> None:
        while grid.count():
            w = grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        for i, (k, v) in enumerate(rows):
            grid.addWidget(label(k, muted=True), i, 0, Qt.AlignTop)
            val = label(v, wrap=True)
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            val.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            grid.addWidget(val, i, 1)

    def retheme(self) -> None:
        p = self.theme.palette
        self.back.setIcon(self.theme.icon("chevron-left", p.text, 18))
        self.play.setIcon(self.theme.icon("play", p.accent_text, 20))
        self.edit.setIcon(self.theme.icon("edit", p.text, 18))
        self.more.setIcon(self.theme.icon("more", p.text, 18))
        self._icon_fav()
        self.hero.update()

    def _icon_fav(self) -> None:
        on = bool(self._app and self._app.favorite)
        self.fav.setChecked(on)
        self.fav.setText("Favorited" if on else "Add to Favorites")
        self.fav.setIcon(self.theme.icon("star-filled" if on else "star", "#f5c542" if on else self.theme.palette.text, 18))
        self.fav.setAccessibleName("Favorite: on" if on else "Favorite: off")

    def current_id(self) -> int | None:
        return self._app.id if self._app else None

    def show_app(self, app: Application, state: str | None) -> None:
        self._app = app
        art = self.ctx.artwork
        pm = art.cover(app, 1200) or None
        self.cover.set_pixmap(pm if pm is not None else art.icon(app))
        self.hero.set_cover(pm)
        self.title.setText(app.name)
        self.category.setText(app.category_name or "Uncategorised")
        bits = [x for x in (app.developer, app.release_year) if x]
        self.subtitle.setText("  ·  ".join(bits))
        self.subtitle.setVisible(bool(bits))
        self.desc.setText(app.description or "No description yet. Use Edit to add one.")
        self.desc.setProperty("muted", not app.description)
        self.desc.style().unpolish(self.desc)
        self.desc.style().polish(self.desc)
        prefix = app.wine_prefix or f"Default ({short_path(str(default_prefix()))})"
        self._fill(self.cfg, [
            ("Executable", app.executable_path),
            ("Wine Prefix", app.wine_prefix or prefix),
            ("Working Directory", app.working_directory or "Same folder as the executable"),
            ("Launch Arguments", app.launch_arguments or "None"),
            ("Environment", ", ".join(f"{k}" for k in app.env_vars) or "None"),
        ])
        rows = [(k.replace("_", " ").title(), getattr(app, k)) for k in
                ("developer", "publisher", "version", "genre", "release_year", "website") if getattr(app, k)]
        self.meta_panel.setVisible(bool(rows))
        self._fill(self.meta, rows)
        self._fill(self.act, [
            ("Times Launched", str(app.launch_count)),
            ("Last Played", format_last_played(app.last_played)),
            ("Added", format_datetime(app.created_at)),
        ])
        self._icon_fav()
        self.set_state(state)

    def set_state(self, state: str | None) -> None:
        self._state = state
        self.status.setVisible(bool(state))
        if state:
            self.status.setText({"Running": "● ", "Failed": "✕ ", "Closed": "○ "}.get(state, "◌ ") + state)
        busy = state in (LaunchState.LAUNCHING.value, LaunchState.RUNNING.value)
        self.play.setEnabled(not busy)
        self.play.setText(state.upper() if busy else "PLAY")
