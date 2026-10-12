"""A deployment that names ClickHouse renders it as a real service (ADR-114 decision 9): the image
the adapter was proved against, its password from the env file and never in a generated file, its
data on a volume, a health check the Conduit waits on, and no published port. A DuckDB deployment
renders none of it."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from harness.apply import analytics_secret_lines
from harness.render import load_config, render
from tools.layout import CORE

from schemas.deployment import AnalyticsEngine, OspreyConfig
from tests.harness.test_render import FIXTURE_CONFIG, _fake_resolver


def _config(tmp_path: Path, engine: AnalyticsEngine) -> OspreyConfig:
    path = tmp_path / "osprey.yaml"
    path.write_text(FIXTURE_CONFIG, encoding="utf-8")
    loaded = load_config(path)
    return loaded.model_copy(
        update={
            "components": loaded.components.model_copy(
                update={"source_path": str(CORE), "analytics_engine": engine}
            )
        }
    )


def _compose(config: OspreyConfig) -> dict:  # type: ignore[type-arg]
    return yaml.safe_load(render(config, resolver=_fake_resolver).artefacts["compose.yaml"])


def _env(config: OspreyConfig) -> str:
    return render(config, resolver=_fake_resolver).artefacts["deployment.env"]


def test_clickhouse_renders_as_a_service_the_conduit_waits_for(tmp_path: Path) -> None:
    compose = _compose(_config(tmp_path, AnalyticsEngine.CLICKHOUSE))
    clickhouse = compose["services"]["clickhouse"]
    assert clickhouse["image"].startswith("clickhouse/clickhouse-server:25.8.33.6")
    assert clickhouse["environment"]["CLICKHOUSE_USER"] == "osprey"
    assert clickhouse["environment"]["CLICKHOUSE_PASSWORD"].startswith(
        "${OSPREY_CLICKHOUSE_PASSWORD:?"
    )
    assert "ports" not in clickhouse
    assert "healthcheck" in clickhouse
    volume = clickhouse["volumes"][0].split(":")[0]
    assert volume in compose["volumes"]
    assert compose["services"]["api"]["depends_on"]["clickhouse"] == {
        "condition": "service_healthy"
    }


def test_the_conduit_is_told_where_clickhouse_is_but_not_its_password(tmp_path: Path) -> None:
    env = _env(_config(tmp_path, AnalyticsEngine.CLICKHOUSE))
    assert "OSPREY_ANALYTICS_ENGINE=clickhouse" in env
    assert "CLICKHOUSE_HOST=clickhouse" in env
    assert "CLICKHOUSE_USER=osprey" in env
    assert "PASSWORD" not in "".join(line for line in env.splitlines() if "CLICKHOUSE" in line)


def test_a_duckdb_deployment_renders_no_clickhouse(tmp_path: Path) -> None:
    config = _config(tmp_path, AnalyticsEngine.DUCKDB)
    compose = _compose(config)
    assert "clickhouse" not in compose["services"]
    assert "clickhouse" not in compose["services"]["api"]["depends_on"]
    assert not any("clickhouse" in name for name in compose["volumes"])
    assert "CLICKHOUSE" not in _env(config)


@pytest.mark.parametrize("engine", list(AnalyticsEngine))
def test_apply_mints_the_clickhouse_password_once_for_both_ends_and_only_when_used(
    tmp_path: Path, engine: AnalyticsEngine
) -> None:
    lines = analytics_secret_lines(_config(tmp_path, engine)).splitlines()
    if engine is AnalyticsEngine.DUCKDB:
        assert lines == []
        return
    values = dict(line.split("=", 1) for line in lines)
    assert set(values) == {"OSPREY_CLICKHOUSE_PASSWORD", "CLICKHOUSE_PASSWORD"}
    assert values["OSPREY_CLICKHOUSE_PASSWORD"] == values["CLICKHOUSE_PASSWORD"]
    assert len(values["CLICKHOUSE_PASSWORD"]) >= 24
    minted_again = analytics_secret_lines(_config(tmp_path, engine)).splitlines()
    again = dict(line.split("=", 1) for line in minted_again)
    assert again["CLICKHOUSE_PASSWORD"] != values["CLICKHOUSE_PASSWORD"]
