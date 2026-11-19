"""SE4 item 2 (C164): an unset deployment ceiling is the profile's own ceiling before it is the
scheme's highest (ADR-148 decision 10 and Amendment 5).

The harness gives the cloud-platform profile OFFICIAL-SENSITIVE and renders both `OSPREY_PROFILE`
and `OSPREY_HIGHEST_MARKING` into the Conduit's environment, so a rendered deployment was right. A
Conduit or script that ran without the rendered ceiling (started by hand, or a script run
directly) read "nothing set" as the scheme's highest, and a cloud-platform source got SECRET.

Planted through the environment the Conduit reads, and the backstop through the stamping graph
every Conduit write goes through. Rule 15 controls: with no profile and no ceiling nothing changes
(the scheme's highest); a ceiling that is set wins over the profile, higher or lower.
"""

from __future__ import annotations

import pytest
from services.api.dataset_scope import stamping
from services.ingest.ceiling import (
    CEILING_ENV,
    AboveTheDeploymentCeiling,
    CeilingUnknown,
    DeploymentCeiling,
)

from ontology.handling import load_uk_le_scheme
from schemas.deployment import Profile

from .test_dataset_scope import _RecordingGraph
from .test_deployment_ceiling_backstop import _edge, _node

SCHEME = load_uk_le_scheme()
HIGHEST = SCHEME.classification[-1]


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(CEILING_ENV, raising=False)
    monkeypatch.delenv("OSPREY_PROFILE", raising=False)


def _cloud_platform_without_the_rendered_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OSPREY_PROFILE", Profile.CLOUD_PLATFORM.value)


# --- The fault: the profile's own ceiling, where none is set -------------------------------------


def test_the_cloud_platform_profile_with_no_ceiling_set_is_official_sensitive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _cloud_platform_without_the_rendered_ceiling(monkeypatch)
    ceiling = DeploymentCeiling.from_env()
    assert ceiling.marking == "OFFICIAL-SENSITIVE"
    assert not ceiling.is_the_scheme_s_highest
    assert ceiling.above("SECRET")
    assert not ceiling.above("OFFICIAL-SENSITIVE")


def test_a_blank_ceiling_is_unset_too(monkeypatch: pytest.MonkeyPatch) -> None:
    _cloud_platform_without_the_rendered_ceiling(monkeypatch)
    monkeypatch.setenv(CEILING_ENV, "  ")
    assert DeploymentCeiling.from_env().marking == "OFFICIAL-SENSITIVE"


async def test_a_secret_node_is_refused_at_the_backstop_on_that_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _cloud_platform_without_the_rendered_ceiling(monkeypatch)
    inner = _RecordingGraph()
    graph = stamping(inner, dataset="fixture-corp")  # type: ignore[arg-type]
    with pytest.raises(AboveTheDeploymentCeiling) as raised:
        await graph.upsert_nodes([_node("OFFICIAL"), _node("SECRET")], tx=None)
    assert inner.nodes == [], "a node was written before the refusal"
    assert "OFFICIAL-SENSITIVE" in str(raised.value)


async def test_a_secret_link_is_refused_at_the_backstop_on_that_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _cloud_platform_without_the_rendered_ceiling(monkeypatch)
    inner = _RecordingGraph()
    graph = stamping(inner, dataset="fixture-corp")  # type: ignore[arg-type]
    with pytest.raises(AboveTheDeploymentCeiling):
        await graph.upsert_edges([_edge("SECRET")], tx=None)
    assert inner.edges == []


async def test_an_official_sensitive_write_is_taken_on_that_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _cloud_platform_without_the_rendered_ceiling(monkeypatch)
    inner = _RecordingGraph()
    graph = stamping(inner, dataset="fixture-corp")  # type: ignore[arg-type]
    await graph.upsert_nodes([_node("OFFICIAL-SENSITIVE")], tx=None)
    assert [n.id for n in inner.nodes] == ["n-OFFICIAL-SENSITIVE"]


async def test_the_backstop_follows_the_environment_it_reads_each_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The backstop reads its value once per value, not once per process: a changed environment
    is a changed ceiling."""
    inner = _RecordingGraph()
    graph = stamping(inner, dataset="fixture-corp")  # type: ignore[arg-type]
    await graph.upsert_nodes([_node("SECRET")], tx=None)  # no profile, no ceiling: the highest
    _cloud_platform_without_the_rendered_ceiling(monkeypatch)
    with pytest.raises(AboveTheDeploymentCeiling):
        await graph.upsert_nodes([_node("SECRET")], tx=None)


# --- Controls (rule 15) ---------------------------------------------------------------------------


def test_with_no_profile_and_no_ceiling_it_is_the_scheme_s_highest() -> None:
    ceiling = DeploymentCeiling.from_env()
    assert ceiling.marking == HIGHEST
    assert ceiling.is_the_scheme_s_highest


@pytest.mark.parametrize("profile", ["local-lite", "small", "cluster"])
def test_a_profile_with_no_ceiling_of_its_own_is_the_scheme_s_highest(
    monkeypatch: pytest.MonkeyPatch, profile: str
) -> None:
    monkeypatch.setenv("OSPREY_PROFILE", profile)
    assert DeploymentCeiling.from_env().marking == HIGHEST


def test_a_profile_the_harness_does_not_know_changes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OSPREY_PROFILE", "no-such-profile")
    assert DeploymentCeiling.from_env().marking == HIGHEST


async def test_with_no_profile_and_no_ceiling_a_secret_write_is_taken() -> None:
    inner = _RecordingGraph()
    graph = stamping(inner, dataset="fixture-corp")  # type: ignore[arg-type]
    await graph.upsert_nodes([_node("SECRET")], tx=None)
    assert [n.id for n in inner.nodes] == ["n-SECRET"]


@pytest.mark.parametrize("set_to", ["OFFICIAL", "OFFICIAL-SENSITIVE", "SECRET"])
def test_a_ceiling_that_is_set_wins_over_the_profile(
    monkeypatch: pytest.MonkeyPatch, set_to: str
) -> None:
    _cloud_platform_without_the_rendered_ceiling(monkeypatch)
    monkeypatch.setenv(CEILING_ENV, set_to)
    assert DeploymentCeiling.from_env().marking == set_to


async def test_a_ceiling_that_is_set_higher_than_the_profile_s_admits_a_secret_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _cloud_platform_without_the_rendered_ceiling(monkeypatch)
    monkeypatch.setenv(CEILING_ENV, "SECRET")
    inner = _RecordingGraph()
    graph = stamping(inner, dataset="fixture-corp")  # type: ignore[arg-type]
    await graph.upsert_nodes([_node("SECRET")], tx=None)
    assert [n.id for n in inner.nodes] == ["n-SECRET"]


def test_a_ceiling_the_scheme_does_not_know_is_still_refused_whatever_the_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _cloud_platform_without_the_rendered_ceiling(monkeypatch)
    monkeypatch.setenv(CEILING_ENV, "TOP-DRAWER")
    with pytest.raises(CeilingUnknown):
        DeploymentCeiling.from_env()


def test_the_profile_default_is_the_harness_s_own() -> None:
    """One source: the default the Conduit reads is the one the render writes (ADR-148 decision 10,
    Amendment 5 item 17), so the two cannot drift."""
    from harness.site import PROFILE_CEILINGS as harness_ceilings
    from services.ingest.ceiling import PROFILE_CEILINGS as conduit_ceilings

    assert conduit_ceilings is harness_ceilings
    assert conduit_ceilings[Profile.CLOUD_PLATFORM] == "OFFICIAL-SENSITIVE"
