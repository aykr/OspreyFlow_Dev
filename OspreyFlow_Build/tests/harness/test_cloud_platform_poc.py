"""The `cloud-platform` profile's proof-of-concept shape, `cloud_platform.shape: poc`
(`spec/06_DECISIONS.md` ADR-148 Amendment 5): one ArcadeDB and one ClickHouse whose Keeper runs
inside the server, no PodDisruptionBudgets, the Ingest root on a claim of its own, and the install
and decommission runbooks rendered for the deployment. The standard shape stays as P7 built it.

What a mistake would do, and the case that catches it (rule 12):
- a poc that still runs a Keeper StatefulSet, or a ClickHouse with no Keeper to reach (its
  Replicated database cannot start) — `test_the_clickhouse_server_runs_its_own_keeper`;
- uploads filling the disk the settings files and recipes live on —
  `test_the_ingest_root_is_on_a_claim_of_its_own`;
- a shape setting that changes the standard render — `test_the_standard_shape_is_the_default`;
- a production namespace in the poc shape, which would run one copy of each store and call it
  production — `test_the_poc_shape_is_refused_in_production`.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
import yaml
from harness.render import render
from pydantic import ValidationError
from tools.cp_policy_check import FIXTURES, _resolver

from schemas.deployment import OspreyConfig


def _config(name: str = "poc", **changes: Any) -> OspreyConfig:
    raw = yaml.safe_load((FIXTURES / f"{name}.yaml").read_text(encoding="utf-8"))
    for key, value in changes.items():
        raw[key] = {**raw.get(key, {}), **value} if isinstance(value, dict) else value
    return OspreyConfig.model_validate(raw)


def _artefacts(config: OspreyConfig) -> dict[str, str]:
    return render(config, resolver=_resolver).artefacts


def _values(config: OspreyConfig) -> dict[str, Any]:
    return yaml.safe_load(_artefacts(config)["values.yaml"])


@pytest.fixture(scope="module")
def poc() -> dict[str, Any]:
    return _values(_config())


def _by_name(values: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {w["name"]: w for w in values["workloads"]}


# ---- the setting ------------------------------------------------------------------------------


def test_the_standard_shape_is_the_default() -> None:
    """Naming the standard shape renders exactly what leaving it out does, so every P7 deployment
    is unchanged."""
    for name in ("development", "production"):
        raw = yaml.safe_load((FIXTURES / f"{name}.yaml").read_text(encoding="utf-8"))
        assert "shape" not in raw["cloud_platform"]
        named = _config(name, cloud_platform={**raw["cloud_platform"], "shape": "standard"})
        assert _artefacts(named) == _artefacts(_config(name))


def test_the_poc_shape_is_refused_in_production() -> None:
    raw = yaml.safe_load((FIXTURES / "poc.yaml").read_text(encoding="utf-8"))
    raw["cloud_platform"]["environment"] = "production"
    with pytest.raises(ValidationError, match="shape: poc is a development namespace's"):
        OspreyConfig.model_validate(raw)


def test_a_shape_the_profile_does_not_know_is_refused() -> None:
    raw = yaml.safe_load((FIXTURES / "poc.yaml").read_text(encoding="utf-8"))
    raw["cloud_platform"]["shape"] = "tiny"
    with pytest.raises(ValidationError):
        OspreyConfig.model_validate(raw)


# ---- the stores -------------------------------------------------------------------------------


def test_one_arcadedb_one_clickhouse_and_no_keeper_of_its_own(poc: dict[str, Any]) -> None:
    workloads = _by_name(poc)
    assert workloads["arcadedb"]["replicas"] == 1
    assert workloads["clickhouse"]["replicas"] == 1
    assert "clickhouse-keeper" not in workloads
    assert "keeper.xml" not in poc["files"]


def test_the_clickhouse_server_runs_its_own_keeper(poc: dict[str, Any]) -> None:
    """The cluster's ClickHouse holds a Replicated database, which needs a Keeper: in this shape
    the server runs one itself (`keeper_server` in its own configuration), a Raft of one, its log
    on the server's own claim, and the server's `zookeeper` is that Keeper."""
    config = poc["files"]["clickhouse.xml"]
    keeper = re.search(r"<keeper_server>(.*?)</keeper_server>", config, re.S)
    assert keeper, config
    assert "<tcp_port>9181</tcp_port>" in keeper.group(1)
    assert "<server_id>1</server_id>" in keeper.group(1)
    assert keeper.group(1).count("<server>") == 1
    claim = next(c for c in _by_name(poc)["clickhouse"]["claims"] if c["name"] == "data")
    for path in re.findall(r"<(?:log|snapshot)_storage_path>([^<]+)<", keeper.group(1)):
        assert path.startswith(claim["mountPath"] + "/"), path
    zookeeper = re.search(r"<zookeeper>(.*?)</zookeeper>", config, re.S)
    assert zookeeper and re.findall(r"<host>([^<]+)</host>", zookeeper.group(1)) == ["127.0.0.1"]
    assert "<port>9181</port>" in zookeeper.group(1)
    assert "clickhouse-keeper" not in config


def test_no_disruption_budgets(poc: dict[str, Any]) -> None:
    assert not [w["name"] for w in poc["workloads"] if "disruptionBudget" in w]


# ---- the Ingest root --------------------------------------------------------------------------


def test_the_ingest_root_is_on_a_claim_of_its_own(poc: dict[str, Any]) -> None:
    """ADR-148 Amendment 5: uploads and the drop folder on a disk of their own, so they cannot fill
    the one the settings files and the recipes are on; the other shared folders stay where P7 put
    them."""
    api = _by_name(poc)["api"]
    ingest = [s for s in api["shared"] if s["mountPath"].startswith("/var/lib/osprey/ingest")]
    assert ingest and all(s.get("claim") == "ingest" for s in ingest)
    # A folder on its claim, not the claim's root, which holds the file system's lost+found.
    assert all(s["subPath"].startswith("ingest") for s in ingest)
    others = [s for s in api["shared"] if s not in ingest]
    assert others and not [s for s in others if "claim" in s]
    claims = poc["storage"]["claims"]
    assert [c["name"] for c in claims] == ["ingest"]
    assert claims[0]["size"]
    # Only the shape adds it: the standard shape's values carry no claims of their own.
    assert "claims" not in _values(_config("development"))["storage"]
