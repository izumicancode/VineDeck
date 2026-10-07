"""Read-only text viewer (used for 'View Configuration')."""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtWidgets import QDialog, QHBoxLayout, QPlainTextEdit, QVBoxLayout

from ..widgets import fit_dialog, make_button


class TextDialog(QDialog):
    def __init__(self, parent, title: str, text: str):
        super().__init__(parent)
        self.setWindowTitle(title)
        fit_dialog(self, QSize(640, 420))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 16)
        self.view = QPlainTextEdit(text)
        self.view.setReadOnly(True)
        self.view.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.view.setAccessibleName(title)
        lay.addWidget(self.view, 1)
        row = QHBoxLayout()
        copy = make_button("Copy")
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(text))
        close = make_button("Close", "primary")
        close.clicked.connect(self.accept)
        row.addWidget(copy)
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)
