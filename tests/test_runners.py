import os
import stat

import pytest

from vinedeck.core import launcher
from vinedeck.core.launcher import LaunchError, build_launch_spec, proton_compat_location
from vinedeck.core.runners import (discover_proton, discover_runners, discover_steam_roots, library_folders,
                                   proton_id)
from vinedeck.core.wine_manager import WineInfo, WineManager, detect_proton, detect_runner
from vinedeck.database.models import Application
from vinedeck.utils.config import Settings


@pytest.fixture(autouse=True)
def not_root(monkeypatch):
    monkeypatch.setattr(launcher, "is_root", lambda: False)


def make_proton(d, version_line=None, display_name=None, executable=True):
    d.mkdir(parents=True, exist_ok=True)
    script = d / "proton"
    script.write_text("#!/usr/bin/env python3\n")
    script.chmod(script.stat().st_mode | (stat.S_IXUSR if executable else 0))
    if not executable:
        script.chmod(0o644)
    if version_line:
        (d / "version").write_text(version_line)
    if display_name:
        (d / "compatibilitytool.vdf").write_text(
            f'"compatibilitytools"\n{{\n "compat_tools"\n {{\n  "x"\n  {{\n   "display_name" "{display_name}"\n  }}\n }}\n}}\n')
    return script


@pytest.fixture
def steam(tmp_path):
    """A fake home with a Steam install, a second library drive and GE-Proton."""
    home = tmp_path / "home"
    root = home / ".local/share/Steam"
    (root / "steamapps/common").mkdir(parents=True)
    (home / ".steam").mkdir()
    (home / ".steam/steam").symlink_to(root)                      # like a real install: symlink to the same dir
    other = tmp_path / "SteamLibrary"
    (other / "steamapps/common").mkdir(parents=True)
    (root / "steamapps/libraryfolders.vdf").write_text(
        '"libraryfolders"\n{\n\t"0"\n\t{\n\t\t"path"\t\t"%s"\n\t}\n\t"1"\n\t{\n\t\t"path"\t\t"%s"\n\t}\n}\n'
        % (root, other))
    make_proton(root / "steamapps/common/Proton 9.0 (Beta)", "1700 proton-9.0-beta")
    make_proton(other / "steamapps/common/Proton - Experimental", "1800 proton-experimental")
    make_proton(root / "compatibilitytools.d/GE-Proton9-5", display_name="GE-Proton9-5")
    (root / "steamapps/common/Half-Life").mkdir()                  # a game, not a tool
    make_proton(root / "steamapps/common/Proton 7.0", executable=False)   # broken: not executable
    return home, root, other


def test_roots_are_deduplicated_through_symlinks(steam):
    home, root, _ = steam
    assert discover_steam_roots(home, {}) == [root.resolve()]


def test_library_folders_parsed(steam):
    home, root, other = steam
    assert library_folders(root) == [root, other]


def test_discovers_official_custom_and_other_drive(steam):
    home, root, other = steam
    names = [r.name for r in discover_proton(home, {})]
    assert sorted(names) == sorted(["Proton 9.0 (Beta)", "Proton - Experimental", "GE-Proton9-5"])
    runners = {r.name: r for r in discover_proton(home, {})}
    assert runners["Proton - Experimental"].source == "Steam"
    assert runners["GE-Proton9-5"].source == "Custom"
    assert all(r.steam_root == str(root.resolve()) for r in runners.values())
    assert all(r.id == proton_id(r.path) for r in runners.values())


def test_no_steam_means_only_system_wine(tmp_path):
    runners = discover_runners(tmp_path, {})
    assert [r.id for r in runners] == ["wine"]


def test_flatpak_steam_is_found(tmp_path):
    root = tmp_path / ".var/app/com.valvesoftware.Steam/.local/share/Steam"
    make_proton(root / "compatibilitytools.d/GE-Proton8-1")
    assert [r.name for r in discover_proton(tmp_path, {})] == ["GE-Proton8-1"]


def test_detect_proton(steam):
    home, root, _ = steam
    script = root / "steamapps/common/Proton 9.0 (Beta)/proton"
    info = detect_proton(str(script), home=home)
    assert info.found and info.kind == "proton" and info.version == "proton-9.0-beta"
    assert info.path == str(script) and info.steam_root == str(root.resolve())
    assert detect_proton(str(script.parent), home=home).found           # a folder is accepted too
    assert not detect_proton(str(root / "nope" / "proton")).found
    bad = detect_proton(str(root / "steamapps/common/Proton 7.0/proton"))
    assert not bad.found and "not executable" in bad.error
    assert detect_runner(proton_id(script)).kind == "proton"


def test_wine_manager_switches_runner(steam):
    home, root, _ = steam
    script = root / "compatibilitytools.d/GE-Proton9-5/proton"
    mgr = WineManager("definitely-not-wine-xyz")
    assert not mgr.refresh().found
    info = mgr.refresh(runner=proton_id(script))
    assert info.found and info.kind == "proton" and "Proton" in info.runner_label
    assert not mgr.refresh(runner="wine").found


def app_for(exe, **kw):
    return Application(id=7, name="G", executable_path=str(exe), **kw)


PROTON = WineInfo(True, "/steam/Proton/proton", "Proton 9", kind="proton", steam_root="/home/u/.steam/root")


def test_proton_spec_default_prefix(exe, tmp_path):
    root = tmp_path / "proton"
    spec = build_launch_spec(app_for(exe, launch_arguments="-windowed"), PROTON.path, base_env={"WINEPREFIX": "/x"},
                             runner=PROTON, proton_root=root)
    assert spec.argv == ["/steam/Proton/proton", "run", str(exe), "-windowed"]
    assert spec.env["STEAM_COMPAT_DATA_PATH"] == str(root / "app-7") and (root / "app-7").is_dir()
    assert spec.env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] == "/home/u/.steam/root"
    assert spec.env["STEAM_COMPAT_INSTALL_PATH"] == str(exe.parent)
    assert "WINEPREFIX" not in spec.env                    # Proton derives it itself
    assert spec.compat_data == str(root / "app-7")
    assert "STEAM_COMPAT_DATA_PATH=" in spec.describe()


def test_proton_lnk_goes_through_start(tmp_path):
    lnk = tmp_path / "T.lnk"
    lnk.write_bytes(b"L")
    spec = build_launch_spec(app_for(lnk), PROTON.path, base_env={}, runner=PROTON, proton_root=tmp_path / "p")
    assert spec.argv == ["/steam/Proton/proton", "run", "start", "/unix", str(lnk)]


def test_proton_compat_location_cases(exe, tmp_path):
    root = tmp_path / "proton"
    compat = tmp_path / "compatdata" / "123"
    (compat / "pfx").mkdir(parents=True)
    # 1) the compatdata folder itself, 2) its pfx folder -> both use the compatdata folder directly
    assert proton_compat_location(app_for(exe, wine_prefix=str(compat)), root) == (compat, None)
    assert proton_compat_location(app_for(exe, wine_prefix=str(compat / "pfx")), root) == (compat, None)
    # 3) plain Wine prefix -> linked through a pfx symlink in VineDeck's own folder
    plain = tmp_path / "wineprefix"
    plain.mkdir()
    where, target = proton_compat_location(app_for(exe, wine_prefix=str(plain)), root)
    assert where.parent == root / "linked" and target == plain


def test_proton_plain_prefix_is_symlinked_not_modified(exe, tmp_path):
    plain = tmp_path / "wineprefix"
    plain.mkdir()
    root = tmp_path / "proton"
    spec = build_launch_spec(app_for(exe, wine_prefix=str(plain)), PROTON.path, base_env={}, runner=PROTON,
                             proton_root=root)
    link = os.path.join(spec.env["STEAM_COMPAT_DATA_PATH"], "pfx")
    assert os.path.islink(link) and os.path.realpath(link) == str(plain.resolve())
    assert list(plain.iterdir()) == []                      # the user's prefix gets nothing added
    build_launch_spec(app_for(exe, wine_prefix=str(plain)), PROTON.path, base_env={}, runner=PROTON,
                      proton_root=root)                     # idempotent


def test_proton_requires_an_existing_explicit_prefix_and_valid_runner(exe, tmp_path):
    with pytest.raises(LaunchError) as e:
        build_launch_spec(app_for(exe, wine_prefix="/definitely/missing"), PROTON.path, base_env={},
                          runner=PROTON, proton_root=tmp_path)
    assert "prefix" in e.value.message.lower()
    with pytest.raises(LaunchError) as e:
        build_launch_spec(app_for(exe), None, base_env={}, runner=PROTON, proton_root=tmp_path)
    assert "Proton could not be started" in e.value.message


def test_user_env_vars_still_apply_with_proton(exe, tmp_path):
    spec = build_launch_spec(app_for(exe, env_vars={"PROTON_LOG": "1"}), PROTON.path, base_env={}, runner=PROTON,
                             proton_root=tmp_path)
    assert spec.env["PROTON_LOG"] == "1" and "PROTON_LOG" in spec.env_overrides


def test_runner_setting_validation(tmp_path):
    s = Settings(tmp_path / "c.json")
    assert s["runner"] == "wine"
    s.set("runner", "proton:/a/b/proton")
    assert Settings(tmp_path / "c.json")["runner"] == "proton:/a/b/proton"
    s.set("runner", "bogus")
    assert s["runner"] == "wine"                            # falls back to the default
    s.set("runner", "proton:")
    assert s["runner"] == "wine"
