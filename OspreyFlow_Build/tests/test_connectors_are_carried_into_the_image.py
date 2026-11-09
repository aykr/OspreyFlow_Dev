"""The Conduit's image must carry what the Conduit needs at runtime — round 13bf.

Two things it did not: the `connectors/` profile directory it reads at import, and the `git`
binary it execed to publish a recipe (until the dulwich swap of 9 November 2026, after which the
image must carry nothing that execs it). Both were found by asking what the image actually contains
rather than assuming, and neither was visible to any test running against the source tree.

**Why this is its own file rather than a line in an existing one.** Connector profiles are *data*
the Conduit reads at import (`schemas.ingest.CONNECTOR_CATALOGUE` calls
`load_connector_profiles` at module scope), not an imported module, so
`tests/test_image_imports_are_carried.py` — which traces imports — cannot see them. The failure
mode is the same shape as the one that test exists for and was found the same way: by asking what
the image actually contains rather than assuming.

**What it would have cost.** `09_INGEST_STUDIO.md` §2's availability is derived from these files.
An image without them reports *every* connector unavailable, `generic-csv` included, so a rendered
deployment's Ingest Studio refuses every source — a regression strictly worse than the gap the
profile mechanism was built to close, and invisible in every test that runs against the source
tree.

Static on purpose, like its sibling: it runs in `make test` on every change and cannot be skipped
by a machine that has no Docker.
"""

from __future__ import annotations

import re
from pathlib import Path

from tools.layout import REPO as REPO_ROOT

CONNECTORS_DIR = REPO_ROOT / "connectors"


def _copied_paths(dockerfile: Path) -> set[str]:
    """Every source path a `COPY` brings in, ignoring `--from=` stage copies and flag tokens —
    the same parsing `test_image_imports_are_carried.py` settled on, and for the same reason: a
    `--from=builder /app/connectors` line proves the builder stage had them, not the context."""
    copied: set[str] = set()
    for line in dockerfile.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.upper().startswith("COPY ") or "--from=" in stripped:
            continue
        for token in stripped.split()[1:-1]:
            if token.startswith("--"):
                continue
            copied.add(token.rstrip("/"))
    return copied


def test_the_repository_has_connector_profiles_to_carry() -> None:
    """If this fails the rest of the file is vacuous, so it is asserted rather than assumed."""
    assert CONNECTORS_DIR.is_dir(), "connectors/ is missing"
    assert sorted(p.name for p in CONNECTORS_DIR.glob("*.yaml")), "connectors/ has no profiles"


def test_the_conduit_image_carries_the_connector_profiles() -> None:
    """The Conduit is the service that resolves a draft's `connector_profile`; without these
    files every draft is refused `connector_not_available`."""
    dockerfile = REPO_ROOT / "services" / "api" / "Dockerfile"
    copied = _copied_paths(dockerfile)
    assert "connectors" in copied, (
        "services/api/Dockerfile does not COPY connectors/ from the build context, so a rendered "
        "deployment reports every connector unavailable — including generic-csv, which works "
        f"today. COPY lines found: {sorted(copied)}"
    )


#: A call that runs the `git` binary: a process API whose first argument (or the first element of
#: a list or tuple argv) is the literal "git" or a path ending in "/git", across line breaks — the
#: shape `studio_publish._run_git` had before the dulwich swap,
#: `asyncio.create_subprocess_exec(\n        "git",`. **Not seen**: a name bound to "git" and
#: passed later (`GIT = "git"; run([GIT])`), or an argv built elsewhere and handed through a helper
#: (`scripts/refresh.py`'s `subprocess.run(list(argv))`); the runtime half,
#: `tests/services/api/test_recipe_repository.py::test_publish_never_execs_a_binary`, covers the
#: publish path whatever the spelling.
_GIT_EXEC = re.compile(
    r"(create_subprocess_exec|create_subprocess_shell|Popen|run|call|check_call|check_output"
    r"|system|exec\w*|spawn\w*|which)\(\s*[\[(]?\s*[\"'](?:[^\"'\s]*/)?git[\"'\s]"
)

#: The code the Conduit's image carries (services/api/Dockerfile's COPY lines).
_IMAGE_CODE = ("packages", "services", "scripts", "connectors")


def _git_execs(source: str) -> list[str]:
    return [m.group(0) for m in _GIT_EXEC.finditer(source)]


def test_the_git_scan_finds_the_call_the_conduit_used_to_make() -> None:
    """Rule 15: the scan below shown red on the real shape it exists to catch — the exact
    `_run_git` body `services/api/studio_publish.py` had until the dulwich swap — and on the
    one-line list form `subprocess.run(["git", ...])` the harness uses."""
    before_the_swap = (
        "async def _run_git(*args: str, cwd: Path) -> tuple[int, str]:\n"
        "    proc = await asyncio.create_subprocess_exec(\n"
        '        "git",\n'
        "        *args,\n"
        "        cwd=cwd,\n"
    )
    assert _git_execs(before_the_swap)
    assert _git_execs('subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"])')
    assert _git_execs('subprocess.run(("git", "status"), check=True)')
    assert _git_execs('os.execv("/usr/bin/git", ["git", "status"])')
    assert _git_execs('os.system("git status")')
    assert not _git_execs('Repo.init(str(repo_root), default_branch=b"main")')
    assert not _git_execs('subprocess.run(["gitleaks", "detect"])')
    assert not _git_execs('subprocess.run(["/opt/digit", "x"])')


def test_nothing_the_conduit_image_carries_execs_git() -> None:
    """**Round 13bf, then the owner's ruling of 9 November 2026 (MORNING item 89).**

    Round 13bf found Publish returned a bare 500 in every rendered deployment, because
    `services/api/studio_publish.py` execed `git` and the image had none; the image gained `git`
    and this test asserted it was installed. `git` is GPL-2.0-only, and the owner ruled it leaves
    the image: Publish now commits with dulwich (Apache-2.0), and
    `tests/services/api/test_recipe_repository.py` proves the publish path spawns no process and
    that real `git` reads what dulwich writes.

    So the runtime dependency this test guarded is gone, and the invariant turns round: nothing
    the image carries may exec `git`, or removing it from the image (platform's carry) brings the
    bare 500 back. An executable a service shells out to is a runtime dependency exactly as an
    imported package is; this is the check that none of the Conduit's is `git`.
    """
    offenders = [
        f"{path.relative_to(REPO_ROOT)}: {call!r}"
        for directory in _IMAGE_CODE
        for path in sorted((REPO_ROOT / directory).rglob("*.py"))
        for call in _git_execs(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], (
        "code the Conduit's image carries execs `git`, which leaves the image (the owner's ruling "
        f"of 9 November 2026); commit with dulwich as studio_publish.py does: {offenders}"
    )


def test_the_conduit_image_carries_every_product_file_a_route_loads_at_runtime() -> None:
    """**The third instance of one class — round 13cdc.**

    `services/api/app.py`'s `POST …/sites/{id}/grid` — `08_ACCEPTANCE_SCENARIOS.md` A1's own
    route — loaded its recipe from `tests/scenarios/fixtures/site_grid_recipe.yaml`. The Conduit's
    image deliberately does not ship `tests/`, so that route returned a bare 500 in **every
    rendered deployment**: `FileNotFoundError` on a path under a directory that is not there.
    Measured over the wire.

    A route the product serves cannot depend on a file only the test tree has. The recipe moved to
    `recipes/`, beside `connectors/`, and both are COPYed into the image.

    **The assertion is the general rule, not the instance**: every directory the Conduit loads
    product data from at runtime must be in the image. `connectors/` was the first (round 13bf),
    `recipes/` the second, and a third would be caught here rather than by a 500 in front of an
    operator.
    """
    dockerfile = REPO_ROOT / "services" / "api" / "Dockerfile"
    copied = _copied_paths(dockerfile)

    for directory in ("connectors", "recipes"):
        assert (REPO_ROOT / directory).is_dir(), f"{directory}/ is missing from the repository"
        assert directory in copied, (
            f"services/api/Dockerfile does not COPY {directory}/, but the Conduit loads product "
            f"data from it at runtime — the route that needs it will 500. COPY lines: "
            f"{sorted(copied)}"
        )


def test_no_conduit_module_loads_a_path_under_tests() -> None:
    """**The gate for the class, rather than for the two known instances.**

    A `Path(...)/"tests"/...` inside `services/` is the shape the A1 defect took: it resolves
    perfectly in a checkout and does not exist in the image, so it passes every test that runs
    from the source tree and fails only on a real deployment. Nothing was watching for it.
    """
    offenders: list[str] = []
    for module in (REPO_ROOT / "services").rglob("*.py"):
        source = module.read_text(encoding="utf-8")
        for line_number, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if '"tests"' in stripped or "'tests'" in stripped:
                offenders.append(f"{module.relative_to(REPO_ROOT)}:{line_number}: {stripped}")

    assert not offenders, (
        "a Conduit module builds a path into tests/, which the image does not ship — the route "
        "that loads it will 500 on a rendered deployment while every source-tree test passes:\n"
        + "\n".join(offenders)
    )
