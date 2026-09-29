"""The Profile/Components/Models screens' own server-side logic — `06_DECISIONS.md` ADR-049 Stage
2 §6, amendment 23: "every later screen filters its options to what is valid here" and
"consequences are shown, not described." Both properties are spec-derived facts about a profile
(`05_DEPLOYMENT.md` §1's own table), so they live here, once, in Python — the browser fetches them
rather than holding a second copy. `harness/webapp.py`'s own `/api/profile-options` and
`/api/consequences` routes are a thin JSON wrapper around the two functions below; nothing in
`apps/harness` hardcodes a profile's machine count, memory floor or component options.
"""

from __future__ import annotations

from dataclasses import dataclass

from schemas.deployment import AnalyticsEngine, GraphStore, ModelsConfig, OspreyConfig, Profile


@dataclass(frozen=True)
class ProfileFootprint:
    """One row of `05_DEPLOYMENT.md` §1's own table, as data rather than prose."""

    label: str
    machines: str
    memory_gb_floor: int
    orchestrator: str
    allowed_graph_stores: tuple[GraphStore, ...]
    allowed_analytics_engines: tuple[AnalyticsEngine, ...]


#: `05_DEPLOYMENT.md` §1's own table, transcribed once. `small`'s own row names two valid graph
#: stores ("ArcadeDB with Raft, or JanusGraph on a single Scylla") and two valid analytics engines
#: ("DuckDB or ClickHouse single node") — both real choices, not a range description.
PROFILE_TABLE: dict[Profile, ProfileFootprint] = {
    Profile.LOCAL_LITE: ProfileFootprint(
        label="One laptop, 16 GB",
        machines="1",
        memory_gb_floor=16,
        orchestrator="Docker Compose",
        allowed_graph_stores=(GraphStore.ARCADEDB,),
        allowed_analytics_engines=(AnalyticsEngine.DUCKDB,),
    ),
    Profile.SMALL: ProfileFootprint(
        label="3 machines",
        machines="3",
        memory_gb_floor=16,
        orchestrator="Docker Compose across hosts, or a small Kubernetes",
        allowed_graph_stores=(GraphStore.ARCADEDB, GraphStore.JANUSGRAPH),
        allowed_analytics_engines=(AnalyticsEngine.DUCKDB, AnalyticsEngine.CLICKHOUSE),
    ),
    Profile.CLUSTER: ProfileFootprint(
        label="10+ machines",
        machines="10+",
        memory_gb_floor=16,
        orchestrator="Kubernetes",
        allowed_graph_stores=(GraphStore.JANUSGRAPH,),
        allowed_analytics_engines=(AnalyticsEngine.CLICKHOUSE,),
    ),
}


def profile_options(profile: Profile) -> ProfileFootprint:
    """§2.1's "every later screen filters its options to what is valid here" — the Components
    screen's own filter, as a lookup rather than a branch duplicated per screen."""
    return PROFILE_TABLE[profile]


def invalid_components_for_profile(
    profile: Profile, graph_store: GraphStore, analytics_engine: AnalyticsEngine
) -> list[str]:
    """The Components screen's own validation, called both by `/api/config` (a submitted answer
    the schema itself cannot reject, since `ComponentsConfig` has no `profile` field to check
    against) and by the option-filtering test amendment 23 asks for. Returns messages, not a bare
    bool, so a refusal names which field and why — the same "shown next to the field" requirement
    the round's own brief states for schema validation errors."""
    footprint = PROFILE_TABLE[profile]
    problems: list[str] = []
    if graph_store not in footprint.allowed_graph_stores:
        allowed = ", ".join(g.value for g in footprint.allowed_graph_stores)
        problems.append(
            f"components.graph_store {graph_store.value!r} is not valid at profile "
            f"{profile.value!r} — allowed: {allowed}"
        )
    if analytics_engine not in footprint.allowed_analytics_engines:
        allowed = ", ".join(a.value for a in footprint.allowed_analytics_engines)
        problems.append(
            f"components.analytics_engine {analytics_engine.value!r} is not valid at profile "
            f"{profile.value!r} — allowed: {allowed}"
        )
    return problems


@dataclass(frozen=True)
class Consequences:
    """§2.1's "consequences are shown, not described" — the Profile screen's machine
    count/components/memory footprint, and the Models screen's egress exception, computed from
    the config an operator has entered so far rather than asserted in prose next to the control."""

    profile: Profile
    machines: str
    memory_gb_floor: int
    orchestrator: str
    graph_store: GraphStore
    analytics_engine: AnalyticsEngine
    egress_exception: bool
    egress_detail: str | None


def consequences_for(config: OspreyConfig) -> Consequences:
    footprint = PROFILE_TABLE[config.profile]
    egress_exception, egress_detail = _egress_consequence(config.models)
    return Consequences(
        profile=config.profile,
        machines=footprint.machines,
        memory_gb_floor=footprint.memory_gb_floor,
        orchestrator=footprint.orchestrator,
        graph_store=config.components.graph_store,
        analytics_engine=config.components.analytics_engine,
        egress_exception=egress_exception,
        egress_detail=egress_detail,
    )


def _egress_consequence(models: ModelsConfig) -> tuple[bool, str | None]:
    """`04_VAULT_BACKEND.md` §4's egress exception, described rather than applied — this module
    never touches `services/` or `adapters/`; it only states, for the screen, what a hosted
    fallback would mean. `ModelsConfig`'s own validator already refuses an inconsistent answer
    (a `hosted_fallback` with no codes, or codes with no fallback), so by the time a config reaches
    here the two fields already agree."""
    if models.local_only or models.hosted_fallback is None:
        return False, None
    codes = ", ".join(models.sendable_handling_codes) if models.sendable_handling_codes else "none"
    return (
        True,
        f"queries carrying handling code(s) [{codes}] may leave this deployment for "
        f"{models.hosted_fallback!r}",
    )


#: Re-exported for `harness/webapp.py`'s own dataclass -> dict conversion, and for tests that want
#: the field name without importing `dataclasses` themselves.
__all__ = [
    "Consequences",
    "ProfileFootprint",
    "consequences_for",
    "invalid_components_for_profile",
    "profile_options",
    "PROFILE_TABLE",
]
