"""The deployment's monitoring settings (`spec/06_DECISIONS.md` ADR-133 ruling 3):
`monitoring.hotlist_audience` (`only_me` by default, or `team`) and
`monitoring.hotlist_audience_editable` (true by default), from `osprey.yaml` through the rendered
`deployment.env` to the Conduit — which reads anything it does not recognise as the narrower choice
(fail closed: `only_me`, and an unreadable "editable" as not editable). An existing hotlist keeps
`only_me` when the column arrives (`test_a_hotlist_made_before_the_setting_keeps_only_me`), which
needs real Postgres (`make dev-up`, or a throwaway one)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import asyncpg
import pytest
from harness.render import _render_env
from pydantic import ValidationError
from services.api.config import MonitoringSettings, PostgresConfig
from services.api.hotlists import HotlistStore

from conduit_common.identity import new_id
from schemas.deployment import OspreyConfig


def test_the_defaults_are_only_me_and_editable() -> None:
    config = OspreyConfig()
    assert config.monitoring.hotlist_audience == "only_me"
    assert config.monitoring.hotlist_audience_editable is True


def test_an_audience_outside_the_two_is_refused_at_validation() -> None:
    with pytest.raises(ValidationError):
        OspreyConfig.model_validate({"monitoring": {"hotlist_audience": "everyone"}})


def test_the_settings_are_rendered_for_the_conduit() -> None:
    env = _render_env(OspreyConfig())
    assert "OSPREY_HOTLIST_AUDIENCE=only_me\n" in env
    assert "OSPREY_HOTLIST_AUDIENCE_EDITABLE=true\n" in env
    chosen = OspreyConfig.model_validate(
        {"monitoring": {"hotlist_audience": "team", "hotlist_audience_editable": False}}
    )
    env = _render_env(chosen)
    assert "OSPREY_HOTLIST_AUDIENCE=team\n" in env
    assert "OSPREY_HOTLIST_AUDIENCE_EDITABLE=false\n" in env


@pytest.mark.parametrize(
    ("audience", "editable", "expected"),
    [
        (None, None, ("only_me", True)),
        ("team", "true", ("team", True)),
        ("team", "false", ("team", False)),
        ("Team ", "yes", ("only_me", False)),  # neither exactly recognised: the narrower choice
        ("", "", ("only_me", False)),
    ],
)
def test_the_conduit_reads_the_settings_failing_closed(
    monkeypatch: pytest.MonkeyPatch, audience: str | None, editable: str | None,
    expected: tuple[str, bool],
) -> None:  # fmt: skip
    for name, value in (("OSPREY_HOTLIST_AUDIENCE", audience),
                        ("OSPREY_HOTLIST_AUDIENCE_EDITABLE", editable)):  # fmt: skip
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    settings = MonitoringSettings.from_env()
    assert (settings.hotlist_audience, settings.hotlist_audience_editable) == expected


async def test_a_hotlist_made_before_the_setting_keeps_only_me() -> None:
    """A database whose `hotlists` table predates ADR-133 (no `audience` column) gains it when the
    store connects, and its rows read `only_me`. Run in a schema of its own, so the shared test
    database's table is untouched."""
    schema = f"before_{new_id().lower()}"
    dsn = PostgresConfig.from_env().dsn
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(f"CREATE SCHEMA {schema}")
        await conn.execute(
            f"CREATE TABLE {schema}.hotlists (id TEXT PRIMARY KEY, identifier TEXT NOT NULL, "
            "owner_id TEXT NOT NULL, review_date DATE NOT NULL, "
            "status TEXT NOT NULL DEFAULT 'active', created_at TIMESTAMPTZ NOT NULL)"
        )
        await conn.execute(
            f"INSERT INTO {schema}.hotlists VALUES ('h-old', '+447700900310', 'owner-1', $1, "
            "'active', $2)",
            date(2027, 1, 1),
            datetime.now(UTC),
        )
        store = await HotlistStore.connect(f"{dsn}?search_path={schema}")
        try:
            (old,) = await store.list_all_active()
            assert old.id == "h-old" and old.audience == "only_me"
        finally:
            await store.close()
    finally:
        await conn.execute(f"DROP SCHEMA {schema} CASCADE")
        await conn.close()
