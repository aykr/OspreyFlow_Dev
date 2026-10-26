"""HTTP route wiring for `/v1/ingest/*` — `spec/09_INGEST_STUDIO.md` §2
(Connect) and §8 (studio roles). Mirrors `test_sites_routes.py`'s own
discipline: dependency overrides and a fake store, never a live Postgres —
`StudioRecipeStore`'s own correctness is proven in
`test_studio_recipes_store.py`; what belongs here is only "does the right
role get through, does the wrong role get a 403, does org-unit scoping
collapse to a 404"."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from services.api.app import (
    app,
    get_audit,
    get_handling_scheme,
    get_investigations,
    get_ontology,
    get_principal,
    get_principal_names,
    get_studio_recipes,
)
from services.api.studio_recipes import (
    StudioRecipeCannotVersionError,
    StudioRecipeNotADraftError,
    StudioRecipeNotFoundError,
    StudioRecipeNotVerifiedError,
)

from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import Principal
from schemas.ingest import CONNECTOR_CATALOGUE, StudioRecipeDraft, StudioRecipeStatus
from tests.services.api.any_case import AnyCase
from tests.services.api.test_app import _FakeAudit

SOURCE_AUTHOR = Principal(
    id="analyst-1", clearance="OFFICIAL", org_unit="unit-1", roles=["source_author"]
)
NO_ROLE_ANALYST = Principal(id="analyst-2", clearance="OFFICIAL", org_unit="unit-1", roles=[])
SOURCE_APPROVER = Principal(
    id="approver-1", clearance="OFFICIAL", org_unit="unit-1", roles=["source_approver"]
)
LOADER = Principal(id="loader-1", clearance="OFFICIAL", org_unit="unit-1", roles=["loader"])


def _draft(**overrides: object) -> StudioRecipeDraft:
    defaults: dict[str, object] = {
        "recipe_id": "recipe-1",
        "version": 1,
        "status": StudioRecipeStatus.DRAFT,
        "label": "Carrier A — CDR",
        "connector_profile": "generic-csv",
        "owning_unit": "unit-1",
        "created_by": "analyst-1",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    defaults.update(overrides)
    return StudioRecipeDraft(**defaults)  # type: ignore[arg-type]


class _FakeStudioRecipes:
    def __init__(self, draft: StudioRecipeDraft | None = None) -> None:
        self.draft = draft
        self.create_calls: list[dict[str, object]] = []
        self.update_calls: list[dict[str, object]] = []
        self.raise_not_a_draft = False

    async def create_draft(self, principal: Principal, **kwargs: object) -> StudioRecipeDraft:
        self.create_calls.append(kwargs)
        self.draft = _draft(**{**kwargs, "owning_unit": principal.org_unit})  # type: ignore[arg-type]
        return self.draft

    async def get(self, recipe_id: str) -> StudioRecipeDraft:
        if self.draft is None or self.draft.recipe_id != recipe_id:
            raise StudioRecipeNotFoundError(recipe_id)
        return self.draft

    async def get_authorized(self, recipe_id: str, principal: Principal) -> StudioRecipeDraft:
        draft = await self.get(recipe_id)
        if draft.owning_unit != principal.org_unit:
            raise StudioRecipeNotFoundError(recipe_id)
        return draft

    async def update_pipeline(
        self, recipe_id: str, principal: Principal, *, pipeline: object
    ) -> StudioRecipeDraft:
        if self.raise_not_a_draft:
            raise StudioRecipeNotADraftError(recipe_id)
        assert self.draft is not None
        self.draft = self.draft.model_copy(update={"pipeline": pipeline})
        return self.draft

    async def update_draft(
        self, recipe_id: str, principal: Principal, **kwargs: object
    ) -> StudioRecipeDraft:
        if self.raise_not_a_draft:
            raise StudioRecipeNotADraftError(recipe_id)
        self.update_calls.append(kwargs)
        assert self.draft is not None
        non_none = {k: v for k, v in kwargs.items() if v is not None}
        # A fresh `StudioRecipeDraft(**...)` rather than `model_copy` — the
        # real store's `update_draft` re-fetches from Postgres afterwards,
        # which re-runs `_compute_ready_for_profile`; `model_copy` would
        # skip that validator and leave the fake store's `ready_for_profile`
        # stale.
        self.draft = _draft(**{**self.draft.model_dump(), **non_none})
        return self.draft

    async def list_drafts(self, principal: Principal) -> list[StudioRecipeDraft]:
        if self.draft is not None and self.draft.owning_unit == principal.org_unit:
            return [self.draft]
        return []

    async def update_row_template(
        self, recipe_id: str, principal: Principal, **kwargs: object
    ) -> StudioRecipeDraft:
        if self.raise_not_a_draft:
            raise StudioRecipeNotADraftError(recipe_id)
        self.update_calls.append(kwargs)
        assert self.draft is not None
        self.draft = _draft(**{**self.draft.model_dump(), **kwargs})
        return self.draft

    # --- Publish (09_INGEST_STUDIO.md §6) ---------------------------------

    async def list_all(self, principal: Principal) -> list[StudioRecipeDraft]:
        if self.draft is not None and self.draft.owning_unit == principal.org_unit:
            return [self.draft]
        return []

    async def mark_verified(self, recipe_id: str, version: int, *, now: datetime) -> None:
        assert self.draft is not None
        self.draft = self.draft.model_copy(update={"verified_at": now})

    async def publish(
        self, recipe_id: str, principal: Principal, **kwargs: object
    ) -> StudioRecipeDraft:
        # Refuses what the real store refuses: `pack_versions` is a required keyword (ADR-120
        # Amendment 1, decision 5) and never `None` (Amendment 2, decision 3), so a route test
        # cannot pass on a call the real `publish` would reject.
        if "pack_versions" not in kwargs:
            raise TypeError("publish() missing 1 required keyword-only argument: 'pack_versions'")
        if kwargs["pack_versions"] is None:
            raise ValueError("publish() needs pack_versions as a map, not None")
        assert self.draft is not None
        if self.draft.status is not StudioRecipeStatus.DRAFT:
            raise StudioRecipeNotADraftError(recipe_id)
        if self.draft.verified_at is None:
            raise StudioRecipeNotVerifiedError(recipe_id)
        self.draft = _draft(
            **{
                **self.draft.model_dump(),
                **kwargs,
                "status": StudioRecipeStatus.PUBLISHED,
                "published_by": principal.id,
            }
        )
        return self.draft

    async def update_schedule(
        self, recipe_id: str, principal: Principal, **kwargs: object
    ) -> StudioRecipeDraft:
        assert self.draft is not None
        if self.draft.status not in (StudioRecipeStatus.PUBLISHED, StudioRecipeStatus.FLAGGED):
            raise StudioRecipeNotADraftError(recipe_id)
        self.draft = _draft(**{**self.draft.model_dump(), **kwargs})
        return self.draft

    async def create_new_version(
        self, recipe_id: str, principal: Principal, *, now: datetime
    ) -> StudioRecipeDraft:
        assert self.draft is not None
        if self.draft.status not in (StudioRecipeStatus.PUBLISHED, StudioRecipeStatus.FLAGGED):
            raise StudioRecipeCannotVersionError(recipe_id)
        self.draft = _draft(
            **{
                **self.draft.model_dump(),
                "version": self.draft.version + 1,
                "status": StudioRecipeStatus.DRAFT,
                "verified_at": None,
                "git_path": None,
                "published_by": None,
                "published_at": None,
            }
        )
        return self.draft


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    studio_recipes = _FakeStudioRecipes()

    app.dependency_overrides[get_principal] = lambda: SOURCE_AUTHOR

    app.dependency_overrides[get_investigations] = AnyCase
    app.dependency_overrides[get_studio_recipes] = lambda: studio_recipes
    app.dependency_overrides[get_audit] = lambda: _FakeAudit()
    # A real scheme, not `object()`: the profile route below actually calls
    # `HandlingScheme.clears`/`.handling_codes` (via `principal_may_view`),
    # unlike every route above it which never touches the scheme at all.
    app.dependency_overrides[get_handling_scheme] = lambda: load_uk_le_scheme()
    app.dependency_overrides[get_ontology] = lambda: load_default_ontology()

    # ADR-106: the read decorates author names; this harness runs no lifespan, so a directory
    # that resolves nothing stands in (its real behaviour is proven in test_principal_names.py).
    class _NoNames:
        async def display_names(self, ids: object) -> dict[str, str]:
            return {}

    app.dependency_overrides[get_principal_names] = _NoNames

    test_client = TestClient(app)
    test_client.studio_recipes = studio_recipes  # type: ignore[attr-defined]
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


def test_list_connectors_returns_the_whole_catalogue(client: TestClient) -> None:
    response = client.get("/v1/ingest/connectors")

    assert response.status_code == 200
    assert len(response.json()) == len(CONNECTOR_CATALOGUE)


def test_create_draft_as_source_author_succeeds(client: TestClient) -> None:
    response = client.post(
        "/v1/investigations/inv-1/ingest/recipes",
        json={"label": "Carrier A — CDR", "connector_profile": "generic-csv"},
    )

    assert response.status_code == 201
    assert response.json()["status"] == "draft"
    assert response.json()["ready_for_profile"] is False


def test_create_draft_without_the_source_author_role_is_forbidden(client: TestClient) -> None:
    app.dependency_overrides[get_principal] = lambda: NO_ROLE_ANALYST
    app.dependency_overrides[get_investigations] = AnyCase

    response = client.post(
        "/v1/investigations/inv-1/ingest/recipes",
        json={"label": "Carrier A — CDR", "connector_profile": "generic-csv"},
    )

    assert response.status_code == 403


def test_get_draft_returns_404_for_a_recipe_in_a_different_unit(client: TestClient) -> None:
    client.studio_recipes.draft = _draft(owning_unit="unit-2")  # type: ignore[attr-defined]

    response = client.get("/v1/investigations/inv-1/ingest/recipes/recipe-1")

    assert response.status_code == 404
    assert response.json()["error"] == "studio_recipe_not_found"


def test_patch_draft_updates_and_reports_ready_for_profile_once_complete(
    client: TestClient,
) -> None:
    client.studio_recipes.draft = _draft()  # type: ignore[attr-defined]

    response = client.patch(
        "/v1/investigations/inv-1/ingest/recipes/recipe-1",
        json={
            "label": "Carrier A — CDR",
            "connector_profile": "generic-csv",
            "source_location": "s3://bucket/carrier-a.csv",
            "handling": {
                "classification": "OFFICIAL",
                "handling_code": "P",
                "originator": "unit-1",
                "owning_unit": "unit-1",
            },
            "legal_basis": "RIPA s22 acquisition — authorisation 2026/0114",
        },
    )

    assert response.status_code == 200
    assert response.json()["ready_for_profile"] is True


def test_patch_draft_without_the_source_author_role_is_forbidden(client: TestClient) -> None:
    client.studio_recipes.draft = _draft()  # type: ignore[attr-defined]
    app.dependency_overrides[get_principal] = lambda: NO_ROLE_ANALYST
    app.dependency_overrides[get_investigations] = AnyCase

    response = client.patch(
        "/v1/investigations/inv-1/ingest/recipes/recipe-1",
        json={"label": "Carrier A — CDR", "connector_profile": "generic-csv"},
    )

    assert response.status_code == 403


def test_patch_draft_that_is_no_longer_a_draft_is_a_conflict(client: TestClient) -> None:
    client.studio_recipes.draft = _draft()  # type: ignore[attr-defined]
    client.studio_recipes.raise_not_a_draft = True  # type: ignore[attr-defined]

    response = client.patch(
        "/v1/investigations/inv-1/ingest/recipes/recipe-1",
        json={"label": "Carrier A — CDR", "connector_profile": "generic-csv"},
    )

    assert response.status_code == 409
    assert response.json()["error"] == "studio_recipe_not_a_draft"


def test_list_drafts_returns_only_the_principals_own_drafts(client: TestClient) -> None:
    client.studio_recipes.draft = _draft()  # type: ignore[attr-defined]

    response = client.get("/v1/investigations/inv-1/ingest/recipes")

    assert response.status_code == 200
    assert len(response.json()) == 1


# --- profile (09_INGEST_STUDIO.md §3) ----------------------------------------


def _write_csv(tmp_path: Path, rows: list[dict[str, str]]) -> str:
    path = tmp_path / "source.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return str(path)


_CLEARED_HANDLING = {
    "classification": "OFFICIAL",
    "handling_code": "P",
    "originator": "unit-1",
    "owning_unit": "unit-1",
}

_UNCLEARED_HANDLING = {**_CLEARED_HANDLING, "classification": "SECRET"}


def _ready_draft(tmp_path: Path, **overrides: object) -> StudioRecipeDraft:
    source_location = overrides.pop("source_location", None) or _write_csv(
        tmp_path, [{"a_party": "07960112334", "duration": "42"}]
    )
    defaults: dict[str, object] = {
        "source_location": source_location,
        "handling": _CLEARED_HANDLING,
        "legal_basis": "RIPA s22 acquisition — authorisation 2026/0114",
    }
    defaults.update(overrides)
    return _draft(**defaults)


def test_get_profile_on_a_draft_missing_a_gate_answer_is_a_conflict(client: TestClient) -> None:
    client.studio_recipes.draft = _draft()  # type: ignore[attr-defined]

    response = client.get("/v1/investigations/inv-1/ingest/recipes/recipe-1/profile")

    assert response.status_code == 409
    assert response.json()["error"] == "recipe_not_ready_for_profile"


def test_get_profile_returns_unmasked_samples_for_a_cleared_principal(
    client: TestClient, tmp_path: Path
) -> None:
    client.studio_recipes.draft = _ready_draft(tmp_path)  # type: ignore[attr-defined]

    response = client.get("/v1/investigations/inv-1/ingest/recipes/recipe-1/profile")

    assert response.status_code == 200
    body = response.json()
    assert body["values_masked"] is False
    assert body["rows_sampled"] == 1
    a_party = next(c for c in body["columns"] if c["name"] == "a_party")
    assert a_party["sample_values"] == ["07960112334"]


def test_get_profile_shape_masks_samples_for_a_principal_who_cannot_clear_the_source(
    client: TestClient, tmp_path: Path
) -> None:
    client.studio_recipes.draft = _ready_draft(  # type: ignore[attr-defined]
        tmp_path, handling=_UNCLEARED_HANDLING
    )

    response = client.get("/v1/investigations/inv-1/ingest/recipes/recipe-1/profile")

    assert response.status_code == 200
    body = response.json()
    assert body["values_masked"] is True
    a_party = next(c for c in body["columns"] if c["name"] == "a_party")
    # `_shape_mask`: every digit renders as `#`, and `07960112334` (11
    # digits, under the mask cap) has no separator to keep literal.
    assert a_party["sample_values"] == ["#" * len("07960112334")]


def test_an_incomplete_handling_marking_no_longer_reaches_ready_for_profile(
    tmp_path: Path,
) -> None:
    """`schemas.ingest.StudioRecipeDraft._compute_ready_for_profile` now
    requires `handling` to actually construct a `schemas.domain.Handling`,
    not just be non-empty (`tests/schemas/test_ingest_connect.py`'s own
    proof of this at the schema layer) — so the normal Connect → Profile
    flow can no longer produce the state the next test has to force by
    hand. Checked again here, against `_ready_draft` specifically, since
    that is what the route tests below build every draft from."""
    draft = _ready_draft(tmp_path, handling={"classification": "OFFICIAL", "handling_code": "P"})
    assert draft.ready_for_profile is False


def test_get_profile_defends_against_a_bypassed_ready_for_profile_flag(
    client: TestClient, tmp_path: Path
) -> None:
    """Connect's own gate can no longer produce a `ready_for_profile=True`
    draft with incomplete handling (the test above) — this proves
    `services/api/studio_profile.py`'s own `Handling(**recipe.handling)`
    check is still there as defense-in-depth, for a draft that reaches this
    route with the flag set some other way (a future caller that builds a
    `StudioRecipeDraft` without going through `_compute_ready_for_profile`,
    or a stored row from before this gate was tightened). Plain attribute
    assignment, not a second constructor call — `StudioRecipeDraft` isn't
    frozen, and re-validating here would just recompute the correct value
    and defeat the point of the test."""
    draft = _ready_draft(tmp_path, handling={"classification": "OFFICIAL", "handling_code": "P"})
    draft.ready_for_profile = True
    client.studio_recipes.draft = draft  # type: ignore[attr-defined]

    response = client.get("/v1/investigations/inv-1/ingest/recipes/recipe-1/profile")

    assert response.status_code == 409
    assert response.json()["error"] == "source_handling_incomplete"


def test_get_profile_with_an_unavailable_connector_is_unprocessable(
    client: TestClient, tmp_path: Path
) -> None:
    client.studio_recipes.draft = _ready_draft(  # type: ignore[attr-defined]
        tmp_path, connector_profile="mobile-xry"
    )

    response = client.get("/v1/investigations/inv-1/ingest/recipes/recipe-1/profile")

    assert response.status_code == 422
    assert response.json()["error"] == "connector_not_available"


def test_get_profile_for_a_missing_source_file_is_unprocessable(
    client: TestClient, tmp_path: Path
) -> None:
    client.studio_recipes.draft = _ready_draft(  # type: ignore[attr-defined]
        tmp_path, source_location=str(tmp_path / "does-not-exist.csv")
    )

    response = client.get("/v1/investigations/inv-1/ingest/recipes/recipe-1/profile")

    assert response.status_code == 422
    assert response.json()["error"] == "source_unreadable"


def test_get_draft_carries_its_pipeline_chain(client: TestClient) -> None:
    """ADR-108 phase A: a v1 recipe reads as its canonical chain — derived at read time, never
    stored, so the canvas can draw every recipe ever made without touching what is stored."""
    made = client.post(
        "/v1/investigations/inv-1/ingest/recipes",
        json={"label": "Carrier A — CDR", "connector_profile": "generic-csv"},
    ).json()
    read = client.get(f"/v1/investigations/inv-1/ingest/recipes/{made['recipe_id']}")
    assert read.status_code == 200
    pipeline = read.json()["pipeline"]
    assert pipeline is not None
    assert [n["kind"] for n in pipeline["nodes"]] == [
        "domain_model",
        "source",
        "profile",
        "map",
        "load",
    ]
    assert pipeline["nodes"][0]["config"]["pack"] == "pole"


def test_the_domain_pack_catalogue_names_each_pack_and_what_it_adds(client: TestClient) -> None:
    """ADR-108 phase D: the Studio's domain-model choice — the POLE core first, then each pack
    with the entity and link types it brings, so the chooser never guesses."""
    response = client.get("/v1/ingest/packs")
    assert response.status_code == 200
    body = response.json()
    assert [p["name"] for p in body] == ["pole", "fibo", "niem", "stix"]
    fibo = body[1]
    assert "Account" in fibo["entity_types"]
    assert "BENEFICIAL_OWNER_OF" in fibo["edge_types"]
    pole = body[0]
    assert pole["entity_types"] == []  # the core adds nothing to itself; it is the base


_CHAIN_NODES = [
    {"id": "domain", "kind": "domain_model", "label": "D", "config": {"pack": "niem"}},
    {"id": "source", "kind": "source", "label": "S", "config": {}},
    {"id": "profile", "kind": "profile", "label": "P", "config": {}},
    {"id": "map", "kind": "map", "label": "M", "config": {}},
    {"id": "load", "kind": "load", "label": "L", "config": {}},
]
_CHAIN_EDGES = [
    {"source": "domain", "target": "source"},
    {"source": "source", "target": "profile"},
    {"source": "profile", "target": "map"},
    {"source": "map", "target": "load"},
]


def test_put_pipeline_saves_a_valid_graph(client: TestClient) -> None:
    made = client.post(
        "/v1/investigations/inv-1/ingest/recipes",
        json={"label": "Pipelined", "connector_profile": "generic-csv"},
    ).json()
    response = client.put(
        f"/v1/investigations/inv-1/ingest/recipes/{made['recipe_id']}/pipeline",
        json={"nodes": _CHAIN_NODES, "edges": _CHAIN_EDGES},
    )
    assert response.status_code == 200, response.text
    assert response.json()["pipeline"]["nodes"][0]["config"]["pack"] == "niem"


def test_put_pipeline_refuses_a_cycle_in_words(client: TestClient) -> None:
    """ADR-108 phase B: the graph half of the save gate — a violation is 422 with every problem
    named, never a saved graph the engine would walk forever."""
    made = client.post(
        "/v1/investigations/inv-1/ingest/recipes",
        json={"label": "Pipelined", "connector_profile": "generic-csv"},
    ).json()
    response = client.put(
        f"/v1/investigations/inv-1/ingest/recipes/{made['recipe_id']}/pipeline",
        json={
            "nodes": _CHAIN_NODES,
            "edges": [*_CHAIN_EDGES, {"source": "load", "target": "source"}],
        },
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "pipeline_invalid"
    assert any("cycle" in problem for problem in body["problems"])


def test_publish_refuses_what_the_runner_cannot_run_yet(client: TestClient) -> None:
    """ADR-108 phase C: the runner runs extract stages now, so the gate refuses only what it
    still cannot — here, a library outside the runner's set — in words, never part-run (rule 2)."""
    made = client.post(
        "/v1/investigations/inv-1/ingest/recipes",
        json={"label": "Pipelined", "connector_profile": "generic-csv"},
    ).json()
    saved = client.put(
        f"/v1/investigations/inv-1/ingest/recipes/{made['recipe_id']}/pipeline",
        json={
            "nodes": [
                *_CHAIN_NODES,
                {
                    "id": "extract",
                    "kind": "extract",
                    "label": "Extract",
                    "config": {"library": "whisper", "media": "text"},
                },
                {"id": "load2", "kind": "load", "label": "Load", "config": {}},
            ],
            "edges": [
                *_CHAIN_EDGES,
                {"source": "map", "target": "extract"},
                {"source": "extract", "target": "load2"},
            ],
        },
    )
    assert saved.status_code == 200, saved.text
    approver = SOURCE_AUTHOR.model_copy(
        update={"roles": [*SOURCE_AUTHOR.roles, "source_approver"]}
    )
    app.dependency_overrides[get_principal] = lambda: approver
    # The refusal fires before anything touches the recipes repository, so a throwaway path
    # satisfies the dependency without ever being written to.
    from pathlib import Path

    from services.api.app import get_recipes_repo_root

    app.dependency_overrides[get_recipes_repo_root] = lambda: Path("/tmp/never-written")
    response = client.post(
        f"/v1/investigations/inv-1/ingest/recipes/{made['recipe_id']}/publish",
        json={},
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "pipeline_not_runnable"
    assert any("whisper" in problem for problem in body["problems"])


# --- ADR-127 decision 5 (B2-5): a Studio draft carries `deduplicate` ------------------------------


def _dedupe_draft(tmp_path: Path) -> StudioRecipeDraft:
    return _ready_draft(
        tmp_path,
        source_location=_write_csv(
            tmp_path, [{"payer": "a", "payee": "b", "paid_at": "2026-03-01T09:00:00+00:00"}]
        ),
    )


_PATCH_BODY = {
    "label": "Carrier A — CDR",
    "connector_profile": "generic-csv",
    "handling": {
        "classification": "OFFICIAL",
        "handling_code": "P",
        "originator": "unit-1",
        "owning_unit": "unit-1",
    },
    "legal_basis": "RIPA s22 acquisition — authorisation 2026/0114",
}
_URL = "/v1/investigations/inv-1/ingest/recipes/recipe-1"


def test_patch_saves_a_deduplicate_whose_fields_are_source_columns(
    client: TestClient, tmp_path: Path
) -> None:
    from schemas.ingest import DeduplicateConfig, FieldBinding

    client.studio_recipes.draft = _dedupe_draft(tmp_path)  # type: ignore[attr-defined]
    key = [{"field": "payer"}, {"field": "payee"}, {"field": "paid_at", "transform": "datetime"}]

    response = client.patch(_URL, json={**_PATCH_BODY, "deduplicate": {"key": key}})

    assert response.status_code == 200, response.text
    saved = client.studio_recipes.update_calls[-1]["deduplicate"]  # type: ignore[attr-defined]
    assert saved == DeduplicateConfig(
        key=[
            FieldBinding(field="payer"),
            FieldBinding(field="payee"),
            FieldBinding(field="paid_at", transform="datetime"),
        ]
    )
    assert response.json()["deduplicate"]["key"][0]["field"] == "payer"


def test_patch_without_a_deduplicate_leaves_the_drafts_own_alone(
    client: TestClient, tmp_path: Path
) -> None:
    client.studio_recipes.draft = _dedupe_draft(tmp_path)  # type: ignore[attr-defined]
    response = client.patch(_URL, json=_PATCH_BODY)
    assert response.status_code == 200
    assert client.studio_recipes.update_calls[-1]["deduplicate"] is None  # type: ignore[attr-defined]


def test_patch_with_an_empty_key_clears_the_deduplicate(client: TestClient, tmp_path: Path) -> None:
    client.studio_recipes.draft = _dedupe_draft(tmp_path)  # type: ignore[attr-defined]
    response = client.patch(_URL, json={**_PATCH_BODY, "deduplicate": {"key": []}})
    assert response.status_code == 200
    saved = client.studio_recipes.update_calls[-1]["deduplicate"]  # type: ignore[attr-defined]
    assert saved is not None and saved.key == [], "the store reads an empty key as clearing it"


@pytest.mark.parametrize(
    ("key", "named"),
    [
        ([{"field": "no_such_column"}], "no_such_column"),
        ([{"fields": ["payer", "ghost"], "transform": "coordinate_pair"}], "ghost"),
        ([{"literal": "x"}], "names no source column"),
        ([{"fields": ["payer", "payee"]}], "must declare a `transform`"),
    ],
    ids=[
        "unknown column",
        "unknown column in fields",
        "a literal alone",
        "fields with no transform",
    ],
)
def test_patch_refuses_a_deduplicate_the_source_cannot_support_in_words(
    client: TestClient, tmp_path: Path, key: list[dict[str, object]], named: str
) -> None:
    client.studio_recipes.draft = _dedupe_draft(tmp_path)  # type: ignore[attr-defined]
    response = client.patch(_URL, json={**_PATCH_BODY, "deduplicate": {"key": key}})
    assert response.status_code == 422
    assert named in " ".join(response.json()["problems"])
    assert client.studio_recipes.update_calls == []  # type: ignore[attr-defined]


def test_patch_judges_the_deduplicate_by_the_columns_when_the_source_cannot_be_read(
    client: TestClient, tmp_path: Path
) -> None:
    """No source to read is no column to judge against (as `source_column_names` has it for a
    marking bound to a column): the shape is still checked, a column is judged at run."""
    client.studio_recipes.draft = _ready_draft(tmp_path, source_location=str(tmp_path / "gone.csv"))  # type: ignore[attr-defined]
    ok = client.patch(_URL, json={**_PATCH_BODY, "deduplicate": {"key": [{"field": "x"}]}})
    assert ok.status_code == 200
    bad = client.patch(_URL, json={**_PATCH_BODY, "deduplicate": {"key": [{"literal": "x"}]}})
    assert bad.status_code == 422
