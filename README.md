# VineDeck

A modern, customisable library and launcher for Windows applications and games that run through **Wine**. VineDeck includes an Arch Linux package recipe and a portable x86_64 AppImage for other Linux distributions. It is built with Python 3, PySide6 (Qt 6), SQLite and Pillow.

## Screenshots

![VineDeck library in grid view](docs/library.png)
![Application details in VineDeck](docs/details.png)
![VineDeck library in list view](docs/list-view.png)

_Screenshots show the application UI with generated sample cover art._

## Requirements

- VineDeck runs on Linux. The package recipe targets Arch Linux, while the AppImage targets x86_64 Linux.
- Wine is needed to launch Windows applications; install it using your distribution's package manager ([WineHQ](https://www.winehq.org/) has platform-specific guidance). For Steam Proton, install [Steam](https://store.steampowered.com/about/) and a Proton build.
- Running from source requires Python 3.11 or newer. The AppImage bundles Python and VineDeck's Python libraries.

## Features

- Add a `.exe` (or `.lnk`) with an optional **Wine prefix**, working directory, launch arguments and per-application environment variables that override inherited values
- A Wine prefix contains a Windows-style drive and registry. Separate prefixes keep each application's environment independent.
- Grid, compact grid, list and large-cover views, with sorting and drag-and-drop custom ordering in All, Favorites and category views (select Custom Order; reverse sorting disables dragging)
- Sort the library by name, date added, last played, launch count, category or custom order
- Adjustable card grids include column count, size, gaps, corner radius and visible details; changes apply immediately
- Appearance and layout controls can be previewed live in Settings without closing the window
- Cover images (PNG/JPG/JPEG/WEBP, up to 60 MB) are copied as WebP files, resized to at most 2000 px per side, and cached as thumbnails; the source image is left untouched
- Categories, favourites, Recently Played (ordered by launch time) and Most Played (ordered by launch count) views, plus case-insensitive, as-you-type search across names, categories and descriptions; every search term must match
- Deleting a category keeps its applications in the library and makes them uncategorised
- Optional developer, publisher, version, genre, release year and website details can be entered for each application
- Launch states (Launching… / Running / Closed / Failed) update without blocking the UI; running games remain open if you close VineDeck
- Dark, light or system theme, with an accent colour and optional blurred custom background
- Export and import the library as JSON, or as a ZIP archive with artwork
- **Steam Proton support**: detected builds can be selected instead of System Wine from the top bar or *Settings → Wine* (see below)
- Friendly error dialogs, rotating logs, keyboard shortcuts, tooltips and accessible names

VineDeck does not currently manage Bottles, Lutris or Heroic installations, or fetch online metadata. See *Architecture* for extension points.

Exports without artwork are JSON files. Exports with artwork are ZIP archives containing `library.json` and managed covers and icons under `artwork/`; neither format includes app settings, executable files, Wine prefix contents, or the full launch history.

Import merges entries into the current library. Entries with the same name (case-insensitive) and executable path are skipped rather than overwritten, and VineDeck reports how many were added or skipped.
Category names from the export are also restored; missing categories are created during import.

Exports keep the executable and prefix paths as references, not as files. On another machine, place those files where the saved paths resolve or edit each imported entry before launching it.

## Quick start

Install VineDeck using an option in *Installation* or *Packaging*, then follow these steps:

1. Install Wine, or install Steam and a Proton build if you plan to use Proton.
2. Launch VineDeck and select **Add Your First Application** (or **+ Add Application** when the library is not empty).
3. Select the Windows `.exe` or `.lnk` file. Set a working directory, launch arguments, environment variables, or an existing Wine prefix if needed. Enter arguments as a command-line string; quote values that contain spaces. VineDeck parses the string into arguments and does not invoke a shell.
  A custom prefix must already exist; create one with `WINEPREFIX="$HOME/Games/MyGame" wineboot`. If you leave the prefix unset, Wine uses its default prefix. An empty working directory uses the executable's folder.
  VineDeck launches `.lnk` shortcuts through Wine's `start /unix` command.
4. Save the entry and launch it from the library.

Removing an entry only removes its library record and VineDeck-managed artwork; the executable, its files and its Wine prefix are left in place.

## Using Proton from Steam

VineDeck searches Steam's Proton install locations automatically; no path configuration is needed:

Install an official Proton version from Steam's **Library → Tools**. VineDeck discovers installed builds; it does not download or update Proton for you.
Proton Experimental receives frequent changes; if you prefer fewer surprises, select a regular Proton release instead.
Update official builds through Steam. Tools such as [ProtonUp-Qt](https://github.com/DavidoTek/ProtonUp-Qt) can manage GE-Proton and other custom builds.

| Location | What it finds |
|----------|---------------|
| `<steam>/steamapps/common/Proton*` | Official builds installed from Steam's *Library → Tools* |
| `<steam>/compatibilitytools.d/` | GE-Proton and other custom builds, including ProtonUp-Qt installs |
| `/usr/share/steam/compatibilitytools.d/` | System-wide builds such as the AUR `proton-ge-custom` package |
| Extra library folders in `libraryfolders.vdf` | Builds installed in another Steam library |

VineDeck checks native, Flatpak and Snap Steam installs. When it finds a Proton build, a **runner switcher**
appears in the top bar. The same choices are available in *Settings → Wine → Runner*, along with a **Rescan** button. The
selected runner applies to every application and is remembered; choose *System Wine* to switch back.

VineDeck launches Proton with `proton run <exe>` and sets `STEAM_COMPAT_DATA_PATH` and
`STEAM_COMPAT_CLIENT_INSTALL_PATH`, as Steam does.

* **Prefixes.** Proton stores its prefix in `<compatdata>/pfx`. An application without a prefix gets a dedicated one in
  `~/.local/share/vinedeck/proton/app-<id>`. If an application's prefix is a Steam `compatdata/<appid>` folder (or its `pfx`
  folder), it is used directly, so you can reuse a prefix Steam already made. If it is a plain Wine prefix, VineDeck creates a
  `pfx` symlink to it inside its own `proton/linked/` folder and never adds files to your prefix folder.
* **Heads-up:** Proton upgrades a prefix on first use; it may no longer work with plain Wine afterwards.
  Keep separate prefixes for Wine and Proton, or back up before switching an existing one.
* Set Proton options with per-application environment variables, such as `PROTON_LOG=1`, `PROTON_USE_WINED3D=1` or `DXVK_HUD=…`.
* Proton is started directly (outside Steam's container runtime). That works for GE-Proton and normally for Valve's builds; if a
  Valve build refuses to start, try GE-Proton.

## Installation (Arch Linux)

```bash
sudo pacman -S wine            # Required
git clone https://github.com/izumicancode/VineDeck.git vinedeck
cd vinedeck/packaging
makepkg -si
```

Before the first `makepkg` run, install the build and runtime dependencies listed under *Packaging*.

The PKGBUILD installs the Python package, `vinedeck` command, desktop entry and icon. It builds from the surrounding source tree; for the AUR, change it to use a release tarball as described in the file.

## Development

From the repository root, use the project virtual environment so `python -m vinedeck` can import VineDeck:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
python -m vinedeck          # or use the installed vinedeck command
python -m vinedeck --version
python -m vinedeck --help
pytest -q                   # runs headless (offscreen Qt); Wine is never launched in tests
```

Without the project environment, `python -m vinedeck` may fail with `No module named vinedeck`. Activate `.venv` or run directly from the source tree:

```bash
PYTHONPATH=src python -m vinedeck
```

To test with a disposable profile, point the XDG directories at a temporary location:

```bash
XDG_CONFIG_HOME=/tmp/vinedeck-test/config \
XDG_DATA_HOME=/tmp/vinedeck-test/data \
XDG_CACHE_HOME=/tmp/vinedeck-test/cache \
python -m vinedeck
```

Run `python -m vinedeck --debug` for debug logging. To keep an ad-hoc debug session separate from your regular profile, also override the XDG directories:

```bash
XDG_CONFIG_HOME=/tmp/vinedeck-debug/config \
XDG_DATA_HOME=/tmp/vinedeck-debug/data \
XDG_CACHE_HOME=/tmp/vinedeck-debug/cache \
python -m vinedeck --debug
```

### Where things are stored

| What | Location |
|------|----------|
| Preferences | `~/.config/vinedeck/config.json` (or `$XDG_CONFIG_HOME/vinedeck/config.json`) |
| Database, artwork, logs | `~/.local/share/vinedeck/` (`library.db`, `artwork/`, `logs/`; or `$XDG_DATA_HOME/vinedeck/`) |
| Thumbnails and theme cache (safe to delete) | `~/.cache/vinedeck/` (or `$XDG_CACHE_HOME/vinedeck/`) |

These are the default locations; VineDeck respects the corresponding XDG environment variables when they are set.

To reset generated data without changing the library, delete `~/.cache/vinedeck/` and relaunch; VineDeck rebuilds thumbnails and theme assets as needed.

For a portable library backup, export a ZIP with artwork. For a full profile backup, close VineDeck and copy the configuration and data directories; the cache is reproducible. To test a clean profile without affecting your install, set `XDG_CONFIG_HOME`, `XDG_DATA_HOME` and `XDG_CACHE_HOME` to temporary directories before launch.

### Architecture

```
src/vinedeck/
  core/       wine detection, launch-command construction, async process manager, library filtering,
              metadata provider interface, prefix discovery
  database/   SQLite access, models, versioned migrations (PRAGMA user_version)
  services/   images (Pillow), exe icon extraction, export/import, filesystem helpers, metadata service
  ui/         Qt widgets: main window, model/delegate/view, dialogs, settings, theme
  utils/      XDG paths, JSON settings, logging, platform helpers
```

Launching is split in two: `core/launcher.py` validates an application and builds an **argument array** and environment (no shell, `shlex` for user arguments); `core/runners.py` discovers Steam/Proton installs and `core/wine_manager.py` validates the selected runner; `core/process_manager.py` starts it with `subprocess.Popen(..., shell=False, start_new_session=True)` and watches it from a worker thread. Proton uses the same function with the `runner=` argument. To support another runner later (Bottles…), extend `build_launch_spec` the same way. External metadata sources plug in via `MetadataProvider` / `MetadataService`. The small utility layer in `utils/` is intentionally testable so config, logging and path behavior remain predictable across different desktop setups.


## Packaging

VineDeck is a Python package with a `vinedeck` command, desktop entry and icon. The package uses `packaging/PKGBUILD`,
`packaging/vinedeck.desktop` and `src/vinedeck/resources/icons/vinedeck.svg`. Build a wheel with `python -m build`.

### Build and install as a desktop app (Arch Linux)

```bash
sudo pacman -S --needed base-devel python-build python-installer python-setuptools python-wheel \
                        pyside6 python-pillow wine
cd packaging
makepkg -si          # builds and installs the package
```

For a quick package-level smoke test without building the full Arch package, install the `build` frontend in your active Python environment with `python -m pip install build`, then run `python -m build` from the repository root and confirm the wheel can be produced cleanly.

This installs the `vinedeck` command, the application-menu entry (`/usr/share/applications/vinedeck.desktop`), the icon
and the license files (`LICENSE`, `NOTICE`). Afterwards VineDeck appears in your launcher like any other app. To remove it:
`sudo pacman -R vinedeck`.

### Publishing to the AUR

1. Push the code to GitHub and tag a release (for example `v0.1.0`).
2. In `packaging/PKGBUILD`, set `source=` to the tagged GitHub archive (for example, `https://github.com/izumicancode/VineDeck/archive/refs/tags/v$pkgver.tar.gz`), then run `updpkgsums`.
3. Test in a clean chroot with `extra-x86_64-build` (from `devtools`), then run `makepkg --printsrcinfo > .SRCINFO` and
   push the `PKGBUILD` and `.SRCINFO` to your AUR repository.

### Install a released AppImage

Download the latest `VineDeck-<version>-x86_64.AppImage` from the [GitHub Releases](https://github.com/izumicancode/VineDeck/releases/latest) page, then run:

```bash
chmod +x VineDeck-*.AppImage
./VineDeck-*.AppImage
```

To verify the download, also download `SHA256SUMS` from the release and run `sha256sum --check SHA256SUMS` in the directory containing both files.

If FUSE is unavailable, launch it with `--appimage-extract-and-run` instead.

### Build an AppImage (any x86_64 Linux distro)

An AppImage is a single file that bundles Python, Qt (PySide6) and Pillow, so users need to install nothing except Wine
and/or Steam, which VineDeck uses from the host.

```bash
packaging/appimage/build-appimage.sh
# -> dist/VineDeck-<version>-x86_64.AppImage   (about 85 MB)
```

The build machine needs `bash`, `curl` and `python3` with `pip`, `setuptools` and `wheel` (`sudo pacman -S python-pip
python-setuptools python-wheel`). The script downloads a portable Python (from
[python-appimage](https://github.com/niess/python-appimage)) and `appimagetool` once and caches them in
`~/.cache/vinedeck-build`. It then installs VineDeck into that Python, trims files that are not needed at runtime, runs a smoke
test (`--version` and a headless Qt start) and packs the result.

Run it, or install it like any other app:

```bash
chmod +x dist/VineDeck-*.AppImage
./dist/VineDeck-*.AppImage
./dist/VineDeck-*.AppImage --version
./dist/VineDeck-*.AppImage --appimage-extract-and-run     # if FUSE is not available
```

Running an AppImage requires FUSE 2 on the host (`sudo pacman -S fuse2`); alternatively, use `--appimage-extract-and-run`.
To get a menu entry, use a tool such as [Gear Lever](https://github.com/pkgforge-dev/Gear-Lever) or
[AppImageLauncher](https://github.com/TheAssassin/AppImageLauncher).

On X11, Qt needs `libxcb-cursor` from the host (Arch: `xcb-util-cursor`; Debian/Ubuntu: `libxcb-cursor0`). Wayland sessions work
without it.

Build options (environment variables):

| Variable | Default | Meaning |
|----------|---------|---------|
| `PYTHON_VERSION` | `3.12` | Bundled Python version |
| `QT_PACKAGE` | `PySide6-Essentials` | Qt requirement installed into the bundle (the app only uses QtCore, QtGui, QtWidgets and QtSvg) |
| `BASE_IMAGE` / `APPIMAGETOOL` | downloaded | Paths to local copies, for offline builds |
| `CACHE_DIR` | `~/.cache/vinedeck-build` | Download cache |
| `SKIP_TEST=1` | off | Skip the smoke test |

The downloaded tools are not checksum-verified by the script; if you publish AppImages, build in CI from pinned copies
(set `BASE_IMAGE` and `APPIMAGETOOL`). Only x86_64 is supported by the script.

### Flatpak

Not included yet. A Flatpak needs the KDE or Freedesktop runtime, and its sandbox cannot see the host's Wine, Steam or Proton by
default, so it would require extra filesystem permissions and `flatpak-spawn`. It is best left until the Arch and AppImage
builds are settled.

### Release checklist

- Keep the version consistent across `pyproject.toml`, `src/vinedeck/__init__.py` and `packaging/PKGBUILD`.
- Run `pytest -q` (tests use headless Qt; Wine and Proton are never launched).
- Refresh the screenshots in `docs/` if the UI changed (for example the runner switcher in the top bar).
- Test on a clean system or chroot that the menu entry and icon appear and VineDeck starts from the desktop launcher.
- Rebuild the AppImage (`packaging/appimage/build-appimage.sh`) and start it once on a real desktop session.

## Troubleshooting

- **Launching is disabled** – VineDeck does not launch applications when run as root. Start it from your regular desktop account.
- **`--help` does not show a list of options** – run `python -m vinedeck --help` or `vinedeck --help`; the CLI exits with usage text before Qt starts.
- **XDG overrides look ignored** – empty or relative values are discarded; set absolute paths such as `/tmp/vinedeck-test/config` and re-run the app.
- **A Proton build is missing** – install it through Steam or place a custom build in `compatibilitytools.d`, then choose **Settings → Wine → Runner → Rescan**.
- **“Wine is not available” banner** – install `wine`, or set the binary under *Settings → Wine* and press *Detect Wine*.
- **“The selected Wine prefix does not exist”** – prefixes must exist before use. Create one with `WINEPREFIX=~/Games/MyGame wineboot`.
- **Application closes immediately (“Failed”)** – open *View Details* in the dialog or read `~/.local/share/vinedeck/logs/launch-<id>.log` for Wine’s output.
- **No tray/window icon on Wayland** – make sure the `.desktop` file is installed (the app id is `vinedeck`).
- **Blank rendering on some setups** – try `QT_QPA_PLATFORM=xcb` or `wayland` explicitly.
- Logs: `~/.local/share/vinedeck/logs/vinedeck.log`.

## Keyboard shortcuts

| Action | Shortcut |
|--------|----------|
| Search | `Ctrl+F` |
| Add an application | `Ctrl+N` |
| Open settings | `Ctrl+,` |
| Toggle the sidebar | `Ctrl+B` |
| Launch the selected application | `Enter` |
| Remove the selected application | `Delete` |
| Go back, clear search, or close a dialog | `Esc` |
| Toggle fullscreen | `F11` |
| Quit VineDeck | `Ctrl+Q` |

## Contributing

[Issues](https://github.com/izumicancode/VineDeck/issues) and [pull requests](https://github.com/izumicancode/VineDeck/pulls) are welcome. Please run `pytest -q` before submitting, check both the normal app entry path and the `--help`/`--version` flags, keep UI code free of business logic (put it in `core/` or `services/` with tests), and never launch real Wine from tests – mock `subprocess`.

## License

VineDeck is licensed under the [Apache License 2.0](LICENSE). See `NOTICE` for attribution.

Created by [izumicancode](https://github.com/izumicancode).
