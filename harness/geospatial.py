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
structural, not the Java dependency `run_planetiler` would raise if it ever got that far. Recorded
as **Proposed, not decided** in `07_BUILD_PLAN.md`'s Stage 2 §6 part-B entry, the same discipline
the Docker-NAT loopback finding got in part A — not silently resolved by vendoring `services/` and
`adapters/` into the harness image (a real cost: a much larger image, tighter coupling of what is
supposed to be a standalone setup tool to Conduit/Vault internals) and not silently resolved by
adding new Conduit routes either (out of this round's own scope: "do not touch services/ or
adapters/ except the one scripts/real_data_exceptions.py change").
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
