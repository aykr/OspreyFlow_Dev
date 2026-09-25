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

from pathlib import Path

import pytest
from harness.apply import main

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
    main(["--profile", "local-lite", "--out-root", str(tmp_path), "--no-build"])
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

    main(["--profile", "local-lite", "--out-root", str(tmp_path), "--no-build", "--demo-analyst"])

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
