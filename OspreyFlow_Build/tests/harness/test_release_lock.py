"""The release's `versions.lock` names every image any deployment of that release can run (build
order step 20a, ADR-114 Amendment 34).

Found drafting Amendment 33: the release's lock was rendered from the committed `osprey.yaml`, which
switches dashboards off, so v0.4.4's lock names no Superset (and no ClickHouse). A deployment that
turns dashboards on could not take Superset from a release's lock or from a bundle, which carries
exactly what the lock names.

The first test runs the release workflow's own lock step — its shell, as written in
`.github/workflows/release.yml` — against the committed `osprey.yaml`, with only Docker stood in (it
answers a digest for any image, as a registry holding the release would), and compares the lock with
the images every combination of options renders into a compose file.
"""

from __future__ import annotations

import hashlib
import itertools
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from harness.render import render
from tools.layout import CORE

from schemas.deployment import (
    AnalyticsEngine,
    ExternalConfig,
    GraphStore,
    OspreyConfig,
    SearchBackend,
)

RELEASE = CORE / ".github" / "workflows" / "release.yml"
REGISTRY = "ghcr.io/acme"


def _resolver(ref: str) -> str:
    return "sha256:" + hashlib.sha256(ref.encode()).hexdigest()


def _committed_config_text() -> str:
    """`osprey.yaml` as the tag holds it — the release renders a checkout, not a working copy."""
    return subprocess.run(
        ["git", "-C", str(CORE), "show", "HEAD:./osprey.yaml"],
        capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip


def _the_lock_step() -> str:
    steps = yaml.safe_load(RELEASE.read_text(encoding="utf-8"))["jobs"]["release"]["steps"]
    return next(s["run"] for s in steps if "versions.lock" in s.get("name", ""))


def _stand_ins(bin_dir: Path) -> None:
    """`docker` answering a digest for any image; `uv run` and `python` as this test's own."""
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        f"#!{sys.executable}\n"
        "import hashlib, sys\n"
        "image = sys.argv[-1] if sys.argv[1:3] == ['image', 'inspect'] else None\n"
        "if image is None and sys.argv[1:4] == ['buildx', 'imagetools', 'inspect']:\n"
        "    image = sys.argv[4]\n"
        "if image is None:\n"
        "    sys.exit(1)\n"
        "digest = 'sha256:' + hashlib.sha256(image.encode()).hexdigest()\n"
        "if sys.argv[1] == 'image':\n"
        "    print(image.split('@')[0].rsplit(':', 1)[0] + '@' + digest)\n"
        "else:\n"
        "    print(digest)\n"
    )
    (bin_dir / "uv").write_text('#!/bin/sh\n[ "$1" = run ] && shift\nexec "$@"\n')
    (bin_dir / "python").write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    for tool in bin_dir.iterdir():
        tool.chmod(0o755)


def _lock_as_the_release_writes_it(tmp_path: Path) -> dict[str, str]:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    for item in CORE.iterdir():
        if item.name not in ("osprey.yaml", "deploy"):
            (checkout / item.name).symlink_to(item)
    # `deploy/` holds rendered deployments (`deploy/generated`); only its sources are linked.
    (checkout / "deploy").mkdir()
    for item in (CORE / "deploy").iterdir():
        if item.name != "generated":
            (checkout / "deploy" / item.name).symlink_to(item)
    (checkout / "osprey.yaml").write_text(_committed_config_text(), encoding="utf-8")
    _stand_ins(tmp_path / "bin")
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "OSPREY_IMAGE_REGISTRY")}
    env |= {"PATH": f"{tmp_path / 'bin'}{os.pathsep}{env['PATH']}",
            "GITHUB_REPOSITORY_OWNER": "acme"}  # fmt: skip
    # The runner's bash lower-cases the owner with `${…,,}`; macOS's bash 3.2 has no such
    # expansion, so the owner is given in lower case already and the expansion read plainly.
    script = _the_lock_step().replace("${GITHUB_REPOSITORY_OWNER,,}", "${GITHUB_REPOSITORY_OWNER}")
    done = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", script],
        cwd=checkout, env=env, capture_output=True, text=True, timeout=300, check=False,
    )  # fmt: skip
    assert done.returncode == 0, done.stdout + done.stderr
    lock = yaml.safe_load((checkout / "versions.lock").read_text(encoding="utf-8"))
    return {f"{e['repository']}:{e['tag']}": str(e["digest"]) for e in lock["images"]}


def _runnable_graph_stores() -> list[GraphStore]:
    """A graph store a deployment can run has its adapter (`packages/adapters/graph_<name>`);
    JanusGraph is declarable before its adapter exists (`GraphStore`'s own note)."""
    return [g for g in GraphStore if (CORE / "packages" / "adapters" / f"graph_{g.value}").is_dir()]


def _every_image_any_option_runs(monkeypatch: pytest.MonkeyPatch) -> set[str]:
    monkeypatch.setenv("OSPREY_IMAGE_REGISTRY", REGISTRY)
    base = OspreyConfig.model_validate(yaml.safe_load(_committed_config_text()) or {})
    images: set[str] = set()
    for graph, analytics, search, dashboards in itertools.product(
        _runnable_graph_stores(), AnalyticsEngine, SearchBackend, (False, True)
    ):
        components = base.components.model_copy(update={
            "graph_store": graph, "analytics_engine": analytics, "search": search,
            "source_path": None})  # fmt: skip
        reporting = base.reporting.model_copy(update={"sync": dashboards, "superset": dashboards})
        config = base.model_copy(update={"components": components, "reporting": reporting,
                                          "external": ExternalConfig()})  # fmt: skip
        compose = yaml.safe_load(render(config, resolver=_resolver).artefacts["compose.yaml"])
        images |= {str(s["image"]) for s in compose["services"].values() if "image" in s}
    return images


def test_the_release_lock_names_every_image_any_option_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Red before step 20a: the lock step rendered the committed answers alone (dashboards off), so
    Superset and ClickHouse were missing."""
    locked = _lock_as_the_release_writes_it(tmp_path)
    wanted = _every_image_any_option_runs(monkeypatch)
    assert any("/superset:" in image for image in wanted)  # the comparison can see Superset
    missing = sorted(wanted - set(locked))
    assert missing == [], f"the release's lock names no digest for: {missing}"
    assert all(digest.startswith("sha256:") for digest in locked.values())


def test_a_graph_store_the_release_leaves_out_is_one_no_deployment_can_run() -> None:
    """The release's lock carries no JanusGraph while it has no adapter; the day its adapter lands,
    this fails and the lock must name it."""
    from harness.release_lock import NOT_YET_RUNNABLE

    assert set(NOT_YET_RUNNABLE) == set(GraphStore) - set(_runnable_graph_stores())
