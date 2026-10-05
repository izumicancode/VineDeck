"""Rotating file logging."""

from __future__ import annotations

import logging as _logging
import logging.handlers
from pathlib import Path

from ..branding import APP_SLUG

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging(logs_dir: Path, *, debug: bool = False, console: bool = True,
                  file_name: str | None = None) -> _logging.Logger:
    """Create a VineDeck logger sized for long-lived desktop sessions."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger = _logging.getLogger(APP_SLUG)
    logger.setLevel(_logging.DEBUG if debug else _logging.INFO)
    for h in list(logger.handlers):          # idempotent
        logger.removeHandler(h)
        h.close()
    log_file = logs_dir / (file_name or f"{APP_SLUG}.log")
    fh = logging.handlers.RotatingFileHandler(log_file, maxBytes=512_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(_logging.Formatter(_FORMAT))
    logger.addHandler(fh)
    if console:
        sh = _logging.StreamHandler()
        sh.setFormatter(_logging.Formatter(_FORMAT))
        logger.addHandler(sh)
    logger.propagate = False
    return logger


def get_logger(name: str) -> _logging.Logger:
    """Return a nested logger for a specific module."""
    return _logging.getLogger(f"{APP_SLUG}.{name}")
