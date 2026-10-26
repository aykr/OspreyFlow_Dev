"""ADR-127 Amendments 23 and 27 ("The pictures"): the picture service's shared core, and the seed's
path through it. No store, no socket: the graph fake of `test_entity_picture_stored_link_ids.py`
(which merges a same-pair, same-audience link write as the adapter does), the in-memory media store
and a recording audit writer. The same invariants against the real adapter are in
`test_entity_pictures.py` ("seed" cases).

The invariants, and the case that fails if each is broken:

- the refusals live in the core, so the seed's path is bound by them as the route is
  (`test_a_refusal_holds_on_both_paths`);
- the seed attaches only to a subject with no `DEPICTS` link at all, shown or removed, of any name,
  and never writes to a subject's picture history (`test_a_subject_with_any_picture_history_is_left_
  alone`, `test_a_removal_is_left_exactly_as_the_analyst_left_it`);
- the seed touches no working set (`test_the_seed_touches_no_working_set`);
- the seed re-reads its subject as the worker and refuses an unscoped worker, a subject not
  returned, and a subject it cannot mark faithfully (`test_the_seed_refuses_...`);
- a service without a scheme refuses on both paths (`test_a_service_without_a_scheme_refuses_...`);
- both paths write the same audit entry, before the graph commit (`test_both_paths_write_the_same_
  audit_entry`, `test_the_audit_is_written_before_the_graph_commit`);
- a seeded picture is an ordinary one to an analyst afterwards (`test_a_seeded_picture_is_found_...`);
- the picture takes the subject's classification and handling code and the worker's unit, no action
  or sanitisation code, and provenance naming the seed (`test_the_seeded_picture_is_marked_...`);
- the lifespan builds the service with `app.state.audit` and the scheme itself, not merely keywords
  of those names (`test_the_lifespan_gives_the_service_the_audit_and_the_scheme`).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
from services.api.document_content import UploadRefusedError
from services.api.entity_pictures import EntityPictureService, PictureNotFoundError
from services.api.working_set.service import WorkingSetService
from services.extract.writer import NodeNotFoundError

from adapters.media_objectstore.testing import InMemoryMediaStore
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import EdgeWrite, Handling, Node, Principal, Subgraph

from .test_entity_picture_stored_link_ids import CAR, PictureGraph
from .working_set.fakes import FakeGraphPort, FakeWorkingSetStore

ONTOLOGY = load_default_ontology()
SCHEME = load_uk_le_scheme()
WORKER = Principal(
    id="pid-seed-worker", clearance="OFFICIAL", org_unit="verify", datasets=["prison-intelligence"]
)
UNSCOPED = WORKER.model_copy(update={"datasets": None})
SECRET_WORKER = WORKER.model_copy(update={"clearance": "SECRET"})
ANALYST = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="verify")
BASIS = "Synthetic demonstration data"
PNG_A = b"\x89PNG\r\n\x1a\nfirst"
PNG_B = b"\x89PNG\r\n\x1a\nsecond"
APP = Path(__file__).parents[3] / "../OspreyFlow_Core/services/api/app.py"


class _Audit:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> None:
        self.rows.append(kwargs)


class _NoWorkingSet:
    """Any use of it fails the test: the seed's path must not touch a working set."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"the seed's path used the working set ({name})")


class _OrderedGraph(PictureGraph):
    """Records what the audit held at the moment of the commit."""

    def __init__(self, audit: _Audit) -> None:
        super().__init__()
        self.audit = audit
        self.audit_rows_at_commit: list[int] = []

    async def commit_transaction(self, tx: Any) -> None:
        self.audit_rows_at_commit.append(len(self.audit.rows))


def _subject(
    node_id: str = "car-1",
    node_type: str = "Vehicle",
    *,
    classification: str = "OFFICIAL",
    handling_code: str = "P",
    action_code: str | None = None,
    sanitisation_code: str | None = None,
) -> Node:
    return CAR.model_copy(
        update={
            "id": node_id,
            "type": node_type,
            "handling": Handling(
                classification=classification,
                handling_code=handling_code,
                action_code=action_code,
                sanitisation_code=sanitisation_code,
                originator="fenwick-moor-security",
                owning_unit="fenwick-moor-security",
            ),
        }
    )


class _Fx:
    def __init__(
        self, service: EntityPictureService, graph: PictureGraph, audit: _Audit, media: Any
    ) -> None:
        self.service = service
        self.graph = graph
        self.audit = audit
        self.media = media


async def _build(
    subject: Node | None = None, *, working_set: Any = None, ordered: bool = False
) -> _Fx:
    subject = subject or _subject()
    audit = _Audit()
    graph = _OrderedGraph(audit) if ordered else PictureGraph()
    graph.nodes[subject.id] = subject
    store = FakeWorkingSetStore()
    await store.add_nodes("inv-1", [subject])
    media = InMemoryMediaStore()
    service = EntityPictureService(
        working_set
        or WorkingSetService(
            FakeGraphPort(Subgraph(nodes=[], edges=[])),
            store,
            SCHEME,  # type: ignore[arg-type]
        ),
        graph,  # type: ignore[arg-type]
        media,
        ONTOLOGY,
        scheme=SCHEME,
        audit=audit,
    )
    return _Fx(service, graph, audit, media)


def _handling(classification: str = "OFFICIAL") -> Handling:
    return Handling(
        classification=classification,
        handling_code="P",
        originator="verify",
        owning_unit="verify",
    )


async def _route_set(
    fx: _Fx,
    subject: Node,
    name: str = "car.png",
    data: bytes = PNG_A,
    principal: Principal = ANALYST,
) -> str:
    result = await fx.service.set(
        "inv-1",
        subject.id,
        principal,
        name=name,
        data=data,
        handling=_handling(subject.handling.classification),
        legal_basis=BASIS,
    )
    return result.document_id


async def _seed(
    fx: _Fx,
    subject: Node,
    name: str = "car.png",
    data: bytes = PNG_A,
    principal: Principal = WORKER,
) -> bool:
    return await fx.service.attach_for_seed(
        "inv-1", subject.id, principal, name=name, data=data, legal_basis=BASIS
    )


def _nothing_written(fx: _Fx) -> bool:
    return not fx.graph.links and not fx.audit.rows and not fx.media.files


@pytest.mark.parametrize("path", ["route", "seed"])
@pytest.mark.parametrize(
    ("subject", "refusal"),
    [
        (_subject(classification="SECRET"), "could not read"),
        (_subject("meeting-1", "Event"), "cannot have a picture"),
    ],
    ids=["a marking the caller cannot read", "a target type DEPICTS does not allow"],
)
async def test_a_refusal_holds_on_both_paths(path: str, subject: Node, refusal: str) -> None:
    fx = await _build(subject)
    with pytest.raises(UploadRefusedError, match=refusal):
        if path == "route":
            await _route_set(fx, subject)
        else:
            await _seed(fx, subject)
    assert _nothing_written(fx), "a refused picture left something behind"


async def test_a_subject_with_any_picture_history_is_left_alone() -> None:
    subject = _subject()
    fx = await _build(subject)
    assert await _seed(fx, subject, "front.png", PNG_A) is True
    held = (list(fx.graph.links), len(fx.audit.rows))
    # Whatever the name, and whatever the bytes, a second seed writes nothing.
    assert await _seed(fx, subject, "front.png", PNG_A) is False
    assert await _seed(fx, subject, "front.png", PNG_B) is False
    assert await _seed(fx, subject, "side.png", PNG_B) is False
    assert (list(fx.graph.links), len(fx.audit.rows)) == held
    # A subject with no history still takes the same name.
    other = _subject("car-2")
    fx.graph.nodes["car-2"] = other
    assert await _seed(fx, other, "front.png", PNG_A) is True


async def test_a_removal_is_left_exactly_as_the_analyst_left_it() -> None:
    subject = _subject()
    fx = await _build(subject)
    assert await _seed(fx, subject, "front.png", PNG_A) is True
    await fx.service.remove("inv-1", "car-1", ANALYST)
    (removal,) = fx.graph.live
    assert removal.properties["shown"] is False
    audit_rows = len(fx.audit.rows)
    # The same bytes, so the same Document and the same pair: the real store merges a write into
    # the removal record, and the fake does too, so only the seed's own refusal can prevent it.
    assert await _seed(fx, subject, "front.png", PNG_A) is False
    assert await _seed(fx, subject, "other-name.png", PNG_B) is False
    assert fx.graph.live == [removal]
    assert len(fx.audit.rows) == audit_rows
    assert await fx.service.pictures("inv-1", ["car-1"], ANALYST) == []


async def test_a_replacement_under_another_name_is_left_as_the_analyst_left_it() -> None:
    subject = _subject()
    fx = await _build(subject)
    assert await _seed(fx, subject, "front.png", PNG_A) is True
    mine = await _route_set(fx, subject, "mine.png", PNG_B, ANALYST)
    live = list(fx.graph.live)
    assert await _seed(fx, subject, "front.png", PNG_A) is False
    assert fx.graph.live == live
    assert [p.document_id for p in await fx.service.pictures("inv-1", ["car-1"], ANALYST)] == [mine]


async def test_the_fake_merges_a_same_pair_write_as_the_adapter_does() -> None:
    """Rule 15: the fake merges exactly where the adapter's audience does. A write of the pair and
    audience of a live link lands in that link, under its id; a write of the same pair in another
    dataset, or of another unit under a restricted code, is a link of its own. Driven through
    `upsert_edges` itself, so the check does not rest on the route's own behaviour (the route's
    re-upload after a removal merging into the removal record is a separate build-plan row)."""
    subject = _subject()
    fx = await _build(subject)
    await _route_set(fx, subject, "front.png", PNG_A)
    (held,) = fx.graph.live

    def write(wid: str, **changes: Any) -> EdgeWrite:
        fields: dict[str, Any] = {
            "id": wid,
            "type": held.type,
            "source": held.source,
            "target": held.target,
            "properties": {"shown": False},
            "provenance": held.provenance,
            "handling": held.handling,
            "created_by": "someone",
            "created_at": held.audit.created_at,
        }
        fields.update(changes)
        return EdgeWrite(**fields)

    restricted = held.handling.model_copy(update={"handling_code": "R"})
    ids = await fx.graph.upsert_edges(
        [
            write("w-same"),
            write("w-ds", datasets=["another-dataset"]),
            write("w-unit-a", handling=restricted),
            write(
                "w-unit-b",
                handling=restricted.model_copy(update={"originator": "u-x", "owning_unit": "u-x"}),
            ),
        ],
        "tx",
    )
    assert ids[0] == held.id, "a same-audience write did not merge"
    assert ids[1] != held.id, "a write in another dataset merged"
    assert len({ids[2], ids[3], held.id}) == 3, "restricted writes of two units merged"


async def test_the_seed_touches_no_working_set() -> None:
    subject = _subject()
    fx = await _build(subject, working_set=_NoWorkingSet())
    assert await _seed(fx, subject, "front.png") is True
    assert await _seed(fx, subject, "side.png", PNG_B) is False
    assert len(fx.graph.live) == 1


async def test_the_seed_refuses_an_unscoped_worker_and_a_subject_it_cannot_read() -> None:
    subject = _subject()
    fx = await _build(subject)
    with pytest.raises(UploadRefusedError, match="scoped to a case"):
        await _seed(fx, subject, principal=UNSCOPED)
    with pytest.raises(NodeNotFoundError):
        await fx.service.attach_for_seed(
            "inv-1", "car-9", WORKER, name="car.png", data=PNG_A, legal_basis=BASIS
        )
    assert _nothing_written(fx)


@pytest.mark.parametrize(
    "subject",
    [
        _subject(handling_code="R"),
        _subject(action_code="A1"),
        _subject(sanitisation_code="S2"),
    ],
    ids=["a restricted code", "an action code", "a sanitisation code"],
)
async def test_the_seed_refuses_a_subject_it_cannot_mark_faithfully(subject: Node) -> None:
    fx = await _build(subject)
    with pytest.raises(UploadRefusedError, match="cannot take a seeded picture"):
        await _seed(fx, subject)
    assert _nothing_written(fx)


async def test_a_service_without_a_scheme_refuses_on_both_paths() -> None:
    subject = _subject()
    fx = await _build(subject)
    bare = EntityPictureService(
        fx.service._working_set,
        fx.graph,  # type: ignore[arg-type]
        fx.media,
        ONTOLOGY,
        audit=fx.audit,
    )
    with pytest.raises(RuntimeError, match="scheme"):
        await bare.set(
            "inv-1", "car-1", WORKER, name="car.png", data=PNG_A, handling=_handling(),
            legal_basis=BASIS,
        )  # fmt: skip
    with pytest.raises(RuntimeError, match="scheme"):
        await bare.attach_for_seed(
            "inv-1", "car-1", WORKER, name="car.png", data=PNG_A, legal_basis=BASIS
        )
    assert _nothing_written(fx)


async def test_both_paths_write_the_same_audit_entry() -> None:
    subject = _subject()
    routed, seeded = await _build(subject), await _build(subject)
    await _route_set(routed, subject)
    await _seed(seeded, subject)
    (route_row,) = routed.audit.rows
    (seed_row,) = seeded.audit.rows
    assert {**route_row, "principal": None} == {**seed_row, "principal": None}
    assert (route_row["principal"], seed_row["principal"]) == (ANALYST, WORKER)
    assert route_row["action"] == "set_entity_picture"
    assert route_row["investigation_id"] == "inv-1"
    assert route_row["result_cardinality"] == 1
    assert route_row["resolved_query"] == {
        "node_id": "car-1",
        "document_id": route_row["resolved_query"]["document_id"],
        "name": "car.png",
        "size": len(PNG_A),
        "classification": "OFFICIAL",
        "legal_basis": BASIS,
    }
    assert route_row["resolved_query"]["document_id"].startswith("content:")


@pytest.mark.parametrize("path", ["route", "seed"])
async def test_the_audit_is_written_before_the_graph_commit(path: str) -> None:
    subject = _subject()
    fx = await _build(subject, ordered=True)
    if path == "route":
        await _route_set(fx, subject)
    else:
        await _seed(fx, subject)
    assert fx.graph.audit_rows_at_commit == [1], "the commit came before the audit entry"  # type: ignore[attr-defined]


async def test_a_seeded_picture_is_found_by_the_routes_reads_and_replaced_and_removed() -> None:
    subject = _subject()
    fx = await _build(subject)
    assert await _seed(fx, subject, "front.png", PNG_A) is True
    shown = await fx.service.pictures("inv-1", ["car-1"], ANALYST)
    assert [p.node_id for p in shown] == ["car-1"]
    assert await fx.service.file("inv-1", "car-1", ANALYST) == (PNG_A, "image/png")

    # An analyst's own picture afterwards supersedes the seeded one...
    new = await _route_set(fx, subject, "mine.png", PNG_B, ANALYST)
    (live,) = fx.graph.live
    assert live.source == new
    assert [p.document_id for p in await fx.service.pictures("inv-1", ["car-1"], ANALYST)] == [new]

    # ...and removing the seeded picture of a fresh subject shows nothing afterwards.
    other = _subject("car-2")
    fx.graph.nodes["car-2"] = other
    await fx.service._working_set._store.add_nodes("inv-1", [other])  # type: ignore[attr-defined]
    assert await _seed(fx, other, "front.png", PNG_A) is True
    await fx.service.remove("inv-1", "car-2", ANALYST)
    assert await fx.service.pictures("inv-1", ["car-2"], ANALYST) == []
    with pytest.raises(PictureNotFoundError):
        await fx.service.file("inv-1", "car-2", ANALYST)


async def test_the_seeded_picture_is_marked_as_amendment_27_says() -> None:
    """A SECRET-cleared worker and a SECRET subject with a conditional code (`C`, permitted by the
    scheme, not restricted): the picture takes the subject's classification and code, the worker's
    unit, no action or sanitisation code, and provenance naming the seed."""
    subject = _subject(classification="SECRET", handling_code="C")
    fx = await _build(subject)
    assert await _seed(fx, subject, principal=SECRET_WORKER) is True
    (link,) = fx.graph.live
    document = fx.graph.nodes[link.source]
    for held in (link.handling, document.handling):
        assert held.classification == "SECRET"
        assert held.handling_code == "C"
        assert (held.action_code, held.sanitisation_code) == (None, None)
        assert (held.originator, held.owning_unit) == (WORKER.org_unit, WORKER.org_unit)
        assert held.legal_basis is None
    for provenance in (link.provenance, document.provenance):
        assert [s.document_id for s in provenance.sources] == ["seed:pid-seed-worker:car.png"]


async def test_the_route_keeps_its_upload_provenance() -> None:
    subject = _subject()
    fx = await _build(subject)
    await _route_set(fx, subject)
    (link,) = fx.graph.live
    assert [s.document_id for s in link.provenance.sources] == ["upload:car.png"]


async def test_a_seeded_picture_needs_an_audit_writer() -> None:
    subject = _subject()
    fx = await _build(subject)
    unaudited = EntityPictureService(
        fx.service._working_set,
        fx.graph,  # type: ignore[arg-type]
        InMemoryMediaStore(),
        ONTOLOGY,
        scheme=SCHEME,
    )
    with pytest.raises(RuntimeError, match="audit"):
        await unaudited.attach_for_seed(
            "inv-1", "car-1", WORKER, name="car.png", data=PNG_A, legal_basis=BASIS
        )


def _lifespan_service_call() -> ast.Call:
    tree = ast.parse(APP.read_text())
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "EntityPictureService"
    ]
    assert len(calls) == 1
    return calls[0]


def test_the_lifespan_gives_the_service_the_audit_and_the_scheme() -> None:
    """The values, not only the keywords: `app.state.audit` (the writer the routes use) and the
    scheme the lifespan loaded, which is the one the graph adapter was built with."""
    call = _lifespan_service_call()
    given = {k.arg: ast.unparse(k.value) for k in call.keywords}
    assert given.get("audit") == "app.state.audit"
    assert given.get("scheme") == "handling_scheme"
    tree = ast.parse(APP.read_text())
    adapter_schemes = [
        ast.unparse(n)
        for n in ast.walk(tree)
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "handling_scheme" for t in n.targets)
    ]
    assert adapter_schemes, "the lifespan names no `handling_scheme` for the service to be given"
