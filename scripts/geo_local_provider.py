"""`register_local_provider` — split out of `scripts/build_local_basemap.py` (26 September 2026,
`06_DECISIONS.md` ADR-049 Stage 2 §6 part B), for one reason: it is the only one of that module's
own stages with no `services/`/`adapters/` dependency, and `harness/Dockerfile`'s traced dependency
set is `harness`, `packages/schemas`, `scripts` only — it does not copy `services/` or `adapters/`
in. A Python `import` executes its target module's whole top level, not just the one name a caller
reaches for, so `scripts/build_local_basemap.py`'s own top-level `from services.ingest...` /
`from adapters.graph_arcadedb...` imports made `register_local_provider` unreachable from inside
the harness image even though its own body never touches either package — importing it at all,
for any reason, would raise `ModuleNotFoundError` there. This module is the fix: the harness's
Geospatial screen (`harness/geospatial.py`) imports from here, never from
`scripts.build_local_basemap`, and this file's own import list is the thing that keeps it that way.

`scripts/build_local_basemap.py` re-imports `register_local_provider` from here unchanged — its own
behaviour, its own tests (`tests/test_build_local_basemap.py`) and its own CLI are untouched by
this move.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from schemas.mapconfig import ClientScope, MapConfig, MapProvider, MapSourceKind, ProviderLicence


def _default_licence() -> ProviderLicence:
    return ProviderLicence(id="ODbL", redistributable=True, client_scope=ClientScope.OPEN)


def register_local_provider(
    config_path: Path,
    *,
    provider_id: str,
    label: str,
    pmtiles_path: Path,
    make_default: bool = True,
) -> MapConfig:
    """Upserts one tier-1 provider entry into `osprey.yaml`'s `map:`
    section — replaces an existing entry with the same id, otherwise
    appends. Starts a fresh `MapConfig` if `config_path` does not exist
    yet, or exists but has no `map:` key, rather than requiring a caller
    to have one already.

    **Every other top-level key in `config_path` is read back and
    rewritten unchanged** (26 September 2026, found wiring `harness/
    geospatial.py`'s own real caller against an `osprey.yaml` the
    Profile/Components/Models/Governance screens had already written to:
    the previous version read only `raw["map"]` and wrote back
    `{"map": ...}` alone, silently discarding every other section on the
    very first real, non-empty file it was ever called against — every
    existing test happened to call it only on a fresh or
    already-map-only file, so nothing had exercised this). Fixed here,
    not worked around in the caller — this function's own contract is
    "upsert the map section", not "own the whole file."

    **Known limitation, not a silent one.** This round-trips through
    `yaml.safe_dump`, which does not preserve comments or key ordering in
    an existing file — fine for a script whose whole job is to *produce*
    this section, wrong for hand-maintained prose elsewhere in the same
    file. The harness (Phase 8) is the real, comment-preserving answer
    (`05_DEPLOYMENT.md` §2.1: "the generated artefacts are shown before
    anything runs" as a diff); this script predates it."""
    provider = MapProvider(
        id=provider_id,
        label=label,
        kind=MapSourceKind.VECTOR,
        source=f"file://{pmtiles_path}",
        style="bundled:osprey-dark",
        attribution="© OpenStreetMap contributors",
        licence=_default_licence(),
    )

    raw: dict[str, object] = {}
    if config_path.exists():
        raw = yaml.safe_load(config_path.read_text()) or {}
    map_raw = raw.get("map")
    if map_raw:
        existing = MapConfig.model_validate(map_raw)
        providers = [p for p in existing.providers if p.id != provider_id] + [provider]
        default = provider_id if make_default else existing.default
    else:
        providers = [provider]
        default = provider_id

    config = MapConfig(default=default, providers=providers)
    raw["map"] = config.model_dump(mode="json", exclude_none=True)
    config_path.write_text(yaml.safe_dump(raw, sort_keys=False))
    return config
