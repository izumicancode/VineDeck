import subprocess
from types import SimpleNamespace

import pytest

from vinedeck.core import launcher
from vinedeck.core.launcher import LaunchError, build_launch_spec
from vinedeck.core.wine_manager import detect_wine
from vinedeck.database.models import Application


@pytest.fixture(autouse=True)
def not_root(monkeypatch):
    monkeypatch.setattr(launcher, "is_root", lambda: False)


def app_for(exe, **kw):
    return Application(id=1, name="G", executable_path=str(exe), **kw)


def test_basic_command_uses_argument_array(exe):
    spec = build_launch_spec(app_for(exe), "/usr/bin/wine", base_env={"PATH": "/bin"})
    assert spec.argv == ["/usr/bin/wine", str(exe)]
    assert spec.cwd == str(exe.parent)                 # defaults to the exe folder
    assert "WINEPREFIX" not in spec.env


def test_prefix_args_env_and_cwd(exe, tmp_path):
    prefix = tmp_path / "pfx"
    prefix.mkdir()
    wd = tmp_path / "wd"
    wd.mkdir()
    a = app_for(exe, wine_prefix=str(prefix), working_directory=str(wd),
                launch_arguments='--fullscreen "my file.txt" -windowed',
                env_vars={"WINEDEBUG": "-all", "DXVK_HUD": ""})
    spec = build_launch_spec(a, "/usr/bin/wine", base_env={"HOME": "/h"})
    assert spec.argv == ["/usr/bin/wine", str(exe), "--fullscreen", "my file.txt", "-windowed"]
    assert spec.env["WINEPREFIX"] == str(prefix)
    assert spec.env["WINEDEBUG"] == "-all" and spec.env["DXVK_HUD"] == ""
    assert spec.cwd == str(wd)
    assert "-all" not in spec.describe()              # values are never logged
    assert "WINEDEBUG" in spec.describe()


def test_arguments_are_not_shell_interpreted(exe):
    spec = build_launch_spec(app_for(exe, launch_arguments="; rm -rf ~ $(whoami) `id`"), "wine", base_env={})
    assert spec.argv[2:] == [";", "rm", "-rf", "~", "$(whoami)", "`id`"]   # inert literal args


def test_lnk_uses_wine_start(tmp_path):
    lnk = tmp_path / "Thing.lnk"
    lnk.write_bytes(b"L")
    spec = build_launch_spec(app_for(lnk), "wine", base_env={})
    assert spec.argv == ["wine", "start", "/unix", str(lnk)]


@pytest.mark.parametrize("kw, text", [
    ({"wine_prefix": "/definitely/missing"}, "prefix"),
    ({"working_directory": "/definitely/missing"}, "working directory"),
    ({"launch_arguments": "'unterminated"}, "arguments"),
    ({"env_vars": {"BAD NAME": "1"}}, "environment variable"),
])
def test_validation_errors(exe, kw, text):
    with pytest.raises(LaunchError) as e:
        build_launch_spec(app_for(exe, **kw), "wine", base_env={})
    assert text in e.value.message.lower()


def test_missing_executable_and_wine(tmp_path, exe):
    with pytest.raises(LaunchError) as e:
        build_launch_spec(app_for(tmp_path / "gone.exe"), "wine", base_env={})
    assert "executable" in e.value.message.lower() and e.value.causes
    with pytest.raises(LaunchError):
        build_launch_spec(app_for(exe), None, base_env={})


def test_refuses_root(exe, monkeypatch):
    monkeypatch.setattr(launcher, "is_root", lambda: True)
    with pytest.raises(LaunchError):
        build_launch_spec(app_for(exe), "wine", base_env={})


def test_detect_wine_found_and_missing():
    ok = lambda *a, **k: SimpleNamespace(returncode=0, stdout="wine-9.0\n", stderr="")      # noqa: E731
    info = detect_wine("wine", runner=ok, which=lambda b: "/usr/bin/wine")
    assert info.found and info.version == "wine-9.0" and info.path == "/usr/bin/wine"
    assert not detect_wine("wine", which=lambda b: None).found
    bad = lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="boom")           # noqa: E731
    assert not detect_wine("wine", runner=bad, which=lambda b: "/w").found

    def timeout(*a, **k):
        raise subprocess.TimeoutExpired("wine", 1)
    assert not detect_wine("wine", runner=timeout, which=lambda b: "/w").found
