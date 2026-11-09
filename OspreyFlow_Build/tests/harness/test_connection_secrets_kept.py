"""A SQL or API connection's secret and the egress allow-list survive `apply`, and a restore names
the ones to enter again (`06_DECISIONS.md` ADR-140 Amendment 13; `05_DEPLOYMENT.md` §6.1; the
orchestrator's second review of L1.6, item 4).

Both live only in `deployment.env`: `OSPREY_CONNECTION_SECRET_<NAME>` and `OSPREY_CONNECTOR_EGRESS`.
A re-render writes the file afresh, keeping only what `keep_existing_secrets` keeps; and no backup
carries the file, so a restored deployment's connections name secrets it does not hold.

What a mistake would do, and the case that catches it:
- an `apply` that silently drops every connection's secret, or the egress list, so each read is
  refused until someone notices — `test_apply_keeps_connection_secrets_and_the_egress_list`;
- a restore that says nothing of them — `test_a_restore_names_each_connection_secret_to_enter`;
- a connection's secret given to every container that reads `deployment.env`, not the Conduit
  alone (the orchestrator's review of ADR-140 Amendment 15, item 9) —
  `test_no_service_but_the_conduit_is_given_a_connection_secret` (Compose),
  `test_no_cluster_workload_but_the_conduit_is_given_a_connection_secret` and
  `test_the_conduit_reads_only_a_declared_secret`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from harness.apply import keep_existing_secrets
from harness.render import load_config, render
from harness.restore import connection_secrets_to_enter
from tools.layout import CORE

from schemas.deployment import ConnectorsConfig, OspreyConfig
from tests.harness.test_cluster_render import _workloads, cluster_config, values_for
from tests.harness.test_render import FIXTURE_CONFIG, _fake_resolver

DECLARED = ConnectorsConfig(secrets=["NOMIS_READER", "TELCO"])
VARIABLES = ("OSPREY_CONNECTION_SECRET_NOMIS_READER", "OSPREY_CONNECTION_SECRET_TELCO")


def test_apply_keeps_connection_secrets_and_the_egress_list() -> None:
    previous = (
        "OSPREY_PROFILE=local-lite\n"
        "OSPREY_CONNECTION_SECRET_NOMIS_READER=synthetic-pw-1\n"
        "OSPREY_CONNECTION_SECRET_TELCO=synthetic-token-2\n"
        "OSPREY_CONNECTOR_EGRESS=telco.example,db.client.example\n"
    )
    fresh = "OSPREY_PROFILE=local-lite\nOSPREY_CONNECTOR_EGRESS=\n"
    kept = keep_existing_secrets(fresh, previous)
    assert "OSPREY_CONNECTION_SECRET_NOMIS_READER=synthetic-pw-1" in kept.splitlines()
    assert "OSPREY_CONNECTION_SECRET_TELCO=synthetic-token-2" in kept.splitlines()
    assert "OSPREY_CONNECTOR_EGRESS=telco.example,db.client.example" in kept.splitlines()
    assert kept.count("OSPREY_CONNECTOR_EGRESS=") == 1


def _dump(rows: list[dict[str, object]]) -> str:
    lines = ["-- PostgreSQL database dump", "",
             "COPY public.ingest_connections (id, kind, name, created_by, created_at, settings, "
             "datasets) FROM stdin;"]  # fmt: skip
    for r in rows:
        settings = "\\N" if r["settings"] is None else json.dumps(r["settings"])
        lines.append("\t".join([str(r["id"]), str(r["kind"]), str(r["name"]), "adm",
                                "2026-11-09 00:00:00+00", settings, '["ds-a"]']))  # fmt: skip
    return "\n".join([*lines, "\\.", "", "COPY public.other (x) FROM stdin;", "1", "\\.", ""])


def test_a_restore_names_each_connection_secret_to_enter(tmp_path: Path) -> None:
    (tmp_path / "postgres").mkdir()
    (tmp_path / "postgres" / "dump.sql").write_text(_dump([
        {"id": "files", "kind": "files", "name": "Files", "settings": None},
        {"id": "c1", "kind": "sql", "name": "NOMIS", "settings": {"kind": "sql",
                                                                  "secret": "NOMIS_READER"}},
        {"id": "c2", "kind": "api", "name": "Telco", "settings": {"kind": "api", "auth": "bearer",
                                                                  "secret": "TELCO"}},
        {"id": "c3", "kind": "json", "name": "Files", "settings": {"kind": "json"}},
    ]))  # fmt: skip
    assert connection_secrets_to_enter(tmp_path) == [
        "OSPREY_CONNECTION_SECRET_NOMIS_READER",
        "OSPREY_CONNECTION_SECRET_TELCO",
        "OSPREY_CONNECTOR_EGRESS",
    ]
    assert connection_secrets_to_enter(tmp_path / "nowhere") == []


def _lite(tmp_path: Path) -> OspreyConfig:
    path = tmp_path / "osprey.yaml"
    path.write_text(FIXTURE_CONFIG, encoding="utf-8")
    loaded = load_config(path)
    return loaded.model_copy(update={
        "connectors": DECLARED,
        "components": loaded.components.model_copy(update={"source_path": str(CORE)}),
    })  # fmt: skip


def test_no_service_but_the_conduit_is_given_a_connection_secret(tmp_path: Path) -> None:
    """Every owned service reads `deployment.env` whole; its own environment, which Compose puts
    above the file, blanks each declared secret, except the Conduit's."""
    rendered = render(_lite(tmp_path), resolver=_fake_resolver)
    services = yaml.safe_load(rendered.artefacts["compose.yaml"])["services"]
    readers = [name for name, service in services.items() if "env_file" in service]
    assert "api" in readers and len(readers) > 1
    for name in readers:
        environment = services[name].get("environment") or {}
        for variable in VARIABLES:
            if name == "api":
                assert variable not in environment, (name, variable)
            else:
                assert environment.get(variable) == "", (name, variable)
    lines = rendered.artefacts["deployment.env"].splitlines()
    env = dict(line.partition("=")[::2] for line in lines if "=" in line and line[0] != "#")
    assert env["OSPREY_CONNECTOR_SECRETS"] == "NOMIS_READER,TELCO"


def test_no_cluster_workload_but_the_conduit_is_given_a_connection_secret() -> None:
    values = values_for(cluster_config(connectors=DECLARED.model_dump()))
    readers = [w for w in _workloads(values).values() if w.get("envFrom")]
    assert any(w["name"] == "api" for w in readers) and len(readers) > 1
    for workload in readers:
        blanked = {e["name"]: e.get("value") for e in workload.get("env", [])}
        for variable in VARIABLES:
            if workload["name"] == "api":
                assert variable not in blanked, (workload["name"], variable)
            else:
                assert blanked.get(variable) == "", (workload["name"], variable)


def test_the_conduit_reads_only_a_declared_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """An undeclared secret is blanked nowhere, so the Conduit never reads one, even if set."""
    from services.api.connector_reads import secret_of

    monkeypatch.setenv("OSPREY_CONNECTION_SECRET_TELCO", "synthetic-token")
    monkeypatch.setenv("OSPREY_CONNECTION_SECRET_ROGUE", "synthetic-other")
    monkeypatch.setenv("OSPREY_CONNECTOR_SECRETS", "TELCO")
    assert secret_of("TELCO") == "synthetic-token"
    assert secret_of("ROGUE") is None
    monkeypatch.delenv("OSPREY_CONNECTOR_SECRETS")
    assert secret_of("TELCO") is None
