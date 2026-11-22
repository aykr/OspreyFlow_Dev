"""`tools/release_local.py` runs the product's release short of everything that leaves the machine (the owner's
ruling, 15 November 2026: it follows the product workflow, `OspreyFlow_Core/.github/workflows/release.yml`, not
the development repository's root workflow, which is retired). It reads the workflow's own image matrix and trivy
settings, builds and scans each image as the workflow's scan build does, with the upgrade stamp, and never pushes,
signs or publishes. The lock's refusal is the real one, recorded from `harness.release_lock` on 15 November 2026
(`tests/fixtures/v060/lock_refusal.txt`)."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
from tools import release_local

FLOW = release_local.workflow()


def _calls(monkeypatch: pytest.MonkeyPatch, flow: dict | None = None) -> list[list[str]]:
    calls: list[list[str]] = []
    monkeypatch.setattr(release_local, "_run", lambda cmd, *a, **k: calls.append(list(cmd)))
    release_local.build_and_scan("abc123", flow)
    return calls


def test_it_follows_the_product_workflow() -> None:
    assert release_local.WORKFLOW == release_local.REPO_ROOT / ".github" / "workflows" / "release.yml"
    assert release_local.REPO_ROOT.name == "OspreyFlow_Core"


def test_it_builds_every_image_the_product_releases(monkeypatch: pytest.MonkeyPatch) -> None:
    services = {e["service"] for e in release_local.matrix(FLOW)}
    base = {"workspace", "api", "ingest", "ner", "worker", "report-sync", "superset"}
    # The model gateway joins the matrix with PL13b's release patch (its entry in `release.yml`);
    # the list is held with it and without it, and nothing else may be there.
    assert base <= services <= base | {"litellm"}
    assert {s for s, _d, _c in release_local.SERVICES} == services
    builds = [c for c in _calls(monkeypatch) if c[:3] == ["docker", "buildx", "build"]]
    assert len(builds) == len(services)
    superset = next(c for c in builds if "deploy/superset/Dockerfile" in c)
    assert superset[-1] == str(release_local.REPO_ROOT / "deploy/superset")  # its own folder


def test_each_build_is_the_scan_build_with_the_upgrade_stamp(monkeypatch: pytest.MonkeyPatch) -> None:
    for c in (c for c in _calls(monkeypatch) if c[:3] == ["docker", "buildx", "build"]):
        assert c[3] == "--pull" and c[4:7] == ["--platform", "linux/amd64", "--load"]
        assert c[7] == "--build-arg" and c[8].startswith("OSPREY_UPGRADE_STAMP=")


def test_the_scan_uses_the_workflow_s_own_trivy_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    scans = [c for c in _calls(monkeypatch) if c[:2] == ["trivy", "image"]]
    assert len(scans) == len(release_local.matrix(FLOW))
    assert scans[0][2:9] == ["--scanners", "vuln", "--severity", "HIGH,CRITICAL", "--ignore-unfixed",
                             "--exit-code", "1"]  # fmt: skip


def test_nothing_is_pushed_or_signed(monkeypatch: pytest.MonkeyPatch) -> None:
    for c in _calls(monkeypatch):
        assert "--push" not in c and c[0] not in ("cosign", "gh") and c[:2] != ["docker", "push"]


def test_an_image_added_to_the_workflow_is_built_here_too(monkeypatch: pytest.MonkeyPatch) -> None:
    """The matrix is read, not copied: a service the product starts to release is built and scanned here."""
    flow = copy.deepcopy(FLOW)
    flow["jobs"]["images"]["strategy"]["matrix"]["include"].append(
        {"service": "newone", "dockerfile": "services/newone/Dockerfile"})
    assert any("services/newone/Dockerfile" in c for c in _calls(monkeypatch, flow))


def test_a_real_push_is_refused_in_words(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Refused before anything runs: every command and the lock are stood in, so a missing refusal fails
    here on what it would have run, never by running it."""
    ran: list[list[str]] = []
    monkeypatch.setattr(release_local, "_run", lambda cmd, *a, **k: ran.append(list(cmd)))
    monkeypatch.setattr(release_local, "lock", lambda out: ran.append(["lock", str(out)]))
    monkeypatch.setattr(release_local.subprocess, "run", lambda *a, **k: ran.append(["subprocess", *map(str, a)]))
    assert release_local.main(["--tag", "v0.6.0", "--out", "/nonexistent/never-made"]) == 1
    assert ran == []
    assert "a push from here would publish unsigned images" in capsys.readouterr().err


def test_the_lock_s_real_refusal_names_exactly_our_locked_images() -> None:
    text = (Path(__file__).parent / "fixtures/v060/lock_refusal.txt").read_text()
    assert release_local.lock_refusal_names(text) == set(release_local.LOCKED_OURS)
