"""`grid_ref` — `01_DOMAIN_MODEL.md` §7. UK source documents quote a
British National Grid reference directly rather than a raw easting and
northing — the HMP analysis itself is a grid — so parsing one is not
optional for the target geography (ADR-017).

A grid reference is always EPSG:27700, by construction, so unlike
`coordinate_lon`/`coordinate_lat`/`geometry_ref` there is no `source_crs`
to declare or guess — the two-letter prefix *is* the declaration.

Two input shapes, matching `01_DOMAIN_MODEL.md` §7's table entry
("letter pair plus digits, or a bare easting/northing pair"):

- **One column, a bare reference string** — `"TG 23324 08791"`,
  `"TG2332408791"`, mixed case, arbitrary internal spacing.
- **Three columns** — the letter pair and the easting/northing already
  split by the source system, e.g. `grid_letters="TG"`,
  `easting="23324"`, `northing="08791"`. `FieldBinding.fields` of length
  three, since `grid_ref` declares arity 3 for the multi-column form
  (`knowledge_adapters.ARITY`).

The two-letter-to-100km-square algorithm is the standard published OS one
(letters `A`-`Z` excluding `I`, arranged as a 5×5 grid per 500 km square):
verified here against `SV` (the grid's true origin, `e100k=0, n100k=0`,
the Isles of Scilly) and `TQ` (London, `e100k=5, n100k=1`) as fixed
points, then used both directions so the golden test can assert a real
round trip rather than trust the derivation.
"""

from __future__ import annotations

import re

from .coordinates import geometry_reference, reproject_point
from .errors import NormalisationError

#: OS grid letters, A-Z excluding I (25 letters, indices 0-24).
_LETTERS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"

_SOURCE_CRS = "EPSG:27700"

_BARE_RE = re.compile(r"^([A-Za-z]{2})(\d+)$")


def _decode_100km_square(letter_pair: str) -> tuple[int, int]:
    if len(letter_pair) != 2:
        raise ValueError("not a two-letter grid square")
    l1 = _LETTERS.find(letter_pair[0].upper())
    l2 = _LETTERS.find(letter_pair[1].upper())
    if l1 < 0 or l2 < 0:
        raise ValueError(f"not a recognised OS grid letter pair: {letter_pair!r}")

    e100k = ((l1 - 2) % 5) * 5 + (l2 % 5)
    n100k = (19 - (l1 // 5) * 5) - (l2 // 5)
    # Great Britain's grid squares span roughly e100k 0..7, n100k 0..12 —
    # a wider bound here just catches a letter pair that decodes to a
    # square that could never be a real GB reference (the far side of the
    # notional 5x5x5x5 lettering scheme) rather than guessing it is fine.
    if not (0 <= e100k <= 12 and 0 <= n100k <= 19):
        raise ValueError(f"grid letter pair {letter_pair!r} decodes outside Great Britain")
    return e100k, n100k


def _digits_to_offset(digits: str) -> float:
    """`digits` is an easting- or northing-offset within a 100 km square,
    at whatever precision the source gave: `"234"` is 100 m precision,
    `"23400"` is 1 m precision — same value, more digits. Multiplying by
    `10 ** (5 - len(digits))` converts either to metres."""
    if not digits.isdigit() or len(digits) > 5:
        raise ValueError(f"not a plausible grid offset: {digits!r}")
    return float(digits) * (10.0 ** (5 - len(digits)))


def _parse(raw: str | tuple[str, ...]) -> tuple[float, float]:
    if isinstance(raw, str):
        stripped = re.sub(r"\s+", "", raw.strip())
        match = _BARE_RE.fullmatch(stripped)
        if match is None:
            raise ValueError(f"not a recognisable British National Grid reference: {raw!r}")
        letter_pair, digits = match.groups()
        if len(digits) % 2 != 0:
            raise ValueError(
                f"an odd number of digits cannot split into easting and northing: {raw!r}"
            )
        half = len(digits) // 2
        easting_digits, northing_digits = digits[:half], digits[half:]
    else:
        if len(raw) != 3:
            raise ValueError(
                "grid_ref's three-column form takes exactly (letters, easting, northing)"
            )
        letter_pair, easting_digits, northing_digits = raw

    e100k, n100k = _decode_100km_square(letter_pair)
    easting = e100k * 100_000 + _digits_to_offset(easting_digits)
    northing = n100k * 100_000 + _digits_to_offset(northing_digits)
    return easting, northing


def grid_ref(raw: str | tuple[str, ...]) -> str:
    sample = raw if isinstance(raw, str) else "/".join(raw)
    try:
        easting, northing = _parse(raw)
    except ValueError as exc:
        raise NormalisationError("grid_ref", sample, str(exc)) from exc

    # Reprojection failure here (out-of-bounds, PROJ error) is not
    # expected once _decode_100km_square has already bounded the square
    # to Great Britain, but goes through the same path as every other
    # coordinate rather than being assumed infallible.
    reproject_point(easting, northing, source_crs=_SOURCE_CRS)
    return geometry_reference(_SOURCE_CRS, easting, northing)
