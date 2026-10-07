"""Small reusable widgets."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QCompleter, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QVBoxLayout, QWidget)

from . import icons

IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.webp *.PNG *.JPG *.JPEG *.WEBP)"
EXE_FILTER = "Windows programs (*.exe *.EXE *.lnk *.LNK);;All files (*)"


def make_button(text: str = "", variant: str | None = None, *, icon=None, big: bool = False,
                tooltip: str = "") -> QPushButton:
    b = QPushButton(text)
    if variant:
        b.setProperty("variant", variant)
    if big:
        b.setProperty("big", True)
    if icon is not None:
        b.setIcon(icon)
        b.setIconSize(QSize(18, 18))
    if tooltip:
        b.setToolTip(tooltip)
        b.setAccessibleName(tooltip)
    b.setCursor(Qt.PointingHandCursor)
    return b


def label(text: str = "", name: str | None = None, *, wrap: bool = False, muted: bool = False) -> QLabel:
    lb = QLabel(text)
    if name:
        lb.setObjectName(name)
    if muted:
        lb.setProperty("muted", True)
    lb.setWordWrap(wrap)
    return lb


class PathField(QWidget):
    """Line edit + Browse button for a file or folder path."""

    textChanged = Signal(str)

    def __init__(self, mode: str = "file", *, placeholder: str = "", file_filter: str = EXE_FILTER,
                 start_dir=lambda: "", title: str = "Select", accessible: str = "", parent=None):
        super().__init__(parent)
        self.mode, self._filter, self._start_dir, self._title = mode, file_filter, start_dir, title
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.setClearButtonEnabled(True)
        self.edit.setAccessibleName(accessible or title)
        self.button = make_button("Browse…", tooltip=f"Browse: {accessible or title}")
        self.button.clicked.connect(self._browse)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(self.edit, 1)
        lay.addWidget(self.button)
        self.edit.textChanged.connect(self.textChanged)
        self.setFocusProxy(self.edit)

    def text(self) -> str:
        return self.edit.text().strip()

    def setText(self, t: str) -> None:
        self.edit.setText(t)

    def set_suggestions(self, items: list[str]) -> None:
        comp = QCompleter(items, self.edit)
        comp.setCaseSensitivity(Qt.CaseInsensitive)
        comp.setFilterMode(Qt.MatchContains)
        self.edit.setCompleter(comp)

    def _browse(self) -> None:
        start = self.text() or self._start_dir() or str(Path.home())
        if self.mode == "dir":
            path = QFileDialog.getExistingDirectory(self, self._title, start)
        else:
            path, _ = QFileDialog.getOpenFileName(self, self._title, start, self._filter)
        if path:
            self.edit.setText(path)


class PreviewBox(QWidget):
    """Rounded, cover-fit image preview."""

    def __init__(self, size: QSize, placeholder: str, parent=None):
        super().__init__(parent)
        self._pm: QPixmap | None = None
        self._placeholder = placeholder
        self.setFixedSize(size)

    def set_pixmap(self, pm: QPixmap | None) -> None:
        self._pm = pm
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(r, 10, 10)
        pal = self.palette()
        if self._pm is not None and not self._pm.isNull():
            p.setClipPath(path)
            pm = self._pm
            scale = max(r.width() / pm.width(), r.height() / pm.height())
            sw, sh = r.width() / scale, r.height() / scale
            p.drawPixmap(r, pm, QRectF((pm.width() - sw) / 2, (pm.height() - sh) / 2, sw, sh))
        else:
            pen = QPen(pal.color(pal.ColorRole.PlaceholderText), 1.2, Qt.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
            p.setPen(pal.color(pal.ColorRole.PlaceholderText))
            p.drawText(self.rect(), Qt.AlignCenter | Qt.TextWordWrap, self._placeholder)


class ImagePicker(QWidget):
    """Choose / replace / remove one image; reports what changed."""

    changed = Signal()

    def __init__(self, title: str, size: QSize, placeholder: str, extra_buttons=(), parent=None):
        super().__init__(parent)
        self.source: Path | None = None        # newly chosen file
        self.image = None                      # newly provided PIL image (e.g. from an .exe)
        self.cleared = False
        self._title = title
        self.preview = PreviewBox(size, placeholder)
        self.select_btn = make_button("Select Image…", tooltip=f"Select {title.lower()} image")
        self.clear_btn = make_button("Remove", "ghost", tooltip=f"Remove {title.lower()}")
        self.select_btn.clicked.connect(self._choose)
        self.clear_btn.clicked.connect(self.clear)
        col = QVBoxLayout()
        col.setSpacing(8)
        col.addWidget(self.select_btn)
        for b in extra_buttons:
            col.addWidget(b)
        col.addWidget(self.clear_btn)
        col.addStretch(1)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        lay.addWidget(self.preview)
        lay.addLayout(col)
        lay.addStretch(1)
        self.setFocusProxy(self.select_btn)

    def set_existing(self, pm: QPixmap | None) -> None:
        self.preview.set_pixmap(pm)
        self.clear_btn.setEnabled(pm is not None)

    def _choose(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, f"Select {self._title}", str(Path.home()), IMAGE_FILTER)
        if path:
            pm = QPixmap(path)
            if pm.isNull():
                from .dialogs.error_dialog import show_error
                show_error(self, "Unable to use this image", "That file is not a valid image.",
                           ["The file is damaged", "The format is not PNG, JPG or WEBP"])
                return
            self.source, self.image, self.cleared = Path(path), None, False
            self.preview.set_pixmap(pm)
            self.clear_btn.setEnabled(True)
            self.changed.emit()

    def set_image(self, pil_image, pm: QPixmap) -> None:
        self.source, self.image, self.cleared = None, pil_image, False
        self.preview.set_pixmap(pm)
        self.clear_btn.setEnabled(True)
        self.changed.emit()

    def clear(self) -> None:
        self.source, self.image, self.cleared = None, None, True
        self.preview.set_pixmap(None)
        self.clear_btn.setEnabled(False)
        self.changed.emit()

    @property
    def dirty(self) -> bool:
        return self.cleared or self.source is not None or self.image is not None


class EmptyState(QWidget):
    action_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logo = QLabel()
        self.logo.setAlignment(Qt.AlignCenter)
        self.title = label(name="Title")
        self.title.setAlignment(Qt.AlignCenter)
        self.text = label(muted=True, wrap=True)
        self.text.setAlignment(Qt.AlignCenter)
        self.button = make_button("", "primary", big=True)
        self.button.clicked.connect(self.action_clicked)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(12)
        for w in (self.logo, self.title, self.text):
            lay.addWidget(w)
        lay.addSpacing(10)
        lay.addWidget(self.button, 0, Qt.AlignCenter)
        self.text.setMaximumWidth(460)

    def configure(self, *, title: str, text: str, button: str | None, logo: QPixmap | None = None,
                  icon: QPixmap | None = None) -> None:
        self.title.setText(title)
        self.text.setText(text)
        self.button.setVisible(bool(button))
        self.button.setText(button or "")
        pm = logo or icon
        self.logo.setVisible(pm is not None)
        if pm is not None:
            self.logo.setPixmap(pm)


class Toast(QLabel):
    """Transient message pinned to the bottom of its parent."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAccessibleName("Notification")
        self._timer = QTimer(self, singleShot=True)
        self._timer.timeout.connect(self.hide)
        parent.installEventFilter(self)
        self.hide()

    def show_message(self, text: str, ms: int = 3500) -> None:
        self.setText(text)
        self.adjustSize()
        self._place()
        self.show()
        self.raise_()
        self._timer.start(ms)

    def _place(self) -> None:
        p = self.parentWidget()
        self.setMaximumWidth(max(1, p.width() - 32))
        self.adjustSize()
        self.move(max(0, (p.width() - self.width()) // 2), max(0, p.height() - self.height() - 28))

    def eventFilter(self, obj, e):
        if e.type() == QEvent.Resize and self.isVisible():
            self._place()
        return False
