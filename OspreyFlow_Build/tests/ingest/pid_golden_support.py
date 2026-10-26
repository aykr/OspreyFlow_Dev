"""What the PID recipes' golden tests share: the plan, the real files, the committed recipes and the
load. A golden test derives every expectation from `pid_plan` (never typed), loads the real file
through `load_with_rules` against the graph stand-in with the deployment ontology, and loads the
recipes it depends on first, from the committed files, in the seed's order (R11, then R1, then the
rest). Not a test module.

**The marking replay (ADR-127 Amendment 18).** A recipe binds the six handling columns on every
element, so an element several rows name is created with the marking of the first row, in the seed's
load order, that creates it, and later rows find it by reference. `replay` derives that from the
plan's own rows (`pid_files.ordered_rows`, the order the writer writes them), step by step in the
order given, and a link as the store merges it: a write of a link merges into an existing link of
the same type and pair only within one audience (`audience_of`, ADR-102 Amendment 3), by
`merge_handling` (the first write's originator and owning unit stay); a write of another audience is
a link of its own.
`assert_loaded_markings` holds every node and link a load stored to that replay."""

from __future__ import annotations

import csv
import re
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache, lru_cache
from pathlib import Path
from typing import Any

import yaml
from services.api.studio_publish import load_with_rules

from adapters.media_objectstore.testing import InMemoryMediaStore
from demo_fixtures import pid_files, pid_plan
from knowledge_adapters import REGISTRY
from ontology.handling import audience_of, load_uk_le_scheme, merge_handling
from ontology.packs import load_deployment_ontology
from schemas.domain import Handling, Principal
from schemas.ingest import Recipe
from tests.ingest.recipe_test_support import MergingGraph
from tests.ingest.test_row_keys import KeyStore, Sink

ONTOLOGY = load_deployment_ontology()
SCHEME = load_uk_le_scheme()
LOADER = Principal(id="data-engineer-1", clearance="SECRET", org_unit="fenwick-moor-security")
FIXTURES = Path(__file__).resolve().parents[3] / "OspreyFlow_Core/packages/demo_fixtures"
CASE = "pid-case"
PLAN = pid_plan.build_plan("demo")
CALLS = "pid_pin_calls.csv"
COORDINATOR_NUMBER = "+447700900640"

#: file -> recipe file, for every recipe a golden test may need first.
RECIPE_OF = {
    "pid_establishment_plan.csv": "pid_establishment_plan_recipe.yaml",
    "pid_nomis_prisoners.csv": "pid_nomis_prisoners_recipe.yaml",
    "pid_nomis_cell_stays.csv": "pid_nomis_cell_stays_recipe.yaml",
    "pid_nomis_cell_shares.csv": "pid_nomis_cell_shares_recipe.yaml",
    "pid_nomis_visits.csv": "pid_nomis_visits_recipe.yaml",
    "pid_nomis_incidents.csv": "pid_nomis_incidents_recipe.yaml",
    "pid_soc_nominals.csv": "pid_soc_nominals_recipe.yaml",
    "pid_family_and_associates.csv": "pid_family_and_associates_recipe.yaml",
    "pid_codefendants.csv": "pid_codefendants_recipe.yaml",
    "pid_conflicts.csv": "pid_conflicts_recipe.yaml",
    "pid_number_owners.csv": "pid_number_owners_recipe.yaml",
    "pid_pin_calls.csv": "pid_pin_calls_recipe.yaml",
    "pid_seized_comms_batch1.csv": "pid_seized_comms_recipe.yaml",
    "pid_seized_comms_batch2.csv": "pid_seized_comms_recipe.yaml",
    "pid_prisoner_money.csv": "pid_prisoner_money_recipe.yaml",
    "pid_throwover_log.csv": "pid_throwover_log_recipe.yaml",
    "pid_intel_reports.csv": "pid_intel_reports_recipe.yaml",
    "pid_report_incidents.csv": "pid_report_incidents_recipe.yaml",
}


def recipe_for(file: str) -> Recipe:
    text = (FIXTURES / RECIPE_OF[file]).read_text(encoding="utf-8")
    return Recipe.model_validate(yaml.safe_load(text))


@lru_cache(maxsize=1)
def _folder() -> Path:
    folder = Path(tempfile.mkdtemp(prefix="pid-golden-"))
    pid_files.write_files(PLAN, folder)
    return folder


@cache
def rows_of(file: str) -> tuple[dict[str, str], ...]:
    """The rows of one of the plan's files, from where the writer put it (`pid_files.output_name`:
    the second seized-phone batch is in the folder's `incoming/`)."""
    path = _folder() / pid_files.output_name(PLAN.profile, file)
    with path.open(newline="", encoding="utf-8") as handle:
        return tuple(csv.DictReader(handle))


def keys_in(file: str) -> tuple[list[str], list[str]]:
    """The plan's entity keys and link keys the file's rows write (`pid_plan.rows_for`)."""
    entities: dict[str, None] = {}
    links: dict[str, None] = {}
    for row in pid_plan.rows_for(PLAN, file):
        entities.update(dict.fromkeys(row.entities))
        links.update(dict.fromkeys(row.links))
    return list(entities), list(links)


@dataclass(frozen=True)
class Step:
    """One load of the seed's order: a whole file, or (for the million-row call file) the rows of it
    a test loads, with the predicate that selects the plan's own rows for the same ones, so a replay
    sees what the load saw."""

    file: str
    rows: tuple[dict[str, str], ...] | None = None
    plan_rows: Callable[[pid_plan.PlanRow], bool] | None = None


def _step(step: str | Step) -> Step:
    return step if isinstance(step, Step) else Step(step)


async def load(
    graph: MergingGraph,
    file: str,
    sink: Sink | None,
    load_id: str | None = None,
    rows: list[dict[str, str]] | None = None,
    recipe: Recipe | None = None,
    media: InMemoryMediaStore | None = None,
) -> tuple[Any, list[Any]]:
    report, events, _held = await load_with_rules(
        recipe or recipe_for(file),
        rows if rows is not None else list(rows_of(file)),
        LOADER,
        graph=graph,  # type: ignore[arg-type]
        ontology=ONTOLOGY,
        load_id=load_id or f"load-{file}",
        investigation_scope=CASE,
        source=file,
        media=media if media is not None else InMemoryMediaStore(),
        rules=None,
        scheme=SCHEME,
        sink=sink,  # type: ignore[arg-type]
    )
    return report, events


async def loaded(*steps: str | Step) -> tuple[MergingGraph, KeyStore, dict[str, Any]]:
    """A graph with each step loaded in the order given, through its committed recipe, as the seed
    runs them, and the row keys kept as the case keeps them. Returns the reports by file."""
    graph = MergingGraph(ONTOLOGY)
    store = KeyStore()
    reports: dict[str, Any] = {}
    for step in map(_step, steps):
        rows = list(step.rows) if step.rows is not None else None
        report, _events = await load(graph, step.file, Sink(store, CASE), rows=rows)
        assert report.rejections == [], (step.file, report.rejections[:3])
        reports[step.file] = report
    return graph, store, reports


def marking(handling: Any) -> tuple[Any, ...]:
    """A handling as the tuple the tests compare: the six parts, whichever type holds them."""
    return (
        handling.classification,
        handling.handling_code,
        getattr(handling, "action_code", None),
        getattr(handling, "sanitisation_code", None),
        handling.originator,
        handling.owning_unit,
    )


# --- The marking of a row ----------------------------------------------------------------------


def row_marking(values: Mapping[str, str]) -> tuple[Any, ...]:
    """The marking a row's six handling columns give, an empty cell being no code."""
    return (
        values["classification"],
        values["handling_code"],
        values["action_code"] or None,
        values["sanitisation_code"] or None,
        values["originator"],
        values["owning_unit"],
    )


def handling_columns_in(file: str) -> set[str]:
    """Which of the six handling columns the file's header holds."""
    return set(pid_files.header_for(file)) & set(pid_plan.HANDLING_COLUMNS)


def _default_marking(file: str) -> tuple[Any, ...]:
    declared = recipe_for(file).defaults.handling
    return (
        declared["classification"],
        declared["handling_code"],
        None,
        None,
        declared["originator"],
        declared["owning_unit"],
    )


def _handling_of(mark: tuple[Any, ...]) -> Handling:
    return Handling(
        classification=mark[0],
        handling_code=mark[1],
        action_code=mark[2],
        sanitisation_code=mark[3],
        originator=mark[4],
        owning_unit=mark[5],
    )


@cache
def _plan_links() -> dict[str, pid_plan.PlanLink]:
    return {lk.key: lk for lk in PLAN.links}


def _pair(link_type: str, source: str, target: str) -> tuple[str, str, str]:
    """A link's pair as the store holds it: either way round for an undirected type."""
    edge_type = ONTOLOGY.edge_type(link_type)
    assert edge_type is not None, link_type
    ends = (source, target) if edge_type.directed else tuple(sorted((source, target)))
    return (link_type, ends[0], ends[1])


# --- The replay ---------------------------------------------------------------------------------


@dataclass
class Replay:
    """What a load of the steps leaves stored, by the plan's own keys."""

    #: entity key -> the marking of the first row that creates it.
    nodes: dict[str, tuple[Any, ...]] = field(default_factory=dict)
    #: (type, source key, target key) -> the markings of the links the store holds for the pair, one
    #: for each audience the writes fall into.
    links: dict[tuple[str, str, str], list[tuple[Any, ...]]] = field(default_factory=dict)
    #: (type, source key, target key) -> the plan links whose rows wrote it.
    plan_links: dict[tuple[str, str, str], list[str]] = field(default_factory=dict)
    #: How many plan rows were replayed (a replay of nothing proves nothing).
    rows_replayed: int = 0

    def differs_from_plan(self) -> tuple[list[str], list[str]]:
        """The nodes (entity keys) and links (plan link keys) whose loaded marking is not the plan's
        own marking for the element."""
        nodes = [k for k, m in self.nodes.items() if m != marking(PLAN.entity(k).handling)]
        links = []
        for pair, keys in self.plan_links.items():
            for key in keys:
                own = marking(_plan_links()[key].handling)
                if sorted(self.links[pair], key=repr) != [own]:
                    links.append(key)
        return nodes, links


def link_markings(writes: Sequence[tuple[Any, ...]]) -> list[tuple[Any, ...]]:
    """The markings of the links the store holds for one pair after these writes, in order: a write
    merges into the link of its own audience (`audience_of`: classification, handling code, datasets
    and, under a restricted code, the units) by `merge_handling`, which keeps the first write's
    originator and owning unit; a write of another audience is a link of its own (ADR-102
    Amendment 3). Not first-write-wins: a SECRET write onto an OFFICIAL link is a second link."""
    groups: list[tuple[Any, Handling]] = []
    for mark in writes:
        incoming = _handling_of(mark)
        audience = audience_of(incoming, (), SCHEME)
        for index, (held_audience, existing) in enumerate(groups):
            if held_audience == audience:
                groups[index] = (audience, merge_handling(existing, incoming, SCHEME))
                break
        else:
            groups.append((audience, incoming))
    return [marking(h) for _, h in groups]


def replay(*steps: str | Step) -> Replay:
    """The markings a load of the steps, in the seed's order, leaves stored (the module docstring).
    A file with some but not all of the six handling columns is a defect and is refused: its rows'
    markings are neither the columns' nor the recipe's defaults."""
    out = Replay()
    written: dict[tuple[str, str, str], list[tuple[Any, ...]]] = {}
    for step in map(_step, steps):
        held = handling_columns_in(step.file)
        assert held in (set(), set(pid_plan.HANDLING_COLUMNS)), (step.file, sorted(held))
        default = _default_marking(step.file)
        for row in pid_files.ordered_rows(PLAN, step.file):
            if step.plan_rows is not None and not step.plan_rows(row):
                continue
            mark = row_marking(row.values) if held else default
            out.rows_replayed += 1
            # A row's recipe makes every end of every link it writes, whatever file the plan homes
            # the entity in (`row.entities` holds only the ones homed here), when none holds it yet.
            for key in row.entities:
                out.nodes.setdefault(key, mark)
            for link_key in row.links:
                lk = _plan_links()[link_key]
                out.nodes.setdefault(lk.source, mark)
                out.nodes.setdefault(lk.target, mark)
                pair = _pair(lk.link_type, lk.source, lk.target)
                keys = out.plan_links.setdefault(pair, [])
                if link_key not in keys:
                    keys.append(link_key)
                written.setdefault(pair, []).append(mark)
    out.links = {pair: link_markings(marks) for pair, marks in written.items()}
    return out


# --- Holding a load to the replay --------------------------------------------------------------

_IDENTIFIERS = (
    "prison_number", "nino", "site_ref", "establishment_ref", "org_ref", "incident_ref", "imei",
    "value_normalised", "message_id",
)  # fmt: skip
_IR = re.compile(r"IR \d+")


def _identity(entity: pid_plan.PlanEntity) -> tuple[str, str, str]:
    """How the store names the entity: its type and the first identifying property it holds. A
    handset is named by its 14-digit body (`imei` drops the check digit, ADR-127 Amendment 18)."""
    for name in _IDENTIFIERS:
        if name in entity.properties:
            value = str(entity.properties[name])
            return (entity.entity_type, name, value[:14] if name == "imei" else value)
    if entity.key in PLAN.report_texts:
        # A report has no identifying property of its own: the store names it by `message_id`, the
        # reference its text begins with (ADR-127 Amendment 17).
        found = _IR.match(PLAN.report_texts[entity.key])
        assert found is not None, entity.key
        return (entity.entity_type, "message_id", found.group())
    raise AssertionError(f"{entity.key} holds no identifying property")


def stored_node_of(graph: MergingGraph, key: str) -> Any:
    """The one stored node for a plan entity, by its identifying property."""
    entity_type, name, value = _identity(PLAN.entity(key))
    found = [
        n
        for n in graph.committed_nodes
        if n.type == entity_type and str(n.properties.get(name)) == value
    ]
    assert len(found) == 1, (key, len(found))
    return found[0]


@dataclass(frozen=True)
class Differences:
    nodes: tuple[str, ...]
    links: tuple[str, ...]


def assert_loaded_markings(graph: MergingGraph, expected: Replay) -> Differences:
    """Every node and link the loads stored carries the marking the replay gives, and the store
    holds nothing else. Returns the elements whose loaded marking is not the plan's own."""
    ids: dict[str, str] = {}
    by_identity: dict[tuple[str, str, str], Any] = {}
    for node in graph.committed_nodes:
        for name in _IDENTIFIERS:
            if name in node.properties:
                identity = (node.type, name, str(node.properties[name]))
                assert identity not in by_identity, ("a node made twice", identity)
                by_identity[identity] = node
    for key, mark in expected.nodes.items():
        node = by_identity[_identity(PLAN.entity(key))]
        ids[key] = node.id
        assert marking(node.handling) == mark, (key, marking(node.handling), mark)
    assert len(graph.committed_nodes) == len(expected.nodes), "a node the plan does not name"
    stored: dict[tuple[str, str, str], list[Any]] = {}
    for edge in graph.committed_edges:
        stored.setdefault(_pair(edge.type, edge.source, edge.target), []).append(edge)
    assert len(graph.committed_edges) == sum(len(v) for v in expected.links.values()), (
        "a link the plan does not name, or a pair held as more or fewer links than its audiences"
    )
    for (link_type, source, target), marks in expected.links.items():
        held = stored[_pair(link_type, ids[source], ids[target])]
        assert sorted((marking(e.handling) for e in held), key=repr) == sorted(marks, key=repr), (
            link_type,
            source,
            target,
        )
    nodes, links = expected.differs_from_plan()
    return Differences(tuple(nodes), tuple(links))


# --- The PIN call file, in part -----------------------------------------------------------------


@cache
def msisdn(raw: str) -> str:
    return str(REGISTRY["msisdn"](raw))


def pin_link_of(row: Mapping[str, str]) -> tuple[str, str]:
    """The (PIN account, number as `msisdn` reads it) pair a call row is on."""
    return (row["pin_account"], msisdn(row["called_number"]))


def pin_call_of(row: Mapping[str, str]) -> tuple[str, str, str, str]:
    return (*pin_link_of(row), row["call_start"], row["duration_s"])


def is_national(raw: str) -> bool:
    return raw.startswith("0") and not raw.startswith("00")


@lru_cache(maxsize=1)
def pin_calls_slice() -> tuple[tuple[dict[str, str], ...], frozenset[str]]:
    """A slice of the demo profile's million-row call file, and the plan's link keys it holds whole:
    every row of every link (one PIN account to one number) that holds a planted duplicate, that
    ends at the coordinator's number, or that ends at one of the first three numbers the file writes
    in other forms; plus, for each number in the slice, the link its first row sits on (so the raw
    form kept is the plan's)."""
    rows = rows_of(CALLS)
    by_call: dict[tuple[str, str, str, str], int] = {}
    for r in rows:
        by_call[pin_call_of(r)] = by_call.get(pin_call_of(r), 0) + 1
    links = {pin_link_of(r) for r in rows if by_call[pin_call_of(r)] > 1}
    links |= {pin_link_of(r) for r in rows if pin_link_of(r)[1] == COORDINATOR_NUMBER}
    other_forms = sorted({pin_link_of(r)[1] for r in rows if not is_national(r["called_number"])})
    numbers = set(other_forms[:3])
    links |= {link for link in {pin_link_of(r) for r in rows} if link[1] in numbers}
    first_row_of: dict[str, tuple[str, str]] = {}
    for r in rows:
        first_row_of.setdefault(pin_link_of(r)[1], pin_link_of(r))
    links |= {first_row_of[n] for n in {link[1] for link in links}}
    kept = tuple(r for r in rows if pin_link_of(r) in links)
    _, link_keys = keys_in(CALLS)
    wanted = set(link_keys)
    keys = set()
    for lk in PLAN.links:
        if lk.key in wanted and lk.link_type == "COMMUNICATED_WITH":
            src, tgt = PLAN.entity(lk.source), PLAN.entity(lk.target)
            if (str(src.properties["handle"]), str(tgt.properties["value_normalised"])) in links:
                keys.add(lk.key)
    return kept, frozenset(keys)


def pin_calls_slice_step() -> Step:
    rows, keys = pin_calls_slice()
    return Step(CALLS, rows, lambda row: row.links[0] in keys)


@cache
def pin_calls_to_step(numbers: frozenset[str]) -> Step:
    """The call file's rows to the given numbers (as `msisdn` reads them), whole: what the seed's
    R5 load does to those numbers, whatever else it does."""
    rows = tuple(r for r in rows_of(CALLS) if msisdn(r["called_number"]) in numbers)
    return Step(CALLS, rows, lambda row: msisdn(row.values["called_number"]) in numbers)


def assert_exact_instants(plan_link: pid_plan.PlanLink, seen: Sequence[Any]) -> None:
    """The instants of a link's events are exactly the plan's own for it (`link_instants`, the one
    function the files and the store writes share), not merely inside its dates."""
    assert sorted(seen) == sorted(pid_plan.link_instants(PLAN, plan_link)), plan_link.key
