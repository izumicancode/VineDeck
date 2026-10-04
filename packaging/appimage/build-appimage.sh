#!/usr/bin/env bash
# Build a self-contained VineDeck AppImage (bundles Python, Qt/PySide6 and Pillow).
#
#   packaging/appimage/build-appimage.sh            # -> dist/VineDeck-<version>-x86_64.AppImage
#
# Needs: bash, curl, tar-less basics (grep, sed, sort), and python3 with pip on the build machine.
# Wine, Steam and Proton are NOT bundled: VineDeck uses the ones installed on the host.
#
# Options (environment variables):
#   PYTHON_VERSION      bundled Python, default 3.12 (must exist at github.com/niess/python-appimage)
#   BASE_IMAGE          path to a python-appimage base .AppImage (skips the download; useful offline)
#   APPIMAGETOOL        path to an appimagetool binary (skips the download)
#   QT_PACKAGE          pip requirement for Qt, default "PySide6-Essentials" (the app only uses QtCore/Gui/Widgets/Svg)
#   CACHE_DIR           where downloads are cached, default ~/.cache/vinedeck-build
#   SKIP_TEST=1         skip the smoke test of the finished AppDir
#   NO_COMPRESS_FLAG=1  do not pass "--comp zstd" to appimagetool
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
PYTHON_VERSION="${PYTHON_VERSION:-3.12}"
QT_PACKAGE="${QT_PACKAGE:-PySide6-Essentials}"
CACHE_DIR="${CACHE_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/vinedeck-build}"
WORK="$ROOT/.appimage-build"
OUT_DIR="$ROOT/dist"
ARCH_NAME="$(uname -m)"

log()  { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

[ "$ARCH_NAME" = "x86_64" ] || die "only x86_64 is supported by this script (found $ARCH_NAME)"
command -v curl    >/dev/null || die "curl is required"
command -v python3 >/dev/null || die "python3 is required to build the wheel"

VERSION="$(sed -n 's/^__version__ *= *"\(.*\)"/\1/p' "$ROOT/src/vinedeck/__init__.py")"
[ -n "$VERSION" ] || die "could not read the version from src/vinedeck/__init__.py"
OUT="$OUT_DIR/VineDeck-$VERSION-$ARCH_NAME.AppImage"

mkdir -p "$CACHE_DIR" "$OUT_DIR"
rm -rf "$WORK"
mkdir -p "$WORK"

# AppImages are normally run through FUSE; extract-and-run works without it (containers, CI).
export APPIMAGE_EXTRACT_AND_RUN=1

download() {  # download <url> <dest>
  log "Downloading $(basename "$2")"
  curl -fL --retry 3 --progress-bar -o "$2.part" "$1" && mv "$2.part" "$2"
}
is_elf() { [ "$(head -c 4 "$1" 2>/dev/null | od -An -c | tr -d ' ')" = '177ELF' ]; }

# -- 1. tools -------------------------------------------------------------------------------------------------
if [ -n "${BASE_IMAGE:-}" ]; then
  [ -f "$BASE_IMAGE" ] || die "BASE_IMAGE not found: $BASE_IMAGE"
else
  log "Looking for the Python $PYTHON_VERSION base image"
  page="$(curl -fsSL "https://github.com/niess/python-appimage/releases/expanded_assets/python$PYTHON_VERSION")" \
    || die "could not list python-appimage releases for Python $PYTHON_VERSION"
  # manylinux_2_28 is required by the PySide6 wheels
  asset="$(printf '%s' "$page" | grep -o 'href="[^"]*manylinux_2_28_x86_64\.AppImage"' | sed 's/^href="//; s/"$//' \
           | sort -V | tail -n 1)"
  [ -n "$asset" ] || die "no manylinux_2_28 x86_64 base image found for Python $PYTHON_VERSION"
  BASE_IMAGE="$CACHE_DIR/$(basename "$asset")"
  [ -f "$BASE_IMAGE" ] || download "https://github.com$asset" "$BASE_IMAGE"
fi
is_elf "$BASE_IMAGE" || die "$BASE_IMAGE is not an AppImage (corrupt download? delete it and retry)"
chmod +x "$BASE_IMAGE"

if [ -z "${APPIMAGETOOL:-}" ]; then
  APPIMAGETOOL="$CACHE_DIR/appimagetool-x86_64.AppImage"
  [ -f "$APPIMAGETOOL" ] || download \
    "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage" "$APPIMAGETOOL"
fi
is_elf "$APPIMAGETOOL" || die "$APPIMAGETOOL is not an executable (corrupt download? delete it and retry)"
chmod +x "$APPIMAGETOOL"

# -- 2. unpack the Python base image into an AppDir ---------------------------------------------------------
log "Preparing the AppDir"
( cd "$WORK" && "$BASE_IMAGE" --appimage-extract >/dev/null ) || die "could not unpack the base image"
APPDIR="$WORK/AppDir"
mv "$WORK/squashfs-root" "$APPDIR"
PYBIN="$(ls "$APPDIR"/opt/python3.*/bin/python3.* 2>/dev/null | grep -E 'python3\.[0-9]+$' | head -n 1)"
[ -x "$PYBIN" ] || die "no Python found inside the base image"
PYREL="${PYBIN#"$APPDIR"/}"
# drop the generic Python launcher files; this AppDir is VineDeck
rm -f "$APPDIR"/AppRun "$APPDIR"/*.desktop "$APPDIR"/*.png "$APPDIR"/.DirIcon
rm -rf "$APPDIR"/usr/share/applications "$APPDIR"/usr/share/icons "$APPDIR"/usr/share/metainfo "$APPDIR"/usr/bin

# -- 3. build and install VineDeck + dependencies ------------------------------------------------------------
log "Building the VineDeck wheel"
python3 -m pip wheel --no-deps --no-build-isolation -q -w "$WORK/wheels" "$ROOT" 2>/dev/null \
  || python3 -m pip wheel --no-deps -q -w "$WORK/wheels" "$ROOT" \
  || die "wheel build failed (is setuptools available? try: pip install setuptools wheel)"
WHEEL="$(ls "$WORK"/wheels/vinedeck-*.whl | head -n 1)"

log "Installing $QT_PACKAGE and Pillow into the bundle (this downloads ~100 MB)"
"$PYBIN" -m pip install -q --no-warn-script-location --disable-pip-version-check "$QT_PACKAGE" "Pillow>=10.0"
log "Installing VineDeck $VERSION"
"$PYBIN" -m pip install -q --no-warn-script-location --disable-pip-version-check --no-deps "$WHEEL"
"$PYBIN" -m pip uninstall -y -q pip setuptools wheel build pyproject_hooks packaging 2>/dev/null || true  # not needed at runtime

# -- 4. slim the bundle -------------------------------------------------------------------------------------
log "Removing files that are not needed at runtime"
SITE="$("$PYBIN" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
rm -rf "$SITE"/PySide6/{Qt/translations,include,typesystems,glue,scripts,examples,support}
rm -f  "$SITE"/PySide6/*.pyi "$SITE"/PySide6/py.typed "$SITE"/shiboken6/*.pyi
find "$APPDIR/opt" -type d \( -name test -o -name tests -o -name idlelib -o -name turtledemo -o -name ensurepip \) \
  -prune -exec rm -rf {} + 2>/dev/null || true
find "$APPDIR/opt" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true

# -- 5. launcher, desktop entry, icon -------------------------------------------------------------------------
log "Writing AppRun, desktop entry and icon"
cat > "$APPDIR/AppRun" <<EOF
#!/usr/bin/env bash
HERE="\$(dirname "\$(readlink -f "\${0}")")"
export APPDIR="\${APPDIR:-\$HERE}"
export SSL_CERT_FILE="\${SSL_CERT_FILE:-\$APPDIR/opt/_internal/certs.pem}"
# Wine/Proton are started from this process, so keep their environment clean of anything Python-specific.
unset PYTHONHOME PYTHONPATH
exec "\$APPDIR/$PYREL" -m vinedeck "\$@"
EOF
chmod +x "$APPDIR/AppRun"

install -Dm644 "$ROOT/packaging/vinedeck.desktop" "$APPDIR/vinedeck.desktop"
install -Dm644 "$ROOT/packaging/vinedeck.desktop" "$APPDIR/usr/share/applications/vinedeck.desktop"
install -Dm644 "$ROOT/src/vinedeck/resources/icons/vinedeck.svg" "$APPDIR/vinedeck.svg"
install -Dm644 "$ROOT/src/vinedeck/resources/icons/vinedeck.svg" \
  "$APPDIR/usr/share/icons/hicolor/scalable/apps/vinedeck.svg"
ln -sf vinedeck.svg "$APPDIR/.DirIcon"
install -Dm644 "$ROOT/LICENSE" "$APPDIR/usr/share/licenses/vinedeck/LICENSE"
install -Dm644 "$ROOT/NOTICE"  "$APPDIR/usr/share/licenses/vinedeck/NOTICE"

# -- 6. smoke test --------------------------------------------------------------------------------------------
if [ -z "${SKIP_TEST:-}" ]; then
  log "Smoke test"
  got="$("$APPDIR/AppRun" --version)" || die "AppRun --version failed"
  [ "$got" = "VineDeck $VERSION" ] || die "unexpected version output: $got"
  QT_QPA_PLATFORM=offscreen "$APPDIR/$PYREL" - <<'PY' || die "Qt/Pillow did not load inside the bundle"
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from PySide6 import QtSvg
import PIL, vinedeck
app = QApplication([])
assert app.platformName() == "offscreen"
print("Qt", __import__("PySide6").__version__, "| Pillow", PIL.__version__, "| ok")
PY
fi

# -- 7. pack ---------------------------------------------------------------------------------------------------
log "Packing $(basename "$OUT")"
comp=(--comp zstd)
[ -n "${NO_COMPRESS_FLAG:-}" ] && comp=()
rm -f "$OUT"
ARCH=x86_64 "$APPIMAGETOOL" --no-appstream "${comp[@]}" "$APPDIR" "$OUT" >"$WORK/appimagetool.log" 2>&1 \
  || { cat "$WORK/appimagetool.log" >&2; die "appimagetool failed"; }
chmod +x "$OUT"
rm -rf "$WORK"
log "Done: $OUT ($(du -h "$OUT" | cut -f1))"
echo "Run it with:  $OUT"
echo "No FUSE?      $OUT --appimage-extract-and-run"
