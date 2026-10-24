"""Trends offer the case's domain packs (`06_DECISIONS.md` ADR-126 decision 6, unit D3; ADR-113
Amendment 4): the options, the refusal on save and preview, and what is never refused, which is
running a trend that is already saved. Pure: the real deployment ontology (a file read), real
routes through the real level dependencies, and in-memory stand-ins for the stores and analytics.
Nothing here reads graph data, so the access rules are the routes' existing ones
(`test_trends.py`'s levels, `test_investigation_levels.py`'s table); these cases add the packs.

What a mistake here would do, and the case that catches it:

- options that ignored the packs would offer `BENEFICIAL_OWNER_OF` to a prison case
  (`test_a_niem_case_is_offered_no_fibo_or_stix_type`);
- narrowing by each pack's raw list, which names the core types a pack only widens, would hide
  `TRANSACTED` from a case with no `fibo` (`test_a_case_of_no_packs_is_offered_the_core_types_only`,
  `test_a_type_a_pack_only_widens_is_core`);
- a save or preview that accepted an outside type would store a trend the builder never offered
  (`test_save_and_preview_refuse_a_type_outside_the_cases_packs_in_words`);
- the domain check reaching running would break a saved trend, and a pack holding it, the moment
  an Author changed the packs
  (`test_a_saved_trend_still_runs_after_the_packs_change`,
  `test_a_pack_holding_a_trend_refreshes_after_the_packs_change`,
  `test_the_domain_check_is_called_only_by_save_and_preview`);
- the marker set for a trend that is inside the packs, or missing for one outside them
  (`test_the_marker_is_set_exactly_for_a_trend_outside_the_cases_packs`).
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api import app as app_module
from services.api.app import (
    app,
    get_analytics,
    get_audit,
    get_handling_scheme,
    get_investigations,
    get_ontology,
    get_principal,
    get_trend_store,
    get_working_set,
)
from services.api.investigations import (
    AccessLevel,
    InsufficientAccessError,
    Investigation,
    InvestigationNotFoundError,
)
from services.api.trends import (
    TrendDefinitionRefused,
    check_in_case_domains,
    mark_outside_case_domains,
    trend_options,
    validate_definition,
)

from ontology.handling import load_uk_le_scheme
from ontology.packs import PACK_NAMES, load_deployment_ontology
from schemas.analytics import TrendRequest, TrendResult
from schemas.domain import Principal
from schemas.packs import AddPackItem
from schemas.trends import TrendDefinition, TrendDefinitionInput

ONTOLOGY = load_deployment_ontology()
CORE = ["COMMUNICATED_WITH", "PRESENT_AT", "TRANSACTED", "PAIRED_WITH"]
FIBO = ["REGISTERED_AT", "BENEFICIAL_OWNER_OF", "CONTROLS", "HOLDS_ACCOUNT"]
NIEM = [
    "USED_AS", "ROLE_IN", "SHARED_CELL_WITH", "IN_CONFLICT_WITH", "VISITED", "HELD_AT",
    "OCCURRED_AT", "PASSES_ITEMS_TO",
]  # fmt: skip
STIX = ["TARGETS", "COMPROMISES"]

EDITOR = Principal(id="ed", clearance="SECRET", org_unit="unit-1", roles=["analyst"])
VIEWER = Principal(id="vw", clearance="SECRET", org_unit="unit-1", roles=["analyst"])


def _names(domains: list[str]) -> set[str]:
    return {o.name for o in trend_options(ONTOLOGY, domains).event_types}


def _defn(*types: str, **kwargs: Any) -> TrendDefinitionInput:
    return TrendDefinitionInput(**{"title": "T", "event_types": list(types), **kwargs})


# --- the options ------------------------------------------------------------------------------


def test_a_case_of_no_packs_is_offered_the_core_types_only() -> None:
    assert _names([]) == set(CORE)


def test_a_niem_case_is_offered_no_fibo_or_stix_type() -> None:
    offered = _names(["niem"])

    assert offered == set(CORE) | set(NIEM)
    assert not offered & (set(FIBO) | set(STIX))


@pytest.mark.parametrize(
    ("domains", "expected"),
    [
        (["fibo"], CORE + FIBO),
        (["stix"], CORE + STIX),
        (["fibo", "niem"], CORE + FIBO + NIEM),
        (["fibo", "niem", "stix"], CORE + FIBO + NIEM + STIX),
    ],
)
def test_each_pack_adds_exactly_its_own_temporal_types(
    domains: list[str], expected: list[str]
) -> None:
    assert _names(domains) == set(expected)


def test_a_type_a_pack_only_widens_is_core() -> None:
    """`TRANSACTED`, `USES` and `DEPICTS` are widened by a pack (`extends`) and defined by none, so
    `type_packs` leaves them out: core. The pack files' raw lists name them, and narrowing by those
    would hide them from a case without the pack."""
    for name in ("TRANSACTED", "USES", "DEPICTS"):
        assert ONTOLOGY.type_packs.get(name) is None, name
    assert "TRANSACTED" in _names([])


def test_a_widened_core_type_that_is_temporal_is_offered_to_a_case_of_no_packs() -> None:
    """`USES` and `DEPICTS` are not temporal in the shipped ontology, so the builder offers neither
    today; were they, a case of no packs would still be offered them."""
    temporal = ONTOLOGY.model_copy(
        update={
            "edge_types": [
                e.model_copy(update={"temporal": True}) if e.name in ("USES", "DEPICTS") else e
                for e in ONTOLOGY.edge_types
            ]
        }
    )

    offered = {o.name for o in trend_options(temporal, []).event_types}

    assert {"TRANSACTED", "USES", "DEPICTS"} <= offered


def test_a_type_in_no_pack_is_core_even_when_the_ontology_is_composed_without_packs() -> None:
    """Analyst-promoted types (ADR-090) are in no pack, so every case is offered them."""
    from schemas.domain import EdgeTypeDef, OntologySchema

    promoted = OntologySchema(
        version=1,
        entity_types=[],
        edge_types=[
            EdgeTypeDef.model_validate(
                {"name": "PROMOTED", "from": ["Person"], "to": ["Person"], "temporal": True,
                 "basis": "direct"}
            ),
        ],
    )  # fmt: skip

    assert {o.name for o in trend_options(promoted, []).event_types} == {"PROMOTED"}


def test_every_packs_temporal_types_are_known_to_this_test() -> None:
    """If a pack gains a temporal type, the lists above are stale and say so here."""
    in_a_pack = {
        e.name
        for e in ONTOLOGY.edge_types
        if e.temporal and not e.hidden and not e.system and ONTOLOGY.type_packs.get(e.name)
    }
    assert in_a_pack == set(FIBO + NIEM + STIX)
    assert set(PACK_NAMES) == {"fibo", "niem", "stix"}


# --- save and preview refuse an outside type ------------------------------------------------------


def test_the_check_refuses_a_type_outside_the_packs_naming_the_packs_and_where_to_change_them() -> (
    None
):
    with pytest.raises(TrendDefinitionRefused) as refused:
        check_in_case_domains(_defn("BENEFICIAL_OWNER_OF", "TRANSACTED"), ONTOLOGY, ["niem"])

    words = str(refused.value)
    # Named as the builder shows the type, never by its key.
    assert "Beneficial owner of" in words and "BENEFICIAL_OWNER_OF" not in words
    assert "Transacted" not in words and "TRANSACTED" not in words
    assert "Crime case analysis (NIEM)" in words
    assert "An Author can change them in the Cases drawer, beside 'Data this case reads'." in words


def test_the_check_names_the_core_model_for_a_case_of_no_packs() -> None:
    with pytest.raises(TrendDefinitionRefused, match=r"Bespoke POLE \(the core model\)"):
        check_in_case_domains(_defn("OCCURRED_AT"), ONTOLOGY, [])


def test_the_check_accepts_core_types_and_the_cases_own_packs() -> None:
    check_in_case_domains(_defn("TRANSACTED", "COMMUNICATED_WITH"), ONTOLOGY, [])
    check_in_case_domains(_defn("OCCURRED_AT", "TRANSACTED"), ONTOLOGY, ["niem"])
    check_in_case_domains(_defn("BENEFICIAL_OWNER_OF", "OCCURRED_AT"), ONTOLOGY, ["fibo", "niem"])


def test_the_check_leaves_an_unknown_type_to_the_ontology_check() -> None:
    check_in_case_domains(_defn("NOT_A_TYPE"), ONTOLOGY, [])
    with pytest.raises(TrendDefinitionRefused, match="not an event type of this deployment"):
        validate_definition(_defn("NOT_A_TYPE"), ONTOLOGY)


def test_the_whole_ontology_check_still_accepts_every_packs_type() -> None:
    """`validate_definition` stays on the whole ontology: running and pack refresh depend on it."""
    for name in (*FIBO, *NIEM, *STIX):
        validate_definition(_defn(name), ONTOLOGY)


# --- the routes -------------------------------------------------------------------------------


class _Cases:
    """One case whose packs a test can change between requests, as an Author's change does."""

    def __init__(self) -> None:
        self.domains: list[str] = []
        self.levels = {"ed": AccessLevel.EDITOR, "vw": AccessLevel.VIEWER}

    async def get_authorized(
        self, investigation_id: str, principal: Principal, *, need: AccessLevel
    ) -> Investigation:
        level = self.levels.get(principal.id)
        if investigation_id != "case-1" or level is None:
            raise InvestigationNotFoundError(investigation_id)
        if level.rank < need.rank:
            raise InsufficientAccessError("too low")
        return Investigation(
            id="case-1",
            name="C",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_by="a",
            owning_unit="unit-1",
            domains=self.domains,  # type: ignore[arg-type]
        )


class _Analytics:
    def __init__(self) -> None:
        self.asked: list[TrendRequest] = []

    async def trend(self, req: TrendRequest, principal: Principal) -> TrendResult:
        self.asked.append(req)
        return TrendResult(interval=req.interval, measure=req.measure, points=[], total=0, events=0,
                           classifications=["OFFICIAL"])  # fmt: skip


class _Store:
    def __init__(self) -> None:
        self.saved: dict[str, TrendDefinition] = {}

    async def create(
        self, case_id: str, defn: TrendDefinitionInput, by: Principal
    ) -> TrendDefinition:
        now = datetime(2026, 3, 1, tzinfo=UTC)
        saved = TrendDefinition(**defn.model_dump(), id=f"t{len(self.saved) + 1}",
                                investigation_id=case_id,
                                created_by=by.id, created_at=now, updated_at=now)  # fmt: skip
        self.saved[saved.id] = saved
        return saved

    async def list_for_case(self, case_id: str) -> list[TrendDefinition]:
        return list(self.saved.values())

    async def get(self, case_id: str, trend_id: str) -> TrendDefinition | None:
        return self.saved.get(trend_id)


class _Audit:
    async def record(self, **kwargs: Any) -> None:
        return None


@pytest.fixture
def world() -> Any:
    cases, analytics, store = _Cases(), _Analytics(), _Store()
    app.dependency_overrides.update({
        get_investigations: lambda: cases, get_analytics: lambda: analytics,
        get_trend_store: lambda: store, get_ontology: lambda: ONTOLOGY,
        get_handling_scheme: load_uk_le_scheme, get_audit: _Audit, get_working_set: lambda: None,
    })  # fmt: skip
    yield cases, analytics, store
    app.dependency_overrides.clear()


def _as(who: Principal) -> TestClient:
    app.dependency_overrides[get_principal] = lambda: who
    return TestClient(app)


def _body(*types: str) -> dict[str, Any]:
    return {"title": "T", "event_types": list(types)}


def test_the_options_route_offers_the_cases_packs_only(world: Any) -> None:
    cases, _, _ = world
    cases.domains = ["niem"]

    offered = {
        o["name"]
        for o in _as(VIEWER).get("/v1/investigations/case-1/trends/options").json()["event_types"]
    }

    assert offered == set(CORE) | set(NIEM)
    cases.domains = []
    offered = {
        o["name"]
        for o in _as(VIEWER).get("/v1/investigations/case-1/trends/options").json()["event_types"]
    }
    assert offered == set(CORE)


def test_save_and_preview_refuse_a_type_outside_the_cases_packs_in_words(world: Any) -> None:
    cases, analytics, store = world
    cases.domains = ["niem"]

    saved = _as(EDITOR).post("/v1/investigations/case-1/trends", json=_body("BENEFICIAL_OWNER_OF"))
    previewed = _as(VIEWER).post(
        "/v1/investigations/case-1/trends/preview", json=_body("BENEFICIAL_OWNER_OF")
    )

    for refused in (saved, previewed):
        assert refused.status_code == 422 and refused.json()["error"] == "trend_refused"
        detail = refused.json()["detail"]
        assert "Crime case analysis (NIEM)" in detail
        assert "in the Cases drawer, beside 'Data this case reads'" in detail
    assert store.saved == {} and analytics.asked == [], "nothing saved, nothing counted"


def test_save_and_preview_accept_a_core_type_and_the_cases_own_pack_type(world: Any) -> None:
    cases, _, _ = world
    cases.domains = ["niem"]

    for types in (("TRANSACTED",), ("OCCURRED_AT",), ("OCCURRED_AT", "TRANSACTED")):
        assert (
            _as(EDITOR).post("/v1/investigations/case-1/trends", json=_body(*types)).status_code
            == 201
        )
        assert (
            _as(VIEWER)
            .post("/v1/investigations/case-1/trends/preview", json=_body(*types))
            .status_code
            == 200
        )


def test_a_saved_trend_still_runs_after_the_packs_change(world: Any) -> None:
    """Saved while the case held `fibo`; an Author then removes it. Running is the whole ontology's
    check, so the trend still runs. The plant is the domain check inside `_trend_figures`."""
    cases, analytics, _ = world
    cases.domains = ["fibo"]
    trend = (
        _as(EDITOR)
        .post("/v1/investigations/case-1/trends", json=_body("BENEFICIAL_OWNER_OF"))
        .json()["id"]
    )

    cases.domains = []
    ran = _as(VIEWER).get(f"/v1/investigations/case-1/trends/{trend}/figures")

    assert ran.status_code == 200, ran.text
    assert len(analytics.asked) == 1


def test_a_pack_holding_a_trend_refreshes_after_the_packs_change(world: Any) -> None:
    """Adding a trend to a pack, and refreshing a snapshot, both run `_trend_figures` for the saved
    definition; neither may meet the domain check."""
    import asyncio

    cases, analytics, store = world
    cases.domains = ["fibo"]
    saved = asyncio.run(store.create("case-1", _defn("BENEFICIAL_OWNER_OF"), EDITOR))
    cases.domains = []
    case = asyncio.run(cases.get_authorized("case-1", EDITOR, need=AccessLevel.VIEWER))

    item = asyncio.run(
        app_module._build_pack_item(
            AddPackItem(kind="trend", trend_id=saved.id), case, EDITOR, None,  # type: ignore[arg-type]
            load_uk_le_scheme(), None, store, ONTOLOGY, analytics, cases, _Audit(), None,  # type: ignore[arg-type]
        )
    )  # fmt: skip

    assert item.kind == "trend" and len(analytics.asked) == 1


def test_the_domain_check_is_called_only_by_save_and_preview() -> None:
    """Every module under `services/api/`, not only `app.py`: the plant is a call inside
    `_trend_figures`, or in any other function of any module, found here by module and name."""
    root = Path(app_module.__file__).parent
    callers: set[tuple[str, str]] = set()
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for node in ast.walk(fn):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name | ast.Attribute)
                    and getattr(node.func, "id", getattr(node.func, "attr", ""))
                    == "check_in_case_domains"
                ):
                    callers.add((path.relative_to(root).as_posix(), fn.name))

    assert callers == {("app.py", "save_trend"), ("app.py", "preview_trend")}


def test_the_marker_is_set_exactly_for_a_trend_outside_the_cases_packs(world: Any) -> None:
    cases, _, _ = world
    cases.domains = ["fibo", "niem"]
    _as(EDITOR).post("/v1/investigations/case-1/trends", json=_body("TRANSACTED"))
    _as(EDITOR).post(
        "/v1/investigations/case-1/trends", json={**_body("BENEFICIAL_OWNER_OF"), "title": "Owners"}
    )
    _as(EDITOR).post(
        "/v1/investigations/case-1/trends", json={**_body("OCCURRED_AT"), "title": "Throw-overs"}
    )

    def marks() -> dict[str, bool]:
        listed = _as(VIEWER).get("/v1/investigations/case-1/trends").json()
        return {t["title"]: t["outside_case_domains"] for t in listed}

    assert marks() == {"T": False, "Owners": False, "Throw-overs": False}
    cases.domains = ["niem"]
    assert marks() == {"T": False, "Owners": True, "Throw-overs": False}
    cases.domains = []
    assert marks() == {"T": False, "Owners": True, "Throw-overs": True}
    cases.domains = ["fibo", "niem", "stix"]
    assert marks() == {"T": False, "Owners": False, "Throw-overs": False}


def test_a_saved_trend_response_is_never_marked_because_it_was_just_checked(world: Any) -> None:
    cases, _, _ = world
    cases.domains = ["fibo"]

    saved = _as(EDITOR).post("/v1/investigations/case-1/trends", json=_body("BENEFICIAL_OWNER_OF"))

    assert saved.status_code == 201 and saved.json()["outside_case_domains"] is False


def test_the_marker_helper_is_exact_for_the_ontology() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    saved = TrendDefinition(**_defn("BENEFICIAL_OWNER_OF", "TRANSACTED").model_dump(), id="t",
                            investigation_id="c",
                            created_by="x", created_at=now, updated_at=now)  # fmt: skip

    assert mark_outside_case_domains(saved, ONTOLOGY, ["niem"]).outside_case_domains is True
    assert mark_outside_case_domains(saved, ONTOLOGY, ["fibo"]).outside_case_domains is False
    assert mark_outside_case_domains(saved, ONTOLOGY, []).outside_case_domains is True
