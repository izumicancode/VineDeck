# VineDeck

A modern, customisable library and launcher for Windows applications and games that run through **Wine**. VineDeck has a native Arch Linux package recipe and a portable x86_64 AppImage for other Linux distributions. It is built with Python 3, PySide6 (Qt 6), SQLite and Pillow.

## Screenshots

![VineDeck library in grid view](docs/library.png)
![Application details in VineDeck](docs/details.png)
![VineDeck library in list view](docs/list-view.png)

_Screenshots use generated sample cover art._

## Requirements

- VineDeck runs on Linux. The native package recipe targets Arch Linux; the AppImage targets x86_64 Linux.
- Wine is needed to launch Windows applications; install it using your distribution's package manager ([WineHQ](https://www.winehq.org/) has platform-specific guidance). For Steam Proton, install [Steam](https://store.steampowered.com/about/) and a Proton build.
- Running from source requires Python 3.11 or newer. The AppImage bundles Python and the Python libraries used by VineDeck.

## Features

- Add a `.exe` (or `.lnk`) with its own **Wine prefix**, working directory, launch arguments and environment variables
- A Wine prefix contains a Windows-style drive and registry; using a separate prefix per application keeps their environments independent
- Grid, compact grid, list and large-cover views; sorting; drag-and-drop custom order
- Fully adjustable card grid (columns, size, gaps, radius, what is shown) that applies instantly
- Cover images (PNG/JPG/WEBP) stored in VineDeck’s own data folder, with cached thumbnails; icons extracted from executables when possible
- Categories, favourites, Recently/Most Played, as-you-type search
- Launch state (Launching… / Running / Closed / Failed) without blocking the UI; games keep running if you close the launcher
- Dark / light / system theme, accent colour, optional blurred custom background
- Export / import your library as JSON (optionally with artwork)
- **Steam Proton support**: Proton builds are detected automatically and can be switched with System Wine from the top bar or *Settings → Wine* (see below)
- Friendly error dialogs, rotating logs, keyboard shortcuts, tooltips and accessible names

Not currently supported: managing Bottles, Lutris, or Heroic installations, and fetching online metadata. See *Architecture* for the extension points.

## Quick start

Install VineDeck using one of the options in the *Installation* or *Packaging* sections, then:

1. Install Wine, or install Steam and a Proton build if you want to use Proton.
2. Launch VineDeck and choose **Add Your First Application** (or **+ Add Application** when the library is not empty).
3. Select the Windows `.exe` or `.lnk` file. Set a working directory, launch arguments, environment variables, or an existing Wine prefix if needed. Quote argument values that contain spaces.
4. Save the entry, then launch it from your library.

## Using Proton from Steam

VineDeck looks for Proton in every place Steam keeps it, so there is nothing to configure:

Install an official Proton version from Steam's **Library → Tools**. VineDeck discovers installed builds; it does not download or update Proton for you.
Proton Experimental receives frequent changes; if you prefer fewer surprises, select a regular Proton release instead.
Update official builds in Steam; tools such as [ProtonUp-Qt](https://github.com/DavidoTek/ProtonUp-Qt) can manage GE-Proton and other custom builds.

| Location | What it finds |
|----------|---------------|
| `<steam>/steamapps/common/Proton*` | Official Proton builds installed from Steam (*Library → Tools*) |
| `<steam>/compatibilitytools.d/` | GE-Proton and other custom builds (e.g. from ProtonUp-Qt) |
| `/usr/share/steam/compatibilitytools.d/` | System-wide installs such as the AUR `proton-ge-custom` |
| Extra library folders in `libraryfolders.vdf` | Proton installed on another drive |

Native, Flatpak and Snap Steam installs are all checked. If at least one Proton build is found, a **runner switcher**
appears in the top bar; the same list is in *Settings → Wine → Runner* (with a **Rescan** button). The choice applies to every
application and is remembered. Switch back to *System Wine* at any time.

How Proton is launched: VineDeck runs `proton run <exe>` with `STEAM_COMPAT_DATA_PATH` and
`STEAM_COMPAT_CLIENT_INSTALL_PATH` set, which is what Steam does.

* **Prefixes.** Proton keeps its prefix in `<compatdata>/pfx`. An application *without* a prefix gets its own, created in
  `~/.local/share/vinedeck/proton/app-<id>`. If an application's prefix is a Steam `compatdata/<appid>` folder (or its `pfx`
  folder), it is used directly, so you can reuse a prefix Steam already made. If it is a plain Wine prefix, VineDeck creates a
  `pfx` symlink to it inside its own `proton/linked/` folder and never adds files to your prefix folder.
* **Heads-up:** a prefix first used with Proton is upgraded by Proton, and may no longer work with plain Wine afterwards.
  Keep separate prefixes for Wine and Proton, or back up before switching an existing one.
* Per-application environment variables work as usual (`PROTON_LOG=1`, `PROTON_USE_WINED3D=1`, `DXVK_HUD=…`).
* Proton is started directly (outside Steam's container runtime). That works for GE-Proton and normally for Valve's builds; if a
  Valve build refuses to start, try GE-Proton.

## Installation (Arch Linux)

```bash
sudo pacman -S wine            # Required
git clone https://github.com/izumicancode/VineDeck.git vinedeck
cd vinedeck/packaging
makepkg -si
```

Before running `makepkg` for the first time, install the build and runtime dependencies listed under *Packaging* below.

The PKGBUILD installs the Python package, a `vinedeck` command, the `.desktop` entry and the icon. It builds from the surrounding source tree; for the AUR switch it to a release tarball (instructions are in the file).

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m vinedeck          # or: vinedeck
python -m vinedeck --version
pytest                      # runs headless (offscreen Qt); Wine is never launched in tests
```

If you have installed the dependencies but not the editable package, start from the repository root with `PYTHONPATH=src python -m vinedeck`.

To run with an isolated, throw-away profile, point the XDG directories at a temporary location:

```bash
XDG_CONFIG_HOME=/tmp/vinedeck-test/config \
XDG_DATA_HOME=/tmp/vinedeck-test/data \
XDG_CACHE_HOME=/tmp/vinedeck-test/cache \
python -m vinedeck
```

Run `python -m vinedeck --debug` to enable debug logging.

### Where things are stored

| What | Location |
|------|----------|
| Preferences | `~/.config/vinedeck/config.json` |
| Database, artwork, logs | `~/.local/share/vinedeck/` (`library.db`, `artwork/`, `logs/`) |
| Thumbnails and theme cache (safe to delete) | `~/.cache/vinedeck/` |

These are the default locations; VineDeck respects the corresponding XDG environment variables when they are set.

For a portable library backup, export it as JSON and include artwork. For a full profile backup, close VineDeck first, then copy both the configuration and data directories; the cache can be recreated.

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

Launching is split in two: `core/launcher.py` validates an application and builds an **argument array** and environment (no shell, `shlex` for user arguments); `core/runners.py` discovers Steam/Proton installs and `core/wine_manager.py` validates the selected runner; `core/process_manager.py` starts it with `subprocess.Popen(..., shell=False, start_new_session=True)` and watches it from a worker thread. Proton uses the same function with the `runner=` argument. To support another runner later (Bottles…), extend `build_launch_spec` the same way. External metadata sources plug in via `MetadataProvider` / `MetadataService`.


## Packaging

VineDeck is a normal Python package that ships a `vinedeck` command, a desktop entry and an icon, so it installs as a
regular desktop app. `packaging/PKGBUILD`, `packaging/vinedeck.desktop` and `src/vinedeck/resources/icons/vinedeck.svg`
are everything a package needs. Wheel build: `python -m build`.

### Build and install as a desktop app (Arch Linux)

```bash
sudo pacman -S --needed base-devel python-build python-installer python-setuptools python-wheel \
                        pyside6 python-pillow wine
cd packaging
makepkg -si          # builds and installs the package
```

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

The build machine needs `bash`, `curl`, and `python3` with `pip` and `setuptools`/`wheel` (`sudo pacman -S python-pip
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

Running an AppImage needs FUSE 2 on the host (`sudo pacman -S fuse2`), or use `--appimage-extract-and-run` as above.
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

- Keep the version in sync in `pyproject.toml`, `src/vinedeck/__init__.py` and `packaging/PKGBUILD`.
- Run `pytest` (it runs headless; Wine and Proton are never launched).
- Refresh the screenshots in `docs/` if the UI changed (for example the runner switcher in the top bar).
- Test the install on a clean system or chroot: the menu entry appears, the icon shows, and the app starts from the launcher.
- Rebuild the AppImage (`packaging/appimage/build-appimage.sh`) and start it once on a real desktop session.

## Troubleshooting

- **Launching is disabled** – VineDeck does not launch applications when run as root. Start it from your regular desktop account.
- **A Proton build is missing** – install it through Steam or place a custom build in `compatibilitytools.d`, then choose **Settings → Wine → Runner → Rescan**.
- **“Wine is not available” banner** – install `wine`, or set the binary under *Settings → Wine* and press *Detect Wine*.
- **“The selected Wine prefix does not exist”** – prefixes must exist before use. Create one with `WINEPREFIX=~/Games/MyGame wineboot`.
- **Application closes immediately (“Failed”)** – open *View Details* in the dialog or read `~/.local/share/vinedeck/logs/launch-<id>.log` for Wine’s output.
- **No tray/window icon on Wayland** – make sure the `.desktop` file is installed (the app id is `vinedeck`).
- **Blank rendering on odd GPUs** – try `QT_QUICK_BACKEND=software` or `QT_QPA_PLATFORM=xcb`/`wayland` explicitly.
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

[Issues](https://github.com/izumicancode/VineDeck/issues) and [pull requests](https://github.com/izumicancode/VineDeck/pulls) are welcome. Please run `pytest` before submitting, keep UI code free of business logic (put it in `core/` or `services/` with tests), and never launch real Wine from tests – mock `subprocess`.

## License

VineDeck is licensed under the [Apache License 2.0](LICENSE). See `NOTICE` for attribution.

Created by [izumicancode](https://github.com/izumicancode).
