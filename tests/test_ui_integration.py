"""Drives the real main window (offscreen) through the main user journeys."""
import os
import stat
import time

import pytest
from PIL import Image
from PySide6.QtCore import Qt, QEventLoop, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtWidgets import QScrollArea

from vinedeck.app_context import AppContext
from vinedeck.core import launcher
from vinedeck.database.models import Application
from vinedeck.ui import main_window as mw_mod
from vinedeck.ui.application_dialog import ApplicationDialog
from vinedeck.ui.library_model import MIME
from vinedeck.ui.widgets import Toast, _fit_dialog_size
from vinedeck.utils.paths import AppPaths


@pytest.fixture(autouse=True)
def not_root(monkeypatch):
    monkeypatch.setattr(launcher, "is_root", lambda: False)


@pytest.fixture
def errors(monkeypatch):
    seen = []
    monkeypatch.setattr(mw_mod, "show_error", lambda parent, title, msg, causes=(), details="": seen.append((title, msg, causes, details)))
    return seen


@pytest.fixture
def fake_wine(tmp_path):
    script = tmp_path / "bin" / "wine"
    script.parent.mkdir()
    out = tmp_path / "wine-calls.txt"
    script.write_text(f"""#!/bin/sh
if [ "$1" = "--version" ]; then echo wine-9.0-fake; exit 0; fi
echo "prefix=$WINEPREFIX dbg=$WINEDEBUG cwd=$PWD args=$*" >> {out}
sleep 0.4
exit 0
""")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script, out


def make_ctx(root, qapp):
    ctx = AppContext.create(AppPaths.under(root))
    ctx.theme.apply()
    return ctx


def pump(cond, ms=4000):
    loop = QEventLoop()
    t = QTimer()
    t.timeout.connect(lambda: cond() and loop.quit())
    t.start(15)
    QTimer.singleShot(ms, loop.quit)
    loop.exec()
    t.stop()


@pytest.fixture
def env(tmp_path, qapp, fake_wine):
    ctx = make_ctx(tmp_path / "state", qapp)
    ctx.settings.set("wine_binary", str(fake_wine[0]))
    ctx.wine.refresh(str(fake_wine[0]))
    win = mw_mod.MainWindow(ctx)
    win.show()
    qapp.processEvents()
    exe = tmp_path / "Game.exe"
    exe.write_bytes(b"MZ")
    cover = tmp_path / "cover.png"
    Image.new("RGB", (400, 600), (50, 120, 200)).save(cover)
    yield win, ctx, exe, cover
    win.close()
    ctx.close()


def add_via_dialog(win, ctx, exe, cover, name="My Game", **extra):
    dlg = ApplicationDialog(ctx, win)
    dlg.exe.setText(str(exe))
    dlg.name.setText(name)                       # also exercises name auto-fill not overriding
    dlg.cover.source = cover
    dlg.cover.cleared = False
    for k, v in extra.items():
        getattr(dlg, k).setText(v)
    dlg.accept()
    assert dlg.result_application is not None
    return ctx.db.add_application(dlg.result_application)


def test_first_run_welcome_then_add_edit_search_favorite_filter(env):
    win, ctx, exe, cover = env
    assert win.holder_layout.currentWidget() is win.empty and "Welcome" in win.empty.title.text()
    app = add_via_dialog(win, ctx, exe, cover, prefix="")
    win.reload()
    assert win.holder_layout.currentWidget() is win.view and win.model.rowCount() == 1
    # cover stored in the data dir, original untouched, thumbnail renders
    assert ctx.images.cover_file(app.cover_path) and cover.exists()
    assert not ctx.artwork.cover(app).isNull()

    # edit
    dlg = ApplicationDialog(ctx, win, app)
    assert dlg.name.text() == "My Game"
    dlg.name.setText("Renamed")
    dlg.category.setCurrentIndex(dlg.category.findText("Games"))
    dlg.args.setText("-windowed")
    dlg.accept()
    ctx.db.update_application(dlg.result_application)
    win.reload()
    assert win.model.app_at(0).name == "Renamed" and win.model.app_at(0).category_name == "Games"

    # search (as-you-type) + no-results state
    QTest.keyClicks(win.search, "rena")
    assert win.model.rowCount() == 1
    win.search.setText("zzz")
    assert win.model.rowCount() == 0 and "No matches" in win.empty.title.text()
    win.search.clear()

    # favorite + sidebar filters
    win.toggle_favorite(app.id)
    win._section_selected("favorites", None)
    assert win.model.rowCount() == 1
    win._section_selected("category", ctx.db.get_category_by_name("Tools").id)
    assert win.model.rowCount() == 0
    win._section_selected("category", ctx.db.get_category_by_name("Games").id)
    assert win.model.rowCount() == 1


def test_validation_blocks_bad_input(env, tmp_path):
    win, ctx, exe, cover = env
    dlg = ApplicationDialog(ctx, win)
    assert not dlg.cover.clear_btn.isEnabled() and not dlg.icon.clear_btn.isEnabled()
    assert dlg.cover.preview.accessibleName() == "Cover preview"
    assert dlg.icon.preview.accessibleName() == "Icon preview"
    dlg.cover.set_image(Image.new("RGB", (2, 2)), QPixmap(2, 2))
    assert dlg.cover.clear_btn.isEnabled()
    dlg.accept()
    assert dlg.result_application is None and "name" in dlg.error.text().lower()
    dlg.name.setText("X")
    dlg.exe.setText(str(tmp_path / "missing.exe"))
    dlg.accept()
    assert dlg.result_application is None and "exist" in dlg.error.text()
    dlg.exe.setText(str(exe))
    dlg.prefix.setText(str(tmp_path / "no-prefix"))
    dlg.accept()
    assert dlg.result_application is None and "prefix" in dlg.error.text().lower()
    dlg.prefix.setText("")
    dlg.cover.source = tmp_path / "nope.png"
    dlg.accept()
    assert dlg.result_application is None            # invalid image reported, not raised


def test_launch_through_wine_with_prefix_env_and_state(env, tmp_path, errors):
    win, ctx, exe, cover = env
    prefix = tmp_path / "pfx"
    prefix.mkdir()
    app = ctx.db.add_application(Application(name="G", executable_path=str(exe), wine_prefix=str(prefix),
                                             launch_arguments="-windowed", env_vars={"WINEDEBUG": "-all"}))
    win.reload()
    states = []
    ctx.processes.state_changed.connect(lambda i, s, d: states.append(s))
    win.launch(app.id)
    assert not errors
    pump(lambda: "Closed" in states)
    assert states[0].startswith("Launching") and states[-1] == "Closed"
    calls = (tmp_path / "wine-calls.txt").read_text()
    assert f"prefix={prefix}" in calls and "dbg=-all" in calls and f"args={exe} -windowed" in calls
    assert f"cwd={exe.parent}" in calls
    got = ctx.db.get_application(app.id)
    assert got.launch_count == 1 and got.last_played
    pump(lambda: ctx.db.launch_history(app.id)[0]["exit_code"] == 0, 1000)
    assert ctx.db.launch_history(app.id)[0]["exit_code"] == 0


def test_invalid_executable_is_graceful(env, tmp_path, errors):
    win, ctx, exe, cover = env
    app = ctx.db.add_application(Application(name="Gone", executable_path=str(tmp_path / "deleted.exe")))
    win.reload()
    win.launch(app.id)
    assert errors and errors[0][0] == "Unable to launch application" and "executable" in errors[0][1].lower()
    assert ctx.db.get_application(app.id).launch_count == 0     # failed launch is not counted


def test_missing_wine_is_graceful(tmp_path, qapp, errors, exe_file=None):
    ctx = make_ctx(tmp_path / "s", qapp)
    ctx.settings.set("wine_binary", "definitely-not-wine-xyz")
    win = mw_mod.MainWindow(ctx)
    win.show()
    pump(lambda: win._banner_frame.isVisible(), 2000)
    assert win._banner_frame.isVisible()                        # library still opens, with a warning
    exe = tmp_path / "a.exe"
    exe.write_bytes(b"MZ")
    app = ctx.db.add_application(Application(name="A", executable_path=str(exe)))
    win.reload()
    win.launch(app.id)
    assert errors and "Wine could not be started" in errors[0][1]
    win.close()
    ctx.close()


def test_persistence_across_restart(tmp_path, qapp):
    root = tmp_path / "state"
    ctx = make_ctx(root, qapp)
    exe = tmp_path / "g.exe"
    exe.write_bytes(b"MZ")
    cov = tmp_path / "c.png"
    Image.new("RGB", (100, 150), "red").save(cov)
    win = mw_mod.MainWindow(ctx)
    add = add_via_dialog(win, ctx, exe, cov, name="Persist")
    ctx.db.set_favorite(add.id, True)
    ctx.settings.set("view_mode", "list")
    win.close()
    ctx.close()
    ctx2 = make_ctx(root, qapp)
    win2 = mw_mod.MainWindow(ctx2)
    assert win2.model.rowCount() == 1 and win2.model.app_at(0).favorite
    assert win2.s["view_mode"] == "list" and win2.view_btns["list"].isChecked()
    assert ctx2.paths.db_path.exists() and ctx2.paths.config_file.exists()
    assert "Welcome" not in win2.empty.title.text()
    win2.close()
    ctx2.close()


def test_remove_does_not_touch_files_and_view_modes(env, errors):
    win, ctx, exe, cover = env
    app = add_via_dialog(win, ctx, exe, cover)
    win.reload()
    for mode in ("grid", "compact", "list", "large"):
        ctx.settings.set("view_mode", mode)
        win.view.resize(900, 600)
        win.grab()                                              # paints every mode without error
    ctx.settings.set("confirm_remove", False)
    win.remove_application(app.id)
    assert exe.exists() and ctx.db.count_applications() == 0
    assert ctx.images.cover_file(app.cover_path) is None        # only VineDeck's own copy is removed


def test_responsive_columns_and_drag_reorder(env):
    win, ctx, exe, cover = env
    apps = [ctx.db.add_application(Application(name=n, executable_path=str(exe))) for n in "ABCD"]
    win.reload()
    win.view.resize(1300, 600)
    wide = win.view.columns()
    win.view.resize(500, 600)
    narrow = win.view.columns()
    assert wide > narrow >= 1
    ctx.settings.set("sort_key", "custom")
    assert win.view.dragDropMode().name == "DragDrop"
    from PySide6.QtCore import QMimeData, Qt
    data = QMimeData()
    data.setData(MIME, str(apps[0].id).encode())
    assert win.model.dropMimeData(data, Qt.CopyAction, -1, -1, win.model.index(2))
    assert [a.name for a in win.model._apps] == ["B", "C", "A", "D"]
    ctx.settings.set("sort_key", "name")
    assert win.view.dragDropMode().name == "NoDragDrop"


def test_sidebar_collapse_and_custom_grid_applies_immediately(env):
    win, ctx, exe, cover = env
    win.toggle_sidebar()
    assert ctx.settings["sidebar_collapsed"] is True
    assert win.sidebar.settings_btn.text() == ""
    assert win.sidebar.settings_btn.accessibleName() == "Settings"
    for i in range(30):
        ctx.db.add_application(Application(name=f"App {i}", executable_path=str(exe)))
    win.reload()
    win.view.resize(1000, 600)
    ctx.settings.set("grid_columns", 3)
    assert win.view.columns() == 3
    ctx.settings.set("grid_columns", 0)
    ctx.settings.set("card_width", 300)
    assert win.view.delegate.cell.width() >= 300


def test_long_category_name_is_available_as_tooltip(env):
    win, ctx, _exe, _cover = env
    name = "A very long category name that does not fit in the sidebar"
    category = ctx.db.add_category(name)
    win.reload()
    assert win.sidebar._cat_buttons[category.id].toolTip() == name


def test_library_favorite_can_be_toggled_from_keyboard(env):
    win, ctx, exe, _cover = env
    application = ctx.db.add_application(Application(name="Keyboard Favorite", executable_path=str(exe)))
    win.reload()
    win.view.setFocus()
    win.view.setCurrentIndex(win.model.index(0))
    QTest.keyClick(win.view, Qt.Key_F)
    assert ctx.db.get_application(application.id).favorite
    assert "F to toggle favorite" in win.view.accessibleDescription()


def test_list_mode_accessibility_exposes_columns_and_last_played(env):
    win, ctx, exe, _cover = env
    application = ctx.db.add_application(Application(name="Accessible List", executable_path=str(exe),
                                                     last_played="2024-01-15T00:00:00+00:00"))
    win.reload()
    item_text = win.model.data(win.model.index(0), Qt.AccessibleTextRole)
    assert "Last played:" in item_text and application.name in item_text
    assert win.list_header.accessibleDescription() == "Name, Category, Last Played"


def test_topbar_controls_fit_at_minimum_window_width(env):
    win, _ctx, _exe, _cover = env
    win.runner_combo.addItem("A long Proton runner label", "proton:test")
    win.runner_combo.setCurrentIndex(win.runner_combo.count() - 1)
    win.runner_combo.show()
    win.resize(760, 600)
    QApplication.processEvents()
    controls = [win.menu_btn, win.brand, win.search, *win.view_btns.values(),
                win.runner_combo, win.sort_combo, win.rev_btn, win.settings_btn]
    visible = sorted((control for control in controls if control.isVisible()), key=lambda control: control.x())
    assert all(left.x() + left.width() <= right.x() for left, right in zip(visible, visible[1:]))
    assert win.settings_btn.x() + win.settings_btn.width() <= win.menu_btn.parentWidget().width()


def test_details_hero_fits_at_minimum_window_width(env):
    win, ctx, exe, _cover = env
    app = ctx.db.add_application(Application(name="Narrow Details", executable_path=str(exe)))
    win.resize(760, 600)
    win.show()
    win.open_details(app.id)
    QApplication.processEvents()
    scroll = win.details.findChild(QScrollArea)
    assert win.details.cover.width() == 150
    assert scroll.horizontalScrollBar().maximum() == 0


def test_long_toast_stays_inside_parent(qapp):
    parent = QWidget()
    parent.resize(320, 240)
    toast = Toast(parent)
    toast.show_message("LongApplicationName" * 20)
    qapp.processEvents()
    assert toast.x() >= 0
    assert toast.x() + toast.width() <= parent.width()
    assert toast.y() >= 0
    assert toast.y() + toast.height() <= parent.height()


def test_long_toast_stays_inside_short_parent(qapp):
    parent = QWidget()
    parent.resize(320, 80)
    toast = Toast(parent)
    toast.show_message("LongApplicationName" * 40)
    qapp.processEvents()
    assert toast.x() >= 0 and toast.x() + toast.width() <= parent.width()
    assert toast.y() >= 0 and toast.y() + toast.height() <= parent.height()


def test_dialog_size_respects_small_screen():
    from PySide6.QtCore import QSize

    assert _fit_dialog_size(QSize(640, 760), QSize(500, 400)) == QSize(452, 352)


def test_configuration_viewer_fits_available_screen(qapp):
    from vinedeck.ui.dialogs.text_dialog import TextDialog

    dialog = TextDialog(None, "Configuration", "Configuration details")
    available = dialog.screen().availableGeometry().size()
    assert dialog.width() <= available.width() - 48
    assert dialog.height() <= available.height() - 48


def test_error_dialog_minimum_width_respects_screen(qapp):
    from vinedeck.ui.dialogs.error_dialog import ErrorDialog

    dialog = ErrorDialog(None, "Launch failed", "The application could not start.")
    assert dialog.minimumWidth() <= dialog.screen().availableGeometry().width() - 48


def test_system_theme_reacts_to_platform_color_scheme(env, monkeypatch):
    _win, ctx, _exe, _cover = env
    ctx.settings.set("theme", "system")
    applied = []
    monkeypatch.setattr(ctx.theme, "apply", lambda: applied.append(True))
    ctx.theme._system_scheme_changed(None)
    assert applied == [True]
    ctx.settings.set("theme", "dark")
    applied.clear()
    ctx.theme._system_scheme_changed(None)
    assert not applied


def _fake_proton_home(tmp_path, monkeypatch):
    """A throw-away HOME containing a Steam install with one fake Proton build that records its calls."""
    home = tmp_path / "home"
    root = home / ".local/share/Steam"
    d = root / "compatibilitytools.d" / "Fake-Proton"
    d.mkdir(parents=True)
    out = tmp_path / "proton-calls.txt"
    script = d / "proton"
    script.write_text(f"""#!/bin/sh
echo "verb=$1 data=$STEAM_COMPAT_DATA_PATH client=$STEAM_COMPAT_CLIENT_INSTALL_PATH wineprefix=$WINEPREFIX args=$*" >> {out}
sleep 0.4
exit 0
""")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    (root / "steamapps").mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    return script, out, root


def test_switch_runner_from_top_bar_and_launch_with_proton(tmp_path, qapp, monkeypatch, errors, fake_wine):
    script, out, root = _fake_proton_home(tmp_path, monkeypatch)
    ctx = make_ctx(tmp_path / "state", qapp)
    ctx.settings.set("wine_binary", str(fake_wine[0]))
    win = mw_mod.MainWindow(ctx)
    win.show()
    qapp.processEvents()
    try:
        assert not win.runner_combo.isHidden()                     # Proton exists, so the switcher is shown
        ids = [win.runner_combo.itemData(i) for i in range(win.runner_combo.count())]
        assert ids[0] == "wine" and f"proton:{script}" in ids
        exe = tmp_path / "Game.exe"
        exe.write_bytes(b"MZ")
        app = ctx.db.add_application(Application(name="G", executable_path=str(exe), launch_arguments="-x"))
        win.reload()

        # switch to Proton exactly as a click on the combo box would
        win.runner_combo.setCurrentIndex(ids.index(f"proton:{script}"))
        win.runner_combo.activated.emit(win.runner_combo.currentIndex())
        assert ctx.settings["runner"] == f"proton:{script}" and ctx.wine.runner == f"proton:{script}"
        pump(lambda: ctx.wine.info.found and ctx.wine.info.kind == "proton" or False, 1500)
        states = []
        ctx.processes.state_changed.connect(lambda i, s, d: states.append(s))
        win.launch(app.id)
        assert not errors
        pump(lambda: "Closed" in states)
        calls = out.read_text()
        data = ctx.paths.proton_dir / f"app-{app.id}"
        assert "verb=run" in calls and f"data={data}" in calls and f"client={root.resolve()}" in calls
        assert f"args=run {exe} -x" in calls and "wineprefix= " in calls
        assert not (tmp_path / "wine-calls.txt").exists()          # system Wine was not used

        # and back to system Wine
        win.runner_combo.setCurrentIndex(0)
        win.runner_combo.activated.emit(0)
        assert ctx.settings["runner"] == "wine"
        pump(lambda: ctx.wine.info.kind == "wine" and ctx.wine.info.found, 1500)
        win.launch(app.id)
        pump(lambda: (tmp_path / "wine-calls.txt").exists(), 2000)
        assert (tmp_path / "wine-calls.txt").exists()
    finally:
        win.close()
        ctx.close()


def test_runner_switcher_hidden_without_proton(tmp_path, qapp, monkeypatch, fake_wine):
    monkeypatch.setenv("HOME", str(tmp_path / "empty-home"))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    ctx = make_ctx(tmp_path / "state", qapp)
    win = mw_mod.MainWindow(ctx)
    win.show()
    qapp.processEvents()
    try:
        assert win.runner_combo.isHidden()
    finally:
        win.close()
        ctx.close()


def test_missing_proton_selection_is_graceful(tmp_path, qapp, monkeypatch, errors):
    monkeypatch.setenv("HOME", str(tmp_path / "empty-home"))
    ctx = make_ctx(tmp_path / "state", qapp)
    ctx.settings.set("runner", "proton:/gone/Proton/proton")
    win = mw_mod.MainWindow(ctx)
    win.show()
    pump(lambda: win._banner_frame.isVisible(), 2000)
    try:
        assert win._banner_frame.isVisible() and "Proton" in win.banner_text.text()
        assert not win.runner_combo.isHidden()                     # still shown so the user can switch away
        exe = tmp_path / "a.exe"
        exe.write_bytes(b"MZ")
        app = ctx.db.add_application(Application(name="A", executable_path=str(exe)))
        win.reload()
        win.launch(app.id)
        assert errors and "Proton could not be started" in errors[0][1]
    finally:
        win.close()
        ctx.close()


def test_settings_dialog_runner_picker(tmp_path, qapp, monkeypatch, fake_wine):
    from vinedeck.ui.settings_dialog import SettingsDialog
    script, out, root = _fake_proton_home(tmp_path, monkeypatch)
    ctx = make_ctx(tmp_path / "state", qapp)
    ctx.settings.set("wine_binary", str(fake_wine[0]))
    seen = []
    dlg = SettingsDialog(ctx, {"wine_changed": seen.append, "export": lambda: None, "import": lambda: None},
                         None, "Wine")
    try:
        assert dlg.width() <= dlg.screen().availableGeometry().width() - 48
        box = dlg.runner_box
        ids = [box.itemData(i) for i in range(box.count())]
        assert ids == ["wine", f"proton:{script}"] and box.currentData() == "wine"
        assert dlg.wine_path.isEnabled() and "wine-9.0-fake" in dlg.wine_status.text()

        box.setCurrentIndex(1)
        box.activated.emit(1)
        assert ctx.settings["runner"] == f"proton:{script}"
        assert not dlg.wine_path.isEnabled()                       # the binary field only matters for system Wine
        assert "Fake-Proton" in dlg.wine_status.text() and dlg.wine_status.text().startswith("✓")
        assert seen[-1].kind == "proton"

        script.unlink()                                           # build uninstalled behind our back
        dlg._rescan_runners()
        assert "(not found)" in box.currentText() and dlg.wine_status.text().startswith("✕")
    finally:
        dlg.close()
        ctx.close()


@pytest.mark.parametrize("page", ["General", "About"])
def test_escape_closes_settings_dialog_from_any_section(tmp_path, qapp, page):
    from vinedeck.ui.settings_dialog import SettingsDialog

    ctx = make_ctx(tmp_path / "state", qapp)
    dlg = SettingsDialog(ctx, {"wine_changed": lambda *_: None, "export": lambda: None,
                               "import": lambda: None}, None, page)
    try:
        dlg.show()
        qapp.processEvents()
        QTest.keyClick(dlg.nav, Qt.Key_Escape)
        qapp.processEvents()
        assert not dlg.isVisible()
    finally:
        dlg.close()
        ctx.close()
