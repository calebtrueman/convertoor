<p align="center">
  <img src="data/icons/io.github.calebtrueman.Convertoor.svg" width="112" alt="">
</p>

<h1 align="center">Convertoor</h1>

<p align="center">
  Drag-and-drop file converter for Linux. Images, audio, video, documents, spreadsheets,
  slides, ebooks, archives, fonts and data files, all in one window.
</p>

<p align="center">
  <a href="https://github.com/calebtrueman/convertoor/releases/latest"><img alt="Release" src="https://img.shields.io/github/v/release/calebtrueman/convertoor"></a>
  <a href="https://github.com/calebtrueman/convertoor/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/calebtrueman/convertoor/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue">
</p>

---

Drop files (or whole folders) on the window, choose a format for each file or for all of
them at once, and press **Convert**. Converted files land next to the originals, or in a
folder you pick. Nothing is ever overwritten.

Convertoor is a native GTK 4 / libadwaita app. It runs the open-source tools that already
handle these formats well (FFmpeg, ImageMagick, Pandoc, LibreOffice and others) and
**chains them automatically** when no single tool can do a conversion. For example,
Markdown → DOCX → PDF, or PowerPoint → PDF → one PNG per slide.

## Install

Grab the package for your distro from the [**latest release**](https://github.com/calebtrueman/convertoor/releases/latest):

| Distro | Package | Install |
|---|---|---|
| Ubuntu 22.04+, Debian 12+, Mint, Pop!_OS, elementary, Zorin | `.deb` | `sudo apt install ./convertoor_*_all.deb` |
| Fedora | `.rpm` | `sudo dnf install ./convertoor-*.noarch.rpm` |
| openSUSE Tumbleweed / Leap | `.rpm` | `sudo zypper install --allow-unsigned-rpm ./convertoor-*.noarch.rpm` |
| Arch, Manjaro, EndeavourOS, CachyOS | `.pkg.tar.zst` | `sudo pacman -U ./convertoor-*-any.pkg.tar.zst` |
| Any distro with Flatpak | `.flatpak` | `flatpak install --user ./convertoor-*-x86_64.flatpak` |
| Any other distro | `.tar.gz` | `tar xf convertoor-*.tar.gz && ./convertoor-*/install.sh` |

Before a release is published, every package is installed and tested (CLI and GUI) in
clean Ubuntu 22.04, Ubuntu 24.04, Debian 12, Debian 13, Fedora, openSUSE Tumbleweed and
Arch Linux containers. The Flatpak is tested on x86_64 and aarch64.

### Flatpak

The Flatpak (x86_64 and aarch64) runs on the GNOME runtime and **bundles its own
converters**: FFmpeg (with x264, LAME, VP9, Opus, Vorbis, dav1d), ImageMagick, libheif,
Poppler, Pandoc, 7-Zip, PyYAML and fontTools. Nothing else needs to be installed for
images, audio, video, markup documents, data, archives and fonts.

**LibreOffice and Calibre are not bundled, because they're too big.** Office documents
(Word, Excel, PowerPoint, OpenDocument) and ebook formats (MOBI, AZW3, FB2 …) **only work if
you install them yourself**, either on your system or from Flathub:

```sh
flatpak install flathub org.libreoffice.LibreOffice   # office formats
flatpak install flathub com.calibre_ebook.calibre     # ebook formats
```

Convertoor finds either kind of install and runs it through `flatpak-spawn`. See
[Formats that require extra software](#formats-that-require-extra-software).

Sandbox permissions, and why each is needed:

| Permission | Why |
|---|---|
| `--filesystem=home`, `/media`, `/run/media`, `/mnt` | Save converted files next to the originals |
| `--talk-name=org.freedesktop.FileManager1` | "Show in folder" button |
| `--talk-name=org.freedesktop.Flatpak` | Run LibreOffice/Calibre from the host. This lets the app run host commands, so it's effectively unsandboxed. Remove it with `flatpak override --user --no-talk-name=org.freedesktop.Flatpak io.github.calebtrueman.Convertoor` if you don't need office/ebook formats |

Build it yourself:

```sh
flatpak-builder --user --install --force-clean build-dir \
  packaging/flatpak/io.github.calebtrueman.Convertoor.yml
```

The universal `install.sh` detects apt, dnf, zypper, pacman, xbps (Void), apk (Alpine) and
eopkg (Solus) and installs the dependencies for you. Options:

```
./install.sh --user        # install into ~/.local, no root needed
./install.sh --full        # also install Calibre for ebook formats
./install.sh --no-deps     # don't touch the package manager
./install.sh --uninstall
```

Or run it straight from a checkout: `PYTHONPATH=src python3 -m convertoor`

## Supported formats

| Category | Formats | Powered by |
|---|---|---|
| **Images** | PNG, JPG, WebP, GIF, BMP, TIFF, ICO, HEIC/HEIF, AVIF, JPEG XL, JPEG 2000, SVG, PSD, XCF, TGA, PPM/PGM/PBM, PCX, XPM, DDS, EXR, HDR, EPS; RAW photos (CR2, CR3, NEF, ARW, DNG, ORF, RW2, RAF) | ImageMagick, librsvg, libheif |
| **Audio** | MP3, WAV, FLAC, OGG, Opus, M4A, AAC, WMA, AIFF, AC3, AMR, APE, MKA, WavPack, AU, CAF, MP2, DTS | FFmpeg |
| **Video** | MP4, MKV, WebM, AVI, MOV, WMV, FLV, MPG, M4V, 3GP, TS, MTS/M2TS, OGV, VOB, MXF, ASF, F4V. Video → animated GIF, GIF → video, and audio extraction from video | FFmpeg |
| **Subtitles** | SRT, VTT, ASS, SSA, LRC | FFmpeg |
| **Documents** | PDF, DOCX, DOC, ODT, RTF, TXT, Markdown, HTML, reStructuredText, LaTeX, Org, AsciiDoc, Textile, Typst, Jupyter, WordPerfect, Works, AbiWord, Pages | Pandoc, LibreOffice, Poppler |
| **Spreadsheets** | XLSX, XLS, XLSM, XLSB, ODS, CSV, Numbers, DBF | LibreOffice |
| **Presentations** | PPTX, PPT, PPSX, ODP, Keynote. Slides → PDF or one image per slide | LibreOffice |
| **Drawings** | ODG, Visio (VSD/VSDX), Publisher, CorelDRAW | LibreOffice |
| **Ebooks** | EPUB, MOBI, AZW3, FB2, LIT, PDB, CBZ/CBR/CB7, DjVu, CHM | Calibre, Pandoc |
| **Data** | JSON, YAML, TOML, XML, CSV, TSV, plus spreadsheets via CSV | built in |
| **Archives** | ZIP, TAR, TAR.GZ, TAR.BZ2, TAR.XZ, 7Z, RAR (read) | built in, 7-Zip |
| **Fonts** | TTF, OTF, WOFF, WOFF2 | fontTools |

### Formats that require extra software

Convertoor doesn't convert anything itself. It drives the tools in the table above, so
**a format only works if the tool listed for it is installed.** Two of them are often
not installed:

| Required software | Needed for | `.deb` | `.rpm` | Arch | Flatpak | `install.sh` |
|---|---|---|---|---|---|---|
| **LibreOffice** | Word (DOC/DOCX), Excel (XLS/XLSX), PowerPoint (PPT/PPTX), OpenDocument, RTF, WordPerfect, Pages/Numbers/Keynote, Visio, Publisher; office files → PDF; Markdown/HTML → PDF; spreadsheets ⇄ JSON/CSV | installed by default | installed by default | **you must install** `libreoffice-fresh` | **you must install** on your system or `flatpak install flathub org.libreoffice.LibreOffice` | installed |
| **Calibre** | MOBI, AZW/AZW3, FB2, LIT, PDB, LRF, CBZ/CBR/CB7, DjVu, CHM | **you must install** `calibre` | **you must install** `calibre` | **you must install** `calibre` | **you must install** on your system or `flatpak install flathub com.calibre_ebook.calibre` | only with `--full` |

Pandoc covers basic DOCX/ODT/EPUB conversion without LibreOffice or Calibre. For
example, DOCX → Markdown works with Pandoc alone, but DOCX → PDF needs LibreOffice.

When a tool is missing, Convertoor tells you instead of failing silently:

- a banner at the top of the window names the missing tool and what it's needed for;
- a file that needs it says **"Requires LibreOffice (not installed)"**, or **"More
  formats require LibreOffice"** when some conversions still work without it;
- **Menu → Installed Converters** and `convertoor --doctor` list every tool, what each is
  required for, and the command to install it.

After installing a tool, restart Convertoor to pick it up.

## Command line

The same engine works without the GUI:

```sh
convertoor                          # open the window
convertoor *.heic                   # open the window with these files loaded
convertoor -t jpg *.heic            # convert in the terminal
convertoor -t mp3 -o ~/Music videos/
convertoor --targets report.docx    # what can this file become?
convertoor --formats                # every known format
convertoor --doctor                 # installed converters
```

## How it works

```
src/convertoor/
├── formats.py   # format catalogue: extensions, aliases, categories
├── engine.py    # backends + routing + safe execution
├── datafmt.py   # pure-Python JSON/YAML/TOML/XML/CSV conversion
├── gui.py       # GTK 4 / libadwaita interface
└── cli.py       # command line + entry point
```

Each **backend** declares which conversions it can do in one step. To convert A → B, the
engine runs a breadth-first search over the backends that are installed and picks the
shortest chain (at most 3 steps), preferring higher-priority tools. Every step runs in a
private temporary folder. Only finished results are moved into place, and they get a
unique name, so a failed or cancelled conversion never leaves partial files and never
overwrites anything.

Adding a tool means subclassing `Backend` in `engine.py` and implementing `targets()` and
`convert()`. The GUI, CLI and routing pick it up automatically.

## Development

```sh
git clone https://github.com/calebtrueman/convertoor && cd convertoor
PYTHONPATH=src python3 -m convertoor          # run the app
python3 -m pytest tests                       # tests (tool-dependent ones skip if missing)
```

To cut a release, bump `__version__` in `src/convertoor/__init__.py`, then tag `vX.Y.Z` and
push the tag. GitHub Actions builds every package, smoke-tests each one on its distro, and
publishes the release.

## License

MIT © Caleb Trueman. Convertoor runs external programs and doesn't bundle them. Each tool
keeps its own license.
