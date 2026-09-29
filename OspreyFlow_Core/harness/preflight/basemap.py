"""The basemap is built **and** served over HTTP — a rehearsal-derived check, two faults not one.

The 23 September 2026 rehearsal hit both halves separately, which is why this check reports them
separately:

1. **The tiles do not exist — a warning, not a blocker.** `scripts/build_local_basemap.py` has not
   been run, so there is nothing to serve. `services/api/app.py`'s own local-source route
   already answers this with "basemap not built — <path> does not exist yet"; Preflight says it
   before Launch instead of after, and does not block on it.
2. **The tiles exist and the provider still points at `file://` — this one fails.** It is worse,
   because
   everything looks built. A browser cannot fetch a `file://` URI at all — no network stack reaches
   it — so the map renders blank with no error. `services/api/mapconfig_loader.py`'s `public_view()`
   already rewrites `file://` to an HTTP route the Conduit serves, and this check confirms the
   rewrite is the path in play rather than the raw on-disk URI.
"""

from __future__ import annotations

from pathlib import Path

from harness.preflight.context import PreflightContext
from harness.preflight.result import CheckResult, failed, passed, skipped, warned
from schemas.deployment import TILES_CONTAINER_PATH

NAME = "basemap"

def _host_path(source: Path, context: PreflightContext) -> Path:
    """A provider's source is a path inside the Conduit's container; the file is in the host
    folder mounted there (`components.storage.tiles`). Anything else is a host path already."""
    mount = Path(TILES_CONTAINER_PATH)
    if source.is_relative_to(mount):
        return Path(context.config.components.storage.tiles) / source.relative_to(mount)
    return source


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

    tiles = _host_path(Path(default.source.removeprefix("file://")), context)
    if not tiles.is_file():
        # **Warn, not fail — the two outcomes are different faults with different urgencies.**
        # Tiles that have not been built yet are a post-install step: the stack comes up, every
        # other surface works, and the map is blank until someone runs one command. Blocking Launch
        # on it means a fresh clone can never reach a running system at all, which is a worse
        # failure than a blank map an operator can fix afterwards.
        #
        # Owner's decision, 24 September 2026: reaching a health-checked stack does not require a
        # basemap. `05_DEPLOYMENT.md` §2.1 now says a warning does not block Launch, and §2.2
        # describes the build as a post-install step.
        return warned(
            NAME,
            what_is_wrong=(
                f"the default basemap provider points at {tiles}, which does not exist yet. The "
                "map will render blank until it is built. Nothing else is affected, which is why "
                "this does not block Launch."
            ),
            what_to_do=(
                "After install, build it: "
                "`python -m scripts.build_local_basemap --tiles-only`. It runs "
                "planetiler on an extract and writes the PMTiles file this provider expects. "
                "Re-check this one afterwards rather than re-running the whole deploy."
            ),
            detail=detail,
        )

    # The tiles exist and the provider is a `file://` source. That is the correct, working
    # configuration: the Conduit serves it over `/v1/map/local-source/<id>` and
    # `mapconfig_loader.public_view` rewrites the URI for the Glass. (This case used to *fail*,
    # which meant a successfully built basemap blocked Launch.)
    return passed(NAME, detail=detail)
