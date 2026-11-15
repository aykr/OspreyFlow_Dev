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


class _Door:
    """The Glass's door as a deployment that passes every check answers it. Tokens are the names
    `token()` was stood in to give: `admin`, `stranger`, or `refused`."""

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
        for tail, (status, body) in answers.items():
            if path.endswith(tail):
                return _Answer(status, body)
        raise AssertionError(f"an unexpected POST {path}")

    def put(self, path: str, **_: Any) -> _Answer:
        return _Answer(200)


def _checks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, search: str) -> tuple[list[str], str]:
    r1 = _r1_kind()
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
