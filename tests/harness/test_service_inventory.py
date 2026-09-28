"""The enumeration is checked against the tree, not merely written down.

`06_DECISIONS.md` ADR-049's Stage 2 §5a. The owner's direction was that the enumeration runs and is
reported before any image is built, and the reason a document table was not enough is the failure
mode: a service that grows an entrypoint becomes deployable and needs an image, and nothing would
have said so. These cases fail the build instead.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from harness.service_inventory import (
    INVENTORY,
    REPO_ROOT,
    RULE_8_DEBT,
    Kind,
    deployable,
    discover,
)


def test_every_inventoried_directory_still_exists() -> None:
    for entry in INVENTORY:
        assert (REPO_ROOT / entry.directory).is_dir(), f"{entry.directory} is gone from the tree"


def test_the_inventory_covers_every_directory_under_services_and_apps() -> None:
    """A new service directory must be classified, not silently omitted. Without this, the check
    below passes forever by only checking what it already knows about."""
    on_disk = {
        f"services/{p.name}"
        for p in (REPO_ROOT / "services").iterdir()
        if p.is_dir() and not p.name.startswith((".", "__"))
    } | {
        f"apps/{p.name}"
        for p in (REPO_ROOT / "apps").iterdir()
        if p.is_dir() and not p.name.startswith((".", "__"))
    }
    inventoried = {entry.directory for entry in INVENTORY}

    assert on_disk == inventoried, (
        f"the inventory and the tree disagree — only in tree: {sorted(on_disk - inventoried)}; "
        f"only in inventory: {sorted(inventoried - on_disk)}. A new directory needs classifying "
        "before it can be deployed or excluded."
    )


@pytest.mark.parametrize("entry", INVENTORY, ids=lambda e: e.directory)
def test_each_directory_s_declared_kind_matches_what_the_tree_says(entry) -> None:
    """The load-bearing case. `discover()` reads the tree independently of the declared table, so a
    directory that gains a `__main__.py` or an ASGI app — or loses one — fails here until the
    inventory and the reasoning attached to it are updated."""
    assert discover()[entry.directory] is entry.kind, (
        f"{entry.directory} is declared {entry.kind.value} but the tree says otherwise. If it "
        "gained an entrypoint it is now deployable and owes an image (standing rule 8); if it lost "
        "one, its image should go."
    )


def test_every_deployable_directory_has_a_dockerfile() -> None:
    """Standing rule 8, as a test rather than a promise: a deployable service with no image is the
    debt this sub-stage exists to pay, and this is what keeps it paid."""
    missing = [
        entry.directory
        for entry in deployable()
        if not (REPO_ROOT / entry.directory / "Dockerfile").is_file()
    ]
    assert missing == [], f"deployable with no Dockerfile: {missing}"


def test_no_library_or_placeholder_directory_has_a_dockerfile() -> None:
    """The other direction, and not a formality: four directories under `services/` were recorded
    as owing an image before this enumeration ran. They are libraries — they ship inside the api
    image and have no process to run — so an image for any of them would be a container that
    starts nothing."""
    stray = [
        entry.directory
        for entry in INVENTORY
        if entry.kind is not Kind.DEPLOYABLE
        and (REPO_ROOT / entry.directory / "Dockerfile").is_file()
    ]
    assert stray == [], (
        f"{stray} are libraries or placeholders with a Dockerfile — an image for one would start "
        "no process. Reclassify the directory or delete the Dockerfile."
    )


def test_the_rule_8_debt_names_a_directory_that_is_deployable_and_was_created_before_phase_8() -> (
    None
):
    """The repayment record has to point at something real. A debt entry naming a library would be
    the same misclassification this enumeration corrected."""
    deployable_dirs = {entry.directory for entry in deployable()}
    for directory, phase in RULE_8_DEBT:
        assert directory in deployable_dirs, f"{directory} is not deployable, so it owed no image"
        assert phase.startswith("Phase "), f"{directory}: {phase!r} is not a phase"


def test_the_glass_dockerfile_can_reach_tokens_css() -> None:
    """`tokens.css` moved into the product tree at Trigger A (round 14a, ADR-034 §B8):
    `apps/workspace/src/design/tokens.css`, reached by `apps/workspace/Dockerfile`'s own
    `COPY apps/workspace ./apps/workspace` line — no separate `COPY` and no `.dockerignore`
    negation any more, both of which existed only because the file used to live under the private
    `docs/` tree this image otherwise excludes wholesale. Asserts the file is present, not
    excluded from the build context, and that the Dockerfile's own blanket copy actually reaches
    it (not a narrower `COPY apps/workspace/dist` or similar that would silently miss it)."""
    pathspec = pytest.importorskip("pathspec")
    spec = pathspec.PathSpec.from_lines(
        "gitignore", (REPO_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    )

    token_path = REPO_ROOT / "apps" / "workspace" / "src" / "design" / "tokens.css"
    assert token_path.is_file()
    assert not spec.match_file("apps/workspace/src/design/tokens.css"), (
        "tokens.css is excluded from the build context, so the Glass image cannot build"
    )
    dockerfile = (REPO_ROOT / "apps" / "workspace" / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY apps/workspace ./apps/workspace" in dockerfile, (
        "no COPY line reaches apps/workspace/src/design/tokens.css any more"
    )


def test_no_dockerfile_copies_the_whole_context() -> None:
    """`COPY . .` would pull the private build tree into an image layer regardless of what
    `.dockerignore` says about paths nobody thought of — ADR-034 §B7's first assertion, enforced at
    the only point where it is cheap."""
    for entry in deployable():
        dockerfile = REPO_ROOT / entry.directory / "Dockerfile"
        for lineno, line in enumerate(dockerfile.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("COPY") and stripped.split()[-2:] in (
                [".", "."],
                [".", "./"],
            ):
                pytest.fail(f"{dockerfile}:{lineno} copies the whole build context: {stripped!r}")


def test_each_deployable_image_runs_as_a_non_root_user() -> None:
    """`05_DEPLOYMENT.md` §7: "Containers run as non-root". Read out of the Dockerfile rather than
    out of a built image, so this holds in CI with no daemon."""
    for entry in deployable():
        dockerfile = (REPO_ROOT / entry.directory / "Dockerfile").read_text(encoding="utf-8")
        users = [
            line.split(maxsplit=1)[1].strip()
            for line in dockerfile.splitlines()
            if line.strip().startswith("USER ")
        ]
        assert users, f"{entry.directory}/Dockerfile never switches away from root"
        assert users[-1] != "root", f"{entry.directory}/Dockerfile ends as root"


def test_the_python_images_copy_selectively_with_chown() -> None:
    """A single `0600` file anywhere in `packages/` or `services/` breaks an image that copies
    without `--chown`, because `COPY` preserves the mode and the runtime user cannot read it. Found
    the first time `services/ingest`'s image was actually run. `services/api` is immune only by
    accident — its DuckDB step runs `chown -R` for an unrelated reason — so both are asserted here
    rather than trusting the accident to survive an edit."""
    for directory in ("services/api", "services/ingest"):
        dockerfile = (REPO_ROOT / directory / "Dockerfile").read_text(encoding="utf-8")
        assert "--chown=osprey:osprey" in dockerfile or "chown -R osprey:osprey" in dockerfile, (
            f"{directory}/Dockerfile neither chowns its copies nor runs chown -R; one restrictive "
            "file mode in the source tree will make the image unstartable"
        )


def test_the_worker_finding_is_still_true() -> None:
    """`05_DEPLOYMENT.md` §3 names three worker containers and this tree can render none, because
    `services/api/worker.py` declares a class and no entrypoint. When someone gives it one, this
    fails — which is the point: the §3 finding recorded as Proposed would then be resolvable, and
    leaving it recorded as open would be wrong."""
    worker = (REPO_ROOT / "services" / "api" / "worker.py").read_text(encoding="utf-8")
    assert 'if __name__ == "__main__"' not in worker, (
        "services/api/worker.py has gained an entrypoint — the worker is now a runnable process, "
        "so 05_DEPLOYMENT.md §3's 'three workers' finding needs revisiting and the inventory "
        "needs a worker row"
    )
    assert not (REPO_ROOT / "services" / "api" / "__main__.py").is_file()


def test_the_glass_serves_as_a_single_page_application() -> None:
    """A deep link into an investigation must survive a refresh. Asserted against the nginx config
    the image actually ships rather than against the running container, so it holds in CI."""
    conf = (REPO_ROOT / "apps" / "workspace" / "nginx.conf").read_text(encoding="utf-8")
    assert "try_files $uri $uri/ /index.html" in conf
    assert "listen 8080" in conf, "05 §7 requires non-root, which cannot bind a privileged port"


def test_the_inventory_is_importable_without_docker(tmp_path: Path) -> None:
    """The enumeration is a property of the tree, not of a daemon — CI must be able to check it
    with no Docker at all."""
    assert discover(REPO_ROOT)
    assert discover(tmp_path) == {entry.directory: Kind.PLACEHOLDER for entry in INVENTORY}
