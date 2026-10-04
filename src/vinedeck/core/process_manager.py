"""Runs Wine/Proton processes without blocking the UI.

Processes are started in their own session and are never killed by the launcher,
so closing the launcher leaves running games untouched.
"""

from __future__ import annotations

import subprocess
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QTimer, Signal

from ..utils.logging import get_logger
from .launcher import LaunchError, LaunchSpec

log = get_logger("process")

QUICK_FAIL_SECONDS = 5.0


class LaunchState(str, Enum):
    LAUNCHING = "Launching…"
    RUNNING = "Running"
    CLOSED = "Closed"
    FAILED = "Failed"


class ProcessManager(QObject):
    state_changed = Signal(int, str, str)      # app_id, LaunchState value, detail
    exited = Signal(int, int)                  # app_id, return code
    _thread_done = Signal(int, int, float)     # internal: app_id, rc, elapsed

    def __init__(self, logs_dir: Path, *, popen: Callable = subprocess.Popen,
                 running_delay_ms: int = 1500, parent: QObject | None = None):
        super().__init__(parent)
        self._logs_dir = logs_dir
        self._popen = popen
        self._delay = running_delay_ms
        self._active: dict[int, LaunchState] = {}
        self._thread_done.connect(self._on_thread_done)

    def state(self, app_id: int) -> LaunchState | None:
        return self._active.get(app_id)

    def is_active(self, app_id: int) -> bool:
        return app_id in self._active

    def launch_log_path(self, app_id: int) -> Path:
        return self._logs_dir / f"launch-{app_id}.log"

    def launch(self, spec: LaunchSpec) -> None:
        app_id = spec.app_id if spec.app_id is not None else -1
        if app_id in self._active:
            raise LaunchError(f"“{spec.name}” is already running.")
        self._logs_dir.mkdir(parents=True, exist_ok=True)
        log.info("Launching %s: %s", spec.name, spec.describe())
        try:
            with open(self.launch_log_path(app_id), "wb") as out:
                proc = self._popen(
                    spec.argv, env=spec.env, cwd=spec.cwd,
                    stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                    start_new_session=True, shell=False)
        except OSError as exc:
            log.error("Launch of %s failed: %s", spec.name, exc)
            raise LaunchError(
                "Wine could not be started.",
                ["Wine is not installed", "The Wine executable is invalid",
                 "The executable or working directory cannot be accessed"],
                f"{type(exc).__name__}: {exc}") from exc

        self._set(app_id, LaunchState.LAUNCHING)
        QTimer.singleShot(self._delay, lambda: self._maybe_running(app_id, proc))
        threading.Thread(target=self._wait, args=(app_id, proc, time.monotonic()),
                         name=f"wait-{app_id}", daemon=True).start()

    # -- internals -----------------------------------------------------------
    def _set(self, app_id: int, state: LaunchState, detail: str = "") -> None:
        if state in (LaunchState.CLOSED, LaunchState.FAILED):
            self._active.pop(app_id, None)
        else:
            self._active[app_id] = state
        self.state_changed.emit(app_id, state.value, detail)

    def _maybe_running(self, app_id: int, proc) -> None:
        if self._active.get(app_id) == LaunchState.LAUNCHING and proc.poll() is None:
            self._set(app_id, LaunchState.RUNNING)

    def _wait(self, app_id: int, proc, started: float) -> None:
        rc = proc.wait()
        self._thread_done.emit(app_id, rc, time.monotonic() - started)

    def _on_thread_done(self, app_id: int, rc: int, elapsed: float) -> None:
        log.info("Process for app %s exited with code %s after %.1fs", app_id, rc, elapsed)
        self.exited.emit(app_id, rc)
        if rc != 0 and elapsed < QUICK_FAIL_SECONDS:
            self._set(app_id, LaunchState.FAILED, f"Exited immediately with code {rc}")
        else:
            self._set(app_id, LaunchState.CLOSED)


class WineProbe(QObject):
    """Runs Wine detection off the UI thread so startup never waits on it."""

    finished = Signal(object)          # WineInfo

    def start(self, binary: str, runner: str = "wine") -> None:
        from .wine_manager import detect_runner
        threading.Thread(target=lambda: self.finished.emit(detect_runner(runner, binary)),
                         name="wine-probe", daemon=True).start()
