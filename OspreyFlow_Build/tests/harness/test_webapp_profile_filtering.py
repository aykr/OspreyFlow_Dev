"""`06_DECISIONS.md` ADR-049 Stage 2 §6 amendment 23: "every later screen filters its options to
what is valid here" — asserted per profile, against `harness/screens.py`, the one place this table
lives (`05_DEPLOYMENT.md` §1's own profile table, transcribed there once). `apps/harness`'s own
Components screen reads `GET /api/profile-options/{profile}` for the same values; this file proves
the table itself, not the fetch.
"""

from __future__ import annotations

import pytest
from harness.screens import PROFILE_TABLE, invalid_components_for_profile, profile_options

from schemas.deployment import AnalyticsEngine, GraphStore, Profile


@pytest.mark.parametrize(
    ("profile", "expected_graph_stores", "expected_analytics_engines"),
    [
        (Profile.LOCAL_LITE, {GraphStore.ARCADEDB}, {AnalyticsEngine.DUCKDB}),
        (
            Profile.SMALL,
            {GraphStore.ARCADEDB, GraphStore.JANUSGRAPH},
            {AnalyticsEngine.DUCKDB, AnalyticsEngine.CLICKHOUSE},
        ),
        (Profile.CLUSTER, {GraphStore.JANUSGRAPH}, {AnalyticsEngine.CLICKHOUSE}),
    ],
)
def test_each_profile_offers_exactly_05_deployment_section_1s_own_options(
    profile: Profile,
    expected_graph_stores: set[GraphStore],
    expected_analytics_engines: set[AnalyticsEngine],
) -> None:
    footprint = profile_options(profile)
    assert set(footprint.allowed_graph_stores) == expected_graph_stores
    assert set(footprint.allowed_analytics_engines) == expected_analytics_engines


@pytest.mark.parametrize("profile", list(Profile))
def test_every_profiles_own_allowed_combination_is_accepted(profile: Profile) -> None:
    footprint = PROFILE_TABLE[profile]
    for graph_store in footprint.allowed_graph_stores:
        for analytics_engine in footprint.allowed_analytics_engines:
            assert invalid_components_for_profile(profile, graph_store, analytics_engine) == []


def test_local_lite_refuses_janusgraph_and_names_the_field() -> None:
    problems = invalid_components_for_profile(
        Profile.LOCAL_LITE, GraphStore.JANUSGRAPH, AnalyticsEngine.DUCKDB
    )
    assert len(problems) == 1
    assert "graph_store" in problems[0]
    assert "local-lite" in problems[0]


def test_cluster_refuses_arcadedb_and_duckdb_together_naming_both_fields() -> None:
    problems = invalid_components_for_profile(
        Profile.CLUSTER, GraphStore.ARCADEDB, AnalyticsEngine.DUCKDB
    )
    assert len(problems) == 2
    assert any("graph_store" in p for p in problems)
    assert any("analytics_engine" in p for p in problems)


def test_small_accepts_both_of_its_own_two_graph_stores_with_either_analytics_engine() -> None:
    """`small`'s own row names a genuine choice, not a single valid combination — every
    cross-product of its two allowed values on each field must be accepted."""
    for graph_store in (GraphStore.ARCADEDB, GraphStore.JANUSGRAPH):
        for analytics_engine in (AnalyticsEngine.DUCKDB, AnalyticsEngine.CLICKHOUSE):
            problems = invalid_components_for_profile(Profile.SMALL, graph_store, analytics_engine)
            assert problems == []
