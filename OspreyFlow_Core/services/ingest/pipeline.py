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

from ontology.packs import PACK_NAMES
from schemas.ingest import PipelineGraph, PipelineNode, PipelineNodeKind, StudioRecipeDraft

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
    return problems


def pipeline_run_violations(graph: PipelineGraph) -> list[str]:
    """What a publish must refuse because the runner does not run it yet (ADR-108 phase B): a
    valid-to-save pipeline may hold stages ahead of the engine — publishing one is refused in
    words, never published and silently part-run (rule 2). Phase C's runner empties this list."""
    problems: list[str] = []
    sources = [n for n in graph.nodes if n.kind is PipelineNodeKind.SOURCE]
    if len(sources) > 1:
        problems.append(
            "the pipeline holds a second source; the runner runs one source until phase C's "
            "pipeline runner lands — publish one pipeline per source meanwhile"
        )
    for node in graph.nodes:
        if node.kind in (PipelineNodeKind.EXTRACT, PipelineNodeKind.ENRICH):
            problems.append(
                f"the pipeline holds an {node.kind.value} stage ('{node.label}'); the runner "
                "runs it with phase C — remove it to publish now, or wait for phase C"
            )
    return problems
