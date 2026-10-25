"""Knowledge Adapters — `01_DOMAIN_MODEL.md` §7, `09_INGEST_STUDIO.md` §4.

Pure functions only; every one has a golden test file
(`tests/knowledge_adapters/`). `REGISTRY` is what a recipe's `transform:`
field resolves against (`09_INGEST_STUDIO.md` §6) and what the Ingest
Studio's profiler runs for pattern recognition (§3) — the same functions,
not a second implementation of the same normalisation logic.

`ARITY` declares, for every adapter that accepts a `FieldBinding.fields`
(plural) multi-column binding rather than a single `field`, exactly how
many source columns it takes. An adapter absent from `ARITY` does not
support `fields` at all — `msisdn`, `email` and the rest only ever take
one column. `services/ingest/engine.py` checks a `fields` binding's length
against this before calling the adapter, so a recipe that names the wrong
number of columns is rejected with a clear reason rather than the adapter
raising a confusing `TypeError`/unpacking error at call time.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .account_ref import account_ref
from .address import address
from .coordinates import coordinate_lat, coordinate_lon, geometry_ref, polygon_ref
from .datetime_adapter import datetime_adapter
from .email import email
from .errors import NormalisationError
from .grid_ref import grid_ref
from .iban_card import card, iban
from .imei import imei
from .imsi import imsi
from .msisdn import msisdn
from .person_name import person_name
from .postcode import postcode

REGISTRY: dict[str, Callable[..., Any]] = {
    "msisdn": msisdn,
    "imei": imei,
    "imsi": imsi,
    "email": email,
    "datetime": datetime_adapter,
    "person_name": person_name,
    "address": address,
    "iban": iban,
    "card": card,
    "coordinate_lon": coordinate_lon,
    "coordinate_lat": coordinate_lat,
    "geometry_ref": geometry_ref,
    "polygon_ref": polygon_ref,
    "grid_ref": grid_ref,
    "postcode": postcode,
    "account_ref": account_ref,
}

#: `coordinate_lon`/`coordinate_lat`/`geometry_ref` take an (easting,
#: northing) pair. `grid_ref` takes three only in its split-column form
#: (letters, easting, northing) — bound via a plain `field` (a bare
#: reference string) it takes one, which `fields`/`ARITY` has no bearing
#: on at all.
ARITY: dict[str, int] = {
    "coordinate_lon": 2,
    "coordinate_lat": 2,
    "geometry_ref": 2,
    "polygon_ref": 8,
    "grid_ref": 3,
}

__all__ = [
    "ARITY",
    "REGISTRY",
    "NormalisationError",
    "account_ref",
    "address",
    "card",
    "coordinate_lat",
    "coordinate_lon",
    "datetime_adapter",
    "email",
    "geometry_ref",
    "polygon_ref",
    "grid_ref",
    "iban",
    "imei",
    "imsi",
    "msisdn",
    "person_name",
    "postcode",
]
