"""`ospreyflow doctor` (ADR-114 decision 4; Amendment 3 decision 4): each prerequisite, in words,
with its fix, and a non-zero exit on any failure.

What a mistake would do, and the case that catches it:
- a missing prerequisite passing silently — `test_each_lite_prerequisite_faked_absent_fails_in_words`;
- Compose v1 accepted, or a new major version refused —
  `test_compose_v1_is_refused_and_v2_and_v5_are_accepted`;
- the memory floor off by a rounding — `test_memory_below_sixteen_gigabytes_is_refused`;
- a port our own deployment holds reported as a conflict, which would fail every re-install —
  `test_a_port_held_by_our_own_deployment_passes`;
- a healthy machine refused — `test_a_healthy_machine_passes_with_exit_zero`;
- the cloud modes checking Lite's Docker, or not checking OpenTofu —
  `test_small_and_enterprise_check_tofu_and_the_cloud_cli_not_docker`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from ospreyflow.doctor import Check, run_doctor

from .conftest import FakeProbes, Rig


def _by_name(checks: list[Check]) -> dict[str, Check]:
    return {c.name: c for c in checks}


def _less_memory(probes: FakeProbes) -> None:
    probes.info = {"MemTotal": 8_000_000_000}


def test_a_healthy_machine_passes_with_exit_zero(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    assert rig("doctor") == 0
    out = capsys.readouterr().out
    assert "✘" not in out
    assert out.count("✔") >= 8


@pytest.mark.parametrize(
    ("name", "arrange", "words", "fix"),
    [
        (
            "docker-installed",
            lambda p: p.missing.add("docker"),
            "Docker is not installed",
            "Install",
        ),
        ("docker-running", lambda p: setattr(p, "info", None), "not running", "Start Docker"),
        ("compose", lambda p: setattr(p, "compose", None), "Compose", "Docker Desktop"),
        ("memory", _less_memory, "8.0 GB", "settings"),
        ("disk", lambda p: setattr(p, "disk_gb", 20.0), "20", "Free up"),
        ("git", lambda p: p.missing.add("git"), "Git is not installed", "Install"),
        ("uv", lambda p: p.missing.add("uv"), "uv is not installed", "Install"),
        ("port-80", lambda p: p.busy_ports.add(80), "80", "Stop whatever"),
    ],
)
def test_each_lite_prerequisite_faked_absent_fails_in_words(
    tmp_path: Path, name: str, arrange: Callable[[FakeProbes], object], words: str, fix: str
) -> None:
    probes = FakeProbes()
    arrange(probes)
    checks = _by_name(run_doctor("lite", probes, product=tmp_path))
    failed = [c.name for c in checks.values() if not c.ok]
    # Docker not being installed also means it is not running; every other case is exactly one.
    assert name in failed
    assert failed == [name] or name == "docker-installed"
    assert words in checks[name].says
    assert fix in checks[name].fix


def test_the_exit_is_one_when_any_check_fails(rig: Rig, capsys: pytest.CaptureFixture[str]) -> None:
    rig.probes.missing.add("git")
    assert rig("doctor") == 1
    out = capsys.readouterr().out
    assert "✘ Git is not installed" in out
    assert " — " in out.split("✘", 1)[1]  # the fix follows the sentence


def test_compose_v1_is_refused_and_v2_and_v5_are_accepted(tmp_path: Path) -> None:
    for version, ok in [
        ("docker-compose version 1.29.2, build 5becea4c", False),
        ("Docker Compose version v2.29.1", True),
        ("Docker Compose version v5.5.1", True),
        ("2.20.0", True),
    ]:
        probes = FakeProbes()
        probes.compose = version
        checks = _by_name(run_doctor("lite", probes, product=tmp_path))
        assert checks["compose"].ok is ok, version


def test_memory_below_sixteen_gigabytes_is_refused(tmp_path: Path) -> None:
    probes = FakeProbes()
    probes.info = {"MemTotal": 15_900_000_000}
    memory = _by_name(run_doctor("lite", probes, product=tmp_path))["memory"]
    assert not memory.ok
    assert "15.9 GB" in memory.says and "32 GB" in memory.says
    probes.info = {"MemTotal": 16_000_000_000}
    assert _by_name(run_doctor("lite", probes, product=tmp_path))["memory"].ok


def test_a_port_held_by_our_own_deployment_passes(tmp_path: Path) -> None:
    probes = FakeProbes()
    probes.busy_ports = {80}
    probes.ours_ports = {80}
    assert all(c.ok for c in run_doctor("lite", probes, product=tmp_path))
    probes.ours_ports = set()
    failed = [c.name for c in run_doctor("lite", probes, product=tmp_path) if not c.ok]
    assert failed == ["port-80"]


def test_lite_checks_only_the_front_proxys_port(tmp_path: Path) -> None:
    """ADR-114 Amendment 4: the Glass, Keycloak and Superset publish nothing of their own, so a
    machine using 8080, 8081 or 8088 for something else can still install."""
    probes = FakeProbes()
    probes.busy_ports = {8080, 8081, 8088}
    assert all(c.ok for c in run_doctor("lite", probes, product=tmp_path))


def test_small_checks_tofu_and_the_cloud_cli_not_docker(tmp_path: Path) -> None:
    probes = FakeProbes()
    probes.missing = {"docker", "tofu", "aws", "az"}
    probes.info = None
    checks = _by_name(run_doctor("small", probes, product=tmp_path, cloud="aws"))
    assert {n for n, c in checks.items() if not c.ok} == {"tofu", "cloud-cli"}
    assert "docker-installed" not in checks
    assert "small install" in checks["tofu"].says
    azure = _by_name(run_doctor("small", probes, product=tmp_path, cloud="azure"))["cloud-cli"]
    assert "Azure" in azure.says
    probes.missing = {"aws"}
    assert _by_name(run_doctor("small", probes, product=tmp_path, cloud="azure"))["cloud-cli"].ok
    assert not _by_name(run_doctor("small", probes, product=tmp_path, cloud="aws"))["cloud-cli"].ok


def test_enterprise_checks_kubectl_helm_and_a_cluster_that_answers(tmp_path: Path) -> None:
    """ADR-114 Amendment 16: Enterprise installs onto a cluster `kubectl` already reaches; OpenTofu
    and the cloud's command line arrive with the stage that builds the cluster."""
    probes = FakeProbes()
    probes.missing = {"docker", "tofu", "aws", "az"}
    probes.info = None
    checks = _by_name(run_doctor("enterprise", probes, product=tmp_path))
    assert all(c.ok for c in checks.values()), checks
    assert {"kubectl", "helm", "cluster"} <= set(checks) and "docker-installed" not in checks
    assert "osprey-test-context" in checks["cluster"].says
    probes.missing |= {"kubectl", "helm"}
    probes.kube = None
    checks = _by_name(run_doctor("enterprise", probes, product=tmp_path))
    assert {n for n, c in checks.items() if not c.ok} == {"kubectl", "helm", "cluster"}
    assert "kubectl" in checks["cluster"].fix


def test_enterprise_building_its_cluster_checks_the_build_tools_not_a_cluster(
    tmp_path: Path,
) -> None:
    """ADR-114 Amendment 19: with `--cloud` the cluster does not exist yet — so no cluster check —
    and OpenTofu, the cloud's command line, kubectl and Helm are needed; on Azure kubelogin too,
    since the cluster takes Entra ID sign-ins only."""
    probes = FakeProbes()
    probes.kube = None
    checks = _by_name(run_doctor("enterprise", probes, product=tmp_path, cloud="aws"))
    assert "cluster" not in checks and all(c.ok for c in checks.values()), checks
    assert {"kubectl", "helm", "tofu", "cloud-cli"} <= set(checks) and "kubelogin" not in checks
    probes.missing = {"tofu", "az", "kubelogin"}
    checks = _by_name(run_doctor("enterprise", probes, product=tmp_path, cloud="azure"))
    assert {n for n, c in checks.items() if not c.ok} == {"tofu", "cloud-cli", "kubelogin"}
    assert "Entra ID" in checks["kubelogin"].says
