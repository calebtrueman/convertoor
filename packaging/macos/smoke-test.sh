#!/bin/bash
# Install Convertoor.app from the .dmg, hide Homebrew, and exercise every bundled tool.
set -euxo pipefail
DMG=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
HERE=$(cd "$(dirname "$0")/../.." && pwd)

MNT=$(mktemp -d)
hdiutil attach -nobrowse -readonly -mountpoint "$MNT" "$DMG"
DEST=$(mktemp -d)
cp -R "$MNT/Convertoor.app" "$DEST/"
hdiutil detach "$MNT"
APP="$DEST/Convertoor.app"
codesign --verify --deep --strict "$APP"
/usr/bin/python3 "$HERE/packaging/macos/bundle_tools.py" --verify "$APP"

# Prove the app doesn't need Homebrew: move it out of the way for the test.
hidden=()
for d in /opt/homebrew /usr/local/Cellar /usr/local/opt; do
    if [ -d "$d" ]; then sudo mv "$d" "$d.hidden"; hidden+=("$d"); fi
done
restore() { for d in "${hidden[@]}"; do sudo mv "$d.hidden" "$d"; done; }
trap restore EXIT

C="$APP/Contents/MacOS/Convertoor"
T="$APP/Contents/Resources/tools/bin"
# A Finder launch gets a bare environment like this one.
run() { env -i HOME="$HOME" TMPDIR="$TMPDIR" PATH=/usr/bin:/bin:/usr/sbin:/sbin "$C" "$@"; }

run --version
run --doctor
[ "$(run --doctor | grep -cE "✔ (librsvg|libheif|Poppler|ImageMagick|FFmpeg|Pandoc|fontTools)  ")" -eq 7 ]

cd "$(mktemp -d)"
"$T/ffmpeg" -loglevel error -f lavfi -i "sine=frequency=440:duration=1" tone.wav
"$T/ffmpeg" -loglevel error -f lavfi -i "testsrc=duration=1:size=160x120:rate=10" -pix_fmt yuv420p clip.mp4
"$T/ffmpeg" -loglevel error -f lavfi -i "testsrc=size=160x120" -frames:v 1 pic.png
printf '# Hello\n\nFrom *Convertoor*.\n' > doc.md
printf '{"name": "convertoor", "tags": ["a", "b"]}\n' > data.json
cp "$HERE/data/icons/io.github.calebtrueman.Convertoor.svg" icon.svg
cp /System/Library/Fonts/Supplemental/Arial.ttf font.ttf
tar -cf files.tar doc.md data.json

run -t mp3 tone.wav
run -t flac tone.wav
run -t webm clip.mp4
run -t gif clip.mp4
run -t jpg pic.png
run -t webp pic.png
run -t heic pic.png
run -t png pic.heic
run -t pdf pic.png
run -t png pic.pdf
run -t png icon.svg
run -t docx doc.md
run -t html doc.md
run -t yaml data.json
run -t 7z files.tar
run -t woff2 font.ttf
ls -la

# The real GUI, end to end.
run --self-test tone.wav ogg
test -s tone.ogg
echo "MACOS SMOKE TEST PASSED"
