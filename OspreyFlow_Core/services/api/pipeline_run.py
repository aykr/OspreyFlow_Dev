"""The pipeline runner — `06_DECISIONS.md` ADR-108 phase C.

Runs a published recipe's pipeline graph end to end: every source branch through the existing
engine (`run_published_recipe`, one branch per source, each under its own `load_id` so each stays
independently revertible), then every extract stage over the documents those branches created,
then every enrich stage over the locations they created. The committed YAML is the record — the
topology executed is the `pipeline` block of the recipe loaded from git, never a registry-side
rebuild of it.

**Every stage is loud (rule 2).** A stage that cannot run — an unwired library, a handling
override missing its mandatory reason (ruling Q2), an online geocode with no configured provider
(ruling Q5) — does nothing and says so in its own report's `refusals`, in words; the run never
silently part-executes a stage.

**Extraction output obeys rule 5 either way.** `review_queue` queues pending candidates
(`services/api/review.py`'s own machinery, the same queue the Dossier's quick scan fills);
`inferred_graph` writes nodes through `services/extract/writer.write_candidate`, which writes
`provenance.state = inferred`, never `asserted` — the per-node choice is where findings *wait*,
not whether a human is bypassed.

**Enrichment never merges (rule 6).** A local gazetteer match is a scored, `inferred` `SAME_AS`
edge (`services/geocoder/match.py`); an online geocode writes the point into the analytics
geometry partition and supersedes the node with its `geometry_ref` — a new revision, never an
in-place edit (`01_DOMAIN_MODEL.md` §2.4).

**Access control stays in the adapter (rule 3).** Documents and locations are read back via
`GraphPort.get_node` as the running principal; what the principal cannot view never reaches a
recogniser or a geocoder, and the gazetteer match already refuses candidates the principal may
not view inside `match_place_mention` itself.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
from collections import deque
from collections.abc import Awaitable, Callable
from pathlib import Path

from pydantic import ValidationError
from services.api.review import (
    RECOGNISE_OVERLAP_CHARS,
    RECOGNISE_WINDOW_CHARS,
    ExtractionCandidateStore,
    _shifted,
    run_recognition,
    text_windows,
)
from services.api.rule_evaluation import RuleGate
from services.api.studio_publish import LoadSink, load_published_recipe, run_published_recipe
from services.extract.candidates import ExtractionCandidate
from services.extract.recognised import recognised_candidates
from services.extract.writer import write_candidate
from services.geocoder.match import match_place_mention
from services.ingest.engine import distinct_markings
from services.ingest.geometries import POINT_GEOMETRY_VERSION
from services.ingest.pipeline import (
    SUPPORTED_EXTRACT_LIBRARIES,
    SUPPORTED_EXTRACT_MEDIA,
    SUPPORTED_GEOCODERS,
    pipeline_from_recipe,
)

from conduit_common.identity import new_node_id
from knowledge_adapters import REGISTRY
from ontology.handling import HandlingScheme
from ports.analytics import AnalyticsPort
from ports.graph import GraphPort
from ports.media import MediaStore
from ports.recognise import RecognisePort, RecogniserRefusedError
from schemas.analytics import GeometryKind, GeometryRecord
from schemas.domain import Handling, Node, NodeWrite, OntologySchema, Principal, TxId
from schemas.ingest import (
    BranchRunReport,
    EnrichStageReport,
    ExtractStageReport,
    PipelineGraph,
    PipelineNode,
    PipelineNodeKind,
    PipelineRunReport,
    StudioRecipeDraft,
)

#: The coordinate system an online provider answers in (ruling Q5's allow-listed providers are
#: WGS84 lon/lat APIs).
_ONLINE_CRS = "EPSG:4326"

RecogniserFor = Callable[[str], RecognisePort | None]
OnlineGeocode = Callable[[str], Awaitable[tuple[float, float] | None]]


def recogniser_for_deployment(stanza: RecognisePort) -> RecogniserFor:
    """The deployment's recogniser lookup: `stanza` is the ner sidecar the Conduit already runs
    (ADR-098); `spacy` and `transformers` load in process, lazily and once — their model weights
    are venv-pinned (ruling Q3), so an import that fails means the deployment was built without
    the `extraction` extra, and the stage refuses in words rather than the route failing."""
    cache: dict[str, RecognisePort | None] = {"stanza": stanza}

    def get(name: str) -> RecognisePort | None:
        if name not in cache:
            # The adapters import their libraries lazily, so it is the library that is looked for;
            # importing the adapter alone succeeded without it and the stage then crashed.
            if name in ("spacy", "transformers") and importlib.util.find_spec(name) is None:
                cache[name] = None
                return None
            try:
                if name == "spacy":
                    from adapters.recognise_spacy.adapter import RecogniseSpacyAdapter

                    cache[name] = RecogniseSpacyAdapter()
                elif name == "transformers":
                    from adapters.recognise_transformers.adapter import (
                        RecogniseTransformersAdapter,
                    )

                    cache[name] = RecogniseTransformersAdapter()
                else:
                    cache[name] = None
            except ImportError:
                cache[name] = None
        return cache[name]

    return get


def online_geocode_from_env() -> OnlineGeocode | None:
    """Ruling Q5's allow-list, as deployment configuration: `OSPREY_ONLINE_GEOCODER` names the one
    provider this deployment may call out to (`nominatim` is the one wired), and nothing set means
    no online geocoding at all — the enrich stage then says so in its own report rather than
    quietly skipping. The provider call runs in a thread; geopy is synchronous."""
    provider = os.environ.get("OSPREY_ONLINE_GEOCODER", "").strip()
    if provider != "nominatim":
        return None
    from geopy.geocoders import Nominatim

    geolocator = Nominatim(user_agent="ospreyflow-enrich")

    async def geocode(name: str) -> tuple[float, float] | None:
        place = await asyncio.to_thread(geolocator.geocode, name)
        if place is None:
            return None
        return (place.longitude, place.latitude)

    return geocode


def _topological(graph: PipelineGraph) -> list[PipelineNode]:
    """Kahn's order, ties broken by node id — the save gate guarantees acyclicity, but a runner
    ordering is re-derived here rather than trusted from the stored node list's accidents."""
    by_id = {n.id: n for n in graph.nodes}
    indegree = dict.fromkeys(by_id, 0)
    forward: dict[str, list[str]] = {}
    for edge in graph.edges:
        if edge.source in by_id and edge.target in by_id:
            indegree[edge.target] += 1
            forward.setdefault(edge.source, []).append(edge.target)
    queue = deque(sorted(node_id for node_id, n in indegree.items() if n == 0))
    ordered: list[PipelineNode] = []
    while queue:
        at = queue.popleft()
        ordered.append(by_id[at])
        for nxt in sorted(forward.get(at, [])):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    return ordered


def _upstream_sources(graph: PipelineGraph, node_id: str) -> list[str]:
    """The source nodes whose branches feed `node_id`, walking data-dependencies backward."""
    kinds = {n.id: n.kind for n in graph.nodes}
    backward: dict[str, list[str]] = {}
    for edge in graph.edges:
        backward.setdefault(edge.target, []).append(edge.source)
    queue, seen, sources = deque([node_id]), {node_id}, []
    while queue:
        at = queue.popleft()
        if kinds.get(at) is PipelineNodeKind.SOURCE:
            sources.append(at)
        for back in backward.get(at, []):
            if back not in seen:
                seen.add(back)
                queue.append(back)
    return sorted(sources)


async def _mark_uncovered(
    sink: LoadSink | None, branches: list[BranchRunReport], source_ids: list[str]
) -> None:
    """Each branch a stage that wrote something was fed by has a record that does not cover it
    (ADR-127 decision 6, Amendment 6): said on the record, so a revert refuses the load."""
    if sink is None:
        return
    wanted = set(source_ids)
    for branch in branches:
        if branch.source_id in wanted:
            await sink.uncovered(branch.report.load_id)


async def _created_nodes_of_type(
    graph: GraphPort,
    branches: list[BranchRunReport],
    source_ids: list[str],
    node_type: str,
    principal: Principal,
) -> tuple[list[Node], int]:
    """The nodes of `node_type` the named branches created, as `principal` may view them.
    Returns the visible nodes and how many were withheld — withheld is counted, never silent
    (rule 2), and never read around the adapter's own filter (rule 3)."""
    nodes: list[Node] = []
    withheld = 0
    wanted = set(source_ids)
    for branch in branches:
        if branch.source_id not in wanted:
            continue
        for node_id in branch.report.created_node_ids:
            node = await graph.get_node(node_id, principal)
            if node is None:
                withheld += 1
                continue
            if node.type == node_type:
                nodes.append(node)
    return nodes, withheld


async def _run_extract_stage(
    node: PipelineNode,
    *,
    pipeline: PipelineGraph,
    branches: list[BranchRunReport],
    graph: GraphPort,
    ontology: OntologySchema,
    principal: Principal,
    recogniser_for: RecogniserFor,
    candidates: ExtractionCandidateStore | None,
    media: MediaStore | None,
) -> tuple[ExtractStageReport, list[str]]:
    """One extract node's run. Returns the stage report and the node ids written `inferred`
    (empty for `review_queue` output)."""
    library = str(node.config.get("library", "stanza"))
    output = str(node.config.get("output", "review_queue"))
    report = ExtractStageReport(node_id=node.id, library=library, output=output)
    written_ids: list[str] = []

    media_kind = str(node.config.get("media", "text"))
    if media_kind not in SUPPORTED_EXTRACT_MEDIA:
        report.refusals.append(
            f"this runner extracts from text documents only; '{media_kind}' media comes later"
        )
        return report, written_ids
    if library not in SUPPORTED_EXTRACT_LIBRARIES:
        report.refusals.append(
            f"the extraction library '{library}' is not one this runner runs; "
            f"it runs {', '.join(SUPPORTED_EXTRACT_LIBRARIES)}"
        )
        return report, written_ids
    recogniser = recogniser_for(library)
    if recogniser is None:
        report.refusals.append(
            f"the extraction library '{library}' is not available in this deployment; "
            "nothing was extracted by this stage"
        )
        return report, written_ids
    if output == "review_queue" and candidates is None:
        report.refusals.append(
            "no review queue store is wired; the stage's findings had nowhere to go"
        )
        return report, written_ids
    if media is None:
        report.refusals.append(
            "no media store is wired; a document's text lives there, so nothing could be read"
        )
        return report, written_ids

    override_raw = node.config.get("handling_override")
    override_reason = node.config.get("override_reason")
    override: Handling | None = None
    if override_raw is not None:
        if not override_reason:
            report.refusals.append(
                "the stage declares a handling override without a reason; ruling Q2 makes the "
                "reason mandatory, so nothing was extracted"
            )
            return report, written_ids
        try:
            override = Handling.model_validate(override_raw)
        except ValidationError as error:
            report.refusals.append(f"the handling override does not read as a handling: {error}")
            return report, written_ids
        report.override_reason = str(override_reason)

    documents, withheld = await _created_nodes_of_type(
        graph, branches, _upstream_sources(pipeline, node.id), "Document", principal
    )
    if withheld:
        report.refusals.append(
            f"{withheld} element(s) this run created could not be read back by the running "
            "principal and were not extracted"
        )
    for document in documents:
        if document.properties.get("media_kind") != "text":
            continue
        text = (await media.get(document.properties["object_ref"])).decode("utf-8")
        handling = override if override is not None else document.handling
        # Rule 3, ADR-127 Amendment 26: what the stage read is at the document's marking and what
        # it wrote at `handling` (the override where there is one): the counts include both.
        report.markings = distinct_markings(report.markings, [document.handling, handling])
        try:
            if output == "inferred_graph":
                found: list[ExtractionCandidate] = []
                seen: set[tuple[str, str]] = set()
                for offset, window in text_windows(
                    text, RECOGNISE_WINDOW_CHARS, RECOGNISE_OVERLAP_CHARS
                ):
                    result = await recogniser.recognise(window)
                    for candidate in recognised_candidates(
                        result, window, document.id, handling, ontology
                    ):
                        located = _shifted(candidate, offset)
                        key = (located.entity_type, located.locator)
                        if key not in seen:
                            seen.add(key)
                            found.append(located)
                tx = await graph.begin_transaction()
                try:
                    for candidate in found:
                        written_ids.append(
                            await write_candidate(
                                graph, candidate, created_by=principal.id, tx=tx
                            )
                        )
                except Exception:
                    await graph.rollback_transaction(tx)
                    raise
                await graph.commit_transaction(tx)
                report.nodes_written_inferred += len(found)
                if override is not None:
                    report.handling_overridden += len(found)
            else:
                assert candidates is not None
                records = await run_recognition(
                    recogniser,
                    ontology,
                    candidates,
                    document_id=document.id,
                    text=text,
                    handling=handling,
                    principal=principal,
                )
                report.candidates_queued += len(records)
                if override is not None:
                    report.handling_overridden += len(records)
        except RecogniserRefusedError as refusal:
            report.refusals.append(
                f"document '{document.properties.get('title', document.id)}' was refused by the "
                f"recogniser: {refusal}"
            )
            continue
        report.documents_read += 1
    return report, written_ids


async def _run_enrich_stage(
    node: PipelineNode,
    *,
    pipeline: PipelineGraph,
    branches: list[BranchRunReport],
    graph: GraphPort,
    principal: Principal,
    scheme: HandlingScheme,
    analytics: AnalyticsPort | None,
    online_geocode: OnlineGeocode | None,
) -> tuple[EnrichStageReport, list[str]]:
    """One enrich node's run. Returns the stage report and the `SAME_AS` edge ids it wrote."""
    geocoder = str(node.config.get("geocoder", "local_gazetteer"))
    report = EnrichStageReport(node_id=node.id, geocoder=geocoder)
    edge_ids: list[str] = []
    if geocoder not in SUPPORTED_GEOCODERS:
        report.refusals.append(
            f"the geocoder '{geocoder}' is not one this runner runs; "
            f"it runs {', '.join(SUPPORTED_GEOCODERS)}"
        )
        return report, edge_ids

    online = geocoder == "online_allowlist"
    if online and online_geocode is None:
        report.refusals.append(
            "no online geocoding provider is configured on this deployment's allow-list "
            "(ruling Q5); only the local gazetteer was consulted"
        )
    if online and analytics is None:
        report.refusals.append(
            "no analytics store is wired, so an online geocode's point had nowhere to live; "
            "only the local gazetteer was consulted"
        )

    locations, withheld = await _created_nodes_of_type(
        graph, branches, _upstream_sources(pipeline, node.id), "Location", principal
    )
    if withheld:
        report.refusals.append(
            f"{withheld} element(s) this run created could not be read back by the running "
            "principal and were not enriched"
        )
    run_created = {
        node_id for branch in branches for node_id in branch.report.created_node_ids
    }
    to_ref = REGISTRY["geometry_ref"]

    tx = await graph.begin_transaction()
    try:
        for mention in locations:
            name = mention.properties.get("name")
            if not name or mention.properties.get("geometry_ref"):
                continue
            report.locations_considered += 1
            suggestions = await graph.suggest_locations(str(name), principal)
            gazetteer = [
                c for c in suggestions if c.id != mention.id and c.id not in run_created
            ]
            edge = await match_place_mention(graph, mention, gazetteer, principal, scheme, tx)
            if edge is not None:
                report.matched_local += 1
                edge_ids.append(edge.id)
                continue
            if online and online_geocode is not None and analytics is not None:
                coordinates = await online_geocode(str(name))
                if coordinates is not None:
                    await _persist_online_point(
                        graph, analytics, mention, coordinates, to_ref, principal, tx
                    )
                    report.matched_online += 1
                    continue
            report.unmatched += 1
    except Exception:
        await graph.rollback_transaction(tx)
        raise
    await graph.commit_transaction(tx)
    return report, edge_ids


async def _persist_online_point(
    graph: GraphPort,
    analytics: AnalyticsPort,
    mention: Node,
    coordinates: tuple[float, float],
    to_ref: Callable[..., str],
    principal: Principal,
    tx: TxId,
) -> None:
    """An online geocode made durable: the point as a geometry-partition row (insert-only, keyed
    by its deterministic ref) and the mention superseded with that `geometry_ref` — a new node
    revision, never an in-place edit."""
    lon, lat = coordinates
    ref = to_ref((str(lon), str(lat)), source_crs=_ONLINE_CRS)
    held = {
        record.geometry_ref
        for record in await analytics.get_geometries(
            [ref], principal, version=POINT_GEOMETRY_VERSION
        )
    }
    if ref not in held:
        await analytics.load_geometries(
            [
                GeometryRecord(
                    geometry_ref=ref,
                    version=POINT_GEOMETRY_VERSION,
                    kind=GeometryKind.POINT,
                    lon=lon,
                    lat=lat,
                    source_crs=_ONLINE_CRS,
                    source_x=lon,
                    source_y=lat,
                    handling=mention.handling,
                )
            ]
        )
    now = mention.audit.created_at
    replacement = NodeWrite(
        id=new_node_id(),
        type=mention.type,
        properties={**mention.properties, "geometry_ref": ref},
        provenance=mention.provenance,
        handling=mention.handling,
        created_by=principal.id,
        created_at=now,
    )
    await graph.supersede_node(mention.id, replacement, tx)


async def run_published_pipeline(
    draft: StudioRecipeDraft,
    principal: Principal,
    *,
    graph: GraphPort,
    ontology: OntologySchema,
    scheme: HandlingScheme,
    load_id: str,
    investigation_scope: str,
    repo_root: Path,
    recogniser_for: RecogniserFor,
    candidates: ExtractionCandidateStore | None = None,
    analytics: AnalyticsPort | None = None,
    media: MediaStore | None = None,
    source_location: str | None = None,
    online_geocode: OnlineGeocode | None = None,
    rules: RuleGate | None = None,
    sink: LoadSink | None = None,
) -> PipelineRunReport:
    """The whole pipeline, in topological order: branches, then extracts, then enriches.

    `source_location`, when given, overrides the location of every source node that does not
    carry its own — the same "today's fresh export" override `run_published_recipe` has, applied
    to the sources that read the draft's own recorded location. A source node carrying its own
    `source_location` in its config keeps it."""
    recipe = load_published_recipe(draft, repo_root) if draft.git_path else None
    pipeline = (
        recipe.pipeline
        if recipe is not None and recipe.pipeline is not None
        else pipeline_from_recipe(draft)
    )

    report = PipelineRunReport(
        load_id=load_id, recipe_id=draft.recipe_id, recipe_version=draft.version
    )
    ordered = _topological(pipeline)

    for node in ordered:
        if node.kind is not PipelineNodeKind.SOURCE:
            continue
        branch_location = node.config.get("source_location") or source_location
        branch_report = await run_published_recipe(
            draft,
            principal,
            graph=graph,
            ontology=ontology,
            load_id=f"{load_id}:{node.id}",
            investigation_scope=investigation_scope,
            source_location=branch_location,
            repo_root=repo_root,
            analytics=analytics,
            media=media,
            rules=rules,
            scheme=scheme,
            sink=sink,
        )
        report.branches.append(
            BranchRunReport(
                source_id=node.id,
                source_label=node.label,
                source_location=branch_location or draft.source_location,
                report=branch_report,
            )
        )

    for node in ordered:
        if node.kind is PipelineNodeKind.EXTRACT:
            extract_stage, written = await _run_extract_stage(
                node,
                pipeline=pipeline,
                branches=report.branches,
                graph=graph,
                ontology=ontology,
                principal=principal,
                recogniser_for=recogniser_for,
                candidates=candidates,
                media=media,
            )
            report.extracts.append(extract_stage)
            report.created_node_ids.extend(written)
            report.nodes_created += len(written)
            if written:
                await _mark_uncovered(sink, report.branches, _upstream_sources(pipeline, node.id))
        elif node.kind is PipelineNodeKind.ENRICH:
            enrich_stage, edges = await _run_enrich_stage(
                node,
                pipeline=pipeline,
                branches=report.branches,
                graph=graph,
                principal=principal,
                scheme=scheme,
                analytics=analytics,
                online_geocode=online_geocode,
            )
            report.enriches.append(enrich_stage)
            report.touched_edge_ids.extend(edges)
            report.edges_created += len(edges)
            # Its `SAME_AS` links, and the points an online geocode inserts and the node revisions
            # it writes, are in no record.
            if edges or enrich_stage.matched_online:
                await _mark_uncovered(sink, report.branches, _upstream_sources(pipeline, node.id))

    for branch in report.branches:
        report.rows_read += branch.report.rows_read
        report.rows_already_loaded += branch.report.rows_already_loaded
        report.nodes_created += branch.report.nodes_created
        report.nodes_referenced += branch.report.nodes_referenced
        report.edges_created += branch.report.edges_created
        report.rejections.extend(branch.report.rejections)
        report.rows_held += branch.report.rows_held
        report.rule_notes.extend(branch.report.rule_notes)
        report.created_node_ids.extend(branch.report.created_node_ids)
        report.referenced_node_ids.extend(branch.report.referenced_node_ids)
        report.touched_edge_ids.extend(branch.report.touched_edge_ids)
    # Rule 3, ADR-127 Amendment 23: the counts above are the branches' together, so a reader must
    # be able to view every marking any branch wrote at to be shown them.
    # An extract stage's counts are in it too, at what it read and what it wrote (its override
    # included), which may be above every branch's.
    report.markings = distinct_markings(
        *(b.report.markings for b in report.branches), *(e.markings for e in report.extracts)
    )
    # A node one branch referenced and another created is the second's own: named once, as created.
    created = set(report.created_node_ids)
    report.referenced_node_ids = [
        node_id
        for node_id in dict.fromkeys(report.referenced_node_ids)
        if node_id not in created
    ]
    return report
