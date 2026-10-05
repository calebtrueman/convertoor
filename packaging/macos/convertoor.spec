# PyInstaller spec for Convertoor.app. Run through packaging/macos/build.sh.
import os
import platform

from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
VERSION = os.environ["CONVERTOOR_VERSION"]
BREW = os.environ["HOMEBREW_PREFIX"]
ICNS = os.environ["CONVERTOOR_ICNS"]
APP_ID = "io.github.calebtrueman.Convertoor"
MIN_MACOS = platform.mac_ver()[0].split(".")[0] + ".0"

datas = [
    (os.path.join(BREW, "share/icons/Adwaita"), "share/icons/Adwaita"),
    (os.path.join(BREW, "share/icons/hicolor/index.theme"), "share/icons/hicolor"),
    (os.path.join(ROOT, f"data/icons/{APP_ID}.svg"), "share/icons/hicolor/scalable/apps"),
]

a = Analysis(
    [os.path.join(SPECPATH, "launcher.py")],
    pathex=[os.path.join(ROOT, "src")],
    datas=datas,
    hiddenimports=collect_submodules("convertoor") + collect_submodules("fontTools.ttLib")
    + ["yaml", "brotli", "fontTools.ttLib.woff2"],
    hooksconfig={
        "gi": {
            "icons": ["Adwaita", "hicolor"],
            "themes": ["Adwaita"],
            "languages": ["en_US"],
            "module-versions": {"Gtk": "4.0", "Gdk": "4.0", "Gsk": "4.0"},
        }
    },
    excludes=["tkinter", "PyQt5", "PyQt6", "PySide6", "IPython", "numpy"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Convertoor",
    console=False,
    argv_emulation=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Convertoor")
app = BUNDLE(
    coll,
    name="Convertoor.app",
    icon=ICNS,
    bundle_identifier=APP_ID,
    version=VERSION,
    info_plist={
        "CFBundleName": "Convertoor",
        "CFBundleDisplayName": "Convertoor",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "LSMinimumSystemVersion": MIN_MACOS,
        "LSApplicationCategoryType": "public.app-category.utilities",
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,
        "NSHumanReadableCopyright": "© 2026 Caleb Trueman. MIT License.",
    },
)
