"""Friendly error dialog: plain-language message, likely causes, optional technical details."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from ...utils.logging import get_logger
from .. import icons
from ..widgets import fit_dialog, label, make_button

log = get_logger("ui")


class ErrorDialog(QDialog):
    def __init__(self, parent: QWidget | None, title: str, message: str,
                 causes: list[str] | tuple[str, ...] = (), details: str = ""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        screen = self.screen() or QGuiApplication.primaryScreen()
        available_width = screen.availableGeometry().width() if screen else 508
        self.setMinimumWidth(max(1, min(460, available_width - 48)))
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 18)
        root.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(14)
        ic = QLabel()
        ic.setPixmap(icons.pixmap("alert", "#f0616d", 34))
        ic.setAlignment(Qt.AlignTop)
        ic.setAccessibleName("Error")
        head.addWidget(ic)
        col = QVBoxLayout()
        col.setSpacing(6)
        t = label(title, "H2", wrap=True)
        col.addWidget(t)
        col.addWidget(label(message, wrap=True))
        head.addLayout(col, 1)
        root.addLayout(head)

        if causes:
            root.addWidget(label("Possible causes:", muted=True))
            root.addWidget(label("\n".join(f"•  {c}" for c in causes), wrap=True))

        self.details = QPlainTextEdit(details)
        self.details.setReadOnly(True)
        self.details.setMinimumHeight(110)
        self.details.setAccessibleName("Technical details")
        self.details.hide()
        root.addWidget(self.details)

        row = QHBoxLayout()
        self.details_btn = make_button("View Details")
        self.details_btn.setVisible(bool(details))
        self.details_btn.clicked.connect(self._toggle)
        ok = make_button("OK", "primary")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        row.addWidget(self.details_btn)
        row.addStretch(1)
        row.addWidget(ok)
        root.addLayout(row)
        fit_dialog(self, QSize(520, 420))
        ok.setFocus()

    def _toggle(self) -> None:
        show = not self.details.isVisible()
        self.details.setVisible(show)
        self.details_btn.setText("Hide Details" if show else "View Details")
        self.adjustSize()


def show_error(parent, title: str, message: str, causes=(), details: str = "") -> None:
    log.warning("%s: %s | %s", title, message, details.replace("\n", " | ")[:300])
    ErrorDialog(parent, title, message, causes, details).exec()
