"""Loads `osprey.yaml`'s `map:` section — mirrors `services/ingest/
recipe_loader.py`'s `yaml.safe_load` + `model_validate` shape exactly
(`schemas/mapconfig.py`'s own module docstring).

`public_view()` is the sanitised projection the Conduit serves to the
Glass (`GET /v1/map/providers`, `spec/02_GLASS_FRONTEND.md` §3.5's "layer
control listing every provider declared in `osprey.yaml`"). Not
principal-scoped and not audited — the same category `get_ontology_route`
already established for deployment-wide schema metadata
(`services/api/app.py`): a provider list is configuration, never a node, a
property value or a count. It strips `credential` (an env-var *name*, not
a secret value, but still an internal wiring detail the browser has no use
for) and `variables`/`endpoint` for a tier-4 provider proxied through the
Conduit — a browser talking to that endpoint directly would bypass the
tile proxy `00_ARCHITECTURE.md` §1.2 requires for exactly this case.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from schemas.mapconfig import MapConfig, MapProvider, PublicMapProvider


def load_map_config(path: str | Path) -> MapConfig:
    raw = yaml.safe_load(Path(path).read_text())
    return MapConfig.model_validate(raw["map"])


#: Rewritten, not passed through raw — see `local_source_route`'s own docstring in
#: `services/api/app.py` (Stage 3a rehearsal finding, 23 September 2026): a browser cannot
#: fetch a `file://` URI at all (no network stack reaches it), so the Glass's PMTiles source
#: must be an HTTP path the Conduit itself serves, never the on-disk path `osprey.yaml` records.
_LOCAL_SOURCE_ROUTE_PREFIX = "/v1/map/local-source"


def public_view(provider: MapProvider) -> PublicMapProvider:
    source = provider.source if provider.proxy == "none" else None
    if source is not None and source.startswith("file://"):
        source = f"{_LOCAL_SOURCE_ROUTE_PREFIX}/{provider.id}"
    return PublicMapProvider(
        id=provider.id,
        label=provider.label,
        kind=provider.kind,
        style=provider.style,
        attribution=provider.attribution,
        licence_id=provider.licence.id,
        licence_note=provider.licence.note,
        client_scope=provider.licence.client_scope,
        source=source,
    )
