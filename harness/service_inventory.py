"""Which directories under `services/` and `apps/` are deployable, and which are not.

`06_DECISIONS.md` ADR-049's Stage 2 §5a, and the owner's own direction of 24 September 2026: the
enumeration runs and is reported **before any image is built**, because building an image per
directory would answer the question by accident rather than settle it.

**Why this is code and not a table in a document.** The declared inventory below is the answer as of
the date in each row; `discover()` reads the same facts out of the tree. `tests/harness/
test_service_inventory.py` asserts the two agree, so a service that gains or loses an entrypoint
fails the build until the inventory — and the reasoning attached to it — is updated. A table in a
document would have gone stale silently, which is the failure `07_BUILD_PLAN.md`'s own drift gates
exist to prevent for models and routes.

## What "deployable" means here

A directory is deployable when it runs as **its own process**: an ASGI application, a batch
entrypoint, or a static bundle a server can serve. A package that only ever runs inside another
service's process is a library, whatever directory it sits in. `05_DEPLOYMENT.md` §1's
"The same container images run in all three [profiles]" is about images, and an image needs a
process to run.

**This distinction is what settles the rule 8 question.** Standing rule 8 requires "each service"
to get its Dockerfile and `trivy image` scan in the phase that created it. A library package under
`services/` is not a service in that sense and never owed an image — so the four directories
previously recorded as a rule 8 violation (`extract`, `resolve`, `geocoder`, `compute`) are not one.
The real, unpaid rule 8 debt is `apps/workspace`, which is a deployable process with no image,
created in Phase 4. See this module's own `RULE_8_DEBT`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


class Kind(StrEnum):
    """What a directory is, by what it does rather than where it sits."""

    #: Runs as its own process; needs an image.
    DEPLOYABLE = "deployable"
    #: Imported in-process by a deployable service; ships inside that service's image.
    LIBRARY = "library"
    #: A declared package with no code in it yet.
    PLACEHOLDER = "placeholder"


@dataclass(frozen=True)
class ServiceEntry:
    directory: str
    kind: Kind
    #: How it starts, for a deployable; why it is not one, otherwise.
    entrypoint: str | None
    #: Which deployable services import it in-process. Empty for a deployable.
    imported_by: tuple[str, ...]
    #: The phase that created it, for the rule 8 record.
    created_in: str
    note: str


#: The enumeration, as of 24 September 2026. Every row is checked against the tree by
#: `tests/harness/test_service_inventory.py`.
INVENTORY: tuple[ServiceEntry, ...] = (
    ServiceEntry(
        directory="services/api",
        kind=Kind.DEPLOYABLE,
        entrypoint="uvicorn services.api.app:app",
        imported_by=(),
        created_in="Phase 3",
        note=(
            "The Conduit. Also contains services/api/worker.py, the job-queue consumer — a "
            "JobWorker class with no entrypoint of its own, which is why §3's 'three workers' "
            "cannot be satisfied by this tree today. See WORKER_FINDING."
        ),
    ),
    ServiceEntry(
        directory="services/ingest",
        kind=Kind.DEPLOYABLE,
        entrypoint="python -m services.ingest",
        imported_by=(),
        created_in="Phase 2",
        note=(
            "A batch job image (ADR-013): one run loads one recipe against one source, then exits."
        ),
    ),
    ServiceEntry(
        directory="services/extract",
        kind=Kind.LIBRARY,
        entrypoint=None,
        imported_by=("services/api",),
        created_in="Phase 6",
        note="Imported by services/api/review.py and app.py. Ships inside the api image.",
    ),
    ServiceEntry(
        directory="services/resolve",
        kind=Kind.LIBRARY,
        entrypoint=None,
        imported_by=("services/api",),
        created_in="Phase 6",
        note=(
            "Imported by services/api/evaluation.py, resolution_trigger.py, app.py and "
            "working_set/service.py. Ships inside the api image."
        ),
    ),
    ServiceEntry(
        directory="services/geocoder",
        kind=Kind.LIBRARY,
        entrypoint=None,
        imported_by=(),
        created_in="Phase 5",
        note=(
            "match.py, imported by its own tests only today. A library with no current in-process "
            "caller is still not a process: it has no entrypoint and nothing to run."
        ),
    ),
    ServiceEntry(
        directory="services/compute",
        kind=Kind.PLACEHOLDER,
        entrypoint=None,
        imported_by=(),
        created_in="Phase 7",
        note=(
            "__init__.py and nothing else. ADR-028 puts ComputePort Tier 1 in a plain Node script "
            "and defers Tier 3 to Phase 8a, so no Python process is expected here at all."
        ),
    ),
    ServiceEntry(
        directory="apps/workspace",
        kind=Kind.DEPLOYABLE,
        entrypoint="vite build, served as static files",
        imported_by=(),
        created_in="Phase 4",
        note=(
            "The Glass. Had no Dockerfile from Phase 4 until Stage 2 §5a — the one real standing "
            "rule 8 debt this enumeration found."
        ),
    ),
)

#: Standing rule 8: "Each service gets its Dockerfile, and a `trivy image` CI scan, in the phase
#: that creates it — never batched into Phase 8." One directory in this tree owed one and did not
#: have it. The four library directories never owed one, so they are not a debt and not an
#: exception — they are simply not services in rule 8's sense.
RULE_8_DEBT: tuple[tuple[str, str], ...] = (("apps/workspace", "Phase 4"),)

#: `05_DEPLOYMENT.md` §3 lists "the workspace, one Conduit, three workers" among the twelve
#: containers a `local-lite` launch produces. The tree has one worker *implementation*
#: (`services/api/worker.py`'s `JobWorker`, a generic dispatcher keyed by `job_type` per ADR-025)
#: and **no worker process**: that module declares a class and a private helper, with no `main()`,
#: no `__main__`, and nothing that runs it. Three worker containers cannot be rendered from this
#: tree without first writing an entrypoint, which is service code and outside Stage 2 §5a.
#: Raised as Proposed in `05_DEPLOYMENT.md` §3 rather than resolved by inventing one.
WORKER_FINDING = (
    "05_DEPLOYMENT.md §3 names three worker containers; services/api/worker.py is a JobWorker "
    "class with no process entrypoint, so zero worker containers are renderable today."
)

_ENTRYPOINT_MARKERS = (
    re.compile(r"^if __name__ == [\"']__main__[\"']", re.MULTILINE),
    re.compile(r"^app = FastAPI\(", re.MULTILINE),
)


def _python_files(directory: Path) -> list[Path]:
    return sorted(p for p in directory.glob("*.py") if p.name != "__init__.py")


def discover(repo_root: Path = REPO_ROOT) -> dict[str, Kind]:
    """Reads the tree and classifies each inventoried directory, independently of `INVENTORY`.

    Deliberately narrow: it answers "does this directory contain a process entrypoint, any code at
    all, or neither", which is the question the inventory's own `kind` column records. It does not
    try to rediscover `imported_by` — that is recorded reasoning, and a grep-based rediscovery would
    be a second, worse implementation of what the inventory already states.
    """
    found: dict[str, Kind] = {}
    for entry in INVENTORY:
        directory = repo_root / entry.directory
        if entry.directory.startswith("apps/"):
            # A front-end app's entrypoint is its build, not a Python module.
            manifest = directory / "package.json"
            found[entry.directory] = Kind.DEPLOYABLE if manifest.is_file() else Kind.PLACEHOLDER
            continue
        files = _python_files(directory)
        if not files:
            found[entry.directory] = Kind.PLACEHOLDER
            continue
        if (directory / "__main__.py").is_file():
            found[entry.directory] = Kind.DEPLOYABLE
            continue
        has_entrypoint = any(
            marker.search(path.read_text(encoding="utf-8"))
            for path in files
            for marker in _ENTRYPOINT_MARKERS
        )
        found[entry.directory] = Kind.DEPLOYABLE if has_entrypoint else Kind.LIBRARY
    return found


def deployable() -> tuple[ServiceEntry, ...]:
    return tuple(entry for entry in INVENTORY if entry.kind is Kind.DEPLOYABLE)
