"""Collapsible navigation sidebar."""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QMenu, QPushButton, QScrollArea, QVBoxLayout, QWidget

from ..database.models import Category
from .theme import ThemeManager
from .widgets import label, make_button

EXPANDED_W = 236
COLLAPSED_W = 68

_LIBRARY = (("all", "All Applications", "grid"), ("favorites", "Favorites", "star"),
            ("recent", "Recently Played", "clock"), ("most_played", "Most Played", "trending"))


class Sidebar(QFrame):
    section_selected = Signal(str, object)       # section key, category id or None
    add_clicked = Signal()
    settings_clicked = Signal()
    category_new = Signal()
    category_rename = Signal(int)
    category_delete = Signal(int)

    def __init__(self, theme: ThemeManager, animations=lambda: True, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.theme = theme
        self._animations = animations
        self._collapsed = False
        self._buttons: list[tuple[QPushButton, str, str]] = []     # button, full text, icon name
        self._cat_buttons: dict[int, QPushButton] = {}
        self._current = ("all", None)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._anim = QPropertyAnimation(self, b"navWidth", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.setFixedWidth(EXPANDED_W)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 12)
        root.setSpacing(2)

        self.lib_header = label("LIBRARY", "Section")
        root.addWidget(self.lib_header)
        for key, text, icon in _LIBRARY:
            root.addWidget(self._nav(text, icon, key, None))

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 4, 0)
        self.cat_header = label("CATEGORIES", "Section")
        self.add_cat = make_button("", "ghost", tooltip="New category")
        self.add_cat.setFixedSize(26, 26)
        self.add_cat.clicked.connect(self.category_new)
        head.addWidget(self.cat_header, 1)
        head.addWidget(self.add_cat)
        self.cat_head_widget = QWidget()
        self.cat_head_widget.setLayout(head)
        root.addWidget(self.cat_head_widget)

        self.cat_area = QVBoxLayout()
        self.cat_area.setSpacing(2)
        self.cat_area.setContentsMargins(0, 0, 0, 0)
        holder = QWidget()
        holder.setLayout(self.cat_area)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(holder)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.cat_area.addStretch(1)
        root.addWidget(scroll, 1)

        self.add_btn = make_button("Add Application", "primary", tooltip="Add Application (Ctrl+N)")
        self.add_btn.clicked.connect(self.add_clicked)
        root.addWidget(self.add_btn)
        self.settings_btn = self._plain_nav("Settings", "settings", self.settings_clicked)
        root.addWidget(self.settings_btn)
        self._buttons.append((self.settings_btn, "Settings", "settings"))
        self.retheme()
        theme.changed.connect(self.retheme)
        self.select("all", None)

    # -- animation property --------------------------------------------------------
    def _get_w(self) -> int:
        return self.width()

    def _set_w(self, v: int) -> None:
        self.setFixedWidth(v)

    navWidth = Property(int, _get_w, _set_w)

    # -- construction helpers --------------------------------------------------------
    def _plain_nav(self, text, icon, signal) -> QPushButton:
        b = QPushButton(text)
        b.setObjectName("Nav")
        b.setAccessibleName(text)
        b.setCursor(Qt.PointingHandCursor)
        b.setToolTip("Settings (Ctrl+,)")
        b.clicked.connect(signal)
        return b

    def _nav(self, text, icon, key, cat_id) -> QPushButton:
        b = QPushButton(text)
        b.setObjectName("Nav")
        b.setCheckable(True)
        b.setCursor(Qt.PointingHandCursor)
        b.setAccessibleName(text)
        b.clicked.connect(lambda: self._clicked(key, cat_id))
        self._group.addButton(b)
        self._buttons.append((b, text, icon))
        b.setProperty("key", key)
        b.setProperty("cat", cat_id)
        return b

    def _clicked(self, key, cat_id) -> None:
        self._current = (key, cat_id)
        self.section_selected.emit(key, cat_id)

    # -- public ----------------------------------------------------------------------
    def set_categories(self, cats: list[Category]) -> None:
        for b in self._cat_buttons.values():
            self._group.removeButton(b)
            self._buttons[:] = [t for t in self._buttons if t[0] is not b]
            b.setParent(None)
            b.deleteLater()
        self._cat_buttons.clear()
        for i, c in enumerate(cats):
            b = self._nav(c.name, "tag", "category", c.id)
            b.setContextMenuPolicy(Qt.CustomContextMenu)
            b.customContextMenuRequested.connect(lambda pos, cid=c.id, btn=b: self._cat_menu(cid, btn.mapToGlobal(pos)))
            self.cat_area.insertWidget(i, b)
            self._cat_buttons[c.id] = b
        self._apply_collapsed_text()
        self.retheme()
        key, cid = self._current
        if key == "category" and cid not in self._cat_buttons:
            self.select("all", None)
            self.section_selected.emit("all", None)
        else:
            self.select(key, cid)

    def select(self, key: str, cat_id) -> None:
        self._current = (key, cat_id)
        for b, _t, _i in self._buttons:
            if b.isCheckable() and b.property("key") == key and b.property("cat") == cat_id:
                b.setChecked(True)
                return

    def _cat_menu(self, cat_id: int, pos) -> None:
        m = QMenu(self)
        m.addAction("Rename…", lambda: self.category_rename.emit(cat_id))
        m.addAction("Delete…", lambda: self.category_delete.emit(cat_id))
        m.exec(pos)

    def is_collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool, animate: bool = True) -> None:
        self._collapsed = collapsed
        target = COLLAPSED_W if collapsed else EXPANDED_W
        self._anim.stop()
        if animate and self._animations():
            self._anim.setStartValue(self.width())
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self.setFixedWidth(target)
        self._apply_collapsed_text()

    def _apply_collapsed_text(self) -> None:
        c = self._collapsed
        for b, text, _icon in self._buttons:
            b.setText("" if c else text)
            b.setToolTip(text if c else ("Settings (Ctrl+,)" if text == "Settings" else ""))
        self.add_btn.setText("" if c else "Add Application")
        for w in (self.lib_header, self.cat_header):
            w.setVisible(not c)
        self.add_cat.setVisible(not c)

    def retheme(self) -> None:
        p = self.theme.palette
        for b, _t, icon in self._buttons:
            b.setIcon(self.theme.icon(icon, p.text, 20))
        self.add_btn.setIcon(self.theme.icon("plus", p.accent_text, 18))
        self.add_cat.setIcon(self.theme.icon("plus", p.muted, 16))
