"""ADR-127 Amendment 23 (B2-10a): the dependencies of a recipe run are built in one place,
`services/api/run_resources.py`, which the Conduit's lifespan and the seed both call, so a seed's
load is judged, stamped and cached exactly as the route's. What a mistake would do, and the case
that catches it:

- the builder not hooking the stamping graph to the dataset registry, so a write names a dataset
  nobody registered (`test_the_graph_checks_every_write_against_the_datasets_store`);
- the builder not hooking the graph to the explore cache, so a seed's write leaves a stale figure
  (`test_the_graph_clears_the_explore_cache_after_a_write`);
- the run's dependencies being built from something other than what the builder opened
  (`test_the_run_dependencies_are_the_stores_the_builder_opened`);
- a resource opened and never closed (`test_closing_closes_everything_the_builder_opened`);
- the lifespan keeping a copy of the construction, so the two drift
  (`test_the_lifespan_builds_through_the_builder_and_holds_no_copy`), and that check itself failing
  for a lifespan that does (`test_the_copy_check_flags_a_lifespan_that_constructs_its_own`).

The real constructors open Postgres, Valkey, ArcadeDB and DuckDB, so the builder's own module
names are replaced with fakes that open nothing; what each fake is asked is what is asserted."""

from __future__ import annotations

import dataclasses
import inspect
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from services.api import recipe_run, run_resources
from services.api.recipe_run import RecipeRunDeps


class _Store:
    """A store that opens nothing: records its arguments and whether it was closed."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.closed = False

    @classmethod
    async def connect(cls, *args: Any, **kwargs: Any) -> Any:
        return cls(*args, **kwargs)

    async def close(self) -> None:
        self.closed = True

    async def aclose(self) -> None:
        self.closed = True

    async def create_database_if_absent(self) -> None:
        return None


class _Graph:
    def __init__(self) -> None:
        self.registry: Any = None
        self.hooks: list[Any] = []
        self.applied: Any = None

    async def apply_schema(self, ontology: Any) -> None:
        self.applied = ontology

    def check_against(self, registry: Any) -> None:
        self.registry = registry

    def after_write(self, hook: Any) -> None:
        self.hooks.append(hook)


class _Datasets(_Store):
    pass


class _Cache:
    def __init__(self, valkey: Any, *, prefix: str, ttl_seconds: int) -> None:
        self.prefix = prefix

    async def invalidate_prefix(self) -> None:
        return None


CLOSED_ANALYTICS: list[bool] = []


async def _open_analytics(engine: str, *, duckdb_path: str, handling_scheme: Any) -> Any:
    analytics = _Store()

    async def close() -> None:
        CLOSED_ANALYTICS.append(True)

    return analytics, close


SCHEME = object()
ONTOLOGY = object()
GRAPH = _Graph()
CONFIG = SimpleNamespace(
    postgres=SimpleNamespace(dsn="postgres://nowhere"),
    valkey=SimpleNamespace(client_kwargs=lambda: {}),
    analytics_engine="duckdb",
    analytics_db_path="nowhere.duckdb",
)
STORES = (
    "PatternStore",
    "HotlistStore",
    "MonitorStore",
    "AlertStore",
    "TypologyRuleStore",
    "ScreeningListStore",
    "KycExpiryStore",
    "RecipeRunStore",
    "ExtractionCandidateStore",
)


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> _Graph:
    graph = _Graph()
    CLOSED_ANALYTICS.clear()
    patched: dict[str, Any] = {
        "ArcadeDBClient": lambda config: _Store(),
        "ArcadeDBConfig": SimpleNamespace(from_env=lambda database: database),
        "GraphArcadeDBAdapter": lambda client, scheme: object(),
        "stamping": lambda inner: graph,
        "load_uk_le_scheme": lambda: SCHEME,
        "load_deployment_ontology": lambda: ONTOLOGY,
        "Valkey": lambda **kwargs: _Store(),
        "AuditWriter": _Store,
        "HeldRowStore": _Store,
        "PostgresDatasetStore": _Datasets,
        "CachedQuery": _Cache,
        "open_analytics": _open_analytics,
        "open_media_store": lambda: "media",
        "RecogniserConfig": SimpleNamespace(from_env=lambda: "recogniser-config"),
        "RecogniseStanzaAdapter": lambda config: "recogniser",
        "recogniser_for_deployment": lambda recogniser: ("recogniser_for", recogniser),
        "online_geocode_from_env": lambda: "online-geocode",
        "JobQueue": lambda valkey: _Store(),
        "PrincipalResolver": lambda config: _Store(),
    }
    for name in STORES:
        patched[name] = _Store
    for name, fake in patched.items():
        monkeypatch.setattr(run_resources, name, fake)
    return graph


async def test_the_graph_checks_every_write_against_the_datasets_store(fakes: _Graph) -> None:
    resources = await run_resources.build_run_resources(CONFIG)  # type: ignore[arg-type]
    assert fakes.registry is resources.datasets_store
    assert isinstance(fakes.registry, _Datasets)


async def test_the_graph_clears_the_explore_cache_after_a_write(fakes: _Graph) -> None:
    resources = await run_resources.build_run_resources(CONFIG)  # type: ignore[arg-type]
    assert fakes.hooks == [resources.explore_cache.invalidate_prefix]


async def test_the_schema_is_applied_for_the_ontology_in_force(fakes: _Graph) -> None:
    await run_resources.build_run_resources(CONFIG)  # type: ignore[arg-type]
    assert fakes.applied is ONTOLOGY


async def test_the_run_dependencies_are_the_stores_the_builder_opened(fakes: _Graph) -> None:
    resources = await run_resources.build_run_resources(CONFIG)  # type: ignore[arg-type]
    deps = resources.run_deps()
    assert isinstance(deps, RecipeRunDeps)
    assert deps.graph is resources.graph is fakes
    assert deps.ontology is ONTOLOGY and deps.handling_scheme is SCHEME
    assert deps.config is CONFIG
    assert deps.analytics is resources.analytics and deps.media == "media"
    assert deps.recipe_repo_root == run_resources.RECIPES_REPO_ROOT
    assert deps.recogniser_for == ("recogniser_for", "recogniser")
    assert deps.online_geocode == "online-geocode"
    for field in dataclasses.fields(RecipeRunDeps):
        assert getattr(deps, field.name) is not None or field.name == "online_geocode"
    # each of the named stores is the one the builder holds, not a second connection
    assert deps.recipe_runs is resources.recipe_runs
    assert deps.held_rows is resources.held_rows
    assert deps.typology_rules is resources.typology_rules
    assert deps.principal_resolver is resources.principal_resolver


async def test_the_builder_covers_every_field_a_run_needs(fakes: _Graph) -> None:
    resources = await run_resources.build_run_resources(CONFIG)  # type: ignore[arg-type]
    names = {f.name for f in dataclasses.fields(RecipeRunDeps)}
    assert names == set(inspect.signature(RecipeRunDeps).parameters)
    for name in names:
        source = recipe_run._RUN_DEP_STATE_NAMES.get(name, name)
        assert hasattr(resources, name) or hasattr(resources, source), name


async def test_closing_closes_everything_the_builder_opened(fakes: _Graph) -> None:
    resources = await run_resources.build_run_resources(CONFIG)  # type: ignore[arg-type]
    held = [
        resources.audit,
        resources.patterns_store,
        resources.hotlists_store,
        resources.monitors_store,
        resources.alerts_store,
        resources.typology_rules,
        resources.held_rows,
        resources.screening_lists,
        resources.kyc_expiries,
        resources.recipe_runs,
        resources.extraction_candidates,
        resources.datasets_store,
        resources.valkey,
        resources.arcadedb_client,
        resources.principal_resolver,
    ]
    assert not any(h.closed for h in held)
    await resources.close()
    assert all(h.closed for h in held)
    assert CLOSED_ANALYTICS == [True]


# --- the lifespan holds no copy ------------------------------------------------------------------

#: What only the builder may construct: a lifespan that names any of these builds its own.
CONSTRUCTED_ONLY_IN_THE_BUILDER = (
    "stamping(",
    ".check_against(",
    ".after_write(",
    "PatternStore.connect(",
    "HotlistStore.connect(",
    "MonitorStore.connect(",
    "AlertStore.connect(",
    "TypologyRuleStore.connect(",
    "HeldRowStore.connect(",
    "ScreeningListStore.connect(",
    "KycExpiryStore.connect(",
    "RecipeRunStore.connect(",
    "ExtractionCandidateStore.connect(",
    "PostgresDatasetStore.connect(",
    "AuditWriter.connect(",
    "open_analytics(",
    "open_media_store(",
    "ComputeRustworkxAdapter(",
    "JobQueue(",
    "PrincipalResolver(",
    "recogniser_for_deployment(",
    "online_geocode_from_env(",
    "ArcadeDBClient(",
    "Valkey(",
    "CachedQuery(",
    "load_deployment_ontology(",
    "RecogniseStanzaAdapter(",
)


def copies_in(source: str) -> list[str]:
    return [name for name in CONSTRUCTED_ONLY_IN_THE_BUILDER if name in source]


def test_the_lifespan_builds_through_the_builder_and_holds_no_copy() -> None:
    from services.api import app as app_module

    source = inspect.getsource(app_module.lifespan)
    assert "build_run_resources(" in source
    assert copies_in(source) == []


def test_the_lifespan_takes_the_recipe_repository_root_from_the_builder() -> None:
    """One holding of the root: the application's state reads the builder's, and the module-level
    copy in the application, which the routes' dependency also read, derives from the same value."""
    from services.api import app as app_module

    source = inspect.getsource(app_module.lifespan)
    assert "resources.recipe_repo_root" in source and "_RECIPES_REPO_ROOT" not in source
    assert app_module._RECIPES_REPO_ROOT is run_resources.RECIPES_REPO_ROOT


def test_the_builder_does_construct_each_of_them() -> None:
    source = Path(run_resources.__file__).read_text(encoding="utf-8")
    assert [name for name in CONSTRUCTED_ONLY_IN_THE_BUILDER if name not in source] == []


def test_the_copy_check_flags_a_lifespan_that_constructs_its_own() -> None:
    lifespan = (
        "async def lifespan(app):\n"
        "    graph = stamping(GraphArcadeDBAdapter(client, scheme))\n"
        "    held = await HeldRowStore.connect(dsn, scheme)\n"
    )
    assert copies_in(lifespan) == ["stamping(", "HeldRowStore.connect("]
    assert copies_in("async def lifespan(app):\n    r = await build_run_resources(config)\n") == []
