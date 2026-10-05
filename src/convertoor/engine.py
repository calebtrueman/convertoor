"""Conversion engine: backends, routing and execution.

Each backend wraps one tool (ffmpeg, ImageMagick, pandoc, LibreOffice, ...)
and declares which format pairs it can convert directly. When no single
backend can do a conversion, the engine chains up to three of them through
intermediate formats (for example ``md -> docx -> pdf``).
"""

from __future__ import annotations

import collections
import functools
import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
from pathlib import Path

from . import formats as F
from . import datafmt
from . import macos

macos.setup()

MAX_HOPS = 3


class ConversionError(Exception):
    pass


class Cancelled(ConversionError):
    pass


class Job:
    """Tracks one conversion so it can report progress and be cancelled."""

    def __init__(self, progress=None):
        self._progress_cb = progress
        self._lock = threading.Lock()
        self._proc = None
        self.cancelled = False
        self._step = 0
        self._steps = 1

    def cancel(self):
        with self._lock:
            self.cancelled = True
            proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                proc.terminate()

    def check(self):
        if self.cancelled:
            raise Cancelled("Cancelled")

    def report(self, fraction):
        """Report progress of the current step (0..1), or None if unknown."""
        if self._progress_cb is None:
            return
        if fraction is None:
            self._progress_cb(None)
            return
        fraction = min(max(fraction, 0.0), 1.0)
        self._progress_cb((self._step + fraction) / self._steps)


@functools.lru_cache(maxsize=None)
def which(*names):
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    return None


IN_FLATPAK = os.path.exists("/.flatpak-info")


@functools.lru_cache(maxsize=None)
def host_command(binaries, flatpak_app=None, flatpak_command=None):
    """Command prefix that runs a host tool from inside the Flatpak sandbox.

    Tries a native install on the host first, then the tool's own Flatpak.
    Returns None outside Flatpak or when the host has neither.
    """
    if not IN_FLATPAK or not shutil.which("flatpak-spawn"):
        return None

    def host(*args):
        try:
            r = subprocess.run(["flatpak-spawn", "--host"] + list(args), capture_output=True,
                               text=True, timeout=20, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            return None
        return r.stdout.strip() if r.returncode == 0 else None

    for name in binaries:
        found = host("sh", "-c", f"command -v {name}")
        if found:
            return ("flatpak-spawn", "--host", found)
    if flatpak_app and host("flatpak", "info", "--show-ref", flatpak_app):
        return ("flatpak-spawn", "--host", "flatpak", "run", f"--command={flatpak_command}",
                flatpak_app)
    return None


def host_path(path):
    """Map a document-portal path (from drag and drop in Flatpak) to the real file."""
    path = os.fspath(path)
    if "/doc/" not in path or not path.startswith("/run/"):
        return path
    try:
        real = os.getxattr(path, "user.document-portal.host-path").decode().rstrip("\0")
    except (OSError, AttributeError, UnicodeDecodeError):
        return path
    return real if real and os.access(real, os.R_OK) else path


def run(cmd, job, cwd=None, on_line=None, env=None):
    """Run a command, streaming stdout lines to ``on_line``.

    Raises ConversionError with the tail of the output if it fails.
    """
    job.check()
    try:
        proc = subprocess.Popen(
            [str(c) for c in cmd],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=env,
            text=True,
            errors="replace",
            start_new_session=True,
        )
    except OSError as exc:
        raise ConversionError(f"Could not run {cmd[0]}: {exc}") from exc
    with job._lock:
        job._proc = proc
    tail = collections.deque(maxlen=40)

    def drain_stderr():
        for line in proc.stderr:
            tail.append(line.rstrip())

    t = threading.Thread(target=drain_stderr, daemon=True)
    t.start()
    for line in proc.stdout:
        if on_line is not None:
            on_line(line.rstrip("\n"))
        else:
            tail.append(line.rstrip())
    proc.wait()
    t.join()
    with job._lock:
        job._proc = None
    job.check()
    if proc.returncode != 0:
        msg = "\n".join(l for l in tail if l.strip())[-1500:]
        raise ConversionError(
            f"{os.path.basename(str(cmd[0]))} failed (exit {proc.returncode})"
            + (f":\n{msg}" if msg else "")
        )


def _cache_dir():
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    path = Path(base) / "convertoor"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _outputs(directory: Path, ext: str):
    """Files in ``directory`` with the given extension, naturally sorted."""

    def key(p):
        return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", p.name)]

    return sorted(
        (p for p in directory.iterdir() if p.is_file() and p.name.lower().endswith("." + ext)),
        key=key,
    )


# --------------------------------------------------------------------------
# Backends
# --------------------------------------------------------------------------


class Backend:
    name = ""
    description = ""
    #: executables (any of) or python modules needed
    binaries: tuple = ()
    #: package names shown to the user when the backend is missing
    install_hint = ""
    #: formats that need this tool (shown when it's missing)
    required_for = ""

    def available(self) -> bool:
        return bool(self.path())

    def path(self):
        return which(*self.binaries) if self.binaries else "builtin"

    def command(self):
        """argv prefix used to invoke the tool."""
        return [self.path()]


class HostBackend(Backend):
    """A tool that, inside Flatpak, may be borrowed from the host system."""

    host_flatpak = None  # (app id, command)

    def __init__(self):
        if IN_FLATPAK and self.host_flatpak:
            self.install_hint = (f"{self.name} on your system, or: "
                                 f"flatpak install flathub {self.host_flatpak[0]}")

    def _host(self):
        app, cmd = self.host_flatpak or (None, None)
        return host_command(self.binaries, app, cmd)

    def path(self):
        local = which(*self.binaries)
        if local:
            return local
        host = self._host()
        return " ".join(host) if host else None

    def command(self):
        local = which(*self.binaries)
        if local:
            return [local]
        host = self._host()
        return list(host) if host else [None]

    def on_host(self):
        return not which(*self.binaries) and self._host() is not None

    def targets(self, src: str):
        return ()

    def convert(self, src: Path, src_fmt: str, dst_fmt: str, out: Path, job: Job):
        """Convert ``src`` into ``out`` (a path inside a private temp dir).

        Returns the list of files produced. Extra files (e.g. one image per
        PDF page) may be written next to ``out``.
        """
        raise NotImplementedError


def _pairs(inputs, outputs):
    inputs, outputs = tuple(inputs), tuple(outputs)

    def targets(src):
        return [o for o in outputs if o != src] if src in inputs else []

    return targets


# ---- ffmpeg ---------------------------------------------------------------

VIDEO_IN = ("mp4", "mkv", "webm", "avi", "mov", "wmv", "flv", "mpg", "m4v", "3gp",
            "ts", "mts", "ogv", "vob", "mxf", "asf", "f4v", "gif")
VIDEO_OUT = ("mp4", "mkv", "webm", "mov", "avi", "gif", "wmv", "flv", "mpg", "m4v",
             "3gp", "ts", "ogv")
AUDIO_IN = ("mp3", "wav", "flac", "ogg", "opus", "m4a", "aac", "wma", "aiff", "ac3",
            "amr", "ape", "mka", "wv", "au", "caf", "mp2", "dts")
AUDIO_OUT = ("mp3", "wav", "flac", "ogg", "opus", "m4a", "aac", "wma", "aiff", "ac3",
             "mka", "wv", "au", "caf", "mp2")
SUBS = ("srt", "vtt", "ass", "ssa", "lrc")


@functools.lru_cache(maxsize=None)
def _ffmpeg_encoders(ffmpeg):
    try:
        out = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True,
                             text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return frozenset()
    names = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and len(parts[0]) == 6:
            names.add(parts[1])
    return frozenset(names)


class FFmpeg(Backend):
    name = "FFmpeg"
    description = "Audio, video, animated GIF and subtitle conversion"
    binaries = ("ffmpeg",)
    install_hint = "ffmpeg"

    def targets(self, src):
        if src in VIDEO_IN:
            outs = VIDEO_OUT + AUDIO_OUT
            if src == "gif":
                outs = tuple(o for o in VIDEO_OUT if o != "gif")
            return [o for o in outs if o != src]
        if src in AUDIO_IN:
            return [o for o in AUDIO_OUT if o != src]
        if src in SUBS:
            return [o for o in SUBS if o != src]
        return []

    def _duration(self, src):
        probe = which("ffprobe")
        if not probe:
            return None
        try:
            out = subprocess.run(
                [probe, "-v", "error", "-show_entries", "format=duration", "-of",
                 "default=noprint_wrappers=1:nokey=1", str(src)],
                capture_output=True, text=True, timeout=30,
            ).stdout.strip()
            return float(out) if out and out != "N/A" else None
        except (OSError, ValueError, subprocess.SubprocessError):
            return None

    def _codec_args(self, src_fmt, dst):
        enc = _ffmpeg_encoders(self.path())
        args = []
        if dst in AUDIO_OUT:
            args += ["-vn"]
            audio = {
                "mp3": (["libmp3lame", "-q:a", "2"], None),
                "ogg": (["libvorbis", "-q:a", "5"], ["vorbis", "-strict", "-2", "-ac", "2"]),
                "opus": (["libopus", "-b:a", "128k"], ["opus", "-strict", "-2", "-ar", "48000"]),
                "m4a": (["aac", "-b:a", "192k"], None),
                "aac": (["aac", "-b:a", "192k"], None),
                "wma": (["wmav2", "-b:a", "192k"], None),
            }.get(dst)
            if audio:
                pref, fallback = audio
                if pref[0] in enc or fallback is None:
                    args += ["-c:a"] + pref
                else:
                    args += ["-c:a"] + fallback
            return args
        if dst == "gif":
            return ["-vf", "fps=12,scale='min(640,iw)':-1:flags=lanczos,split[a][b];"
                    "[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer",
                    "-loop", "0", "-an"]
        # Video: keep dimensions even and pixel format widely playable.
        vf = ["-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-pix_fmt", "yuv420p"]
        if dst in ("mp4", "mov", "m4v", "mkv", "3gp", "ts", "flv"):
            if "libx264" in enc:
                args += ["-c:v", "libx264", "-crf", "23", "-preset", "medium"]
            elif "libopenh264" in enc:
                args += ["-c:v", "libopenh264", "-b:v", "4M"]
            args += ["-c:a", "aac", "-b:a", "160k"]
            if dst in ("mp4", "mov", "m4v"):
                args += ["-movflags", "+faststart"]
        elif dst == "webm":
            if "libvpx-vp9" in enc:
                args += ["-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", "-row-mt", "1",
                         "-deadline", "good", "-cpu-used", "4"]
            elif "libvpx" in enc:
                args += ["-c:v", "libvpx", "-crf", "10", "-b:v", "2M"]
            elif "libaom-av1" in enc:
                args += ["-c:v", "libaom-av1", "-crf", "34", "-cpu-used", "6"]
            args += ["-c:a", "libopus" if "libopus" in enc else "libvorbis"]
        elif dst == "ogv":
            if "libtheora" in enc:
                args += ["-c:v", "libtheora", "-q:v", "7"]
            args += ["-c:a", "libvorbis" if "libvorbis" in enc else "vorbis", "-strict", "-2"]
        elif dst == "wmv":
            args += ["-c:v", "wmv2", "-b:v", "3M", "-c:a", "wmav2"]
        elif dst == "mpg":
            args += ["-c:v", "mpeg2video", "-q:v", "3", "-c:a", "mp2"]
        elif dst == "avi":
            args += ["-c:v", "mpeg4", "-q:v", "4",
                     "-c:a", "libmp3lame" if "libmp3lame" in enc else "ac3"]
        if src_fmt == "gif":
            args += ["-an"]
        return vf + args

    def convert(self, src, src_fmt, dst, out, job):
        cmd = [self.path(), "-hide_banner", "-nostdin", "-y", "-i", str(src)]
        if dst in SUBS:
            cmd += [str(out)]
            run(cmd, job)
            return [out]
        cmd += self._codec_args(src_fmt, dst)
        duration = self._duration(src)
        cmd += ["-progress", "pipe:1", "-nostats", str(out)]
        job.report(None if not duration else 0.0)

        def on_line(line):
            if duration and (line.startswith("out_time_us=") or line.startswith("out_time_ms=")):
                try:
                    us = int(line.split("=", 1)[1])
                except ValueError:
                    return
                job.report(us / 1e6 / duration)

        run(cmd, job, on_line=on_line)
        return [out]


# ---- Images -----------------------------------------------------------------

MAGICK_IN = ("png", "jpg", "webp", "gif", "bmp", "tiff", "ico", "heic", "avif", "jxl",
             "jp2", "svg", "psd", "xcf", "tga", "ppm", "pgm", "pbm", "pcx", "xpm", "dds",
             "exr", "hdr", "eps", "pdf", "cr2", "cr3", "nef", "arw", "dng", "orf", "rw2",
             "raf")
MAGICK_OUT = ("png", "jpg", "webp", "gif", "bmp", "tiff", "ico", "avif", "heic", "jxl",
              "jp2", "tga", "ppm", "pgm", "pbm", "pcx", "xpm", "pdf", "eps")
MULTI_FRAME_OUT = ("gif", "tiff", "pdf", "webp")
MULTI_FRAME_IN = ("gif", "tiff", "webp", "ico", "psd", "xcf", "heic", "avif", "dds")
VECTOR_IN = ("svg", "eps", "pdf")


@functools.lru_cache(maxsize=None)
def _magick_path():
    magick = which("magick")
    if magick:
        return magick
    convert = which("convert")
    # Make sure "convert" is ImageMagick 6 and not something else.
    if convert:
        try:
            out = subprocess.run([convert, "-version"], capture_output=True, text=True,
                                 timeout=10).stdout
        except (OSError, subprocess.SubprocessError):
            return None
        if "ImageMagick" in out:
            return convert
    return None


class ImageMagick(Backend):
    name = "ImageMagick"
    description = "Raster images, RAW photos, PSD, icons, images to PDF"
    binaries = ("magick", "convert")
    install_hint = "imagemagick"

    def path(self):
        return _magick_path()

    def targets(self, src):
        if src not in MAGICK_IN:
            return []
        outs = [o for o in MAGICK_OUT if o != src]
        if src == "pdf":
            outs = [o for o in outs if o not in ("pdf", "eps")]
        return outs

    def convert(self, src, src_fmt, dst, out, job):
        cmd = [self.path()]
        if src_fmt in VECTOR_IN:
            cmd += ["-density", "200" if src_fmt == "pdf" else "300"]
        if src_fmt == "svg":
            cmd += ["-background", "none"]
        source = str(src)
        if src_fmt in MULTI_FRAME_IN and dst not in MULTI_FRAME_OUT:
            source += "[0]"
        cmd.append(source)
        if src_fmt in ("pdf", "eps") and dst in ("jpg", "bmp", "ppm", "pgm", "pbm", "pcx"):
            cmd += ["-background", "white", "-alpha", "remove", "-alpha", "off"]
        if dst == "jpg":
            cmd += ["-background", "white", "-alpha", "remove", "-alpha", "off",
                    "-quality", "92"]
        elif dst in ("webp", "avif", "heic", "jxl"):
            cmd += ["-quality", "85"]
        elif dst == "ico":
            cmd += ["-background", "none", "-resize", "256x256", "-gravity", "center",
                    "-extent", "256x256", "-define", "icon:auto-resize=256,128,64,48,32,16"]
        elif dst == "gif" and src_fmt not in MULTI_FRAME_IN:
            cmd += ["-layers", "optimize"]
        cmd.append(f"{dst.upper() if dst in ('ppm', 'pgm', 'pbm') else dst}:{out}")
        job.report(None)
        run(cmd, job)
        produced = _outputs(out.parent, dst)
        if not produced:
            raise ConversionError("ImageMagick produced no output")
        return produced


class Rsvg(Backend):
    name = "librsvg"
    description = "High-quality SVG rendering"
    binaries = ("rsvg-convert",)
    install_hint = "librsvg2-bin / librsvg"
    targets = staticmethod(_pairs(["svg"], ["png", "pdf"]))

    def convert(self, src, src_fmt, dst, out, job):
        run([self.path(), "-f", dst, "-o", str(out), str(src)], job)
        return [out]


class HeifConvert(Backend):
    name = "libheif"
    description = "HEIC/HEIF photos from iPhones"
    binaries = ("heif-dec", "heif-convert")
    install_hint = "libheif-examples / libheif"
    targets = staticmethod(_pairs(["heic", "avif"], ["jpg", "png"]))

    def convert(self, src, src_fmt, dst, out, job):
        cmd = [self.path()]
        if dst == "jpg":
            cmd += ["-q", "92"]
        run(cmd + [str(src), str(out)], job)
        # Multi-image HEIC files produce name-1.jpg, name-2.jpg ...
        produced = _outputs(out.parent, dst)
        if not produced:
            raise ConversionError("heif-convert produced no output")
        return produced


class FFmpegImage(FFmpeg):
    """Fallback for basic image conversion when ImageMagick is missing."""

    name = "FFmpeg (images)"
    description = "Basic image conversion fallback"
    targets = staticmethod(_pairs(["png", "jpg", "bmp", "webp", "tiff", "tga", "ppm"],
                                  ["png", "jpg", "bmp", "webp", "tiff"]))

    def convert(self, src, src_fmt, dst, out, job):
        cmd = [self.path(), "-hide_banner", "-nostdin", "-y", "-i", str(src), "-frames:v", "1"]
        if dst == "jpg":
            cmd += ["-q:v", "2"]
        run(cmd + [str(out)], job)
        return [out]


# ---- PDF utilities ----------------------------------------------------------


class Poppler(Backend):
    name = "Poppler"
    description = "PDF pages to images, PDF to text"
    binaries = ("pdftoppm",)
    install_hint = "poppler-utils / poppler"
    targets = staticmethod(_pairs(["pdf"], ["png", "jpg", "tiff", "txt"]))

    def convert(self, src, src_fmt, dst, out, job):
        if dst == "txt":
            pdftotext = which("pdftotext")
            if not pdftotext:
                raise ConversionError("pdftotext is not installed")
            run([pdftotext, "-layout", str(src), str(out)], job)
            return [out]
        flag = {"png": "-png", "jpg": "-jpeg", "tiff": "-tiff"}[dst]
        prefix = out.parent / F.stem(out)
        run([self.path(), flag, "-r", "150", str(src), str(prefix)], job)
        produced = _outputs(out.parent, "jpg" if dst == "jpg" else dst)
        if not produced:
            # pdftoppm writes .tif for TIFF output
            produced = _outputs(out.parent, "tif")
        if dst == "tiff":
            renamed = []
            for p in produced:
                if p.suffix == ".tif":
                    q = p.with_suffix(".tiff")
                    p.rename(q)
                    p = q
                renamed.append(p)
            produced = renamed
        return produced


# ---- Documents --------------------------------------------------------------

PANDOC_READERS = {
    "md": "markdown", "txt": "markdown", "html": "html", "docx": "docx", "odt": "odt",
    "epub": "epub", "rst": "rst", "tex": "latex", "org": "org", "textile": "textile",
    "ipynb": "ipynb", "fb2": "fb2", "rtf": "rtf", "csv": "csv", "tsv": "tsv", "typ": "typst",
}
PANDOC_WRITERS = {
    "docx": "docx", "odt": "odt", "pdf": "pdf", "html": "html", "md": "gfm", "epub": "epub3",
    "pptx": "pptx", "rtf": "rtf", "txt": "plain", "rst": "rst", "tex": "latex", "org": "org",
    "adoc": "asciidoc", "ipynb": "ipynb", "typ": "typst", "textile": "textile", "fb2": "fb2",
}
# minimum pandoc version for some readers/writers
PANDOC_MIN = {("r", "rtf"): (2, 14), ("r", "csv"): (2, 9, 2), ("r", "tsv"): (3, 0),
              ("r", "typst"): (3, 1, 2), ("w", "typst"): (3, 0)}
PDF_ENGINES = ("xelatex", "lualatex", "pdflatex", "tectonic", "typst", "weasyprint",
               "wkhtmltopdf")


@functools.lru_cache(maxsize=None)
def _pandoc_version(pandoc):
    try:
        first = subprocess.run([pandoc, "--version"], capture_output=True, text=True,
                               timeout=20).stdout.splitlines()[0]
        return tuple(int(x) for x in re.findall(r"\d+", first)[:3])
    except (OSError, IndexError, ValueError, subprocess.SubprocessError):
        return (0,)


class Pandoc(Backend):
    name = "Pandoc"
    description = "Markdown, HTML, Word, ODT, EPUB, LaTeX and other markup"
    binaries = ("pandoc",)
    install_hint = "pandoc"

    def _ok(self, kind, fmt):
        need = PANDOC_MIN.get((kind, fmt))
        if need is None or not self.path():
            return True
        return _pandoc_version(self.path()) >= need

    def targets(self, src):
        reader = PANDOC_READERS.get(src)
        if not reader or not self._ok("r", reader):
            return []
        outs = []
        for ext, writer in PANDOC_WRITERS.items():
            if ext == src or not self._ok("w", writer):
                continue
            if ext == "pdf" and not self._pdf_engine():
                continue
            outs.append(ext)
        return outs

    def _pdf_engine(self):
        for engine in PDF_ENGINES:
            if which(engine):
                return engine
        return None

    def convert(self, src, src_fmt, dst, out, job):
        reader = PANDOC_READERS[src_fmt]
        cmd = [self.path(), "-f", reader, str(src), "-o", str(out)]
        if dst == "pdf":
            cmd += ["--pdf-engine", self._pdf_engine()]
        else:
            cmd += ["-t", PANDOC_WRITERS[dst]]
        if dst in ("html", "tex", "rtf", "org", "typ") or dst == "pdf":
            cmd.append("--standalone")
        cmd += ["--resource-path", str(src.parent)]
        job.report(None)
        run(cmd, job, cwd=str(src.parent))
        return [out]


WRITER_IN = ("doc", "docx", "docm", "dotx", "odt", "fodt", "rtf", "txt", "html", "wpd", "wps",
             "abw", "pages", "lwp")
WRITER_OUT = ("pdf", "docx", "odt", "doc", "rtf", "txt", "html", "epub")
CALC_IN = ("xls", "xlsx", "xlsm", "xlsb", "ods", "fods", "csv", "numbers", "dbf")
CALC_OUT = ("xlsx", "ods", "xls", "csv", "pdf", "html")
IMPRESS_IN = ("ppt", "pptx", "pptm", "pps", "ppsx", "odp", "fodp", "key")
IMPRESS_OUT = ("pdf", "pptx", "odp", "ppt")
DRAW_IN = ("odg", "vsd", "vsdx", "pub", "cdr")
DRAW_OUT = ("pdf", "odg", "svg", "png")

_LO_LOCK = threading.Lock()


class LibreOffice(HostBackend):
    name = "LibreOffice"
    description = "Office documents, spreadsheets, presentations, to PDF"
    binaries = ("soffice", "libreoffice")
    install_hint = "libreoffice"
    short_required = "office documents"
    required_for = ("Word, Excel, PowerPoint and OpenDocument files, office files to PDF, "
                    "and Markdown/HTML to PDF")
    host_flatpak = ("org.libreoffice.LibreOffice", "libreoffice")

    def targets(self, src):
        for ins, outs in ((WRITER_IN, WRITER_OUT), (CALC_IN, CALC_OUT),
                          (IMPRESS_IN, IMPRESS_OUT), (DRAW_IN, DRAW_OUT)):
            if src in ins:
                return [o for o in outs if o != src]
        return []

    def convert(self, src, src_fmt, dst, out, job):
        if self.on_host():
            # The host can't see our sandboxed cache dir, use the real one.
            profile = Path.home() / ".cache" / "convertoor" / "libreoffice-profile"
            profile.parent.mkdir(parents=True, exist_ok=True)
        else:
            profile = _cache_dir() / "libreoffice-profile"
        filt = dst
        if dst == "txt":
            filt = "txt:Text (encoded):UTF8"
        elif dst == "csv":
            filt = "csv:Text - txt - csv (StarCalc):44,34,76"
        elif dst == "html" and src_fmt in CALC_IN:
            filt = "html:HTML (StarCalc)"
        cmd = self.command() + [f"-env:UserInstallation={profile.as_uri()}", "--headless",
               "--norestore", "--nologo", "--nolockcheck", "--nodefault"]
        if src_fmt == "html":
            cmd.append("--infilter=HTML (StarWriter)")
        elif src_fmt == "csv":
            cmd.append("--infilter=CSV:44,34,76,1")
        cmd += ["--convert-to", filt, "--outdir", str(out.parent), str(src)]
        job.report(None)
        # LibreOffice can't run two conversions on one profile at once.
        with _LO_LOCK:
            run(cmd, job)
        produced = _outputs(out.parent, dst)
        if not produced:
            raise ConversionError("LibreOffice could not convert this file")
        return produced[:1]


CALIBRE_IN = ("epub", "mobi", "azw", "azw3", "fb2", "lit", "pdb", "lrf", "htmlz", "txtz",
              "cbz", "cbr", "cb7", "chm", "djvu", "pdf", "docx", "odt", "rtf", "txt",
              "html", "md")
CALIBRE_OUT = ("epub", "mobi", "azw3", "pdf", "docx", "fb2", "txt", "rtf", "htmlz", "lit",
               "pdb", "txtz")


class Calibre(HostBackend):
    name = "Calibre"
    description = "Ebooks: EPUB, MOBI, AZW3, FB2, comics"
    binaries = ("ebook-convert",)
    install_hint = "calibre"
    short_required = "ebook formats"
    required_for = "MOBI, AZW3, FB2, LIT, PDB and comic book (CBZ/CBR) ebooks"
    host_flatpak = ("com.calibre_ebook.calibre", "ebook-convert")
    targets = staticmethod(_pairs(CALIBRE_IN, CALIBRE_OUT))

    def convert(self, src, src_fmt, dst, out, job):
        job.report(0.0)

        def on_line(line):
            m = re.match(r"\s*(\d+)%", line)
            if m:
                job.report(int(m.group(1)) / 100)

        run(self.command() + [str(src), str(out)], job, on_line=on_line)
        return [out]


# ---- Archives ---------------------------------------------------------------

PY_ARCHIVES = ("zip", "tar", "tar.gz", "tar.bz2", "tar.xz")


class Archives(Backend):
    name = "Archives"
    description = "ZIP, TAR, GZ, BZ2, XZ (built in); 7z and RAR with 7-Zip"
    install_hint = "7zip / p7zip-full (for 7z and RAR)"

    def seven(self):
        return which("7zz", "7z", "7za")

    def targets(self, src):
        readable = list(PY_ARCHIVES)
        if self.seven() or which("bsdtar"):
            readable += ["7z", "rar"]
        if which("unrar"):
            readable.append("rar")
        if src not in readable:
            return []
        outs = list(PY_ARCHIVES) + (["7z"] if self.seven() else [])
        return [o for o in outs if o != src]

    def _extract(self, src, src_fmt, dest, job):
        import tarfile
        import zipfile

        if src_fmt == "zip":
            with zipfile.ZipFile(src) as zf:
                zf.extractall(dest)
            return
        if src_fmt.startswith("tar"):
            with tarfile.open(src) as tf:
                root = os.path.realpath(dest)
                members = []
                for m in tf.getmembers():
                    target = os.path.realpath(os.path.join(dest, m.name))
                    if not (target == root or target.startswith(root + os.sep)):
                        continue
                    if m.isdev() or ((m.issym() or m.islnk()) and (
                            os.path.isabs(m.linkname) or ".." in Path(m.linkname).parts)):
                        continue
                    members.append(m)
                if hasattr(tarfile, "data_filter"):
                    tf.extractall(dest, members=members, filter="data")
                else:
                    tf.extractall(dest, members=members)
            return
        seven = self.seven()
        if seven:
            run([seven, "x", "-y", f"-o{dest}", str(src)], job)
        elif src_fmt == "rar" and which("unrar"):
            run([which("unrar"), "x", "-o+", str(src), str(dest) + os.sep], job)
        elif which("bsdtar"):
            run([which("bsdtar"), "-xf", str(src), "-C", str(dest)], job)
        else:
            raise ConversionError("Install 7-Zip to read this archive")

    def _pack(self, srcdir, dst, out, job):
        import tarfile
        import zipfile

        entries = sorted(os.listdir(srcdir))
        if dst == "zip":
            with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(srcdir):
                    dirs.sort()
                    for name in sorted(files):
                        full = os.path.join(root, name)
                        zf.write(full, os.path.relpath(full, srcdir))
                    if not files and not dirs and root != str(srcdir):
                        zf.write(root, os.path.relpath(root, srcdir) + "/")
        elif dst.startswith("tar"):
            mode = {"tar": "w", "tar.gz": "w:gz", "tar.bz2": "w:bz2", "tar.xz": "w:xz"}[dst]
            with tarfile.open(out, mode) as tf:
                for e in entries:
                    tf.add(os.path.join(srcdir, e), arcname=e)
        elif dst == "7z":
            run([self.seven(), "a", "-y", str(out)] + entries, job, cwd=str(srcdir))
        else:
            raise ConversionError(f"Cannot create {dst}")

    def convert(self, src, src_fmt, dst, out, job):
        job.report(None)
        work = out.parent / ".contents"
        work.mkdir()
        self._extract(src, src_fmt, work, job)
        job.check()
        self._pack(work, dst, out, job)
        shutil.rmtree(work, ignore_errors=True)
        return [out]


# ---- Data & fonts (pure python) ---------------------------------------------


class Data(Backend):
    name = "Data formats"
    description = "JSON, YAML, TOML, XML, CSV, TSV (built in)"
    install_hint = "python3-yaml (for YAML)"

    def targets(self, src):
        fmts = datafmt.supported()
        if src not in fmts["read"]:
            return []
        return [f for f in fmts["write"] if f != src]

    def convert(self, src, src_fmt, dst, out, job):
        datafmt.convert(src, src_fmt, out, dst)
        return [out]


class Fonts(Backend):
    name = "fontTools"
    description = "TTF, OTF, WOFF, WOFF2 fonts"
    install_hint = "python3-fonttools (+ python3-brotli for WOFF2)"

    def path(self):
        try:
            import fontTools  # noqa: F401
        except ImportError:
            return None
        return "python:fontTools"

    def _woff2(self):
        try:
            import brotli  # noqa: F401
            return True
        except ImportError:
            try:
                import brotlicffi  # noqa: F401
                return True
            except ImportError:
                return False

    def targets(self, src):
        if src not in ("ttf", "otf", "woff", "woff2"):
            return []
        outs = ["woff"] + (["woff2"] if self._woff2() else [])
        if src in ("woff", "woff2"):
            outs += ["ttf", "otf"]
        if src == "woff2" and not self._woff2():
            return []
        return [o for o in outs if o != src]

    def convert(self, src, src_fmt, dst, out, job):
        from fontTools.ttLib import TTFont

        font = TTFont(str(src))
        is_cff = "CFF " in font or "CFF2" in font
        if dst == "ttf" and is_cff:
            raise ConversionError("This font has PostScript outlines; convert it to OTF instead")
        if dst == "otf" and not is_cff:
            raise ConversionError("This font has TrueType outlines; convert it to TTF instead")
        font.flavor = dst if dst in ("woff", "woff2") else None
        font.save(str(out))
        return [out]


# Order matters: earlier backends win when several can do the same step.
BACKENDS = [
    Rsvg(), HeifConvert(), Poppler(), ImageMagick(), FFmpeg(), Pandoc(), LibreOffice(),
    Calibre(), Data(), Archives(), Fonts(), FFmpegImage(),
]
macos.apply_hints(BACKENDS)

# Multi-step routes may only cross categories in these directions; direct
# single-tool conversions are always allowed.
_CROSS = {
    (F.DOCUMENT, F.EBOOK), (F.EBOOK, F.DOCUMENT), (F.DOCUMENT, F.IMAGE),
    (F.PRESENTATION, F.IMAGE), (F.PRESENTATION, F.DOCUMENT), (F.SPREADSHEET, F.DOCUMENT),
    (F.SPREADSHEET, F.DATA), (F.DATA, F.SPREADSHEET), (F.DATA, F.DOCUMENT),
    (F.DRAWING, F.IMAGE), (F.DRAWING, F.DOCUMENT), (F.DOCUMENT, F.PRESENTATION),
    (F.EBOOK, F.IMAGE),
}
# Cross-category routes limited to a few sensible destinations.
_CROSS_ONLY = {
    (F.DATA, F.DOCUMENT): {"pdf", "docx", "odt", "html", "md"},
    (F.EBOOK, F.IMAGE): {"png", "jpg"},
}
# Formats never used as stepping stones (lossy or odd intermediates).
_NO_TRANSIT = {"gif", "txt", "ico", "pbm", "pgm", "xpm", "eps", "jpg", "wma", "amr"}


def available_backends():
    return [b for b in BACKENDS if b.available()]


def refresh():
    """Forget cached tool lookups (e.g. after the user installs something)."""
    which.cache_clear()
    host_command.cache_clear()
    _magick_path.cache_clear()
    _targets_cached.cache_clear()
    _ffmpeg_encoders.cache_clear()
    _pandoc_version.cache_clear()
    datafmt.supported.cache_clear()


def plan(src, dst, backends=None):
    """Shortest list of (backend, from_fmt, to_fmt) steps converting src to dst."""
    if src == dst or src not in F.FORMATS or dst not in F.FORMATS:
        return None
    backends = available_backends() if backends is None else backends
    prev = {src: None}
    depth = {src: 0}
    queue = collections.deque([src])
    while queue:
        cur = queue.popleft()
        if depth[cur] >= MAX_HOPS:
            continue
        if cur != src and cur in _NO_TRANSIT:
            continue
        for b in backends:
            for nxt in b.targets(cur):
                if nxt in prev:
                    continue
                prev[nxt] = (cur, b)
                depth[nxt] = depth[cur] + 1
                if nxt == dst:
                    steps = []
                    node = dst
                    while prev[node] is not None:
                        frm, bk = prev[node]
                        steps.append((bk, frm, node))
                        node = frm
                    return list(reversed(steps))
                queue.append(nxt)
    return None


@functools.lru_cache(maxsize=512)
def _targets_cached(src, key):
    backends = [b for b in BACKENDS if b.name in key]
    found = {}
    # Direct conversions
    for b in backends:
        for t in b.targets(src):
            found.setdefault(t, 1)
    # Multi-step conversions
    for dst in F.FORMATS:
        if dst in found or dst == src:
            continue
        sc, dc = F.category(src), F.category(dst)
        if sc != dc and ((sc, dc) not in _CROSS or
                         dst not in _CROSS_ONLY.get((sc, dc), (dst,))):
            continue
        steps = plan(src, dst, backends)
        if steps:
            found[dst] = len(steps)
    cat = F.category(src)
    order = list(F.CATEGORY_LABELS)
    pos = {f: i for i, f in enumerate(F.FORMATS)}
    return tuple(sorted(found, key=lambda f: (F.category(f) != cat,
                                               order.index(F.category(f)), pos[f])))


def targets(src):
    """All formats ``src`` can be converted to with the installed tools."""
    if src not in F.FORMATS:
        return ()
    key = frozenset(b.name for b in available_backends())
    return _targets_cached(src, key)


_STATIC_INPUTS = {
    "FFmpeg": VIDEO_IN + AUDIO_IN + SUBS,
    "ImageMagick": MAGICK_IN,
    "librsvg": ("svg",),
    "libheif": ("heic", "avif"),
    "Poppler": ("pdf",),
    "Pandoc": tuple(PANDOC_READERS),
    "LibreOffice": WRITER_IN + CALC_IN + IMPRESS_IN + DRAW_IN,
    "Calibre": CALIBRE_IN,
    "Archives": ("7z", "rar"),
    "fontTools": ("ttf", "otf", "woff", "woff2"),
    "Data formats": ("yaml", "toml"),
}


def missing_backends(src):
    """Backends that aren't installed but would handle ``src`` (or handle it better)."""
    missing = []
    for b in BACKENDS:
        if src not in _STATIC_INPUTS.get(b.name, ()):
            continue
        if b.available() and b.targets(src):
            continue
        missing.append(b)
    return missing


def missing_for(src, dst):
    """Uninstalled backends that would each make ``src`` -> ``dst`` possible."""
    have = available_backends()
    found = []
    for b in BACKENDS:
        if b in have:
            continue
        try:
            if plan(src, dst, have + [b]):
                found.append(b)
        except Exception:
            continue
    return found


def missing_tools(src):
    """Install hints for tools that would let us handle ``src`` (or handle it better)."""
    hints = []
    for b in missing_backends(src):
        if b.name == "Data formats":
            hint = "python3-yaml" if src == "yaml" else "python3-tomli"
        else:
            hint = b.install_hint
        if hint not in hints:
            hints.append(hint)
    return hints


def _unique(path: Path) -> Path:
    if not path.exists():
        return path
    base, ext = F.stem(path), path.name[len(F.stem(path)):]
    n = 1
    while True:
        candidate = path.with_name(f"{base} ({n}){ext}")
        if not candidate.exists():
            return candidate
        n += 1


def convert_file(src, dst_fmt, out_dir=None, job=None):
    """Convert one file. Returns the list of output paths (usually one)."""
    src = Path(src).resolve()
    job = job or Job()
    if not src.is_file():
        raise ConversionError(f"{src} is not a file")
    src_fmt = F.detect(src)
    if src_fmt is None:
        raise ConversionError(f"Unrecognised file type: {src.name}")
    dst_fmt = F.canonical(dst_fmt) or dst_fmt
    steps = plan(src_fmt, dst_fmt)
    if not steps:
        need = missing_for(src_fmt, dst_fmt)
        extra = ""
        if need:
            extra = ": requires " + " or ".join(
                f"{b.name} (install: {b.install_hint})" for b in need)
        raise ConversionError(f"Can't convert {src_fmt.upper()} to {dst_fmt.upper()}{extra}")
    out_dir = Path(out_dir).expanduser().resolve() if out_dir else src.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        tmp = Path(tempfile.mkdtemp(prefix=".convertoor-", dir=out_dir))
    except OSError:
        tmp = Path(tempfile.mkdtemp(prefix="convertoor-"))
    name = F.stem(src)
    try:
        current = src
        produced = []
        job._steps = len(steps)
        for i, (backend, frm, to) in enumerate(steps):
            job.check()
            job._step = i
            step_dir = tmp / f"step{i}"
            step_dir.mkdir()
            produced = backend.convert(current, frm, to, step_dir / f"{name}.{to}", job)
            produced = [Path(p) for p in produced if Path(p).exists()]
            if not produced:
                raise ConversionError(f"{backend.name} produced no output")
            current = produced[0]
        job._step, job._steps = 0, 1
        job.report(1.0)
        results = []
        if len(produced) == 1:
            dest = _unique(out_dir / f"{name}.{dst_fmt}")
            shutil.move(str(produced[0]), str(dest))
            results.append(dest)
        else:
            folder = _unique(out_dir / f"{name} ({dst_fmt.upper()})")
            folder.mkdir()
            width = len(str(len(produced)))
            for idx, p in enumerate(produced, 1):
                dest = folder / f"{name}-{str(idx).zfill(width)}.{dst_fmt}"
                shutil.move(str(p), str(dest))
                results.append(dest)
        return results
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
