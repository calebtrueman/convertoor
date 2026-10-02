"""Command-line interface. With no conversion flags it launches the GUI."""

from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import __version__
from . import engine
from . import formats as F


def _parser():
    p = argparse.ArgumentParser(
        prog="convertoor",
        description="Convert images, audio, video, documents, ebooks, data, archives and fonts. "
                    "Run without -t to open the drag-and-drop window.",
    )
    p.add_argument("files", nargs="*", help="files (or folders) to convert")
    p.add_argument("-t", "--to", metavar="FORMAT", help="convert FILES to FORMAT without the GUI")
    p.add_argument("-o", "--output", metavar="DIR", help="output folder (default: next to each file)")
    p.add_argument("-j", "--jobs", type=int, default=2, help="parallel conversions (default 2)")
    p.add_argument("--targets", action="store_true", help="list formats each FILE can become")
    p.add_argument("--formats", action="store_true", help="list every known format")
    p.add_argument("--doctor", action="store_true", help="show which converters are installed")
    p.add_argument("--self-test", nargs=2, metavar=("FILE", "FORMAT"), help=argparse.SUPPRESS)
    p.add_argument("-V", "--version", action="version", version=f"convertoor {__version__}")
    return p


def expand(paths):
    out = []
    for path in paths:
        if os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                dirs[:] = sorted(d for d in dirs if not d.startswith("."))
                out += [os.path.join(root, f) for f in sorted(files) if not f.startswith(".")]
        else:
            out.append(path)
    return out


def doctor():
    print(f"Convertoor {__version__}\n")
    for b in engine.BACKENDS:
        path = b.path()
        mark = "✔" if path else "✘"
        where = path if path and path not in ("builtin",) else ("built in" if path else
                                                                 f"missing — install {b.install_hint}")
        print(f" {mark} {b.name:<16} {b.description}\n   {'':<16} {where}")
        if not path and b.required_for:
            print(f"   {'':<16} required for: {b.required_for}")
    return 0


def list_formats():
    by_cat = {}
    for fmt, (desc, cat) in F.FORMATS.items():
        by_cat.setdefault(cat, []).append(fmt)
    for cat, fmts in by_cat.items():
        print(f"{F.CATEGORY_LABELS[cat]}: {' '.join(fmts)}")
    return 0


def list_targets(files):
    for path in files:
        fmt = F.detect(path)
        if not fmt:
            print(f"{path}: unrecognised file type")
            continue
        t = engine.targets(fmt)
        missing = engine.missing_backends(fmt)
        print(f"{path} ({fmt}): {' '.join(t) if t else '(none)'}")
        for b in missing:
            what = "required" if not t else "needed for more formats"
            print(f"  {b.name} {what} — install: {b.install_hint}")
    return 0


def convert_cli(files, target, output, jobs):
    target = F.canonical(target) or target.lower().lstrip(".")
    if target not in F.FORMATS:
        print(f"Unknown format: {target}", file=sys.stderr)
        return 2
    failures = 0

    def one(path):
        return path, engine.convert_file(path, target, output)

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        futures = [pool.submit(one, f) for f in files]
        for fut in as_completed(futures):
            try:
                path, outs = fut.result()
                for o in outs:
                    print(f"✔ {path} → {o}")
            except engine.ConversionError as exc:
                failures += 1
                print(f"✘ {exc}", file=sys.stderr)
    return 1 if failures else 0


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.doctor:
        return doctor()
    if args.formats:
        return list_formats()
    files = expand(args.files)
    if args.targets:
        return list_targets(files)
    if args.to:
        if not files:
            print("No input files given", file=sys.stderr)
            return 2
        return convert_cli(files, args.to, args.output, args.jobs)
    try:
        from .gui import run_gui
    except (ImportError, ValueError) as exc:
        print(f"Can't start the GUI ({exc}).\n"
              "Install GTK 4, libadwaita and PyGObject, or use: convertoor -t FORMAT FILES",
              file=sys.stderr)
        return 1
    return run_gui(files, self_test=args.self_test)
