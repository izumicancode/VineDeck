"""Add / Edit application dialog."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout, QInputDialog,
                               QLineEdit, QPlainTextEdit, QScrollArea, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget, QHeaderView)

from ..core.launcher import validate_env_name
from ..core.scanner import default_prefix, discover_prefixes
from ..database.models import Application
from ..services import filesystem_service as fs
from ..services.icon_service import extract_exe_icon
from ..services.image_service import ImageError
from .widgets import ImagePicker, PathField, label, make_button

NEW_CATEGORY = "New category…"


def pil_to_pixmap(img) -> QPixmap:
    img = img.convert("RGBA")
    qimg = QImage(img.tobytes("raw", "RGBA"), img.width, img.height, QImage.Format_RGBA8888).copy()
    return QPixmap.fromImage(qimg)


class ApplicationDialog(QDialog):
    """Creates (``app=None``) or edits an application.

    On accept, :meth:`result_application` holds the new values; artwork has already been
    imported into the data directory. ``obsolete_artwork`` lists replaced files the caller
    may delete once the database write succeeded.
    """

    def __init__(self, ctx, parent=None, app: Application | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self.original = app
        self.editing = app is not None
        self.result_application: Application | None = None
        self.obsolete_artwork: list[tuple[str, str]] = []     # (kind, name)
        self.setWindowTitle("Edit Application" if self.editing else "Add Application")
        self.setModal(True)
        self.resize(640, 760)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        body = QWidget()
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        col = QVBoxLayout(body)
        col.setContentsMargins(26, 24, 26, 8)
        col.setSpacing(14)
        col.addWidget(label("Edit Application" if self.editing else "Add Application", "Title"))
        col.addWidget(label("Choose the program, then tell Wine where its prefix lives.", muted=True))

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        col.addLayout(form)

        self.name = QLineEdit()
        self.name.setPlaceholderText("e.g. Cyberpunk 2077")
        self.name.setAccessibleName("Application name")
        form.addRow("Application Name", self.name)

        self.exe = PathField("file", placeholder="/path/to/program.exe", title="Select executable",
                             accessible="Executable", start_dir=lambda: self.exe.text() and str(Path(self.exe.text()).parent))
        self.exe.textChanged.connect(self._exe_changed)
        form.addRow("Executable", self.exe)

        self.prefix = PathField("dir", placeholder=f"Default ({default_prefix()})", title="Select Wine prefix",
                                accessible="Wine prefix", start_dir=lambda: str(Path.home()))
        self.prefix.set_suggestions([str(p) for p in discover_prefixes()])
        form.addRow("Wine Prefix", self.prefix)
        form.addRow("", label("Leave empty to use Wine’s default prefix. A custom prefix must already exist.",
                              muted=True, wrap=True))

        self.workdir = PathField("dir", placeholder="Same folder as the executable", title="Select working directory",
                                 accessible="Working directory", start_dir=lambda: self.exe.text() and str(Path(self.exe.text()).parent))
        form.addRow("Working Directory", self.workdir)

        self.args = QLineEdit()
        self.args.setPlaceholderText("--fullscreen -windowed")
        self.args.setAccessibleName("Launch arguments")
        form.addRow("Launch Arguments", self.args)

        self.category = QComboBox()
        self.category.setAccessibleName("Category")
        self._fill_categories(None)
        self.category.activated.connect(self._category_activated)
        form.addRow("Category", self.category)

        self.cover = ImagePicker("Cover", QSize(120, 180), "No cover")
        form.addRow("Cover Image", self.cover)

        self.from_exe = make_button("Use Icon from Executable", tooltip="Extract the icon from the .exe file")
        self.from_exe.clicked.connect(self._extract_icon)
        self.icon = ImagePicker("Icon", QSize(84, 84), "No icon", extra_buttons=[self.from_exe])
        form.addRow("Icon", self.icon)

        self.description = QPlainTextEdit()
        self.description.setPlaceholderText("Optional notes about this application")
        self.description.setFixedHeight(84)
        self.description.setAccessibleName("Description")
        form.addRow("Description", self.description)

        self.favorite = QCheckBox("Favorite")
        form.addRow("", self.favorite)

        # collapsible: details
        self.details_toggle = make_button("Details  ▸", "ghost")
        self.details_toggle.setCheckable(True)
        self.details_box = QWidget()
        dform = QFormLayout(self.details_box)
        dform.setContentsMargins(0, 0, 0, 0)
        dform.setVerticalSpacing(10)
        dform.setHorizontalSpacing(18)
        self.meta = {k: QLineEdit() for k in ("developer", "publisher", "version", "genre", "release_year", "website")}
        for key, edit in self.meta.items():
            edit.setAccessibleName(key.replace("_", " ").title())
            dform.addRow(key.replace("_", " ").title(), edit)
        self.details_box.hide()
        self.details_toggle.toggled.connect(lambda on: self._toggle(self.details_toggle, self.details_box, "Details", on))
        col.addWidget(self.details_toggle, 0, Qt.AlignLeft)
        col.addWidget(self.details_box)

        # collapsible: environment variables
        self.env_toggle = make_button("Advanced: environment variables  ▸", "ghost")
        self.env_toggle.setCheckable(True)
        self.env_box = QWidget()
        elay = QVBoxLayout(self.env_box)
        elay.setContentsMargins(0, 0, 0, 0)
        elay.addWidget(label("Set per-application variables such as WINEDEBUG, DXVK_HUD or VKD3D_DEBUG.", muted=True, wrap=True))
        self.env_table = QTableWidget(0, 2)
        self.env_table.setHorizontalHeaderLabels(["Name", "Value"])
        self.env_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.env_table.verticalHeader().hide()
        self.env_table.setMinimumHeight(140)
        self.env_table.setAccessibleName("Environment variables")
        elay.addWidget(self.env_table)
        erow = QHBoxLayout()
        add = make_button("Add Variable")
        add.clicked.connect(lambda: self._add_env_row("", ""))
        rm = make_button("Remove Selected", "ghost")
        rm.clicked.connect(self._remove_env_rows)
        erow.addWidget(add)
        erow.addWidget(rm)
        erow.addStretch(1)
        elay.addLayout(erow)
        self.env_box.hide()
        self.env_toggle.toggled.connect(lambda on: self._toggle(self.env_toggle, self.env_box, "Advanced: environment variables", on))
        col.addWidget(self.env_toggle, 0, Qt.AlignLeft)
        col.addWidget(self.env_box)
        col.addStretch(1)

        # footer
        footer = QVBoxLayout()
        footer.setContentsMargins(26, 8, 26, 18)
        self.error = label(name="Error", wrap=True)
        self.error.setAccessibleName("Form error")
        self.error.hide()
        footer.addWidget(self.error)
        row = QHBoxLayout()
        cancel = make_button("Cancel")
        cancel.clicked.connect(self.reject)
        self.submit = make_button("Save Changes" if self.editing else "Add Application", "primary")
        self.submit.setDefault(True)
        self.submit.clicked.connect(self.accept)
        row.addStretch(1)
        row.addWidget(cancel)
        row.addWidget(self.submit)
        footer.addLayout(row)
        outer.addLayout(footer)

        if app is not None:
            self._load(app)
        else:
            self.prefix.setText(ctx.settings["default_prefix"])
        self.name.setFocus()

    # -- helpers ----------------------------------------------------------------
    @staticmethod
    def _toggle(btn, box, title, on):
        box.setVisible(on)
        btn.setText(f"{title}  {'▾' if on else '▸'}")

    def _fill_categories(self, selected_id) -> None:
        self.category.blockSignals(True)
        self.category.clear()
        self.category.addItem("No category", None)
        for c in self.ctx.db.list_categories():
            self.category.addItem(c.name, c.id)
        self.category.addItem(NEW_CATEGORY, "__new__")
        idx = self.category.findData(selected_id)
        self.category.setCurrentIndex(max(idx, 0))
        self.category.blockSignals(False)
        self._last_category = self.category.currentIndex()

    def _category_activated(self, index: int) -> None:
        if self.category.itemData(index) != "__new__":
            self._last_category = index
            return
        name, ok = QInputDialog.getText(self, "New Category", "Category name:")
        if ok and name.strip():
            try:
                cat = self.ctx.db.add_category(name)
            except ValueError as exc:
                existing = self.ctx.db.get_category_by_name(name)
                if existing is None:
                    self._show_error(str(exc))
                    self.category.setCurrentIndex(self._last_category)
                    return
                cat = existing
            self._fill_categories(cat.id)
        else:
            self.category.setCurrentIndex(self._last_category)

    def _add_env_row(self, name: str, value: str) -> None:
        r = self.env_table.rowCount()
        self.env_table.insertRow(r)
        self.env_table.setItem(r, 0, QTableWidgetItem(name))
        self.env_table.setItem(r, 1, QTableWidgetItem(value))
        if not name:
            self.env_table.editItem(self.env_table.item(r, 0))

    def _remove_env_rows(self) -> None:
        for r in sorted({i.row() for i in self.env_table.selectedIndexes()}, reverse=True):
            self.env_table.removeRow(r)

    def _env_dict(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for r in range(self.env_table.rowCount()):
            n = (self.env_table.item(r, 0) or QTableWidgetItem()).text().strip()
            v = (self.env_table.item(r, 1) or QTableWidgetItem()).text()
            if n or v:
                out[n] = v
        return out

    def _exe_changed(self, text: str) -> None:
        if not self.name.text().strip() and fs.validate_executable(text) is None:
            meta = self.ctx.metadata.lookup(text)
            if meta and meta.name:
                self.name.setText(meta.name)

    def _extract_icon(self) -> None:
        if fs.validate_executable(self.exe.text()) is not None:
            self._show_error("Choose a valid executable first.")
            return
        img = extract_exe_icon(self.exe.text())
        if img is None:
            self._show_error("No icon could be extracted from this executable. You can pick an image instead.")
            return
        self.error.hide()
        self.icon.set_image(img, pil_to_pixmap(img))

    def _show_error(self, text: str) -> None:
        self.error.setText(text)
        self.error.show()

    # -- load / save -----------------------------------------------------------------
    def _load(self, a: Application) -> None:
        self.name.setText(a.name)
        self.exe.setText(a.executable_path)
        self.prefix.setText(a.wine_prefix)
        self.workdir.setText(a.working_directory)
        self.args.setText(a.launch_arguments)
        self._fill_categories(a.category_id)
        self.description.setPlainText(a.description)
        self.favorite.setChecked(a.favorite)
        for k, edit in self.meta.items():
            edit.setText(getattr(a, k))
        for n, v in a.env_vars.items():
            self._add_env_row(n, v)
        self.cover.set_existing(self.ctx.artwork.cover(a))
        self.icon.set_existing(self.ctx.artwork.icon(a))
        if any(getattr(a, k) for k in self.meta):
            self.details_toggle.setChecked(True)
        if a.env_vars:
            self.env_toggle.setChecked(True)

    def accept(self) -> None:
        name = self.name.text().strip()
        problem = None
        if not name:
            problem, widget = "Please enter a name for the application.", self.name
        elif (err := fs.validate_executable(self.exe.text())):
            problem, widget = f"Executable: {err}", self.exe
        elif self.prefix.text() and not fs.expand(self.prefix.text()).is_dir():
            problem, widget = ("Wine prefix: that folder does not exist. Pick an existing prefix or leave it empty.", self.prefix)
        elif (err := fs.validate_directory(self.workdir.text())):
            problem, widget = f"Working directory: {err}", self.workdir
        elif self.meta["release_year"].text().strip() and not self.meta["release_year"].text().strip().isdigit():
            problem, widget = "Release year must be a number.", self.meta["release_year"]
        else:
            env = self._env_dict()
            bad = [n for n in env if not validate_env_name(n)]
            if bad:
                self.env_toggle.setChecked(True)
                problem, widget = (f"Invalid environment variable name: “{bad[0] or '(empty)'}”. "
                                   "Use letters, digits and underscores only.", self.env_table)
        if problem:
            self._show_error(problem)
            widget.setFocus()
            return

        a = Application() if self.original is None else Application(**{**self.original.__dict__})
        a.name = name
        a.executable_path = str(fs.expand(self.exe.text()))
        a.wine_prefix = str(fs.expand(self.prefix.text())) if self.prefix.text() else ""
        a.working_directory = str(fs.expand(self.workdir.text())) if self.workdir.text() else ""
        a.launch_arguments = self.args.text().strip()
        a.env_vars = env
        a.description = self.description.toPlainText().strip()
        a.category_id = self.category.currentData() if self.category.currentData() != "__new__" else None
        a.favorite = self.favorite.isChecked()
        for k, edit in self.meta.items():
            setattr(a, k, edit.text().strip())

        images = self.ctx.images
        try:
            old_cover, old_icon = a.cover_path, a.icon_path
            if self.cover.source is not None:
                a.cover_path = images.import_cover(self.cover.source)
            elif self.cover.cleared:
                a.cover_path = ""
            if self.icon.source is not None:
                a.icon_path = images.import_icon(self.icon.source)
            elif self.icon.image is not None:
                a.icon_path = images.import_icon(self.icon.image)
            elif self.icon.cleared:
                a.icon_path = ""
            elif not a.icon_path and not self.editing:
                auto = extract_exe_icon(a.executable_path)       # best effort, never required
                if auto is not None:
                    a.icon_path = images.import_icon(auto)
        except ImageError as exc:
            self._show_error(str(exc))
            return
        if old_cover and old_cover != a.cover_path:
            self.obsolete_artwork.append(("cover", old_cover))
        if old_icon and old_icon != a.icon_path:
            self.obsolete_artwork.append(("icon", old_icon))
        self.result_application = a
        super().accept()
