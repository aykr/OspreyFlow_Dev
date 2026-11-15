"""v0.6.0 stage 3 preparation's dry run of the product's release
(`process/lanes/platform-b/v060/release_dry_run.py`): it reads the product workflow's own matrix and trivy settings,
builds and scans each image as the workflow's scan build does, with the upgrade stamp, and never pushes, signs or
publishes. The lock's refusal is the real one, recorded from `harness.release_lock` on 15 November 2026
(`tests/fixtures/v060/lock_refusal.txt`)."""

from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "process/lanes/platform-b/v060/release_dry_run.py"
spec = importlib.util.spec_from_file_location("release_dry_run", HERE)
assert spec and spec.loader
rd = importlib.util.module_from_spec(spec)
sys.modules["release_dry_run"] = rd
spec.loader.exec_module(rd)

STAMP = ["--build-arg", "OSPREY_UPGRADE_STAMP=2026-11-15"]
FLOW = rd.workflow()


def _plan(flow: dict = FLOW) -> list[list[str]]:
    return rd.plan("v0.6.0", "abc123", Path("/tmp/out"), STAMP, flow)


def test_it_builds_every_image_the_product_workflow_releases() -> None:
    assert rd.owned_images(FLOW) == {"workspace", "api", "ingest", "ner", "worker", "report-sync", "superset"}
    builds = [s for s in _plan() if s[:3] == ["docker", "buildx", "build"]]
    assert len(builds) == 7
    superset = next(s for s in builds if "deploy/superset/Dockerfile" in s)
    assert superset[-1] == "deploy/superset"  # its own folder, as the workflow builds it


def test_each_build_is_the_scan_build_with_the_upgrade_stamp() -> None:
    for step in (s for s in _plan() if s[:3] == ["docker", "buildx", "build"]):
        assert ["--platform", "linux/amd64", "--load"] == step[4:7] and step[3] == "--pull"
        assert step[7:9] == STAMP


def test_the_scan_uses_the_workflow_s_own_trivy_settings() -> None:
    scans = [s for s in _plan() if s[:2] == ["trivy", "image"]]
    assert len(scans) == 7
    assert scans[0][2:9] == ["--scanners", "vuln", "--severity", "HIGH,CRITICAL", "--ignore-unfixed", "--exit-code", "1"]


def test_nothing_leaves_the_machine() -> None:
    for step in _plan():
        if step[0] == "[would]":
            continue
        assert "--push" not in step and "cosign" not in step and step[:2] != ["gh", "release"]
        assert not (step[0] == "helm" and step[1] == "push")


def test_an_image_added_to_the_workflow_is_built_here_too() -> None:
    """The matrix is read, not copied: a service the product starts to release is built and scanned here."""
    flow = copy.deepcopy(FLOW)
    flow["jobs"]["images"]["strategy"]["matrix"]["include"].append({"service": "newone", "dockerfile": "services/newone/Dockerfile"})
    assert any("services/newone/Dockerfile" in s for s in _plan(flow) if s[:3] == ["docker", "buildx", "build"])


def test_the_lock_s_real_refusal_names_exactly_our_five_locked_images() -> None:
    text = (Path(__file__).parent / "fixtures/v060/lock_refusal.txt").read_text()
    assert rd.lock_refusal_names(text) == {"workspace", "api", "ingest", "ner", "superset"}


def test_the_chart_is_packaged_at_the_tag_s_version() -> None:
    helm = next(s for s in _plan() if s[:2] == ["helm", "package"])
    assert helm[helm.index("--version") + 1] == "0.6.0" and helm[helm.index("--app-version") + 1] == "v0.6.0"
