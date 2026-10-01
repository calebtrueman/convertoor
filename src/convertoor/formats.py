"""Catalogue of file formats Convertoor knows about."""

from __future__ import annotations

import os

IMAGE = "image"
AUDIO = "audio"
VIDEO = "video"
DOCUMENT = "document"
SPREADSHEET = "spreadsheet"
PRESENTATION = "presentation"
DRAWING = "drawing"
EBOOK = "ebook"
DATA = "data"
ARCHIVE = "archive"
FONT = "font"
SUBTITLE = "subtitle"

CATEGORY_LABELS = {
    IMAGE: "Image",
    AUDIO: "Audio",
    VIDEO: "Video",
    DOCUMENT: "Document",
    SPREADSHEET: "Spreadsheet",
    PRESENTATION: "Presentation",
    DRAWING: "Drawing",
    EBOOK: "Ebook",
    DATA: "Data",
    ARCHIVE: "Archive",
    FONT: "Font",
    SUBTITLE: "Subtitle",
}

CATEGORY_ICONS = {
    IMAGE: "image-x-generic-symbolic",
    AUDIO: "audio-x-generic-symbolic",
    VIDEO: "video-x-generic-symbolic",
    DOCUMENT: "x-office-document-symbolic",
    SPREADSHEET: "x-office-spreadsheet-symbolic",
    PRESENTATION: "x-office-presentation-symbolic",
    DRAWING: "x-office-drawing-symbolic",
    EBOOK: "x-office-document-symbolic",
    DATA: "text-x-generic-symbolic",
    ARCHIVE: "package-x-generic-symbolic",
    FONT: "font-x-generic-symbolic",
    SUBTITLE: "text-x-generic-symbolic",
}

# format id -> (description, category). The id doubles as the file extension.
FORMATS = {
    # Images
    "png": ("PNG image", IMAGE),
    "jpg": ("JPEG image", IMAGE),
    "webp": ("WebP image", IMAGE),
    "gif": ("GIF image", IMAGE),
    "bmp": ("Bitmap image", IMAGE),
    "tiff": ("TIFF image", IMAGE),
    "ico": ("Windows icon", IMAGE),
    "heic": ("HEIC/HEIF image", IMAGE),
    "avif": ("AVIF image", IMAGE),
    "jxl": ("JPEG XL image", IMAGE),
    "jp2": ("JPEG 2000 image", IMAGE),
    "svg": ("SVG vector image", IMAGE),
    "psd": ("Photoshop document", IMAGE),
    "xcf": ("GIMP image", IMAGE),
    "tga": ("Targa image", IMAGE),
    "ppm": ("Portable pixmap", IMAGE),
    "pgm": ("Portable graymap", IMAGE),
    "pbm": ("Portable bitmap", IMAGE),
    "pcx": ("PCX image", IMAGE),
    "xpm": ("X pixmap", IMAGE),
    "dds": ("DirectDraw surface", IMAGE),
    "exr": ("OpenEXR image", IMAGE),
    "hdr": ("Radiance HDR image", IMAGE),
    "eps": ("Encapsulated PostScript", IMAGE),
    "cr2": ("Canon RAW photo", IMAGE),
    "cr3": ("Canon RAW photo", IMAGE),
    "nef": ("Nikon RAW photo", IMAGE),
    "arw": ("Sony RAW photo", IMAGE),
    "dng": ("Digital negative", IMAGE),
    "orf": ("Olympus RAW photo", IMAGE),
    "rw2": ("Panasonic RAW photo", IMAGE),
    "raf": ("Fujifilm RAW photo", IMAGE),
    # Audio
    "mp3": ("MP3 audio", AUDIO),
    "wav": ("WAV audio", AUDIO),
    "flac": ("FLAC audio", AUDIO),
    "ogg": ("Ogg Vorbis audio", AUDIO),
    "opus": ("Opus audio", AUDIO),
    "m4a": ("AAC/M4A audio", AUDIO),
    "aac": ("AAC audio", AUDIO),
    "wma": ("Windows Media audio", AUDIO),
    "aiff": ("AIFF audio", AUDIO),
    "ac3": ("Dolby AC-3 audio", AUDIO),
    "amr": ("AMR audio", AUDIO),
    "ape": ("Monkey's Audio", AUDIO),
    "mka": ("Matroska audio", AUDIO),
    "wv": ("WavPack audio", AUDIO),
    "au": ("Sun audio", AUDIO),
    "caf": ("Core Audio file", AUDIO),
    "mp2": ("MPEG-1 Layer II audio", AUDIO),
    "dts": ("DTS audio", AUDIO),
    # Video
    "mp4": ("MP4 video", VIDEO),
    "mkv": ("Matroska video", VIDEO),
    "webm": ("WebM video", VIDEO),
    "avi": ("AVI video", VIDEO),
    "mov": ("QuickTime video", VIDEO),
    "wmv": ("Windows Media video", VIDEO),
    "flv": ("Flash video", VIDEO),
    "mpg": ("MPEG video", VIDEO),
    "m4v": ("M4V video", VIDEO),
    "3gp": ("3GP video", VIDEO),
    "ts": ("MPEG transport stream", VIDEO),
    "mts": ("AVCHD video", VIDEO),
    "ogv": ("Ogg video", VIDEO),
    "vob": ("DVD video", VIDEO),
    "mxf": ("MXF video", VIDEO),
    "asf": ("ASF video", VIDEO),
    "f4v": ("F4V video", VIDEO),
    # Subtitles
    "srt": ("SubRip subtitles", SUBTITLE),
    "vtt": ("WebVTT subtitles", SUBTITLE),
    "ass": ("Advanced SubStation subtitles", SUBTITLE),
    "ssa": ("SubStation Alpha subtitles", SUBTITLE),
    "lrc": ("LRC lyrics", SUBTITLE),
    # Documents
    "pdf": ("PDF document", DOCUMENT),
    "docx": ("Word document", DOCUMENT),
    "doc": ("Word 97-2003 document", DOCUMENT),
    "docm": ("Word macro document", DOCUMENT),
    "dotx": ("Word template", DOCUMENT),
    "odt": ("OpenDocument text", DOCUMENT),
    "fodt": ("Flat OpenDocument text", DOCUMENT),
    "rtf": ("Rich Text Format", DOCUMENT),
    "txt": ("Plain text", DOCUMENT),
    "md": ("Markdown", DOCUMENT),
    "html": ("HTML page", DOCUMENT),
    "rst": ("reStructuredText", DOCUMENT),
    "tex": ("LaTeX document", DOCUMENT),
    "org": ("Org mode document", DOCUMENT),
    "adoc": ("AsciiDoc document", DOCUMENT),
    "textile": ("Textile document", DOCUMENT),
    "typ": ("Typst document", DOCUMENT),
    "ipynb": ("Jupyter notebook", DOCUMENT),
    "wpd": ("WordPerfect document", DOCUMENT),
    "wps": ("Works document", DOCUMENT),
    "abw": ("AbiWord document", DOCUMENT),
    "pages": ("Apple Pages document", DOCUMENT),
    "lwp": ("Lotus WordPro document", DOCUMENT),
    "xps": ("XPS document", DOCUMENT),
    # Spreadsheets
    "xlsx": ("Excel workbook", SPREADSHEET),
    "xls": ("Excel 97-2003 workbook", SPREADSHEET),
    "xlsm": ("Excel macro workbook", SPREADSHEET),
    "xlsb": ("Excel binary workbook", SPREADSHEET),
    "ods": ("OpenDocument spreadsheet", SPREADSHEET),
    "fods": ("Flat OpenDocument spreadsheet", SPREADSHEET),
    "numbers": ("Apple Numbers spreadsheet", SPREADSHEET),
    "dbf": ("dBASE table", SPREADSHEET),
    # Presentations
    "pptx": ("PowerPoint presentation", PRESENTATION),
    "ppt": ("PowerPoint 97-2003 presentation", PRESENTATION),
    "pptm": ("PowerPoint macro presentation", PRESENTATION),
    "ppsx": ("PowerPoint show", PRESENTATION),
    "pps": ("PowerPoint 97-2003 show", PRESENTATION),
    "odp": ("OpenDocument presentation", PRESENTATION),
    "fodp": ("Flat OpenDocument presentation", PRESENTATION),
    "key": ("Apple Keynote presentation", PRESENTATION),
    # Drawings
    "odg": ("OpenDocument drawing", DRAWING),
    "vsd": ("Visio drawing", DRAWING),
    "vsdx": ("Visio drawing", DRAWING),
    "pub": ("Publisher document", DRAWING),
    "cdr": ("CorelDRAW drawing", DRAWING),
    # Ebooks
    "epub": ("EPUB ebook", EBOOK),
    "mobi": ("Mobipocket ebook", EBOOK),
    "azw": ("Kindle ebook", EBOOK),
    "azw3": ("Kindle KF8 ebook", EBOOK),
    "fb2": ("FictionBook ebook", EBOOK),
    "lit": ("Microsoft Reader ebook", EBOOK),
    "pdb": ("Palm ebook", EBOOK),
    "lrf": ("Sony Reader ebook", EBOOK),
    "htmlz": ("Zipped HTML ebook", EBOOK),
    "txtz": ("Zipped text ebook", EBOOK),
    "cbz": ("Comic book (ZIP)", EBOOK),
    "cbr": ("Comic book (RAR)", EBOOK),
    "cb7": ("Comic book (7z)", EBOOK),
    "chm": ("Compiled HTML help", EBOOK),
    "djvu": ("DjVu document", EBOOK),
    # Data
    "json": ("JSON data", DATA),
    "yaml": ("YAML data", DATA),
    "toml": ("TOML data", DATA),
    "xml": ("XML data", DATA),
    "csv": ("Comma-separated values", DATA),
    "tsv": ("Tab-separated values", DATA),
    # Archives
    "zip": ("ZIP archive", ARCHIVE),
    "tar": ("Tar archive", ARCHIVE),
    "tar.gz": ("Gzip tarball", ARCHIVE),
    "tar.bz2": ("Bzip2 tarball", ARCHIVE),
    "tar.xz": ("XZ tarball", ARCHIVE),
    "7z": ("7-Zip archive", ARCHIVE),
    "rar": ("RAR archive", ARCHIVE),
    # Fonts
    "ttf": ("TrueType font", FONT),
    "otf": ("OpenType font", FONT),
    "woff": ("WOFF web font", FONT),
    "woff2": ("WOFF2 web font", FONT),
}

ALIASES = {
    "jpeg": "jpg",
    "jpe": "jpg",
    "jfif": "jpg",
    "tif": "tiff",
    "heif": "heic",
    "htm": "html",
    "xhtml": "html",
    "yml": "yaml",
    "markdown": "md",
    "mdown": "md",
    "mkd": "md",
    "text": "txt",
    "latex": "tex",
    "aif": "aiff",
    "oga": "ogg",
    "mpeg": "mpg",
    "m2ts": "mts",
    "qt": "mov",
    "3gpp": "3gp",
    "tgz": "tar.gz",
    "tbz": "tar.bz2",
    "tbz2": "tar.bz2",
    "txz": "tar.xz",
    "asciidoc": "adoc",
    "pnm": "ppm",
}

_COMPOUND = ("tar.gz", "tar.bz2", "tar.xz")


def canonical(ext: str) -> str | None:
    ext = ext.lower().lstrip(".")
    ext = ALIASES.get(ext, ext)
    return ext if ext in FORMATS else None


def detect(path: str | os.PathLike) -> str | None:
    """Return the canonical format id for a path, based on its extension."""
    name = os.path.basename(os.fspath(path)).lower()
    for compound in _COMPOUND:
        if name.endswith("." + compound):
            return compound
    if "." not in name:
        return None
    return canonical(name.rsplit(".", 1)[1])


def stem(path: str | os.PathLike) -> str:
    """File name without its (possibly compound) extension."""
    name = os.path.basename(os.fspath(path))
    lower = name.lower()
    for compound in _COMPOUND:
        if lower.endswith("." + compound):
            return name[: -len(compound) - 1]
    root, _ = os.path.splitext(name)
    return root or name


def category(fmt: str) -> str:
    return FORMATS[fmt][1]


def describe(fmt: str) -> str:
    return FORMATS[fmt][0]


def label(fmt: str) -> str:
    return fmt.upper()
