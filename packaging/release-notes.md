## Install

| Distro | Download | Command |
|---|---|---|
| Ubuntu 22.04+, Debian 12+, Linux Mint, Pop!_OS, elementary, Zorin | `convertoor_@VERSION@_all.deb` | `sudo apt install ./convertoor_@VERSION@_all.deb` |
| Fedora 39+ | `convertoor-@VERSION@-1.noarch.rpm` | `sudo dnf install ./convertoor-@VERSION@-1.noarch.rpm` |
| openSUSE Tumbleweed / Leap | `convertoor-@VERSION@-1.noarch.rpm` | `sudo zypper install --allow-unsigned-rpm ./convertoor-@VERSION@-1.noarch.rpm` |
| Arch, Manjaro, EndeavourOS, CachyOS | `convertoor-@VERSION@-1-any.pkg.tar.zst` | `sudo pacman -U ./convertoor-@VERSION@-1-any.pkg.tar.zst` |
| Any distro with Flatpak | `convertoor-@VERSION@-x86_64.flatpak` (or `-aarch64`) | `flatpak install --user ./convertoor-@VERSION@-x86_64.flatpak` |
| Anything else (Void, Alpine, Solus, Gentoo …) | `convertoor-@VERSION@.tar.gz` | `tar xf convertoor-@VERSION@.tar.gz && ./convertoor-@VERSION@/install.sh` |

Every installer on this page was installed and tested on Ubuntu 22.04 & 24.04, Debian 12 & 13, Fedora, openSUSE Tumbleweed and Arch Linux, and the Flatpak on x86_64 and aarch64, before this release was published.

The Flatpak bundles FFmpeg, ImageMagick, Pandoc, Poppler, libheif and 7-Zip. For office and ebook formats it uses LibreOffice and Calibre from your system if they're installed, natively or as Flatpaks.

After installing, run `convertoor --doctor` to see which converters are available. Fedora users who want the full set of video codecs can swap `ffmpeg-free` for RPM Fusion's `ffmpeg`.
