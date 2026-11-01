"""ADR-136: egress decided per dataset as well as by handling code, and keys marked as under a
privacy contract.

Material is sent to a hosted engine only when its handling code is sendable **and** every dataset
it comes from allows that engine: `none` (the default) never, `contracted` only a provider marked
`privacy_contract: true`, `any` any enabled provider. Datasets not known are `none`, so nothing
leaves by omission.

The requests here reach the **stand-in gateway** of `test_model_engines.py`, built from the model
table the renderer writes and the keys the gateway's own environment holds. It refuses what the real
LiteLLM proxy refuses (`CLAUDE.md` rule 15), shown there by `test_the_stand_in_gateway_refuses_as_
the_real_one_does` and again here for this file's own table; "not sent" means it recorded no call
for the hosted model at all.

What a mistake would do, and the case that catches it (rule 12):
- a dataset left at `none` sent anyway — `test_a_dataset_set_to_none_is_not_sent_to_gemini`;
- `contracted` honoured for a provider with no contract —
  `test_contracted_and_a_provider_without_a_contract_is_not_sent`;
- `contracted` never honoured (so the setting is meaningless) —
  `test_contracted_and_a_provider_with_a_contract_is_sent`;
- material whose datasets are not known sent — `test_a_request_with_no_datasets_known_is_not_sent`;
- one permissive dataset letting another's material out —
  `test_material_from_two_datasets_one_any_one_none_is_not_sent`;
- the store's default not `none`, or an existing row not read as `none` —
  `test_a_dataset_is_none_until_an_administrator_changes_it`;
- anyone but an administrator setting egress, or the change unaudited (rule 4) — the
  `test_setting_egress_*` cases;
- the engine choice offering an engine the case's data may not reach, or not saying why —
  `test_the_case_engines_route_disables_an_engine_the_cases_data_may_not_reach_and_says_why`;
- the contract mark lost between `osprey.yaml` and the Conduit, or a reference carrying a secret —
  `test_the_conduit_reads_the_contract_mark_the_renderer_wrote`,
  `test_a_contract_reference_that_looks_like_a_key_is_refused`.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from harness.render import model_engines_env, render_litellm_config
from pydantic import ValidationError
from services.api.app import (
    app,
    get_audit,
    get_datasets,
    get_investigations,
    get_model_routes,
    get_principal,
)
from services.api.config import DeploymentModels
from services.api.datasets import Dataset, InMemoryDatasetStore
from services.api.investigations import AccessLevel, Investigation, InvestigationNotFoundError
from services.api.model_routing import (
    ModelEgressRefused,
    ModelRoutes,
    RoutedModel,
    model_status,
    routes_from_env,
)
from tools.layout import CORE

from schemas.deployment import ModelProviderConfig, ModelsConfig, OspreyConfig
from schemas.domain import Handling, Principal
from schemas.model import ExtractionRequest
from tests.harness.test_render import FIXTURE_CONFIG
from tests.services.api.test_model_engines import GatewayRefused, StandInGateway

LOCAL = "qwen2.5:7b-instruct"
GEMINI = "gemini/gemini-2.5-flash"
CLAUDE = "anthropic/claude-sonnet-4"
GEMINI_KEY = "AIza-gemini-NEVER-IN-AN-ANSWER"
ANTHROPIC_KEY = "sk-ant-NEVER-IN-AN-ANSWER"

MODELS = ModelsConfig.model_validate(
    {
        "local_only": False,
        "sendable_handling_codes": ["P"],
        "providers": [
            # No contract: the default, and the owner's Gemini key (ADR-136 decision 4).
            {"name": "gemini", "roles": {"extraction": "gemini-2.5-flash"}},
            {"name": "anthropic", "label": "Claude", "roles": {"extraction": "claude-sonnet-4"},
             "privacy_contract": True, "contract_reference": "DPA 2026/07 with Anthropic"},
        ],
        "defaults": {"extraction": "gemini"},
    }
)  # fmt: skip
GATEWAY_ENV = {"OSPREY_MODEL_KEY_GEMINI": GEMINI_KEY, "OSPREY_MODEL_KEY_ANTHROPIC": ANTHROPIC_KEY}
PROVIDERS_ACCEPT = {"gemini": GEMINI_KEY, "anthropic": ANTHROPIC_KEY}


def _config() -> OspreyConfig:
    loaded = OspreyConfig.model_validate(yaml.safe_load(FIXTURE_CONFIG))
    return loaded.model_copy(
        update={
            "models": MODELS,
            "components": loaded.components.model_copy(update={"source_path": str(CORE)}),
        }
    )


def _routes(extraction: str | None = LOCAL) -> ModelRoutes:
    """What the Conduit reads, from the lines the renderer wrote and each key's presence."""
    env = dict(line.split("=", 1) for line in model_engines_env(_config()))
    for provider in MODELS.enabled_providers:
        env[f"OSPREY_MODEL_KEY_PRESENT_{provider.name.upper()}"] = "yes"
    locals_ = DeploymentModels(extraction=extraction or "", vision="moondream",
                               transcription="whisper", embedding="minilm")  # fmt: skip
    routes = routes_from_env(locals_, env)
    if extraction is None:
        routes = ModelRoutes(locals={**routes.locals, "extraction": None}, engines=routes.engines,
                             defaults=routes.defaults, sendable=routes.sendable)  # fmt: skip
    return routes


def _gateway() -> StandInGateway:
    table = dict(yaml.safe_load(render_litellm_config(_config())))
    return StandInGateway(table, GATEWAY_ENV, PROVIDERS_ACCEPT)


def _dataset(id_: str, egress: str, unit: str = "unit-1") -> Dataset:
    return Dataset(id=id_, name=id_.replace("-", " ").title(), owning_unit=unit,
                   created_at=datetime(2026, 11, 1, tzinfo=UTC), created_by="seed",
                   egress=egress)  # type: ignore[arg-type]  # fmt: skip


def _store(*datasets: Dataset) -> InMemoryDatasetStore:
    store = InMemoryDatasetStore()
    for dataset in datasets:
        store.add(dataset)
    return store


STORE = _store(
    _dataset("kept-in", "none"),
    _dataset("contract-only", "contracted"),
    _dataset("synthetic", "any"),
)


def _handling(code: str = "P") -> Handling:
    return Handling(classification="OFFICIAL", handling_code=code, owning_unit="u", originator="u")


def _ask(engine: str | None, datasets: Sequence[str] | None) -> ExtractionRequest:
    return ExtractionRequest(document_id="q", text="t", json_schema={}, model=LOCAL,
                             handling=_handling("P"), engine=engine,
                             datasets=None if datasets is None else list(datasets))  # fmt: skip


def _routed(gateway: StandInGateway, extraction: str | None = LOCAL) -> RoutedModel:
    return RoutedModel(gateway, routes=_routes(extraction), egress=STORE)  # type: ignore[arg-type]


# --- the stand-in, shown to refuse for this table first (rule 15) --------------------------------


async def test_the_stand_in_gateway_refuses_for_this_table_as_the_real_one_does() -> None:
    gateway = _gateway()
    for model in ("gemini/gemini-9", "mistral/large"):  # a model, a provider, not in its table
        with pytest.raises(GatewayRefused, match="Invalid model name"):
            await gateway.extract(_ask(None, None).model_copy(update={"model": model}))
    wrong = StandInGateway(dict(yaml.safe_load(render_litellm_config(_config()))),
                           {"OSPREY_MODEL_KEY_GEMINI": "AIza-wrong"}, PROVIDERS_ACCEPT)  # fmt: skip
    with pytest.raises(GatewayRefused, match="not valid"):
        await wrong.extract(_ask(None, None).model_copy(update={"model": GEMINI}))
    with pytest.raises(GatewayRefused, match="no API key"):
        await wrong.extract(_ask(None, None).model_copy(update={"model": CLAUDE}))
    assert (await gateway.extract(_ask(None, None).model_copy(update={"model": GEMINI}))).model == (
        GEMINI
    )


# --- routing ------------------------------------------------------------------------------------


async def test_a_dataset_set_to_any_is_sent_where_named() -> None:
    """The positive control: without it, every "not sent" below could be a routing that never
    sends anything."""
    gateway = _gateway()
    result = await _routed(gateway).extract(_ask("gemini", ["synthetic"]))
    assert gateway.asked == [GEMINI]
    assert (result.engine, result.model) == ("gemini", GEMINI)
    # And on the role's default, with no engine named.
    await _routed(gateway).extract(_ask(None, ["synthetic"]))
    assert gateway.asked == [GEMINI, GEMINI]


async def test_a_dataset_set_to_none_is_not_sent_to_gemini() -> None:
    gateway = _gateway()
    result = await _routed(gateway).extract(_ask("gemini", ["kept-in"]))
    assert not [m for m in gateway.asked if m == GEMINI]
    assert gateway.asked == [LOCAL]
    assert (result.engine, result.model) == ("local", LOCAL)
    # Nor on the role's default.
    await _routed(gateway).extract(_ask(None, ["kept-in"]))
    assert gateway.asked == [LOCAL, LOCAL]


async def test_contracted_and_a_provider_without_a_contract_is_not_sent() -> None:
    gateway = _gateway()
    result = await _routed(gateway).extract(_ask("gemini", ["contract-only"]))
    assert gateway.asked == [LOCAL] and result.engine == "local"


async def test_contracted_and_a_provider_with_a_contract_is_sent() -> None:
    gateway = _gateway()
    result = await _routed(gateway).extract(_ask("anthropic", ["contract-only"]))
    assert gateway.asked == [CLAUDE]
    assert (result.engine, result.model) == ("anthropic", CLAUDE)


async def test_a_request_with_no_datasets_known_is_not_sent() -> None:
    gateway = _gateway()
    for datasets in (None, [], ["no-such-dataset"]):
        result = await _routed(gateway).extract(_ask("gemini", datasets))
        assert result.engine == "local", datasets
    assert gateway.asked == [LOCAL, LOCAL, LOCAL]
    # And a router given no way to read egress at all sends nothing either.
    bare = RoutedModel(gateway, routes=_routes())  # type: ignore[arg-type]
    await bare.extract(_ask("gemini", ["synthetic"]))
    assert gateway.asked == [LOCAL] * 4


async def test_material_from_two_datasets_one_any_one_none_is_not_sent() -> None:
    gateway = _gateway()
    for order in (["synthetic", "kept-in"], ["kept-in", "synthetic"]):
        result = await _routed(gateway).extract(_ask("gemini", order))
        assert result.engine == "local"
    assert gateway.asked == [LOCAL, LOCAL]


async def test_with_no_local_model_a_dataset_that_may_not_leave_is_refused_in_words() -> None:
    gateway = _gateway()
    with pytest.raises(ModelEgressRefused, match="Kept In") as refused:
        await _routed(gateway, extraction=None).extract(_ask("gemini", ["kept-in"]))
    assert "none" in str(refused.value) and "Gemini" in str(refused.value)
    with pytest.raises(ModelEgressRefused, match="privacy contract"):
        await _routed(gateway, extraction=None).extract(_ask("gemini", ["contract-only"]))
    with pytest.raises(ModelEgressRefused, match="not known"):
        await _routed(gateway, extraction=None).extract(_ask("gemini", None))
    assert gateway.asked == []


async def test_handling_is_still_checked_whatever_the_dataset_allows() -> None:
    """ADR-136 adds a condition; it removes none. `any` does not let unsendable material out."""
    gateway = _gateway()
    request = _ask("gemini", ["synthetic"]).model_copy(update={"handling": _handling("C")})
    result = await _routed(gateway).extract(request)
    assert gateway.asked == [LOCAL] and result.engine == "local"


# --- the contract mark ---------------------------------------------------------------------------


def test_a_provider_is_not_under_contract_unless_marked() -> None:
    plain = ModelProviderConfig.model_validate({"name": "gemini", "roles": {"extraction": "g"}})
    assert plain.privacy_contract is False and plain.contract_reference is None


def test_a_contract_reference_that_looks_like_a_key_is_refused() -> None:
    secrets = (
        "sk-ant-api03-abcdefghijklmnop",
        "AIzaSyD4f9-abcdefghijklmnopqrstu",
        "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
        "DPA\n2026",
        "DPA $HOME #7",
    )
    marked = {"name": "gemini", "roles": {"extraction": "g"}, "privacy_contract": True}
    for secret in secrets:
        with pytest.raises(ValidationError, match="reference"):
            ModelProviderConfig.model_validate({**marked, "contract_reference": secret})
    kept = ModelProviderConfig.model_validate(
        {**marked, "contract_reference": "  DPA-2026-0001, signed 3 March  "}
    )
    assert kept.contract_reference == "DPA-2026-0001, signed 3 March"


def test_the_conduit_reads_the_contract_mark_the_renderer_wrote() -> None:
    routes = _routes()
    assert {n: (e.privacy_contract, e.contract_reference) for n, e in routes.engines.items()} == {
        "gemini": (False, None),
        "anthropic": (True, "DPA 2026/07 with Anthropic"),
    }
    rendered = "\n".join(model_engines_env(_config()))
    assert GEMINI_KEY not in rendered and ANTHROPIC_KEY not in rendered


def test_the_status_shows_the_contract_mark_and_never_a_key() -> None:
    _, engines, notice = model_status(_routes())
    marks = {e.name: (e.privacy_contract, e.contract_reference) for e in engines}
    assert marks == {"local": (False, None), "gemini": (False, None),
                     "anthropic": (True, "DPA 2026/07 with Anthropic")}  # fmt: skip
    assert notice is not None and "egress" in notice
    for text in (repr(engines), notice):
        assert GEMINI_KEY not in text and ANTHROPIC_KEY not in text


# --- the store -----------------------------------------------------------------------------------


async def test_a_dataset_is_none_until_an_administrator_changes_it() -> None:
    store = InMemoryDatasetStore()
    made = await store.create(Principal(id="a", clearance="OFFICIAL", org_unit="unit-1"), "Mine")
    assert made.egress == "none"
    seed = Dataset(id="seed", name="Seed", owning_unit="unit-1", created_at=datetime.now(UTC),
                   created_by="seed")  # fmt: skip
    registered = await store.register(seed)
    assert registered.egress == "none"
    before, after = await store.set_egress("seed", "any")
    assert (before, after.egress) == ("none", "any")
    assert {d.id: d.egress for d in await store.list_all()} == {made.id: "none", "seed": "any"}
    assert (await store.egress_of(["seed", "nobody"])).keys() == {"seed"}


# --- the routes ----------------------------------------------------------------------------------

ADMIN = Principal(id="admin-1", clearance="OFFICIAL", org_unit="unit-1", roles=["osprey-admin"])
ANALYST = Principal(id="analyst-1", clearance="SECRET", org_unit="unit-1", roles=["analyst"])
OUTSIDER = Principal(id="outsider-1", clearance="SECRET", org_unit="unit-1", roles=["analyst"])


class _Audit:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> None:
        self.records.append(kwargs)


class _Cases:
    """The analyst is a Viewer of `case-1`; the outsider holds nothing, and is told the case is
    not there, as the real store tells them (`InvestigationNotFoundError`, a 404)."""

    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: AccessLevel
    ) -> Investigation:
        if investigation_id != "case-1" or principal.id != ANALYST.id:
            raise InvestigationNotFoundError(investigation_id)
        return Investigation(id="case-1", name="Case", created_at=datetime.now(UTC),
                             created_by="analyst-1", owning_unit="unit-1")  # fmt: skip


@pytest.fixture
def client() -> Any:
    store = _store(_dataset("kept-in", "none"), _dataset("contract-only", "contracted"),
                   _dataset("synthetic", "any"))  # fmt: skip
    audit = _Audit()
    app.dependency_overrides[get_datasets] = lambda: store
    app.dependency_overrides[get_audit] = lambda: audit
    app.dependency_overrides[get_investigations] = _Cases
    app.dependency_overrides[get_model_routes] = _routes
    test_client = TestClient(app)
    test_client.store, test_client.audit = store, audit  # type: ignore[attr-defined]
    yield test_client
    app.dependency_overrides.clear()


def _as(who: Principal | None) -> None:
    if who is None:
        app.dependency_overrides.pop(get_principal, None)
    else:
        app.dependency_overrides[get_principal] = lambda: who


def test_setting_egress_is_an_administrators_and_is_audited(client: Any) -> None:
    _as(ADMIN)
    listed = client.get("/v1/admin/datasets")
    assert listed.status_code == 200, listed.text
    assert {d["id"]: d["egress"] for d in listed.json()} == {
        "kept-in": "none", "contract-only": "contracted", "synthetic": "any",
    }  # fmt: skip
    changed = client.put("/v1/admin/datasets/kept-in/egress", json={"egress": "contracted"})
    assert changed.status_code == 200, changed.text
    assert changed.json()["egress"] == "contracted"
    (record,) = client.audit.records
    assert record["action"] == "set_dataset_egress"
    assert record["principal"].id == "admin-1"  # who; the audit writer stamps when
    assert record["resolved_query"] == {"dataset_id": "kept-in", "before": "none",
                                        "after": "contracted"}  # fmt: skip


@pytest.mark.parametrize("who", [ANALYST, None], ids=["analyst", "no-sign-in"])
def test_setting_egress_is_refused_to_anyone_else(client: Any, who: Principal | None) -> None:
    _as(who)
    expected = 403 if who is not None else 401
    assert client.get("/v1/admin/datasets").status_code == expected
    put = client.put("/v1/admin/datasets/kept-in/egress", json={"egress": "any"})
    assert put.status_code == expected
    assert client.store.datasets["kept-in"].egress == "none"
    assert client.audit.records == []


def test_setting_egress_refuses_an_unknown_dataset_and_an_unknown_setting(client: Any) -> None:
    _as(ADMIN)
    assert client.put("/v1/admin/datasets/nobody/egress", json={"egress": "any"}).status_code == 404
    bad = client.put("/v1/admin/datasets/kept-in/egress", json={"egress": "everywhere"})
    assert bad.status_code == 422
    assert client.audit.records == []


def _case_engines(client: Any, datasets: list[str]) -> dict[str, dict[str, Any]]:
    client.store.cases["case-1"] = datasets
    response = client.get("/v1/investigations/case-1/models/engines")
    assert response.status_code == 200, response.text
    return {e["name"]: e for e in response.json()["engines"]}


def test_the_case_engines_route_disables_an_engine_the_cases_data_may_not_reach_and_says_why(
    client: Any,
) -> None:
    _as(ANALYST)
    everything = _case_engines(client, ["synthetic"])
    assert [(n, e["available"]) for n, e in everything.items()] == [
        ("local", True), ("gemini", True), ("anthropic", True),
    ]  # fmt: skip
    marks = {name: engine["privacy_contract"] for name, engine in everything.items()}
    assert marks == {"local": False, "gemini": False, "anthropic": True}

    contracted = _case_engines(client, ["synthetic", "contract-only"])
    assert contracted["anthropic"]["available"] is True
    assert contracted["gemini"]["available"] is False
    assert "Contract Only" in contracted["gemini"]["reason"]
    assert "privacy contract" in contracted["gemini"]["reason"]

    kept = _case_engines(client, ["kept-in", "synthetic"])
    assert kept["local"]["available"] is True and kept["local"]["reason"] is None
    for name in ("gemini", "anthropic"):
        assert kept[name]["available"] is False
        assert "Kept In" in kept[name]["reason"] and "none" in kept[name]["reason"]
    for engine in kept.values():
        assert "key" not in repr(engine).lower()


@pytest.mark.parametrize("who", [OUTSIDER, None], ids=["not-on-the-case", "no-sign-in"])
def test_the_case_engines_route_is_refused_to_anyone_who_cannot_open_the_case(
    client: Any, who: Principal | None
) -> None:
    _as(who)
    client.store.cases["case-1"] = ["kept-in"]
    response = client.get("/v1/investigations/case-1/models/engines")
    assert response.status_code == (404 if who is not None else 401)
    assert "Kept In" not in response.text


# --- the callers name their datasets -------------------------------------------------------------


class _Candidates:
    """`run_extraction`'s store, holding nothing: what matters here is the request the model got."""

    async def store_document_text(self, *args: Any) -> None:
        return None

    async def store(self, candidates: Any, principal: Principal) -> list[Any]:
        return []


async def test_an_extraction_names_its_datasets_and_one_left_at_none_stays_local() -> None:
    """`review.run_extraction` (the extraction route, a Document, an email) carries the datasets it
    is given onto every window's request, so the routing can refuse them."""
    from services.api.review import run_extraction
    from services.extract.profile import ExtractionProfile

    from ontology.loader import load_default_ontology

    gateway = _gateway()
    routed = _routed(gateway)
    for datasets, reached in ((["kept-in"], LOCAL), (["synthetic"], GEMINI), (None, LOCAL)):
        await run_extraction(
            routed, load_default_ontology(), _Candidates(),  # type: ignore[arg-type]
            document_id="d", text="Dana Mercer met Callum Price.",
            profile=ExtractionProfile(["Person"]), handling=_handling("P"),
            principal=ANALYST, extraction_model=LOCAL, datasets=datasets,
        )  # fmt: skip
        assert gateway.asked[-1] == reached, datasets
