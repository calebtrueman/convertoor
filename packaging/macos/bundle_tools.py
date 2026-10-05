#!/usr/bin/env python3
"""Copy the converters from Homebrew into Convertoor.app and make them self-contained.

Every executable goes into Contents/Resources/tools/bin and every non-system
library it needs (recursively) into tools/lib. All library references are
rewritten to @executable_path/../lib/<name>, so nothing points back into
Homebrew and the app runs on Macs without it.

    bundle_tools.py Convertoor.app          bundle
    bundle_tools.py --verify Convertoor.app check nothing references outside the app
"""

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

TOOLS = ["ffmpeg", "ffprobe", "magick", "pdftoppm", "pdftotext", "rsvg-convert",
         "heif-dec", "pandoc", "7zz"]
SYSTEM_PREFIXES = ("/usr/lib/", "/System/Library/")
MACHO_MAGIC = {b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"}
LIB_REF = "@executable_path/../lib/"


def sh(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def is_macho(path):
    try:
        with open(path, "rb") as fh:
            return fh.read(4) in MACHO_MAGIC
    except OSError:
        return False


def load_commands(path):
    """(install name id, [dependencies], [rpaths]) of a Mach-O file."""
    out = sh("otool", "-l", str(path)).splitlines()
    ident, deps, rpaths = None, [], []
    cmd = None
    for line in out:
        line = line.strip()
        if line.startswith("cmd "):
            cmd = line.split()[1]
        elif line.startswith("name ") and cmd in ("LC_LOAD_DYLIB", "LC_LOAD_WEAK_DYLIB",
                                                  "LC_REEXPORT_DYLIB", "LC_LOAD_UPWARD_DYLIB"):
            deps.append(line.split()[1])
        elif line.startswith("name ") and cmd == "LC_ID_DYLIB":
            ident = line.split()[1]
        elif line.startswith("path ") and cmd == "LC_RPATH":
            rpaths.append(line.split()[1])
    return ident, deps, rpaths


def resolve(dep, origin, exe_origin, rpaths):
    """Find the file a dependency refers to, relative to the original locations."""
    def sub(p):
        return (p.replace("@loader_path", str(Path(origin).parent))
                 .replace("@executable_path", str(Path(exe_origin).parent)))

    if dep.startswith("@rpath/"):
        for rp in rpaths:
            cand = Path(sub(rp)) / dep[len("@rpath/"):]
            if cand.exists():
                return cand
        return None
    cand = Path(sub(dep))
    return cand if cand.exists() else None


def writable(path):
    os.chmod(path, os.stat(path).st_mode | stat.S_IWUSR)


def copy_tree(src, dst, exe, queue):
    if not src.is_dir():
        return
    for f in sorted(src.rglob("*")):
        if f.is_dir():
            continue
        dest = dst / f.relative_to(src)
        dest.parent.mkdir(parents=True, exist_ok=True)
        real = f.resolve()
        shutil.copy2(real, dest)
        if is_macho(dest):
            writable(dest)
            queue.append((dest, real, exe))


def bundle(app):
    brew = Path(sh("brew", "--prefix").strip())
    tools = app / "Contents" / "Resources" / "tools"
    bindir, libdir = tools / "bin", tools / "lib"
    if tools.exists():
        shutil.rmtree(tools)
    bindir.mkdir(parents=True)
    libdir.mkdir()

    queue = []  # (file in bundle, original path, original executable)
    for name in TOOLS:
        found = shutil.which(name, path=str(brew / "bin"))
        if not found:
            sys.exit(f"missing tool: {name}")
        real = Path(found).resolve()
        dest = bindir / name
        shutil.copy2(real, dest)
        writable(dest)
        queue.append((dest, real, real))

    # ImageMagick coders/filters and libheif codecs are plugins loaded at runtime,
    # with their own config files; copy them and process their libraries too.
    im = Path(sh("brew", "--prefix", "imagemagick").strip())
    heif = Path(sh("brew", "--prefix", "libheif").strip())
    magick_exe = (brew / "bin" / "magick").resolve()
    copy_tree(im / "lib" / "ImageMagick", tools / "lib" / "ImageMagick", magick_exe, queue)
    copy_tree(im / "etc" / "ImageMagick-7", tools / "etc" / "ImageMagick-7", magick_exe, queue)
    copy_tree(heif / "lib" / "libheif", libdir / "libheif", magick_exe, queue)

    fonts = tools / "etc" / "fonts"
    fonts.mkdir(parents=True)
    shutil.copy2(Path(__file__).with_name("fonts.conf"), fonts / "fonts.conf")

    done = set()
    while queue:
        f, origin, exe_origin = queue.pop()
        if f in done:
            continue
        done.add(f)
        ident, deps, rpaths = load_commands(f)
        changes = []
        for dep in deps:
            if dep.startswith(SYSTEM_PREFIXES) or dep.startswith(LIB_REF):
                continue
            real = resolve(dep, origin, exe_origin, rpaths)
            if real is None:
                sys.exit(f"{f}: can't resolve {dep}")
            real_resolved = real.resolve()
            if str(real_resolved).startswith(SYSTEM_PREFIXES):
                continue
            name = Path(dep).name
            target = libdir / name
            if not target.exists():
                shutil.copy2(real_resolved, target)
                writable(target)
                sh("install_name_tool", "-id", LIB_REF + name, str(target))
                queue.append((target, real_resolved, exe_origin))
            changes += ["-change", dep, LIB_REF + name]
        for rp in rpaths:
            if not rp.startswith("@"):
                changes += ["-delete_rpath", rp]
        if changes:
            subprocess.run(["install_name_tool", *changes, str(f)], check=True,
                           stderr=subprocess.DEVNULL)
    print(f"bundled {len(TOOLS)} tools, {len(list(libdir.glob('*.dylib')))} libraries")


def verify(app):
    libdir = app / "Contents" / "Resources" / "tools" / "lib"
    bad, count = [], 0
    for f in sorted(app.rglob("*")):
        if not f.is_file() or f.is_symlink() or not is_macho(f):
            continue
        count += 1
        _, deps, rpaths = load_commands(f)
        for ref in deps + rpaths:
            if ref.startswith(("/opt/homebrew", "/usr/local", "/opt/local")):
                bad.append(f"{f.relative_to(app)} -> {ref}")
            elif ref.startswith(LIB_REF) and not (libdir / ref[len(LIB_REF):]).exists():
                bad.append(f"{f.relative_to(app)} -> missing {ref}")
    if bad:
        print("Broken or external references:\n  " + "\n  ".join(bad))
        sys.exit(1)
    print(f"verified {count} Mach-O files: everything resolves inside the app")


if __name__ == "__main__":
    if sys.argv[1] == "--verify":
        verify(Path(sys.argv[2]))
    else:
        bundle(Path(sys.argv[1]))
