#!/bin/sh
# Convertoor installer for any Linux distribution.
#
#   ./install.sh              install system-wide (asks for sudo) + dependencies
#   ./install.sh --user       install for this user only (~/.local)
#   ./install.sh --full       also install Calibre (ebook formats)
#   ./install.sh --no-deps    skip installing dependencies
#   ./install.sh --deps-only  only install dependencies
#   ./install.sh --uninstall  remove Convertoor
#
# Packagers: DESTDIR=/stage PREFIX=/usr ./install.sh --no-deps
set -eu

APP_ID=io.github.calebtrueman.Convertoor
HERE=$(cd "$(dirname "$0")" && pwd)
PREFIX=${PREFIX:-/usr/local}
DESTDIR=${DESTDIR:-}
PYTHON=${PYTHON:-}
WITH_DEPS=1
DEPS_ONLY=0
UNINSTALL=0
FULL=0
USER_INSTALL=0

while [ $# -gt 0 ]; do
    case "$1" in
        --user) USER_INSTALL=1; PREFIX="$HOME/.local" ;;
        --prefix) shift; PREFIX=$1 ;;
        --prefix=*) PREFIX=${1#--prefix=} ;;
        --no-deps) WITH_DEPS=0 ;;
        --deps-only) DEPS_ONLY=1 ;;
        --full) FULL=1 ;;
        --uninstall) UNINSTALL=1 ;;
        -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mwarning:\033[0m %s\n' "$*" >&2; }

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then SUDO=sudo
    elif command -v doas >/dev/null 2>&1; then SUDO=doas
    fi
fi

# Run with root rights only when writing outside the user's home.
as_root_for_prefix() {
    if [ -n "$DESTDIR" ] || [ "$USER_INSTALL" -eq 1 ] || [ -w "$PREFIX" ] 2>/dev/null; then
        "$@"
    else
        $SUDO "$@"
    fi
}

# Install a required package list, then each optional package on its own so
# one missing package doesn't block the rest.
pkg_install() {
    mgr=$1; shift
    required=$1; shift
    optional=$*
    case "$mgr" in
        apt) $SUDO apt-get update -qq || true
             inst="$SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends" ;;
        dnf) inst="$SUDO dnf install -y" ;;
        zypper) inst="$SUDO zypper --non-interactive install --no-recommends" ;;
        pacman) inst="$SUDO pacman -S --needed --noconfirm" ;;
        xbps) inst="$SUDO xbps-install -Sy" ;;
        apk) inst="$SUDO apk add" ;;
        eopkg) inst="$SUDO eopkg install -y" ;;
    esac
    say "Installing required packages: $required"
    # shellcheck disable=SC2086
    $inst $required
    if [ -n "$optional" ]; then
        say "Installing converters: $optional"
        # shellcheck disable=SC2086
        if ! $inst $optional 2>/dev/null; then
            for p in $optional; do
                $inst "$p" >/dev/null 2>&1 || warn "could not install $p (skipped)"
            done
        fi
    fi
}

install_deps() {
    office_apt="libreoffice-writer libreoffice-calc libreoffice-impress libreoffice-draw"
    office_rpm="libreoffice-writer libreoffice-calc libreoffice-impress libreoffice-draw"
    if command -v apt-get >/dev/null 2>&1; then
        opt="ffmpeg imagemagick pandoc poppler-utils librsvg2-bin libheif-examples python3-yaml python3-fonttools python3-brotli p7zip-full $office_apt"
        [ "$FULL" -eq 1 ] && opt="$opt calibre"
        pkg_install apt "python3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1" "$opt"
    elif command -v dnf >/dev/null 2>&1; then
        opt="ImageMagick pandoc poppler-utils librsvg2-tools libheif-tools python3-pyyaml python3-fonttools python3-brotli 7zip $office_rpm"
        command -v ffmpeg >/dev/null 2>&1 || opt="ffmpeg-free $opt"
        [ "$FULL" -eq 1 ] && opt="$opt calibre"
        pkg_install dnf "python3 python3-gobject gtk4 libadwaita" "$opt"
    elif command -v zypper >/dev/null 2>&1; then
        opt="/usr/bin/ffmpeg ImageMagick /usr/bin/pandoc poppler-tools rsvg-convert python3-PyYAML python3-fonttools python3-Brotli 7zip $office_rpm"
        [ "$FULL" -eq 1 ] && opt="$opt calibre"
        pkg_install zypper "python3 python3-gobject typelib-1_0-Gtk-4_0 typelib-1_0-Adw-1" "$opt"
    elif command -v pacman >/dev/null 2>&1; then
        opt="ffmpeg imagemagick pandoc-cli poppler librsvg libheif python-yaml python-fonttools python-brotli 7zip libreoffice-fresh"
        [ "$FULL" -eq 1 ] && opt="$opt calibre"
        pkg_install pacman "python python-gobject gtk4 libadwaita" "$opt"
    elif command -v xbps-install >/dev/null 2>&1; then
        opt="ffmpeg ImageMagick pandoc poppler-utils librsvg-utils libheif python3-yaml python3-fonttools 7zip libreoffice"
        [ "$FULL" -eq 1 ] && opt="$opt calibre"
        pkg_install xbps "python3 python3-gobject gtk4 libadwaita" "$opt"
    elif command -v apk >/dev/null 2>&1; then
        opt="ffmpeg imagemagick pandoc-cli poppler-utils rsvg-convert libheif-tools py3-yaml py3-fonttools 7zip libreoffice"
        [ "$FULL" -eq 1 ] && opt="$opt calibre"
        pkg_install apk "python3 py3-gobject3 gtk4.0 libadwaita" "$opt"
    elif command -v eopkg >/dev/null 2>&1; then
        pkg_install eopkg "python3 python-gobject libgtk-4 libadwaita" \
            "ffmpeg imagemagick pandoc poppler-utils librsvg python-yaml libreoffice"
    else
        warn "Unknown package manager. Please install: Python 3, PyGObject, GTK 4, libadwaita,"
        warn "and any of: ffmpeg, ImageMagick, pandoc, LibreOffice, poppler, librsvg, 7-Zip, calibre."
    fi
}

FILES="bin/convertoor
share/convertoor
share/applications/$APP_ID.desktop
share/icons/hicolor/scalable/apps/$APP_ID.svg
share/metainfo/$APP_ID.metainfo.xml"

refresh_caches() {
    [ -n "$DESTDIR" ] && return 0
    command -v update-desktop-database >/dev/null 2>&1 &&
        as_root_for_prefix update-desktop-database -q "$PREFIX/share/applications" 2>/dev/null || true
    command -v gtk-update-icon-cache >/dev/null 2>&1 &&
        as_root_for_prefix gtk-update-icon-cache -q -t -f "$PREFIX/share/icons/hicolor" 2>/dev/null || true
}

if [ "$UNINSTALL" -eq 1 ]; then
    say "Removing Convertoor from $PREFIX"
    for f in $FILES; do as_root_for_prefix rm -rf "$DESTDIR$PREFIX/$f"; done
    refresh_caches
    say "Done."
    exit 0
fi

[ "$WITH_DEPS" -eq 1 ] && install_deps
[ "$DEPS_ONLY" -eq 1 ] && exit 0

if [ -z "$PYTHON" ]; then
    if [ -n "$DESTDIR" ] || [ -x /usr/bin/python3 ]; then PYTHON=/usr/bin/python3
    else PYTHON=$(command -v python3 || echo /usr/bin/python3)
    fi
fi

say "Installing Convertoor to $DESTDIR$PREFIX"
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/bin" "$STAGE/share/convertoor" "$STAGE/share/applications" \
         "$STAGE/share/icons/hicolor/scalable/apps" "$STAGE/share/metainfo"
cp -R "$HERE/src/convertoor" "$STAGE/share/convertoor/"
find "$STAGE/share/convertoor" -name '__pycache__' -type d -prune -exec rm -rf {} +
cat > "$STAGE/bin/convertoor" <<EOF
#!$PYTHON
import sys
sys.path.insert(0, "$PREFIX/share/convertoor")
from convertoor.cli import main
sys.exit(main())
EOF
cp "$HERE/data/$APP_ID.desktop" "$STAGE/share/applications/"
cp "$HERE/data/icons/$APP_ID.svg" "$STAGE/share/icons/hicolor/scalable/apps/"
cp "$HERE/data/$APP_ID.metainfo.xml" "$STAGE/share/metainfo/"
if [ "$USER_INSTALL" -eq 1 ]; then
    sed -i.bak "s|^Exec=convertoor|Exec=$PREFIX/bin/convertoor|" "$STAGE/share/applications/$APP_ID.desktop"
    rm -f "$STAGE/share/applications/$APP_ID.desktop.bak"
fi

as_root_for_prefix mkdir -p "$DESTDIR$PREFIX"
as_root_for_prefix rm -rf "$DESTDIR$PREFIX/share/convertoor"
# Copy the staged tree with sane permissions.
(cd "$STAGE" && find . -type d) | while read -r d; do
    as_root_for_prefix install -d -m 755 "$DESTDIR$PREFIX/$d"
done
(cd "$STAGE" && find . -type f) | while read -r f; do
    mode=644
    [ "$f" = "./bin/convertoor" ] && mode=755
    as_root_for_prefix install -m "$mode" "$STAGE/$f" "$DESTDIR$PREFIX/$f"
done
refresh_caches

say "Installed. Launch \"Convertoor\" from your app menu or run: convertoor"
if [ "$USER_INSTALL" -eq 1 ]; then
    case ":$PATH:" in *":$PREFIX/bin:"*) ;; *) warn "$PREFIX/bin is not on your PATH" ;; esac
fi
