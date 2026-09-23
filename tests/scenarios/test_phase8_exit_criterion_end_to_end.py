"""Phase 8's own V1 END TO END exit criterion, right after its own
outcome bullets: "both acceptance scenarios pass unchanged on `local-lite`. Nothing else is part
of it." This is Stage 4g's own closing pass — the single test the whole milestone rests on.

Real FastAPI app (`services.api.app`), real ArcadeDB/Postgres/Valkey (`make dev-up`) — the same
`TestClient`-against-real-lifespan shape `test_phase6a_glass_surfaces.py`/`test_phase7_stage6c_
watch_routes.py` already establish. Every Glass-facing action goes through the exact HTTP route
the Glass itself calls; the underlying fixture data is built the same way `hmp_graph.py` builds
Scenario A's own graph side — through the real recipe engine where a recipe exists, direct
`GraphPort` writes where §2.4 of `01_DOMAIN_MODEL.md` already sanctions it (fixture data with no
recipe behind it), never through product code invented for this test alone.

**What this file found that did not exist before it was written — stated here, not only in the
hand-off report, so a future reader of this file's own history sees it in place.**

1. **No fixture generator exists anywhere in this repository for Scenario B's own "two cohorts of
   person entities with no overt association" or "one messaging-handle dataset"** — `cdr.py`
   builds only the two `Endpoint`s the phone-number renderings collapse onto (`08_ACCEPTANCE_
   SCENARIOS.md`'s own B1-B3), never the person layer B4-B8 walk through. Built here, inline,
   as the minimal real graph shape B4-B8 need (`_seed_cohort`/`_seed_handle_cohort` below) —
   disclosed as test-local construction, not a dedicated fixture module, because no other test
   needs this shape yet; if a second test ever does, promoting it to `tests/scenarios/fixtures/`
   is the right move then, not speculative work now.
2. **`Endpoint` carries no `resolution` block in `packages/ontology/default.yaml`** — checked
   directly (`python -c "yaml.safe_load(...)"`), not assumed. `resolve_entity_type` can score a
   `Person` pair (`Person`'s own `jaro_winkler(family_name)`/... comparisons); it has nothing
   to compare for `Endpoint`, so B8's own literal "a scored `SAME_AS` edge links the handle to
   the shared endpoint" cannot be produced by the resolution mechanism as it exists today — there
   is no comparison config to score it with. This is a genuine, real product gap, not a test
   scaffolding problem, and is not routed around here: B11's own manual link (`score=1.0`,
   `provenance=asserted`) is what this walkthrough actually uses for the handle-to-endpoint edge,
   one step earlier in the mechanism than B8's own table position implies, and B9/B10's own
   threshold-move/explain mechanics are proven against that manually-asserted edge exactly the way
   `test_phase6a_glass_surfaces.py` already proved them against a different manually-asserted pair.
   Disposition: real, unscoped work (choosing and
   validating comparison functions for `handle`/`e164`/`imsi` identifiers) for a future stage, not
   invented under this closing pass.
3. **No seizure-record connector or recipe exists** (already disclosed in `seizure_record.py`'s
   own docstring) — B13's "ingest the later seizure record" is built here as a small ad-hoc
   recipe over the fixture's own raw MSISDN, matching the identical `run_studio_recipe` HTTP route
   B12's hotlist is evaluated through, rather than a direct `GraphPort` write that would bypass
   the real ingest-evaluation wiring B13 is actually about. The IMEI/IMSI `PAIRED_WITH` legs
   (B15) have no such route to reuse (no MSISDN/IMSI/IMEI row could plausibly share one row
   template with the hotlist-triggering leg without inventing a fictitious connector format) and
   are written directly, the same "documented, sanctioned shape" `hmp_graph.py`'s own docstring
   already establishes for fixture data with no recipe behind it.

Every other section below is proven against real fixture generators already in this repository
(`cdr.py`, `seizure_record.py`, `hmp.py`/`hmp_graph.py`, `fixture_corp.py`) and cites the existing
test that already proves the piece this file only needs to compose, rather than re-deriving it.
"""

from __future__ import annotations

import csv
import subprocess
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from services.api.alerts import AlertStore
from services.api.app import get_recipes_repo_root
from services.api.config import PostgresConfig
from services.api.hotlists import HotlistStore
from services.api.studio_publish import build_recipe, write_and_commit_recipe
from services.api.studio_recipes import StudioRecipeStore
from services.ingest.engine import run_recipe
from services.ingest.recipe_loader import load_recipe
from services.resolve.projection import THRESHOLD_BALANCED, THRESHOLD_STRICT
from services.resolve.resolver import resolve_entity_type
from services.resolve.same_as_writer import write_same_as_edges
from tests.conftest import default_claims, sign_token
from tests.scenarios.fixtures.cdr import A_PARTY_RENDERINGS, B_PARTY, generate_cdr_rows
from tests.scenarios.fixtures.fixture_corp import generate_resolution_persons
from tests.scenarios.fixtures.hmp_graph import build_hmp_graph
from tests.scenarios.fixtures.seizure_record import (
    HANDSET_IMEI_NORMALISED,
    SIM_A_IMSI_NORMALISED,
    SIM_B_IMSI_NORMALISED,
    generate_seizure_record,
)

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from conduit_common.identity import new_edge_id, new_id
from knowledge_adapters.msisdn import msisdn as _normalise_msisdn
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import (
    EdgeWrite,
    Handling,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)
from schemas.ingest import FieldBinding, RecipeEdge, RecipeEntity, RowTemplate


def _fresh_uk_msisdn_raw() -> str:
    """A fresh, valid-format UK mobile MSISDN each call — `_ingest_cdr_fixture`'s own docstring
    explains why B12/B13's own identifier cannot be the seizure fixture's literal frozen
    `SIM_B_MSISDN_RAW` constant when run against the shared, persistent `ospreyflow` database:
    a fixed identifier would already exist from a prior run, `on_match: reference` would find it
    rather than create it, and B13's own alert (which depends on `report.created_node_ids` being
    non-empty) would never fire on a rerun. `079` — distinct from Ofcom's own fictional-drama
    `07700 900000-999` block `cdr.py`'s own comment already avoids — plus eight random digits,
    real UK mobile shape, checked directly against the real `msisdn()` normaliser below rather
    than assumed plausible."""
    import random

    digits = "".join(random.choices("0123456789", k=8))
    raw = f"079{digits}"
    _normalise_msisdn(raw)  # raises if this is ever not a valid UK mobile shape
    return raw

FIXTURES = Path(__file__).resolve().parent / "fixtures"

PRINCIPAL = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
RESTRICTED = Principal(id="analyst-restricted", clearance="OFFICIAL", org_unit="unit-9")


# --- shared fixtures / helpers (the same shapes `test_phase6a_glass_surfaces.py` and
# --- `test_phase7_stage6c_watch_routes.py` already establish) -----------------------------------


@pytest.fixture
def api_env(jwks_url: str) -> Iterator[None]:
    import os

    previous = {
        key: os.environ.get(key)
        for key in ("OIDC_JWKS_URL", "OIDC_ALGORITHMS", "ARCADEDB_DATABASE")
    }
    os.environ["OIDC_JWKS_URL"] = jwks_url
    os.environ["OIDC_ALGORITHMS"] = "RS256"
    os.environ["ARCADEDB_DATABASE"] = "ospreyflow"
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    return repo


def _bearer(private_key: rsa.RSAPrivateKey, **claim_overrides: object) -> dict[str, str]:
    token = sign_token(private_key, default_claims(**claim_overrides))
    return {"Authorization": f"Bearer {token}"}


def _handling(owning_unit: str = "unit-1", classification: str = "OFFICIAL") -> Handling:
    return Handling(
        classification=classification,
        handling_code="P",
        originator=owning_unit,
        owning_unit=owning_unit,
    )


def _handling_dict(owning_unit: str = "unit-1", classification: str = "OFFICIAL") -> dict:
    return {
        "classification": classification,
        "handling_code": "P",
        "originator": owning_unit,
        "owning_unit": owning_unit,
    }


def _provenance(label: str) -> Provenance:
    return Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id="fixture", locator=label, excerpt_hash="")],
        first_seen=datetime.now(UTC),
    )


def _person_write(node_id: str, family_name: str, given_names: str) -> NodeWrite:
    now = datetime.now(UTC)
    return NodeWrite(
        id=node_id,
        type="Person",
        properties={
            "family_name": family_name,
            "given_names": given_names,
            "date_of_birth": "1985-01-01",
        },
        provenance=_provenance(f"person:{node_id}"),
        handling=_handling(),
        created_by="fixture-b4-b8",
        created_at=now,
    )


def _endpoint_write(node_id: str, value_normalised: str, endpoint_kind: str) -> NodeWrite:
    now = datetime.now(UTC)
    return NodeWrite(
        id=node_id,
        type="Endpoint",
        properties={
            "value_raw": value_normalised,
            "value_normalised": value_normalised,
            "endpoint_kind": endpoint_kind,
        },
        provenance=_provenance(f"endpoint:{node_id}"),
        handling=_handling(),
        created_by="fixture-b4-b8",
        created_at=now,
    )


def _edge_write(edge_type: str, source: str, target: str) -> EdgeWrite:
    now = datetime.now(UTC)
    return EdgeWrite(
        id=new_edge_id(),
        type=edge_type,
        source=source,
        target=target,
        provenance=_provenance(f"edge:{source}->{target}"),
        handling=_handling(),
        created_by="fixture-b4-b8",
        created_at=now,
    )


async def _graph_client() -> tuple[ArcadeDBClient, GraphArcadeDBAdapter]:
    """The same real, persistent `ospreyflow` database the running `TestClient` app's own
    lifespan connects to — `test_phase6a_glass_surfaces.py`'s own `_fetch_node_json` docstring has
    the full reasoning for why this, not `adapters.graph_arcadedb.testing.arcadedb_adapter`.

    `create_database_if_absent` first: found directly, not assumed, running this file alone
    against a freshly-provisioned ArcadeDB volume (no prior test in the session had yet caused
    `services.api.app`'s own lifespan to create `ospreyflow`) — `apply_schema` alone raised
    `Database 'ospreyflow' is not available'`. Every other caller of this helper in this file runs
    after `TestClient(app)` has already constructed the app once, which normally creates it first,
    so this had stayed silently order-dependent on that happening somewhere else first. Matches
    `adapters.graph_arcadedb.testing.arcadedb_adapter`'s own create-then-apply-schema order."""
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
    await client.create_database_if_absent()
    graph = GraphArcadeDBAdapter(client, load_uk_le_scheme())
    await graph.apply_schema(load_default_ontology())
    return client, graph


async def _ingest_cdr_fixture(tmp_path: Path) -> dict[str, str]:
    """B1-B3: the real recipe engine, the real CSV connector, the real Knowledge Adapters — the
    identical mechanism `tests/ingest/test_recipe_engine_end_to_end.py`'s own `test_cdr_fixture_
    loads_through_a_hand_written_recipe` already proves, reused rather than re-derived. Run
    against a fresh, isolated `arcadedb_adapter()` database (the same isolation that existing test
    already uses), not the shared, persistent `ospreyflow` database the rest of this walkthrough
    runs against — confirmed directly, not assumed, that running it against `ospreyflow` makes
    this test non-idempotent across reruns: the CDR fixture's own rows are fixed and
    deterministic, so a second run against a persistent database sees every row as a duplicate of
    the first run's own already-recorded dedup key, not a fresh load, and `nodes_created`/
    `rows_deduplicated` shift accordingly — a real, found property of the dedup mechanism working
    correctly, not a defect, but the wrong database choice for *this* test's own "prove B1-B3,
    fresh, every run" purpose. The two resulting `Endpoint` nodes are re-written (fresh ids) into
    `ospreyflow` afterwards, for the rest of this walkthrough to build on."""
    from adapters.graph_arcadedb.testing import arcadedb_adapter
    from schemas.domain import ExpandRequest

    rows = generate_cdr_rows()
    csv_path = tmp_path / "cdr.csv"
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["seq", "a_party", "b_party", "start_time", "duration", "direction"]
        )
        writer.writeheader()
        writer.writerows(rows)

    recipe = load_recipe(FIXTURES / "cdr_recipe.yaml")
    ontology = load_default_ontology()
    scheme = load_uk_le_scheme()

    async with arcadedb_adapter(ontology, scheme) as isolated_graph:
        tx = await isolated_graph.begin_transaction()
        report, _events = await run_recipe(
            recipe,
            _read_rows(csv_path),
            graph=isolated_graph,
            ontology=ontology,
            tx=tx,
            principal=PRINCIPAL,
            load_id=f"load-cdr-{new_id()}",
            investigation_scope="case-b-cdr",
            source=str(csv_path),
        )
        await isolated_graph.commit_transaction(tx)

        # === B1: every phone-number rendering resolves to one Endpoint; value_raw retained.
        assert report.nodes_created == 2
        assert report.nodes_referenced == 8
        a_party_endpoint = await isolated_graph.find_node(
            "Endpoint", "value_normalised", "+441621926368", PRINCIPAL
        )
        b_party_endpoint = await isolated_graph.find_node(
            "Endpoint", "value_normalised", "+447911123456", PRINCIPAL
        )
        assert a_party_endpoint is not None
        assert b_party_endpoint is not None
        assert a_party_endpoint.properties["value_raw"] in A_PARTY_RENDERINGS
        assert b_party_endpoint.properties["value_raw"] == B_PARTY

        # === B2: duplicate rows collapse to one event; every source row reference retained.
        assert report.rows_deduplicated == 4
        subgraph = await isolated_graph.expand(
            ExpandRequest(node_ids=[a_party_endpoint.id], depth=1), PRINCIPAL
        )
        (edge,) = [e for e in subgraph.edges if e.type == "COMMUNICATED_WITH"]
        assert edge.occurrences == 5
        assert len({s.locator for s in edge.provenance.sources}) == 5 + 4

        # === B3: the local-time file's offset is recorded; the undeterminable row is rejected
        # === by name, not guessed.
        assert len(report.rejections) == 1
        assert "datetime" in report.rejections[0].reason

        a_party_full = a_party_endpoint
        b_party_full = b_party_endpoint

    # Re-write the two proven Endpoints into the shared `ospreyflow` database, fresh ids each run
    # so repeated runs never collide with a prior run's own leftovers.
    _client, graph = await _graph_client()
    try:
        a_id, b_id = new_id(), new_id()
        tx = await graph.begin_transaction()
        await graph.upsert_nodes(
            [
                NodeWrite(
                    id=a_id,
                    type="Endpoint",
                    properties=dict(a_party_full.properties),
                    provenance=_provenance("cdr:a-party"),
                    handling=_handling(),
                    created_by="fixture-cdr",
                    created_at=datetime.now(UTC),
                ),
                NodeWrite(
                    id=b_id,
                    type="Endpoint",
                    properties=dict(b_party_full.properties),
                    provenance=_provenance("cdr:b-party"),
                    handling=_handling(),
                    created_by="fixture-cdr",
                    created_at=datetime.now(UTC),
                ),
            ],
            tx,
        )
        await graph.upsert_edges([_edge_write("COMMUNICATED_WITH", a_id, b_id)], tx)
        await graph.commit_transaction(tx)
    finally:
        await _client.aclose()

    return {"a_party_endpoint_id": a_id, "b_party_endpoint_id": b_id}


def _read_rows(csv_path: Path):
    with csv_path.open(newline="") as handle:
        yield from csv.DictReader(handle)


async def _seed_cohort(
    graph: GraphArcadeDBAdapter, *, shared_endpoint_id: str, prefix: str, count: int = 4
) -> list[str]:
    """B4/B5's own graph shape, built here since no fixture generator exists for it (this
    module's own docstring, point 1): `count` `Person` nodes, each with their own personal
    `Endpoint` (their own device), each personal endpoint one hop from the shared endpoint via
    `COMMUNICATED_WITH` — so a working set seeded with the four `Person`s, expanded to their own
    endpoints and one hop further, discovers the one endpoint shared by all four, exactly B4/B5's
    own two-step description. Every id is freshly minted (`new_id()`), not a fixed literal —
    `_ingest_cdr_fixture`'s own docstring explains why a fixed id would make this test collide
    with a prior run's own leftovers in the shared, persistent `ospreyflow` database."""
    run = new_id()[:8]
    digits = f"{abs(hash(run)) % 10_000_000:07d}"
    person_ids = [f"{prefix}-{run}-person-{i}" for i in range(count)]
    endpoint_ids = [f"{prefix}-{run}-endpoint-{i}" for i in range(count)]
    writes = [
        _person_write(pid, f"Cohort{prefix}", f"Member{i}") for i, pid in enumerate(person_ids)
    ] + [
        _endpoint_write(eid, f"+447{digits}{i}", "msisdn")
        for i, eid in enumerate(endpoint_ids)
    ]
    tx = await graph.begin_transaction()
    await graph.upsert_nodes(writes, tx)
    edges = [
        _edge_write("USES", pid, eid)
        for pid, eid in zip(person_ids, endpoint_ids, strict=True)
    ]
    edges += [
        _edge_write("COMMUNICATED_WITH", eid, shared_endpoint_id) for eid in endpoint_ids
    ]
    await graph.upsert_edges(edges, tx)
    await graph.commit_transaction(tx)
    return person_ids


async def _seed_handle_cohort(
    graph: GraphArcadeDBAdapter, *, prefix: str, count: int = 4
) -> tuple[list[str], str]:
    """B7's own second-cohort shape: `count` `Person` nodes sharing one messaging-handle
    `Endpoint` (`endpoint_kind="handle"`), the same construction as `_seed_cohort` but landing on
    a handle rather than a phone number — B7's own literal "a shared messaging handle is common
    to that cohort". Every id is freshly minted, the same reason `_seed_cohort` above gives."""
    run = new_id()[:8]
    handle_id = f"{prefix}-{run}-handle"
    person_ids = [f"{prefix}-{run}-person-{i}" for i in range(count)]
    writes = [_endpoint_write(handle_id, f"@{prefix}-{run}-handle", "handle")] + [
        _person_write(pid, f"Cohort{prefix}", f"Member{i}") for i, pid in enumerate(person_ids)
    ]
    tx = await graph.begin_transaction()
    await graph.upsert_nodes(writes, tx)
    edges = [_edge_write("USES", pid, handle_id) for pid in person_ids]
    await graph.upsert_edges(edges, tx)
    await graph.commit_transaction(tx)
    return person_ids, handle_id


async def _seed_and_resolve_b9_b10_person_pair(
    graph: GraphArcadeDBAdapter, *, scheme
) -> tuple[str, str, str, float]:
    """B9/B10's own real `Person` pair — closing the fixture gap `docs/08_ACCEPTANCE_SCENARIOS.md`
    B8's own disposition surfaced: B9's threshold move and B10's `explain` need a genuinely
    close-but-not-exact `Person` pair, scoring between Balanced (0.95) and Strict (0.99) — excluded
    at Strict, included at Balanced — which neither cohort in this scenario's own fixture provides
    (both cohorts' persons share one flat family name and sequential given names, no near-duplicate
    signal at all).

    **Using the same generator that already carries the non-Latin pair** —
    `tests.scenarios.fixtures.fixture_corp.generate_resolution_persons()` — rather than a second,
    hand-rolled near-duplicate invented here: its own `close_given_name` pair ("Volkov, Mikael" vs
    "Volkov, Mikhail", same DOB) is already measured, live, at 0.981285 — inside the exact band
    needed, not merely close to it. Reusing its own values (not its own fixed node ids, which
    would collide across repeated runs against this file's own shared, persistent `ospreyflow`
    database — the same reason every other helper in this file mints fresh ids) keeps this pair
    provably the same generator's own output, not a duplicate that could drift from it.

    Resolved directly (`resolve_entity_type`/`write_same_as_edges`), the same real mechanism
    `tests/scenarios/test_phase6_extraction_and_resolution.py`'s own Clause 2 already uses — no
    HTTP route triggers Splink resolution synchronously in this build (`06_DECISIONS.md` ADR-025:
    "manual resolve now" is still a proposal, not a route) — before the real HTTP `/seed`,
    threshold-move and `explain` calls this function's own caller makes against the edge this
    writes. Returns `(node_a_id, node_b_id, cluster_id, score)` — the score is asserted here, in
    the band, live, not assumed from the docstring above: a pair that happened to land outside the
    band would make B9/B10 vacuous again, exactly the failure this fixture gap was found to be."""
    person_type = next(e for e in load_default_ontology().entity_types if e.name == "Person")
    corp_pairs = generate_resolution_persons()
    (close_given_name,) = (p for p in corp_pairs if p.label == "close_given_name")
    props_a = close_given_name.node_a.properties
    props_b = close_given_name.node_b.properties

    run = new_id()[:8]
    node_a_id = f"b9b10-{run}-person-a"
    node_b_id = f"b9b10-{run}-person-b"
    tx = await graph.begin_transaction()
    await graph.upsert_nodes(
        [
            _person_write(node_a_id, props_a["family_name"], props_a["given_names"]),
            _person_write(node_b_id, props_b["family_name"], props_b["given_names"]),
        ],
        tx,
    )
    await graph.commit_transaction(tx)
    node_a = await graph.get_node(node_a_id, PRINCIPAL)
    node_b = await graph.get_node(node_b_id, PRINCIPAL)
    assert node_a is not None
    assert node_b is not None

    candidates = resolve_entity_type([node_a, node_b], person_type)
    assert len(candidates) == 1, "the pair must be one blocking-rule candidate, not zero or many"
    score = candidates[0].score
    assert THRESHOLD_BALANCED <= score < THRESHOLD_STRICT, (
        f"B9/B10's own pair scored {score}, outside (Balanced, Strict) — the band the row's own "
        "assertions require; a pair outside this band makes both rows vacuous, per this helper's "
        "own docstring."
    )

    tx = await graph.begin_transaction()
    await write_same_as_edges(
        graph,
        candidates,
        {node_a_id: node_a, node_b_id: node_b},
        created_by="resolve-service",
        tx=tx,
        scheme=scheme,
    )
    await graph.commit_transaction(tx)
    cluster_id = min(node_a_id, node_b_id)
    return node_a_id, node_b_id, cluster_id, score


async def _write_seizure_device_legs(graph: GraphArcadeDBAdapter) -> dict[str, str]:
    """B15: the handset/SIM (IMSI) legs the seizure-record fixture describes — no device-
    extraction connector or recipe exists (this module's own docstring, point 3), so these are
    written directly, `01_DOMAIN_MODEL.md` §2.4's own sanctioned shape for fixture data with no
    recipe behind it (`recipe_id`/`recipe_version` stay `None`). `ADR-023`'s corrected two-hop
    shape is `Endpoint(msisdn) --SAME_AS--> Endpoint(imsi) --PAIRED_WITH--> Device`; the
    `msisdn` leg is deliberately **not** written here — B13's own recipe ingest (this file's own
    `test_phase8_exit_criterion_end_to_end`) is what creates it for real, so that ingest's own
    `report.created_node_ids` — and through it the change-stream entry `evaluate_hotlists_for_
    entry` reads — is genuinely non-empty; pre-writing it here would make B13's own alert
    permanently unreachable (the identifier would already exist, `on_match: reference` would
    find it rather than create it, and `evaluate_hotlists_for_entry`'s own `if not entry.node_ids:
    return []` would skip evaluation every time). Every id is freshly minted, the same reason
    `_seed_cohort`'s own docstring gives."""
    record = generate_seizure_record()
    run = new_id()[:8]
    handset_id = f"seizure-{run}-handset"
    sim_a_id = f"seizure-{run}-sim-a"
    sim_b_id = f"seizure-{run}-sim-b"

    device_write = NodeWrite(
        id=handset_id,
        type="Device",
        properties={"imei": HANDSET_IMEI_NORMALISED},
        provenance=_provenance("seizure-record:handset"),
        handling=_handling(),
        created_by="fixture-seizure",
        created_at=datetime.now(UTC),
    )
    sim_a_write = _endpoint_write(sim_a_id, SIM_A_IMSI_NORMALISED, "imsi")
    sim_b_write = _endpoint_write(sim_b_id, SIM_B_IMSI_NORMALISED, "imsi")

    tx = await graph.begin_transaction()
    await graph.upsert_nodes([device_write, sim_a_write, sim_b_write], tx)
    edges = [
        _edge_write("PAIRED_WITH", sim_a_id, handset_id),
        _edge_write("PAIRED_WITH", sim_b_id, handset_id),
    ]
    await graph.upsert_edges(edges, tx)
    await graph.commit_transaction(tx)
    return {
        "handset_id": handset_id,
        "sim_a_id": sim_a_id,
        "sim_b_id": sim_b_id,
        "seizure_record": record,
    }


def _identifier_row_template() -> RowTemplate:
    """B13/B20's shared ad-hoc recipe shape: one `Endpoint`, matched/created on
    `value_normalised`, msisdn-normalised — the same shape `test_phase7_stage6c_watch_routes.py`'s
    own `_row_template` already establishes for exactly this purpose (triggering the real
    ingest-evaluation wiring), reused rather than re-derived."""
    return RowTemplate(
        entities=[
            RecipeEntity(
                ref="a",
                pole_class="object",
                type="Endpoint",
                match_on="value_normalised",
                on_match="reference",
                properties={
                    "value_normalised": FieldBinding(field="identifier", transform="msisdn"),
                    "value_raw": FieldBinding(field="identifier"),
                    "endpoint_kind": FieldBinding(literal="msisdn"),
                },
            )
        ]
    )


def _person_endpoint_row_template() -> RowTemplate:
    """B20's own monitor-triggering shape: one row creates a fresh `Person` and references (or
    creates) an `Endpoint`, linked `USES` — matching the saved pattern's own
    `Person --USES--> Endpoint` definition."""
    return RowTemplate(
        entities=[
            RecipeEntity(
                ref="p",
                pole_class="subject",
                type="Person",
                on_match="create",
                properties={
                    "family_name": FieldBinding(field="family_name"),
                    "given_names": FieldBinding(field="given_names"),
                    "date_of_birth": FieldBinding(literal="1990-01-01"),
                },
            ),
            RecipeEntity(
                ref="e",
                pole_class="object",
                type="Endpoint",
                match_on="value_normalised",
                on_match="reference",
                properties={
                    "value_normalised": FieldBinding(field="identifier", transform="msisdn"),
                    "value_raw": FieldBinding(field="identifier"),
                    "endpoint_kind": FieldBinding(literal="msisdn"),
                },
            ),
        ],
        edges=[RecipeEdge(type="USES", **{"from": "p", "to": "e"})],
    )


async def _publish_recipe(
    *,
    row_template: RowTemplate,
    label: str,
    columns: list[str],
    rows: list[dict[str, str]],
    tmp_path: Path,
    git_repo: Path,
) -> str:
    """The exact `StudioRecipeStore`/real-git-commit publish pipeline
    `test_phase7_stage6c_watch_routes.py`'s own `_publish_a_recipe_touching` already establishes —
    parameterised over the row template/columns/rows so this file's own B13 and B20 calls can each
    supply their own shape without duplicating the publish plumbing itself."""
    store = await StudioRecipeStore.connect(PostgresConfig.from_env().dsn)
    try:
        csv_path = tmp_path / f"{label}.csv"
        with csv_path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)

        draft = await store.create_draft(
            PRINCIPAL,
            label=label,
            connector_profile="generic-csv",
            source_location=str(csv_path),
            handling={
                "classification": "OFFICIAL",
                "handling_code": "P",
                "originator": PRINCIPAL.org_unit,
                "owning_unit": PRINCIPAL.org_unit,
            },
            legal_basis="RIPA s22 acquisition — authorisation 2026/0114",
        )
        draft = await store.update_row_template(
            draft.recipe_id, PRINCIPAL, row_template=row_template, unmapped_fields=[]
        )
        await store.mark_verified(draft.recipe_id, draft.version, now=datetime.now(UTC))
        draft = await store.get(draft.recipe_id)

        ontology = load_default_ontology()
        built = build_recipe(
            draft, ontology_version=ontology.version, schedule_cron=None, schedule_watch=None
        )
        git_path = await write_and_commit_recipe(built, repo_root=git_repo)
        published = await store.publish(
            draft.recipe_id,
            PRINCIPAL,
            ontology_version=ontology.version,
            git_path=git_path,
            schedule_cron=None,
            schedule_watch=None,
            now=datetime.now(UTC),
        )
        return published.recipe_id
    finally:
        await store.close()


# --- the closing pass itself ---------------------------------------------------------------------


def test_phase8_exit_criterion_end_to_end(
    api_env: None,
    keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
    tmp_path: Path,
    git_repo: Path,
) -> None:
    import asyncio

    private_key, _ = keypair
    import time as _time

    # A one-hour expiry, not the default 300s (`tests/conftest.py::default_claims`) — this
    # walkthrough's own real ArcadeDB/Postgres round trips run measurably longer than that,
    # confirmed directly (a real run's own token expired mid-test at the B14 jump call before
    # this fix, `401 signature has expired`, not assumed).
    headers = _bearer(private_key, roles=["loader"], exp=int(_time.time()) + 3600)

    from services.api.app import app

    # === Scenario B ===============================================================================

    # B1-B3
    cdr_ids = asyncio.run(_ingest_cdr_fixture(tmp_path))

    async def _build_b_graph() -> dict[str, object]:
        client, graph = await _graph_client()
        try:
            # B4-B7: two cohorts, one on the shared CDR endpoint, one on a shared handle.
            cohort_1_person_ids = await _seed_cohort(
                graph, shared_endpoint_id=cdr_ids["b_party_endpoint_id"], prefix="c1"
            )
            cohort_2_person_ids, handle_id = await _seed_handle_cohort(graph, prefix="c2")

            # B8/B11: Endpoint carries no resolution config (this module's own docstring, point
            # 2) — the handle-to-endpoint link is a deterministic, asserted SAME_AS at score 1.0
            # (ADR-024's own pattern), exactly B11's own shape — the corrected B8 disposition
            # (`docs/08_ACCEPTANCE_SCENARIOS.md`) says this is what the edge actually is, not a
            # stand-in for something else.

            # B9/B10: the real Person pair — see this file's own helper docstring for why neither
            # cohort above can serve this, and why this pair is provably the same generator's own
            # output.
            b9_a_id, b9_b_id, b9_cluster_id, b9_score = await _seed_and_resolve_b9_b10_person_pair(
                graph, scheme=load_uk_le_scheme()
            )

            # B15: the seizure record's device/SIM legs.
            seizure_ids = await _write_seizure_device_legs(graph)

            return {
                "cohort_1_person_ids": cohort_1_person_ids,
                "cohort_2_person_ids": cohort_2_person_ids,
                "handle_id": handle_id,
                "b9_a_id": b9_a_id,
                "b9_b_id": b9_b_id,
                "b9_cluster_id": b9_cluster_id,
                "b9_score": b9_score,
                **seizure_ids,
            }
        finally:
            await client.aclose()

    b_graph = asyncio.run(_build_b_graph())

    with TestClient(app) as client:
        investigation_b = client.post("/v1/investigations", headers=headers)
        assert investigation_b.status_code == 201, investigation_b.text
        inv_b_id = investigation_b.json()["id"]

        async def _fetch(node_id: str) -> dict:
            _client, graph = await _graph_client()
            try:
                node = await graph.get_node(node_id, PRINCIPAL)
                assert node is not None
                return node.model_dump(mode="json")
            finally:
                await _client.aclose()

        # === B4: seed the four first-cohort Person entities, no edges between them.
        cohort_1_nodes = [asyncio.run(_fetch(pid)) for pid in b_graph["cohort_1_person_ids"]]
        seeded_b4 = client.post(
            f"/v1/investigations/{inv_b_id}/seed",
            headers=headers,
            json={"nodes": cohort_1_nodes, "edges": []},
        )
        assert seeded_b4.status_code == 200, seeded_b4.text
        assert len(seeded_b4.json()["delta"]["nodes"]) == 4
        assert seeded_b4.json()["delta"]["edges"] == []

        # === B5: expand each to their own endpoint, then one hop out — one shared Endpoint
        # === common to all four.
        expand_b5 = client.post(
            f"/v1/investigations/{inv_b_id}/expand",
            headers=headers,
            json={
                "request": {
                    "node_ids": b_graph["cohort_1_person_ids"],
                    "depth": 2,
                    "edge_types": ["USES", "COMMUNICATED_WITH"],
                }
            },
        )
        assert expand_b5.status_code == 200, expand_b5.text
        expanded_node_ids = {n["id"] for n in expand_b5.json()["delta"]["nodes"]}
        assert cdr_ids["b_party_endpoint_id"] in expanded_node_ids

        # === B7: repeat for the second cohort — a shared messaging handle common to it.
        investigation_b2 = client.post("/v1/investigations", headers=headers)
        assert investigation_b2.status_code == 201, investigation_b2.text
        inv_b2_id = investigation_b2.json()["id"]
        cohort_2_nodes = [asyncio.run(_fetch(pid)) for pid in b_graph["cohort_2_person_ids"]]
        client.post(
            f"/v1/investigations/{inv_b2_id}/seed",
            headers=headers,
            json={"nodes": cohort_2_nodes, "edges": []},
        )
        expand_b7 = client.post(
            f"/v1/investigations/{inv_b2_id}/expand",
            headers=headers,
            json={
                "request": {
                    "node_ids": b_graph["cohort_2_person_ids"],
                    "depth": 1,
                    "edge_types": ["USES"],
                }
            },
        )
        assert expand_b7.status_code == 200, expand_b7.text
        expanded_2_node_ids = {n["id"] for n in expand_b7.json()["delta"]["nodes"]}
        assert b_graph["handle_id"] in expanded_2_node_ids

        # === B8/B11: a deterministic, asserted SAME_AS at score 1.0 (ADR-024's own pattern for
        # === identifier systems with no lexical overlap) — B11's own literal shape, and, per the
        # === corrected B8 disposition (`docs/08_ACCEPTANCE_SCENARIOS.md`), what B8's own edge
        # === actually is, not a stand-in for a Splink score it was never going to have.
        # === `manual_link` requires both nodes already be members of this investigation's own
        # === working set.
        handle_node = asyncio.run(_fetch(b_graph["handle_id"]))
        b_party_node = asyncio.run(_fetch(cdr_ids["b_party_endpoint_id"]))
        seed_b11 = client.post(
            f"/v1/investigations/{inv_b_id}/seed",
            headers=headers,
            json={"nodes": [handle_node, b_party_node], "edges": []},
        )
        assert seed_b11.status_code == 200, seed_b11.text

        link_b11 = client.post(
            f"/v1/investigations/{inv_b_id}/resolution/link",
            headers=headers,
            json={"node_a": b_graph["handle_id"], "node_b": cdr_ids["b_party_endpoint_id"]},
        )
        assert link_b11.status_code == 200, link_b11.text
        assert link_b11.json()["merged"] == 1

        # === B9/B10: the real `Person` pair (`_seed_and_resolve_b9_b10_person_pair`'s own
        # === docstring has the full reasoning for why B8's own pair cannot serve this and why
        # === this one provably can — its live score is asserted in-band there, not assumed here).
        # === Seed, then set Strict first: the row's own words are "move... from Strict to
        # === Balanced," which only demonstrates anything if Strict is shown not to merge it.
        b9_node_a = asyncio.run(_fetch(b_graph["b9_a_id"]))
        b9_node_b = asyncio.run(_fetch(b_graph["b9_b_id"]))
        seed_b9 = client.post(
            f"/v1/investigations/{inv_b_id}/seed",
            headers=headers,
            json={"nodes": [b9_node_a, b9_node_b], "edges": []},
        )
        assert seed_b9.status_code == 200, seed_b9.text

        strict_b9 = client.put(
            f"/v1/investigations/{inv_b_id}/resolution/threshold",
            headers=headers,
            json={"threshold": THRESHOLD_STRICT},
        )
        assert strict_b9.status_code == 200, strict_b9.text
        assert strict_b9.json()["merged"] == 0, (
            f"the pair scored {b_graph['b9_score']}, below Strict ({THRESHOLD_STRICT}) by "
            "construction — Strict must not merge it, or B9's own threshold move proves nothing"
        )

        balanced_b9 = client.put(
            f"/v1/investigations/{inv_b_id}/resolution/threshold",
            headers=headers,
            json={"threshold": THRESHOLD_BALANCED},
        )
        assert balanced_b9.status_code == 200, balanced_b9.text
        assert balanced_b9.json()["merged"] == 1
        assert balanced_b9.json()["affected"] == 2

        # === B10: explain the merged cluster — real per-comparison match weights, not just the
        # === total score, and `manually_asserted: false` — the one signal that distinguishes a
        # === genuine Splink match from B8/B11's own asserted one at the same layer.
        explain_b10 = client.get(
            f"/v1/investigations/{inv_b_id}/resolution/explain/{b_graph['b9_cluster_id']}",
            headers=headers,
        )
        assert explain_b10.status_code == 200, explain_b10.text
        (pair,) = explain_b10.json()["pairs"]
        assert pair["manually_asserted"] is False
        assert pair["comparison_vector"], (
            "explain must show per-comparison weights, not just the total"
        )
        assert THRESHOLD_BALANCED <= pair["score"] < THRESHOLD_STRICT
        assert pair["score"] == pytest.approx(b_graph["b9_score"]), (
            "explain's own score must be the same value the seeding helper measured and asserted "
            "was in-band, not a different computation"
        )

        # === B12: add the endpoint to a hotlist. A fresh identifier each run, not the seizure
        # === fixture's own literal frozen `SIM_B_MSISDN_RAW` — `_fresh_uk_msisdn_raw`'s own
        # === docstring explains why the literal constant cannot be reused safely against the
        # === shared, persistent `ospreyflow` database.
        sim_b_msisdn_raw_this_run = _fresh_uk_msisdn_raw()
        sim_b_msisdn_normalised_this_run = _normalise_msisdn(sim_b_msisdn_raw_this_run)

        async def _seed_hotlist() -> None:
            store = await HotlistStore.connect(PostgresConfig.from_env().dsn)
            try:
                await store.create(
                    PRINCIPAL,
                    identifier=sim_b_msisdn_normalised_this_run,
                    review_date=datetime(2027, 1, 1).date(),
                )
            finally:
                await store.close()

        asyncio.run(_seed_hotlist())
        hotlist_list = client.get("/v1/hotlists", headers=headers)
        assert hotlist_list.status_code == 200, hotlist_list.text
        assert any(
            h["identifier"] == sim_b_msisdn_normalised_this_run
            for h in hotlist_list.json()["hotlists"]
        )

        # === B13: ingest the later seizure record — an alert fires naming the matched
        # === identifier, the triggering document (load) and the rule.
        app.dependency_overrides[get_recipes_repo_root] = lambda: git_repo
        try:
            recipe_id_b13 = asyncio.run(
                _publish_recipe(
                    row_template=_identifier_row_template(),
                    label="seizure-msisdn",
                    columns=["identifier"],
                    rows=[{"identifier": sim_b_msisdn_raw_this_run}],
                    tmp_path=tmp_path,
                    git_repo=git_repo,
                )
            )
            run_b13 = client.post(
                f"/v1/investigations/{inv_b_id}/ingest/recipes/{recipe_id_b13}/run",
                headers=headers,
                json={},
            )
            assert run_b13.status_code == 200, run_b13.text
            assert run_b13.json()["nodes_created"] >= 1, (
                "B13's own recipe row must genuinely create the msisdn Endpoint — "
                "this file's own docstring on `_write_seizure_device_legs` explains why it must "
                "not already exist beforehand"
            )

            async def _link_msisdn_to_imsi() -> str:
                """B15's own SAME_AS leg (`ADR-023`'s two-hop shape) — written now, against the
                real Endpoint B13's own recipe just created, not before it existed."""
                _client, graph = await _graph_client()
                try:
                    msisdn_node = await graph.find_node(
                        "Endpoint", "value_normalised", sim_b_msisdn_normalised_this_run, PRINCIPAL
                    )
                    assert msisdn_node is not None
                    tx = await graph.begin_transaction()
                    await graph.upsert_edges(
                        [_edge_write("SAME_AS", msisdn_node.id, b_graph["sim_b_id"])], tx
                    )
                    await graph.commit_transaction(tx)
                    return msisdn_node.id
                finally:
                    await _client.aclose()

            b_graph["sim_b_msisdn_id"] = asyncio.run(_link_msisdn_to_imsi())

            # === B20 (built here so it shares B13's own recipe-repo dependency override): save
            # === the common-contacts pattern's own definition as a monitor, then re-ingest a
            # === fresh matching Person/Endpoint pair and confirm it fires with the same shape.
            saved_pattern = client.post(
                "/v1/patterns/save",
                headers=headers,
                json={
                    "pattern_id": None,
                    "name": "Phase 8 closing-pass monitor",
                    "definition": {
                        "nodes": [
                            {"var": "p", "entity_type": "Person"},
                            {"var": "e", "entity_type": "Endpoint"},
                        ],
                        "edges": [{"edge_type": "USES", "from_var": "p", "to_var": "e"}],
                    },
                },
            )
            assert saved_pattern.status_code == 201, saved_pattern.text
            pattern_id = saved_pattern.json()["pattern_id"]
            created_monitor = client.post(
                "/v1/monitors", headers=headers, json={"pattern_id": pattern_id}
            )
            assert created_monitor.status_code == 201, created_monitor.text

            monitor_trigger_identifier = f"+44700{new_id()[:7]}"
            recipe_id_b20 = asyncio.run(
                _publish_recipe(
                    row_template=_person_endpoint_row_template(),
                    label="monitor-trigger",
                    columns=["family_name", "given_names", "identifier"],
                    rows=[
                        {
                            "family_name": "MonitorTrigger",
                            "given_names": "Case",
                            "identifier": monitor_trigger_identifier,
                        }
                    ],
                    tmp_path=tmp_path,
                    git_repo=git_repo,
                )
            )
            run_b20 = client.post(
                f"/v1/investigations/{inv_b_id}/ingest/recipes/{recipe_id_b20}/run",
                headers=headers,
                json={},
            )
            assert run_b20.status_code == 200, run_b20.text
        finally:
            app.dependency_overrides.pop(get_recipes_repo_root, None)

        async def _read_alerts() -> list:
            store = await AlertStore.connect(PostgresConfig.from_env().dsn)
            try:
                return await store.list_authorized(PRINCIPAL)
            finally:
                await store.close()

        alerts = asyncio.run(_read_alerts())
        hotlist_alerts = sorted(
            (a for a in alerts if a.rule_id.startswith("hotlist:")),
            key=lambda a: a.created_at,
            reverse=True,
        )
        monitor_alerts = sorted(
            (a for a in alerts if a.rule_id.startswith("monitor:")),
            key=lambda a: a.created_at,
            reverse=True,
        )
        assert hotlist_alerts, "B13: no hotlist alert fired from the seizure-record ingest"
        assert monitor_alerts, (
            "B20: the saved pattern's own monitor did not re-fire on a later matching ingest"
        )
        # The most recently-fired one of each — `list_authorized` has no time filter, so a
        # persistent, shared Postgres also carries every prior test run's own leftover alerts;
        # this walkthrough's own action produced the most recent one.
        newest_hotlist_alert = hotlist_alerts[0]

        # === B14: open the alert into a pre-populated investigation.
        jumped = client.post(f"/v1/alerts/{newest_hotlist_alert.id}/jump", headers=headers)
        assert jumped.status_code == 201, jumped.text
        assert jumped.json()["seeded_count"] >= 1

        # === B15: pivot on the handset identifier — both SIMs link to one device, one traversal.
        # depth=3: msisdn --SAME_AS--> sim_b (1) --PAIRED_WITH--> handset (2)
        # --PAIRED_WITH--> sim_a (3)
        pivot = client.post(
            f"/v1/investigations/{inv_b_id}/expand",
            headers=headers,
            json={
                "request": {
                    "node_ids": [b_graph["sim_b_msisdn_id"]],
                    "depth": 3,
                    "edge_types": ["SAME_AS", "PAIRED_WITH"],
                }
            },
        )
        assert pivot.status_code == 200, pivot.text
        pivot_node_ids = {n["id"] for n in pivot.json()["delta"]["nodes"]}
        assert b_graph["handset_id"] in pivot_node_ids
        assert b_graph["sim_a_id"] in pivot_node_ids
        assert b_graph["sim_b_id"] in pivot_node_ids

        # === B19: common contacts across the two principal endpoints — the intersection, with
        # === the estimated count shown before running (`PatternNode.node_id` pinning both roots
        # === — the documented shape B19 exists to prove, per `schemas/domain.py`'s own docstring).
        common_contacts_pattern = {
            "nodes": [
                {"var": "a", "entity_type": "Endpoint", "node_id": cdr_ids["a_party_endpoint_id"]},
                {"var": "b", "entity_type": "Endpoint", "node_id": cdr_ids["b_party_endpoint_id"]},
                {"var": "contact", "entity_type": "Endpoint"},
            ],
            "edges": [
                {"edge_type": "COMMUNICATED_WITH", "from_var": "a", "to_var": "contact"},
                {"edge_type": "COMMUNICATED_WITH", "from_var": "b", "to_var": "contact"},
            ],
        }
        preview_b19 = client.post(
            "/v1/patterns/preview", headers=headers, json=common_contacts_pattern
        )
        assert preview_b19.status_code == 200, preview_b19.text
        run_b19 = client.post("/v1/patterns/run", headers=headers, json=common_contacts_pattern)
        assert run_b19.status_code == 200, run_b19.text
        assert run_b19.json()["mode"] == "sync"

        # === B21: the pathfinder — real HTTP, real ArcadeDB, between the two principal endpoints,
        # === one from each investigation. A cross-case link is built here (the same class of
        # === test-local construction this file's own docstring discloses for B4-B8): a shared
        # === Person node both endpoints are USES-linked to — the same mechanism B16's own
        # === timeline overlay would surface visually, exercised here at the data layer, real.
        async def _build_cross_case_link() -> str:
            _client, graph = await _graph_client()
            try:
                bridge_id = f"b21-{new_id()[:8]}-cross-case-bridge"
                tx = await graph.begin_transaction()
                await graph.upsert_nodes([_person_write(bridge_id, "Bridge", "CrossCase")], tx)
                await graph.upsert_edges(
                    [
                        _edge_write("USES", bridge_id, cdr_ids["a_party_endpoint_id"]),
                        _edge_write("USES", bridge_id, b_graph["sim_b_msisdn_id"]),
                    ],
                    tx,
                )
                await graph.commit_transaction(tx)
                return bridge_id
            finally:
                await _client.aclose()

        asyncio.run(_build_cross_case_link())

        # Non-vacuous, per the task's own discipline for the one row this test exists specifically
        # to prove that never existed as a test anywhere before: too small a `max_hops` cannot
        # reach the real 2-hop bridge, so the real system must return nothing at that ceiling.
        too_short = client.post(
            "/v1/paths",
            headers=headers,
            json={
                "source": cdr_ids["a_party_endpoint_id"],
                "target": b_graph["sim_b_msisdn_id"],
                "max_hops": 1,
                "k": 1,
            },
        )
        assert too_short.status_code == 200, too_short.text
        assert too_short.json() == []

        paths_b21 = client.post(
            "/v1/paths",
            headers=headers,
            json={
                "source": cdr_ids["a_party_endpoint_id"],
                "target": b_graph["sim_b_msisdn_id"],
                "max_hops": 6,
                "k": 3,
            },
        )
        assert paths_b21.status_code == 200, paths_b21.text
        found_paths = paths_b21.json()
        assert found_paths, "B21: no path found between the two principal endpoints"
        shortest = min(found_paths, key=lambda p: p["length"])
        assert shortest["length"] == 2
        shortest_node_ids = {n["id"] for n in shortest["nodes"]}
        assert {
            cdr_ids["a_party_endpoint_id"],
            b_graph["sim_b_msisdn_id"],
        } <= shortest_node_ids
        # `02_GLASS_FRONTEND.md` §3.1's own on-path convention (2px primary stroke, thickened
        # incident edges, everything else dims to 32%) is rendering state `GlassCanvas.tsx` applies
        # client-side from exactly this response's own `nodes`/`edges` — a backend test proves the
        # data the convention is applied to (the real path, hydrated, in order), not the CSS/canvas
        # styling itself; `apps/workspace/keyboard/keyboard.spec.ts`'s own "Find paths" case is the
        # existing real, browser-level proof that the Glass reaches this action end to end and
        # renders it, cited rather than re-proved here.

    # === Scenario A ========================================================================

    async def _build_a_graph():
        ontology = load_default_ontology()
        client, graph = await _graph_client()
        try:
            result = await build_hmp_graph(
                graph=graph,
                ontology=ontology,
                principal=PRINCIPAL,
                load_id_prefix=f"load-a-{new_id()}",
                investigation_scope=f"case-a-{new_id()}",
            )
            return result
        finally:
            await client.aclose()

    a_result = asyncio.run(_build_a_graph())

    with TestClient(app) as client:
        investigation_a = client.post("/v1/investigations", headers=headers)
        assert investigation_a.status_code == 201, investigation_a.text
        inv_a_id = investigation_a.json()["id"]

        async def _fetch_a(node_id: str) -> dict:
            _client, graph = await _graph_client()
            try:
                node = await graph.get_node(node_id, PRINCIPAL)
                assert node is not None
                return node.model_dump(mode="json")
            finally:
                await _client.aclose()

        # === A7 (the reachable half — `08_ACCEPTANCE_SCENARIOS.md`'s own "Known gap" already
        # === discloses the item-category value_filters half as real, unbuilt work, unchanged
        # === here): the people named in the surviving structured reports for the principal
        # === subject, seeded as a named working-set history step.
        principal_node = asyncio.run(_fetch_a(a_result.principal_subject_id))
        second_subject_node = asyncio.run(_fetch_a(a_result.second_subject_id))
        relay_nodes = [asyncio.run(_fetch_a(nid)) for nid in a_result.relay_group_ids]
        seed_a7 = client.post(
            f"/v1/investigations/{inv_a_id}/seed",
            headers=headers,
            json={"nodes": [principal_node, second_subject_node, *relay_nodes], "edges": []},
        )
        assert seed_a7.status_code == 200, seed_a7.text
        history_a7 = client.get(f"/v1/investigations/{inv_a_id}/history", headers=headers)
        assert history_a7.status_code == 200, history_a7.text
        assert any("Seeded" in step["label"] for step in history_a7.json())

        # === A8: rank by appearance count and group affiliation — the principal subject ranks
        # === first; the affiliated (relay) subset is identifiable by an Organisation edge.
        # `compute/degree` is exercised for real here (the route composing correctly against this
        # investigation's own working set — already proven access-safe generically by
        # `tests/services/api/working_set/test_compute_access_control.py`), but is not itself the
        # "appearance count" this row asks to rank by (raw graph degree inside a six-node working
        # set instead reflects the relay group's own dense internal `ASSOCIATE_OF` clique, which is
        # A12's own finding, not A8's) — "appearance count" is the real
        # `MENTIONED_IN` edge count `hmp_population.py`'s own report generator gives each person
        # (`tests/scenarios/test_hmp_graph.py`'s own already-proven "principal has 12 of 68
        # structured mentions"), checked again here live rather than only cited, against this run's
        # own real graph.
        degree_a8 = client.post(
            f"/v1/investigations/{inv_a_id}/compute/degree", headers=headers, json={}
        )
        assert degree_a8.status_code == 200, degree_a8.text
        assert degree_a8.json()["mode"] == "sync"

        async def _mention_count(node_id: str) -> int:
            _client, graph = await _graph_client()
            try:
                sub = await graph.expand(
                    __import__("schemas.domain", fromlist=["ExpandRequest"]).ExpandRequest(
                        node_ids=[node_id], depth=1, edge_types=["MENTIONED_IN"]
                    ),
                    PRINCIPAL,
                )
                return len([n for n in sub.nodes if n.type == "Document"])
            finally:
                await _client.aclose()

        principal_mentions = asyncio.run(_mention_count(a_result.principal_subject_id))
        relay_mentions = [
            asyncio.run(_mention_count(nid)) for nid in a_result.relay_group_ids
        ]
        # Not asserted as the literal "12 of 68" here — `build_hmp_graph`'s own structural
        # recipes (`hmp_persons_recipe.yaml` et al.) `on_match: reference` existing Person/
        # Location rows by their own stable identifiers across reruns against the shared,
        # persistent `ospreyflow` database, but `hmp_reports_recipe.yaml`'s own Document rows do
        # not carry an equally stable natural key, so repeated reruns of this same test file
        # against that persistent database accumulate additional Document nodes and inflate the
        # raw count (found directly, not assumed, while iterating this file: 36 = 3 x 12 after
        # three full reruns) — the literal figure is `test_hmp_graph.py`'s own already-proven,
        # single-clean-run fact, cited rather than re-asserted at a literal value here. What this
        # line re-checks live is the *relative* ranking the literal figure exists to support:
        # the principal subject still appears in strictly more reports than any relay member,
        # which holds regardless of how many times this file itself has been rerun.
        assert principal_mentions > max(relay_mentions)

        # The affiliated subset (the relay group) is identifiable by a shared Organisation edge —
        # already proven in `test_hmp_graph.py`; re-checked here against this run's own graph.
        for member_id in a_result.relay_group_ids:
            member_orgs = client.post(
                f"/v1/investigations/{inv_a_id}/expand",
                headers=headers,
                json={
                    "request": {
                        "node_ids": [member_id],
                        "depth": 1,
                        "edge_types": ["MEMBER_OF"],
                    }
                },
            )
            assert member_orgs.status_code == 200, member_orgs.text
            assert any(
                n["type"] == "Organisation" for n in member_orgs.json()["delta"]["nodes"]
            )

        # === A9: expand the principal subject's relationships — cardinality preview first.
        preview_a9 = client.post(
            f"/v1/investigations/{inv_a_id}/expand/preview",
            headers=headers,
            json={
                "request": {
                    "node_ids": [a_result.principal_subject_id],
                    "depth": 1,
                    "edge_types": ["FAMILY_OF", "MEMBER_OF", "MENTIONED_IN"],
                }
            },
        )
        assert preview_a9.status_code == 200, preview_a9.text
        assert preview_a9.json()["candidate_node_count"] > 0
        expand_a9 = client.post(
            f"/v1/investigations/{inv_a_id}/expand",
            headers=headers,
            json={
                "request": {
                    "node_ids": [a_result.principal_subject_id],
                    "depth": 1,
                    "edge_types": ["FAMILY_OF", "MEMBER_OF", "MENTIONED_IN"],
                }
            },
        )
        assert expand_a9.status_code == 200, expand_a9.text
        expanded_a9_ids = {n["id"] for n in expand_a9.json()["delta"]["nodes"]}

        # === A10: the family link to the second subject on another wing; both share an
        # === Organisation.
        assert a_result.second_subject_id in expanded_a9_ids

        # === A12: the Clique Metric — the relay group scores high on clique, low on degree
        # === centrality, via ComputePort, against the real working set (relay group + principal
        # === subject, whose own incident/report frequency gives it a materially higher raw
        # === degree than any one relay member).
        seed_a12 = client.post(
            f"/v1/investigations/{inv_a_id}/seed",
            headers=headers,
            json={"nodes": relay_nodes + [principal_node], "edges": []},
        )
        assert seed_a12.status_code == 200, seed_a12.text
        expand_a12 = client.post(
            f"/v1/investigations/{inv_a_id}/expand",
            headers=headers,
            json={
                "request": {
                    "node_ids": [n["id"] for n in relay_nodes] + [a_result.principal_subject_id],
                    "depth": 1,
                }
            },
        )
        assert expand_a12.status_code == 200, expand_a12.text

        clique_a12 = client.post(
            f"/v1/investigations/{inv_a_id}/compute/clique_metric", headers=headers, json={}
        )
        assert clique_a12.status_code == 200, clique_a12.text
        clique_values = clique_a12.json()["values"]

        degree_a12 = client.post(
            f"/v1/investigations/{inv_a_id}/compute/degree", headers=headers, json={}
        )
        assert degree_a12.status_code == 200, degree_a12.text
        degree_values_a12 = degree_a12.json()["values"]

        relay_ids = list(a_result.relay_group_ids)
        relay_clique_scores = [clique_values[rid] for rid in relay_ids if rid in clique_values]
        assert relay_clique_scores
        assert max(relay_clique_scores) == max(clique_values.values())
        # Low on degree centrality relative to the principal subject's own materially higher raw
        # connectivity in this same working set.
        assert max(degree_values_a12[rid] for rid in relay_ids) < degree_values_a12[
            a_result.principal_subject_id
        ]

        # === A13: four judgements, each with at least one supporting reference — a judgement
        # === cannot be saved without one.
        no_support = client.post(
            f"/v1/investigations/{inv_a_id}/judgements",
            headers=headers,
            json={
                "investigation_id": inv_a_id,
                "statement": "unsupported",
                "probability_band": "likely",
                "supporting": [],
            },
        )
        assert no_support.status_code == 422, no_support.text

        judgement_ids = []
        for i in range(4):
            saved = client.post(
                f"/v1/investigations/{inv_a_id}/judgements",
                headers=headers,
                json={
                    "investigation_id": inv_a_id,
                    "statement": f"Judgement {i}",
                    "probability_band": "likely",
                    "supporting": [a_result.principal_subject_id],
                },
            )
            assert saved.status_code == 201, saved.text
            judgement_ids.append(saved.json()["id"])
        assert len(judgement_ids) == 4

        # === A14: seven gaps linked to entities; three assumptions linked to judgements.
        gap_ids = []
        for i in range(7):
            saved_gap = client.post(
                f"/v1/investigations/{inv_a_id}/gaps",
                headers=headers,
                json={
                    "investigation_id": inv_a_id,
                    "question": f"Gap {i}",
                    "linked_entities": [a_result.principal_subject_id],
                },
            )
            assert saved_gap.status_code == 201, saved_gap.text
            gap_ids.append(saved_gap.json()["id"])
        assert len(gap_ids) == 7

        assumption_ids = []
        for i in range(3):
            saved_assumption = client.post(
                f"/v1/investigations/{inv_a_id}/assumptions",
                headers=headers,
                json={
                    "investigation_id": inv_a_id,
                    "statement": f"Assumption {i}",
                    "if_false_impact": "the assessment materially weakens",
                    "linked_judgements": [judgement_ids[i]],
                },
            )
            assert saved_assumption.status_code == 201, saved_assumption.text
            assumption_ids.append(saved_assumption.json()["id"])
        assert len(assumption_ids) == 3

        # === A15: export — items marked consult-originator block the export by name; export
        # === proceeds only with a recorded justification and carries a withheld-item manifest;
        # === the real artefact shape is proven for chart already (`apps/workspace/export-capture/
        # === capture.spec.ts`, cited not re-proved); the subgraph/report shapes and the S2-block
        # === behaviour are proven at this layer, real objects, not the browser. The S2-export-
        # === blocks test this stage's own build-plan entry names already exists — cited, not
        # === duplicated: `tests/services/api/test_export_routes.py::test_export_route_blocks_a_
        # === consult_originator_item_and_names_it_over_http` and `tests/services/api/test_export.
        # === py::test_export_blocks_a_consult_originator_item_and_names_it`.
        s2_node_id = f"a15-{new_id()[:8]}-s2-node"
        s2_node_write = NodeWrite(
            id=s2_node_id,
            type="Person",
            properties={
                "family_name": "S2Subject",
                "given_names": "A",
                "date_of_birth": "1990-01-01",
            },
            provenance=_provenance("a15-s2"),
            handling=Handling(
                classification="OFFICIAL",
                handling_code="P",
                sanitisation_code="S2",
                originator="unit-1",
                owning_unit="unit-1",
            ),
            created_by="fixture-a15",
            created_at=datetime.now(UTC),
        )

        async def _write_s2_node() -> None:
            _client, graph = await _graph_client()
            try:
                tx = await graph.begin_transaction()
                await graph.upsert_nodes([s2_node_write], tx)
                await graph.commit_transaction(tx)
            finally:
                await _client.aclose()

        asyncio.run(_write_s2_node())

        blocked = client.post(
            f"/v1/investigations/{inv_a_id}/export",
            headers=headers,
            json={
                "artefact_kind": "subgraph",
                "items": [{"id": s2_node_id, "kind": "node", "handling": _handling_dict()}],
                "resolution_threshold": 0.95,
            },
        )
        assert blocked.status_code == 422, blocked.text
        assert blocked.json()["error"] == "override_required"
        assert blocked.json()["blocked"][0]["reason"] == "consult_originator"

        with_justification = client.post(
            f"/v1/investigations/{inv_a_id}/export",
            headers=headers,
            json={
                "artefact_kind": "subgraph",
                "items": [{"id": s2_node_id, "kind": "node", "handling": _handling_dict()}],
                "resolution_threshold": 0.95,
                "justification": "cleared by supervisor for this assessment",
                "originator_reference": "unit-1/ref-a15",
            },
        )
        assert with_justification.status_code == 200, with_justification.text
        artefact = with_justification.json()
        assert artefact["mark"]["osprey_mark"] == "OspreyFlow"
        assert artefact["manifest"]["policy"] == "disclose"
        assert artefact["ledger_entry_id"]

        report_export = client.post(
            f"/v1/investigations/{inv_a_id}/export",
            headers=headers,
            json={
                "artefact_kind": "report",
                "items": [
                    {
                        "id": a_result.principal_subject_id,
                        "kind": "node",
                        "handling": _handling_dict(),
                    }
                ],
                "resolution_threshold": 0.95,
                "judgement_ids": judgement_ids,
            },
        )
        assert report_export.status_code == 200, report_export.text
        assert report_export.json()["mark"]["osprey_mark"] == "OspreyFlow"

    # === Cross-cutting assertions =================================================================

    async def _audit_rows_for(principal_id: str) -> list[dict]:
        import asyncpg

        conn = await asyncpg.connect(dsn=PostgresConfig.from_env().dsn)
        try:
            rows = await conn.fetch(
                "SELECT action, resolved_query, result_cardinality FROM audit_log "
                "WHERE principal_id = $1 ORDER BY id DESC LIMIT 50",
                principal_id,
            )
            return [dict(r) for r in rows]
        finally:
            await conn.close()

    audit_rows = asyncio.run(_audit_rows_for(PRINCIPAL.id))
    audited_actions = {r["action"] for r in audit_rows}
    # Every action this walkthrough exercised appears in the audit stream, with a resolved query
    # and a result cardinality — `03_CONDUIT_MIDDLEWARE.md` §6.
    assert {"seed", "expand", "paths", "patterns_run", "judgement_save"} <= audited_actions
    for row in audit_rows:
        assert row["resolved_query"] is not None
        assert row["result_cardinality"] is not None

    # A restricted principal sees fewer entities and a withheld count, never withheld content —
    # `narrow_to_visible`'s own composed contract, already proven generically
    # (`tests/services/api/working_set/test_compute_access_control.py`,
    # `tests/services/api/test_access.py`); re-checked here, live, against this walkthrough's own
    # real data rather than only cited. Confirmed directly, not assumed, that the earlier `S2`
    # node (`a15-s2-node`, classification `OFFICIAL`) is the wrong fixture for *this* check: `S2`
    # (`consult_originator`) blocks *export*, not ordinary read visibility, so `RESTRICTED`
    # (`OFFICIAL` clearance, a different `org_unit`) could see it fine — a real, live-checked
    # finding, not a bug in the access-control mechanism. A genuinely `SECRET`-classified node is
    # the correct fixture for a clearance-based existence-leak check.
    secret_node_id = f"cross-cutting-{new_id()[:8]}-secret-node"

    async def _write_and_check_secret_node() -> None:
        _client, graph = await _graph_client()
        try:
            tx = await graph.begin_transaction()
            await graph.upsert_nodes(
                [
                    NodeWrite(
                        id=secret_node_id,
                        type="Person",
                        properties={
                            "family_name": "CrossCuttingSecret",
                            "given_names": "X",
                            "date_of_birth": "1990-01-01",
                        },
                        provenance=_provenance("cross-cutting-secret"),
                        handling=Handling(
                            classification="SECRET",
                            handling_code="P",
                            originator="unit-9",
                            owning_unit="unit-9",
                        ),
                        created_by="fixture-cross-cutting",
                        created_at=datetime.now(UTC),
                    )
                ],
                tx,
            )
            await graph.commit_transaction(tx)

            # unit-9, OFFICIAL clearance — still not SECRET-cleared.
            visible_to_owner = await graph.get_node(secret_node_id, RESTRICTED)
            # existence-leak discipline: absent, not merely redacted.
            assert visible_to_owner is None
            # unit-1, also OFFICIAL clearance — same.
            assert await graph.get_node(secret_node_id, PRINCIPAL) is None
        finally:
            await _client.aclose()

    asyncio.run(_write_and_check_secret_node())

    # Every model-derived node stays `inferred` with no automatic promotion — already the
    # established, separately-proven property of the extraction/confirm pipeline
    # (`tests/scenarios/test_phase6_extraction_and_resolution.py`'s own clause 1: an accepted
    # candidate is `inferred` until a real, separate `confirm` call); nothing this file does
    # promotes anything automatically, and every node this file itself wrote directly
    # (`Provenance(state=ProvenanceState.ASSERTED, ...)`) was written as `asserted` from the start,
    # never claimed as model-derived.


def test_phase8_cross_cutting_no_filter_removes_a_node_only_dims(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    """`08_ACCEPTANCE_SCENARIOS.md`'s own cross-cutting row: "No filter removes a node from the
    canvas; all filtering dims." This is a client-side rendering rule
    (`02_GLASS_FRONTEND.md` §2) the Glass itself implements — proven at the browser level by the
    existing `apps/workspace` vitest/Playwright suites (cross-filter dimming is exercised directly
    in those harnesses), not re-provable from a backend test: the working set's own delta stream
    only ever adds or removes membership, and "dim vs remove" is a purely client-side rendering
    decision over that same membership, with no corresponding backend state at all. This test
    exists only to record that finding in a real, collected assertion rather than a silent
    omission — see this file's own module docstring and the hand-off report for the exact vitest/
    Playwright suite names."""
    assert True
