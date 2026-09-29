"""`packages/geo/image_dimensions.py` — hand-constructed minimal PNG/JPEG
headers, since only the header structure matters here, never real pixel
data."""

from __future__ import annotations

import struct

import pytest

from geo.image_dimensions import (
    UnsupportedImageFormatError,
    image_content_type,
    image_dimensions,
)


def _png_bytes(width: int, height: int) -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_length = struct.pack(">I", 13)
    ihdr_type = b"IHDR"
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    fake_crc = b"\x00\x00\x00\x00"
    return signature + ihdr_length + ihdr_type + ihdr_data + fake_crc


def _jpeg_bytes(width: int, height: int) -> bytes:
    soi = b"\xff\xd8"
    # A JFIF APP0 segment first, to prove the parser skips non-SOF
    # segments rather than assuming SOF0 comes immediately after SOI.
    app0_payload = b"JFIF\x00" + b"\x01\x01" + b"\x00" + b"\x00\x01" + b"\x00\x01" + b"\x00\x00"
    app0 = b"\xff\xe0" + struct.pack(">H", len(app0_payload) + 2) + app0_payload
    sof0_payload = struct.pack(">BHH", 8, height, width) + b"\x01" + b"\x01\x11\x00"
    sof0 = b"\xff\xc0" + struct.pack(">H", len(sof0_payload) + 2) + sof0_payload
    eoi = b"\xff\xd9"
    return soi + app0 + sof0 + eoi


def test_png_dimensions_are_read_from_the_ihdr_chunk() -> None:
    assert image_dimensions(_png_bytes(1920, 1080)) == (1920, 1080)


def test_jpeg_dimensions_are_read_from_the_sof0_marker_past_other_segments() -> None:
    assert image_dimensions(_jpeg_bytes(640, 480)) == (640, 480)


def test_content_type_matches_the_same_magic_bytes_dimensions_reads() -> None:
    assert image_content_type(_png_bytes(10, 10)) == "image/png"
    assert image_content_type(_jpeg_bytes(10, 10)) == "image/jpeg"


def test_an_unrecognised_format_is_rejected_not_guessed() -> None:
    with pytest.raises(UnsupportedImageFormatError):
        image_dimensions(b"GIF89a" + b"\x00" * 20)


def test_a_truncated_png_is_rejected() -> None:
    with pytest.raises(UnsupportedImageFormatError):
        image_dimensions(_png_bytes(100, 100)[:10])


def test_a_jpeg_with_no_start_of_frame_marker_is_rejected() -> None:
    with pytest.raises(UnsupportedImageFormatError):
        image_dimensions(b"\xff\xd8" + b"\xff\xd9")
