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


def test_settings_batch_update_and_defaults(tmp_path):
    s = Settings.from_file(tmp_path / "config.json")
    s.update({"theme": "light", "card_width": 220, "accent": "#00ff00"})
    assert s.get("theme") == "light"
    assert s.get("card_width") == 220
    assert s.get("accent") == "#00ff00"
    assert s.get("missing_key", "fallback") == "fallback"
    assert "theme" in s
    assert "missing_key" not in s
    assert s.copy()["theme"] == "light"
    assert "theme" in s.keys()
    assert s.items()[0][0] in s


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


def test_blank_xdg_values_fall_back_to_defaults(tmp_path):
    p = AppPaths.from_env({"XDG_CONFIG_HOME": "", "XDG_DATA_HOME": "   ", "XDG_CACHE_HOME": None})
    assert p.config_dir == Path.home() / ".config" / "vinedeck"
    assert p.data_dir == Path.home() / ".local/share" / "vinedeck"
    assert p.cache_dir == Path.home() / ".cache" / "vinedeck"
    assert not p.has_custom_xdg()
    assert tuple(p) == (p.config_dir, p.data_dir, p.cache_dir)


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


def test_help_flag_prints_usage(capsys):
    from vinedeck.main import main
    assert main(["vinedeck", "--help"]) == 0
    out = capsys.readouterr().out
    assert "Usage:" in out
    assert "--version" in out
    assert "--help" in out


def test_validate_key_rejects_unknown_setting_names():
    from vinedeck.utils.config import validate_key
    assert validate_key("theme") == "theme"
    try:
        validate_key("not_a_real_key")
    except KeyError:
        pass
    else:
        raise AssertionError("Unknown setting key should raise KeyError")
