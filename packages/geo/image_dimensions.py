"""Width/height extraction from an uploaded site image's raw bytes —
`spec/00_ARCHITECTURE.md` §1.2's site-plan case, `08_ACCEPTANCE_SCENARIOS.md`
A1. A hand-rolled PNG/JPEG header reader rather than a full image library:
the only thing this feature needs from the file is its pixel dimensions,
never decoding or re-encoding, and this build already established the same
"read only the header structure you actually need" approach for a binary
format in `services/ingest/connectors/geo/pbf_wire.py`. PNG and JPEG only —
the two formats a real aerial/site photograph or scan realistically
arrives in; an unrecognised format is rejected by name, not guessed at,
the same "reject rather than guess" discipline `00_ARCHITECTURE.md` §1.2.2
applies to an undeclared CRS.
"""

from __future__ import annotations

import struct


class UnsupportedImageFormatError(Exception):
    """Raised for anything that isn't a well-formed PNG or JPEG header —
    no attempt to guess dimensions from an unrecognised or malformed
    format."""


_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_JPEG_SOI = b"\xff\xd8"

# SOF0-SOF15 except DHT (0xC4), JPG (0xC8) and DAC (0xCC), which share the
# 0xCx range but are not start-of-frame markers.
_JPEG_SOF_MARKERS = frozenset(
    {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
)
# Markers with no length-prefixed payload to skip over.
_JPEG_STANDALONE_MARKERS = frozenset({0x01, 0xD8, 0xD9, *range(0xD0, 0xD8)})


def image_dimensions(data: bytes) -> tuple[int, int]:
    """Returns `(width_px, height_px)`. Raises `UnsupportedImageFormatError`
    for anything that isn't a well-formed PNG or JPEG header."""
    if data.startswith(_PNG_SIGNATURE):
        return _png_dimensions(data)
    if data.startswith(_JPEG_SOI):
        return _jpeg_dimensions(data)
    raise UnsupportedImageFormatError("unrecognised image format — only PNG and JPEG are supported")


def image_content_type(data: bytes) -> str:
    """The MIME type the `GET .../sites/{id}/image` proxy route serves the
    stored bytes back as — read from the same magic-byte prefix
    `image_dimensions` already checks, not stored separately, so the two
    can never disagree about what format a file is."""
    if data.startswith(_PNG_SIGNATURE):
        return "image/png"
    if data.startswith(_JPEG_SOI):
        return "image/jpeg"
    raise UnsupportedImageFormatError("unrecognised image format — only PNG and JPEG are supported")


def _png_dimensions(data: bytes) -> tuple[int, int]:
    # Signature (8) + IHDR chunk length (4) + "IHDR" (4) = 16, then width
    # (4, big-endian) and height (4, big-endian) — the first chunk in any
    # well-formed PNG is always IHDR, first field always width/height.
    if len(data) < 24:
        raise UnsupportedImageFormatError("PNG file is too short to contain an IHDR chunk")
    if data[12:16] != b"IHDR":
        raise UnsupportedImageFormatError("PNG file's first chunk is not IHDR")
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def _jpeg_dimensions(data: bytes) -> tuple[int, int]:
    offset = 2  # past the SOI marker
    length = len(data)
    while offset < length:
        if data[offset] != 0xFF:
            raise UnsupportedImageFormatError("JPEG file is malformed: expected a marker")
        marker = data[offset + 1]
        offset += 2
        if marker in _JPEG_STANDALONE_MARKERS:
            continue
        if offset + 2 > length:
            raise UnsupportedImageFormatError("JPEG file is truncated")
        segment_length = struct.unpack(">H", data[offset : offset + 2])[0]
        if marker in _JPEG_SOF_MARKERS:
            # Precision (1) + height (2) + width (2), big-endian, right
            # after the 2-byte segment length.
            if offset + 7 > length:
                raise UnsupportedImageFormatError("JPEG start-of-frame segment is truncated")
            height, width = struct.unpack(">HH", data[offset + 3 : offset + 7])
            return width, height
        offset += segment_length
    raise UnsupportedImageFormatError("JPEG file has no start-of-frame marker")
