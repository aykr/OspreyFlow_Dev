"""The Conduit's image must carry what the Conduit needs at runtime — round 13bf.

Two things it did not: the `connectors/` profile directory it reads at import, and the `git`
binary it execs to publish a recipe. Both were found by asking what the image actually contains
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

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
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


def test_the_conduit_image_carries_the_binaries_the_conduit_shells_out_to() -> None:
    """**The second thing the image did not have, found the same way — round 13bf.**

    `services/api/studio_publish.py` runs `git` with `asyncio.create_subprocess_exec` to satisfy
    §6's "Publishing writes the recipe to version control". The runtime stage installed no
    packages at all, so `git` was absent and Publish returned a bare 500 — `FileNotFoundError`
    from the exec itself — in **every rendered deployment this project has ever built**.

    It stayed invisible for the reason rule 15 names. The one test of publishing
    (`tests/ingest/test_studio_publish_pipeline.py`) runs on the host, where `git` is on `PATH`,
    and hands `write_and_commit_recipe` a `git_repo` fixture it has just `git init`ed. So the test
    environment supplied both things the real deployment lacked — the binary and the repository —
    and agreed with the code perfectly while the deployed article could not publish at all.

    An executable a service shells out to is a runtime dependency exactly as an imported package
    is; the difference is only that nothing type-checks it. This is that check.
    """
    dockerfile = (REPO_ROOT / "services" / "api" / "Dockerfile").read_text(encoding="utf-8")
    installed = " ".join(
        line.strip() for line in dockerfile.splitlines() if "apt-get install" in line
    )
    assert "git" in installed.split(), (
        "services/api/Dockerfile's runtime stage does not install `git`, but "
        "services/api/studio_publish.py execs it to commit a published recipe — Publish will "
        f"500 with FileNotFoundError in every rendered deployment. apt-get install lines: "
        f"{installed!r}"
    )
