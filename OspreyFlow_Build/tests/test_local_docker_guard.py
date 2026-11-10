"""A test that calls the docker CLI skips at once, in words, where local stacks are off
(`tests/local_docker_guard.py`; CARRIES, 10 November 2026: Docker Desktop started on the owner's
Mac from a local run of `test_workspace_proxy.py`).

Each case runs an inner pytest session wired through this suite's own `conftest.py`, with the
switch in a lease dir of its own and a `PATH` whose only `docker` is a stand-in that records being
started. So the real docker CLI is never reachable from these tests, guarded or not, and "the
stand-in was started" is what an unguarded run looks like.
- At collection (`test_image_references.py`'s `docker info`), in a test, through `sh -c`, and in
  a child process: `test_a_docker_call_skips_in_words_and_starts_nothing`.
- Without the switch, nothing is changed: `test_without_the_switch_the_call_goes_through`.
- The shapes a docker call takes: `test_the_shapes_of_a_docker_call`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests import local_docker_guard
from tests.local_docker_guard import starts_docker

BUILD = Path(__file__).resolve().parents[1]

INNER = {
    "test_at_collection.py": (
        "import subprocess\n"
        "DAEMON = subprocess.run(['docker', 'info'], capture_output=True).returncode == 0\n"
        "def test_collected():\n"
        "    assert DAEMON\n"
    ),
    "test_in_a_test.py": (
        "import subprocess\n"
        "def test_builds():\n"
        "    subprocess.run(['docker', 'build', '-q', '.'], check=True)\n"
        "def test_through_a_shell():\n"
        "    subprocess.run(['sh', '-c', 'docker version'], check=True)\n"
    ),
    "test_in_a_child.py": (
        "import subprocess, sys\n"
        "def test_child():\n"
        "    done = subprocess.run(['make', '-v'], capture_output=True, text=True)\n"
        "    assert done.returncode == 0\n"
        "def test_a_python_child():\n"
        "    # The real shape: a child Python process (python -m harness.apply) shelling out.\n"
        '    code = \'import subprocess; print(subprocess.run(["docker", "info"]).returncode)\'\n'
        "    done = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)\n"
        "    assert done.stdout.strip() == '1' and 'refused: a server-only test' in done.stderr\n"
    ),
}


def _inner(tmp_path: Path, *, switch: bool) -> tuple[subprocess.CompletedProcess[str], Path]:
    lease = tmp_path / "lease"
    lease.mkdir()
    if switch:
        (lease / "no-local-stacks").touch()
    stand_in = tmp_path / "bin"
    stand_in.mkdir()
    ran = tmp_path / "docker-was-started"
    (stand_in / "docker").write_text(f'#!/bin/sh\necho "$@" >> {ran}\nexit 0\n', encoding="utf-8")
    (stand_in / "docker").chmod(0o755)
    suite = tmp_path / "suite"
    suite.mkdir()
    (suite / "conftest.py").write_text(
        "from tests.conftest import pytest_configure, pytest_plugins  # noqa: F401\n",
        encoding="utf-8",
    )
    for name, body in INNER.items():
        (suite / name).write_text(body, encoding="utf-8")
    env = {
        **os.environ,
        "OSPREY_LEASE_DIR": str(lease),
        "PATH": f"{stand_in}{os.pathsep}/usr/bin{os.pathsep}/bin",
        "PYTHONPATH": os.pathsep.join([str(BUILD), os.environ.get("PYTHONPATH", "")]),
    }
    done = subprocess.run(  # noqa: S603 - this interpreter, an inner pytest of our own
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-rs", "-q", str(suite)],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        timeout=120,
        check=False,
    )
    return done, ran


def test_a_docker_call_skips_in_words_and_starts_nothing(tmp_path: Path) -> None:
    done, ran = _inner(tmp_path, switch=True)
    out = done.stdout + done.stderr
    assert not ran.exists(), f"the docker stand-in was started: {ran.read_text()}\n{out}"
    assert "2 passed, 3 skipped" in out, out  # the child refused, and a call not docker's run
    said = [line for line in out.splitlines() if line.startswith("SKIPPED")]
    assert len(said) == 3 and all(
        "a server-only test: it calls the docker CLI" in x for x in said
    ), out
    assert "(docker build -q .)" in out and "(sh -c docker version)" in out, out  # the call, named
    assert "no-local-stacks" in out and "stack_lease.sh offline|live" in out, out


def test_without_the_switch_the_call_goes_through(tmp_path: Path) -> None:
    done, ran = _inner(tmp_path, switch=False)
    out = done.stdout + done.stderr
    assert ran.exists(), out
    assert "skipped" not in out, out
    # The stand-in answers 0 throughout; the Python child expects a refusal and so fails.
    assert "1 failed, 4 passed" in out, out


@pytest.mark.parametrize(
    ("args", "docker"),
    [
        (["docker", "build", "."], True),
        (["/usr/local/bin/docker", "info"], True),
        ("docker compose -p x down -v", True),
        (b"docker version", True),
        (["sh", "-c", "docker build -q ."], True),
        (["bash", "-c", "docker info"], True),
        ([Path("/usr/local/bin/docker"), "info"], True),
        (["env", "FOO=1", "docker", "info"], True),
        (["sudo", "-u", "ci", "docker", "ps"], True),
        (["timeout", "60", "docker", "build", "."], True),
        (["timeout", "-s", "KILL", "60", "env", "docker", "info"], True),
        (["bash", "-e", "-o", "pipefail", "-c", "set -e; docker info"], True),
        (["sh", "-lc", "cd x && docker build ."], True),
        ("DOCKER_BUILDKIT=1 docker build .", True),
        ("make x | docker load", True),
        (["env", "git", "status"], False),
        (["timeout", "5", "sleep", "1"], False),
        (["sh", "-c", "echo docker"], False),
        (["sudo", "-u", "docker", "id"], False),
        (["git", "status"], False),
        (["sh", "-c", "make test"], False),
        (["dockerd-rootless.sh"], False),
        ("", False),
        ([], False),
    ],
)
def test_the_shapes_of_a_docker_call(args: object, docker: bool) -> None:
    assert starts_docker(args) is docker


def test_the_switch_is_read_where_stack_lease_reads_it(tmp_path: Path) -> None:
    assert local_docker_guard.switch_path({"OSPREY_LEASE_DIR": str(tmp_path)}) == (
        tmp_path / "no-local-stacks"
    )
    assert local_docker_guard.switch_path({}) == Path.home() / ".ospreyflow" / "no-local-stacks"


def test_the_guard_puts_back_what_it_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "no-local-stacks").touch()
    monkeypatch.setenv("OSPREY_LEASE_DIR", str(tmp_path))
    monkeypatch.setattr(local_docker_guard, "_installed", {})  # this session's own guard left alone
    popen, path = subprocess.Popen, os.environ["PATH"]
    try:
        local_docker_guard.install()
        shim_dir = Path(os.environ["PATH"].split(os.pathsep)[0])
        assert (shim_dir / "docker").is_file() and subprocess.Popen is not popen
        local_docker_guard.uninstall()
        assert not shim_dir.exists()
        assert os.environ["PATH"] == path and subprocess.Popen is popen
    finally:
        local_docker_guard.uninstall()
        subprocess.Popen, os.environ["PATH"] = popen, path  # type: ignore[misc]
