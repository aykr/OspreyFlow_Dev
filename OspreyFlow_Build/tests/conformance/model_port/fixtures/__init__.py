"""Fixtures for `ModelPort`'s `transcribe()`/`describe_image()` conformance cases.

`sample_speech.wav` is synthetic TTS output (no real intelligence data, ever)
— generated once via macOS `say -o sample_speech.aiff "testing one two three"` then `ffmpeg -i
sample_speech.aiff -ar 16000 -ac 1 -sample_fmt s16 sample_speech.wav`, and committed rather than
regenerated at test time because `say`/`ffmpeg` are not available on every CI runner. A pure
sine-tone WAV built from stdlib alone was tried first and rejected: Whisper correctly transcribes
it as silence (`segments: []`), which exercises no field of `TranscriptSegment` at all — a
committed short recording of real (synthetic) speech is what actually exercises the mapping.

The vision fixture is not committed, deliberately: a valid, decodable PNG is fully and
deterministically reproducible from the standard library (`zlib`, `struct`) with no external tool,
so `png_bytes()` below builds one fresh every run rather than shipping a binary nobody can diff.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

SAMPLE_SPEECH_WAV = (Path(__file__).parent / "sample_speech.wav").read_bytes()


def png_bytes(width: int = 64, height: int = 64, rgb: tuple[int, int, int] = (255, 0, 0)) -> bytes:
    """A minimal but fully valid, decodable single-colour PNG — confirmed directly to decode
    correctly through a real vision-language model (`06_DECISIONS.md` ADR-020's Stage 2 addendum),
    not merely well-formed enough to satisfy a parser that never renders it."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    row = bytes([0]) + bytes(rgb) * width  # filter-type byte, then RGB pixels
    idat = chunk(b"IDAT", zlib.compress(row * height, 9))
    iend = chunk(b"IEND", b"")
    return signature + ihdr + idat + iend
