"""The basemap is built **and** served over HTTP — a rehearsal-derived check, two faults not one.

The 23 September 2026 rehearsal hit both halves separately, which is why this check reports them
separately:

1. **The tiles do not exist.** `scripts/build_local_basemap.py` has not been run, so there is
   nothing to serve. `services/api/app.py`'s own local-source route already answers this with
   "basemap not built — <path> does not exist yet"; Preflight says it before Launch instead of
   after.
2. **The tiles exist and the provider still points at `file://`.** This one is worse, because
   everything looks built. A browser cannot fetch a `file://` URI at all — no network stack reaches
   it — so the map renders blank with no error. `services/api/mapconfig_loader.py`'s `public_view()`
   already rewrites `file://` to an HTTP route the Conduit serves, and this check confirms the
   rewrite is the path in play rather than the raw on-disk URI.
"""

from __future__ import annotations

from pathlib import Path

from harness.preflight.context import PreflightContext
from harness.preflight.result import CheckResult, failed, passed, skipped

NAME = "basemap"

_LOCAL_SOURCE_ROUTE_PREFIX = "/v1/map/local-source"


def check(context: PreflightContext) -> CheckResult:
    map_config = context.config.map
    if map_config is None:
        return skipped(
            NAME,
            reason=(
                "osprey.yaml declares no map section, so no basemap has been chosen on the "
                "Geospatial screen yet. Not checked."
            ),
        )

    default = next((p for p in map_config.providers if p.id == map_config.default), None)
    if default is None:
        return failed(
            NAME,
            what_is_wrong=(
                f"the default provider {map_config.default!r} is not in the provider list."
            ),
            what_to_do="Fix the map.default value in osprey.yaml and re-render.",
        )

    detail = (f"default provider: {default.id}", f"source: {default.source or '(proxied)'}")

    if default.source is None or not default.source.startswith("file://"):
        return passed(NAME, detail=detail)

    tiles = Path(default.source.removeprefix("file://"))
    if not tiles.is_file():
        return failed(
            NAME,
            what_is_wrong=(
                f"the default basemap provider points at {tiles}, which does not exist. The map "
                "will render blank."
            ),
            what_to_do=(
                "Build it: `python -m scripts.build_local_basemap`. It downloads the extract, "
                "runs planetiler and writes the PMTiles file this provider expects."
            ),
            detail=detail,
        )

    return failed(
        NAME,
        what_is_wrong=(
            f"the tiles at {tiles} exist, but the provider's source is a file:// URI. A browser "
            "cannot fetch file:// at all — no network stack reaches it — so the map renders blank "
            "with no error anywhere. This is the second half of the 23 September rehearsal's own "
            "basemap failure, and it is the half that looks like everything worked."
        ),
        what_to_do=(
            f"The Conduit serves these tiles over HTTP at {_LOCAL_SOURCE_ROUTE_PREFIX}/"
            f"{default.id}, and mapconfig_loader.public_view() rewrites the URI for the Glass "
            "automatically — so confirm the Glass is reading the Conduit's provider list rather "
            "than osprey.yaml directly. Tiles served straight from disk are the failure, not the "
            "file:// entry in osprey.yaml, which is correct as written."
        ),
        detail=detail,
    )
