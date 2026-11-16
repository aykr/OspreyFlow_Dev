"""R1's checks probe the OpenSearch domain only where the release being checked has one (step 6,
the orchestrator, 15 November 2026). Step 6's copy A is v0.5.1 with main's R1 scripts over it and
v0.5.1's own `r1_kind_osprey.yaml`, which searches with `postgres-fulltext` and makes no domain
(ADR-148 Amendment 5 point 16), so row 2's checks stopped on "the namespace's role reaches the
domain" after every v0.5.1 check had passed. The v0.5.2 rows after the upgrade search with
OpenSearch, and their checks must still probe it (ADR-148 Amendment 13).

What a mistake would do, and the case that catches it (rule 12):
- the domain probed on a release without one:
  `test_a_release_without_opensearch_passes_its_checks_with_the_domain_skipped`;
- the domain skipped on a release with one: `test_a_release_with_opensearch_has_its_domain_checked`.

The run API's app role (ADR-148 Amendment 20, v0.6.0 #18) likewise, by the release's own version:
- checked on a release before v0.6.0, which has no such role:
  `test_a_release_before_v060_skips_the_run_api_role_in_words`;
- skipped on a release that has it, or on one whose version cannot be read:
  `test_a_v060_release_has_its_run_api_role_checked_with_the_standins_tokens`;
- a run API that lets an application holding no app role past its door, refuses the orchestrator
  holding the role, or lets the report sync's dashboard identity in, or a 404 that is not the
  Conduit's, passes the checks:
  `test_a_run_api_answering_wrongly_fails_the_checks`;
- the checks' words drift from the Conduit's own:
  `test_the_checks_words_are_the_conduits_own`.

Each runs the real `r1_kind.checks()`, the door, the tokens and the record stood in for, and the
domain's own checks (`domain_checks`, held by the domain's tests) recorded rather than run."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

GATES = Path(__file__).parents[1] / "process/lanes/platform/gates"
ADMIN_OID = "50000000-0000-4000-8000-000000000001"


def _r1_kind():  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(GATES))
    try:
        import r1_kind
    finally:
        sys.path.remove(str(GATES))
    return r1_kind


class _Answer:
    def __init__(self, status: int, body: Any = None) -> None:
        self.status_code = status
        self._body = {} if body is None else body
        self.text = str(self._body)

    def json(self) -> Any:
        return self._body


def _conduit_words() -> tuple[str, str, str]:
    """The Conduit's own refusals, and its 404 for a run it has no record of, read from its code."""
    import re

    from services.api.service_identity import DASHBOARD_IS_NO_SERVICE_IDENTITY, RUN_ROLE_NOT_HELD

    app = (Path(__file__).parents[2] / "OspreyFlow_Core/services/api/app.py").read_text(encoding="utf-8")
    found = re.search(r'"(no run this service identity triggered[^"]*)"', app)
    assert found, "the run API's own 404 for an unknown run"
    return RUN_ROLE_NOT_HELD, DASHBOARD_IS_NO_SERVICE_IDENTITY, found.group(1)


class _Door:
    """The Glass's door as a deployment that passes every check answers it. Tokens are the names
    `token()` was stood in to give: `admin`, `stranger`, or `refused`, and `standin_token()` the
    application's own name from `r1_kind_entra.yaml`. `version` is what Admin › System says;
    `wrong` says what the run API gets wrong, if anything."""

    version: Any = "v0.6.0"
    #: What the run API gets wrong, if anything: "unassigned-in", "orchestrator-out", "dashboard-in", or
    #: "ingress-404" (the path reaches no Conduit, so a 404 in another's words).
    wrong = ""
    runs: list[str] = []
    #: How many searches answer no node before the load is found: the indexer writes a moment
    #: after the load (ADR-150), so a search at once can find nothing
    #: (`tests/test_r1_kind_search_wait.py`).
    found_after = 0
    searches = 0

    def get(self, path: str, headers: dict[str, str] | None = None, **_: Any) -> _Answer:
        who = (headers or {}).get("Authorization", "").removeprefix("Bearer ")
        if path == "/healthz":
            return _Answer(200)
        if path == "/v1/me":
            if who == "admin":
                return _Answer(200, {"roles": ["osprey-admin"], "clearance": "OFFICIAL-SENSITIVE"})
            return _Answer(200, {"roles": []}) if who == "stranger" else _Answer(401)
        if path == "/v1/admin/people":
            return _Answer(200, [{"id": ADMIN_OID}]) if who == "admin" else _Answer(403)
        if path.endswith("/profile"):
            return _Answer(200)
        if path.endswith("/alert-queue"):
            return _Answer(200, [{"rule_id": "hotlist:h1"}])
        if path == "/v1/admin/system":
            return _Answer(200, {"version": self.version}) if who == "admin" else _Answer(403)
        if path == "/v1/runs/r1-no-such-run":
            self.runs.append(who)
            role, dashboard, not_found = _conduit_words()
            let_in = {"orchestrator": self.wrong != "orchestrator-out",
                      "orchestrator-unassigned": self.wrong == "unassigned-in",
                      "report-sync": self.wrong == "dashboard-in"}
            if who == "orchestrator" and self.wrong == "ingress-404":
                return _Answer(404, {"detail": "Not Found"})
            if let_in.get(who):
                return _Answer(404, {"detail": not_found})
            return _Answer(403, {"detail": dashboard if who == "report-sync" else role})
        raise AssertionError(f"an unexpected GET {path}")

    def post(self, path: str, headers: dict[str, str] | None = None, **_: Any) -> _Answer:
        who = (headers or {}).get("Authorization", "").removeprefix("Bearer ")
        if path == "/v1/investigations":
            return _Answer(201, {"id": "case-1"}) if who == "admin" else _Answer(403)
        answers = {
            "/hotlists": (201, {"id": "h1"}),
            "/source-files": (201, {"source_location": "loc"}),
            "/recipes": (201, {"recipe_id": "r1"}),
            "/verify": (200, {}),
            "/publish": (200, {}),
            "/run": (200, {"nodes_created": 2}),
            "/search": (200, {"nodes": [{"id": "n1"}]}),
        }
        if path.endswith("/search"):
            type(self).searches += 1
            if type(self).searches <= self.found_after:
                return _Answer(200, {"nodes": [], "source": "index"})
        for tail, (status, body) in answers.items():
            if path.endswith(tail):
                return _Answer(status, body)
        raise AssertionError(f"an unexpected POST {path}")

    def put(self, path: str, **_: Any) -> _Answer:
        return _Answer(200)


def _checks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, search: str, version: Any = "v0.6.0",
            wrong: str = "", issue: Any = None) -> tuple[list[str], str]:
    r1 = _r1_kind()
    monkeypatch.setattr(_Door, "version", version)
    monkeypatch.setattr(_Door, "wrong", wrong)
    monkeypatch.setattr(_Door, "runs", [])
    monkeypatch.setattr(_Door, "searches", 0)
    # The stand-in's issuing (held by tests/test_r1_entra_standin.py) stood in by the application's name.
    names = {v["client_id"]: k for k, v in yaml.safe_load((GATES / "r1_kind_entra.yaml").read_text()).items()
             if isinstance(v, dict) and "client_id" in v}
    monkeypatch.setattr(r1, "standin_token", issue or (lambda client_id, secret: names[client_id]))
    monkeypatch.setattr(r1, "entra_clients", lambda: {n: f"{n}-secret" for n in names.values()})
    config = tmp_path / "r1_kind_osprey.yaml"
    config.write_text(yaml.safe_dump({
        "components": {"search": search},
        "cloud_platform": {"claims": {"first_administrators": [ADMIN_OID]}},
    }))  # fmt: skip
    monkeypatch.setattr(r1, "CONFIG", config)
    monkeypatch.setattr(r1, "door", _Door)
    monkeypatch.setattr(r1, "token", lambda **o: "stranger" if "oid" in o and o["oid"] else (
        "refused" if o else "admin"))  # fmt: skip
    monkeypatch.setattr(r1, "_foreign_signed", lambda: "refused")
    monkeypatch.setattr(r1, "record", lambda name: tmp_path / f"{name}.log")
    monkeypatch.setattr(r1, "save", lambda **_: {})
    probed: list[str] = []
    monkeypatch.setattr(r1, "domain_checks", lambda ok: probed.append("domain"))
    r1.checks()
    return probed, (tmp_path / "check.log").read_text()


def test_a_release_without_opensearch_passes_its_checks_with_the_domain_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    probed, log = _checks(tmp_path, monkeypatch, "postgres-fulltext")
    assert probed == [], "v0.5.1 makes no domain, so nothing probes one"
    assert "FAIL" not in log
    assert "SKIP the domain" in log and "postgres-fulltext" in log, log[-300:]
    assert "every check passed" in capsys.readouterr().out


def test_a_release_with_opensearch_has_its_domain_checked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probed, log = _checks(tmp_path, monkeypatch, "opensearch")
    assert probed == ["domain"]
    assert "SKIP the domain" not in log


def test_a_release_before_v060_skips_the_run_api_role_in_words(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, log = _checks(tmp_path, monkeypatch, "postgres-fulltext", version="v0.5.1")
    assert _Door.runs == [], "v0.5.1 has no OspreyFlow.Run, so nothing asks its run API for it"
    assert "SKIP the run API's app role" in log and "FAIL" not in log, log[-300:]


@pytest.mark.parametrize("version", ["v0.6.0", "0.7.1", None, "unreleased"])
def test_a_v060_release_has_its_run_api_role_checked_with_the_standins_tokens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, version: Any
) -> None:
    _, log = _checks(tmp_path, monkeypatch, "opensearch", version=version)
    assert _Door.runs == ["orchestrator", "orchestrator-unassigned", "report-sync"]
    assert "SKIP the run API's app role" not in log and "FAIL" not in log, log[-300:]
    assert "PASS the run API refuses an application holding no app role, in words" in log


@pytest.mark.parametrize(("wrong", "check"), [
    ("unassigned-in", "refuses an application holding no app role"),
    ("orchestrator-out", "takes an orchestrator holding OspreyFlow.Run past its door"),
    ("dashboard-in", "refuses the report sync's dashboard identity"),
    ("ingress-404", "takes an orchestrator holding OspreyFlow.Run past its door"),
], ids=["unassigned-in", "orchestrator-out", "dashboard-in", "ingress-404"])  # fmt: skip
def test_a_run_api_answering_wrongly_fails_the_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wrong: str, check: str
) -> None:
    with pytest.raises(SystemExit, match=check):
        _checks(tmp_path, monkeypatch, "opensearch", wrong=wrong)


def test_the_checks_words_are_the_conduits_own() -> None:
    r1 = _r1_kind()
    role, dashboard, not_found = _conduit_words()
    assert r1.RUN_ROLE_WORDS in role and r1.DASHBOARD_WORDS in dashboard and r1.RUN_NOT_FOUND == not_found


def test_a_token_the_standin_will_not_issue_is_a_fail_in_the_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stand-in started before the orchestrators were added refuses them (700016): said in the
    record as a FAIL with its AADSTS words, never a bare exit the record does not show."""

    def refused(client_id: str, secret: str) -> str:
        # `sh()`'s own shape for a failed kubectl exec, with what STANDIN_TOKEN writes of a refusal
        # (that script, against the real stand-in: tests/test_r1_entra_standin.py).
        raise SystemExit("kubectl -n platform-managed exec deployment/entra-standin --: exit 1\n"
                         "the stand-in refused (400): unauthorized_client: AADSTS700016: Application "
                         "with identifier was not found in the directory\n"
                         "command terminated with exit code 1\n")

    with pytest.raises(SystemExit, match="issues orchestrator its token"):
        _checks(tmp_path, monkeypatch, "opensearch", issue=refused)
    log = (tmp_path / "check.log").read_text()
    line = next(x for x in log.splitlines() if x.startswith("FAIL the Entra stand-in issues"))
    assert "AADSTS700016" in line and "kubectl" not in line, line
    assert "command terminated" not in log, "one line a check in the record"
