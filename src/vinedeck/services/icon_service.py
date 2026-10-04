"""Extracts the main icon from a Windows executable (best effort).

A small, bounds-checked PE resource parser: it only *reads* the file and never
executes it. Any failure simply returns ``None``; icons are never required.
"""

from __future__ import annotations

import io
import mmap
import struct
from pathlib import Path

from PIL import Image, IcoImagePlugin

from ..utils.logging import get_logger

log = get_logger("icons")

RT_ICON, RT_GROUP_ICON = 3, 14
_MAX_ENTRIES = 512


class _Bad(Exception):
    pass


def _u16(d, o):
    return struct.unpack_from("<H", d, o)[0]


def _u32(d, o):
    return struct.unpack_from("<I", d, o)[0]


def _resource_blobs(data) -> dict[int, dict[int, bytes]]:
    """Return ``{resource_type: {name_id: raw_bytes}}`` for icons and icon groups."""
    if data[:2] != b"MZ":
        raise _Bad("not an MZ executable")
    pe = _u32(data, 0x3C)
    if data[pe:pe + 4] != b"PE\0\0":
        raise _Bad("no PE header")
    n_sections = _u16(data, pe + 6)
    opt_size = _u16(data, pe + 20)
    opt = pe + 24
    magic = _u16(data, opt)
    if magic not in (0x10B, 0x20B):
        raise _Bad("unknown optional header")
    dirs = opt + (96 if magic == 0x10B else 112)
    res_rva = _u32(data, dirs + 2 * 8)
    if not res_rva:
        raise _Bad("no resources")
    sections = []
    sec = opt + opt_size
    for i in range(min(n_sections, 96)):
        o = sec + i * 40
        vsize, va, rawsize, rawptr = struct.unpack_from("<IIII", data, o + 8)
        sections.append((va, max(vsize, rawsize), rawptr))

    def rva_to_off(rva: int) -> int:
        for va, size, raw in sections:
            if va <= rva < va + size:
                return raw + (rva - va)
        raise _Bad("RVA outside sections")

    root = rva_to_off(res_rva)

    def entries(off: int):
        n = _u16(data, off + 12) + _u16(data, off + 14)
        if n > _MAX_ENTRIES:
            raise _Bad("too many entries")
        for i in range(n):
            name, target = struct.unpack_from("<II", data, off + 16 + i * 8)
            yield name, bool(target & 0x80000000), target & 0x7FFFFFFF

    def leaf(off: int, is_dir: bool, depth: int) -> bytes:
        while is_dir:
            if depth > 4:
                raise _Bad("resource tree too deep")
            first = next(iter(entries(off)), None)       # first language
            if first is None:
                raise _Bad("empty directory")
            _, is_dir, rel = first
            off = root + rel
            depth += 1
        rva, size = struct.unpack_from("<II", data, off)
        start = rva_to_off(rva)
        if size > 8 * 1024 * 1024 or start + size > len(data):
            raise _Bad("bad resource size")
        return bytes(data[start:start + size])

    out: dict[int, dict[int, bytes]] = {RT_ICON: {}, RT_GROUP_ICON: {}}
    for type_id, is_dir, rel in entries(root):
        if type_id not in out or type_id & 0x80000000 or not is_dir:
            continue
        for name_id, name_is_dir, name_rel in entries(root + rel):
            if name_id & 0x80000000:
                continue
            try:
                out[type_id][name_id] = leaf(root + name_rel, name_is_dir, 2)
            except (_Bad, struct.error):
                continue
    return out


def _build_ico(blobs: dict[int, dict[int, bytes]]) -> bytes:
    groups = blobs[RT_GROUP_ICON]
    if not groups:
        raise _Bad("no icon group")
    group = groups[min(groups)]                    # lowest id is the main application icon
    _, _, count = struct.unpack_from("<HHH", group, 0)
    members = []
    for i in range(min(count, 32)):
        w, h, colors, _r, planes, bits, size, icon_id = struct.unpack_from("<BBBBHHIH", group, 6 + i * 14)
        payload = blobs[RT_ICON].get(icon_id)
        if payload:
            members.append((w, h, colors, planes, bits, payload))
    if not members:
        raise _Bad("icon images missing")
    header = struct.pack("<HHH", 0, 1, len(members))
    offset = 6 + 16 * len(members)
    directory, body = b"", b""
    for w, h, colors, planes, bits, payload in members:
        directory += struct.pack("<BBBBHHII", w, h, colors, 0, planes, bits, len(payload), offset)
        body += payload
        offset += len(payload)
    return header + directory + body


def extract_exe_icon(path: str | Path) -> Image.Image | None:
    """Return the largest icon in the executable as an RGBA image, or None."""
    p = Path(path).expanduser()
    if p.suffix.lower() != ".exe" or not p.is_file():
        return None
    try:
        with open(p, "rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            ico_bytes = _build_ico(_resource_blobs(mm))
        ico = IcoImagePlugin.IcoFile(io.BytesIO(ico_bytes))
        best = max(ico.sizes(), key=lambda s: s[0] * s[1])
        return ico.getimage(best).convert("RGBA")
    except (_Bad, struct.error, OSError, ValueError, KeyError, SyntaxError, Image.DecompressionBombError) as exc:
        log.debug("No icon extracted from %s: %s", p.name, exc)
        return None
