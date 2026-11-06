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
