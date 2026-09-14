"""Resolves a recipe's `transform:` string against the Knowledge Adapter
registry — `09_INGEST_STUDIO.md` §4: transforms are Knowledge Adapters,
never an expression language. A transform is a bare name (`msisdn`) or a
name with keyword arguments (`datetime(tz=Europe/London)`); nothing more
expressive is parsed here, because nothing more expressive is meant to
exist.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from knowledge_adapters import REGISTRY
from knowledge_adapters.errors import NormalisationError

_CALL = re.compile(r"^(?P<name>\w+)(\((?P<args>.*)\))?$")

#: Which adapters take which connector-level default, so a connector's
#: `date_order`/`source_crs` (`01_DOMAIN_MODEL.md` §7, `00_ARCHITECTURE.md`
#: §1.2.2) reach every relevant transform without every field binding
#: having to repeat it — an explicit argument in the transform string
#: still overrides it.
_CONNECTOR_DEFAULT_PARAMS: dict[str, tuple[str, ...]] = {
    "datetime": ("date_order",),
    "coordinate_lon": ("source_crs",),
    "coordinate_lat": ("source_crs",),
    "geometry_ref": ("source_crs",),
    # `grid_ref` takes no `source_crs` — a British National Grid reference
    # is EPSG:27700 by construction, never ambiguous, never declared.
}


def apply_transform(
    spec: str,
    value: str | tuple[str, ...],
    *,
    connector_defaults: Mapping[str, str | None] | None = None,
) -> object:
    match = _CALL.match(spec.strip())
    if match is None:
        raise NormalisationError("transform", spec, "not a recognised transform expression")
    name = match.group("name")
    adapter = REGISTRY.get(name)
    if adapter is None:
        raise NormalisationError("transform", spec, f"no such Knowledge Adapter: {name!r}")

    kwargs: dict[str, str] = {}
    if connector_defaults:
        for param in _CONNECTOR_DEFAULT_PARAMS.get(name, ()):
            value_for_param = connector_defaults.get(param)
            if value_for_param is not None:
                kwargs[param] = value_for_param

    raw_args = match.group("args")
    if raw_args:
        for part in raw_args.split(","):
            key, sep, val = part.partition("=")
            if not sep:
                raise NormalisationError(
                    "transform", spec, f"argument {part!r} is not `key=value`"
                )
            # An explicit argument here overrides the connector default set above.
            kwargs[key.strip()] = val.strip()
    return adapter(value, **kwargs)
