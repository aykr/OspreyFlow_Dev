"""`scripts/stack_lease.sh` (ADR-142 decision 4): one holder of the dev stack at a time.

Rule 12's invariant, "one holder of the stack at a time", is
`test_a_second_acquire_while_one_is_held_is_refused_and_names_the_holder`. Rule 15: every case runs
the real script, as a lane does, against a lease directory of the shape the script itself writes;
`docker` is a stand-in on `PATH` that answers as the real one does when the stack is up, when it is
down, and when it cannot answer (the refusal the draft let through).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
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


def _names_docker(down: tuple[str, ...] = ()) -> str:
    """A docker whose `ps --format {{.Names}} --filter name=^/?<c>$ …` answers as the real one does: the name of
    each filtered container that is running, and nothing for one that is stopped (`down`)."""
    skip = " ".join(down)
    return (
        "#!/bin/sh\n"
        'if [ "$1" = ps ]; then\n'
        '  for a; do case "$a" in name=*) n="${a#name=^/?}"; n="${n%$}";'
        f' case " {skip} " in *" $n "*) ;; *) echo "$n";; esac;; esac; done\n'
        "fi\nexit 0\n"
    )


_DOCKER["all-up"] = _names_docker()


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
            ["bash", str(SCRIPT), *args], cwd=REPO, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL
        )

    run.lock = lease_dir / "stack.lease"  # type: ignore[attr-defined]
    return run


def test_an_acquire_while_every_stack_is_held_is_refused_and_names_every_holder(lease) -> None:
    """ADR-142 Amendments 3 and 4: throwaway stacks, one holder each, a, b and c on this machine and d and e on
    the owner's test server (9 November 2026; b and c moved there the same day). The first five lanes get a to e in order; the sixth is refused
    and told who holds each."""
    lanes = ["studio", "rules", "case", "admin", "platform", "studio-b", "rules-b"]
    for lane, stack in zip(lanes, "abcdefg"):
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
    # Stack b has its own ClickHouse on the server (9 November 2026), pinned like its other ports.
    assert pins["CLICKHOUSE_HTTP_PORT"] == "18124"
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
    assert lease("status").stdout.strip() == "a: free\nb: free\nc: free\nd: free\ne: free\nf: free\ng: free"
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


# `up` reads the stack's Postgres `max_connections` (`docker exec … psql`); a recording fake answers as one
# that already allows the test stacks' 400, so `up` neither changes nor restarts it.
_PG_AT_400 = 'case "$1" in exec) echo 400;; esac\n'


def _start_stop(log: Path) -> list[str]:
    return [c for c in log.read_text().splitlines() if c.split()[0] in ("start", "stop")]


def _recording_docker(tmp_path: Path) -> tuple[str, Path]:
    log = tmp_path / "docker.log"
    script = f'#!/bin/sh\necho "$@" >> "{log}"\n{_PG_AT_400}exit 0\n'
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
    calls = _start_stop(log)
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


_STACK_B = ("osprey-test-b-arcadedb", "osprey-test-b-pg", "osprey-test-b-valkey", "osprey-test-b-objectstore", "osprey-test-b-clickhouse")


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
    calls = _start_stop(log)
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
    docker = f'#!/bin/sh\necho "docker host=${{DOCKER_HOST:-local}} $*" >> "{log}"\n{_PG_AT_400}exit 0\n'
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


# --- remote: a lane's command run on its remote stack's own host (9 November 2026) -----------------------------
# Over the tunnel each database call crossed the internet (about 0.3 to 0.7 s), so a live run was network-bound;
# `remote` copies the worktree to the stack's host and runs the command there, beside the containers.


def _remote_tools(tmp_path: Path) -> Path:
    """ssh and rsync stand-ins that record their arguments (and what rsync was told to send) and answer 0."""
    log = tmp_path / "remote.log"
    bin_dir = tmp_path / "bin"
    # Records each call and what it was sent; answers 3 to the "is the last run alive" check when told to.
    (bin_dir / "ssh").write_text(
        f'#!/bin/sh\necho "ssh $*" >> "{log}"\nsed "s/^/stdin /" >> "{log}"\n'
        f'case "$*" in *"kill -0"*) [ -f "{tmp_path}/alive" ] && exit 3;; esac\nexit 0\n'
    )
    (bin_dir / "rsync").write_text(
        "#!/bin/sh\n"
        f'for a in "$@"; do case "$a" in --files-from=*) sed "s/^/sent /" "${{a#--files-from=}}" >> "{log}";; esac; done\n'
        f'echo "rsync $*" >> "{log}"\nexit 0\n'
    )
    for tool in ("ssh", "rsync"):
        (bin_dir / tool).chmod(0o755)
    return log


def _lane_worktree(tmp_path: Path) -> Path:
    """A tiny lane worktree: tracked files, an owner-edited osprey.yaml, an untracked new test file, and a
    gitignored dataset of the shape config/real_data_exceptions.yaml admits."""
    wt = tmp_path / "wt"
    (wt / "OspreyFlow_Core").mkdir(parents=True)
    (wt / "OspreyFlow_Build" / "tests").mkdir(parents=True)
    (wt / ".gitignore").write_text("OspreyFlow_Core/data/\n")
    (wt / "OspreyFlow_Core" / "osprey.yaml").write_text("committed: true\n")
    (wt / "OspreyFlow_Build" / "tests" / "test_x.py").write_text("")
    git = ["git", "-C", str(wt), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "init"], check=True)
    (wt / "OspreyFlow_Core" / "osprey.yaml").write_text("owner_local: secret\n")
    (wt / "OspreyFlow_Build" / "tests" / "test_new.py").write_text("")
    (wt / "OspreyFlow_Core" / "data").mkdir()
    (wt / "OspreyFlow_Core" / "data" / "real_dataset.csv").write_text("real,data\n")
    return wt


def _remote(lease, tmp_path: Path, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    lease("status", docker="all-up")  # writes the fixture's docker stand-in onto PATH
    env = {**os.environ, "OSPREY_LEASE_DIR": str(tmp_path / "lease"),
           "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}"}
    return subprocess.run(["bash", str(SCRIPT), "remote", *args], cwd=cwd, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL)


def test_remote_sends_only_what_git_tracks_and_never_the_local_osprey_yaml(lease, tmp_path: Path) -> None:
    """Rule 9: a gitignored dataset never leaves this machine, and osprey.yaml goes as committed."""
    lease("acquire", "studio", "a run")  # stack a: local
    lease("acquire", "case", "a run")    # stack b: on the server
    log = _remote_tools(tmp_path)
    wt = _lane_worktree(tmp_path)
    ran = _remote(lease, tmp_path, wt / "OspreyFlow_Build", "case", "--", "pytest", "-q", "tests")
    assert ran.returncode == 0, ran.stderr
    sent = {l[len("sent "):] for l in log.read_text().splitlines() if l.startswith("sent ")}
    assert "OspreyFlow_Build/tests/test_x.py" in sent and "OspreyFlow_Build/tests/test_new.py" in sent
    assert not any("real_dataset" in f or f.startswith("OspreyFlow_Core/data") for f in sent), sent
    assert "OspreyFlow_Core/osprey.yaml" not in sent
    assert any("cat > osprey-runs/case/OspreyFlow_Core/osprey.yaml" in l for l in log.read_text().splitlines())


def test_remote_runs_the_command_on_the_stack_s_host_with_its_ports_and_lease(lease, tmp_path: Path) -> None:
    lease("acquire", "studio", "a run")
    lease("acquire", "case", "a run")
    log = _remote_tools(tmp_path)
    wt = _lane_worktree(tmp_path)
    assert _remote(lease, tmp_path, wt / "OspreyFlow_Build", "case", "--", "pytest", "-q", "tests").returncode == 0
    text = log.read_text()
    script = [l[len("stdin "):] for l in text.splitlines() if l.startswith("stdin ")]
    assert "cd osprey-runs/case/OspreyFlow_Build/ || exit 1" in script, script
    export = next(l for l in script if l.startswith("export "))
    assert "ARCADEDB_HTTP_PORT=2492" in export and "POSTGRES_PORT=55434" in export and "OSPREY_LANE=case" in export
    assert "OSPREY_LEASE_DIR=$HOME/osprey-runs/case.meta/lease" in export
    assert "pytest -q tests " in script
    assert any(l.startswith("export OSPREY_RUN_TAG=$HOME/osprey-runs/case.meta/runs/") for l in script), script
    # A call's command spans lines in the log; the start is the one call holding nohup setsid.
    assert text.count("nohup setsid") == 1, text
    mirrored = [l for l in log.read_text().splitlines() if "case.meta/lease/stack-b.lease/info" in l]
    assert mirrored, log.read_text()


def test_remote_is_refused_for_a_local_stack_and_for_a_lane_holding_none(lease, tmp_path: Path) -> None:
    log = _remote_tools(tmp_path)
    wt = _lane_worktree(tmp_path)
    none = _remote(lease, tmp_path, wt, "case", "--", "true")
    assert none.returncode == 1 and "holds no stack" in none.stderr
    lease("acquire", "studio", "a run")  # stack a: local
    local = _remote(lease, tmp_path, wt, "studio", "--", "true")
    assert local.returncode == 1 and "runs on this machine" in local.stderr
    assert not log.exists() or "rsync" not in log.read_text()



# --- A ClickHouse for each server stack (the owner, 9 November 2026) -------------------------------------------
# Only stack a had one, and a is off on the owner's machine, so the analytics suite's ClickHouse half ran nowhere.


def _export_line(taken: subprocess.CompletedProcess[str]) -> dict[str, str]:
    line = next(l for l in taken.stdout.splitlines() if "ARCADEDB_HTTP_PORT=" in l)
    return dict(w.split("=", 1) for w in line.split() if "=" in w)


def test_a_server_stack_pins_its_own_clickhouse_and_its_credentials_never_the_closed_port(lease) -> None:
    lease("acquire", "studio", "a run")
    pins = _export_line(lease("acquire", "rules", "a run"))  # stack b
    assert pins["CLICKHOUSE_HTTP_PORT"] == "18124"
    assert pins["CLICKHOUSE_USER"] == "osprey" and pins["CLICKHOUSE_PASSWORD"] == "throwaway"
    assert "59994" not in pins.values()


def test_stack_a_keeps_its_own_clickhouse_port_and_no_server_credentials(lease) -> None:
    pins = _export_line(lease("acquire", "studio", "a run"))  # stack a: the test starts its own ClickHouse
    assert pins["CLICKHOUSE_HTTP_PORT"] == "18123"
    assert "CLICKHOUSE_USER" not in pins


def test_every_server_stack_s_clickhouse_is_started_and_stopped_with_it(lease, tmp_path: Path) -> None:
    for lane in ("studio", "rules"):
        lease("acquire", lane, "a run")
    script, log = _recording_docker(tmp_path)
    _DOCKER["recording"] = script
    try:
        assert lease("up", "rules", docker="recording").returncode == 0
    finally:
        del _DOCKER["recording"]
    assert "osprey-test-b-clickhouse" in log.read_text()



# --- A remote run survives a dropped ssh session (9 November 2026: studio's run lost its session an hour in) -----


def test_remote_starts_the_run_detached_with_keepalives_and_follows_its_log(lease, tmp_path: Path) -> None:
    lease("acquire", "studio", "a run")
    lease("acquire", "case", "a run")
    log = _remote_tools(tmp_path)
    wt = _lane_worktree(tmp_path)
    assert _remote(lease, tmp_path, wt / "OspreyFlow_Build", "case", "--", "true").returncode == 0
    calls = [l for l in log.read_text().splitlines() if l.startswith("ssh")]
    assert all("ServerAliveInterval=" in c for c in calls), calls
    text = log.read_text()  # a call's command spans lines in the log
    start = next(l for l in text.splitlines() if "nohup setsid" in l)
    assert "> osprey-runs/case.meta/runs/" in start and "/log 2>&1" in start
    assert "tail -n +1 -F --pid=" in text, text


def test_a_second_remote_run_is_refused_while_the_last_is_alive(lease, tmp_path: Path) -> None:
    lease("acquire", "studio", "a run")
    lease("acquire", "case", "a run")
    log = _remote_tools(tmp_path)
    (tmp_path / "alive").touch()
    wt = _lane_worktree(tmp_path)
    ran = _remote(lease, tmp_path, wt / "OspreyFlow_Build", "case", "--", "true")
    assert ran.returncode == 1 and "still running" in ran.stderr and "remote-log case" in ran.stderr
    assert "tail -n +1 -F" not in log.read_text()
    # refused before the copy that run is reading is touched (rules' finding, 9 November 2026)
    text = log.read_text()
    assert "rsync" not in text and "uv sync" not in text and "npm ci" not in text and "git add -A" not in text, text


def test_remote_log_follows_the_lane_s_last_run_on_its_host(lease, tmp_path: Path) -> None:
    lease("acquire", "studio", "a run")
    lease("acquire", "case", "a run")
    log = _remote_tools(tmp_path)
    lease("status")
    env = {**os.environ, "OSPREY_LEASE_DIR": str(tmp_path / "lease"),
           "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}"}
    ran = subprocess.run(["bash", str(SCRIPT), "remote-log", "case"], env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    assert ran.returncode == 0, ran.stderr
    text = log.read_text()  # a call's command spans lines in the log
    assert text.count("tail -n +1 -F") == 1, text
    assert "ospreyflow-test l=osprey-runs/case.meta/runs/last" in text, text


# --- offline: a lane's offline tests on the server, with no stack (the owner, 9 November 2026) ----------------
# The closed ports and no lane, as an offline run here; this machine keeps only what needs Node (test-js).


def test_offline_runs_on_the_server_with_no_stack_the_closed_ports_and_no_lane(lease, tmp_path: Path) -> None:
    log = _remote_tools(tmp_path)
    wt = _lane_worktree(tmp_path)
    ran = _remote(lease, tmp_path, wt / "OspreyFlow_Build", "case", "--", "make", "-k", "test", "SKIP_JS=1")
    assert ran.returncode == 1 and "holds no stack" in ran.stderr  # remote still needs a lease
    env = {**os.environ, "OSPREY_LEASE_DIR": str(tmp_path / "lease"),
           "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}"}
    log.write_text("")
    off = subprocess.run(["bash", str(SCRIPT), "offline", "case", "--", "make", "-k", "test", "SKIP_JS=1"],
                         cwd=wt / "OspreyFlow_Build", env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    assert off.returncode == 0, off.stderr
    text = log.read_text()
    assert "ospreyflow-test" in text
    export = next(l for l in text.splitlines() if l.startswith("stdin export "))
    for pin in ("ARCADEDB_HTTP_PORT=59991", "POSTGRES_PORT=59992", "VALKEY_PORT=59993", "CLICKHOUSE_HTTP_PORT=59994"):
        assert pin in export, export
    assert "OSPREY_LANE" not in export
    # The lane's own Playwright ports on the server too, where lanes' copies run side by side (T2).
    assert "OSPREY_PORTS_LANE=case" in export, export
    assert "OSPREY_PORTS_SLOT=2" in export, export  # case's row in scripts/lane_ports.tsv
    assert "mkdir -p osprey-runs/case.meta/lease" in text and "/info" not in text  # an empty lease directory
    assert "stdin make -k test SKIP_JS=1 " in text


@pytest.mark.parametrize("lane", ["admin-ddl", "admin-b"])
def test_a_lane_with_no_row_of_its_own_gets_no_slot_but_a_refusal(lease, tmp_path: Path, lane: str) -> None:
    """A sub-lane or a sister lane never takes its parent's Playwright ports by its name's prefix: two
    `who`s run on the server side by side (`admin` and `admin-ddl` did on 10 November). It is exported as
    unlisted, which `apps/lanePorts.ts` refuses in words, and nothing but a Playwright run reads it."""
    log = _remote_tools(tmp_path)
    wt = _lane_worktree(tmp_path)
    env = {**os.environ, "OSPREY_LEASE_DIR": str(tmp_path / "lease"),
           "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}"}
    log.write_text("")
    off = subprocess.run(["bash", str(SCRIPT), "offline", lane, "--", "make", "test"],
                         cwd=wt / "OspreyFlow_Build", env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    assert off.returncode == 0, off.stderr
    export = next(l for l in log.read_text().splitlines() if l.startswith("stdin export "))
    assert f"OSPREY_PORTS_SLOT=unlisted-{lane}" in export, export
    assert "OSPREY_PORTS_SLOT=1" not in export, export  # admin's


def test_remote_log_follows_an_offline_run_when_no_stack_is_held(lease, tmp_path: Path) -> None:
    log = _remote_tools(tmp_path)
    lease("status")
    env = {**os.environ, "OSPREY_LEASE_DIR": str(tmp_path / "lease"),
           "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}"}
    ran = subprocess.run(["bash", str(SCRIPT), "remote-log", "case"], env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    assert ran.returncode == 0, ran.stderr
    assert "ospreyflow-test l=osprey-runs/case.meta/runs/last" in log.read_text()


def test_make_test_leaves_out_test_js_only_when_asked() -> None:
    # A clean environment: run inside `make test SKIP_JS=1` (as on the server), SKIP_JS reaches this make through
    # MAKEFLAGS and the plain dry run would leave test-js out too (found at case-b's merge, 9 November 2026).
    env = {k: v for k, v in os.environ.items() if k not in ("MAKEFLAGS", "MFLAGS", "MAKELEVEL", "SKIP_JS")}

    def dry(*extra: str) -> str:
        return subprocess.run(["make", "-n", "-C", str(BUILD), "test", *extra],
                              capture_output=True, text=True, env=env).stdout
    assert "test-js" in dry()
    skipped = dry("SKIP_JS=1")
    assert "test-js" not in skipped and "pytest" in skipped



# --- The server copy behaves as a checkout (9 November 2026: the first offline run failed 66 cases for want of git,
# Node and a clean root) -------------------------------------------------------------------------------------


def test_the_server_copy_is_a_repository_has_the_glass_packages_and_keeps_its_runs_beside_it(lease, tmp_path: Path) -> None:
    log = _remote_tools(tmp_path)
    wt = _lane_worktree(tmp_path)
    env = {**os.environ, "OSPREY_LEASE_DIR": str(tmp_path / "lease"),
           "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}"}
    off = subprocess.run(["bash", str(SCRIPT), "offline", "case", "--", "true"],
                         cwd=wt / "OspreyFlow_Build", env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    assert off.returncode == 0, off.stderr
    text = log.read_text()
    assert "git init -q" in text and "git add -A" in text and "commit -q --allow-empty" in text
    assert "npm ci" in text and "package-lock.json" in text
    assert "$HOME/.local/node/bin" in next(l for l in text.splitlines() if l.startswith("stdin export "))
    assert "osprey-runs/case.meta/runs/" in text
    # nothing of the runs or the lease is written inside the copy's root (the old place is only asked about)
    for written in ("mkdir -p osprey-runs/case/.runs", "> osprey-runs/case/.runs", "osprey-runs/case/.osprey-lease"):
        assert written not in text, written



def test_a_run_in_the_old_layout_is_seen_and_its_folders_never_pruned(lease, tmp_path: Path) -> None:
    """A run started before ada8460 keeps its log and pid in <copy>/.runs: a later call must see it alive and never
    prune it (rules' live log was deleted so, 9 November 2026)."""
    lease("acquire", "studio", "a run")
    lease("acquire", "case", "a run")
    log = _remote_tools(tmp_path)
    wt = _lane_worktree(tmp_path)
    assert _remote(lease, tmp_path, wt / "OspreyFlow_Build", "case", "--", "true").returncode == 0
    text = log.read_text()
    assert "osprey-runs/case/.runs/last/pid" in text  # the old place asked
    prune = next(l for l in text.splitlines() if l.startswith("skip=("))
    assert '".runs"' in prune and '".osprey-lease"' in prune



# --- Every server run names its slowest tests and its wall time (admin's T1 part 1, 10 November 2026) ---------
# Studio's L1.7 live set ran 2½ hours on stack f with nothing in its log saying where the time went.


def _started(text: str) -> str:
    return next(l for l in text.splitlines() if "nohup setsid" in l)


def test_a_remote_run_lists_its_30_slowest_tests_and_logs_its_wall_time_with_its_stack_and_lease(lease, tmp_path: Path) -> None:
    lease("acquire", "studio", "a run")
    lease("acquire", "case", "a run")  # stack b, on the server
    log = _remote_tools(tmp_path)
    wt = _lane_worktree(tmp_path)
    assert _remote(lease, tmp_path, wt / "OspreyFlow_Build", "case", "--", "pytest", "-q", "tests").returncode == 0
    text = log.read_text()
    export = next(l for l in text.splitlines() if l.startswith("stdin export "))
    assert "PYTEST_ADDOPTS=--durations=30" in export, export
    assert "OSPREY_PORTS_LANE=case" in export, export
    assert "OSPREY_PORTS_SLOT=2" in export, export
    start = _started(text)
    assert "Wall time:" in start and "stack b, the lease case took at 20" in start, start
    assert "/wall" in start and "set-up before it" in start, start  # the seconds kept beside the log, for a table
    assert "cp osprey-runs/case.meta/lease/stack-b.lease/info osprey-runs/case.meta/runs/" in text, text  # kept with the run


def test_an_offline_run_lists_its_30_slowest_tests_and_logs_its_wall_time(lease, tmp_path: Path) -> None:
    log = _remote_tools(tmp_path)
    wt = _lane_worktree(tmp_path)
    lease("status")
    env = {**os.environ, "OSPREY_LEASE_DIR": str(tmp_path / "lease"),
           "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}"}
    off = subprocess.run(["bash", str(SCRIPT), "offline", "case", "--", "make", "-k", "test", "SKIP_JS=1"],
                         cwd=wt / "OspreyFlow_Build", env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    assert off.returncode == 0, off.stderr
    text = log.read_text()
    assert "PYTEST_ADDOPTS=--durations=30" in next(l for l in text.splitlines() if l.startswith("stdin export "))
    start = _started(text)
    assert "Wall time:" in start and "no stack, no lease" in start, start


# `ps -o ppid=` right-aligns the pid on Linux ("runner  192907" on the owner's server, 10 November 2026)
# and not on macOS, so the case is run both ways: as ps prints it here, and padded as the server prints it.
_RUNNER = {
    "as ps prints it": 'echo "runner $(ps -o ppid= -p $PPID)"',
    "padded, as on the server": 'printf "runner %10s\\n" "$(ps -o ppid= -p $PPID)"',
}


@pytest.mark.parametrize("runner", list(_RUNNER))
def test_the_start_line_the_host_receives_runs_and_keeps_the_command_s_own_exit_code(
    lease, tmp_path: Path, runner: str
) -> None:
    """The start call exactly as ssh received it (after this machine's own quoting), run as the host runs it, with
    HOME a folder here: red if a lost backslash expands $? or $$ on this machine, or the line goes missing."""
    lease("acquire", "studio", "a run")
    lease("acquire", "case", "a run")
    log = _remote_tools(tmp_path)
    home = tmp_path / "home"
    (home / "osprey-runs" / "case" / "OspreyFlow_Build").mkdir(parents=True)
    (home / "osprey-runs" / "case.meta" / "lease" / "stack-b.lease").mkdir(parents=True)
    (home / "osprey-runs" / "case.meta" / "lease" / "stack-b.lease" / "info").write_text("holder=case\n")
    bin_dir = tmp_path / "bin"
    # The recording ssh, which also runs the start call (the one holding nohup setsid) on its own stdin, as the
    # host would; setsid is stood in for here, since macOS has none.
    (bin_dir / "ssh").write_text(
        f'#!/bin/bash\necho "ssh $*" >> "{log}"\nin="$(cat)"\nprintf "%s\\n" "$in" | sed "s/^/stdin /" >> "{log}"\n'
        f'for a; do last="$a"; done\n'
        f'case "$last" in *"nohup setsid"*) cd "{home}" && printf "%s\\n" "$in" | HOME="{home}" bash -c "$last";; esac\nexit 0\n'
    )
    (bin_dir / "setsid").write_text('#!/bin/sh\nexec "$@"\n')
    for tool in ("ssh", "setsid"):
        (bin_dir / tool).chmod(0o755)
    wt = _lane_worktree(tmp_path)
    ran = _remote(lease, tmp_path, wt / "OspreyFlow_Build", "case", "--", "sh", "-c", f"echo hello; {_RUNNER[runner]}; exit 7")
    assert ran.returncode == 0, ran.stderr
    runs = home / "osprey-runs" / "case.meta" / "runs"
    run = next(p for p in runs.iterdir() if p.name != "last")
    for _ in range(100):
        if (run / "exit").exists():
            break
        time.sleep(0.05)
    assert (run / "exit").read_text().strip() == "7", (run / "log").read_text()
    assert (run / "wall").read_text().strip().isdigit()
    lines = (run / "log").read_text().splitlines()
    # The pid file holds the host's own shell, the one running cmd.sh (what follow's tail --pid waits on).
    # By field, not by the exact line: how wide ps prints a pid is the platform's, not the script's.
    assert lines[1].split() == ["runner", (run / "pid").read_text().strip()], lines
    assert lines[0] == "hello", lines
    assert lines[-1].startswith("Wall time: ") and "exit 7 (stack b, the lease case took at 20" in lines[-1], lines
    assert "set-up before it" in lines[-1], lines
    assert (run / "lease").read_text() == "holder=case\n"



# --- A run's servers are reaped when it ends (T1 part 5; CARRIES: platform-b's upgfix gates, 10 November 2026) --
# A stopped server run left harness-a11y's vite (5893/5894) and harness.webapp (7919) alive: they leave the run's
# process group, so the lane's own slot ports stayed held and its next harness-a11y failed "already used". Each run
# is tagged in its environment (OSPREY_RUN_TAG, inherited through setsid and double forks, which a process group is
# not), and every process still carrying the tag is ended when the run ends, on TERM too (a run starts with INT and
# HUP ignored, so neither is claimed). `reap <lane>` ends what a run whose wrapper was itself killed left behind.
# The leftover here is a real double-forked, setsid'd process (a vite's shape), not a child of the run's shell.

#: The reaper reads /proc and the run is started with setsid, as on the hosts (Linux). Where either is missing (macOS)
#: these cases cannot run, and say so rather than fail (T1 part 5's review, must-fix 7).
_REAPS = pytest.mark.skipif(
    not Path("/proc/self/environ").exists() or shutil.which("setsid") is None,
    reason="the reaper reads /proc and a run is started with setsid, as on the Linux hosts; this machine has "
    "no /proc or no setsid",
)

_DETACHED = (
    "import os, sys, time\n"
    "if os.fork(): sys.exit(0)\n"
    "os.setsid()\n"
    "if os.fork(): sys.exit(0)\n"
    "open(sys.argv[1], 'w').write(str(os.getpid()))\n"
    "time.sleep(300)\n"
)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # A zombie still answers kill 0; it has ended, and only waits for its parent.
    stat = Path(f"/proc/{pid}/stat")
    return not (stat.exists() and stat.read_text().split(") ", 1)[1].startswith("Z"))


def _gone_within(pid: int, seconds: float = 8.0) -> bool:
    for _ in range(int(seconds / 0.1)):
        if not _alive(pid):
            return True
        time.sleep(0.1)
    return False


def _end(*pids: int) -> None:
    for pid in pids:
        try:
            os.kill(pid, 9)
        except ProcessLookupError:
            pass


def _end_tagged(home: Path) -> None:
    """Whatever a run under this case's own home left (a plant may switch the reaper off), and nothing else."""
    mark = f"OSPREY_RUN_TAG={home}/".encode()
    for env in Path("/proc").glob("[0-9]*/environ"):
        try:
            if any(v.startswith(mark) for v in env.read_bytes().split(b"\0")):
                os.kill(int(env.parent.name), 9)
        except (OSError, ValueError):
            pass


def _host(tmp_path: Path) -> Path:
    """The recording ssh, running on this machine (HOME a folder here) both the start call and the reap call, as
    the host would; setsid is the real one, so the run is its own session as on the server."""
    log = _remote_tools(tmp_path)
    home = tmp_path / "home"
    (home / "osprey-runs" / "case" / "OspreyFlow_Build").mkdir(parents=True)
    (home / "osprey-runs" / "case.meta" / "lease" / "stack-b.lease").mkdir(parents=True)
    (home / "osprey-runs" / "case.meta" / "lease" / "stack-b.lease" / "info").write_text("holder=case\n")
    (tmp_path / "bin" / "ssh").write_text(
        f'#!/bin/bash\necho "ssh $*" >> "{log}"\nin="$(cat)"\n'
        f'for a; do last="$a"; done\n'
        # The remote command's own exit code, as a real ssh returns it (rule 15: `reap`'s refusal is an exit code).
        f'case "$last" in *"nohup setsid"*|"bash -s -- "*) cd "{home}" && printf "%s\\n" "$in" | HOME="{home}" bash -c "$last"; exit $?;; esac\nexit 0\n'
    )
    (tmp_path / "bin" / "ssh").chmod(0o755)
    return home


def _finished_run(home: Path) -> Path:
    runs = home / "osprey-runs" / "case.meta" / "runs"
    for _ in range(200):
        done = [p for p in runs.iterdir() if p.name != "last" and (p / "exit").exists()] if runs.exists() else []
        if done:
            return done[0]
        time.sleep(0.05)
    raise AssertionError("the run never finished")


def _pid_from(path: Path) -> int:
    for _ in range(100):
        if path.exists() and path.read_text().strip():
            return int(path.read_text())
        time.sleep(0.05)
    raise AssertionError(f"{path} never written")


@_REAPS
def test_a_run_reaps_a_server_that_left_its_process_group(lease, tmp_path: Path) -> None:
    lease("acquire", "studio", "a run")
    lease("acquire", "case", "a run")
    home = _host(tmp_path)
    pidfile = tmp_path / "server.pid"
    wt = _lane_worktree(tmp_path)
    ran = _remote(lease, tmp_path, wt / "OspreyFlow_Build", "case", "--",
                  "sh", "-c", f'python3 -c "$1" "{pidfile}"; exit 7', "sh", _DETACHED)  # fmt: skip
    server = _pid_from(pidfile)
    try:
        assert ran.returncode == 0, ran.stderr
        run = _finished_run(home)
        assert (run / "exit").read_text().strip() == "7", (run / "log").read_text()  # the command's own code
        assert _gone_within(server), f"the detached server {server} outlived its run"
        assert "Reaped 1 process" in (run / "log").read_text(), (run / "log").read_text()
    finally:
        _end(server)
        _end_tagged(home)


@_REAPS
def test_the_reaper_leaves_every_process_outside_the_run_alone(lease, tmp_path: Path) -> None:
    """Another run's server (another tag) and an untagged process are never ended."""
    lease("acquire", "studio", "a run")
    lease("acquire", "case", "a run")
    home = _host(tmp_path)
    other = subprocess.Popen(["sleep", "300"], env={**os.environ, "OSPREY_RUN_TAG": f"{home}/osprey-runs/x.meta/runs/1"})
    plain = subprocess.Popen(["sleep", "300"], env={k: v for k, v in os.environ.items() if k != "OSPREY_RUN_TAG"})
    try:
        wt = _lane_worktree(tmp_path)
        assert _remote(lease, tmp_path, wt / "OspreyFlow_Build", "case", "--", "true").returncode == 0
        _finished_run(home)
        time.sleep(1)
        assert other.poll() is None and plain.poll() is None
    finally:
        other.kill()
        plain.kill()


@_REAPS
def test_a_run_ended_by_a_signal_still_reaps_its_server(lease, tmp_path: Path) -> None:
    """The run stopped with TERM, as a lane stopping it would: its server is ended too. (INT is not claimed: a run
    starts with INT ignored, inherited from the start call's backgrounded list; CARRIES.)"""
    lease("acquire", "studio", "a run")
    lease("acquire", "case", "a run")
    home = _host(tmp_path)
    pidfile = tmp_path / "server.pid"
    wt = _lane_worktree(tmp_path)
    lease("status", docker="all-up")
    env = {**os.environ, "OSPREY_LEASE_DIR": str(tmp_path / "lease"),
           "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}"}
    # Not waited on: `remote` follows the run's log until it ends.
    caller = subprocess.Popen(
        ["bash", str(SCRIPT), "remote", "case", "--",
         "sh", "-c", f'python3 -c "$1" "{pidfile}"; sleep 300', "sh", _DETACHED],
        cwd=wt / "OspreyFlow_Build", env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )  # fmt: skip
    server = _pid_from(pidfile)
    try:
        runs = home / "osprey-runs" / "case.meta" / "runs"
        run = next(p for p in runs.iterdir() if p.name != "last")
        # The shell running cmd.sh: the child of the wrapper whose pid the run recorded.
        wrapper = _pid_from(run / "pid")
        children = Path(f"/proc/{wrapper}/task/{wrapper}/children").read_text().split()
        os.kill(int(children[0]), 15)
        assert _gone_within(server), f"the detached server {server} outlived its stopped run"
        assert (_finished_run(home) / "exit").read_text().strip() == "143"
    finally:
        _end(server)
        _end_tagged(home)
        subprocess.run(["pkill", "-f", f"{tmp_path}/server.pid"], check=False)
        caller.kill()
        caller.wait()


@_REAPS
def test_reap_ends_what_a_run_whose_wrapper_was_killed_left_behind(lease, tmp_path: Path) -> None:
    lease("acquire", "studio", "a run")
    lease("acquire", "case", "a run")
    home = _host(tmp_path)
    run = home / "osprey-runs" / "case.meta" / "runs" / "20261111T080000Z"
    run.mkdir(parents=True)
    (home / "osprey-runs" / "case.meta" / "runs" / "last").symlink_to(run)
    (run / "pid").write_text(f"{_dead_pid()}\n")  # the wrapper, killed: reap fails closed on anything else
    left = subprocess.Popen(["sleep", "300"], env={**os.environ, "OSPREY_RUN_TAG": str(run)})
    bystander = subprocess.Popen(["sleep", "300"], env={**os.environ, "OSPREY_RUN_TAG": f"{run}0"})
    try:
        reaped = lease("reap", "case", docker="all-up")
        assert reaped.returncode == 0, reaped.stderr
        assert _gone_within(left.pid) or left.poll() is not None
        assert bystander.poll() is None, "a process tagged for another run was ended"
        assert "Reaped 1 process" in reaped.stdout + reaped.stderr
    finally:
        left.kill()
        bystander.kill()


def _reaper_shell(*lines: str) -> list[str]:
    """bash running the script's own REAPER (read from the script, as `reap` and cmd.sh send it), then `lines`."""
    text = SCRIPT.read_text()
    start = text.index("REAPER='") + len("REAPER='")
    reaper = text[start : text.index("\n}'", start) + 2]
    return ["bash", "-c", "\n".join([reaper, *lines])]


def _held_lease_on_host(home: Path) -> None:
    """The lease's info as `remote` mirrors it to the host, which the start call copies into the run."""
    info = home / "osprey-runs" / "case.meta" / "lease" / "stack-b.lease"
    info.mkdir(parents=True, exist_ok=True)
    (info / "info").write_text("holder=case\n")


def _recorded_run(home: Path, pid: int | None = None) -> Path:
    run = home / "osprey-runs" / "case.meta" / "runs" / "20261111T080000Z-0a1b2c3d"
    run.mkdir(parents=True)
    (home / "osprey-runs" / "case.meta" / "runs" / "last").symlink_to(run)
    if pid is not None:
        (run / "pid").write_text(f"{pid}\n")
    return run


def _dead_pid() -> int:
    """A pid that was a process and has ended (and been waited on)."""
    gone = subprocess.Popen(["true"])
    gone.wait()
    return gone.pid


@_REAPS
def test_reap_refuses_while_a_process_of_the_runs_session_lives_on(lease, tmp_path: Path) -> None:
    """Fails closed (T1 part 5's review, should-fix 6): the wrapper killed, its cmd.sh and command go on in its
    session. That run is still running, and reap refuses it, in words; nothing is ended."""
    lease("acquire", "studio", "a run")
    lease("acquire", "case", "a run")
    home = _host(tmp_path)
    run = _recorded_run(home)
    leader = subprocess.Popen(
        ["sh", "-c", "sleep 300 & echo $! > \"$1\"; wait", "sh", str(tmp_path / "member.pid")],
        start_new_session=True, env={**os.environ, "OSPREY_RUN_TAG": str(run)},
    )  # fmt: skip
    member = _pid_from(tmp_path / "member.pid")
    (run / "pid").write_text(f"{leader.pid}\n")
    os.kill(leader.pid, 9)
    leader.wait()
    try:
        reaped = lease("reap", "case", docker="all-up")
        assert reaped.returncode == 3, reaped.stdout + reaped.stderr
        assert "still running" in reaped.stderr and "stop" in reaped.stderr
        assert _alive(member), "a process of the running run was ended"
    finally:
        _end(member)


@_REAPS
def test_reap_says_when_no_tagged_process_was_found(lease, tmp_path: Path) -> None:
    """An ended run with nothing left behind: reap says no tagged process was found, never "reaped"."""
    lease("acquire", "studio", "a run")
    lease("acquire", "case", "a run")
    home = _host(tmp_path)
    run = _recorded_run(home, _dead_pid())
    (run / "exit").write_text("0\n")
    reaped = lease("reap", "case", docker="all-up")
    assert reaped.returncode == 0, reaped.stderr
    assert "No process tagged for the run" in reaped.stdout and "Reaped" not in reaped.stdout


@_REAPS
def test_the_reaper_never_matches_a_tag_inside_another_value(tmp_path: Path) -> None:
    """The environment is read NUL-separated: a value holding a newline and then the tag is not the tag (should-fix
    3), so that process is never ended."""
    tag = str(tmp_path / "run")
    lookalike = subprocess.Popen(["sleep", "300"], env={**os.environ, "NOTE": f"x\nOSPREY_RUN_TAG={tag}"})
    try:
        subprocess.run(_reaper_shell(f'osprey_reap "{tag}"'), capture_output=True, text=True, timeout=30)
        time.sleep(0.3)
        assert lookalike.poll() is None, "a process whose other value merely held the tag was ended"
    finally:
        lookalike.kill()


@_REAPS
def test_a_runs_log_holds_no_error_of_the_reapers_own_reading(lease, tmp_path: Path) -> None:
    """The reaper reads every process's environment; none of its reads may print an error into the run's log (a
    redirection that failed printed "Permission denied" or "No such file" before; should-fix 3). As root on the
    server every environment is readable, so this guards the shape rather than proving the old one red there."""
    lease("acquire", "studio", "a run")
    lease("acquire", "case", "a run")
    home = _host(tmp_path)
    wt = _lane_worktree(tmp_path)
    assert _remote(lease, tmp_path, wt / "OspreyFlow_Build", "case", "--", "true").returncode == 0
    log = (_finished_run(home) / "log").read_text()
    assert "Permission denied" not in log and "No such file" not in log, log


def test_two_runs_named_alike_are_refused_in_words_not_shared(lease, tmp_path: Path) -> None:
    """Should-fix 4: with the clock and the random suffix pinned (date and od stood in for on PATH), two runs get one
    name; the second's folder cannot be made new, so it is refused in words and nothing of it starts."""
    lease("acquire", "studio", "a run")
    lease("acquire", "case", "a run")
    home = _executing_host(tmp_path)
    _held_lease_on_host(home)
    wt = _lane_worktree(tmp_path)
    real_date = shutil.which("date")
    (tmp_path / "bin" / "date").write_text(
        f'#!/bin/sh\ncase "$*" in *%Y%m%dT%H%M%SZ*) echo 20261112T090000Z;; *) exec "{real_date}" "$@";; esac\n'
    )
    (tmp_path / "bin" / "od").write_text("#!/bin/sh\necho ' 0a1b2c3d'\n")
    for tool in ("date", "od"):
        (tmp_path / "bin" / tool).chmod(0o755)
    first = _remote(lease, tmp_path, wt / "OspreyFlow_Build", "case", "--", "true")
    assert first.returncode == 0, first.stderr
    runs = home / "osprey-runs" / "case.meta" / "runs"
    for _ in range(100):
        if (runs / "20261112T090000Z-0a1b2c3d" / "exit").exists():
            break
        time.sleep(0.05)
    second = _remote(lease, tmp_path, wt / "OspreyFlow_Build", "case", "--", "echo", "second")
    assert second.returncode != 0, second.stderr
    assert "could not be made new" in second.stderr and "nothing was started" in second.stderr, second.stderr
    assert "second" not in (runs / "20261112T090000Z-0a1b2c3d" / "log").read_text()


@_REAPS
def test_stop_ends_a_run_its_command_and_its_server_and_the_next_run_is_allowed(lease, tmp_path: Path) -> None:
    """`stop <lane>` (the orchestrator's ruling, should-fix 5), end to end through the verb: TERM to the run's process
    group, then KILL to what is left; cmd.sh, its command and the detached server are gone, the run's exit is
    written, the follow ends, and the lane's next run is allowed."""
    lease("acquire", "studio", "a run")
    lease("acquire", "case", "a run")
    home = _host(tmp_path)
    pidfile = tmp_path / "server.pid"
    wt = _lane_worktree(tmp_path)
    lease("status", docker="all-up")
    env = {**os.environ, "OSPREY_LEASE_DIR": str(tmp_path / "lease"),
           "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}"}
    follower = subprocess.Popen(
        ["bash", str(SCRIPT), "remote", "case", "--",
         "sh", "-c", f'python3 -c "$1" "{pidfile}"; sleep 300', "sh", _DETACHED],
        cwd=wt / "OspreyFlow_Build", env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )  # fmt: skip
    server = _pid_from(pidfile)
    try:
        runs = home / "osprey-runs" / "case.meta" / "runs"
        run = next(p for p in runs.iterdir() if p.name != "last")
        wrapper = _pid_from(run / "pid")
        stopped = lease("stop", "case", docker="all-up")
        assert stopped.returncode == 0, stopped.stderr
        assert "Stopped the run" in stopped.stdout, stopped.stdout
        assert _gone_within(wrapper) and _gone_within(server), "the run or its server outlived stop"
        assert (run / "exit").read_text().strip() == "143", "TERM to the run's group was not enough (a KILL was needed)"
        follower.wait(timeout=20)  # the follow ends
        again = _remote(lease, tmp_path, wt / "OspreyFlow_Build", "case", "--", "true")
        assert again.returncode == 0, again.stderr
    finally:
        _end(server)
        _end_tagged(home)
        follower.kill()
        follower.wait()


@_REAPS
def test_reap_refuses_a_run_that_is_still_running(lease, tmp_path: Path) -> None:
    """T1 part 5's review, must-fix 4: `reap` while the run's pid still answers (kill -0, as a run's start checks)
    would end a running run. It is refused, in words, and nothing is ended."""
    lease("acquire", "studio", "a run")
    lease("acquire", "case", "a run")
    home = _host(tmp_path)
    wrapper = subprocess.Popen(["sleep", "300"])
    run = _recorded_run(home, wrapper.pid)
    tagged = subprocess.Popen(["sleep", "300"], env={**os.environ, "OSPREY_RUN_TAG": str(run)})
    try:
        reaped = lease("reap", "case", docker="all-up")
        assert reaped.returncode == 3, reaped.stdout + reaped.stderr
        assert "still running" in reaped.stderr
        time.sleep(0.5)
        assert tagged.poll() is None, "a running run's process was reaped"
    finally:
        tagged.kill()
        wrapper.kill()


@_REAPS
def test_the_reaper_refuses_an_empty_tag(tmp_path: Path) -> None:
    """An empty tag is refused, never read as every process tagged with nothing (must-fix 4)."""
    untagged = subprocess.Popen(["sleep", "300"], env={**os.environ, "OSPREY_RUN_TAG": ""})
    caller_tag = str(tmp_path / "callers-run")
    callers = subprocess.Popen(["sleep", "300"], env={**os.environ, "OSPREY_RUN_TAG": caller_tag})
    try:
        for call in ('osprey_reap ""', "osprey_reap"):
            # The caller's own OSPREY_RUN_TAG is set: the reaper must not fall back to it.
            ran = subprocess.run(
                _reaper_shell(f'export OSPREY_RUN_TAG="{caller_tag}"; {call}'), capture_output=True, text=True
            )
            assert ran.returncode == 2, ran.stderr
            assert "No run tag" in ran.stderr
        time.sleep(0.5)
        assert untagged.poll() is None, "a process with an empty tag was reaped"
        assert callers.poll() is None, "the caller's own run was reaped by an empty argument"
    finally:
        untagged.kill()
        callers.kill()


_IGNORES_TERM = "import signal, time\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\ntime.sleep(300)\n"
# On TERM, the process becomes another program whose environment holds no tag (execve), as a recycled pid would hold
# another process: the KILL pass must read the environment again and leave it alone (must-fix 5).
_BECOMES_ANOTHER = (
    "import os, signal, sys, time\n"
    "def other(*_):\n"
    "    env = {k: v for k, v in os.environ.items() if k != 'OSPREY_RUN_TAG'}\n"
    "    os.execve(sys.executable, [sys.executable, '-c', 'import signal, time; "
    "signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(300)'], env)\n"
    "signal.signal(signal.SIGTERM, other)\n"
    "time.sleep(300)\n"
)


@_REAPS
def test_the_reaper_kills_what_survives_term(tmp_path: Path) -> None:
    """A tagged process that ignores TERM is ended by the KILL pass two seconds later (red without it)."""
    tag = str(tmp_path / "run")
    stubborn = subprocess.Popen(["python3", "-c", _IGNORES_TERM], env={**os.environ, "OSPREY_RUN_TAG": tag})
    try:
        time.sleep(0.5)
        subprocess.run(_reaper_shell(f'osprey_reap "{tag}"'), capture_output=True, text=True, timeout=30)
        assert _gone_within(stubborn.pid, 4) or stubborn.poll() is not None, "a process that ignored TERM outlived the reaper"
    finally:
        stubborn.kill()


@_REAPS
def test_the_kill_pass_reads_each_pid_again_and_spares_one_now_another_process(tmp_path: Path) -> None:
    """The KILL pass reads each pid's environment again: a pid whose process became another one after TERM (no
    longer tagged, as a recycled pid would be) is not sent -9 (must-fix 5)."""
    tag = str(tmp_path / "run")
    changed = subprocess.Popen(["python3", "-c", _BECOMES_ANOTHER], env={**os.environ, "OSPREY_RUN_TAG": tag})
    try:
        time.sleep(0.5)
        subprocess.run(_reaper_shell(f'osprey_reap "{tag}"'), capture_output=True, text=True, timeout=30)
        time.sleep(0.5)
        assert changed.poll() is None, "the KILL pass ended a pid no longer carrying the run's tag"
    finally:
        changed.kill()


def test_two_runs_of_one_lane_in_one_second_never_share_a_folder(lease, tmp_path: Path) -> None:
    """Must-fix 6: two runs started within the same second get two folders (so two tags), each made new; the
    stand-in host runs both start calls."""
    lease("acquire", "studio", "a run")
    lease("acquire", "case", "a run")
    home = _executing_host(tmp_path)
    _held_lease_on_host(home)
    wt = _lane_worktree(tmp_path)
    for _ in range(2):
        ran = _remote(lease, tmp_path, wt / "OspreyFlow_Build", "case", "--", "true")
        assert ran.returncode == 0, ran.stderr
        runs = home / "osprey-runs" / "case.meta" / "runs"
        done = [p for p in runs.iterdir() if p.name != "last"]
        for _ in range(100):
            if all((p / "exit").exists() for p in done):
                break
            time.sleep(0.05)
    folders = sorted(p.name for p in runs.iterdir() if p.name != "last")
    assert len(folders) == 2 and folders[0] != folders[1], folders
    assert all("-" in name.split("Z", 1)[1] for name in folders), folders


def test_the_start_call_returns_while_the_run_goes_on(lease, tmp_path: Path) -> None:
    """The ssh start call backgrounds the run with its own output closed, so ssh returns at once and `remote` goes on
    to follow the log (T1 part 5's review: the backgrounded list held ssh's output open until the run ended)."""
    lease("acquire", "studio", "a run")
    lease("acquire", "case", "a run")
    _held_lease_on_host(_executing_host(tmp_path))
    wt = _lane_worktree(tmp_path)
    lease("status", docker="all-up")
    env = {**os.environ, "OSPREY_LEASE_DIR": str(tmp_path / "lease"),
           "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}"}
    # The run's command carries a sentinel of this case's own (its tmp path) in its arguments, so it alone is ended
    # after; a bystander whose command line holds "sleep 6" (a sleep 60) must outlive the case (T1 part 5's review,
    # must-fix 1: `pkill -f "sleep 6"` ended any such process of the same user, on a shared server).
    sentinel = str(tmp_path / "start-call-sentinel")
    bystander = subprocess.Popen(["sleep", "60"])
    caller = subprocess.Popen(
        ["bash", str(SCRIPT), "remote", "case", "--", "python3", "-c", "import time; time.sleep(6)", sentinel],
        cwd=wt / "OspreyFlow_Build", env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
    )  # fmt: skip
    try:
        started = time.monotonic()
        line = caller.stderr.readline() if caller.stderr else ""
        assert "Running on" in line, line
        assert time.monotonic() - started < 3, "the start call held ssh until the run ended"
    finally:
        caller.kill()
        caller.wait()
        subprocess.run(["pkill", "-f", sentinel], check=False)
    try:
        time.sleep(0.3)
        assert bystander.poll() is None, "the case ended a bystander whose command line held 'sleep 6'"
    finally:
        bystander.kill()


# --- live: the lane's live tests selected by its change (admin's T1 part 3, 10 November 2026) ----------------


def _live(lease, tmp_path: Path, cwd: Path, picks: str, *args: str, fails: bool = False) -> subprocess.CompletedProcess[str]:
    """`stack_lease.sh live` with the selector stood in for by a script printing `picks` (one path a line), or
    failing as the real one does (a message on stderr, exit 1)."""
    lease("status", docker="all-up")
    selector = tmp_path / "select.sh"
    if fails:
        selector.write_text("#!/bin/sh\necho 'live_map.tsv line 3: names no live test file' >&2\nexit 1\n")
    else:
        selector.write_text(f"#!/bin/sh\necho \"selector $*\" >> \"{tmp_path}/selector.log\"\nprintf '%s' '{picks}'\n")
    selector.chmod(0o755)
    env = {**os.environ, "OSPREY_LEASE_DIR": str(tmp_path / "lease"), "OSPREY_LIVE_SELECT": str(selector),
           "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}"}
    return subprocess.run(["bash", str(SCRIPT), "live", *args], cwd=cwd, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL)


def _executing_host(tmp_path: Path) -> Path:
    """The recording ssh, running the start call as the host would (HOME a folder here), with a stand-in pytest in
    the copy's venv that writes the arguments it was given, one a line."""
    log = _remote_tools(tmp_path)
    home = tmp_path / "home"
    (home / "osprey-runs" / "case" / "OspreyFlow_Build").mkdir(parents=True)
    venv = home / "osprey-runs" / "case" / "OspreyFlow_Core" / ".venv" / "bin"
    venv.mkdir(parents=True)
    (venv / "pytest").write_text(f'#!/bin/sh\npwd > "{tmp_path}/pytest.cwd"\nprintf "%s\\n" "$@" > "{tmp_path}/pytest.argv"\n')
    (venv / "pytest").chmod(0o755)
    bin_dir = tmp_path / "bin"
    (bin_dir / "ssh").write_text(
        f'#!/bin/bash\necho "ssh $*" >> "{log}"\nin="$(cat)"\nprintf "%s\\n" "$in" | sed "s/^/stdin /" >> "{log}"\n'
        f'for a; do last="$a"; done\n'
        # As a real ssh, the call returns only once every holder of its output has closed it (rule 15: a backgrounded
        # list that keeps them open holds ssh), and returns the remote command's own exit code.
        f'case "$last" in *"nohup setsid"*) cd "{home}" && {{ printf "%s\\n" "$in" | HOME="{home}" bash -c "$last"; }} 2>&1 | cat; exit ${{PIPESTATUS[0]}};; esac\nexit 0\n'
    )
    (bin_dir / "setsid").write_text('#!/bin/sh\nexec "$@"\n')
    for tool in ("ssh", "setsid"):
        (bin_dir / tool).chmod(0o755)
    _held_lease_on_host(home)  # as remote mirrors the lease before the start call
    return home


def _wait_for(path: Path) -> None:
    for _ in range(100):
        if path.exists():
            return
        time.sleep(0.05)


def test_live_runs_exactly_the_selection_from_the_core_folder_with_extra_arguments(lease, tmp_path: Path) -> None:
    """At the real call site: the start call run as the host runs it, so the quoting is the shell's own (a lost
    `$0` placeholder would swallow the first file, and a lost "$@" the extra arguments)."""
    lease("acquire", "studio", "a run")
    lease("acquire", "case", "a run")  # stack b, on the server
    _executing_host(tmp_path)
    wt = _lane_worktree(tmp_path)
    picks = "tests/services/api/test_route_rights.py\ntests/conformance/graph_port/test_suite.py\n"
    ran = _live(lease, tmp_path, wt / "OspreyFlow_Core", picks, "case", "--", "-k", "not slow")
    assert ran.returncode == 0, ran.stderr
    _wait_for(tmp_path / "pytest.argv")
    argv = (tmp_path / "pytest.argv").read_text().splitlines()
    assert argv == [
        "-c", "../OspreyFlow_Build/pytest.ini", "-q", "-rfE",
        "../OspreyFlow_Build/tests/services/api/test_route_rights.py",
        "../OspreyFlow_Build/tests/conformance/graph_port/test_suite.py",
        "-k", "not slow",
    ], argv  # fmt: skip
    assert (tmp_path / "pytest.cwd").read_text().strip().endswith("osprey-runs/case/OspreyFlow_Core")
    assert "2 live test files" in ran.stderr, ran.stderr


def test_live_all_and_base_are_passed_to_the_selector(lease, tmp_path: Path) -> None:
    lease("acquire", "studio", "a run")
    lease("acquire", "case", "a run")
    _remote_tools(tmp_path)
    wt = _lane_worktree(tmp_path)
    assert _live(lease, tmp_path, wt, "tests/services/api/test_route_rights.py\n", "case", "--all").returncode == 0
    assert _live(lease, tmp_path, wt, "tests/services/api/test_route_rights.py\n", "case", "--base", "lane/x").returncode == 0
    said = (tmp_path / "selector.log").read_text().splitlines()
    assert said == ["selector --all --why", "selector --base lane/x --why"], said


def test_live_refuses_a_failed_or_empty_selection_and_a_lane_holding_no_stack(lease, tmp_path: Path) -> None:
    log = _remote_tools(tmp_path)
    wt = _lane_worktree(tmp_path)
    none = _live(lease, tmp_path, wt, "tests/services/api/test_route_rights.py\n", "case")
    assert none.returncode == 1 and "holds no stack" in none.stderr
    lease("acquire", "studio", "a run")
    lease("acquire", "case", "a run")
    empty = _live(lease, tmp_path, wt, "", "case")
    assert empty.returncode == 1 and "empty" in empty.stderr, empty.stderr
    failed = _live(lease, tmp_path, wt, "", "case", fails=True)
    assert failed.returncode == 1 and "names no live test file" in failed.stderr
    assert "The selection failed" in failed.stderr, failed.stderr  # not the empty-selection refusal
    assert not log.exists() or "rsync" not in log.read_text()  # nothing sent


# --- live and remote check the stack is up first (T1 part 5; CARRIES: studio's L1.7, 10 November 2026) --------
# A whole live selection ran against a leased stack that was not up: about 2,000 connection refusals, and a run
# that measured nothing. Every one of the stack's containers must be running (one up is not the stack up), or the
# run is refused before anything is copied, naming each container that is down.


def _with_docker(lease, script: str) -> None:
    _DOCKER["case-docker"] = script
    try:
        lease("status", docker="case-docker")  # writes this docker onto PATH for the run that follows
    finally:
        del _DOCKER["case-docker"]


def _remote_after(lease, tmp_path: Path, cwd: Path, script: str, *args: str) -> subprocess.CompletedProcess[str]:
    _with_docker(lease, script)
    env = {**os.environ, "OSPREY_LEASE_DIR": str(tmp_path / "lease"),
           "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}"}
    return subprocess.run(["bash", str(SCRIPT), *args], cwd=cwd, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL)


@pytest.mark.parametrize(
    ("down", "verb"),
    [
        (("osprey-test-b-pg",), "remote"),
        (_STACK_B, "remote"),
        (("osprey-test-b-clickhouse",), "live"),
        (_STACK_B, "live"),
    ],
    ids=["remote-one-down", "remote-all-down", "live-one-down", "live-all-down"],
)
def test_a_run_on_a_stack_not_wholly_up_is_refused_before_anything_is_sent(
    lease, tmp_path: Path, down: tuple[str, ...], monkeypatch: pytest.MonkeyPatch, verb: str
) -> None:
    lease("acquire", "studio", "a run")
    lease("acquire", "case", "a run")  # stack b, on the server
    log = _remote_tools(tmp_path)
    wt = _lane_worktree(tmp_path)
    selector = tmp_path / "select.sh"
    selector.write_text(f'#!/bin/sh\ntouch "{tmp_path}/selected"\necho tests/services/api/test_route_rights.py\n')
    selector.chmod(0o755)
    monkeypatch.setenv("OSPREY_LIVE_SELECT", str(selector))
    if True:
        args = ("remote", "case", "--", "true") if verb == "remote" else ("live", "case")
        ran = _remote_after(lease, tmp_path, wt, _names_docker(down), *args)
    assert ran.returncode == 1, ran.stdout + ran.stderr
    assert "not up" in ran.stderr and all(c in ran.stderr for c in down), ran.stderr
    assert "stack_lease.sh up case" in ran.stderr, ran.stderr
    assert not log.exists() or "rsync" not in log.read_text()  # nothing copied, nothing started
    assert not (tmp_path / "selected").exists()  # refused before the selection is even made


def test_a_run_is_refused_when_docker_cannot_say_whether_the_stack_is_up(lease, tmp_path: Path) -> None:
    lease("acquire", "studio", "a run")
    lease("acquire", "case", "a run")
    log = _remote_tools(tmp_path)
    wt = _lane_worktree(tmp_path)
    ran = _remote_after(lease, tmp_path, wt, _DOCKER["broken"], "remote", "case", "--", "true")
    assert ran.returncode == 1 and "could not say" in ran.stderr, ran.stderr
    assert not log.exists() or "rsync" not in log.read_text()


def test_a_run_on_a_wholly_up_stack_asks_only_its_own_containers_on_its_own_host(lease, tmp_path: Path) -> None:
    """The check asks the stack's host (DOCKER_HOST) about exactly its own containers, and the run goes ahead."""
    lease("acquire", "studio", "a run")
    lease("acquire", "case", "a run")
    log = _remote_tools(tmp_path)
    wt = _lane_worktree(tmp_path)
    asked = tmp_path / "asked.log"
    script = _names_docker().replace("#!/bin/sh\n", f'#!/bin/sh\necho "${{DOCKER_HOST:-local}} $*" >> "{asked}"\n', 1)
    ran = _remote_after(lease, tmp_path, wt, script, "remote", "case", "--", "true")
    assert ran.returncode == 0, ran.stderr
    assert "rsync" in log.read_text()
    line = next(l for l in asked.read_text().splitlines() if " ps " in f" {l} ")
    assert line.startswith("ssh://"), line
    assert all(f"name=^/?{c}$" in line for c in _STACK_B) and "osprey-test-pg" not in line.replace("osprey-test-b-pg", "")


# --- The test stacks' Postgres allows 400 connections (T1 part 4, 10 November 2026) ----------------------------
# One Conduit opens 46 asyncpg pools whose minimums add up to 47 connections; Postgres's default
# `max_connections` of 100 refused rule 3's live access set at four pytest-xdist workers on stack b
# (`TooManyConnectionsError`, process/lanes/admin/T1_P4_RED_RECORD.md). `up` makes each test stack's Postgres
# allow 400. The fake models what the real one refuses: `ALTER SYSTEM` alone changes nothing that `SHOW` reads
# until the server restarts, and `psql` fails while the server is still starting.


def _postgres_docker(tmp_path: Path, live: int, *, starting: int = 0, ignores_alter: bool = False) -> tuple[str, Path]:
    st = tmp_path / "pg"
    st.mkdir()
    (st / "live").write_text(f"{live}\n")
    (st / "starting").write_text(f"{starting}\n")
    keep = "" if ignores_alter else 'echo "$*" | sed -n "s/.*max_connections = \\([0-9]*\\).*/\\1/p" > "$st/pending"; '
    script = f"""#!/bin/sh
st="{st}"
echo "$*" >> "$st/log"
case "$1" in
  exec)
    n=$(cat "$st/starting")
    if [ "$n" -gt 0 ]; then echo $((n - 1)) > "$st/starting"; echo 'psql: error: the database system is starting up' >&2; exit 2; fi
    case "$*" in
      *"SHOW max_connections"*) cat "$st/live" ;;
      *"ALTER SYSTEM SET max_connections"*) {keep}echo 'ALTER SYSTEM' ;;
    esac ;;
  restart) [ -f "$st/pending" ] && mv "$st/pending" "$st/live"; echo 2 > "$st/starting" ;;
esac
exit 0
"""
    return script, st


def _up_with(lease, tmp_path: Path, script: str, **env: str) -> subprocess.CompletedProcess[str]:
    lease("acquire", "case", "conformance")
    _DOCKER["postgres"] = script
    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        return lease("up", "case", docker="postgres")
    finally:
        del _DOCKER["postgres"]
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_up_raises_a_test_stack_s_postgres_to_400_connections_and_restarts_it_once(lease, tmp_path: Path) -> None:
    script, st = _postgres_docker(tmp_path, live=100, starting=1)
    up = _up_with(lease, tmp_path, script, OSPREY_PG_READY_PAUSE="0")
    assert up.returncode == 0, up.stderr
    assert (st / "live").read_text().strip() == "400"
    calls = (st / "log").read_text().splitlines()
    assert [c for c in calls if c.startswith("restart")] == ["restart osprey-test-pg"], calls
    assert any("ALTER SYSTEM SET max_connections = 400" in c and "osprey-test-pg" in c for c in calls), calls
    assert "max_connections 400" in up.stdout, up.stdout


def test_up_leaves_a_postgres_already_at_400_alone(lease, tmp_path: Path) -> None:
    script, st = _postgres_docker(tmp_path, live=400)
    up = _up_with(lease, tmp_path, script, OSPREY_PG_READY_PAUSE="0")
    assert up.returncode == 0, up.stderr
    calls = (st / "log").read_text().splitlines()
    assert not any(c.startswith("restart") or "ALTER SYSTEM" in c for c in calls), calls


def test_up_fails_when_the_restarted_postgres_still_allows_fewer(lease, tmp_path: Path) -> None:
    script, _ = _postgres_docker(tmp_path, live=100, ignores_alter=True)
    up = _up_with(lease, tmp_path, script, OSPREY_PG_READY_PAUSE="0")
    assert up.returncode == 1
    assert "max_connections" in up.stderr and "100" in up.stderr, up.stderr


def test_up_fails_when_postgres_never_answers(lease, tmp_path: Path) -> None:
    script, _ = _postgres_docker(tmp_path, live=100, starting=99)
    up = _up_with(lease, tmp_path, script, OSPREY_PG_READY_PAUSE="0", OSPREY_PG_READY_TRIES="3")
    assert up.returncode == 1
    assert "osprey-test-pg" in up.stderr and "did not answer" in up.stderr, up.stderr
