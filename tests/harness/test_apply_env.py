"""One value under two names — three times, each found by a different failure.

`harness/apply.py` mints each store's credential once and writes it into the deployment's
environment file under **two** names: the one the server container is configured from, and the one
the client library reads. They are different names for historical reasons that are not going away,
and every time only one side has been written the result has been the same shape of fault — a
runtime error naming neither variable:

- **ArcadeDB.** The compose file sets the server's root password from `OSPREY_ARCADEDB_PASSWORD`;
  the adapter reads `ARCADEDB_ROOT_PASSWORD`. Generated separately at first, and the Conduit died
  on a 403 "User/Password not valid".
- **Postgres.** The container is configured from `OSPREY_POSTGRES_*`; `services/api/config.py`
  reads `POSTGRES_*`. Setting only the host left the Conduit dialling `postgres:5433`.
- **MinIO.** The container is configured from `OSPREY_MINIO_*`; `services/ingest/staging.py` reads
  `MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY` and **falls back to `minioadmin`/`minioadmin`** when they
  are absent. So the seed did not fail loudly on a missing variable — it authenticated with the
  wrong credentials and MinIO answered `ACCESS_DENIED during HeadBucket operation`. Found running
  the seeded golden path.

**This is `CLAUDE.md` rule 12's question answered for "each credential is written under both
names".** Two of the three pairs were fixed one at a time as each was hit in a live deploy, and
nothing was ever added that would have found the third before it was hit too. This is that test.
The planted violation is the real shape: one side of a pair left unwritten, exactly as MinIO's was.
"""

from __future__ import annotations

import socket
import subprocess
import time
from pathlib import Path

import pytest
from harness.apply import main

#: The two host ports a `local-lite` render publishes (`harness.render.PORT_OVERRIDES`'s own
#: defaults for `workspace`/`keycloak`) — waited on after teardown, below, for the same reason the
#: teardown itself exists: `docker compose down` returns as soon as the containers are gone, but
#: this host's own release of the port binding it held for them measurably lags behind that by a
#: moment. Found running this file back to back, not assumed: the very next test's own preflight
#: port check failed, naming 8081 already in use, with no container and nothing in `lsof` a moment
#: later — a race between "the down command returned" and "the OS actually freed the port",
#: not a second deployment left running.
_PUBLISHED_PORTS = (8080, 8081)

#: The compose project name every `local-lite` render carries (`harness.render._render_compose`'s
#: own `name: f"osprey-{profile}"`) — fixed regardless of which `tmp_path` rendered it, which is
#: exactly why teardown here is keyed on the project name and not on any one test's own compose
#: file path: a docker-compose project name and its published host ports are host-wide state, not
#: `tmp_path`-scoped state, so a second test's `docker compose up` collides with whatever the first
#: one left running rather than starting anything clean.
LOCAL_LITE_PROJECT = "osprey-local-lite"


@pytest.fixture(autouse=True)
def _teardown_local_lite_deployment():
    """Every test below drives the real `harness.apply.main()` past `--no-build` into `up` —
    `_rendered_env`'s own docstring says so ("the next stage would reach for a Docker daemon"). A
    real `osprey-local-lite` deployment is started, and `main()` has no reason to tear it down on
    this caller's behalf: it does not know the caller only wanted the environment file written.

    **Found, not anticipated.** With no teardown, every test in this file left its own deployment
    running, and the *next* one to run collided with the leftover project name and published ports
    rather than exercising a clean stack of its own — `CLAUDE.md` rule 14's own worked example,
    reproduced by this file rather than by two agents. Runs after every test regardless of outcome
    (a fixture's own teardown fires on failure, not only on success) — rule 15's own question,
    answered here: "does a planted early failure still leave no `osprey-*` container running" is
    exactly what `test_the_deployment_this_file_starts_is_a_real_one_and_the_teardown_removes_it`
    below proves directly, and what was verified manually for the failure case (see that test's own
    docstring). Also waits for this host to actually release the two ports the render publishes —
    `docker compose down` returning is not the same event as the OS freeing the bind, and the next
    test's own preflight port check runs within moments of this one.
    """
    yield
    subprocess.run(
        ["docker", "compose", "-p", LOCAL_LITE_PROJECT, "down", "-v", "--remove-orphans"],
        capture_output=True,
        text=True,
        timeout=180,
    )
    _wait_for_ports_free(_PUBLISHED_PORTS)


def _wait_for_ports_free(ports: tuple[int, ...], *, timeout_seconds: float = 60.0) -> None:
    """Waits for `harness.preflight.ports._is_bindable`'s own check to succeed, not for
    something to stop *answering* on the port — the two are different conditions and the gap
    between them is the bug this function's first version had. A `connect()` to a port in
    `TIME_WAIT` correctly finds nothing listening and returns "free" immediately, while a fresh
    `bind()` to that same port — what Preflight's own check does, deliberately without
    `SO_REUSEADDR` (`ports.py`'s own docstring: "a port in `TIME_WAIT`... this check should still
    report") — keeps failing with `OSError(48, 'Address already in use')` for as long as
    `TIME_WAIT` lasts. Found running this file's own tests back to back: a `connect_ex`-based
    version of this function returned immediately every time, and every test after the first hit
    the exact Preflight failure this function exists to wait out.
    """
    deadline = time.monotonic() + timeout_seconds
    for port in ports:
        while time.monotonic() < deadline:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                try:
                    probe.bind(("127.0.0.1", port))
                except OSError:
                    time.sleep(0.5)
                    continue
            break  # bind succeeded — Preflight's own check will succeed here too


def _local_lite_containers() -> list[str]:
    label = f"label=com.docker.compose.project={LOCAL_LITE_PROJECT}"
    result = subprocess.run(
        ["docker", "ps", "-aq", "--filter", label],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]

#: `(the name the server container is configured from, the name the client library reads)`.
#: A new store with a split credential name belongs here in the same change that introduces it.
PAIRED_CREDENTIAL_NAMES: tuple[tuple[str, str], ...] = (
    ("OSPREY_ARCADEDB_PASSWORD", "ARCADEDB_ROOT_PASSWORD"),
    ("OSPREY_POSTGRES_USER", "POSTGRES_USER"),
    ("OSPREY_POSTGRES_DB", "POSTGRES_DB"),
    ("OSPREY_MINIO_USER", "MINIO_ACCESS_KEY"),
    ("OSPREY_MINIO_PASSWORD", "MINIO_SECRET_KEY"),
)


def _rendered_env(tmp_path: Path) -> dict[str, str]:
    """Runs the real `main()` far enough to write the environment file, then stops.

    `--no-build` is not enough on its own — the next stage would reach for a Docker daemon — so
    this drives the CLI and reads the artefact it wrote, accepting whatever exit code the later
    stages produce. What is under test is the *file*, and the file is written by the same code path
    a real apply uses rather than by a re-implementation of it here.
    """
    main(["--profile", "local-lite", "--out-root", str(tmp_path), "--build", "--no-build"])
    env_path = tmp_path / "local-lite" / "deployment.env"
    assert env_path.exists(), "apply did not get as far as writing the deployment environment file"
    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        values[name.strip()] = value.strip()
    return values


@pytest.mark.parametrize(("server_name", "client_name"), PAIRED_CREDENTIAL_NAMES)
def test_both_names_of_a_split_credential_carry_the_same_value(
    tmp_path: Path, server_name: str, client_name: str
) -> None:
    """Both halves present, and equal. Presence alone is not the assertion: two names holding two
    different generated secrets is precisely the ArcadeDB fault, and it passes a presence check."""
    env = _rendered_env(tmp_path)

    assert server_name in env, f"{server_name} is not written — the container has no credential"
    assert client_name in env, (
        f"{client_name} is not written — the client library falls back to its own default and "
        "authenticates with the wrong credential, which fails as a permission error rather than "
        "as a missing-configuration error"
    )
    assert env[server_name] == env[client_name], (
        f"{server_name} and {client_name} are two names for one value and they disagree"
    )


def test_a_generated_secret_is_not_empty_and_is_not_a_placeholder(tmp_path: Path) -> None:
    """A pair that agreed because both sides were empty would satisfy the test above."""
    env = _rendered_env(tmp_path)

    for _, client_name in PAIRED_CREDENTIAL_NAMES:
        value = env[client_name]
        assert value, f"{client_name} is empty"
        assert value not in {"minioadmin", "changeme", "password", "root"}, (
            f"{client_name} is a well-known default rather than a generated value"
        )


def test_demo_analyst_password_is_absent_without_the_flag(tmp_path: Path) -> None:
    """`06_DECISIONS.md` ADR-050 objection 3's resolution: "absent by default." A plain apply must
    not mint a credential for a subject nobody asked to exist."""
    env = _rendered_env(tmp_path)
    assert "OSPREY_DEMO_ANALYST_PASSWORD" not in env


def test_demo_analyst_password_is_written_and_realm_carries_the_subject_with_the_flag(
    tmp_path: Path,
) -> None:
    """The render-time half of `--demo-analyst`, which needs no live Keycloak: a real generated
    password lands in the environment file, and the realm document (also real, also written at
    this stage) names the subject `harness/keycloak_admin.py`'s `set_demo_analyst_password` would
    later set that password on."""
    import json

    from harness.apply import main
    from harness.realm import DEMO_ANALYST_SUBJECT

    main(
        [
            "--profile",
            "local-lite",
            "--out-root",
            str(tmp_path),
            "--build",
            "--no-build",
            "--demo-analyst",
        ]
    )

    env_path = tmp_path / "local-lite" / "deployment.env"
    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        values[name.strip()] = value.strip()
    assert values.get("OSPREY_DEMO_ANALYST_PASSWORD"), "no demo-analyst password was written"

    realm = json.loads((tmp_path / "local-lite" / "realm.json").read_text(encoding="utf-8"))
    usernames = {u["username"] for u in realm["users"]}
    assert DEMO_ANALYST_SUBJECT in usernames


def test_the_deployment_this_file_starts_is_a_real_one_and_the_teardown_removes_it(
    tmp_path: Path,
) -> None:
    """The mechanism `_teardown_local_lite_deployment` relies on, proven directly rather than
    inferred from reading it: `_rendered_env` really does reach a running `osprey-local-lite`
    deployment (not merely a rendered file), and the exact teardown command the fixture runs after
    every test really does remove it. Calls that command itself, ahead of the fixture's own
    identical call, so this test's assertion is about the command's effect, not about whether the
    fixture happened to run — the fixture then runs again on top of an already-empty project,
    which `docker compose down`'s own idempotence (proven separately, interactively, against this
    machine) makes a no-op rather than a second failure.

    **Verified manually, the "even on failure" half rule 15 asks for** (not re-asserted as a
    second, permanent test here, to avoid a second copy of this fixture's own logic drifting from
    the first): a test in this file was made to raise straight after `_rendered_env` returned, the
    suite was run, and `docker ps --filter label=com.docker.compose.project=osprey-local-lite`
    was empty immediately afterward despite the test's own failure — pytest's own guarantee that a
    `yield`-based fixture's teardown runs whether the test it wraps passed or not, exercised
    against this real fixture rather than assumed of it.
    """
    _rendered_env(tmp_path)
    running = _local_lite_containers()
    assert running, (
        "no osprey-local-lite container exists after _rendered_env — either `main()` no longer "
        "reaches `up`, or this test's own detection is wrong; either way the teardown below "
        "would prove nothing"
    )

    result = subprocess.run(
        ["docker", "compose", "-p", LOCAL_LITE_PROJECT, "down", "-v", "--remove-orphans"],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr

    assert _local_lite_containers() == [], (
        "containers survived the teardown command the autouse fixture relies on"
    )
