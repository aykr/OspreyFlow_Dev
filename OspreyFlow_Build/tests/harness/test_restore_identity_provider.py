"""A restore starts Keycloak again on the restored PostgreSQL before it imports the identity
(`06_DECISIONS.md` ADR-114 Amendment 35 point 7, "as found on the first server").

**Found 4 November 2026.** A deployment running on empty stores (its compose file had been switched
to new named volumes by a refused move, so PostgreSQL was replaced while Keycloak kept running) was
restored with `ospreyflow restore <set> --yes`. The graph store and PostgreSQL were restored; then
the identity step failed, `could not authenticate to Keycloak: 500 {'error': 'unknown_error', ...}`,
Keycloak's log saying `relation "offline_user_session" does not exist`. Keycloak builds its schema
only when it starts. Once the stack was started again, the same identity import succeeded and
brought `admin` back with its original id.

**The stand-in Keycloak models the refusal, not only the grant** (`CLAUDE.md` rule 15): while the
database under it has been replaced and it has not been started again, its token endpoint answers
500 `unknown_error`, as the real one did, however often it is asked; started again, it grants a
token. `test_the_stand_in_keycloak_refuses_until_it_is_restarted` pins that.

What a mistake would do, and the case that catches it:
- the identity step asking a Keycloak still on the replaced database (the server's failure) —
  `test_a_restore_restarts_keycloak_after_postgresql_and_before_the_identity`;
- a restart that does not wait for Keycloak to answer — the same test: the stand-in refuses until
  it has been waited on (`up --wait`), and its token endpoint answers a little later still;
- a refused password waited on for minutes as though Keycloak were starting —
  `test_a_refused_password_is_not_waited_on`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from harness import restore
from harness.keycloak_admin import AdminLoginRefused

ENV = (
    "POSTGRES_USER=osprey\nPOSTGRES_DB=ospreyflow\nOSPREY_KEYCLOAK_PORT=8081\n"
    "OSPREY_KEYCLOAK_ADMIN_PASSWORD=kc-admin-secret\n"
)
TOKEN_PATH = "/realms/master/protocol/openid-connect/token"


class FakeKeycloak:
    """Keycloak over its PostgreSQL, as far as a restore meets it."""

    def __init__(self) -> None:
        self.events: list[str] = []
        self.database_replaced = False
        self.started = True
        #: Asks of the token endpoint, after a restart, before it answers (healthy is not ready).
        self.warming = 0

    def postgres_restored(self) -> None:
        self.events.append("postgres restored")
        self.database_replaced = True

    def compose(self, command: list[str], *, item: str, capture: bool = True) -> str:
        verb = command[command.index("-f") + 2]
        self.events.append(" ".join(command[command.index("-f") + 2 :]))
        if verb == "restart" and command[-1] == "keycloak":
            self.started = False
        elif verb == "up" and command[-1] == "keycloak" and "--wait" in command:
            self.started, self.database_replaced, self.warming = True, False, 2
        else:
            raise AssertionError(f"unexpected compose call: {command}")
        return ""

    def call(self, url: str, **kwargs: Any) -> tuple[int, Any]:
        assert url.endswith(TOKEN_PATH), url
        self.events.append("token asked")
        if not self.started:
            raise restore.keycloak_admin.RealmConfigurationFailed(f"{url} unreachable: refused")
        if self.database_replaced:
            return 500, {"error": "unknown_error", "error_description": "For more on this error"}
        if self.warming:
            self.warming -= 1
            return 503, "starting"
        if kwargs["data"]["password"] != "kc-admin-secret":
            return 401, {"error": "invalid_grant"}
        self.events.append("token granted")
        return 200, {"access_token": "t"}


@pytest.fixture
def keycloak(monkeypatch: pytest.MonkeyPatch) -> FakeKeycloak:
    fake = FakeKeycloak()
    monkeypatch.setattr(restore, "_run", fake.compose)
    monkeypatch.setattr(restore.keycloak_admin, "_call", fake.call)
    monkeypatch.setattr(restore, "KEYCLOAK_PAUSE_SECONDS", 0.0, raising=False)
    monkeypatch.setattr(restore, "answer_localhost_with_loopback", lambda: None)
    return fake


@pytest.fixture
def deployment(tmp_path: Path) -> Path:
    out = tmp_path / "deploy" / "small"
    out.mkdir(parents=True)
    (out / "compose.yaml").write_text(
        "name: osprey-small\nservices:\n  postgres: {}\n  keycloak: {}\n", encoding="utf-8"
    )
    (out / "deployment.env").write_text(ENV, encoding="utf-8")
    return out / "compose.yaml"


def _backup_set(tmp_path: Path) -> Path:
    folder = tmp_path / "set-1"
    (folder / "identity").mkdir(parents=True)
    (folder / "identity" / "realm.json").write_text(
        json.dumps({"format": 1, "realm": "osprey", "people": [], "dashboards": []}),
        encoding="utf-8",
    )
    return folder


def _restore(
    tmp_path: Path, deployment: Path, keycloak: FakeKeycloak, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _backup_set(tmp_path)
    manifest = {"files": [{"item": "postgres", "path": "postgres/dump.sql"},
                          {"item": "identity", "path": "identity/realm.json"}]}  # fmt: skip
    monkeypatch.setattr(restore, "load_manifest", lambda _d: manifest)
    monkeypatch.setattr(restore, "verify_checksums", lambda _d, _m: None)
    monkeypatch.setattr(restore, "check_schema_compatibility", lambda _m: None)
    monkeypatch.setattr(restore, "dry_run_for", lambda _d, _m: None)
    monkeypatch.setattr(restore, "graph_store_is_empty", lambda _c, **_k: True)
    monkeypatch.setattr(restore, "restore_postgres_all",
                        lambda _c, _dumps, _roles: keycloak.postgres_restored())  # fmt: skip
    monkeypatch.setattr(
        restore.identity, "import_identity",
        lambda **kw: keycloak.events.append(f"identity imported with {kw['token']}")
        or {"people": 1, "dashboards": 0, "replaced": 1},
    )  # fmt: skip
    monkeypatch.setattr(restore, "_register_sign_in", lambda _env: None)
    restore.run_restore(
        directory=folder,
        compose_file=deployment,
        database="ospreyflow",
        analytics_container_path="/var/lib/osprey/data/analytics.duckdb",
        acknowledged=True,
    )


def test_the_stand_in_keycloak_refuses_until_it_is_restarted(keycloak: FakeKeycloak) -> None:
    keycloak.postgres_restored()
    for _ in range(5):
        assert keycloak.call(f"https://id.example{TOKEN_PATH}", data={"password": "x"})[0] == 500
    keycloak.compose(["docker", "compose", "-f", "c", "restart", "keycloak"], item="identity")
    with pytest.raises(restore.keycloak_admin.RealmConfigurationFailed):
        keycloak.call(f"https://id.example{TOKEN_PATH}", data={"password": "kc-admin-secret"})
    keycloak.compose(["docker", "compose", "-f", "c", "up", "-d", "--no-deps", "--wait",
                      "keycloak"], item="identity")  # fmt: skip
    answers = [
        keycloak.call(f"https://id.example{TOKEN_PATH}", data={"password": "kc-admin-secret"})[0]
        for _ in range(3)
    ]
    assert answers == [503, 503, 200]


def test_a_restore_restarts_keycloak_after_postgresql_and_before_the_identity(
    tmp_path: Path,
    deployment: Path,
    keycloak: FakeKeycloak,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _restore(tmp_path, deployment, keycloak, monkeypatch)
    events = keycloak.events
    assert events.index("postgres restored") < events.index("restart keycloak")
    assert events.index("restart keycloak") < events.index("up -d --no-deps --wait keycloak")
    assert events.index("up -d --no-deps --wait keycloak") < events.index("token granted")
    assert events[-1] == "identity imported with t"


def test_a_refused_password_is_not_waited_on(
    tmp_path: Path,
    deployment: Path,
    keycloak: FakeKeycloak,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = deployment.parent / "deployment.env"
    env.write_text(ENV.replace("kc-admin-secret", "wrong"), encoding="utf-8")
    with pytest.raises(restore.BackupFailed) as failed:
        _restore(tmp_path, deployment, keycloak, monkeypatch)
    assert failed.value.item == "identity" and "401" in failed.value.detail
    assert isinstance(failed.value.__cause__, AdminLoginRefused)
    assert keycloak.events.count("token asked") == 3  # two while it warms, then the refusal
