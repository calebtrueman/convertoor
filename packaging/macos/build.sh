#!/bin/bash
# Build dist/convertoor-<version>-macos-<arch>.dmg on a macOS machine with Homebrew.
set -euxo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT"
VERSION=$(sh packaging/version.sh)
ARCH=$(uname -m)
BUILD="$ROOT/build/macos"
rm -rf "$BUILD" && mkdir -p "$BUILD" dist

export HOMEBREW_NO_INSTALL_CLEANUP=1 HOMEBREW_NO_INSTALLED_DEPENDENTS_CHECK=1 HOMEBREW_NO_ENV_HINTS=1
brew install python@3.14 pygobject3 gtk4 libadwaita adwaita-icon-theme \
    ffmpeg imagemagick poppler librsvg libheif pandoc sevenzip
HOMEBREW_PREFIX=$(brew --prefix)
export HOMEBREW_PREFIX
PY="$(brew --prefix python@3.14)/bin/python3.14"
"$PY" -c "import gi; gi.require_version('Gtk', '4.0'); gi.require_version('Adw', '1'); from gi.repository import Gtk, Adw"

"$PY" -m venv --system-site-packages "$BUILD/venv"
"$BUILD/venv/bin/pip" install --quiet pyinstaller pyyaml fonttools brotli

# App icon
ICONSET="$BUILD/Convertoor.iconset"
mkdir -p "$ICONSET"
SVG=data/icons/io.github.calebtrueman.Convertoor.svg
for s in 16 32 128 256 512; do
    rsvg-convert -w $s -h $s "$SVG" -o "$ICONSET/icon_${s}x${s}.png"
    rsvg-convert -w $((s * 2)) -h $((s * 2)) "$SVG" -o "$ICONSET/icon_${s}x${s}@2x.png"
done
iconutil -c icns "$ICONSET" -o "$BUILD/Convertoor.icns"

CONVERTOOR_VERSION=$VERSION CONVERTOOR_ICNS="$BUILD/Convertoor.icns" \
    "$BUILD/venv/bin/pyinstaller" --noconfirm --clean \
    --distpath "$BUILD/dist" --workpath "$BUILD/work" packaging/macos/convertoor.spec
APP="$BUILD/dist/Convertoor.app"

"$PY" packaging/macos/bundle_tools.py "$APP"
"$PY" packaging/macos/bundle_tools.py --verify "$APP"

# Ad-hoc sign every binary (required on Apple Silicon after editing them), then the app.
find "$APP" -type f -print0 | while IFS= read -r -d '' f; do
    if file -b "$f" | grep -q "Mach-O"; then codesign --force --sign - "$f"; fi
done
codesign --force --sign - "$APP"
codesign --verify --deep --strict "$APP"

STAGE="$BUILD/dmg"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
DMG="dist/convertoor-$VERSION-macos-$ARCH.dmg"
hdiutil create -volname "Convertoor $VERSION" -srcfolder "$STAGE" -fs HFS+ -format ULMO -ov "$DMG"
du -sh "$APP" "$DMG"
