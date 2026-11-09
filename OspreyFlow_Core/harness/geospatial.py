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

**Settled in P3 (ADR-147 decision 6): Build and Verify run the Conduit's own code in its
container** (`docker compose exec api python -m services.api.map_admin build|verify`, what
`ospreyflow map` runs), so the 501s below are gone; the set-up console holds no Conduit token
before sign-in, so it goes by the deployment's compose file, as the command line does. The history
of the earlier position follows.

**Until P3 this image's Geospatial screen did not call them**, and `build_basemap_step` and
`verify_step` refused with 501s; the history is in `07_BUILD_PLAN.md`'s Stage 2 §6 part B entry.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
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


#: The Conduit's own *Maps* code (`services/api/map_admin.py`), run in its container (ADR-147
#: decision 6), the same command `ospreyflow map` runs.
MAP_PATH = ("python", "-m", "services.api.map_admin")
#: Who the set-up console's changes are recorded as in the maps' history.
BY = "setup-console"
_REGION = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
# A unit as the Conduit names one (`org_unit`, 1 to 60 characters, spaces allowed). Whether it holds
# anything here is the Conduit's to say, in its own words. Only what cannot be a unit is refused
# here: none, one too long, one the command line would read as an option (a leading `-`), or a
# control character. The argv is a list, run with no shell.
_UNIT = re.compile(r"^(?!-)[^\x00-\x1f\x7f]{1,60}$")

MapRunner = Callable[[list[str]], tuple[int, str]]


def run_captured(argv: list[str]) -> tuple[int, str]:
    done = subprocess.run(argv, capture_output=True, text=True, check=False)
    return done.returncode, done.stdout + done.stderr


def _in_conduit(deployment: Path, *words: str) -> list[str]:
    if not (deployment / "compose.yaml").is_file():
        raise GeospatialError(
            "There is no deployment to build or verify the map in yet. Launch it first: the map "
            "is built and verified by the Conduit."
        )
    return [
        "docker", "compose", "--env-file", str(deployment / "deployment.env"),
        "-f", str(deployment / "compose.yaml"), "exec", "-T", "api", *MAP_PATH, *words,
        "--by", BY,
    ]  # fmt: skip


def build_basemap_step(
    deployment: Path, region: str, unit: str, *, runner: MapRunner = run_captured
) -> tuple[int, list[str]]:
    """ADR-147 decision 6: the Conduit's own build, in its container, as `ospreyflow map build`
    runs it; the exit status and the Conduit's own printed lines (fixed words, never a key).
    **The unit the gazetteer's places are held by** is the build's setting (ADR-147 Amendment 2,
    ruling 8), required here as `--unit` is by the Conduit's command line; a unit that holds nothing
    here is refused in the Conduit's own words."""
    if not _REGION.fullmatch(region):
        raise ValueError("a region is a short lower-case name, such as rutland")
    if not _UNIT.fullmatch(unit):
        raise ValueError(
            "name the unit the gazetteer's places are held by, as the deployment names it "
            "(up to 60 characters)"
        )
    code, out = runner(_in_conduit(deployment, "build", region, "--unit", unit))
    return code, [line for line in out.splitlines() if line.strip()]


def verify_step(deployment: Path, *, runner: MapRunner = run_captured) -> tuple[int, list[str]]:
    code, out = runner(_in_conduit(deployment, "verify"))
    return code, [line for line in out.splitlines() if line.strip()]
