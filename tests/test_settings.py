import json

from vinedeck.utils.config import DEFAULTS, Settings
from vinedeck.utils.paths import AppPaths


def test_defaults_roundtrip(tmp_path):
    f = tmp_path / "c" / "config.json"
    s = Settings(f)
    assert s.get("theme") == "dark"
    s.set("accent", "#ff0000")
    s.set("card_width", 250)
    assert Settings(f).get("accent") == "#ff0000"
    assert Settings(f).get("card_width") == 250


def test_invalid_values_fall_back(tmp_path):
    f = tmp_path / "config.json"
    f.write_text(json.dumps({"theme": "neon", "card_width": "wide", "gap_h": 9999,
                             "accent": "red", "animations": "yes"}))
    s = Settings(f)
    assert s.get("theme") == DEFAULTS["theme"]
    assert s.get("card_width") == DEFAULTS["card_width"]
    assert s.get("gap_h") == 60                         # clamped
    assert s.get("accent") == DEFAULTS["accent"]
    assert s.get("animations") is True


def test_corrupt_file_uses_defaults(tmp_path):
    f = tmp_path / "config.json"
    f.write_text("{{{")
    assert Settings(f).get("view_mode") == "grid"


def test_listener_only_fires_on_change(tmp_path):
    s = Settings(tmp_path / "c.json")
    seen = []
    s.subscribe(lambda k, v: seen.append((k, v)))
    s.set("theme", "light")
    s.set("theme", "light")
    assert seen == [("theme", "light")]


def test_xdg_paths_respected_and_relative_ignored(tmp_path):
    p = AppPaths.from_env({"XDG_CONFIG_HOME": str(tmp_path / "cfg"), "XDG_DATA_HOME": "relative/path"})
    assert p.config_dir == tmp_path / "cfg" / "vinedeck"
    assert ".local/share" in str(p.data_dir)
    p2 = AppPaths.under(tmp_path)
    p2.ensure()
    assert p2.logs_dir.is_dir() and p2.thumbs_dir.is_dir() and p2.covers_dir.is_dir()


def test_license_and_credit():
    from pathlib import Path
    from vinedeck import branding
    root = Path(__file__).resolve().parent.parent
    assert branding.APP_LICENSE == "Apache-2.0" and branding.APP_AUTHOR_URL == "https://github.com/izumicancode"
    assert "Apache License" in (root / "LICENSE").read_text() and "Version 2.0, January 2004" in (root / "LICENSE").read_text()
    assert "izumicancode" in (root / "NOTICE").read_text()


def test_version_flag_needs_no_display(capsys):
    from vinedeck.branding import APP_NAME, APP_VERSION
    from vinedeck.main import main
    assert main(["vinedeck", "--version"]) == 0
    assert capsys.readouterr().out.strip() == f"{APP_NAME} {APP_VERSION}"
