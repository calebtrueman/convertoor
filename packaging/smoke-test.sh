#!/bin/sh
# Install a built package inside a distro container and exercise it.
#   packaging/smoke-test.sh deb|fedora|suse|arch|tarball <artifact>
set -eux
kind=$1
pkg=$(readlink -f "$2")

case "$kind" in
    deb)
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq
        apt-get install -y --no-install-recommends "$pkg" xvfb xauth dbus python3-yaml
        ;;
    fedora)
        dnf install -y "$pkg" xorg-x11-server-Xvfb dbus-daemon xauth which
        ;;
    suse)
        zypper --non-interactive refresh
        zypper --non-interactive install --allow-unsigned-rpm "$pkg" xvfb-run dbus-1 xauth which gawk
        zypper --non-interactive install dbus-1-daemon || zypper --non-interactive install dbus-1-tools || true
        ;;
    arch)
        pacman -Syu --noconfirm
        pacman -U --noconfirm "$pkg"
        pacman -S --noconfirm --needed xorg-server-xvfb xorg-xauth dbus which
        ;;
    tarball)
        work=$(mktemp -d)
        tar -xzf "$pkg" -C "$work"
        sh "$work"/convertoor-*/install.sh
        if command -v dnf >/dev/null; then dnf install -y xorg-x11-server-Xvfb dbus-daemon xauth which; fi
        if command -v apt-get >/dev/null; then apt-get install -y xvfb xauth dbus; fi
        ;;
    *) echo "unknown kind $kind"; exit 2 ;;
esac

convertoor --version
convertoor --doctor

cd "$(mktemp -d)"
ffmpeg -loglevel error -f lavfi -i "sine=frequency=440:duration=1" tone.wav
ffmpeg -loglevel error -f lavfi -i "testsrc=duration=1:size=160x120:rate=10" -pix_fmt yuv420p clip.mp4
ffmpeg -loglevel error -f lavfi -i "testsrc=size=160x120" -frames:v 1 pic.png
printf '# Hello\n\nFrom *Convertoor*.\n' > doc.md
printf '{"name": "convertoor", "tags": ["a", "b"]}\n' > data.json

convertoor --targets tone.wav clip.mp4 pic.png doc.md data.json
convertoor -t mp3 tone.wav
convertoor -t webm clip.mp4
convertoor -t gif clip.mp4
convertoor -t jpg pic.png
convertoor -t xml data.json
if command -v pandoc >/dev/null; then convertoor -t docx doc.md; fi
if command -v rsvg-convert >/dev/null; then
    prefix=$(dirname "$(dirname "$(command -v convertoor)")")
    cp "$prefix/share/icons/hicolor/scalable/apps/io.github.calebtrueman.Convertoor.svg" icon.svg
    convertoor -t png icon.svg
fi
ls -la

# Real GUI, end to end, on a virtual display.
export GSK_RENDERER=cairo GDK_BACKEND=x11 NO_AT_BRIDGE=1
if command -v dbus-run-session >/dev/null; then
    dbus-run-session -- xvfb-run -a convertoor --self-test tone.wav flac
else
    xvfb-run -a convertoor --self-test tone.wav flac
fi
test -s tone.flac
echo "SMOKE TEST PASSED ($kind)"
