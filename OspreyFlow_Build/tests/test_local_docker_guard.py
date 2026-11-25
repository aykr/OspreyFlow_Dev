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
import tempfile
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


# --- The one exempt command (the owner's ruling D234, 24 November 2026) -------------------------
#
# The Caddy test of PL7f (`tests/harness/test_page_addresses_caddy.py`) runs the proxy's own image
# once to validate every Caddyfile. Under the switch the guard refused that call too, so the real
# Caddy ran on no merge here. The owner exempted exactly that one command, matched on its whole
# shape as `subprocess.run` hands it to `Popen`, and nothing else: another image, a fourth mount, a
# mount that is not read-only, another network, no `--rm`, another test asking, another docker
# command in the same test, each stays refused. (Rule 15: the refusals are shown red with the
# exemption matched on the image alone, which is how they were first run.)

CADDY_TEST = "tests/harness/test_page_addresses_caddy.py"
ASKING = f"{CADDY_TEST}::test_the_real_caddy_loads_every_derived_case[x] (setup)"


def caddy_command(tmp: Path | str = "") -> list[str]:
    """The command as the Caddy test's `subprocess.run` hands it over (the same words)."""
    base = Path(tmp) if tmp else Path(tempfile.gettempdir()) / "pytest-of-someone" / "caddy0"
    return [
        "docker", "run", "--rm", "--network", "none",
        "-v", f"{base}/cases:/cases:ro",
        "-v", f"{base}/etc:/etc/caddy:ro",
        "-v", f"{base}/certs:/certs:ro",
        local_docker_guard.CADDY_IMAGE, "sh", "-c", local_docker_guard.CADDY_SCRIPT,
    ]  # fmt: skip


def _with(command: list[str], old: str, *new: str) -> list[str]:
    """`command` with the word `old` replaced by `new` (none: removed)."""
    at = command.index(old)
    return [*command[:at], *new, *command[at + 1 :]]


def _mount(command: list[str], which: str, value: str) -> list[str]:
    """`command` with the mount named `which` (cases, etc or certs) replaced by `value`."""
    target = {"cases": "/cases", "etc": "/etc/caddy", "certs": "/certs"}[which]
    at = next(i for i, word in enumerate(command) if word.endswith(f":{target}:ro"))
    return [*command[:at], value, *command[at + 1 :]]


def test_the_one_command_is_exempt_for_the_one_test() -> None:
    assert local_docker_guard.is_the_caddy_validation(caddy_command(), {}, ASKING)
    assert local_docker_guard.is_the_caddy_validation(
        caddy_command(), {"capture_output": True}, f"{CADDY_TEST}::test_x (call)"
    )


def _refused() -> list[tuple[str, list[str], dict[str, object], str]]:
    good = caddy_command()
    tmp = tempfile.gettempdir()
    image = local_docker_guard.CADDY_IMAGE
    sock = "/var/run/docker.sock"
    return [
        # A real fourth mount sits among the `-v` flags, before the image (`good[-4:]` is the
        # image, `sh`, `-c` and the script); after the image Docker would read it as the command.
        ("a fourth mount", [*good[:-4], "-v", f"{tmp}/x:/data:ro", *good[-4:]], {}, ASKING),
        (
            "a fourth mount, the docker socket",
            [*good[:-4], "-v", f"{sock}:/s:ro", *good[-4:]],
            {},
            ASKING,
        ),
        ("a mount that is writable", _mount(good, "cases", f"{tmp}/c/cases:/cases:rw"), {}, ASKING),
        ("a mount with no mode", _mount(good, "certs", f"{tmp}/c/certs:/certs"), {}, ASKING),
        (
            "the docker socket as a mount's source",
            _mount(good, "cases", f"{sock}:/cases:ro"),
            {},
            ASKING,
        ),
        (
            "a mount from the home folder",
            _mount(good, "etc", f"{Path.home()}:/etc/caddy:ro"),
            {},
            ASKING,
        ),
        (
            "a mount from a folder that climbs out",
            _mount(good, "etc", f"{tmp}/../etc:/etc/caddy:ro"),
            {},
            ASKING,
        ),
        (
            "a mount of a different target",
            _mount(good, "certs", f"{tmp}/c/certs:/other:ro"),
            {},
            ASKING,
        ),
        ("the network host", _with(good, "none", "host"), {}, ASKING),
        ("the network bridge", _with(good, "none", "bridge"), {}, ASKING),
        ("no network named", [*good[:3], *good[5:]], {}, ASKING),
        ("the network written as one word", [*good[:3], "--network=host", *good[5:]], {}, ASKING),
        ("no --rm", _with(good, "--rm"), {}, ASKING),
        (
            "another tag",
            _with(good, image, "caddy:2.11.3-alpine"),
            {},
            ASKING,
        ),
        ("the latest tag", _with(good, image, "caddy:latest"), {}, ASKING),
        ("another image", _with(good, image, "alpine"), {}, ASKING),
        ("a published port", _with(good, "--rm", "--rm", "-p", "80:80"), {}, ASKING),
        ("a privileged container", _with(good, "--rm", "--rm", "--privileged"), {}, ASKING),
        ("another script", [*good[:-1], "rm -rf /cases"], {}, ASKING),
        ("another program", [*good[:-3], "caddy", "validate", "--config", "/cases/x"], {}, ASKING),
        (
            "another docker command",
            ["docker", "image", "inspect", image],
            {},
            ASKING,
        ),
        (
            "the hash-password run",
            [
                "docker",
                "run",
                "--rm",
                "-i",
                image,
                "caddy",
                "hash-password",
            ],
            {},
            ASKING,
        ),
        ("docker by a full path", ["/usr/local/bin/docker", *good[1:]], {}, ASKING),
        ("a command string", " ".join(good), {}, ASKING),
        ("through a shell", ["sh", "-c", " ".join(good)], {}, ASKING),
        ("with a shell", good, {"shell": True}, ASKING),
        ("with an environment", good, {"env": {"DOCKER_HOST": "tcp://elsewhere:2375"}}, ASKING),
        ("with another executable", good, {"executable": "/bin/sh"}, ASKING),
        ("another test asking", good, {}, "tests/harness/test_other.py::test_x (call)"),
        ("a test of the same name elsewhere", good, {}, f"other/{CADDY_TEST}::test_x (call)"),
        ("a file that only starts with the name", good, {}, f"{CADDY_TEST}.bak::test_x (call)"),
        ("collection (no test running)", good, {}, ""),
        ("this test file asking", good, {}, "tests/test_local_docker_guard.py::test_x (call)"),
    ]


@pytest.mark.parametrize(
    ("name", "args", "kwargs", "asking"), _refused(), ids=[r[0] for r in _refused()]
)
def test_a_second_command_is_refused_while_the_exemption_is_in_place(
    name: str, args: object, kwargs: dict[str, object], asking: str
) -> None:
    assert not local_docker_guard.is_the_caddy_validation(args, kwargs, asking), name


def test_the_exempt_image_is_the_image_the_deployment_runs() -> None:
    """The guard names the image by its own constant; the test runs `PROXY_IMAGE`. If the proxy's
    tag moves and the exemption does not, the Caddy test's one command is refused: fail here, in
    words, first."""
    from harness.site import PROXY_IMAGE

    assert local_docker_guard.CADDY_IMAGE == PROXY_IMAGE, (
        "harness.site.PROXY_IMAGE changed: move tests/local_docker_guard.py's CADDY_IMAGE with it "
        "(the owner's exemption D234 names the pinned image)"
    )


def test_the_exemption_is_a_decision_with_a_comment_naming_the_issue_that_ends_it() -> None:
    text = (BUILD / "tests" / "local_docker_guard.py").read_text(encoding="utf-8")
    assert "017-1" in text, "the exemption must say it comes out when 017-1 lands"


CADDY_INNER = {
    CADDY_TEST: (
        "import subprocess, tempfile\n"
        "from pathlib import Path\n"
        "from tests.local_docker_guard import CADDY_IMAGE, CADDY_SCRIPT\n"
        "def cmd(extra=(), network='none', mode='ro'):\n"
        "    base = Path(tempfile.mkdtemp())\n"
        "    return ['docker', 'run', '--rm', '--network', network,\n"
        "            '-v', f'{base}/cases:/cases:ro', '-v', f'{base}/etc:/etc/caddy:ro',\n"
        "            '-v', f'{base}/certs:/certs:{mode}', *extra,\n"
        "            CADDY_IMAGE, 'sh', '-c', CADDY_SCRIPT]\n"
        "def test_the_exempt_command():\n"
        "    done = subprocess.run(cmd(), capture_output=True, text=True, check=False)\n"
        "    assert done.returncode == 0, done.stderr\n"
        "def test_a_fourth_mount():\n"
        "    command = cmd()\n"
        "    extra = ['-v', f'{tempfile.mkdtemp()}:/x:ro']\n"
        "    subprocess.run([*command[:-4], *extra, *command[-4:]], check=False)\n"
        "def test_another_network():\n"
        "    subprocess.run(cmd(network='host'), check=False)\n"
        "def test_a_writable_mount():\n"
        "    subprocess.run(cmd(mode='rw'), check=False)\n"
        "def test_another_command():\n"
        "    subprocess.run(['docker', 'image', 'inspect', CADDY_IMAGE], check=False)\n"
    ),
    "test_other.py": (
        "import subprocess, tempfile\n"
        "from pathlib import Path\n"
        "from tests.local_docker_guard import CADDY_IMAGE, CADDY_SCRIPT\n"
        "def test_the_same_command_from_another_test():\n"
        "    base = Path(tempfile.mkdtemp())\n"
        "    subprocess.run(['docker', 'run', '--rm', '--network', 'none',\n"
        "                    '-v', f'{base}/cases:/cases:ro', '-v', f'{base}/etc:/etc/caddy:ro',\n"
        "                    '-v', f'{base}/certs:/certs:ro',\n"
        "                    CADDY_IMAGE, 'sh', '-c', CADDY_SCRIPT],\n"
        "                   check=False)\n"
    ),
}


def test_the_one_command_reaches_the_real_docker_and_every_other_stays_refused(
    tmp_path: Path,
) -> None:
    """End to end, through `subprocess.run` and the session's own wrapper: the Caddy test's one
    command starts the docker found on the real path (the stand-in records it; the refusing shim
    on the session's `PATH` does not), and the others are skipped in words and start nothing."""
    lease = tmp_path / "lease"
    lease.mkdir()
    (lease / "no-local-stacks").touch()
    stand_in = tmp_path / "bin"
    stand_in.mkdir()
    ran = tmp_path / "docker-was-started"
    (stand_in / "docker").write_text(f'#!/bin/sh\necho "$@" >> {ran}\nexit 0\n', encoding="utf-8")
    (stand_in / "docker").chmod(0o755)
    suite = tmp_path / "suite"
    (suite / "tests" / "harness").mkdir(parents=True)
    (suite / "conftest.py").write_text(
        "from tests.conftest import pytest_configure, pytest_plugins  # noqa: F401\n",
        encoding="utf-8",
    )
    (suite / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    for name, body in CADDY_INNER.items():
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
        cwd=suite,
        timeout=120,
        check=False,
    )
    out = done.stdout + done.stderr
    assert "1 passed, 5 skipped" in out, out
    started = ran.read_text(encoding="utf-8").splitlines() if ran.exists() else []
    assert len(started) == 1 and started[0].startswith("run --rm --network none -v "), started
    assert "caddy:2.11.4-alpine sh -c" in started[0], started
