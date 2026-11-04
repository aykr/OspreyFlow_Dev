"""A demo pack loads on a deployment with no demo accounts, its case shared with the first
administrator as Author (ADR-114 Amendment 33, as found on the first server, 4 November 2026).

Found on a Small on its own server, v0.4.6: `ospreyflow demo add <pack>` failed for every pack with
"osprey-demo-admin, osprey-demo-analyst not found in the identity provider … Run `ospreyflow
repair-sign-in`", which on a Small never makes them (administration guide §5a). The guide already
said each pack "loads into its own case, with the installing administrator as Author".

The identity provider here is a stand-in served over HTTP, reached by the real `_lookup_subs`
through `harness.keycloak_admin`, and it answers as Keycloak 26 does for a realm holding `admin` and
no demo account: a master-realm admin token only for the right password (401 otherwise); a user
search without a bearer token refused (401); `users?username=X&exact=true` an empty list, status
200, for an account that is not there; and **without** `exact=true` a substring search, so a lookup
that dropped it would take `osprey-demo-admin` for `admin`. What a mistake would do, and the case
that catches it:
- every pack refused on a deployment without demo accounts —
  `test_each_synthetic_pack_loads_with_the_first_administrator_as_its_author`;
- the case made in the demo accounts' unit, which the first administrator's unit cannot see (a case
  of another unit never appears, whatever its grants) — the same case, on `--org-unit`;
- the Prison Intelligence Dataset's loads attributed to a demo engineer who does not exist —
  the same case, on `--run-as`;
- a pack's mid-demo check looking in the demo unit —
  `test_a_mid_demo_check_reads_the_case_in_the_first_administrators_unit`;
- the Admin role, which does not open a case's graph, left unsaid —
  `test_it_says_the_admin_role_does_not_open_the_case`;
- a deployment with neither the demo accounts nor the first administrator seeded into a case nobody
  can open — `test_with_neither_the_demo_accounts_nor_the_first_administrator_it_refuses_in_words`;
- the demo accounts' behaviour changed where they exist — `test_seed_internal.py`, unchanged.
"""

from __future__ import annotations

import json
import urllib.parse
from collections.abc import Iterator, Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

import pytest
from scripts import seed_internal

ADMIN_PASSWORD = "bootstrap-admin-password"
TOKEN = "stand-in-admin-token"
ADMIN_SUBJECT = "6f1c2e0a-0000-4000-8000-00000000ad01"
FIRST_ADMIN = {
    "id": ADMIN_SUBJECT,
    "username": "admin",
    "enabled": True,
    "emailVerified": False,
    "attributes": {
        "clearance": ["SECRET"],
        "org_unit": ["administration"],
        "receivable_handling_codes": ["H1"],
        "roles": ["osprey-admin"],
    },
    "requiredActions": ["UPDATE_PASSWORD"],
}
SYNTHETIC_PACKS = {
    "hmp": "hmp",
    "operation-ledger": "ledger",
    "fixture-corp": "fixture-corp",
    "cyber-intrusion": "cyber-intrusion",
    "prison-intelligence": "prison-intelligence",
    "prison-intelligence-scale": "prison-intelligence-scale",
}


class _Keycloak(BaseHTTPRequestHandler):
    users: list[dict[str, Any]] = [FIRST_ADMIN]

    def log_message(self, *args: object) -> None:
        pass

    def _answer(self, status: int, body: object) -> None:
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        form = urllib.parse.parse_qs(self.rfile.read(length).decode())
        if self.path != "/realms/master/protocol/openid-connect/token":
            self._answer(404, {"error": "Unable to find matching target resource method"})
        elif form.get("password") != [ADMIN_PASSWORD] or form.get("username") != ["admin"]:
            self._answer(401, {"error": "invalid_grant",
                               "error_description": "Invalid user credentials"})  # fmt: skip
        else:
            self._answer(200, {"access_token": TOKEN, "token_type": "Bearer"})

    def do_GET(self) -> None:  # noqa: N802
        url = urllib.parse.urlparse(self.path)
        if url.path != "/admin/realms/osprey/users":
            self._answer(404, {"error": "Unable to find matching target resource method"})
            return
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            self._answer(401, {"error": "HTTP 401 Unauthorized"})
            return
        query = urllib.parse.parse_qs(url.query)
        wanted = (query.get("username") or [""])[0].lower()
        exact = (query.get("exact") or ["false"])[0] == "true"
        found = [
            user for user in self.users
            if (user["username"] == wanted if exact else wanted in user["username"])
        ]  # fmt: skip
        self._answer(200, found)


@pytest.fixture
def keycloak() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Keycloak)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def repo(tmp_path: Path, keycloak: str) -> Path:
    """A checkout whose one rendered deployment's identity provider is the stand-in."""
    (tmp_path / ".git").mkdir()
    core = tmp_path / "OspreyFlow_Core"
    out = core / "deploy" / "generated" / "small"
    out.mkdir(parents=True)
    (out / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    (out / "deployment.env").write_text(
        f"OSPREY_IDENTITY_ORIGIN={keycloak}\nOSPREY_KEYCLOAK_ADMIN_PASSWORD={ADMIN_PASSWORD}\n",
        encoding="utf-8",
    )
    (core / "scripts").mkdir()
    (tmp_path / "OspreyFlow_Data").mkdir()
    return core


class Runner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, argv: Sequence[str]) -> str:
        self.calls.append(list(argv))
        return "Seeded.\n"


def _seed_call(runner: Runner) -> list[str]:
    (call,) = [c for c in runner.calls if "run" in c]
    return call


def _values(call: list[str], flag: str) -> list[str]:
    return [call[i + 1] for i, a in enumerate(call) if a == flag]


def _seed(repo: Path, dataset: str, runner: Runner, **kwargs: Any) -> list[str]:
    return seed_internal.seed_internal(
        dataset, repo, run=runner, api_running=lambda compose: False, **kwargs
    )


def test_the_lookup_finds_the_first_administrator_and_no_demo_account(repo: Path) -> None:
    found = seed_internal._lookup_subs(repo / "deploy" / "generated" / "small")
    assert found == {"admin": ADMIN_SUBJECT}


@pytest.mark.parametrize("pack", sorted(SYNTHETIC_PACKS))
def test_each_synthetic_pack_loads_with_the_first_administrator_as_its_author(
    repo: Path, pack: str
) -> None:
    runner = Runner()
    _seed(repo, SYNTHETIC_PACKS[pack], runner)
    call = _seed_call(runner)
    assert _values(call, "--grant") == [f"{ADMIN_SUBJECT}=author"], "the Author, and no Editor"
    assert _values(call, "--org-unit") == ["administration"], "the first administrator's own unit"
    spec = seed_internal.DATASETS[SYNTHETIC_PACKS[pack]]
    assert _values(call, "--run-as") == ([ADMIN_SUBJECT] if spec.rehearsal else [])


def test_a_mid_demo_check_reads_the_case_in_the_first_administrators_unit(repo: Path) -> None:
    runner = Runner()
    _seed(repo, "prison-intelligence", runner, check=True)
    call = _seed_call(runner)
    assert _values(call, "--org-unit") == ["administration"]
    assert _values(call, "--run-as") == [ADMIN_SUBJECT]


def test_it_says_the_admin_role_does_not_open_the_case(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lines = _seed(repo, "hmp", Runner())
    said = capsys.readouterr().out
    assert "admin, the first administrator, is its Author" in said
    assert "Analyst role" in said and lines[-1] in said


def test_with_neither_the_demo_accounts_nor_the_first_administrator_it_refuses_in_words(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_Keycloak, "users", [])
    runner = Runner()
    with pytest.raises(seed_internal.SeedRefused) as refused:
        _seed(repo, "hmp", runner)
    said = str(refused.value)
    assert "first administrator" in said and "harness.first_admin" in said
    assert runner.calls == []
