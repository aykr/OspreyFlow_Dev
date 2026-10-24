"""The Prison Intelligence Dataset's pictures: small, synthetic, drawn in code (ADR-120 Amendment 9
decision 8; brief 5.7a).

`draw_picture(subject_key, kind, seed)` returns an 8-bit RGB PNG, 256 by 256 pixels, a few
kilobytes, with correct chunk CRCs. It is drawn from nothing but its arguments: shapes in colours
taken from a SHA-256 of the key, the kind and the seed, and a strip of cells along the foot that
carries thirty-two more bits of the same hash, so that no two subjects, however alike their
shapes, are drawn the same byte for byte (the picture route keys a Document by its content, so two
equal pictures would become one Document depicting two entities).

Standard library only, and it imports nothing from `pid_plan`: a yard's picture is a function of its
key alone, so nothing in it can show which yards are the throw-over hotspots (the analyst must find
them on the map). It reads no file: no font, template or stock image.

Byte-identical output means on one interpreter and one `zlib` build.
"""

from __future__ import annotations

import hashlib
import struct
import zlib
from collections.abc import Callable, Sequence

SIZE = 256
KINDS = ("person", "establishment", "wing", "yard", "handset", "group")
_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_STRIP_TOP = 240

Colour = bytes


class _Canvas:
    def __init__(self, background: Colour) -> None:
        self.rows = [bytearray(background * SIZE) for _ in range(SIZE)]

    def rect(self, x0: int, y0: int, x1: int, y1: int, colour: Colour) -> None:
        x0, x1 = max(0, x0), min(SIZE, x1)
        if x1 <= x0:
            return
        span = colour * (x1 - x0)
        for y in range(max(0, y0), min(SIZE, y1)):
            self.rows[y][x0 * 3 : x1 * 3] = span

    def disc(self, cx: int, cy: int, radius: int, colour: Colour) -> None:
        for y in range(max(0, cy - radius), min(SIZE, cy + radius + 1)):
            half = int((radius * radius - (y - cy) ** 2) ** 0.5)
            self.rect(cx - half, y, cx + half + 1, y + 1, colour)

    def png(self) -> bytes:
        return _encode(SIZE, SIZE, [bytes(row) for row in self.rows])


def _chunk(tag: bytes, body: bytes) -> bytes:
    return (
        struct.pack(">I", len(body))
        + tag
        + body
        + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)
    )


def _encode(width: int, height: int, scanlines: Sequence[bytes]) -> bytes:
    raw = b"".join(b"\x00" + line for line in scanlines)
    return (
        _SIGNATURE
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(raw, 9))
        + _chunk(b"IEND", b"")
    )


def _colour(digest: bytes, at: int, low: int = 50, high: int = 200) -> Colour:
    span = high - low
    return bytes(low + digest[(at + i) % 32] * span // 255 for i in range(3))


def _person(c: _Canvas, d: bytes, ink: Callable[[int], Colour]) -> None:
    cx = 128 + d[8] % 24 - 12
    c.rect(cx - 70, 170, cx + 70, 240, ink(1))  # shoulders
    c.rect(cx - 16, 140, cx + 16, 175, ink(2))  # neck
    c.disc(cx, 100 + d[9] % 16, 46, ink(2))  # head
    c.rect(cx - 46, 60, cx + 46, 70 + d[10] % 20, ink(3))  # hair


def _establishment(c: _Canvas, d: bytes, ink: Callable[[int], Colour]) -> None:
    c.rect(40, 90, 216, 240, ink(1))  # the block
    c.rect(112, 40, 144, 90, ink(2))  # the gate tower
    for row in range(3 + d[8] % 2):
        for col in range(5):
            c.rect(56 + col * 32, 104 + row * 32, 76 + col * 32, 124 + row * 32, ink(3))


def _wing(c: _Canvas, d: bytes, ink: Callable[[int], Colour]) -> None:
    c.rect(24, 100, 232, 200, ink(1))
    c.rect(24, 90, 232, 100, ink(2))  # the roof
    for col in range(8):
        c.rect(36 + col * 25, 120 + d[8 + col] % 10, 52 + col * 25, 150, ink(3))


def _yard(c: _Canvas, d: bytes, ink: Callable[[int], Colour]) -> None:
    c.rect(24, 40, 232, 224, ink(1))  # the ground
    c.rect(24, 40, 232, 48, ink(2))  # the wall
    c.rect(24, 216, 232, 224, ink(2))
    for col in range(9):
        c.rect(30 + col * 24, 60, 34 + col * 24, 204, ink(3))  # the fence
    c.disc(60 + d[8] % 136, 120 + d[9] % 60, 12, ink(2))


def _handset(c: _Canvas, d: bytes, ink: Callable[[int], Colour]) -> None:
    c.rect(88, 30, 168, 220, ink(1))
    c.rect(96, 48, 160, 176, ink(2))  # the screen
    c.disc(128, 198, 10, ink(3))
    c.rect(112, 36, 144, 42 + d[8] % 4, ink(3))


def _group(c: _Canvas, d: bytes, ink: Callable[[int], Colour]) -> None:
    for i, cx in enumerate((72, 128, 184)):
        c.disc(cx, 100 + d[8 + i] % 14, 30, ink(i + 1))
        c.rect(cx - 36, 150, cx + 36, 220, ink(i + 1))


_DRAWERS: dict[str, Callable[[_Canvas, bytes, Callable[[int], Colour]], None]] = {
    "person": _person,
    "establishment": _establishment,
    "wing": _wing,
    "yard": _yard,
    "handset": _handset,
    "group": _group,
}


def draw_picture(subject_key: str, kind: str, seed: int) -> bytes:
    """The picture of one subject. `ValueError` for a kind that is not one of `KINDS`."""
    drawer = _DRAWERS.get(kind)
    if drawer is None:
        raise ValueError(f"unknown picture kind {kind!r}: expected one of {', '.join(KINDS)}")
    digest = hashlib.sha256(f"{seed}|{kind}|{subject_key}".encode()).digest()
    canvas = _Canvas(_colour(digest, 0, 200, 250))
    drawer(canvas, digest, lambda n: _colour(digest, 3 * n))
    # The foot: thirty-two cells, one per bit of the hash's last four bytes.
    bits = int.from_bytes(digest[28:], "big")
    on, off = _colour(digest, 20, 20, 90), _colour(digest, 23, 150, 230)
    for cell in range(32):
        canvas.rect(cell * 8, _STRIP_TOP, cell * 8 + 8, SIZE, on if bits >> cell & 1 else off)
    return canvas.png()


def _decode(data: bytes) -> tuple[int, int, list[bytes]]:
    """The scanlines of a PNG this module wrote: 8-bit RGB, every row filter 0."""
    if not data.startswith(_SIGNATURE):
        raise ValueError("not a PNG")
    pos, idat, header = len(_SIGNATURE), b"", b""
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        tag, body = data[pos + 4 : pos + 8], data[pos + 8 : pos + 8 + length]
        if tag == b"IHDR":
            header = body
        elif tag == b"IDAT":
            idat += body
        pos += 12 + length
    width, height, depth, colour = struct.unpack(">IIBB", header[:10])
    if (depth, colour) != (8, 2):
        raise ValueError("only 8-bit RGB pictures can be tiled")
    raw = zlib.decompress(idat)
    stride = 1 + width * 3
    lines = []
    for row in range(height):
        line = raw[row * stride : (row + 1) * stride]
        if line[0] != 0:
            raise ValueError("only unfiltered scanlines can be tiled")
        lines.append(line[1:])
    return width, height, lines


def contact_sheet(
    pictures: Sequence[bytes], *, columns: int = 6, tile: int = 128
) -> bytes:
    """The pictures tiled in a grid, each shrunk to `tile` pixels square by taking every n-th
    pixel, left to right and top to bottom; a short last row is left grey."""
    if not pictures:
        raise ValueError("a contact sheet needs at least one picture")
    rows = -(-len(pictures) // columns)
    grey = b"\xd0\xd0\xd0"
    lines = [bytearray(grey * (columns * tile)) for _ in range(rows * tile)]
    for index, data in enumerate(pictures):
        width, height, source = _decode(data)
        if width % tile or height % tile:
            raise ValueError(f"a {width} by {height} picture does not shrink to {tile} pixels")
        step_x, step_y = width // tile, height // tile
        left, top = (index % columns) * tile, (index // columns) * tile
        for y in range(tile):
            line = source[y * step_y]
            shrunk = b"".join(line[x * step_x * 3 : x * step_x * 3 + 3] for x in range(tile))
            lines[top + y][left * 3 : (left + tile) * 3] = shrunk
    return _encode(columns * tile, rows * tile, [bytes(line) for line in lines])
