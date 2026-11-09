"""`scripts/stack_lease.sh` (ADR-142 decision 4): one holder of the dev stack at a time.

Rule 12's invariant, "one holder of the stack at a time", is
`test_a_second_acquire_while_one_is_held_is_refused_and_names_the_holder`. Rule 15: every case runs
the real script, as a lane does, against a lease directory of the shape the script itself writes;
`docker` is a stand-in on `PATH` that answers as the real one does when the stack is up, when it is
down, and when it cannot answer (the refusal the draft let through).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

BUILD = Path(__file__).resolve().parents[1]
REPO = BUILD.parent
SCRIPT = BUILD / "scripts" / "stack_lease.sh"

_DOCKER = {
    "up": "#!/bin/sh\necho 3f1c0a9b2d7e\necho 9a8b7c6d5e4f\n",
    "down": "#!/bin/sh\nexit 0\n",
    "broken": "#!/bin/sh\necho 'Cannot connect to the Docker daemon' >&2\nexit 1\n",
    # The handover's throwaway test stack (osprey-test-*, osprey-probe-*) up, dev.yaml's down: the real
    # `docker ps --filter name=...` answers with ids only for the named containers.
    "throwaway-up": (
        '#!/bin/sh\nif [ "$1" = ps ]; then case "$*" in *osprey-*) echo 7e7e7e7e7e7e;; esac; fi\nexit 0\n'
    ),
}


@pytest.fixture
def lease(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # Stacks b to e are on the owner's test server: a no-op ssh, so no case ever reaches the real one (the
    # remote cases replace it with a recording one).
    (bin_dir / "ssh").write_text("#!/bin/sh\nexit 0\n")
    (bin_dir / "ssh").chmod(0o755)
    lease_dir = tmp_path / "lease"

    def run(*args: str, docker: str = "down") -> subprocess.CompletedProcess[str]:
        fake = bin_dir / "docker"
        fake.write_text(_DOCKER[docker])
        fake.chmod(0o755)
        env = {
            **os.environ,
            "OSPREY_LEASE_DIR": str(lease_dir),
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        }
        return subprocess.run(
            ["bash", str(SCRIPT), *args], cwd=REPO, env=env, capture_output=True, text=True
        )

    run.lock = lease_dir / "stack.lease"  # type: ignore[attr-defined]
    return run


def test_an_acquire_while_every_stack_is_held_is_refused_and_names_every_holder(lease) -> None:
    """ADR-142 Amendments 3 and 4: throwaway stacks, one holder each, a, b and c on this machine and d and e on
    the owner's test server (9 November 2026; b and c moved there the same day). The first five lanes get a to e in order; the sixth is refused
    and told who holds each."""
    lanes = ["studio", "rules", "case", "admin", "platform"]
    for lane, stack in zip(lanes, "abcde"):
        taken = lease("acquire", lane, f"{lane} run")
        assert taken.returncode == 0, taken.stderr
        assert f"stack {stack}" in taken.stdout
    sixth = lease("acquire", "docs", "screens")
    assert sixth.returncode == 1
    for lane in lanes:
        assert f"holder={lane}" in sixth.stderr
    assert "purpose=studio run" in sixth.stderr
    status = lease("status").stdout
    assert all(f"holder={lane}" in status for lane in lanes)


def test_a_lane_holds_one_stack_at_a_time(lease) -> None:
    assert lease("acquire", "studio", "walk").returncode == 0
    again = lease("acquire", "studio", "a second walk")
    assert again.returncode == 1
    assert "already holds stack a" in again.stderr
    assert not (lease.lock.parent / "stack-b.lease").exists()


def test_a_named_stack_is_taken_even_when_another_is_free(lease) -> None:
    taken = lease("acquire", "case", "conformance", "b")
    assert taken.returncode == 0, taken.stderr
    assert "stack b" in taken.stdout
    assert (lease.lock.parent / "stack-b.lease" / "info").read_text().count("stack=b") == 1
    assert not lease.lock.exists()


def test_acquire_prints_the_ports_of_the_stack_taken(lease) -> None:
    """The export line a lane copies must name its own stack's ports, which tests/port_guard.py lets
    only that stack's holder reach (rule 12: the two read one table, scripts/lane_stacks.tsv)."""
    from tests import port_guard

    lease("acquire", "studio", "walk")
    taken = lease("acquire", "rules", "axe scans")
    line = next(l for l in taken.stdout.splitlines() if "ARCADEDB_HTTP_PORT=" in l)
    pins = dict(w.split("=", 1) for w in line.split() if "=" in w and w.split("=", 1)[0].endswith("_PORT"))
    assert pins["ARCADEDB_HTTP_PORT"] == "2492" and pins["POSTGRES_PORT"] == "55434"
    assert "OSPREY_LANE=rules" in line
    b_ports = {p for p, (stack, _) in port_guard.stack_ports().items() if stack == "b"}
    # ClickHouse's throwaway is stack a's alone (lane_stacks.tsv), so stack b pins it to a closed port.
    assert pins.pop("CLICKHOUSE_HTTP_PORT") == "59994"
    assert {int(v) for v in pins.values()} <= b_ports


def test_release_by_a_lane_not_holding_it_is_refused(lease) -> None:
    lease("acquire", "studio", "phase 6 route tests")
    other = lease("release", "rules")
    assert other.returncode == 1
    assert "rules holds no stack" in other.stderr
    assert lease.lock.is_dir()


def test_release_with_the_dev_stack_still_up_is_refused(lease) -> None:
    lease("acquire", "case", "conformance")
    up = lease("release", "case", docker="up")
    assert up.returncode == 1
    assert "still up" in up.stderr
    assert lease.lock.is_dir()


def test_release_when_docker_cannot_answer_is_refused(lease) -> None:
    lease("acquire", "case", "conformance")
    broken = lease("release", "case", docker="broken")
    assert broken.returncode == 1
    assert "could not say" in broken.stderr
    assert lease.lock.is_dir()


def test_the_holder_releases_once_the_stack_is_down(lease) -> None:
    lease("acquire", "case", "conformance")
    done = lease("release", "case", docker="down")
    assert done.returncode == 0, done.stderr
    assert lease("status").stdout.strip() == "a: free\nb: free\nc: free\nd: free\ne: free"
    assert lease("acquire", "rules", "axe scans").returncode == 0


def test_release_with_the_throwaway_test_stack_still_up_is_refused(lease) -> None:
    """The lanes' live tests run on the throwaway stack (FDE_HANDOVER.md), not dev.yaml's, so the
    lease must see it too: a release with it up is refused (red with only dev.yaml checked)."""
    lease("acquire", "case", "conformance")
    up = lease("release", "case", docker="throwaway-up")
    assert up.returncode == 1
    assert "still up" in up.stderr
    assert lease.lock.is_dir()


# --- The lease's own way up and down: the throwaway stack, never `make dev-up` (8 November 2026) ----
#
# `acquire` told every lane "Bring the stack up with: make dev-up". dev.yaml publishes ArcadeDB on 2480, the
# owner's own deployment's port; a lane following the instruction on 8 November started dev.yaml's containers
# before the bind failed. The leased stack is the throwaway one (SESSIONS_RUNBOOK.md §4).

_THROWAWAY = ("osprey-probe-arcadedb-new", "osprey-test-pg", "osprey-test-valkey-6379", "osprey-test-objectstore")


def _recording_docker(tmp_path: Path) -> tuple[str, Path]:
    log = tmp_path / "docker.log"
    script = f'#!/bin/sh\necho "$@" >> "{log}"\nexit 0\n'
    return script, log


def test_acquire_names_the_throwaway_stack_and_never_dev_up(lease) -> None:
    taken = lease("acquire", "case", "conformance")
    assert taken.returncode == 0
    assert "dev-up" not in taken.stdout
    assert "stack_lease.sh up case" in taken.stdout


def test_up_and_down_start_and_stop_the_throwaway_containers_alone(lease, tmp_path: Path) -> None:
    lease("acquire", "case", "conformance")
    script, log = _recording_docker(tmp_path)
    _DOCKER["recording"] = script
    try:
        assert lease("up", "case", docker="recording").returncode == 0
        assert lease("down", "case", docker="recording").returncode == 0
    finally:
        del _DOCKER["recording"]
    calls = log.read_text().splitlines()
    assert calls[0].split()[:1] == ["start"] and set(calls[0].split()[1:]) == set(_THROWAWAY)
    assert calls[1].split()[:1] == ["stop"] and set(calls[1].split()[1:]) == set(_THROWAWAY)
    assert not any("compose" in c or "dev.yaml" in c for c in calls)


def test_up_is_refused_to_a_lane_not_holding_the_lease(lease, tmp_path: Path) -> None:
    lease("acquire", "studio", "walk")
    script, log = _recording_docker(tmp_path)
    _DOCKER["recording"] = script
    try:
        refused = lease("up", "case", docker="recording")
    finally:
        del _DOCKER["recording"]
    assert refused.returncode == 1 and "case holds no stack" in refused.stderr
    assert not log.exists()


_STACK_B = ("osprey-test-b-arcadedb", "osprey-test-b-pg", "osprey-test-b-valkey", "osprey-test-b-objectstore")


def test_up_and_down_start_and_stop_only_the_holders_own_stack(lease, tmp_path: Path) -> None:
    lease("acquire", "studio", "walk")
    lease("acquire", "rules", "axe scans")
    script, log = _recording_docker(tmp_path)
    _DOCKER["recording"] = script
    try:
        assert lease("up", "rules", docker="recording").returncode == 0
        assert lease("down", "rules", docker="recording").returncode == 0
    finally:
        del _DOCKER["recording"]
    calls = log.read_text().splitlines()
    assert calls[0].split()[:1] == ["start"] and set(calls[0].split()[1:]) == set(_STACK_B)
    assert calls[1].split()[:1] == ["stop"] and set(calls[1].split()[1:]) == set(_STACK_B)


def test_a_release_looks_only_at_its_own_stack(lease) -> None:
    """Stack a up (another lane's live run) must not stop stack b's holder from releasing a stack b that
    is down; and stack a's holder is still refused while a is up (red with one check over every
    osprey-test-* container)."""
    _DOCKER["a-up"] = '#!/bin/sh\nif [ "$1" = ps ]; then case "$*" in *osprey-test-pg*) echo 7e7e7e7e7e7e;; esac; fi\nexit 0\n'
    try:
        lease("acquire", "studio", "walk")
        lease("acquire", "rules", "axe scans")
        b = lease("release", "rules", docker="a-up")
        a = lease("release", "studio", docker="a-up")
    finally:
        del _DOCKER["a-up"]
    assert b.returncode == 0, b.stderr
    assert a.returncode == 1 and "still up" in a.stderr



@pytest.mark.parametrize(("first", "stack", "endpoint"), [(False, "a", "localhost:9000"), (True, "b", "localhost:9002")])
def test_acquire_pins_the_stack_s_own_object_store(lease, first: bool, stack: str, endpoint: str) -> None:
    """Found 8 November 2026 (the rules lane): with no object-store pin, a run on stack b reached stack a's
    store on 9000 (MINIO_ENDPOINT's default). The export line names the stack's own store (red without it)."""
    if first:
        lease("acquire", "studio", "walk")
    taken = lease("acquire", "rules", "axe scans")
    assert f"stack {stack}" in taken.stdout
    assert f"MINIO_ENDPOINT={endpoint}" in taken.stdout


# --- Stacks on the owner's test server (9 November 2026) ---------------------------------------------------
# scripts/lane_stack_hosts.tsv names a remote stack's ssh host. Its containers are started and stopped there
# (docker with DOCKER_HOST=ssh://<host>), and `up` opens one ssh tunnel carrying each of the stack's ports
# to this machine's localhost, so a test and the port guard see the same localhost ports as for a local stack.

_STACK_D_PORTS = ("2494", "55436", "6382", "9006")


def _recording_tools(tmp_path: Path) -> tuple[str, str, Path]:
    log = tmp_path / "tools.log"
    docker = f'#!/bin/sh\necho "docker host=${{DOCKER_HOST:-local}} $*" >> "{log}"\nexit 0\n'
    ssh = f'#!/bin/sh\necho "ssh $*" >> "{log}"\nexit 0\n'
    return docker, ssh, log


def _take_stack_d(lease) -> None:
    for lane in ("studio", "rules", "case"):
        lease("acquire", lane, "a local run")
    taken = lease("acquire", "admin", "a remote run")
    assert "stack d" in taken.stdout, taken.stdout + taken.stderr


def test_a_remote_stack_is_started_on_its_host_and_tunnelled_to_localhost(lease, tmp_path: Path) -> None:
    _take_stack_d(lease)
    docker, ssh, log = _recording_tools(tmp_path)
    _DOCKER["recording"] = docker
    (tmp_path / "bin" / "ssh").write_text(ssh)
    (tmp_path / "bin" / "ssh").chmod(0o755)
    try:
        assert lease("up", "admin", docker="recording").returncode == 0
    finally:
        del _DOCKER["recording"]
    calls = log.read_text().splitlines()
    start = [c for c in calls if c.startswith("docker") and " start " in c]
    assert start and all("host=ssh://ospreyflow-test" in c for c in start), calls
    assert "osprey-test-d-arcadedb" in start[0]
    tunnel = [c for c in calls if c.startswith("ssh") and " -L " in c]
    assert len(tunnel) == 1, calls
    for port in _STACK_D_PORTS:
        assert f"-L 127.0.0.1:{port}:127.0.0.1:{port}" in tunnel[0], tunnel
    assert "ospreyflow-test" in tunnel[0]


def test_a_remote_stack_s_down_closes_its_tunnel_and_stops_it_on_its_host(lease, tmp_path: Path) -> None:
    _take_stack_d(lease)
    docker, ssh, log = _recording_tools(tmp_path)
    _DOCKER["recording"] = docker
    (tmp_path / "bin" / "ssh").write_text(ssh)
    (tmp_path / "bin" / "ssh").chmod(0o755)
    try:
        assert lease("down", "admin", docker="recording").returncode == 0
    finally:
        del _DOCKER["recording"]
    calls = log.read_text().splitlines()
    assert any(c.startswith("ssh") and "-O exit" in c for c in calls), calls
    stop = [c for c in calls if c.startswith("docker") and " stop " in c]
    assert stop and all("host=ssh://ospreyflow-test" in c for c in stop), calls


def test_a_local_stack_never_reaches_the_server(lease, tmp_path: Path) -> None:
    lease("acquire", "studio", "a local run")
    docker, ssh, log = _recording_tools(tmp_path)
    _DOCKER["recording"] = docker
    (tmp_path / "bin" / "ssh").write_text(ssh)
    (tmp_path / "bin" / "ssh").chmod(0o755)
    try:
        assert lease("up", "studio", docker="recording").returncode == 0
        assert lease("down", "studio", docker="recording").returncode == 0
    finally:
        del _DOCKER["recording"]
    calls = log.read_text().splitlines()
    assert not any(c.startswith("ssh") for c in calls), calls
    assert all("host=local" in c for c in calls if c.startswith("docker")), calls


def test_a_remote_stack_s_release_asks_its_own_host(lease, tmp_path: Path) -> None:
    _take_stack_d(lease)
    docker, ssh, log = _recording_tools(tmp_path)
    _DOCKER["recording"] = docker
    try:
        assert lease("release", "admin", docker="recording").returncode == 0
    finally:
        del _DOCKER["recording"]
    ps = [c for c in log.read_text().splitlines() if " ps " in c]
    assert ps and all("host=ssh://ospreyflow-test" in c for c in ps), ps


# --- Local stacks off on this machine (the owner, 9 November 2026: test on the server, not this machine) -----
# While <lease dir>/no-local-stacks exists, a stack with no host in lane_stack_hosts.tsv is never leased.


def test_with_local_stacks_off_a_default_acquire_skips_the_local_stack(lease) -> None:
    lease.lock.parent.mkdir(parents=True, exist_ok=True)
    (lease.lock.parent / "no-local-stacks").touch()
    taken = lease("acquire", "studio", "a run")
    assert taken.returncode == 0, taken.stderr
    assert "stack b" in taken.stdout
    assert not lease.lock.exists()


def test_with_local_stacks_off_naming_the_local_stack_is_refused(lease) -> None:
    lease.lock.parent.mkdir(parents=True, exist_ok=True)
    (lease.lock.parent / "no-local-stacks").touch()
    taken = lease("acquire", "studio", "the ClickHouse run", "a")
    assert taken.returncode == 1
    assert "local stacks are off" in taken.stderr
    assert not lease.lock.exists()


def test_with_local_stacks_off_status_says_so(lease) -> None:
    lease.lock.parent.mkdir(parents=True, exist_ok=True)
    (lease.lock.parent / "no-local-stacks").touch()
    status = lease("status").stdout.splitlines()
    assert "a: off (local stacks are off on this machine)" in status
    assert "b: free" in status
