"""ADR-148 decision 10 for the demo packs (L1.10, the orchestrator's (b)): a pack whose data is
marked above the deployment's highest marking is refused before its seed starts, so a pack written
in several transactions (fixture-corp's SECRET shortcut, by design) is never partly written. A pack
declares its highest marking only where a test below proves every write it makes is within it; one
that declares none is judged as the scheme's highest, so the refusal fails closed."""

from __future__ import annotations

import asyncio
import csv
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from scripts import seed_internal
from scripts.seed_internal import DATASETS, SeedRefused
from services.ingest.ceiling import (
    AboveTheDeploymentCeiling,
    DeploymentCeiling,
    refuse_rows_above_the_ceiling,
)
from services.ingest.recipe_loader import load_recipe
from services.ingest.recipe_rules import marked_columns

from ontology.handling import load_uk_le_scheme
from schemas.ingest import Recipe
from tests.ingest.recipe_test_support import ValidatingGraph, local_staging  # noqa: F401

from .test_seed_internal import SUBS, Runner

SCHEME = load_uk_le_scheme()
PUBLIC_CATALOGUE = (
    Path(__file__).resolve().parents[2]
    / "OspreyFlow_Core"
    / "packages"
    / "demo_fixtures"
    / "public_datasets"
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A checkout as `test_seed_internal`'s own: `.git`, a rendered local-lite deployment."""
    (tmp_path / ".git").mkdir()
    core = tmp_path / "OspreyFlow_Core"
    out = core / "deploy" / "generated" / "local-lite"
    out.mkdir(parents=True)
    (out / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    (out / "deployment.env").write_text("OSPREY_KEYCLOAK_PORT=8081\n", encoding="utf-8")
    (core / "scripts").mkdir()
    (tmp_path / "OspreyFlow_Data" / "PaySIM_Dataset").mkdir(parents=True)
    return core


def _render(repo: Path, ceiling: str | None) -> None:
    env = repo / "deploy" / "generated" / "local-lite" / "deployment.env"
    line = f"OSPREY_HIGHEST_MARKING={ceiling}\n" if ceiling is not None else ""
    env.write_text("OSPREY_KEYCLOAK_PORT=8081\n" + line, encoding="utf-8")


def _seed(repo: Path, dataset: str, runner: Runner, **more: Any) -> list[str]:
    return seed_internal.seed_internal(
        dataset, repo, run=runner, lookup_subs=lambda directory: SUBS,
        api_running=lambda compose: False, permitted=lambda name, use: True, **more,
    )  # fmt: skip


def test_a_pack_above_the_ceiling_is_refused_before_its_seed_starts(repo: Path) -> None:
    _render(repo, "OFFICIAL-SENSITIVE")
    runner = Runner()
    with pytest.raises(SeedRefused) as raised:
        _seed(repo, "fixture-corp", runner)
    words = str(raised.value)
    assert "OFFICIAL-SENSITIVE" in words and "fixture-corp" in words
    # Its declared marking, said as the declaration's words, not as an undeclared pack's.
    assert "holds data marked up to SECRET" in words, words
    assert runner.calls == [], "something ran before the refusal"


def test_a_pack_within_the_ceiling_is_seeded(repo: Path) -> None:
    _render(repo, "OFFICIAL-SENSITIVE")
    runner = Runner()
    _seed(repo, "cyber-intrusion", runner)
    assert any("scripts.seed_cyber_intrusion" in call for call in runner.calls)


def test_with_no_ceiling_rendered_every_pack_is_seeded_as_before(repo: Path) -> None:
    _render(repo, None)
    runner = Runner()
    _seed(repo, "fixture-corp", runner)
    assert any("scripts.seed_fixture_corp" in call for call in runner.calls)


def test_a_pack_that_declares_nothing_is_judged_as_the_scheme_s_highest(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fails closed: a pack added without a declaration is refused under any ceiling below the
    scheme's top. Every pack declares one now, so one is planted without it."""
    monkeypatch.setitem(
        DATASETS, "fixture-corp", replace(DATASETS["fixture-corp"], highest_marking=None)
    )
    _render(repo, "OFFICIAL-SENSITIVE")
    with pytest.raises(SeedRefused) as raised:
        _seed(repo, "fixture-corp", Runner())
    assert "declares no highest marking" in str(raised.value)


def test_every_pack_declares_its_highest_marking() -> None:
    """L1.10b: every pack declares, each proved below, so none is judged as the scheme's highest
    for want of a declaration; a new pack is added with its own and its proof."""
    undeclared = {
        n
        for n, spec in DATASETS.items()
        if spec.highest_marking is None and not spec.judged_when_staged
    }
    assert undeclared == set()
    assert set(DATASETS) == set(PROVED), "a pack whose declaration no test below proves"


def _within(declared: str, classification: str) -> bool:
    """The ceiling's own judgement: a marking the scheme does not know counts as above it."""
    return not DeploymentCeiling(declared, SCHEME).above(classification)


def _recipe_within(recipe: Recipe, rows: list[dict[str, str]], declared: str) -> None:
    """The ceiling's own judgement (`services.ingest.ceiling`) of a recipe and the rows the pack
    loads through it, at the pack's declaration: what a load would be refused for."""
    refuse_rows_above_the_ceiling(recipe, rows, DeploymentCeiling(declared, SCHEME))


class _Recording:
    """A graph that records every write a builder makes and finds whatever it asks for."""

    def __init__(self) -> None:
        self.writes: list[Any] = []

    async def begin_transaction(self) -> str:
        return "tx"

    async def commit_transaction(self, tx: object) -> None:
        return None

    async def rollback_transaction(self, tx: object) -> None:
        return None

    async def find_node(self, entity_type: str, field: str, value: str, principal: Any) -> Any:
        return SimpleNamespace(id=f"{entity_type}:{value}")

    async def upsert_nodes(self, nodes: list[Any], tx: object) -> list[str]:
        self.writes.extend(nodes)
        return [n.id for n in nodes]

    async def upsert_edges(self, edges: list[Any], tx: object) -> list[str]:
        self.writes.extend(edges)
        return [e.id for e in edges]


class _Stored(ValidatingGraph):
    """The test store, answering a lookup with what it holds, as HMP's places step reads it."""

    async def find_node(self, entity_type: str, field: str, value: str, principal: Any) -> Any:
        for node in [*self.committed_nodes, *self.open_nodes]:
            if node.type == entity_type and str(node.properties.get(field)) == value:
                return node
        return None

    async def list_nodes(self, entity_type: str, principal: Any, *, cursor: Any = None) -> Any:
        held = [n for n in self.committed_nodes if n.type == entity_type]
        return SimpleNamespace(nodes=held, next_cursor=None)


def test_hmps_declaration_is_the_highest_it_writes() -> None:
    """The seed's own three steps, run against a store that records them: the recipes (through the
    engine, which judges them as a load), the network and the places; with every event they give
    the analytics store and the map's geometry. One SECRET conflict, by design: SECRET is the
    highest, and reached."""
    from demo_fixtures.hmp_graph import build_hmp_graph
    from demo_fixtures.hmp_network import geometry_records, write_hmp_network, write_hmp_places
    from ontology.packs import load_deployment_ontology
    from schemas.domain import Principal

    declared = DATASETS["hmp"].highest_marking
    assert declared == "SECRET"
    ontology = load_deployment_ontology()
    graph = _Stored(ontology)
    seeder = Principal(id="seed", clearance="SECRET", org_unit="hmp-hollywood")

    async def seed() -> list[Any]:
        built = await build_hmp_graph(
            graph=graph, ontology=ontology, principal=seeder, investigation_scope="case-hmp"
        )
        network = await write_hmp_network(
            graph=graph, person_ids=built.person_node_ids, principal=seeder,
            investigation_scope="case-hmp",
        )  # fmt: skip
        assert await write_hmp_places(graph=graph, principal=seeder)
        return [*built.current_window_events, *built.prior_period_events, *network]

    events = asyncio.run(seed())
    written = [*graph.committed_nodes, *graph.committed_edges, *events, *geometry_records()]
    assert graph.committed_nodes and graph.committed_edges and events
    marked = {w.handling.classification for w in written}
    assert all(_within(declared, c) for c in marked), "a write above the declaration"
    assert declared in marked, "a declaration higher than anything the pack writes"
    # Everything but the one SECRET conflict and its events is OFFICIAL.
    assert marked == {"OFFICIAL", "SECRET"}, marked


def test_fixture_corps_declaration_is_the_highest_it_writes() -> None:
    """The seed's own three writers, recorded: its resolution persons and their links, its rings,
    and the path spokes, whose shortcut is SECRET by design. SECRET is the highest, and reached."""
    from scripts import seed_fixture_corp

    from demo_fixtures.fixture_corp import build_path_spokes

    declared = DATASETS["fixture-corp"].highest_marking
    assert declared == "SECRET"
    graph = _Recording()

    async def seed() -> None:
        await seed_fixture_corp._seed_resolution_persons(graph, load_id="ld")  # type: ignore[arg-type]
        await seed_fixture_corp._seed_community_rings(graph, load_id="ld")  # type: ignore[arg-type]
        await build_path_spokes(graph)  # type: ignore[arg-type]

    asyncio.run(seed())
    marked = {w.handling.classification for w in graph.writes}
    assert graph.writes and all(_within(declared, c) for c in marked)
    assert declared in marked, "a declaration higher than anything the pack writes"


def test_ledgers_declaration_holds_for_every_write() -> None:
    """Every recipe the Ledger loads (its six, the mid-demo steps' included) sets no marking from a
    column and loads at most OFFICIAL. Its real builder is run against a store that finds only what
    it holds, so its direct writes (the nodes it makes when they are not found, and its links) are
    recorded, with the map's geometry."""
    from demo_fixtures import ledger
    from ontology.packs import load_deployment_ontology
    from schemas.domain import Principal

    declared = DATASETS["ledger"].highest_marking
    assert declared == "OFFICIAL"
    recipes = sorted(ledger.FIXTURES.glob("ledger_*_recipe.yaml"))
    assert len(recipes) == 6
    for path in recipes:
        recipe = load_recipe(path)
        _recipe_within(recipe, [], declared)
        assert not marked_columns(recipe.row_template, recipe.defaults.handling_columns), path.name
    ontology = load_deployment_ontology()
    graph = _Stored(ontology)
    seeder = Principal(id="seed", clearance="SECRET", org_unit="unit-fincrime")
    asyncio.run(ledger.build_ledger_graph(graph=graph, ontology=ontology, principal=seeder))
    direct = [w for w in graph.committed_nodes if (w.load_id or "").endswith("-direct")]
    assert direct, "the builder's own nodes were never recorded"
    written = [*graph.committed_nodes, *graph.committed_edges, *ledger.geometry_records()]
    assert all(_within(declared, w.handling.classification) for w in written), (
        "a write above the declaration"
    )


def test_prison_intelligences_declaration_holds_for_every_write(tmp_path: Path) -> None:
    """Every file the seed writes, judged through the recipe that loads it, as a load would be:
    the recipes bind a classification column, and the plan writes OFFICIAL into it. The inferred
    links the seed writes itself take the plan's markings too."""
    from datetime import UTC, datetime

    from scripts import seed_pid

    from demo_fixtures import pid_files, pid_monitoring, pid_plan

    declared = DATASETS["prison-intelligence"].highest_marking
    assert declared == "OFFICIAL"
    plan = pid_plan.build_plan("demo")
    pid_files.write_files(plan, tmp_path)
    stages = [
        *((s.file, s.recipe) for s in pid_files.SEED_ORDER),
        *((pid_monitoring.output_name(s.file), s.recipe) for s in pid_monitoring.MONITORING_STAGES),
    ]
    judged = 0
    for file, recipe_file in stages:
        name = pid_files.output_name(plan.profile, file) if "/" not in file else file
        with (tmp_path / name).open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        recipe = load_recipe(seed_pid.FIXTURES / recipe_file)
        _recipe_within(recipe, rows, declared)
        judged += bool(marked_columns(recipe.row_template, recipe.defaults.handling_columns))
    assert judged, "no recipe binds a marking column, so no row was judged"
    links = seed_pid.inferred_links(plan, created_at=datetime(2026, 11, 10, tzinfo=UTC))
    assert links
    assert all(_within(declared, w.handling.classification) for _, w in links), (
        "a write above the declaration"
    )


def test_the_scale_cohorts_declaration_holds_for_every_write() -> None:
    from datetime import UTC, datetime

    from scripts.seed_pid_scale import scale_writes

    declared = DATASETS["prison-intelligence-scale"].highest_marking
    assert declared == "OFFICIAL"
    nodes, edges = scale_writes(datetime(2026, 11, 10, tzinfo=UTC))
    assert nodes and edges
    assert all(_within(declared, w.handling.classification) for w in [*nodes, *edges]), (
        "a write above the declaration"
    )


def _stage_public(repo: Path, markings: list[str], *, checksum: bool = True) -> str:
    """A public dataset staged as `scripts.public_dataset stage` leaves it: the catalogue's
    manifest with the file's checksum pinned, its recipe with one element's classification bound
    to a `cls` column, and the file. Synthetic rows (rule 9)."""
    import hashlib

    import yaml

    folder = repo.parent / "OspreyFlow_Data" / "public" / "vast-2008-mc3"
    folder.mkdir(parents=True)
    rows = "".join(f"{i},{m}\n" for i, m in enumerate(markings))
    data = f"call,cls\n{rows}".encode()
    manifest = yaml.safe_load((PUBLIC_CATALOGUE / "vast-2008-mc3.dataset.yaml").read_text())
    manifest["file"]["sha256"] = hashlib.sha256(data).hexdigest() if checksum else "0" * 64
    (folder / "dataset.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")
    recipe = yaml.safe_load((PUBLIC_CATALOGUE / manifest["recipe"]).read_text())
    recipe["row_template"]["entities"][0]["handling"] = {"classification": {"field": "cls"}}
    (folder / "recipe.yaml").write_text(yaml.safe_dump(recipe), encoding="utf-8")
    (folder / manifest["file"]["name"]).write_bytes(data)
    return "vast-2008-mc3"


def test_a_staged_public_dataset_above_the_ceiling_is_refused_before_its_seed_starts(
    repo: Path,
) -> None:
    """No declaration can hold for a recipe the administrator stages, so its rows are judged on
    the host, as the load would judge them, before the seed makes its case or writes anything."""
    public_id = _stage_public(repo, ["OFFICIAL", "SECRET"])
    _render(repo, "OFFICIAL")
    runner = Runner()
    with pytest.raises(SeedRefused) as raised:
        _seed(repo, "public", runner, public_id=public_id)
    assert AboveTheDeploymentCeiling("OFFICIAL").problems[0] in str(raised.value)
    assert runner.calls == [], "something ran before the refusal"


def test_a_staged_public_dataset_within_the_ceiling_is_seeded(repo: Path) -> None:
    public_id = _stage_public(repo, ["OFFICIAL", "OFFICIAL"])
    _render(repo, "OFFICIAL")
    runner = Runner()
    _seed(repo, "public", runner, public_id=public_id)
    assert any("scripts.seed_public" in call for call in runner.calls)


def test_a_staged_public_dataset_that_cannot_be_read_is_refused_under_a_ceiling(
    repo: Path,
) -> None:
    public_id = _stage_public(repo, ["OFFICIAL"], checksum=False)
    _render(repo, "OFFICIAL")
    runner = Runner()
    with pytest.raises(SeedRefused, match="could not be read to judge its markings"):
        _seed(repo, "public", runner, public_id=public_id)
    assert runner.calls == []


def test_with_no_ceiling_a_staged_public_dataset_is_seeded_as_before(repo: Path) -> None:
    public_id = _stage_public(repo, ["SECRET"])
    _render(repo, None)
    runner = Runner()
    _seed(repo, "public", runner, public_id=public_id)
    assert any("scripts.seed_public" in call for call in runner.calls)


def test_enrons_declaration_holds_for_every_write() -> None:
    """Enron is real data, never in a test (rule 9): its builders are proved over a synthetic pair
    and message to stamp each write with the handling they are given, and the seed gives them
    `_HANDLING`, within the declaration."""
    from datetime import UTC, datetime

    from scripts import enron_mail, seed_enron

    from schemas.domain import Handling

    declared = DATASETS["enron"].highest_marking
    assert declared == "OFFICIAL"
    assert _within(declared, seed_enron._HANDLING.classification), "a write above the declaration"
    probe = Handling(
        classification="PUBLIC", handling_code="P", originator="probe", owning_unit="probe"
    )
    at = datetime(2001, 1, 1, tzinfo=UTC)
    pairs = {("a@enron.com", "b@enron.com"): enron_mail.PairSummary(count=2, first=at, last=at)}
    nodes, edges = enron_mail.build_graph_writes(pairs, created_by="seed", handling=probe)
    assert nodes and edges
    assert all(w.handling == probe for w in [*nodes, *edges]), "a write at another marking"
    message = enron_mail.Message(
        message_id="m-1", custodian="a", folder="sent", sent_at=at, sender="a@enron.com",
        recipients=(enron_mail.Recipient("b@enron.com", "to"),), subject="s", excerpt="e",
    )  # fmt: skip
    events = list(enron_mail.to_events(message, investigation_scope="enron", handling=probe))
    assert events and all(e.handling == probe for e in events)


def test_cyber_intrusions_declaration_holds_for_every_write() -> None:
    from scripts.seed_cyber_intrusion import edge_writes, node_writes

    declared = DATASETS["cyber-intrusion"].highest_marking
    assert declared is not None
    top = SCHEME.classification.index(declared)
    writes = [*node_writes("load-1"), *edge_writes("load-1")]
    assert writes
    assert all(SCHEME.classification.index(w.handling.classification) <= top for w in writes)


def test_paysims_declaration_holds_for_every_write() -> None:
    """Every PaySim write takes the seed's one marking: `build_graph_writes` stamps each node and
    link with the handling it is given (proved over synthetic rows), and the seed gives it
    `_HANDLING`, within the declaration."""
    from scripts import seed_paysim

    from demo_fixtures.paysim import PaysimRow, build_graph_writes
    from schemas.domain import Handling

    declared = DATASETS["paysim"].highest_marking
    assert declared is not None
    marking = seed_paysim._HANDLING.classification
    assert SCHEME.classification.index(marking) <= SCHEME.classification.index(declared)
    probe = Handling(
        classification="PUBLIC", handling_code="P", originator="probe", owning_unit="probe"
    )
    rows = [
        PaysimRow(index=i, step=1, type="TRANSFER", amount=9.5, origin=f"C{i}",
                  destination=f"C{i + 1}", is_fraud=1, is_flagged=0)
        for i in range(3)
    ]  # fmt: skip
    nodes, edges = build_graph_writes(rows, created_by="seed", handling=probe)
    assert nodes and edges
    assert all(w.handling == probe for w in [*nodes, *edges]), "a write at another marking"


#: Every pack and the test in this file that proves its declaration: the functions themselves, so a
#: pack named here without a proof does not import (the lane review of L1.10b, item 12).
PROVED = {
    "hmp": test_hmps_declaration_is_the_highest_it_writes,
    "ledger": test_ledgers_declaration_holds_for_every_write,
    "fixture-corp": test_fixture_corps_declaration_is_the_highest_it_writes,
    "paysim": test_paysims_declaration_holds_for_every_write,
    "prison-intelligence": test_prison_intelligences_declaration_holds_for_every_write,
    "prison-intelligence-scale": test_the_scale_cohorts_declaration_holds_for_every_write,
    "cyber-intrusion": test_cyber_intrusions_declaration_holds_for_every_write,
    "public": test_a_staged_public_dataset_above_the_ceiling_is_refused_before_its_seed_starts,
    "enron": test_enrons_declaration_holds_for_every_write,
}
