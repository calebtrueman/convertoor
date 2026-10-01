#!/bin/sh
# Build convertoor_<version>_all.deb into ./dist
set -eu
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
VERSION=$(sh "$ROOT/packaging/version.sh")
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
DESTDIR="$STAGE" PREFIX=/usr "$ROOT/install.sh" --no-deps
mkdir -p "$STAGE/DEBIAN" "$STAGE/usr/share/doc/convertoor"
cp "$ROOT/LICENSE" "$STAGE/usr/share/doc/convertoor/copyright"
SIZE=$(du -sk "$STAGE/usr" | cut -f1)
sed -e "s/@VERSION@/$VERSION/" -e "s/@SIZE@/$SIZE/" "$ROOT/packaging/debian/control.in" > "$STAGE/DEBIAN/control"
mkdir -p "$ROOT/dist"
dpkg-deb --root-owner-group -Zxz --build "$STAGE" "$ROOT/dist/convertoor_${VERSION}_all.deb"
