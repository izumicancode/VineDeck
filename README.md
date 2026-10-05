# VineDeck

VineDeck is a modern launcher for Windows games and apps on Linux. It keeps your Wine and Proton setups organized, gives each app its own launch settings, and presents everything in a clean, polished library.

## Features

- Add `.exe` and `.lnk` apps with per-app prefixes, arguments, environment variables, and working folders
- Switch between Wine and Proton with automatic runner detection
- Browse in grid, compact, list, or large-cover layouts
- Search, favorites, categories, and launch state tracking
- Customize the theme, accent color, card layout, and background
- Export or import your library with optional artwork

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
python -m vinedeck
```

## Requirements

- Linux
- Wine, or Steam + Proton
- Python 3.11+

## Installation

### Local development

```bash
python -m vinedeck --version
python -m vinedeck --help
pytest -q
```

If you are not using the project venv, `python -m vinedeck` can fail with `No module named vinedeck`. Activate `.venv` first or use:

```bash
PYTHONPATH=src python -m vinedeck
```

### Arch package / app image

VineDeck ships with an Arch PKGBUILD and an x86_64 AppImage. See the packaging section in the project docs for build and install steps.

## Data locations

- Config: `~/.config/vinedeck/config.json`
- Data: `~/.local/share/vinedeck/`
- Cache: `~/.cache/vinedeck/`

You can override these with `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, and `XDG_CACHE_HOME` when testing a clean profile.

## Troubleshooting

- Run VineDeck as a normal user; it does not launch apps as root.
- If a Proton build is missing, install it in Steam and choose **Settings → Wine → Runner → Rescan**.
- If imports fail or thumbnails look stale, clear `~/.cache/vinedeck/` and relaunch.
- If `No module named vinedeck` appears, activate the project venv or set `PYTHONPATH=src`.

## License

VineDeck is licensed under the [Apache License 2.0](LICENSE). See `NOTICE` for attribution.

Created by [izumicancode](https://github.com/izumicancode).
