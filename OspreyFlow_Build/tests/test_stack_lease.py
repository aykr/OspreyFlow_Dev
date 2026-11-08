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


def test_a_second_acquire_while_one_is_held_is_refused_and_names_the_holder(lease) -> None:
    first = lease("acquire", "studio", "phase 6 route tests")
    assert first.returncode == 0, first.stderr
    second = lease("acquire", "glass", "axe scans")
    assert second.returncode == 1
    assert "holder=studio" in second.stderr
    assert "purpose=phase 6 route tests" in second.stderr
    assert "holder=studio" in lease("status").stdout


def test_release_by_a_lane_not_holding_it_is_refused(lease) -> None:
    lease("acquire", "studio", "phase 6 route tests")
    other = lease("release", "glass")
    assert other.returncode == 1
    assert "held by studio, not glass" in other.stderr
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
    assert lease("status").stdout.strip() == "free"
    assert lease("acquire", "glass", "axe scans").returncode == 0


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
    assert refused.returncode == 1 and "held by studio" in refused.stderr
    assert not log.exists()
