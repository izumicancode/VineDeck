"""Main window: top bar, sidebar, library page and details page."""

from __future__ import annotations

import base64
from pathlib import Path

from PySide6.QtCore import QByteArray, QPropertyAnimation, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (QApplication, QButtonGroup, QComboBox, QFileDialog, QFrame, QGraphicsOpacityEffect,
                               QHBoxLayout, QInputDialog, QLineEdit, QMainWindow, QMenu, QMessageBox,
                               QStackedLayout, QStackedWidget, QToolButton, QVBoxLayout, QWidget)

from ..app_context import AppContext
from ..branding import APP_NAME, APP_TAGLINE
from ..core.launcher import LaunchError, build_launch_spec, proton_compat_location
from ..core.library import SORT_LABELS, LibraryQuery, filter_and_sort
from ..core.process_manager import LaunchState, WineProbe
from ..core.runners import discover_runners, is_proton_id
from ..core.scanner import default_prefix
from ..services import export_service
from ..services.filesystem_service import open_in_file_manager
from ..services.image_service import ImageError
from ..utils.logging import get_logger
from .app_details import DetailsPage
from .application_dialog import ApplicationDialog
from .dialogs.error_dialog import show_error
from .dialogs.text_dialog import TextDialog
from .library_model import LibraryModel
from .library_view import LibraryView
from .settings_dialog import SettingsDialog
from .sidebar import Sidebar
from .widgets import IMAGE_FILTER, EmptyState, Toast, label, make_button
from .card_delegate import list_columns

log = get_logger("ui")
_TITLES = {"all": "All Applications", "favorites": "Favorites", "recent": "Recently Played", "most_played": "Most Played"}
_VIEW_BUTTONS = (("grid", "grid", "Grid view"), ("compact", "grid-compact", "Compact grid view"),
                 ("list", "list", "List view"), ("large", "large", "Large cover view"))
_VIEW_KEYS = {"view_mode", "grid_columns", "card_width", "card_height", "gap_h", "gap_v", "corner_radius", "show_title",
              "show_category", "show_favorite", "show_launch", "show_description", "card_style"}


class BackgroundWidget(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self._pm: QPixmap | None = None
        self.reload()

    def reload(self) -> None:
        s = self.ctx.settings
        self._pm = None
        if s["background_mode"] == "custom" and s["background_image"]:
            out = self.ctx.images.prepare_background(s["background_image"], s["blur"])
            if out is not None:
                pm = QPixmap(str(out))
                self._pm = pm if not pm.isNull() else None
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        pal = self.ctx.theme.palette
        p.fillRect(self.rect(), pal.q("bg"))
        if self._pm is not None:
            pm = self._pm.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            p.drawPixmap((self.width() - pm.width()) // 2, (self.height() - pm.height()) // 2, pm)
            c = pal.q("bg")
            c.setAlpha(205)
            p.fillRect(self.rect(), c)


class ListHeader(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("ListHeader")
        self.setFixedHeight(30)
        self.names = ("NAME", "CATEGORY", "LAST PLAYED")

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setPen(self.palette().color(self.palette().ColorRole.PlaceholderText))
        f = p.font()
        f.setPointSizeF(f.pointSizeF() - 1.5)
        f.setBold(True)
        p.setFont(f)
        left = 14                     # same inset as the library view
        xs = list_columns(self.width() - left - 20)
        for x, text in zip(xs, self.names):
            p.drawText(left + x, 0, 200, self.height(), Qt.AlignVCenter, text)


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.s = ctx.settings
        self.theme = ctx.theme
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 800)
        self.setMinimumSize(760, 520)
        self.apps = []
        self.section, self.category_id = "all", None
        self._history: dict[int, int] = {}
        self._welcome = not self.s["first_run_done"]

        self.bg = BackgroundWidget(ctx)
        self.setCentralWidget(self.bg)
        root = QVBoxLayout(self.bg)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_topbar())
        self.banner = self._build_banner()
        root.addWidget(self.banner)
        body = QHBoxLayout()
        body.setSpacing(0)
        root.addLayout(body, 1)

        self.sidebar = Sidebar(self.theme, lambda: self.s["animations"])
        body.addWidget(self.sidebar)
        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)

        # library page
        self.model = LibraryModel(self)
        self.view = LibraryView(self.model, self.s, self.theme, ctx.artwork)
        self.empty = EmptyState()
        self.list_header = ListHeader()
        page = QWidget()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(24, 18, 12, 0)
        pl.setSpacing(6)
        head = QHBoxLayout()
        self.heading = label(name="Title")
        self.count = label(muted=True)
        head.addWidget(self.heading)
        head.addWidget(self.count, 0, Qt.AlignBottom)
        head.addStretch(1)
        pl.addLayout(head)
        pl.addWidget(self.list_header)
        holder = QWidget()
        self.holder_layout = QStackedLayout(holder)
        self.holder_layout.addWidget(self.view)
        self.holder_layout.addWidget(self.empty)
        pl.addWidget(holder, 1)
        self.stack.addWidget(page)
        self.library_page = page
        self.details = DetailsPage(ctx)
        self.stack.addWidget(self.details)

        self.toast = Toast(self.bg)
        self._connect()
        self._shortcuts()
        self._sync_controls()
        self.refresh_runners()
        self.retheme()
        self.theme.changed.connect(self.retheme)

        self.sidebar.set_collapsed(self.s["sidebar_collapsed"], animate=False)
        self._restore_geometry()
        self.reload()
        if self._welcome:
            self.s.set("first_run_done", True)
        self.ctx.wine.binary, self.ctx.wine.runner = self.s["wine_binary"], self.s["runner"]
        self._probe = WineProbe()
        self._probe.finished.connect(self._wine_probed)
        self._probe.start(self.s["wine_binary"], self.s["runner"])

    # -- construction --------------------------------------------------------------------
    def _build_topbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(58)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(14, 8, 16, 8)
        lay.setSpacing(8)
        self.menu_btn = QToolButton()
        self.menu_btn.setToolTip("Collapse or expand the sidebar")
        self.menu_btn.setAccessibleName("Toggle sidebar")
        self.brand = label(APP_NAME, "H2")
        lay.addWidget(self.menu_btn)
        lay.addWidget(self.brand)
        lay.addStretch(1)
        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setPlaceholderText("Search  (Ctrl+F)")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(130)
        self.search.setAccessibleName("Search applications")
        self.search_action = QAction(self)
        self.search.addAction(self.search_action, QLineEdit.LeadingPosition)
        lay.addWidget(self.search)
        lay.addSpacing(10)
        self.view_group = QButtonGroup(self)
        self.view_btns: dict[str, QToolButton] = {}
        for key, ic, tip in _VIEW_BUTTONS:
            b = QToolButton()
            b.setCheckable(True)
            b.setToolTip(tip)
            b.setAccessibleName(tip)
            b.setProperty("icon_name", ic)
            self.view_group.addButton(b)
            self.view_btns[key] = b
            lay.addWidget(b)
            b.clicked.connect(lambda _=False, k=key: self.s.set("view_mode", k))
        lay.addSpacing(8)
        self.sort_combo = QComboBox()
        self.sort_combo.setAccessibleName("Sort by")
        self.sort_combo.setMaxVisibleItems(10)
        for k, t in SORT_LABELS.items():
            self.sort_combo.addItem(t, k)
        self.sort_combo.activated.connect(lambda i: self.s.set("sort_key", self.sort_combo.itemData(i)))
        self.runner_combo = QComboBox()
        self.runner_combo.setAccessibleName("Runner")
        self.runner_combo.setToolTip("Choose how applications are launched: system Wine or a Steam Proton build")
        self.runner_combo.setMaximumWidth(230)
        self.runner_combo.setMinimumContentsLength(1)
        self.runner_combo.setMaxVisibleItems(10)
        self.runner_combo.activated.connect(lambda i: self.s.set("runner", self.runner_combo.itemData(i)))
        self.rev_btn = QToolButton()
        self.rev_btn.setCheckable(True)
        self.rev_btn.setToolTip("Reverse sort order")
        self.rev_btn.setAccessibleName("Reverse sort order")
        self.rev_btn.clicked.connect(lambda on: self.s.set("sort_reverse", on))
        self.settings_btn = QToolButton()
        self.settings_btn.setToolTip("Settings (Ctrl+,)")
        self.settings_btn.setAccessibleName("Settings")
        lay.addWidget(self.runner_combo)
        lay.addWidget(self.sort_combo)
        lay.addWidget(self.rev_btn)
        lay.addSpacing(6)
        lay.addWidget(self.settings_btn)
        return bar

    def _build_banner(self) -> QWidget:
        f = QFrame()
        f.setObjectName("Banner")
        lay = QHBoxLayout(f)
        lay.setContentsMargins(14, 8, 8, 8)
        self.banner_text = label(wrap=True)
        lay.addWidget(self.banner_text, 1)
        fix = make_button("Runner Settings")
        fix.clicked.connect(lambda: self.open_settings("Wine"))
        close = make_button("Dismiss", "ghost")
        close.clicked.connect(f.hide)
        lay.addWidget(fix)
        lay.addWidget(close)
        f.hide()
        f.setContentsMargins(0, 0, 0, 0)
        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(16, 10, 16, 0)
        wl.addWidget(f)
        wrap.hide()
        self._banner_frame = f
        wrap.setObjectName("BannerWrap")
        return wrap

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        compact = self.width() < 900
        self.search.setMinimumWidth(130 if compact else 220)
        self.runner_combo.setMaximumWidth(150 if compact else 230)

    def _connect(self) -> None:
        sb, v = self.sidebar, self.view
        self.menu_btn.clicked.connect(self.toggle_sidebar)
        self.settings_btn.clicked.connect(lambda: self.open_settings())
        self.search.textChanged.connect(self.refresh_view)
        sb.section_selected.connect(self._section_selected)
        sb.add_clicked.connect(self.add_application)
        sb.settings_clicked.connect(lambda: self.open_settings())
        sb.category_new.connect(self.new_category)
        sb.category_rename.connect(self.rename_category)
        sb.category_delete.connect(self.delete_category)
        self.empty.action_clicked.connect(self.add_application)
        v.launch_requested.connect(self.launch)
        v.favorite_toggled.connect(self.toggle_favorite)
        v.menu_requested.connect(self.show_menu)
        v.open_requested.connect(self.open_details)
        v.remove_requested.connect(self.remove_application)
        self.model.reorder_requested.connect(self._reorder)
        d = self.details
        d.back_requested.connect(self.show_library)
        d.play_requested.connect(self.launch)
        d.edit_requested.connect(self.edit_application)
        d.favorite_toggled.connect(self.toggle_favorite)
        d.menu_requested.connect(self.show_menu)
        pm = self.ctx.processes
        pm.state_changed.connect(self._state_changed)
        pm.exited.connect(self._process_exited)
        self.s.subscribe(self._setting_changed)

    def _shortcuts(self) -> None:
        def sc(seq, fn):
            QShortcut(QKeySequence(seq), self, activated=fn)
        sc("Ctrl+F", lambda: (self.show_library(), self.search.setFocus(), self.search.selectAll()))
        sc("Ctrl+N", self.add_application)
        sc("Ctrl+,", lambda: self.open_settings())
        sc("F11", self.toggle_fullscreen)
        sc("Ctrl+Q", self.close)
        sc("Escape", self._escape)
        sc("Ctrl+B", self.toggle_sidebar)

    def _escape(self) -> None:
        if self.stack.currentWidget() is self.details:
            self.show_library()
        elif self.search.hasFocus() and self.search.text():
            self.search.clear()
        elif self.isFullScreen():
            self.toggle_fullscreen()

    # -- theming / sync ----------------------------------------------------------------------
    def retheme(self) -> None:
        p = self.theme.palette
        t = self.theme
        self.menu_btn.setIcon(t.icon("menu", p.text, 22))
        self.settings_btn.setIcon(t.icon("settings", p.text, 22))
        self.rev_btn.setIcon(t.icon("sort", p.text, 20))
        self.search_action.setIcon(t.icon("search", p.muted, 18))
        for b in self.view_btns.values():
            b.setIcon(t.icon(b.property("icon_name"), p.text, 20))
        self.bg.reload()
        self._banner_frame.setStyleSheet("")
        self._update_empty_icon()

    def _update_empty_icon(self) -> None:
        self._logo_pm = QPixmap(str(Path(__file__).resolve().parent.parent / "resources/icons/vinedeck.svg")).scaled(
            96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.refresh_view()

    def refresh_runners(self) -> None:
        """Re-scan for Proton builds and rebuild the top-bar runner switcher.

        The switcher is hidden when Proton is not installed so Wine-only setups look unchanged.
        """
        runners = discover_runners()
        current = self.s["runner"]
        self.runner_combo.blockSignals(True)
        self.runner_combo.clear()
        for r in runners:
            self.runner_combo.addItem(r.label if r.kind == "proton" else r.name, r.id)
            self.runner_combo.setItemData(self.runner_combo.count() - 1, r.path or r.source, Qt.ToolTipRole)
        if self.runner_combo.findData(current) < 0:          # selected build vanished: keep showing it
            name = Path(current[len("proton:"):]).parent.name if is_proton_id(current) else current
            self.runner_combo.addItem(f"{name} (not found)", current)
        self.runner_combo.blockSignals(False)
        self._select_runner_item()
        self.runner_combo.setVisible(any(r.kind == "proton" for r in runners) or is_proton_id(current))

    def _select_runner_item(self) -> None:
        i = self.runner_combo.findData(self.s["runner"])
        if i >= 0:
            self.runner_combo.blockSignals(True)
            self.runner_combo.setCurrentIndex(i)
            self.runner_combo.blockSignals(False)

    def _sync_controls(self) -> None:
        self.view_btns[self.s["view_mode"]].setChecked(True)
        self.sort_combo.setCurrentIndex(self.sort_combo.findData(self.s["sort_key"]))
        self.rev_btn.setChecked(self.s["sort_reverse"])

    def _setting_changed(self, key: str, _v) -> None:
        if key in _VIEW_KEYS:
            self.view.apply_settings()
            self.list_header.setVisible(self.s["view_mode"] == "list" and self.holder_layout.currentWidget() is self.view)
            self._sync_controls()
        if key in ("sort_key", "sort_reverse"):
            self._sync_controls()
            self.refresh_view()
        if key in ("background_mode", "background_image", "blur"):
            self.bg.reload()
            self.details.hero.update()
        if key in ("wine_binary", "runner"):
            self.ctx.wine.binary = self.s["wine_binary"]
            self.ctx.wine.runner = self.s["runner"]
            self._probe.start(self.s["wine_binary"], self.s["runner"])
            if key == "runner":
                self._select_runner_item()
                self.notify(f"Runner: {self.runner_combo.currentText().split('  ·')[0]}")
        if key == "animations":
            pass            # consulted lazily by the sidebar, delegate and page transitions

    # -- data / filtering ----------------------------------------------------------------------------
    def reload(self) -> None:
        self.apps = self.ctx.db.list_applications()
        self.sidebar.set_categories(self.ctx.db.list_categories())
        self.refresh_view()
        cur = self.details.current_id()
        if cur is not None and self.stack.currentWidget() is self.details:
            app = self.ctx.db.get_application(cur)
            if app:
                self.details.show_app(app, self._state_text(cur))
            else:
                self.show_library()

    def _state_text(self, app_id):
        return self.model.state(app_id)

    def refresh_view(self) -> None:
        q = LibraryQuery(self.section, self.category_id, self.search.text(), self.s["sort_key"], self.s["sort_reverse"])
        items = filter_and_sort(self.apps, q)
        keep = self.view.currentIndex().data(Qt.UserRole + 3) if self.view.currentIndex().isValid() else None
        self.model.set_applications(items)
        for a in items:
            st = self.ctx.processes.state(a.id)
            if st:
                self.model.set_state(a.id, st.value)
        if keep is not None:
            self.view.select_app(keep)
        title = _TITLES.get(self.section)
        if self.section == "category":
            cat = next((c for c in self.ctx.db.list_categories() if c.id == self.category_id), None)
            title = cat.name if cat else "Category"
        self.heading.setText(title or "")
        self.count.setText(f"  {len(items)} application{'s' if len(items) != 1 else ''}")
        can_reorder = (self.s["sort_key"] == "custom" and not self.s["sort_reverse"]
                       and self.section in ("all", "favorites", "category"))
        self.view.set_reorder_enabled(can_reorder)
        self.view.setToolTip("Drag cards to rearrange them" if can_reorder else "")
        if items:
            self.holder_layout.setCurrentWidget(self.view)
        else:
            self._show_empty()
        self.list_header.setVisible(bool(items) and self.s["view_mode"] == "list")

    def _show_empty(self) -> None:
        total = len(self.apps)
        logo = getattr(self, "_logo_pm", None)
        if total == 0:
            if self._welcome:
                self.empty.configure(title=f"Welcome to {APP_NAME}", text=APP_TAGLINE,
                                     button="Add Your First Application", logo=logo)
            else:
                self.empty.configure(title="Your library is empty.", text="Add your first Windows application or game.",
                                     button="+ Add Application", logo=logo)
        elif self.search.text().strip():
            self.empty.configure(title="No matches", text="No application matches your search. Try a different word.",
                                 button=None, icon=self.theme.icon("search", self.theme.palette.muted, 48).pixmap(48, 48))
        else:
            self.empty.configure(title="Nothing here yet", text="No applications in this section.", button=None,
                                 icon=self.theme.icon("tag", self.theme.palette.muted, 48).pixmap(48, 48))
        self.holder_layout.setCurrentWidget(self.empty)

    def _section_selected(self, key: str, cat_id) -> None:
        self.section, self.category_id = key, cat_id
        self.show_library()
        self.refresh_view()

    # -- navigation -----------------------------------------------------------------------------------------
    def _switch(self, widget: QWidget) -> None:
        if self.stack.currentWidget() is widget:
            return
        self.stack.setCurrentWidget(widget)
        if self.s["animations"]:
            eff = QGraphicsOpacityEffect(widget)
            widget.setGraphicsEffect(eff)
            anim = QPropertyAnimation(eff, b"opacity", widget)
            anim.setDuration(140)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.finished.connect(lambda: widget.setGraphicsEffect(None))
            anim.start(QPropertyAnimation.DeleteWhenStopped)

    def show_library(self) -> None:
        self._switch(self.library_page)

    def open_details(self, app_id: int) -> None:
        app = self.ctx.db.get_application(app_id)
        if app:
            self.details.show_app(app, self._state_text(app_id))
            self._switch(self.details)
            self.details.play.setFocus()

    def toggle_sidebar(self) -> None:
        self.sidebar.set_collapsed(not self.sidebar.is_collapsed())
        self.s.set("sidebar_collapsed", self.sidebar.is_collapsed())

    def toggle_fullscreen(self) -> None:
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def notify(self, text: str) -> None:
        self.toast.show_message(text)

    # -- actions -------------------------------------------------------------------------------------------------
    def add_application(self) -> None:
        dlg = ApplicationDialog(self.ctx, self)
        if dlg.exec() and dlg.result_application:
            app = self.ctx.db.add_application(dlg.result_application)
            self._welcome = False
            self.reload()
            self.view.select_app(app.id)
            self.notify(f"Added “{app.name}”")

    def edit_application(self, app_id: int) -> None:
        app = self.ctx.db.get_application(app_id)
        if not app:
            return
        dlg = ApplicationDialog(self.ctx, self, app)
        if dlg.exec() and dlg.result_application:
            self.ctx.db.update_application(dlg.result_application)
            self._delete_artwork(dlg.obsolete_artwork)
            self.reload()
            self.notify("Changes saved")

    def _delete_artwork(self, items) -> None:
        for kind, name in items:
            (self.ctx.images.delete_cover if kind == "cover" else self.ctx.images.delete_icon)(name)

    def remove_application(self, app_id: int) -> None:
        app = self.ctx.db.get_application(app_id)
        if not app:
            return
        if self.s["confirm_remove"]:
            box = QMessageBox(QMessageBox.Question, "Remove from library", f"Remove “{app.name}” from the library?", parent=self)
            box.setInformativeText("This only removes the library entry. The application, its files and its Wine prefix are not touched.")
            remove = box.addButton("Remove from Library", QMessageBox.DestructiveRole)
            box.addButton(QMessageBox.Cancel)
            box.setDefaultButton(QMessageBox.Cancel)
            box.exec()
            if box.clickedButton() is not remove:
                return
        self.ctx.db.delete_application(app_id)
        self._delete_artwork([("cover", app.cover_path), ("icon", app.icon_path)])
        if self.stack.currentWidget() is self.details:
            self.show_library()
        self.reload()
        self.notify(f"Removed “{app.name}” from the library")

    def toggle_favorite(self, app_id: int) -> None:
        app = self.ctx.db.get_application(app_id)
        if app:
            self.ctx.db.set_favorite(app_id, not app.favorite)
            self.reload()

    def change_cover(self, app_id: int) -> None:
        app = self.ctx.db.get_application(app_id)
        if not app:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Select cover image", str(Path.home()), IMAGE_FILTER)
        if not path:
            return
        try:
            name = self.ctx.images.import_cover(path)
        except ImageError as exc:
            show_error(self, "Unable to use this image", str(exc), ["The file is damaged", "The format is not PNG, JPG or WEBP"])
            return
        old, app.cover_path = app.cover_path, name
        self.ctx.db.update_application(app)
        self.ctx.images.delete_cover(old)
        self.reload()

    def _reorder(self, dragged: int, target: int) -> None:
        self.ctx.db.reorder_application(dragged, target)
        self.apps = self.ctx.db.list_applications()
        self.refresh_view()
        self.view.select_app(dragged)

    # categories
    def new_category(self) -> None:
        name, ok = QInputDialog.getText(self, "New Category", "Category name:")
        if ok and name.strip():
            try:
                cat = self.ctx.db.add_category(name)
            except ValueError as exc:
                show_error(self, "Unable to create category", str(exc))
                return
            self.reload()
            self.sidebar.select("category", cat.id)

    def rename_category(self, cat_id: int) -> None:
        cur = next((c for c in self.ctx.db.list_categories() if c.id == cat_id), None)
        name, ok = QInputDialog.getText(self, "Rename Category", "New name:", text=cur.name if cur else "")
        if ok and name.strip():
            try:
                self.ctx.db.rename_category(cat_id, name)
            except ValueError as exc:
                show_error(self, "Unable to rename category", str(exc))
                return
            self.reload()

    def delete_category(self, cat_id: int) -> None:
        cur = next((c for c in self.ctx.db.list_categories() if c.id == cat_id), None)
        if cur and QMessageBox.question(self, "Delete category", f"Delete the category “{cur.name}”?\n"
                                        "Applications in it are kept and become uncategorised.") == QMessageBox.Yes:
            self.ctx.db.delete_category(cat_id)
            self.reload()

    # context menu
    def show_menu(self, app_id: int, pos) -> None:
        app = self.ctx.db.get_application(app_id)
        if not app:
            return
        m = QMenu(self)
        m.addAction("Launch", lambda: self.launch(app_id)).setEnabled(not self.ctx.processes.is_active(app_id))
        m.addAction("Edit…", lambda: self.edit_application(app_id))
        m.addAction("Remove from Favorites" if app.favorite else "Add to Favorites", lambda: self.toggle_favorite(app_id))
        m.addAction("Change Cover…", lambda: self.change_cover(app_id))
        m.addSeparator()
        m.addAction("Open Application Folder", lambda: self._open_app_folder(app))
        m.addAction("Open Wine Prefix", lambda: self._open_prefix(app))
        m.addAction("Copy Executable Path", lambda: (QGuiApplication.clipboard().setText(app.executable_path),
                                                      self.notify("Executable path copied")))
        m.addAction("View Configuration", lambda: self._view_config(app))
        m.addSeparator()
        m.addAction("Remove from Library…", lambda: self.remove_application(app_id))
        m.exec(pos)

    def _open_app_folder(self, app) -> None:
        if not open_in_file_manager(Path(app.executable_path).expanduser()):
            self.notify("That folder no longer exists")

    def _open_prefix(self, app) -> None:
        if is_proton_id(self.s["runner"]):
            compat, _link = proton_compat_location(app, self.ctx.paths.proton_dir)
            target = compat / "pfx" if (compat / "pfx").exists() else compat
        else:
            target = Path(app.wine_prefix).expanduser() if app.wine_prefix else default_prefix()
        if not target.is_dir() or not open_in_file_manager(target):
            self.notify("That Wine prefix folder does not exist")

    def _view_config(self, app) -> None:
        env = "\n".join(f"  {k}={v}" for k, v in app.env_vars.items()) or "  (none)"
        text = (f"Name: {app.name}\nExecutable: {app.executable_path}\nWine prefix: {app.wine_prefix or '(Wine default)'}\n"
                f"Working directory: {app.working_directory or '(executable folder)'}\n"
                f"Arguments: {app.launch_arguments or '(none)'}\nEnvironment:\n{env}\nCategory: {app.category_name or '(none)'}\n"
                f"Launches: {app.launch_count}\nLast played: {app.last_played or 'never'}")
        TextDialog(self, f"Configuration — {app.name}", text).exec()

    # launching
    def launch(self, app_id: int) -> None:
        app = self.ctx.db.get_application(app_id)
        if not app:
            return
        info = self.ctx.wine.info
        if not info.found:                      # settings may have changed since startup; re-check once
            info = self.ctx.wine.refresh()
        try:
            spec = build_launch_spec(app, info.path if info.found else None, runner=info,
                                     proton_root=self.ctx.paths.proton_dir)
            self.ctx.processes.launch(spec)
        except LaunchError as exc:
            show_error(self, "Unable to launch application", exc.message, exc.causes,
                       exc.details or (info.error or ""))
            return
        self._history[app_id] = self.ctx.db.record_launch_start(app_id)
        self.apps = self.ctx.db.list_applications()
        self.refresh_view()
        self.view.select_app(app_id)

    def _state_changed(self, app_id: int, state: str, detail: str) -> None:
        self.model.set_state(app_id, state)
        if self.details.current_id() == app_id:
            self.details.set_state(state)
        if state == LaunchState.FAILED.value:
            app = self.ctx.db.get_application(app_id)
            tail = ""
            try:
                tail = self.ctx.processes.launch_log_path(app_id).read_text(errors="replace")[-4000:]
            except OSError:
                pass
            show_error(self, "Unable to launch application", f"{self.ctx.wine.info.runner_label} started, but “{app.name if app else 'the application'}” "
                       "closed right away.", ["The program needs a different Wine prefix or Windows version",
                                              "Required libraries (e.g. DXVK, vcrun) are missing from the prefix",
                                              "The launch arguments are not accepted by the program"],
                       f"{detail}\n\n{tail}".strip())
        if state in (LaunchState.CLOSED.value, LaunchState.FAILED.value):
            QTimer.singleShot(6000, lambda: self._clear_state(app_id))

    def _clear_state(self, app_id: int) -> None:
        if not self.ctx.processes.is_active(app_id):
            self.model.set_state(app_id, None)
            if self.details.current_id() == app_id:
                self.details.set_state(None)

    def _process_exited(self, app_id: int, rc: int) -> None:
        hid = self._history.pop(app_id, None)
        if hid:
            self.ctx.db.record_launch_end(hid, rc)

    # wine
    def _wine_probed(self, info) -> None:
        self.ctx.wine.info = info
        self.wine_changed(info)

    def wine_changed(self, info) -> None:
        wrap = self._banner_frame.parentWidget()
        if info.found:
            wrap.hide()
            self._banner_frame.hide()
        else:
            self.banner_text.setText(f"{info.runner_label} is not available: {info.error}  "
                                     "You can still manage your library.")
            wrap.show()
            self._banner_frame.show()

    # settings & backup
    def open_settings(self, page: str = "General") -> None:
        SettingsDialog(self.ctx, {"wine_changed": self.wine_changed, "export": self.export_library,
                                  "import": self.import_library}, self, page).exec()
        self.refresh_runners()
        self.reload()

    def export_library(self) -> None:
        path, flt = QFileDialog.getSaveFileName(self, "Export library", str(Path.home() / "library"),
                                                "Metadata only (*.json);;Metadata with artwork (*.zip)")
        if not path:
            return
        art = flt.endswith("(*.zip)") or path.endswith(".zip")
        if not path.endswith((".json", ".zip")):
            path += ".zip" if art else ".json"
        try:
            n = export_service.export_library(self.ctx.db, self.ctx.paths, Path(path), art)
        except export_service.ExportError as exc:
            show_error(self, "Unable to export library", str(exc))
            return
        self.notify(f"Exported {n} applications")

    def import_library(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import library", str(Path.home()), "Library exports (*.json *.zip)")
        if not path:
            return
        try:
            r = export_service.import_library(self.ctx.db, self.ctx.paths, Path(path), self.ctx.images)
        except export_service.ExportError as exc:
            show_error(self, "Unable to import library", str(exc), ["The file was not created by this application",
                                                                    "The file is damaged"])
            return
        self.reload()
        self.notify(f"Imported {r.added} application(s), skipped {r.skipped} already present")

    # window state
    def _restore_geometry(self) -> None:
        g = self.s["window_geometry"]
        if g and self.s["restore_geometry"]:
            self.restoreGeometry(QByteArray(base64.b64decode(g)))

    def closeEvent(self, e):
        if self.s["restore_geometry"] and not self.isFullScreen():
            self.s.set("window_geometry", base64.b64encode(bytes(self.saveGeometry())).decode(), save=False)
        self.ctx.settings.save()
        super().closeEvent(e)           # running games are untouched: they live in their own sessions
