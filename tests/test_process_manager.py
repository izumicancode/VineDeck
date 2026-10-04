from vinedeck.core.launcher import LaunchError, LaunchSpec
from vinedeck.core.process_manager import LaunchState, ProcessManager


class FakeProc:
    def __init__(self, rc=0, delay=0.0, alive=True):
        self._rc, self._delay, self._alive = rc, delay, alive
        import threading
        self.done = threading.Event()
        if delay == 0:
            self.done.set()

    def wait(self):
        self.done.wait(5)
        return self._rc

    def poll(self):
        return None if not self.done.is_set() else self._rc


def spec(app_id=1):
    return LaunchSpec(app_id, "Game", ["wine", "/x.exe"], {"A": "b"}, "/tmp")


def pump(qapp, cond, timeout=3000):
    from PySide6.QtCore import QEventLoop, QTimer
    loop = QEventLoop()
    t = QTimer()
    t.timeout.connect(lambda: cond() and loop.quit())
    t.start(10)
    QTimer.singleShot(timeout, loop.quit)
    loop.exec()


def test_states_closed(qapp, tmp_path):
    calls = {}

    def fake_popen(argv, **kw):
        calls.update(argv=argv, **kw)
        return FakeProc(rc=0, delay=1)

    pm = ProcessManager(tmp_path, popen=fake_popen, running_delay_ms=30)
    states = []
    pm.state_changed.connect(lambda i, s, d: states.append(s))
    proc_holder = {}
    pm.launch(spec())
    assert calls["argv"] == ["wine", "/x.exe"] and calls["shell"] is False and calls["start_new_session"] is True
    assert states == [LaunchState.LAUNCHING.value] and pm.is_active(1)
    pump(qapp, lambda: LaunchState.RUNNING.value in states)
    assert LaunchState.RUNNING.value in states
    # finish the fake process
    pm._popen  # noqa
    import gc
    for obj in gc.get_objects():
        if isinstance(obj, FakeProc):
            obj.done.set()
    pump(qapp, lambda: states[-1] == LaunchState.CLOSED.value)
    assert states[-1] == LaunchState.CLOSED.value and not pm.is_active(1)


def test_quick_nonzero_exit_is_failure(qapp, tmp_path):
    pm = ProcessManager(tmp_path, popen=lambda *a, **k: FakeProc(rc=1), running_delay_ms=5000)
    states = []
    pm.state_changed.connect(lambda i, s, d: states.append((s, d)))
    pm.launch(spec())
    pump(qapp, lambda: states and states[-1][0] == LaunchState.FAILED.value)
    assert states[-1][0] == LaunchState.FAILED.value and "code 1" in states[-1][1]


def test_oserror_becomes_launcherror(qapp, tmp_path):
    def boom(*a, **k):
        raise FileNotFoundError(2, "No such file")
    pm = ProcessManager(tmp_path, popen=boom)
    try:
        pm.launch(spec())
        assert False, "expected LaunchError"
    except LaunchError as e:
        assert "Wine could not be started" in e.message and e.causes and e.details
    assert not pm.is_active(1)


def test_double_launch_rejected(qapp, tmp_path):
    pm = ProcessManager(tmp_path, popen=lambda *a, **k: FakeProc(delay=1), running_delay_ms=5000)
    pm.launch(spec())
    try:
        pm.launch(spec())
        assert False
    except LaunchError:
        pass
    for obj in __import__("gc").get_objects():
        if isinstance(obj, FakeProc):
            obj.done.set()
