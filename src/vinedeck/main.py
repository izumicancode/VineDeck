"""Application entry point."""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .branding import APP_DESKTOP_ID, APP_NAME, APP_VERSION
from .utils.logging import get_logger, setup_logging
from .utils.paths import AppPaths
from .utils.platform import is_root


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    if "--version" in argv[1:]:                       # handled before Qt starts, so it works without a display
        print(f"{APP_NAME} {APP_VERSION}")
        return 0
    if "--help" in argv[1:] or "-h" in argv[1:]:
        print(f"Usage: {APP_NAME} [--version] [--debug] [--help]")
        print("Run VineDeck as a desktop app. Use --version to print the release number.")
        return 0
    paths = AppPaths.from_env()
    paths.ensure()
    setup_logging(paths.logs_dir, debug="--debug" in argv)
    log = get_logger("main")

    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setDesktopFileName(APP_DESKTOP_ID)          # Wayland app-id / taskbar matching
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "resources" / "icons" / "vinedeck.svg")))

    from .app_context import AppContext
    from .ui.dialogs.error_dialog import ErrorDialog
    from .ui.main_window import MainWindow

    def excepthook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        log.error("Unhandled exception:\n%s", text)
        try:
            ErrorDialog(None, "Something went wrong", "An unexpected error occurred. The details have been "
                        "written to the log file.", [], text).exec()
        except Exception:
            pass

    sys.excepthook = excepthook
    if is_root():
        log.warning("Running as root: launching applications is disabled.")

    try:
        ctx = AppContext.create(paths)
    except Exception as exc:                          # e.g. a database from a newer version
        log.exception("Startup failed")
        ErrorDialog(None, f"{APP_NAME} could not start", str(exc), ["The database is damaged or from a newer version",
                    "The data folder is not writable"], traceback.format_exc()).exec()
        return 1
    ctx.theme.apply()
    win = MainWindow(ctx)
    win.show()
    code = app.exec()
    ctx.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
