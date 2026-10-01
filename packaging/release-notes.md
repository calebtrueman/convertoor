## Install

| Distro | Download | Command |
|---|---|---|
| Ubuntu 22.04+, Debian 12+, Linux Mint, Pop!_OS, elementary, Zorin | `convertoor_@VERSION@_all.deb` | `sudo apt install ./convertoor_@VERSION@_all.deb` |
| Fedora 39+ | `convertoor-@VERSION@-1.noarch.rpm` | `sudo dnf install ./convertoor-@VERSION@-1.noarch.rpm` |
| openSUSE Tumbleweed / Leap | `convertoor-@VERSION@-1.noarch.rpm` | `sudo zypper install --allow-unsigned-rpm ./convertoor-@VERSION@-1.noarch.rpm` |
| Arch, Manjaro, EndeavourOS, CachyOS | `convertoor-@VERSION@-1-any.pkg.tar.zst` | `sudo pacman -U ./convertoor-@VERSION@-1-any.pkg.tar.zst` |
| Anything else (Void, Alpine, Solus, Gentoo …) | `convertoor-@VERSION@.tar.gz` | `tar xf convertoor-@VERSION@.tar.gz && ./convertoor-@VERSION@/install.sh` |

Every installer on this page was installed and tested on Ubuntu 22.04 & 24.04, Debian 12 & 13, Fedora, openSUSE Tumbleweed and Arch Linux before this release was published.

After installing, run `convertoor --doctor` to see which converters are available. Fedora users who want the full set of video codecs can swap `ffmpeg-free` for RPM Fusion's `ffmpeg`.
