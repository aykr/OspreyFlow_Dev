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
import yaml
from ospreyflow.doctor import Check, ServerPlan, SystemProbes, format_check, run_doctor

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


def test_the_port_checked_is_the_one_the_deployments_own_address_uses(tmp_path: Path) -> None:
    """Found installing a second Lite deployment at `http://govuk.ospreyflow.localhost:8081`
    (ADR-132 Amendment 1): doctor checked port 80, which that deployment never binds, and said
    nothing of 8081, the one it does. Busy 8081 must fail; busy 80 must not."""
    (tmp_path / "osprey.yaml").write_text(
        "network:\n  public_origin: http://govuk.ospreyflow.localhost:8081\n", encoding="utf-8"
    )
    probes = FakeProbes()
    probes.busy_ports = {80, 8081}
    failed = [c.name for c in run_doctor("lite", probes, product=tmp_path) if not c.ok]
    assert failed == ["port-8081"]


def test_with_no_address_set_the_lite_default_port_80_is_checked(tmp_path: Path) -> None:
    probes = FakeProbes()
    probes.busy_ports = {80}
    failed = [c.name for c in run_doctor("lite", probes, product=tmp_path) if not c.ok]
    assert failed == ["port-80"]


# ---- ADR-114 Amendment 33 (drop 1): `doctor --mode small --config install.yaml` on a server ------


PLAN = ServerPlan(
    host="osprey.example.internal",
    port=443,
    dashboards=True,
    certificate="/etc/ospreyflow/tls/osprey.crt",
    key="/etc/ospreyflow/tls/osprey.key",
    ca="/etc/ospreyflow/tls/org-root.pem",
)


def _server(probes: FakeProbes, tmp_path: Path, plan: ServerPlan = PLAN) -> dict[str, Check]:
    return _by_name(run_doctor("small", probes, product=tmp_path, server=plan))


def test_self_contained_small_checks_docker_memory_disk_443_certificate_and_clock(
    tmp_path: Path,
) -> None:
    checks = _server(FakeProbes(), tmp_path)
    assert all(c.ok for c in checks.values()), [c for c in checks.values() if not c.ok]
    expected = {"docker-installed", "docker-running", "compose", "docker-at-boot", "architecture",
                "memory", "disk", "git", "uv", "python", "clock", "port-443", "port-2480",
                "certificate", "vm-max-map-count", "account", "names"}  # fmt: skip
    assert expected <= set(checks), expected - set(checks)
    # Not the cloud's build tools: this server is installed onto, not built.
    assert "tofu" not in checks and "cloud-cli" not in checks
    assert "port-80" not in checks  # 443 alone (decision 2)
    redirect = ServerPlan(**{**PLAN.__dict__, "redirect_http": True})
    assert "port-80" in _server(FakeProbes(), tmp_path, redirect)


def test_port_443_held_on_any_interface_fails(tmp_path: Path) -> None:
    """The loopback probe Lite uses cannot see a port another program holds on the server's own
    address; the server's check asks every interface."""
    probes = FakeProbes()
    probes.held_elsewhere = {443}
    checks = _server(probes, tmp_path)
    assert not checks["port-443"].ok
    assert "every interface" in checks["port-443"].says or "443" in checks["port-443"].says
    assert "Stop whatever" in checks["port-443"].fix
    probes.ours_ports = {443}
    assert _server(probes, tmp_path)["port-443"].ok  # this deployment's own proxy


def _lan_address() -> str | None:
    """This machine's own non-loopback IPv4 address, found by asking the routing table (a UDP
    socket's `connect` sends nothing)."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(("192.0.2.1", 9))
        except OSError:
            return None
        address = probe.getsockname()[0]
    return None if address.startswith("127.") or address == "0.0.0.0" else address


def test_the_real_probe_sees_a_port_held_on_another_interface() -> None:
    """The real machine, on a high port: a listener on this machine's own network address (not
    loopback) is invisible to the loopback probe and seen by the every-interface one."""
    import socket

    address = _lan_address()
    if address is None:
        pytest.skip("no non-loopback IPv4 address on this machine")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as held:
        held.bind((address, 0))
        held.listen(1)
        port = held.getsockname()[1]
        probes = SystemProbes()
        assert probes.port_free(port) is True  # the trap: loopback sees nothing
        assert probes.port_free_everywhere(port) is False
    assert SystemProbes().port_free_everywhere(port) is True


def test_memory_below_thirty_gib_fails_for_a_small_server(tmp_path: Path) -> None:
    probes = FakeProbes()
    probes.info = {**(probes.info or {}), "MemTotal": 31_900_000_000}  # 29.7 GiB
    memory = _server(probes, tmp_path)["memory"]
    assert not memory.ok and "29.7 GiB" in memory.says and "30 GiB" in memory.says
    probes.info = {**probes.info, "MemTotal": 32_300_000_000}  # 30.1 GiB: a nominal 32 GB server
    assert _server(probes, tmp_path)["memory"].ok
    # Lite's floor is unchanged.
    assert _by_name(run_doctor("lite", probes, product=tmp_path))["memory"].ok


def test_an_unsynchronised_clock_fails_in_words(tmp_path: Path) -> None:
    probes = FakeProbes()
    probes.clock = False
    clock = _server(probes, tmp_path)["clock"]
    assert not clock.ok and "not synchronised" in clock.says and "sign-in" in clock.says
    assert "timedatectl" in clock.fix
    probes.clock = None  # no timedatectl: cannot tell, which is not a pass
    assert not _server(probes, tmp_path)["clock"].ok


def test_a_machine_that_is_not_amd64_fails_naming_the_release_platform(tmp_path: Path) -> None:
    probes = FakeProbes()
    probes.info = {**(probes.info or {}), "Architecture": "aarch64"}
    architecture = _server(probes, tmp_path)["architecture"]
    assert not architecture.ok and "aarch64" in architecture.says
    assert "linux/amd64" in architecture.says
    probes.info = {**probes.info, "Architecture": "amd64"}
    assert _server(probes, tmp_path)["architecture"].ok


def test_a_low_vm_max_map_count_is_a_warning(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    probes = FakeProbes()
    probes.max_map = 65530
    checks = _server(probes, tmp_path)
    warning = checks["vm-max-map-count"]
    assert warning.ok and warning.warn and "65530" in warning.says
    assert "vm.max_map_count=262144" in warning.fix
    assert all(c.ok for c in checks.values())  # a warning does not stop an install
    assert format_check(warning).startswith("⚠")


def test_disk_is_measured_where_docker_keeps_its_data(tmp_path: Path) -> None:
    probes = FakeProbes()
    probes.info = {**(probes.info or {}), "DockerRootDir": "/data/docker"}
    probes.disk_by_path = {"/data/docker": 20.0, str(tmp_path): 900.0}
    disk = _server(probes, tmp_path)["disk"]
    assert not disk.ok and "/data/docker" in disk.says and "20 GB" in disk.says
    assert ("disk", "/data/docker") in probes.asked


@pytest.mark.parametrize(
    ("arrange", "name", "words"),
    [
        (lambda p: setattr(p, "docker_at_boot", False), "docker-at-boot", "systemctl enable --now docker"),
        (lambda p: setattr(p, "python", (3, 10)), "python", "3.12"),
        (lambda p: setattr(p, "certificate_says", (1, "refused: the key does not match\n")),
         "certificate", "does not match"),  # fmt: skip
    ],
)
def test_each_further_server_check_fails_in_words(
    tmp_path: Path, arrange: Callable[[FakeProbes], object], name: str, words: str
) -> None:
    probes = FakeProbes()
    arrange(probes)
    checks = _server(probes, tmp_path)
    assert [c.name for c in checks.values() if not c.ok] == [name]
    assert words in checks[name].says + checks[name].fix


def test_root_and_unresolved_names_are_warnings(tmp_path: Path) -> None:
    probes = FakeProbes()
    probes.root = True
    probes.unresolved = {"id.osprey.example.internal"}
    checks = _server(probes, tmp_path)
    assert checks["account"].warn and "root" in checks["account"].says
    assert checks["names"].warn and "id.osprey.example.internal" in checks["names"].says
    assert all(c.ok for c in checks.values())


def test_doctor_reads_the_server_from_the_answers_file(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import yaml

    answers = tmp_path / "install.yaml"
    answers.write_text(yaml.safe_dump({
        "mode": "small",
        "server": {"address": "https://osprey.example.internal",
                   "certificate": "/etc/ospreyflow/tls/osprey.crt",
                   "key": "/etc/ospreyflow/tls/osprey.key"},
        "components": {"dashboards": False},
    }), encoding="utf-8")  # fmt: skip
    assert rig("doctor", "--mode", "small", "--config", str(answers)) == 0
    out = capsys.readouterr().out
    assert "443" in out and "OpenTofu" not in out
    assert ("certificate", "/etc/ospreyflow/tls/osprey.crt") in rig.probes.asked
    rig.probes.held_elsewhere = {443}
    assert rig("doctor", "--mode", "small", "--config", str(answers)) == 1


# ---- ADR-114 Amendment 33 drop 2: the backups folder (unit 6), the organisation's sign-in (unit 7)


def test_disk_is_measured_at_the_backups_folder_too(tmp_path: Path) -> None:
    """Decision 5 and 8: `ospreyflow backup` writes to `server.backups`, so the doctor asks how much
    is free there — at the nearest folder that exists, as the folder may not yet."""
    backups = tmp_path / "srv" / "ospreyflow" / "backups"
    plan = ServerPlan(**{**PLAN.__dict__, "backups": str(backups)})
    probes = FakeProbes()
    checks = _server(probes, tmp_path, plan)
    assert checks["backups-disk"].ok and str(backups) in checks["backups-disk"].says
    assert ("disk", str(tmp_path)) in probes.asked
    probes.disk_by_path = {str(tmp_path): 5.0}
    low = _server(probes, tmp_path, plan)["backups-disk"]
    assert not low.ok and "5 GB" in low.says and low.fix


def test_organisation_sign_in_needs_its_secret_and_says_what_to_register(tmp_path: Path) -> None:
    """Decision 4: the doctor says the two addresses the organisation registers, refuses to pass
    without `OSPREY_ORG_SIGN_IN_SECRET` in the terminal, and warns when the provider's name does
    not resolve from the server (Keycloak's one route out)."""
    from harness.realm import organisation_redirect_uris

    from schemas.deployment import OspreyConfig

    organisation = {"alias": "org", "issuer": "https://login.microsoftonline.com/t/v2.0"}
    plan = ServerPlan(**{**PLAN.__dict__, "organisation": organisation,
                         "organisation_secret_given": True})  # fmt: skip
    checks = _server(FakeProbes(), tmp_path, plan)
    config = OspreyConfig.model_validate({
        "profile": "small",
        "network": {"public_origin": "https://osprey.example.internal",
                    "tls": {"certificate": "/c.pem", "key": "/k.pem"}},
        "governance": {"organisation_sign_in": "org", "organisation_provider": {
            "label": "Org", "issuer": organisation["issuer"], "client_id": "c"}},
    })  # fmt: skip
    for address in organisation_redirect_uris(config):
        assert address in checks["organisation-sign-in"].says
    assert plan.organisation_uris == organisation_redirect_uris(config)
    assert checks["organisation-sign-in"].ok
    missing = ServerPlan(**{**plan.__dict__, "organisation_secret_given": False})
    refused = _server(FakeProbes(), tmp_path, missing)["organisation-sign-in"]
    assert not refused.ok and "OSPREY_ORG_SIGN_IN_SECRET" in refused.fix
    probes = FakeProbes()
    probes.unresolved = {"login.microsoftonline.com"}
    route = _server(probes, tmp_path, plan)["organisation-route"]
    assert route.warn and "login.microsoftonline.com" in route.says


# ---- ADR-114 Amendment 33, "Step 33" (build order step 33 (c)): joining by email is warned of ---


def test_joining_by_email_is_warned_of_naming_the_takeover_and_never_stops_the_install(
    tmp_path: Path,
) -> None:
    organisation = {"alias": "org", "issuer": "https://login.microsoftonline.com/t/v2.0"}
    plan = ServerPlan(**{**PLAN.__dict__, "organisation": organisation,
                         "organisation_secret_given": True})  # fmt: skip
    assert "organisation-trust-email" not in _server(FakeProbes(), tmp_path, plan)
    trusting = ServerPlan(**{**plan.__dict__,
                             "organisation": {**organisation, "trust_email": "true"}})  # fmt: skip
    warning = _server(FakeProbes(), tmp_path, trusting)["organisation-trust-email"]
    assert warning.ok and warning.warn
    assert "nOAuth" in warning.says and "takes that account over" in warning.says
    assert "security officer" in warning.fix and "trust_email: false" in warning.fix


def test_the_doctor_warns_of_an_installed_deployment_that_joins_by_email(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    """`ospreyflow doctor` with no answers reads the installed `osprey.yaml`."""
    config = rig.product / "osprey.yaml"
    raw = yaml.safe_load(config.read_text(encoding="utf-8")) if config.is_file() else {}
    raw.setdefault("governance", {})["organisation_provider"] = {
        "label": "Org", "issuer": "https://login.example.org/t", "client_id": "c",
        "trust_email": True}
    config.write_text(yaml.safe_dump(raw), encoding="utf-8")
    assert rig("doctor") == 0, "a warning, not a refusal"
    assert "nOAuth" in capsys.readouterr().out
    raw["governance"]["organisation_provider"]["trust_email"] = False
    config.write_text(yaml.safe_dump(raw), encoding="utf-8")
    assert rig("doctor") == 0
    assert "nOAuth" not in capsys.readouterr().out
