"""Every top-level cross-tree import in shipped code is carried by the image that ships it.

**The defect this exists for** (round 13, 27 September 2026). `services/api/app.py` imports
`scripts.build_local_basemap` and `scripts.verify_map` at module top level — the geospatial admin
routes added in round 09 — and `services/api/Dockerfile` copied only `packages` and `services`.
The Conduit therefore could not import at all in a rendered deployment: the container crash-looped
on `ModuleNotFoundError: No module named 'scripts'`, every time, since round 09.

**Why nothing caught it for four rounds**, which is the part worth keeping. `make test` runs
against the source tree, where `scripts/` is on `PYTHONPATH` and the import is fine. The one test
that would have caught it, `tests/harness/test_six_screen_live_exit.py`, is designed with two real
branches: on a daemon below `local-lite`'s memory floor it asserts Preflight's refusal and stops
*before* Launch. This machine was below that floor from round 05 until round 13, so that test took
the refusal branch every single time and never once reached `docker compose up`. Its green was
real and said nothing about whether the deployment starts — exactly what STANDING.md's rule of
27 September names, and `CLAUDE.md` rule 15's "a gate that has only ever been run against content
it happens to pass has not been tested, only exercised".

A static check, deliberately, rather than another live one: it costs nothing, runs in `make test`
on every change, and cannot itself be skipped by an under-resourced machine.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Each shipped Python image, and the tree whose modules it is built from.
#: `apps/workspace` is absent on purpose — it is a JS/nginx image with no Python in it.
PYTHON_IMAGES: dict[str, Path] = {
    "services/api": REPO_ROOT / "services" / "api" / "Dockerfile",
    "services/ingest": REPO_ROOT / "services" / "ingest" / "Dockerfile",
    "harness": REPO_ROOT / "harness" / "Dockerfile",
}

#: The top-level packages a Dockerfile may need to copy, as they are imported.
TOP_LEVEL_TREES = ("scripts", "services", "harness", "packages")

#: `from X.y import z` / `import X.y` at the start of a line — module scope, not inside a
#: function. A deferred import inside a handler is a different (and also questionable) thing and
#: is not what crashed the Conduit at startup.
_IMPORT = re.compile(r"^(?:from|import)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)


def _module_scope_imports(tree: Path) -> set[str]:
    found: set[str] = set()
    for path in tree.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        for match in _IMPORT.finditer(path.read_text(encoding="utf-8")):
            name = match.group(1)
            if name in TOP_LEVEL_TREES:
                found.add(name)
    return found


def _copied_trees(dockerfile: Path) -> set[str]:
    """What the Dockerfile actually puts in the image, from either stage.

    Matches `COPY packages ./packages` and `COPY --from=builder /app/scripts ./scripts` alike —
    the source spelling is what matters, since that is the tree being carried. `packages/schemas`
    counts as `packages`: a partial copy is a narrower question this check does not try to answer,
    and answering it wrongly would make the check noisy rather than useful."""
    copied: set[str] = set()
    for line in dockerfile.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.upper().startswith("COPY "):
            continue
        for token in stripped.split():
            cleaned = token.lstrip("./").removeprefix("app/")
            head = cleaned.split("/")[0]
            if head in TOP_LEVEL_TREES:
                copied.add(head)
    return copied


#: **A second instance of the same class, found by this check and deliberately not fixed here.**
#: `harness/verify.py` imports `services.api.auth` and `services.api.config` at module scope, and
#: `harness/Dockerfile` does not carry `services/` — its own header says so in terms: the traced
#: set is "`harness`, `packages/schemas`, `scripts` — and nothing under `services/`", because
#: "`services/api/auth.py`'s existing JWT verification is not reused: it lives outside this set."
#:
#: It does not crash the image at startup, because `harness/apply.py` imports `verify` lazily
#: inside its own last stage — but that stage is reached on the customer path (§2's bootstrap,
#: Launch inside the container), so `run_verify` would raise `ModuleNotFoundError` there.
#:
#: Unfixed on purpose: carrying `services/` into the harness image reverses a recorded ADR-049
#: decision about that image's own boundary, which is the owner's call, not a round-13 tidy-up.
#: `strict=True` so the day it is fixed this test fails and demands the marker be removed —
#: an xfail that silently keeps passing is the same "recorded and forgotten" failure this whole
#: check exists to prevent.
KNOWN_UNFIXED = {
    "harness": "harness/verify.py imports services.api.* — ADR-049 excludes services/ from that "
    "image on purpose; see REPORT-13.md and 07_BUILD_PLAN.md"
}


@pytest.mark.parametrize("image", sorted(PYTHON_IMAGES))
def test_the_image_carries_every_tree_its_own_code_imports(
    image: str, request: pytest.FixtureRequest
) -> None:
    if image in KNOWN_UNFIXED:
        request.node.add_marker(pytest.mark.xfail(strict=True, reason=KNOWN_UNFIXED[image]))
    dockerfile = PYTHON_IMAGES[image]
    assert dockerfile.is_file(), dockerfile

    imported = _module_scope_imports(REPO_ROOT / image)
    copied = _copied_trees(dockerfile)
    missing = imported - copied

    assert not missing, (
        f"{image}'s own code imports {sorted(missing)} at module scope, and "
        f"{dockerfile.relative_to(REPO_ROOT)} does not copy "
        f"{'it' if len(missing) == 1 else 'them'} into the image "
        f"(it copies {sorted(copied)}). The container will crash-loop on "
        f"ModuleNotFoundError the moment it starts — which is what happened to the Conduit from "
        f"round 09 until round 13, unnoticed, because `make test` runs against the source tree "
        f"where the import resolves."
    )
