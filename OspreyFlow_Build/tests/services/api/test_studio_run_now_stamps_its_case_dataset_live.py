"""Part A2, through *Run now*: the route's own scoping (`get_principal`, `scope_to_case`) stamps a
Studio load with its case's dataset and confines the loader to it (ADR-099 decisions 2–4,
ADR-102 Amendment 3).

`test_studio_load_stamps_its_case_dataset_live.py` drives the scheduler's `check_case`; this file
drives `POST /v1/investigations/{case}/ingest/recipes/{recipe}/run` through the ASGI app in process
(httpx's `ASGITransport`, on the test's own event loop, which the real stores' pools belong to).
The route runs with the real `get_principal`, the real case and dataset stores in Postgres, and the
Conduit's stamping graph over real ArcadeDB. The loader's answer and what they read are the same
whether or not another case, reading another dataset, loaded the same pair first. Red with
`scope_to_case` taken out of `get_principal`, and with its stamp kept but its confinement dropped.

Every stand-in, so the claim is no wider than the test:
- the token resolver (`_Accounts`) maps a bearer token to its account: identity is not under test,
  what `get_principal` does with it is;
- the recipe store (`_Recipes`) grants the one published draft to any principal;
- the app's state (`_Held`) answers every name it is not given with a store holding nothing;
- `_execute_recipe_run` is replaced by `run_published_recipe` over `deps.graph`, as in the other two
  live files, so the rule gate, `run_published_pipeline` and the change stream are not driven;
- `resolve_source_handling` is patched to the source's marking.
So the stamping and the confinement are proven up to the recipe run (ADR-110 Amendment 17). Driving
the real `_execute_recipe_run` is carried to Part C (`process/lanes/studio/L1.2a_RED_RECORD.md`)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import services.api.recipe_run as run_module
from adapters.graph_arcadedb.testing import arcadedb_adapter
from adapters.media_objectstore.testing import InMemoryMediaStore
from conduit_common.identity import new_id
from schemas.domain import Principal
from services.api.app import app
from services.api.dataset_scope import scope_to_case
from services.api.studio_publish import run_published_recipe
from starlette.datastructures import State

from tests.ingest.recipe_test_support import local_staging  # noqa: F401 (the autouse fixture)
from tests.ingest.test_row_keys import ONTOLOGY, SCHEME
from tests.services.api.test_snapshot_withdrawal_tells_nothing_live import (
    SOURCE,
    _write,
)
from tests.services.api.test_studio_load_stamps_its_case_dataset_live import (
    PAIR,
    World,
    _case,
    _conduits_graph,
    _dataset,
    fresh_published_draft,
    stores,  # noqa: F401 (the fixture)
)


class _Accounts:
    """Stands in for `PrincipalResolver`: a bearer token is the account's own id."""

    def __init__(self) -> None:
        self.by_token: dict[str, Principal] = {}

    def resolve(self, token: str) -> Principal:
        return self.by_token[token]


class _Recipes:
    """Stands in for the recipe store: the one published draft, for any reader in its unit."""

    def __init__(self, draft: Any) -> None:
        self.draft = draft

    async def get_authorized(self, recipe_id: str, principal: Principal) -> Any:
        return self.draft

    async def verified_sources(self, recipe_id: str, version: int) -> None:
        return None


class _Nothing:
    async def record(self, *_: Any, **__: Any) -> None:
        return None

    #: The store methods whose real answer is one record or none, never a list (rule 15: a fake
    #: answers as the real store does): `TargetModelStore.live` and `draft` (read since L3.1b by
    #: `target_models.packs_of_case` on every run), and the rule store's `load_checks`.
    _ONE_OR_NONE = frozenset({"load_checks", "live", "draft"})

    def __getattr__(self, name: str) -> Any:
        async def nothing(*_: Any, **__: Any) -> list[Any] | None:
            return None if name in self._ONE_OR_NONE else []

        return nothing


class _Held(State):
    """The app's state for one test: the stores given, and a store holding nothing for any other
    name the route only passes along (the load itself is `run_published_recipe`)."""

    def __getattr__(self, name: str) -> Any:
        try:
            return super().__getattr__(name)
        except AttributeError:
            return _Nothing()


@pytest.fixture
def routed(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    held = app.state
    yield
    app.state = held
    app.dependency_overrides.clear()


def _loader(name: str) -> Principal:
    return Principal(
        id=f"{name}-{new_id()}", clearance="SECRET", org_unit="unit-1", roles=["loader"]
    )


async def _run_now(
    world: World,
    client: httpx.AsyncClient,
    accounts: _Accounts,
    who: Principal,
    case: str,
) -> dict[str, Any]:
    accounts.by_token[who.id] = who
    response = await client.post(
        f"/v1/investigations/{case}/ingest/recipes/{world.draft.recipe_id}/run",
        headers={"Authorization": f"Bearer {who.id}"},
        json={},
    )
    assert response.status_code == 200, response.text
    said = {
        k: v for k, v in response.json().items() if k not in {"load_id", "recipe_id"}
    }
    if said.get("metering"):
        said["metering"].pop("wall_ms", None)
    return said


async def _told(
    stores: SimpleNamespace,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    beside: bool,
) -> dict[str, Any]:
    repo, draft = fresh_published_draft(tmp_path / ("beside" if beside else "alone"))
    _write(Path(draft.source_location), [PAIR])
    loader, other = _loader("loader"), _loader("other")
    ours = await _case(stores, loader, await _dataset(stores, loader))
    theirs = await _case(stores, other, await _dataset(stores, other))

    async def execute(deps: Any, **kwargs: Any) -> Any:
        return await run_published_recipe(
            draft, kwargs["principal"], graph=deps.graph, ontology=ONTOLOGY, load_id=new_id(),
            investigation_scope=kwargs["investigation_id"], repo_root=repo, analytics=None,
            media=kwargs["media"], scheme=SCHEME, sink=kwargs["sink"],
        )  # fmt: skip

    monkeypatch.setattr(run_module, "_execute_recipe_run", execute)
    monkeypatch.setattr(run_module, "resolve_source_handling", lambda d: SOURCE)
    monkeypatch.setattr("services.api.app.resolve_source_handling", lambda d: SOURCE)
    accounts = _Accounts()
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as raw:
        graph = await _conduits_graph(raw, stores)
        state = _Held()
        state.graph = graph
        state.investigations = stores.cases
        state.datasets = stores.datasets
        state.recipe_runs = stores.runs
        state.studio_recipes = _Recipes(draft)
        state.principal_resolver = accounts
        state.handling_scheme = SCHEME
        state.ontology = ONTOLOGY
        state.recipes_repo_root = repo
        state.media = InMemoryMediaStore()
        state.audit = _Nothing()
        state.run_quotas = None  # no quota set (ADR-141 decision 6): the run is not judged
        app.state = state
        # No lifespan: the state above is the app's.
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://conduit"
        ) as client:
            world = World(stores, graph, repo, draft, monkeypatch)
            if beside:
                await _run_now(world, client, accounts, other, theirs)
            said = await _run_now(world, client, accounts, loader, ours)
        read = await world.reads(await scope_to_case(loader, ours, stores.datasets))
    return {"said": said, "read": read}


async def test_run_now_tells_and_shows_its_case_the_same_whatever_another_dataset_holds(
    stores: SimpleNamespace,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    routed: None,
) -> None:
    alone = await _told(stores, tmp_path, monkeypatch, beside=False)
    beside = await _told(stores, tmp_path, monkeypatch, beside=True)

    assert alone["read"] == {
        "nodes": ["SYN-1", "SYN-2"],
        "links": [("TRANSACTED", "SYN-1", "SYN-2", 1)],
    }, "the loader reads what it loaded"
    assert beside["said"] == alone["said"], "what Run now answers its loader"
    assert beside["read"] == alone["read"], "what the loader reads"
