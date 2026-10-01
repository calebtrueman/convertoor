import json
import os
import shutil
import subprocess
import sys
import zipfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from convertoor import datafmt, engine  # noqa: E402
from convertoor import formats as F  # noqa: E402


def have(*tools):
    return all(shutil.which(t) for t in tools)


# ---- formats ----------------------------------------------------------------

@pytest.mark.parametrize("name,fmt", [
    ("a.JPEG", "jpg"), ("b.tif", "tiff"), ("c.tar.gz", "tar.gz"), ("d.tgz", "tar.gz"),
    ("e.markdown", "md"), ("f.yml", "yaml"), ("g.heif", "heic"), ("noext", None),
    ("x.unknownext", None), ("archive.TAR.XZ", "tar.xz"),
])
def test_detect(name, fmt):
    assert F.detect(name) == fmt


def test_stem():
    assert F.stem("/x/y/report.final.docx") == "report.final"
    assert F.stem("backup.tar.gz") == "backup"


def test_every_format_has_valid_category():
    for fmt, (desc, cat) in F.FORMATS.items():
        assert cat in F.CATEGORY_LABELS, fmt
        assert desc


# ---- routing ----------------------------------------------------------------

class Fake(engine.Backend):
    def __init__(self, name, edges):
        self.name = name
        self.edges = edges

    def path(self):
        return "fake"

    def targets(self, src):
        return self.edges.get(src, [])


def test_plan_direct_and_chained():
    a = Fake("pandoc", {"md": ["docx", "html"]})
    b = Fake("office", {"docx": ["pdf"], "html": ["pdf"]})
    assert [(s[1], s[2]) for s in engine.plan("md", "docx", [a, b])] == [("md", "docx")]
    steps = engine.plan("md", "pdf", [a, b])
    assert [(s[0].name, s[1], s[2]) for s in steps] == [("pandoc", "md", "docx"),
                                                        ("office", "docx", "pdf")]


def test_plan_respects_priority_and_no_route():
    first = Fake("first", {"png": ["jpg"]})
    second = Fake("second", {"png": ["jpg"]})
    assert engine.plan("png", "jpg", [first, second])[0][0] is first
    assert engine.plan("png", "mp3", [first, second]) is None


def test_plan_does_not_transit_lossy_formats():
    g = Fake("g", {"png": ["gif"], "gif": ["mp4"]})
    assert engine.plan("png", "mp4", [g]) is None


def test_targets_are_known_formats():
    for fmt in ("png", "mp4", "mp3", "docx", "json", "zip"):
        for t in engine.targets(fmt):
            assert t in F.FORMATS and t != fmt


# ---- data formats -----------------------------------------------------------

DATA = [{"name": "Ada", "age": 36, "langs": ["en", "fr"], "meta": {"born": 1815}},
        {"name": "Linus", "age": 54, "active": True}]


@pytest.mark.parametrize("fmt", ["xml", "toml", "csv", "tsv"]
                         + (["yaml"] if "yaml" in datafmt.supported()["read"] else []))
def test_data_roundtrip(tmp_path, fmt):
    src = tmp_path / "people.json"
    src.write_text(json.dumps(DATA))
    out = engine.convert_file(src, fmt)
    assert len(out) == 1 and out[0].suffix == "." + fmt
    text = out[0].read_text()
    assert "Ada" in text and "Linus" in text
    if fmt in datafmt.supported()["read"]:
        back = datafmt.load(text, fmt)
        assert back


def test_toml_output_is_valid(tmp_path):
    try:
        import tomllib
    except ImportError:
        tomllib = pytest.importorskip("tomli")
    text = datafmt.dump({"title": "x", "owner": {"name": "y"}, "items": DATA}, "toml")
    parsed = tomllib.loads(text)
    assert parsed["owner"]["name"] == "y"
    assert parsed["items"][1]["active"] is True


def test_csv_to_json_types(tmp_path):
    src = tmp_path / "t.csv"
    src.write_text("a,b,c\n1,2.5,true\n,x,\n")
    out = engine.convert_file(src, "json")[0]
    rows = json.loads(out.read_text())
    assert rows[0] == {"a": 1, "b": 2.5, "c": True}


def test_output_names_never_overwrite(tmp_path):
    src = tmp_path / "d.json"
    src.write_text("{}")
    first = engine.convert_file(src, "yaml" if "yaml" in datafmt.supported()["write"] else "xml")
    second = engine.convert_file(src, first[0].suffix[1:])
    assert first[0] != second[0] and second[0].name.startswith("d (1)")
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".convertoor-")]


# ---- archives ---------------------------------------------------------------

def test_zip_to_tar_gz(tmp_path):
    src = tmp_path / "a.zip"
    with zipfile.ZipFile(src, "w") as zf:
        zf.writestr("dir/hello.txt", "hi")
    out = engine.convert_file(src, "tar.gz", tmp_path / "out")[0]
    assert out.name == "a.tar.gz"
    import tarfile
    with tarfile.open(out) as tf:
        assert "dir/hello.txt" in tf.getnames()


# ---- tool-backed conversions (skipped when the tool is missing) -------------

@pytest.mark.skipif(not have("ffmpeg"), reason="ffmpeg missing")
def test_audio_and_video(tmp_path):
    wav = tmp_path / "tone.wav"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=1", str(wav)], check=True)
    for fmt in ("mp3", "flac", "ogg", "m4a"):
        out = engine.convert_file(wav, fmt)[0]
        assert out.stat().st_size > 0
    mp4 = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc=duration=1:size=160x120:rate=10", "-pix_fmt", "yuv420p", str(mp4)],
                   check=True)
    progress = []
    job = engine.Job(progress.append)
    for fmt in ("webm", "gif", "mkv"):
        assert engine.convert_file(mp4, fmt, job=job)[0].stat().st_size > 0
    assert any(p is not None for p in progress)


@pytest.mark.skipif(not (have("magick") or have("convert")), reason="ImageMagick missing")
def test_images(tmp_path):
    png = tmp_path / "img.png"
    tool = shutil.which("magick") or shutil.which("convert")
    subprocess.run([tool, "-size", "64x48", "gradient:red-blue", str(png)], check=True)
    for fmt in ("jpg", "webp", "bmp", "tiff", "ico", "gif", "pdf"):
        out = engine.convert_file(png, fmt)[0]
        assert out.stat().st_size > 0, fmt


@pytest.mark.skipif(not have("rsvg-convert"), reason="librsvg missing")
def test_svg(tmp_path):
    svg = tmp_path / "a.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
                   '<rect width="10" height="10" fill="red"/></svg>')
    assert engine.convert_file(svg, "png")[0].read_bytes()[:4] == b"\x89PNG"


@pytest.mark.skipif(not have("pandoc"), reason="pandoc missing")
def test_markdown(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text("# Title\n\nSome *text* & stuff.\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")
    for fmt in ("html", "docx", "odt", "epub", "rst", "txt"):
        assert engine.convert_file(md, fmt)[0].stat().st_size > 0, fmt


@pytest.mark.skipif(not (have("pandoc") and (have("soffice") or have("libreoffice"))),
                    reason="pandoc/libreoffice missing")
def test_markdown_to_pdf_chain(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text("# Hello\n\nChained conversion.\n")
    out = engine.convert_file(md, "pdf")[0]
    assert out.read_bytes()[:4] == b"%PDF"


@pytest.mark.skipif(not (have("soffice") or have("libreoffice")), reason="libreoffice missing")
def test_csv_to_xlsx(tmp_path):
    csv = tmp_path / "t.csv"
    csv.write_text("a,b\n1,2\n")
    out = engine.convert_file(csv, "xlsx")[0]
    assert zipfile.is_zipfile(out)


@pytest.mark.skipif(not have("pdftoppm", "pandoc") or not (have("soffice") or have("libreoffice")),
                    reason="poppler/pandoc/libreoffice missing")
def test_document_to_png_pages(tmp_path):
    md = tmp_path / "pages.md"
    md.write_text("# One\n\n" + "\n\n".join("para %d" % i for i in range(5)))
    outs = engine.convert_file(md, "png")
    assert outs and all(o.read_bytes()[:4] == b"\x89PNG" for o in outs)
