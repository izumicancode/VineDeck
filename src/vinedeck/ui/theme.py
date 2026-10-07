"""Colour palettes and the application-wide stylesheet."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

from ..utils.config import Settings
from . import icons


@dataclass(frozen=True)
class Palette:
    dark: bool
    bg: str
    surface: str
    surface2: str
    border: str
    text: str
    muted: str
    accent: str
    accent_text: str
    danger: str
    warn: str

    def q(self, name: str) -> QColor:
        return QColor(getattr(self, name))


def _luma(c: QColor) -> float:
    return 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()


def resolve_dark(theme: str) -> bool:
    if theme == "dark":
        return True
    if theme == "light":
        return False
    hints = QGuiApplication.styleHints()
    try:
        return hints.colorScheme() != Qt.ColorScheme.Light
    except AttributeError:                # very old Qt
        return True


def make_palette(theme: str, accent: str) -> Palette:
    dark = resolve_dark(theme)
    on_accent = "#0b0c10" if _luma(QColor(accent)) > 150 else "#ffffff"
    if dark:
        return Palette(True, "#121317", "#1a1c22", "#23262e", "#2e323c", "#eceef3", "#9aa1b2",
                       accent, on_accent, "#f0616d", "#f2b84b")
    return Palette(False, "#f3f4f7", "#ffffff", "#eceef3", "#d9dce4", "#1b1d25", "#5b6272",
                   accent, on_accent, "#d6384a", "#b97a05")


def _write_assets(p: Palette, cache: Path) -> dict[str, str]:
    cache.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, color in (("check", p.accent_text), ("chevron-down", p.muted)):
        f = cache / f"{name}-{color.lstrip('#')}.svg"
        if not f.exists():
            f.write_text(icons.svg_markup(name, color, 2.4), encoding="utf-8")
        out[name] = f.as_posix()
    return out


def stylesheet(p: Palette, *, square: bool, assets: dict[str, str]) -> str:
    r = 0 if square else 8
    rl = 0 if square else 12
    return f"""
* {{ outline: 0; }}
QWidget {{ color: {p.text}; font-size: 10pt; }}
QMainWindow, QDialog {{ background: {p.bg}; }}
QToolTip {{ background: {p.surface2}; color: {p.text}; border: 1px solid {p.border}; padding: 5px 8px; border-radius: {r}px; }}
QLabel {{ background: transparent; }}
QLabel#Title {{ font-size: 22pt; font-weight: 700; }}
QLabel#H2 {{ font-size: 13pt; font-weight: 650; }}
QLabel#Muted, QLabel[muted="true"] {{ color: {p.muted}; }}
QLabel#Section {{ color: {p.muted}; font-size: 8pt; font-weight: 700; letter-spacing: 1px; padding: 14px 12px 4px 12px; }}
QLabel#Error {{ color: {p.danger}; }}
QLabel#Pill {{ background: {p.surface2}; border: 1px solid {p.border}; border-radius: 10px; padding: 2px 10px; font-size: 9pt; }}

#TopBar, #Sidebar {{ background: {p.surface}; }}
#TopBar {{ border-bottom: 1px solid {p.border}; }}
#Sidebar {{ border-right: 1px solid {p.border}; }}
#Panel {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: {rl}px; }}
#Banner {{ background: {p.surface2}; border: 1px solid {p.warn}; border-radius: {r}px; }}
#Toast {{ background: {p.surface2}; border: 1px solid {p.border}; border-radius: {r + 4}px; padding: 10px 18px; }}
#ListHeader {{ border-bottom: 1px solid {p.border}; }}
#ListHeader QLabel {{ color: {p.muted}; font-size: 8pt; font-weight: 700; letter-spacing: 1px; }}

QPushButton {{ background: {p.surface2}; border: 1px solid {p.border}; border-radius: {r}px; padding: 7px 16px; }}
QPushButton:hover {{ border-color: {p.muted}; }}
QPushButton:pressed {{ background: {p.border}; }}
QPushButton:focus {{ border: 2px solid {p.accent}; padding: 6px 15px; }}
QPushButton:disabled {{ color: {p.muted}; background: {p.surface}; }}
QPushButton[variant="primary"] {{ background: {p.accent}; color: {p.accent_text}; border: 1px solid {p.accent}; font-weight: 650; }}
QPushButton[variant="primary"]:hover {{ background: {QColor(p.accent).lighter(112).name()}; }}
QPushButton[variant="primary"]:focus {{ border: 2px solid {p.text}; padding: 6px 15px; }}
QPushButton[variant="ghost"] {{ background: transparent; border: 1px solid transparent; }}
QPushButton[variant="ghost"]:hover {{ background: {p.surface2}; }}
QPushButton[variant="ghost"]:focus {{ border: 2px solid {p.accent}; }}
QPushButton[variant="danger"] {{ color: {p.danger}; }}
QPushButton[big="true"] {{ padding: 12px 34px; font-size: 12pt; border-radius: {r + 2}px; }}

QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: {r}px; padding: 6px; }}
QToolButton:hover {{ background: {p.surface2}; }}
QToolButton:checked {{ background: {p.surface2}; border: 1px solid {p.border}; }}
QToolButton:focus {{ border: 2px solid {p.accent}; }}

QPushButton#Nav {{ background: transparent; border: 1px solid transparent; text-align: left; padding: 9px 12px; border-radius: {r}px; }}
QPushButton#Nav:hover {{ background: {p.surface2}; }}
QPushButton#Nav:checked {{ background: {p.surface2}; border-left: 3px solid {p.accent}; font-weight: 650; }}
QPushButton#Nav:focus {{ border: 2px solid {p.accent}; }}

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox, QTableWidget {{
    background: {p.surface}; border: 1px solid {p.border}; border-radius: {r}px; padding: 7px 10px;
    selection-background-color: {p.accent}; selection-color: {p.accent_text}; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus {{ border: 2px solid {p.accent}; padding: 6px 9px; }}
QLineEdit#Search {{ border-radius: {18 if not square else 0}px; padding: 7px 14px; background: {p.bg}; }}
QComboBox::drop-down {{ border: 0; width: 26px; }}
QComboBox::down-arrow {{ image: url({assets['chevron-down']}); width: 14px; height: 14px; }}
QComboBox QAbstractItemView {{ background: {p.surface2}; border: 1px solid {p.border}; selection-background-color: {p.accent};
    selection-color: {p.accent_text}; padding: 4px; outline: 0; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: 0; }}
QTableWidget {{ gridline-color: {p.border}; padding: 0; }}
QHeaderView::section {{ background: {p.surface2}; color: {p.muted}; border: 0; padding: 6px 10px; font-weight: 600; }}

QCheckBox, QRadioButton {{ spacing: 10px; padding: 3px 0; background: transparent; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border: 2px solid {p.muted}; border-radius: 5px; background: transparent; }}
QCheckBox::indicator:checked {{ background: {p.accent}; border-color: {p.accent}; image: url({assets['check']}); }}
QCheckBox::indicator:focus, QRadioButton::indicator:focus {{ border-color: {p.accent}; }}
QRadioButton::indicator {{ width: 14px; height: 14px; border: 2px solid {p.muted}; border-radius: 9px; background: transparent; }}
QRadioButton::indicator:checked {{ border-color: {p.accent};
    background: qradialgradient(cx:.5, cy:.5, radius:.5, fx:.5, fy:.5, stop:0 {p.accent}, stop:.55 {p.accent}, stop:.6 transparent, stop:1 transparent); }}

QSlider::groove:horizontal {{ height: 4px; background: {p.border}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {p.accent}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; background: {p.text}; }}
QSlider::handle:horizontal:focus {{ border: 2px solid {p.accent}; }}

QMenu {{ background: {p.surface2}; border: 1px solid {p.border}; border-radius: {r + 2}px; padding: 6px; }}
QMenu::item {{ padding: 7px 28px 7px 14px; border-radius: {max(r - 2, 0)}px; }}
QMenu::item:selected {{ background: {p.accent}; color: {p.accent_text}; }}
QMenu::item:disabled {{ color: {p.muted}; }}
QMenu::separator {{ height: 1px; background: {p.border}; margin: 5px 8px; }}

QListWidget#SettingsNav {{ background: {p.surface}; border: 0; border-right: 1px solid {p.border}; padding: 8px; }}
QListWidget#SettingsNav::item {{ padding: 9px 12px; border-radius: {r}px; }}
QListWidget#SettingsNav::item:selected {{ background: {p.surface2}; color: {p.text}; border-left: 3px solid {p.accent}; }}
QListWidget#SettingsNav:focus {{ border-right: 1px solid {p.accent}; }}

QListView {{ background: transparent; border: 0; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: 0; }}
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p.border}; border-radius: 4px; min-height: 36px; margin: 0 2px; }}
QScrollBar::handle:vertical:hover {{ background: {p.muted}; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {p.border}; border-radius: 4px; min-width: 36px; margin: 2px 0; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QGroupBox {{ border: 1px solid {p.border}; border-radius: {rl}px; margin-top: 14px; padding: 16px 12px 10px 12px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 14px; padding: 0 6px; color: {p.muted}; font-weight: 650; }}
QMessageBox {{ background: {p.bg}; }}
"""


class ThemeManager(QObject):
    changed = Signal()

    def __init__(self, settings: Settings, theme_cache: Path):
        super().__init__()
        self.settings = settings
        self._cache = theme_cache
        self.palette = make_palette(settings["theme"], settings["accent"])
        settings.subscribe(self._on_setting)
        scheme_changed = getattr(QGuiApplication.styleHints(), "colorSchemeChanged", None)
        if scheme_changed is not None:
            scheme_changed.connect(self._system_scheme_changed)

    def _on_setting(self, key: str, _value) -> None:
        if key in ("theme", "accent", "card_style"):
            self.apply()

    def _system_scheme_changed(self, _scheme) -> None:
        if self.settings["theme"] == "system":
            self.apply()

    @property
    def square(self) -> bool:
        return self.settings["card_style"] == "square"

    def apply(self) -> None:
        app = QApplication.instance()
        self.palette = p = make_palette(self.settings["theme"], self.settings["accent"])
        app.setStyle("Fusion")
        font = QFont(app.font())
        font.setFamilies(["Inter", "Noto Sans", "Cantarell", "DejaVu Sans"])
        font.setPointSize(10)
        app.setFont(font)
        qp = QPalette()
        for role, name in ((QPalette.Window, "bg"), (QPalette.Base, "surface"), (QPalette.AlternateBase, "surface2"),
                           (QPalette.Button, "surface2"), (QPalette.Text, "text"), (QPalette.WindowText, "text"),
                           (QPalette.ButtonText, "text"), (QPalette.ToolTipBase, "surface2"),
                           (QPalette.ToolTipText, "text"), (QPalette.Highlight, "accent"),
                           (QPalette.HighlightedText, "accent_text"), (QPalette.PlaceholderText, "muted")):
            qp.setColor(role, p.q(name))
        qp.setColor(QPalette.Disabled, QPalette.Text, p.q("muted"))
        qp.setColor(QPalette.Disabled, QPalette.ButtonText, p.q("muted"))
        app.setPalette(qp)
        app.setStyleSheet(stylesheet(p, square=self.square, assets=_write_assets(p, self._cache)))
        self.changed.emit()

    # convenience for widgets
    def icon(self, name: str, color: str | None = None, size: int = 20) -> "icons.QIcon":
        return icons.icon(name, color or self.palette.text, size, disabled_color=self.palette.muted)
