"""Settings window. Every control applies immediately; there is no OK/Apply step."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QIcon
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QColorDialog, QComboBox, QDialog, QFileDialog,
                               QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLineEdit, QListWidget, QMessageBox,
                               QRadioButton, QScrollArea, QSizePolicy, QSlider, QStackedWidget, QVBoxLayout,
                               QWidget)

from ..branding import (APP_AUTHOR, APP_AUTHOR_BIO, APP_AUTHOR_LINKS, APP_AUTHOR_NAME, APP_AUTHOR_PASSIONS,
                        APP_AUTHOR_PROJECTS, APP_AUTHOR_ROLE, APP_AUTHOR_URL, APP_COPYRIGHT, APP_LICENSE, APP_NAME,
                        APP_TAGLINE, APP_VERSION)
from ..core.library import SORT_LABELS
from ..core.runners import discover_runners, is_proton_id
from ..core.wine_manager import detect_runner
from ..services.filesystem_service import open_in_file_manager
from ..services.image_service import ImageError
from ..utils.config import DEFAULTS, RANGES
from ..utils.platform import session_type
from .dialogs.error_dialog import show_error
from .widgets import IMAGE_FILTER, PathField, label, make_button

SECTIONS = ["General", "Customization", "Appearance", "Library", "Wine", "Advanced", "About"]
RATIOS = {"Poster (2:3)": 1.5, "Box art (3:4)": 4 / 3, "Square (1:1)": 1.0, "Wide (16:9)": 9 / 16}
INFO_H = 56


class SliderRow(QWidget):
    def __init__(self, settings, key: str, unit: str = "", zero_text: str | None = None):
        super().__init__()
        self.settings, self.key, self.unit, self.zero_text = settings, key, unit, zero_text
        lo, hi = RANGES[key]
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(lo, hi)
        self.slider.setAccessibleName(key.replace("_", " ").title())
        self.value_label = label()
        self.value_label.setMinimumWidth(56)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.value_label)
        self.sync()
        self.slider.valueChanged.connect(self._changed)

    def _text(self, v: int) -> str:
        return self.zero_text if (v == 0 and self.zero_text) else f"{v}{self.unit}"

    def _changed(self, v: int) -> None:
        self.value_label.setText(self._text(v))
        self.settings.set(self.key, v)

    def sync(self) -> None:
        v = self.settings[self.key]
        self.slider.blockSignals(True)
        self.slider.setValue(v)
        self.slider.blockSignals(False)
        self.value_label.setText(self._text(v))


class SettingsDialog(QDialog):
    def __init__(self, ctx, actions: dict, parent=None, page: str = "General"):
        super().__init__(parent)
        self.ctx, self.s, self.actions = ctx, ctx.settings, actions
        self.setWindowTitle("Settings")
        self.resize(780, 600)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.nav = QListWidget()
        self.nav.setObjectName("SettingsNav")
        self.nav.setFixedWidth(190)
        self.nav.setAccessibleName("Settings sections")
        self.nav.addItems(SECTIONS)
        root.addWidget(self.nav)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        builders = [self._general, self._customization, self._appearance, self._library, self._wine,
                    self._advanced, self._about]
        for name, build in zip(SECTIONS, builders):
            self.stack.addWidget(self._scrolled(name, build()))
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(SECTIONS.index(page))

    # -- scaffolding ----------------------------------------------------------------
    def _scrolled(self, title: str, content: QWidget) -> QScrollArea:
        holder = QWidget()
        lay = QVBoxLayout(holder)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)
        lay.addWidget(label(title, "Title"))
        lay.addWidget(content)
        lay.addStretch(1)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QScrollArea.NoFrame)
        sa.setWidget(holder)
        return sa

    def _check(self, text: str, key: str, tip: str = "") -> QCheckBox:
        c = QCheckBox(text)
        c.setChecked(self.s[key])
        c.toggled.connect(lambda v: self.s.set(key, v))
        if tip:
            c.setToolTip(tip)
        return c

    def _radios(self, key: str, options: list[tuple[str, str]]) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(18)
        grp = QButtonGroup(w)
        for value, text in options:
            r = QRadioButton(text)
            r.setChecked(self.s[key] == value)
            r.toggled.connect(lambda on, v=value: on and self.s.set(key, v))
            grp.addButton(r)
            lay.addWidget(r)
        lay.addStretch(1)
        w._group = grp
        return w

    @staticmethod
    def _form() -> tuple[QWidget, QFormLayout]:
        w = QWidget()
        f = QFormLayout(w)
        f.setContentsMargins(0, 0, 0, 0)
        f.setHorizontalSpacing(20)
        f.setVerticalSpacing(14)
        f.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        return w, f

    # -- pages -----------------------------------------------------------------------------
    def _general(self) -> QWidget:
        w, f = self._form()
        f.addRow("Removing", self._check("Ask before removing an application from the library", "confirm_remove"))
        f.addRow("Window", self._check("Remember window size and position", "restore_geometry"))
        f.addRow("", label("Removing only deletes the library entry and VineDeck’s copy of its artwork. "
                           "Your game files and Wine prefixes are never touched.", muted=True, wrap=True))
        return w

    def _customization(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(18)

        info = label("Everything here updates live, so you can tune the look and layout without leaving the settings window.",
                     muted=True, wrap=True)
        lay.addWidget(info)

        look = QGroupBox("Look & feel")
        look_lay = QVBoxLayout(look)
        look_lay.setContentsMargins(16, 12, 16, 12)
        look_lay.addWidget(self._appearance())
        lay.addWidget(look)

        library = QGroupBox("Library & card layout")
        library_lay = QVBoxLayout(library)
        library_lay.setContentsMargins(16, 12, 16, 12)
        library_lay.addWidget(self._library())
        lay.addWidget(library)
        return w

    def _appearance(self) -> QWidget:
        w, f = self._form()
        f.addRow("Theme", self._radios("theme", [("dark", "Dark"), ("light", "Light"), ("system", "System")]))
        self.accent_btn = make_button("")
        self.accent_btn.setAccessibleName("Accent colour")
        self.accent_btn.clicked.connect(self._pick_accent)
        reset = make_button("Reset", "ghost")
        reset.clicked.connect(lambda: (self.s.set("accent", DEFAULTS["accent"]), self._paint_accent()))
        row = QHBoxLayout()
        row.addWidget(self.accent_btn)
        row.addWidget(reset)
        row.addStretch(1)
        rw = QWidget()
        rw.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        f.addRow("Accent Color", rw)
        self._paint_accent()
        f.addRow("Background", self._radios("background_mode", [("default", "Default"), ("custom", "Custom Image")]))
        self.bg_label = label(Path(self.s["background_image"]).name or "No image chosen", muted=True)
        pick = make_button("Choose Image…")
        pick.clicked.connect(self._pick_background)
        brow = QHBoxLayout()
        brow.setContentsMargins(0, 0, 0, 0)
        brow.addWidget(pick)
        brow.addWidget(self.bg_label, 1)
        bw = QWidget()
        bw.setLayout(brow)
        f.addRow("", bw)
        f.addRow("Card Style", self._radios("card_style", [("rounded", "Rounded"), ("square", "Square")]))
        f.addRow("Animations", self._check("Enable hover lift and sidebar animation", "animations"))
        f.addRow("Blur Effects", self._check("Blur the custom background and the details backdrop", "blur"))
        f.addRow("", label("Blur is rendered in software and does not need a GPU. Without it, plain "
                           "backgrounds are used.", muted=True, wrap=True))
        return w

    def _paint_accent(self) -> None:
        c = self.s["accent"]
        fg = "#000" if QColor(c).lightness() > 140 else "#fff"
        self.accent_btn.setText(c.upper())
        self.accent_btn.setStyleSheet(f"background:{c}; color:{fg}; font-weight:700; min-width:96px;")

    def _pick_accent(self) -> None:
        c = QColorDialog.getColor(QColor(self.s["accent"]), self, "Accent colour")
        if c.isValid():
            self.s.set("accent", c.name())
            self._paint_accent()

    def _pick_background(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Background image", str(Path.home()), IMAGE_FILTER)
        if not path:
            return
        try:
            self.ctx.images.load(path)
        except ImageError as exc:
            show_error(self, "Unable to use this image", str(exc))
            return
        dest = self.ctx.paths.backgrounds_dir / f"{uuid.uuid4().hex}{Path(path).suffix.lower()}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
        old = self.s["background_image"]
        self.s.set("background_image", str(dest), save=False)
        self.s.set("background_mode", "custom")
        if old and Path(old).parent == dest.parent:
            Path(old).unlink(missing_ok=True)
        self.bg_label.setText(Path(path).name)

    def _library(self) -> QWidget:
        w, f = self._form()
        view = QComboBox()
        view.setMaxVisibleItems(10)
        for key, text in (("grid", "Grid"), ("compact", "Compact Grid"), ("list", "List"), ("large", "Large Cover")):
            view.addItem(text, key)
        view.setCurrentIndex(view.findData(self.s["view_mode"]))
        view.activated.connect(lambda i: self.s.set("view_mode", view.itemData(i)))
        f.addRow("Default View", view)
        sort = QComboBox()
        sort.setMaxVisibleItems(10)
        for key, text in SORT_LABELS.items():
            sort.addItem(text, key)
        sort.setCurrentIndex(sort.findData(self.s["sort_key"]))
        sort.activated.connect(lambda i: self.s.set("sort_key", sort.itemData(i)))
        f.addRow("Default Sort", sort)
        f.addRow("", self._check("Reverse the sort order", "sort_reverse"))

        g = QGroupBox("Card layout")
        gf = QFormLayout(g)
        gf.setVerticalSpacing(12)
        self.cols = SliderRow(self.s, "grid_columns", zero_text="Auto")
        self.cw = SliderRow(self.s, "card_width", " px")
        self.ch = SliderRow(self.s, "card_height", " px")
        gf.addRow("Columns", self.cols)
        gf.addRow("Card Width", self.cw)
        gf.addRow("Card Height", self.ch)
        ratio = QComboBox()
        ratio.setMaxVisibleItems(10)
        ratio.addItem("Choose a cover ratio…", None)
        for text, r in RATIOS.items():
            ratio.addItem(text, r)
        ratio.activated.connect(lambda i: ratio.itemData(i) and self._apply_ratio(ratio.itemData(i)))
        gf.addRow("Cover Ratio", ratio)
        gf.addRow("Horizontal Gap", SliderRow(self.s, "gap_h", " px"))
        gf.addRow("Vertical Gap", SliderRow(self.s, "gap_v", " px"))
        gf.addRow("Corner Radius", SliderRow(self.s, "corner_radius", " px"))
        gf.addRow("", label("Card width is used when Columns is Auto. With a fixed number of columns, "
                            "cards stretch to fill the window (and fewer columns are used if the window is narrow).",
                            muted=True, wrap=True))
        f.addRow(g)
        g2 = QGroupBox("Show on cards")
        v = QVBoxLayout(g2)
        for text, key in (("Title", "show_title"), ("Category", "show_category"), ("Favorite button", "show_favorite"),
                          ("Launch button", "show_launch"), ("Descriptions (Large Cover view)", "show_description")):
            v.addWidget(self._check(text, key))
        f.addRow(g2)
        return w

    def _apply_ratio(self, h_over_w: float) -> None:
        width = self.s["card_width"]
        self.s.set("card_height", round(width * h_over_w) + INFO_H)
        self.ch.sync()

    def _wine(self) -> QWidget:
        w, f = self._form()
        self.runner_box = QComboBox()
        self.runner_box.setAccessibleName("Runner")
        self.runner_box.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.runner_box.setMinimumContentsLength(28)
        self.runner_box.setMaxVisibleItems(10)
        rescan = make_button("Rescan", "ghost")
        rescan.setToolTip("Look for Steam and Proton installs again")
        rescan.clicked.connect(self._rescan_runners)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.runner_box, 1)
        row.addWidget(rescan)
        rw = QWidget()
        rw.setLayout(row)
        f.addRow("Runner", rw)
        self.runner_hint = label(muted=True, wrap=True)
        self.runner_hint.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        f.addRow("", self.runner_hint)
        self._fill_runners()
        self.runner_box.activated.connect(self._runner_chosen)

        self.wine_path = PathField("file", placeholder="wine", file_filter="All files (*)", title="Select Wine binary",
                                   accessible="Wine binary")
        self.wine_path.setText(self.s["wine_binary"])
        self.wine_path.textChanged.connect(lambda t: self.s.set("wine_binary", t.strip() or "wine"))
        f.addRow("Wine Binary", self.wine_path)
        self._sync_wine_field()
        self.wine_status = label(wrap=True)
        self.wine_status.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.wine_status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        det = make_button("Detect Runner")
        det.clicked.connect(self._detect)
        f.addRow("", det)
        f.addRow("Status", self.wine_status)
        self.def_prefix = PathField("dir", placeholder="Wine’s default (~/.wine)", title="Select default prefix",
                                    accessible="Default prefix for new applications")
        self.def_prefix.setText(self.s["default_prefix"])
        self.def_prefix.textChanged.connect(lambda t: self.s.set("default_prefix", t.strip()))
        f.addRow("Default Prefix", self.def_prefix)
        f.addRow("", label("Pre-filled when adding an application. Each application can use its own prefix. "
                           "With Proton, applications without a prefix get their own one inside VineDeck’s data folder.",
                           muted=True, wrap=True))
        self._detect()
        return w

    def _fill_runners(self) -> None:
        """Populate the runner list: System Wine plus every Proton build found on this machine."""
        runners = discover_runners()
        current = self.s["runner"]
        self.runner_box.blockSignals(True)
        self.runner_box.clear()
        for r in runners:
            self.runner_box.addItem(r.label if r.kind == "proton" else r.name, r.id)
            self.runner_box.setItemData(self.runner_box.count() - 1, r.path or r.source, Qt.ToolTipRole)
        if self.runner_box.findData(current) < 0:
            name = Path(current[len("proton:"):]).parent.name if is_proton_id(current) else current
            self.runner_box.addItem(f"{name} (not found)", current)
        self.runner_box.setCurrentIndex(self.runner_box.findData(current))
        self.runner_box.blockSignals(False)
        n = sum(1 for r in runners if r.kind == "proton")
        self.runner_hint.setText(
            f"{n} Proton build{'s' if n != 1 else ''} found in your Steam install(s)." if n else
            "No Proton builds found. Install Proton from Steam (Library → Tools) or put GE-Proton in "
            "~/.steam/root/compatibilitytools.d, then press Rescan.")

    def _sync_wine_field(self) -> None:
        self.wine_path.setEnabled(not is_proton_id(self.s["runner"]))

    def _rescan_runners(self) -> None:
        self._fill_runners()
        self._detect()

    def _runner_chosen(self, index: int) -> None:
        self.s.set("runner", self.runner_box.itemData(index))
        self._sync_wine_field()
        self._detect()

    def _detect(self) -> None:
        info = detect_runner(self.s["runner"], self.s["wine_binary"])
        self.ctx.wine.info = info
        self.actions["wine_changed"](info)
        if info.found and info.kind == "proton":          # the long path goes in the tooltip, not the status line
            self.wine_status.setText(f"✓ {info.version or 'Proton'}")
            self.wine_status.setToolTip(info.path or "")
        else:
            self.wine_status.setText(("✓ " if info.found else "✕ ") + info.summary)
            self.wine_status.setToolTip("")
        self.wine_status.setObjectName("" if info.found else "Error")
        self.wine_status.style().unpolish(self.wine_status)
        self.wine_status.style().polish(self.wine_status)

    def _advanced(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        for text, path in (("Open Data Folder", self.ctx.paths.data_dir), ("Open Config Folder", self.ctx.paths.config_dir),
                           ("Open Logs Folder", self.ctx.paths.logs_dir)):
            b = make_button(text)
            b.clicked.connect(lambda _=False, p=path: open_in_file_manager(p))
            lay.addWidget(b, 0, Qt.AlignLeft)
        g = QGroupBox("Backup")
        gl = QHBoxLayout(g)
        ex = make_button("Export Library…")
        ex.clicked.connect(self.actions["export"])
        im = make_button("Import Library…")
        im.clicked.connect(self.actions["import"])
        gl.addWidget(ex)
        gl.addWidget(im)
        gl.addStretch(1)
        lay.addWidget(g)
        lay.addWidget(label("Exports contain metadata only (names, paths, settings per application) and, optionally, "
                            "artwork. Game files are never copied.", muted=True, wrap=True))
        self.cache_label = label(muted=True)
        clear = make_button("Clear Thumbnail Cache")
        clear.clicked.connect(lambda: self.cache_label.setText(f"Removed {self.ctx.images.clear_thumbnail_cache()} cached files. "
                                                               "They are rebuilt on demand."))
        lay.addWidget(clear, 0, Qt.AlignLeft)
        lay.addWidget(self.cache_label)
        reset = make_button("Reset All Settings…", "danger")
        reset.clicked.connect(self._reset)
        lay.addWidget(reset, 0, Qt.AlignLeft)
        return w

    def _reset(self) -> None:
        if QMessageBox.question(self, "Reset settings", "Restore all settings to their defaults? "
                                "Your library is not affected.") == QMessageBox.Yes:
            keep = {k: self.s[k] for k in ("first_run_done",)}
            self.s.reset()
            for k, v in keep.items():
                self.s.set(k, v)
            self.accept()

    def _about(self) -> QWidget:
        pal = self.ctx.theme.palette
        accent = self.s["accent"]
        soft = QColor(accent)
        soft.setAlphaF(0.16)
        soft_rgba = f"rgba({soft.red()},{soft.green()},{soft.blue()},{soft.alphaF():.2f})"
        w = QWidget()
        w.setStyleSheet(f"""
            QFrame#AboutHero {{ border: 1px solid {pal.border}; border-radius: 16px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {soft_rgba}, stop:1 {pal.surface}); }}
            QFrame#AboutCard {{ border: 1px solid {pal.border}; border-radius: 14px; background: {pal.surface}; }}
            QFrame#AboutHero QLabel, QFrame#AboutCard QLabel {{ background: transparent; border: 0; }}
            QLabel#Avatar {{ background: {accent}; color: {pal.accent_text}; border: 0; border-radius: 32px;
                font-size: 26pt; font-weight: 700; }}
            QLabel#Chip {{ background: {soft_rgba}; color: {pal.text}; border: 1px solid {accent};
                border-radius: 11px; padding: 3px 12px; font-size: 9pt; font-weight: 600; }}
            QLabel#Kicker {{ color: {pal.muted}; font-size: 8pt; font-weight: 700; letter-spacing: 1px; }}
            QLabel#AboutName {{ font-size: 18pt; font-weight: 700; }}
            QLabel#AboutHandle {{ color: {pal.muted}; }}
            QFrame#Divider {{ background: {pal.border}; max-height: 1px; border: 0; }}
        """)
        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)

        def frame(name: str) -> tuple[QFrame, QVBoxLayout]:
            f = QFrame()
            f.setObjectName(name)
            v = QVBoxLayout(f)
            v.setContentsMargins(22, 20, 22, 20)
            v.setSpacing(10)
            return f, v

        def text(lb, selectable: bool = True):
            lb.setTextInteractionFlags(Qt.TextSelectableByMouse if selectable else Qt.NoTextInteraction)
            return lb

        # -- hero: the app ---------------------------------------------------------
        hero, hv = frame("AboutHero")
        top = QHBoxLayout()
        top.setSpacing(16)
        icon_path = Path(__file__).resolve().parent.parent / "resources" / "icons" / "vinedeck.svg"
        logo = label()
        logo.setFixedSize(64, 64)
        if icon_path.exists():
            logo.setPixmap(QIcon(str(icon_path)).pixmap(64, 64))
        top.addWidget(logo, 0, Qt.AlignTop)
        names = QVBoxLayout()
        names.setSpacing(2)
        names.addWidget(text(label(f"{APP_NAME}", "AboutName")))
        names.addWidget(text(label(f"Version {APP_VERSION}", muted=True)))
        top.addLayout(names, 1)
        hv.addLayout(top)
        hv.addWidget(text(label(APP_TAGLINE, wrap=True)))
        outer.addWidget(hero)

        # -- card: the author --------------------------------------------------------
        card, cv = frame("AboutCard")
        cv.addWidget(label("ABOUT THE CREATOR", "Kicker"))
        head = QHBoxLayout()
        head.setSpacing(16)
        avatar = label(APP_AUTHOR_NAME[:1].upper(), "Avatar")
        avatar.setFixedSize(64, 64)
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setAccessibleName(f"{APP_AUTHOR_NAME} avatar")
        head.addWidget(avatar, 0, Qt.AlignTop)
        who = QVBoxLayout()
        who.setSpacing(2)
        who.addWidget(text(label(APP_AUTHOR_NAME, "AboutName")))
        self.credit = label(f'<a href="{APP_AUTHOR_URL}" style="color:{accent}; text-decoration:none">'
                            f'@{APP_AUTHOR}</a>', "AboutHandle")
        self.credit.setTextFormat(Qt.RichText)
        self.credit.setOpenExternalLinks(True)
        self.credit.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.credit.setAccessibleName("Author")
        who.addWidget(self.credit)
        who.addWidget(text(label(APP_AUTHOR_ROLE, wrap=True, muted=True)))
        head.addLayout(who, 1)
        cv.addLayout(head)
        cv.addWidget(text(label(APP_AUTHOR_BIO, wrap=True)))

        chips = QHBoxLayout()
        chips.setSpacing(8)
        for passion in APP_AUTHOR_PASSIONS:
            chips.addWidget(label(passion, "Chip"))
        chips.addStretch(1)
        cv.addLayout(chips)

        div = QFrame()
        div.setObjectName("Divider")
        div.setFixedHeight(1)
        cv.addSpacing(4)
        cv.addWidget(div)
        cv.addSpacing(2)
        cv.addWidget(label("OTHER THINGS I'VE BUILT", "Kicker"))
        for name, url, blurb in APP_AUTHOR_PROJECTS:
            row = label(f'<a href="{url}" style="color:{accent}; text-decoration:none; font-weight:600">{name}</a>'
                        f'<br><span style="color:{pal.muted}">{blurb}</span>', wrap=True)
            row.setTextFormat(Qt.RichText)
            row.setOpenExternalLinks(True)
            row.setTextInteractionFlags(Qt.TextBrowserInteraction)
            cv.addWidget(row)

        links = QHBoxLayout()
        links.setSpacing(8)
        for name, url in APP_AUTHOR_LINKS:
            btn = make_button(name, "ghost", tooltip=f"Open {name} in your browser")
            btn.clicked.connect(lambda _=False, u=url: QDesktopServices.openUrl(QUrl(u)))
            links.addWidget(btn)
        links.addStretch(1)
        cv.addSpacing(6)
        cv.addLayout(links)
        outer.addWidget(card)

        # -- card: technical details -------------------------------------------------
        info, iv = frame("AboutCard")
        iv.addWidget(label("DETAILS", "Kicker"))
        iv.addWidget(text(label(f"License: {APP_LICENSE} (Apache License, Version 2.0)")))
        iv.addWidget(text(label(APP_COPYRIGHT)))
        iv.addWidget(text(label(f"Display server: {session_type()}")))
        pth = self.ctx.paths
        iv.addWidget(text(label(f"Config: {pth.config_dir}\nData: {pth.data_dir}\nCache: {pth.cache_dir}",
                                muted=True, wrap=True)))
        outer.addWidget(info)
        return w
