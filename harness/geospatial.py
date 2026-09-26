"""The Geospatial screen's own headless layer (`06_DECISIONS.md` ADR-049 Stage 2 §6, part B, item
2) — `05_DEPLOYMENT.md` §2.2's "Build local basemap", "Register a tier-4 provider" and "Verify",
each wrapped for `harness/webapp.py` with no capability the CLI lacks (§2.3).

**Only one of the three is actually reachable from inside the harness image, and this module says
so rather than pretending otherwise.** Confirmed by import, not by reasoning about it — a fresh
interpreter importing each of the three real modules, restricted to nothing beyond what
`harness/Dockerfile` actually copies in (`harness`, `packages/schemas`, `scripts`):

- `scripts.geo_local_provider` (this round's own extraction, see its own docstring): loads with
  zero `services`/`adapters` modules pulled in. **Reachable.**
- `scripts.build_local_basemap`: loads 21 `services.ingest.*`/`adapters.graph_arcadedb.*` modules
  as an unavoidable side effect of importing it at all — its own `build_local_basemap()` also
  needs a live `GraphPort` transaction (a running ArcadeDB, not a file). **Not reachable`, and not
  fixable by an import-order trick: the function's own real work needs a live graph.**
- `scripts.verify_map`: loads `services.api.mapconfig_loader` and `services.api.tier4_registration`
  as an unavoidable side effect of importing it at all. **Not reachable.**

The queue brief anticipated one failure mode ("the sandbox has no Java/planetiler... the real
failure ... surfaced verbatim") — a real one, but one level too deep: the actual first failure is
structural, not the Java dependency `run_planetiler` would raise if it ever got that far.

**Decided, round 09: add Conduit routes, never vendor `services`/`adapters` into this image.**
`POST /v1/admin/geospatial/build-basemap` (streamed, the same shape Launch is) and `POST
/v1/admin/geospatial/verify` now live in `services/api/app.py`, admin-role-gated
(`require_admin_role`, the identical `osprey-admin` role and audience check R2 already uses for
this image's own `/admin` — one bearer token authenticates both surfaces) — real, tested, callable
today by anyone holding a valid admin token, in the one process that already has every module
these two actions need.

**Disclosed, not built here: this image's own Geospatial screen does not call them.** Stage 2 §7
(the post-launch admin console) has no React shell yet — `apps/harness/src` renders the six setup
screens and nothing else, confirmed directly (`find apps/harness/src -iname "*console*" -o -iname
"*admin*"` returns nothing). A `mode="console"` branch inside `GeospatialScreen.tsx` with no
console context anywhere to actually render it in would be dead code no test could genuinely
exercise — the same "the check must run against the shape the real caller produces" discipline
`CLAUDE.md` rule 15 already states. Wiring this screen to the two routes above is real work owed
to whoever builds Stage 2 §7's own console shell, not silently dropped; `build_basemap_step`/
`verify_step` below are unchanged, and correctly still refuse — the setup-mode Geospatial screen
still cannot perform either action, which remains true regardless of what the Conduit can now do.
"""

from __future__ import annotations

from pathlib import Path

from scripts.geo_local_provider import register_local_provider

from schemas.mapconfig import MapConfig


class GeospatialError(RuntimeError):
    """Raised for a Geospatial-screen action this harness image cannot currently perform — never
    swallowed, always the real reason, per `CLAUDE.md` rule 2."""


def register_provider_step(
    config_path: Path,
    *,
    provider_id: str,
    label: str,
    pmtiles_path: Path,
    make_default: bool = True,
) -> MapConfig:
    """The one genuinely reachable step — a thin pass-through to
    `scripts.geo_local_provider.register_local_provider`, kept as its own named function so
    `harness/webapp.py`'s own UI→headless map has one entry per screen action, matching every
    other screen's own convention."""
    return register_local_provider(
        config_path,
        provider_id=provider_id,
        label=label,
        pmtiles_path=pmtiles_path,
        make_default=make_default,
    )


def build_basemap_step() -> None:
    """Always raises — this module's own docstring has the real, confirmed-by-import reason.
    Never called with real arguments because there is nothing that would use them: the block is
    before the point any region/output-dir/jar-path parameter would matter."""
    raise GeospatialError(
        "Build local basemap is not available from the setup harness. "
        "scripts.build_local_basemap imports services.ingest and adapters.graph_arcadedb, neither "
        "of which harness/Dockerfile copies into this image, and its own build_local_basemap() "
        "needs a live GraphPort transaction against a running ArcadeDB besides. Run "
        "`python -m scripts.build_local_basemap` directly against a running deployment instead "
        "(05_DEPLOYMENT.md §2.2's own CLI-equivalent path) — see harness/geospatial.py's own "
        "docstring and 07_BUILD_PLAN.md Stage 2 §6 part B for the two undecided options."
    )


def verify_step() -> None:
    """Always raises, for the matching reason — `scripts.verify_map` imports
    `services.api.mapconfig_loader` and `services.api.tier4_registration`, neither of which
    `harness/Dockerfile` copies into this image."""
    raise GeospatialError(
        "Verify is not available from the setup harness. scripts.verify_map imports "
        "services.api.mapconfig_loader and services.api.tier4_registration, neither of which "
        "harness/Dockerfile copies into this image. Run `python -m scripts.verify_map` directly "
        "against osprey.yaml instead — see harness/geospatial.py's own docstring and "
        "07_BUILD_PLAN.md Stage 2 §6 part B for the two undecided options."
    )
