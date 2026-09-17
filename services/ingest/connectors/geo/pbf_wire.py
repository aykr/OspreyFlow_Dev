"""Minimal Protocol Buffers wire-format primitives — just enough to read
(and, for the test fixture, write) an OSM PBF file's handful of message
shapes, with zero third-party dependency.

ADR-005's reasoning applies here as much as it does to extraction: the
actual requirement is "decode/encode a few fixed, well-documented message
shapes," not "embed a general protobuf runtime." A full `protobuf`
dependency pulls in a code-generation step and a licence-review question
for what is, restricted to the two wire types OSM PBF actually uses
(varint and length-delimited), well under a hundred lines either way.

Wire format reference: https://protobuf.dev/programming-guides/encoding/
"""

from __future__ import annotations

from collections.abc import Iterator

WIRE_VARINT = 0
WIRE_LEN = 2


def encode_varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("varint encoding here is unsigned only — zigzag-encode first")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def decode_varint(data: bytes, pos: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7


def zigzag_encode(value: int) -> int:
    return (value << 1) ^ (value >> 63) if value < 0 else value << 1


def zigzag_decode(value: int) -> int:
    return (value >> 1) ^ -(value & 1)


def encode_tag(field_number: int, wire_type: int) -> bytes:
    return encode_varint((field_number << 3) | wire_type)


def encode_len_field(field_number: int, payload: bytes) -> bytes:
    """A length-delimited field: a sub-message, a `bytes`/`string`, or a
    packed-repeated scalar (a caller pre-encodes the payload for any of
    the three — the wire format does not distinguish them)."""
    return encode_tag(field_number, WIRE_LEN) + encode_varint(len(payload)) + payload


def encode_varint_field(field_number: int, value: int) -> bytes:
    return encode_tag(field_number, WIRE_VARINT) + encode_varint(value)


def encode_packed_varints(values: list[int]) -> bytes:
    return b"".join(encode_varint(v) for v in values)


def iter_fields(data: bytes) -> Iterator[tuple[int, int, bytes | int]]:
    """Yields `(field_number, wire_type, value)` for every top-level field
    in one message. `value` is an `int` for `WIRE_VARINT`, the raw
    (still-encoded) `bytes` payload for `WIRE_LEN` — a caller recurses into
    it with another `iter_fields` call for a sub-message, or decodes it
    directly for a packed-repeated scalar or a plain string.

    Only the two wire types OSM PBF uses. A fixed32/fixed64 field
    (wire type 1 or 5) raises rather than silently misreading the stream —
    none of the messages this module reads ever contain one."""
    pos = 0
    while pos < len(data):
        tag, pos = decode_varint(data, pos)
        field_number, wire_type = tag >> 3, tag & 0x7
        if wire_type == WIRE_VARINT:
            value, pos = decode_varint(data, pos)
            yield field_number, wire_type, value
        elif wire_type == WIRE_LEN:
            length, pos = decode_varint(data, pos)
            yield field_number, wire_type, data[pos : pos + length]
            pos += length
        else:
            raise ValueError(f"unsupported wire type {wire_type} on field {field_number}")


def iter_packed_varints(data: bytes) -> Iterator[int]:
    pos = 0
    while pos < len(data):
        value, pos = decode_varint(data, pos)
        yield value
