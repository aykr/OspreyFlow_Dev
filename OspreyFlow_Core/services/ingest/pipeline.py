"""The pipeline graph's own rules and the v1 migration (`06_DECISIONS.md` ADR-108, phase A).

**`pipeline_from_recipe` is a pure function** — a v1 recipe (no stored graph) reads as its one
canonical chain, `domain-model → source → profile → map → load`, every node's `config` taken from
the v1 fields and nothing invented. It is applied at read time and never stored back, so a recipe
written by the old Studio is byte-for-byte what it always was (the same read-time discipline
ADR-106 set for display names).

**`pipeline_rule_violations` is the save gate's graph half** — the row-template half stays
`recipe_rules.recipe_rule_violations`, unchanged. The graph rules: a closed node vocabulary (the
schema enforces it), exactly one domain-model root, no cycles, every edge naming real nodes, every
source reaching a load, and an extract node only downstream of a map (it works on what a map bound,
never on raw bytes). Problems are words a person can act on, in a stable order.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence

from pydantic import TypeAdapter, ValidationError

from ontology.packs import PACK_NAMES
from schemas.domain import OntologySchema
from schemas.ingest import (
    PipelineEdge,
    PipelineGraph,
    PipelineNode,
    PipelineNodeKind,
    RowTemplate,
    StudioRecipeDraft,
)
from schemas.staging import StagingStep, step_inputs

#: The domain pack a v1 recipe reads as: the POLE core itself (phase D's packs overlay it).
CORE_PACK = "pole"


def pipeline_from_recipe(draft: StudioRecipeDraft) -> PipelineGraph:
    """The draft's own graph when it holds one; a v1 draft's canonical chain otherwise."""
    if draft.pipeline is not None:
        return draft.pipeline
    nodes = [
        PipelineNode(
            id="domain",
            kind=PipelineNodeKind.DOMAIN_MODEL,
            label="Domain model",
            config={"pack": CORE_PACK},
        ),
        PipelineNode(
            id="source",
            kind=PipelineNodeKind.SOURCE,
            label=draft.label,
            config={
                "connector_profile": draft.connector_profile,
                "source_location": draft.source_location,
            },
        ),
        PipelineNode(id="profile", kind=PipelineNodeKind.PROFILE, label="Profile"),
        PipelineNode(id="map", kind=PipelineNodeKind.MAP, label="Map"),
        PipelineNode(
            id="load",
            kind=PipelineNodeKind.LOAD,
            label="Load",
            config={"dataset_id": draft.dataset_id},
        ),
    ]
    chain = ["domain", "source", "profile", "map", "load"]
    edges = [
        {"source": a, "target": b} for a, b in zip(chain, chain[1:], strict=False)
    ]
    return PipelineGraph.model_validate({"nodes": nodes, "edges": edges})


def _reaches(graph: PipelineGraph, start: str, kind: PipelineNodeKind) -> bool:
    kinds = {n.id: n.kind for n in graph.nodes}
    forward: dict[str, list[str]] = {}
    for edge in graph.edges:
        forward.setdefault(edge.source, []).append(edge.target)
    queue, seen = deque([start]), {start}
    while queue:
        at = queue.popleft()
        if kinds.get(at) is kind and at != start:
            return True
        for nxt in forward.get(at, []):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return False


def pipeline_rule_violations(graph: PipelineGraph) -> list[str]:
    """Every problem with the graph, in words; empty if none."""
    problems: list[str] = []
    ids = [n.id for n in graph.nodes]
    if len(set(ids)) != len(ids):
        problems.append("two nodes share an id")
    known = set(ids)
    for edge in graph.edges:
        for end in (edge.source, edge.target):
            if end not in known:
                problems.append(f"an edge names a node that is not in the pipeline: '{end}'")

    roots = [n for n in graph.nodes if n.kind is PipelineNodeKind.DOMAIN_MODEL]
    if len(roots) == 0:
        problems.append("the pipeline has no domain model; every pipeline starts from one")
    elif len(roots) > 1:
        problems.append(
            "the pipeline has more than one domain model; exactly one is its root"
        )

    # Kahn's algorithm: anything left over sits on a cycle.
    indegree = dict.fromkeys(known, 0)
    forward: dict[str, list[str]] = {}
    for edge in graph.edges:
        if edge.source in known and edge.target in known:
            indegree[edge.target] += 1
            forward.setdefault(edge.source, []).append(edge.target)
    queue = deque(sorted(node for node, n in indegree.items() if n == 0))
    visited = 0
    while queue:
        at = queue.popleft()
        visited += 1
        for nxt in forward.get(at, []):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    if visited != len(known):
        problems.append("the pipeline holds a cycle; data must flow one way")

    if visited == len(known):  # reachability is only meaningful on an acyclic graph
        for node in graph.nodes:
            reaches_load = _reaches(graph, node.id, PipelineNodeKind.LOAD)
            if node.kind is PipelineNodeKind.SOURCE and not reaches_load:
                problems.append(
                    f"source '{node.label}' reaches no load; its rows would go nowhere"
                )

    for node in graph.nodes:
        if node.kind is PipelineNodeKind.DOMAIN_MODEL:
            pack = node.config.get("pack", CORE_PACK)
            if pack not in (CORE_PACK, *PACK_NAMES):
                problems.append(
                    f"domain model '{node.label}' names an unknown pack '{pack}'; "
                    f"the packs are {CORE_PACK}, {', '.join(PACK_NAMES)}"
                )

    backward: dict[str, list[str]] = {}
    for edge in graph.edges:
        backward.setdefault(edge.target, []).append(edge.source)
    kinds = {n.id: n.kind for n in graph.nodes}
    for node in graph.nodes:
        if node.kind is PipelineNodeKind.EXTRACT:
            feeders = {kinds.get(f) for f in backward.get(node.id, [])}
            if PipelineNodeKind.MAP not in feeders and PipelineNodeKind.EXTRACT not in feeders:
                problems.append(
                    f"extract '{node.label}' is not fed by a map; "
                    "an extract works on what a map bound, never on raw bytes"
                )
    problems.extend(staging_graph_violations(graph))
    return problems


# --- Staging steps as nodes (ADR-140 Amendment 12; Q1 (a)) -------------------------------------

#: The staging catalogue's node kinds (rule 8: closed; the expert steps are phase 8's).
STAGING_KINDS: frozenset[PipelineNodeKind] = frozenset(
    {
        PipelineNodeKind.LOOKUP,
        PipelineNodeKind.JOIN,
        PipelineNodeKind.FILTER,
        PipelineNodeKind.DERIVE,
        PipelineNodeKind.UNION,
        PipelineNodeKind.DEDUPE,
    }
)
_STEP: TypeAdapter[StagingStep] = TypeAdapter(StagingStep)
KIND_LABELS = {
    "lookup": "Lookup", "join": "Join", "filter": "Filter",
    "derive": "Derive", "union": "Union", "dedupe": "Dedupe",
}  # fmt: skip


def step_nodes(graph: PipelineGraph) -> list[PipelineNode]:
    return [n for n in graph.nodes if n.kind in STAGING_KINDS]


def _step_record(node: PipelineNode) -> dict[str, object]:
    return {**node.config, "id": node.id, "kind": node.kind.value}


def _step_of(node: PipelineNode) -> StagingStep:
    return _STEP.validate_python(_step_record(node))


def _record_problems(node: PipelineNode) -> list[str]:
    """A step node's config refused by its kind's record, each cause in words: a missing key, a
    key the step does not declare (rule 8: no expression under a name of its own), a wrong value."""
    try:
        _step_of(node)
    except ValidationError as exc:
        words = []
        for error in exc.errors():
            where = ".".join(str(p) for p in error["loc"][1:]) or "its settings"
            if error["type"] == "extra_forbidden":
                words.append(f"step {node.id!r} declares {where!r}, which a {node.kind.value} "
                             "step does not read")  # fmt: skip
            elif error["type"] == "missing":
                words.append(f"step {node.id!r} needs {where!r}")
            else:
                words.append(f"step {node.id!r}: {where}: {error['msg']}")
        return words
    return []


def _run_order(nodes: Sequence[PipelineNode], inputs: dict[str, list[str]]) -> list[PipelineNode]:
    """The steps so each comes after every step it reads; ties kept in the graph's node order."""
    ordered: list[PipelineNode] = []
    placed: set[str] = set()
    ids = {n.id for n in nodes}
    pending = list(nodes)
    while pending:
        ready = next(
            (n for n in pending if all(t in placed or t not in ids for t in inputs[n.id])), None
        )
        if ready is None:  # a cycle among steps: the graph's own rule says so
            ordered.extend(pending)
            break
        ordered.append(ready)
        placed.add(ready.id)
        pending.remove(ready)
    return ordered


def staging_from_pipeline(graph: PipelineGraph) -> list[StagingStep] | None:
    """The recipe's `staging:` list, built from the pipeline's step nodes in run order: each node's
    id and kind with its config. `None` for a pipeline with no step. Raises pydantic's
    `ValidationError` for a step whose config is not its record; the save gate refuses that first
    (`pipeline_rule_violations`)."""
    nodes = step_nodes(graph)
    if not nodes:
        return None
    steps = {n.id: _step_of(n) for n in nodes}
    order = _run_order(nodes, {i: step_inputs(s) for i, s in steps.items()})
    return [steps[n.id] for n in order]


def pipeline_with_staging(graph: PipelineGraph, staging: Sequence[StagingStep]) -> PipelineGraph:
    """`graph` with `staging` as its step nodes, in place of any it held: each step a node whose
    config is its record less its id and kind; a line from each table it reads, and from the last
    step to each Map, which no source then feeds directly. The inverse of `staging_from_pipeline`
    (`tests/ingest/test_staging_pipeline_nodes.py`)."""
    kept = [n for n in graph.nodes if n.kind not in STAGING_KINDS]
    gone = {n.id for n in graph.nodes} - {n.id for n in kept}
    maps = [n.id for n in kept if n.kind is PipelineNodeKind.MAP]
    sources = {n.id for n in kept if n.kind is PipelineNodeKind.SOURCE}
    edges = [
        e
        for e in graph.edges
        if e.source not in gone and e.target not in gone
        and not (staging and e.source in sources and e.target in maps)
    ]  # fmt: skip
    nodes = list(kept)
    for step in staging:
        record = step.model_dump(by_alias=True, exclude_none=True)
        record.pop("id")
        record.pop("kind")
        nodes.append(
            PipelineNode(
                id=step.id,
                kind=PipelineNodeKind(step.kind),
                label=step.label or KIND_LABELS[step.kind],
                config=record,
            )
        )
        edges.extend(PipelineEdge(source=t, target=step.id) for t in step_inputs(step))
    if staging:
        edges.extend(PipelineEdge(source=staging[-1].id, target=m) for m in maps)
    return PipelineGraph(nodes=nodes, edges=edges)


def staging_graph_violations(graph: PipelineGraph) -> list[str]:
    """The graph's own rules for step nodes: each config its kind's record; each table a step reads
    joined to it by a line, so the canvas never draws what the recipe does not do; and the last
    step feeding a Map. The rest of the save gate (the tables and lists a step may read, its
    adapters) is `staging_catalogue.staging_rule_violations`, which needs the dataset's lists."""
    nodes = step_nodes(graph)
    if not nodes:
        return []
    problems: list[str] = []
    good: dict[str, StagingStep] = {}
    for node in nodes:
        found = _record_problems(node)
        problems.extend(found)
        if not found:
            good[node.id] = _step_of(node)
    if problems:
        return problems
    edges = {(e.source, e.target) for e in graph.edges}
    for node_id, step in good.items():
        for table in step_inputs(step):
            if (table, node_id) not in edges:
                problems.append(
                    f"step {node_id!r} reads {table!r}, but no line joins them on the pipeline"
                )
    order = staging_from_pipeline(graph) or []
    last = order[-1].id
    kinds = {n.id: n.kind for n in graph.nodes}
    if not any(s == last and kinds.get(t) is PipelineNodeKind.MAP for s, t in edges):
        problems.append(f"the last step, {last!r}, feeds no Map: Map reads the last step's table")
    return problems


#: What phase C's runner (`services/api/pipeline_run.py`) runs today. The gate below and the
#: runner's own stage refusals both read these — one vocabulary, two enforcement points.
SUPPORTED_EXTRACT_LIBRARIES = ("stanza", "spacy", "transformers")
SUPPORTED_EXTRACT_MEDIA = ("text",)
SUPPORTED_GEOCODERS = ("local_gazetteer", "online_allowlist")


def pipeline_run_violations(graph: PipelineGraph) -> list[str]:
    """What a publish must refuse because the runner cannot run it (ADR-108 phase C): branches,
    text extraction through the wired recognisers, and gazetteer/allow-list enrichment all run
    now, so what remains is the stage *configuration* the runner would refuse at run time — an
    extract library or media kind outside its set, a handling override missing its mandatory
    reason (ruling Q2), an unknown geocoder. Refused here, in words, rather than published and
    refused loudly later (rule 2 applied as early as the mistake is visible)."""
    problems: list[str] = []
    for node in graph.nodes:
        if node.kind is PipelineNodeKind.EXTRACT:
            library = str(node.config.get("library", "stanza"))
            if library not in SUPPORTED_EXTRACT_LIBRARIES:
                problems.append(
                    f"extract '{node.label}' names the library '{library}'; the runner runs "
                    f"{', '.join(SUPPORTED_EXTRACT_LIBRARIES)}"
                )
            media = str(node.config.get("media", "text"))
            if media not in SUPPORTED_EXTRACT_MEDIA:
                problems.append(
                    f"extract '{node.label}' reads '{media}' media; the runner extracts from "
                    "text documents only for now"
                )
            if node.config.get("handling_override") is not None and not node.config.get(
                "override_reason"
            ):
                problems.append(
                    f"extract '{node.label}' declares a handling override without a reason; "
                    "the reason is mandatory (ruling Q2) — say why the source marking "
                    "over-protects these findings"
                )
        elif node.kind is PipelineNodeKind.ENRICH:
            geocoder = str(node.config.get("geocoder", "local_gazetteer"))
            if geocoder not in SUPPORTED_GEOCODERS:
                problems.append(
                    f"enrich '{node.label}' names the geocoder '{geocoder}'; the runner runs "
                    f"{', '.join(SUPPORTED_GEOCODERS)}"
                )
    return problems


def named_packs(pipeline: PipelineGraph | None) -> list[str]:
    """The packs a pipeline's domain-model nodes name, the core excluded; sorted, once each
    (`06_DECISIONS.md` ADR-120 D10). A recipe with no pipeline names none."""
    if pipeline is None:
        return []
    named = {
        pack
        for node in pipeline.nodes
        if node.kind is PipelineNodeKind.DOMAIN_MODEL
        and isinstance(pack := node.config.get("pack"), str)
        and pack != CORE_PACK
    }
    return sorted(named)


def written_packs(row_template: RowTemplate, ontology: OntologySchema) -> list[str]:
    """The packs that define an entity or link type the row template writes, read from the
    ontology's `type_packs` (ADR-120 Amendment 1, decision 1). A `reference` or `when` entity
    counts, since a row may write it; a core type, or one a pack only widens, maps to no pack."""
    types = [entity.type for entity in row_template.entities]
    types.extend(edge.type for edge in row_template.edges)
    return sorted({ontology.type_packs[t] for t in types if t in ontology.type_packs})


def recipe_packs(
    pipeline: PipelineGraph | None, row_template: RowTemplate, ontology: OntologySchema
) -> list[str]:
    """The packs a recipe pins: those its pipeline names and those whose types its row template
    writes (ADR-120 Amendment 1, decision 1); sorted, once each."""
    return sorted({*named_packs(pipeline), *written_packs(row_template, ontology)})
