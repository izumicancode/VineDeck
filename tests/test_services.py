import io
import json
import struct
import zipfile

import pytest
from PIL import Image

from vinedeck.database.models import Application
from vinedeck.services import export_service, filesystem_service as fs
from vinedeck.services.icon_service import extract_exe_icon
from vinedeck.services.image_service import ImageError, ImageService
from vinedeck.core.metadata import LocalMetadataProvider
from vinedeck.core.scanner import discover_prefixes


def make_png(path, size=(800, 1200), color=(200, 30, 30)):
    Image.new("RGB", size, color).save(path)
    return path


# -- images ---------------------------------------------------------------
def test_cover_import_resizes_and_thumbnails(paths, tmp_path):
    svc = ImageService(paths)
    src = make_png(tmp_path / "big.png", (3000, 2000))
    name = svc.import_cover(src)
    stored = Image.open(svc.cover_file(name))
    assert max(stored.size) == 2000 and stored.format == "WEBP"
    thumb = svc.thumbnail(name)
    t = Image.open(thumb)
    assert max(t.size) == 480 and abs(t.width / t.height - 1.5) < 0.01     # aspect preserved
    svc.delete_cover(name)
    assert svc.cover_file(name) is None and not thumb.exists()
    assert src.exists()                                                     # user's original untouched


def test_image_validation(paths, tmp_path):
    svc = ImageService(paths)
    bad = tmp_path / "fake.png"
    bad.write_text("not an image")
    with pytest.raises(ImageError):
        svc.import_cover(bad)
    with pytest.raises(ImageError):
        svc.import_cover(tmp_path / "missing.png")
    gif = tmp_path / "x.gif"
    Image.new("RGB", (4, 4)).save(gif)
    with pytest.raises(ImageError):
        svc.import_cover(gif)


def test_icon_import_is_square(paths, tmp_path):
    svc = ImageService(paths)
    name = svc.import_icon(make_png(tmp_path / "i.png", (100, 40)))
    assert Image.open(svc.icon_file(name)).size == (256, 256)


# -- exe icon extraction on a synthetic PE ----------------------------------
def build_pe(ico_png: bytes) -> bytes:
    """Minimal PE32 whose .rsrc holds one PNG icon and its group directory."""
    group = struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHIH", 0, 0, 0, 0, 1, 32, len(ico_png), 7)
    # resource layout inside the section (offsets relative to section start)
    dir_sz = 16
    root = 0
    icon_t, icon_n, icon_l = 40, 80, 120          # directories for RT_ICON
    grp_t, grp_n, grp_l = 160, 200, 240           # directories for RT_GROUP_ICON
    de_icon, de_grp = 280, 296
    data_icon = 320
    data_grp = data_icon + len(ico_png) + (-len(ico_png) % 8)
    VA = 0x1000

    def directory(entries):
        out = struct.pack("<IIHHHH", 0, 0, 0, 0, 0, len(entries))
        for ident, target in entries:
            out += struct.pack("<II", ident, target)
        return out.ljust(40, b"\0")

    sec = bytearray(data_grp + len(group) + 8)
    sec[root:root + 40] = directory([(3, 0x80000000 | icon_t), (14, 0x80000000 | grp_t)])
    sec[icon_t:icon_t + 40] = directory([(1, 0x80000000 | icon_n)])
    sec[icon_n:icon_n + 40] = directory([(0x409, de_icon)])
    sec[grp_t:grp_t + 40] = directory([(1, 0x80000000 | grp_n)])
    sec[grp_n:grp_n + 40] = directory([(0x409, de_grp)])
    sec[de_icon:de_icon + 16] = struct.pack("<IIII", VA + data_icon, len(ico_png), 0, 0)
    sec[de_grp:de_grp + 16] = struct.pack("<IIII", VA + data_grp, len(group), 0, 0)
    sec[data_icon:data_icon + len(ico_png)] = ico_png
    sec[data_grp:data_grp + len(group)] = group
    # Fix icon id in the group entry (we used id 7) by storing the icon under id 7 instead of 1
    sec[icon_t + 16 + 0: icon_t + 16 + 4] = struct.pack("<I", 7)

    e_lfanew = 0x80
    dos = bytearray(e_lfanew)
    dos[:2] = b"MZ"
    dos[0x3C:0x40] = struct.pack("<I", e_lfanew)
    opt = bytearray(224)
    opt[:2] = struct.pack("<H", 0x10B)
    opt[96 + 2 * 8: 96 + 2 * 8 + 8] = struct.pack("<II", VA, len(sec))
    coff = struct.pack("<HHIIIHH", 0x14C, 1, 0, 0, 0, len(opt), 0x102)
    raw = 0x200
    section = b".rsrc\0\0\0" + struct.pack("<IIIIIIHHI", len(sec), VA, len(sec), raw, 0, 0, 0, 0, 0x40000040)
    header = bytes(dos) + b"PE\0\0" + coff + bytes(opt) + section
    return header.ljust(raw, b"\0") + bytes(sec)


def test_exe_icon_extraction(tmp_path):
    buf = io.BytesIO()
    Image.new("RGBA", (64, 64), (10, 200, 90, 255)).save(buf, "PNG")
    exe = tmp_path / "app.exe"
    exe.write_bytes(build_pe(buf.getvalue()))
    img = extract_exe_icon(exe)
    assert img is not None and img.size == (64, 64) and img.getpixel((5, 5))[:3] == (10, 200, 90)


def test_exe_icon_failures_return_none(tmp_path):
    for content in (b"", b"MZ", b"hello", b"MZ" + b"\0" * 200, bytes(range(256)) * 20):
        f = tmp_path / "bad.exe"
        f.write_bytes(content)
        assert extract_exe_icon(f) is None
    assert extract_exe_icon(tmp_path / "missing.exe") is None


# -- filesystem / metadata / scanner -----------------------------------------
def test_validate_executable(tmp_path, exe):
    assert fs.validate_executable(str(exe)) is None
    assert fs.validate_executable("") is not None
    assert "exist" in fs.validate_executable(str(tmp_path / "no.exe"))
    txt = tmp_path / "a.txt"
    txt.write_text("x")
    assert ".exe" in fs.validate_executable(str(txt))
    assert fs.validate_executable(str(tmp_path)) is not None
    assert fs.validate_directory("") is None and fs.validate_directory("/nope") is not None


def test_local_metadata_name_guess():
    assert LocalMetadataProvider().lookup("/g/Cyberpunk2077.exe").name == "Cyberpunk2077"
    assert LocalMetadataProvider().lookup("/g/my_cool-game.exe").name == "my cool game"
    assert LocalMetadataProvider().lookup("/g/FooBar.exe").name == "Foo Bar"


def test_discover_prefixes(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("WINEPREFIX", raising=False)
    pfx = tmp_path / "Games" / "GameA"
    pfx.mkdir(parents=True)
    (pfx / "system.reg").write_text("")
    (tmp_path / "Games" / "NotAPrefix").mkdir()
    assert discover_prefixes() == [pfx]


# -- export / import ---------------------------------------------------------
def test_export_import_roundtrip(paths, db, tmp_path):
    images = ImageService(paths)
    cover = images.import_cover(make_png(tmp_path / "c.png"))
    games = db.get_category_by_name("Games")
    db.add_category("RPG")
    db.add_application(Application(name="One", executable_path="/a/one.exe", category_id=games.id,
                                   cover_path=cover, env_vars={"A": "1"}, favorite=True, developer="D"))
    db.add_application(Application(name="Two", executable_path="/a/two.exe"))

    plain = tmp_path / "lib.json"
    assert export_service.export_library(db, paths, plain, include_artwork=False) == 2
    assert json.loads(plain.read_text())["format"] == "library-export"

    bundle = tmp_path / "lib.zip"
    export_service.export_library(db, paths, bundle, include_artwork=True)
    assert any(n.startswith("artwork/covers/") for n in zipfile.ZipFile(bundle).namelist())

    from vinedeck.database.database import Database
    other = Database(":memory:")
    res = export_service.import_library(other, paths, bundle, images)
    assert (res.added, res.skipped) == (2, 0)
    one = [a for a in other.list_applications() if a.name == "One"][0]
    assert one.category_name == "Games" and one.favorite and one.env_vars == {"A": "1"} and one.developer == "D"
    assert one.cover_path and images.cover_file(one.cover_path)
    assert other.get_category_by_name("RPG")
    again = export_service.import_library(other, paths, plain, images)       # merge is idempotent
    assert (again.added, again.skipped) == (0, 2)


def test_import_rejects_garbage(paths, mem_db, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"hello": 1}')
    with pytest.raises(export_service.ExportError):
        export_service.import_library(mem_db, paths, bad)
    bad.write_text("nope")
    with pytest.raises(export_service.ExportError):
        export_service.import_library(mem_db, paths, bad)
