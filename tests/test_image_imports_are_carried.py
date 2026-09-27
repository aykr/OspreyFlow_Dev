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

#: Every top-level importable name this repository's own trees provide.
#:
#: `packages/` is itself not importable — each directory *under* it is a top-level name on
#: `PYTHONPATH` (`schemas`, `ports`, `principal_auth`, …). Discovered rather than listed, so a
#: package added tomorrow is covered without anyone remembering to add it here — which is the
#: failure mode this whole module exists for.
def _repo_top_level_names() -> tuple[str, ...]:
    packages = sorted(
        d.name
        for d in (REPO_ROOT / "packages").iterdir()
        if d.is_dir() and not d.name.startswith((".", "__"))
    )
    return ("scripts", "services", "harness", "packages", *packages)


TOP_LEVEL_TREES = _repo_top_level_names()

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


def _copied_paths(dockerfile: Path) -> set[str]:
    """Which source trees the image carries, at sub-package granularity.

    **Only `COPY` lines that read from the build context count.** A `COPY --from=builder /app/x`
    can carry nothing the builder stage did not itself bring in from the context, so counting it
    as a source of `x` double-counts and — worse — launders a narrow copy into a broad one:
    `harness/Dockerfile` narrows `packages/` to two sub-packages in its builder and then copies
    `/app/packages` wholesale into the final stage, which made this function report bare
    `packages` and, through `_carries` below, claim the image carried *everything*.

    Found by planting a red and watching it pass (round 13b) — the check was wrong, not the code.
    Both faults are the same mistake in different clothes: answering a narrower question with a
    broader match."""
    copied: set[str] = set()
    for line in dockerfile.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.upper().startswith("COPY "):
            continue
        if "--from=" in stripped:
            continue
        for token in stripped.split():
            if token.startswith("--"):
                continue
            cleaned = token.lstrip("./").removeprefix("app/")
            head = cleaned.split("/")[0]
            if head in TOP_LEVEL_TREES:
                copied.add(cleaned.rstrip("/"))
    return copied


#: The trees that are importable in their own right, rather than as children of `packages/`.
_NON_PACKAGE_TREES = ("scripts", "services", "harness")


def _carries(copied: set[str], module: str) -> bool:
    """Whether an image carrying `copied` can import top-level `module`.

    `packages/` is not itself importable — its *children* are the top-level names on
    `PYTHONPATH` — so `COPY packages` carries every package and `COPY packages/schemas` carries
    only `schemas`. **A bare `packages` says nothing about `services`, `scripts` or `harness`**,
    which is the fault this function shipped with for exactly one commit: every planted red
    passed, because `"packages" in copied` was treated as carrying anything at all."""
    if module in copied:
        return True
    if module in _NON_PACKAGE_TREES:
        return False
    return f"packages/{module}" in copied or "packages" in copied


@pytest.mark.parametrize("image", sorted(PYTHON_IMAGES))
def test_the_image_carries_every_tree_its_own_code_imports(image: str) -> None:
    dockerfile = PYTHON_IMAGES[image]
    assert dockerfile.is_file(), dockerfile

    imported = _module_scope_imports(REPO_ROOT / image)
    copied = _copied_paths(dockerfile)
    missing = {m for m in imported if not _carries(copied, m)}

    assert not missing, (
        f"{image}'s own code imports {sorted(missing)} at module scope, and "
        f"{dockerfile.relative_to(REPO_ROOT)} does not copy "
        f"{'it' if len(missing) == 1 else 'them'} into the image "
        f"(it copies {sorted(copied)}). The container will crash-loop on "
        f"ModuleNotFoundError the moment it starts — which is what happened to the Conduit from "
        f"round 09 until round 13, unnoticed, because `make test` runs against the source tree "
        f"where the import resolves."
    )
