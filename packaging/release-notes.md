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

### ⚠️ Office and ebook formats require LibreOffice / Calibre

Convertoor drives existing tools, so these formats **only work when the tool is installed**:

- **LibreOffice** is required for Word, Excel, PowerPoint and OpenDocument files, and for converting office files or Markdown/HTML to PDF. The `.deb` and `.rpm` install it automatically. **On Arch and with the Flatpak you must install it yourself** (`sudo pacman -S libreoffice-fresh`, or `flatpak install flathub org.libreoffice.LibreOffice`).
- **Calibre** is required for MOBI, AZW3, FB2, LIT, PDB and comic-book ebooks. **No package installs it for you**: run `sudo apt/dnf/pacman install calibre`, `flatpak install flathub com.calibre_ebook.calibre`, or use `install.sh --full`.

The Flatpak bundles everything else: FFmpeg, ImageMagick, Pandoc, Poppler, libheif and 7-Zip. When something is missing, the app shows a banner and marks the affected files, and `convertoor --doctor` lists what to install.

After installing, run `convertoor --doctor` to see which converters are available. Fedora users who want the full set of video codecs can swap `ffmpeg-free` for RPM Fusion's `ffmpeg`.
