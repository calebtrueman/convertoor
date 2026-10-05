"""Environment set-up for macOS.

Apps launched from Finder get a bare PATH (/usr/bin:/bin:/usr/sbin:/sbin), so
neither the converters bundled inside Convertoor.app nor Homebrew's tools
would be found. This puts them on PATH and points ImageMagick and fontconfig
at the files bundled with the app.
"""

from __future__ import annotations

import glob
import os
import sys
from pathlib import Path

MAC_HINTS = {
    "FFmpeg": "brew install ffmpeg",
    "ImageMagick": "brew install imagemagick",
    "librsvg": "brew install librsvg",
    "libheif": "brew install libheif",
    "Poppler": "brew install poppler",
    "Pandoc": "brew install pandoc",
    "LibreOffice": "LibreOffice from libreoffice.org, or: brew install --cask libreoffice",
    "Calibre": "Calibre from calibre-ebook.com, or: brew install --cask calibre",
    "Archives": "brew install sevenzip",
    "fontTools": "pip3 install fonttools brotli",
    "Data formats": "pip3 install pyyaml",
}

# Apps that ship command-line tools inside their bundle.
APP_TOOL_DIRS = (
    "LibreOffice.app/Contents/MacOS",
    "calibre.app/Contents/MacOS",
)


def bundled_tools_dir():
    """``Convertoor.app/Contents/Resources/tools`` when running from the app."""
    if not getattr(sys, "frozen", False):
        return None
    tools = Path(sys.executable).resolve().parent.parent / "Resources" / "tools"
    return tools if (tools / "bin").is_dir() else None


def setup():
    if sys.platform != "darwin":
        return
    first, last = [], []
    tools = bundled_tools_dir()
    if tools:
        first.append(str(tools / "bin"))
        _setup_imagemagick(tools)
        heif_plugins = tools / "lib" / "libheif"
        if heif_plugins.is_dir():
            os.environ.setdefault("LIBHEIF_PLUGIN_PATH", str(heif_plugins))
        fonts = tools / "etc" / "fonts" / "fonts.conf"
        if fonts.is_file():
            os.environ.setdefault("FONTCONFIG_FILE", str(fonts))
    last += ["/opt/homebrew/bin", "/usr/local/bin", "/opt/local/bin"]
    for root in ("/Applications", os.path.expanduser("~/Applications")):
        last += [os.path.join(root, d) for d in APP_TOOL_DIRS]
    current = os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin").split(os.pathsep)
    seen, merged = set(), []
    for p in first + current + last:
        if p and p not in seen:
            seen.add(p)
            merged.append(p)
    os.environ["PATH"] = os.pathsep.join(merged)


def _setup_imagemagick(tools: Path):
    lib = tools / "lib" / "ImageMagick"
    coders = glob.glob(str(lib / "modules-*" / "coders"))
    filters = glob.glob(str(lib / "modules-*" / "filters"))
    configs = glob.glob(str(lib / "config-*")) + glob.glob(str(tools / "etc" / "ImageMagick*"))
    os.environ.setdefault("MAGICK_HOME", str(tools))
    if coders:
        os.environ.setdefault("MAGICK_CODER_MODULE_PATH", coders[0])
    if filters:
        os.environ.setdefault("MAGICK_CODER_FILTER_PATH", filters[0])
    if configs:
        os.environ.setdefault("MAGICK_CONFIGURE_PATH", os.pathsep.join(configs))


def apply_hints(backends):
    if sys.platform != "darwin":
        return
    for b in backends:
        if b.name in MAC_HINTS:
            b.install_hint = MAC_HINTS[b.name]
