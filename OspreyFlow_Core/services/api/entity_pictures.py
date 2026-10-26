"""One entity's own picture — `06_DECISIONS.md` ADR-105.

A picture of a person or a car is evidence about it, so it is held as content is (ADR-094): an
image `Document` in the graph, its file in the media store, and a `DEPICTS` link from it to the
entity, carrying the picture's own marking. The entity's picture is the newest `DEPICTS` link
that is not superseded, not `shown: false`, and comes from an image Document. Replacing a picture
supersedes that link with the new one; removing it supersedes it with a copy whose `shown` is
false. Nothing is deleted.

**Who may, on the route: whoever can see the entity in the case** (`visible_node`, one refusal for
missing and hidden). Every read of a picture goes through `GraphPort.expand`, so the adapter filters
the link and the Document by the reader's access (rule 3): a picture the reader may not see reads
exactly as no picture. Setting and removing need Editor, reading needs Viewer: those level and right
checks, the working-set lookup, the room check and the deltas are the routes' and `set`'s alone.

**What binds every path** (the shared core, ADR-127 Amendments 23 and 27): the service must hold a
handling scheme, so the refusal of a marking the caller could not read can never be skipped; the
`DEPICTS` target type is checked; and the `set_entity_picture` audit entry is written before the
graph commit. **The seed's path** (`attach_for_seed`) adds its own refusals: a worker scoped to a
case, a subject the adapter returns to that worker, no restricted, action or sanitisation code on
the subject, and a subject with no `DEPICTS` link at all, shown or removed, since the seed never
writes to a subject's picture history.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Protocol

from pydantic import BaseModel
from services.extract.writer import NodeNotFoundError

from adapters.media_objectstore import content_type_of, reference_for
from conduit_common.identity import new_edge_id
from ontology.handling import HandlingScheme, principal_may_view
from ports.graph import GraphPort
from ports.media import MediaNotFoundError, MediaStore
from schemas.domain import (
    AuditStub,
    Edge,
    EdgeWrite,
    ExpandRequest,
    Handling,
    Node,
    NodeWrite,
    OntologySchema,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

from .change_provenance import PICTURE_MARKER, without_link_ids
from .document_content import DOCUMENT_TYPE, UploadRefusedError
from .email_extraction import _node_from_write
from .link_ids import as_stored
from .working_set.models import DeltaAdd, DeltaReplaceEdge, DeltaReplaceEdgeSent
from .working_set.service import WorkingSetService

DEPICTS = "DEPICTS"

#: What a picture may be: a raster the Glass can draw (ADR-079's strict data-address check), never
#: an SVG, which can carry scripts and links.
PICTURE_TYPES: dict[str, str] = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
}


class PictureNotFoundError(Exception):
    """The entity has no picture the caller can see — the same answer whether it has none or has
    one above them."""


class PictureSetResult(BaseModel):
    """What `EntityPictureService.set` returns to its caller: the stored forms of the deltas, which
    carry the record of the link replaced and are what the route publishes. Not a response model;
    the route answers with `to_response()` (ADR-124 decision 4)."""

    document_id: str
    deltas: list[DeltaAdd | DeltaReplaceEdge]

    def to_response(self) -> PictureSetResponse:
        return PictureSetResponse(
            document_id=self.document_id,
            deltas=[d.to_sent() if isinstance(d, DeltaReplaceEdge) else d for d in self.deltas],
        )


class PictureSetResponse(BaseModel):
    """What the picture upload answers: the document and the steps, in their sent form."""

    document_id: str
    deltas: list[DeltaAdd | DeltaReplaceEdgeSent]


class EntityPicture(BaseModel):
    node_id: str
    document_id: str


def _edge_from(write: EdgeWrite, revision: int = 1) -> Edge:
    return Edge(
        id=write.id,
        type=write.type,
        source=write.source,
        target=write.target,
        properties=dict(write.properties),
        provenance=write.provenance,
        handling=write.handling,
        audit=AuditStub(
            created_at=write.created_at, created_by=write.created_by, revision=revision
        ),
    )


class PictureAudit(Protocol):
    """What the service needs of the audit writer (`audit.AuditWriter`)."""

    async def record(
        self,
        *,
        principal: Principal,
        action: str,
        resolved_query: dict[str, Any],
        result_cardinality: int,
        investigation_id: str | None = None,
        justification: str | None = None,
    ) -> None: ...


@dataclass(frozen=True)
class _Attached:
    """What the core wrote: the Document, the stored form of the link, and the picture it
    superseded, if any."""

    document: NodeWrite
    link: EdgeWrite
    before: tuple[Edge, Node] | None


class EntityPictureService:
    def __init__(
        self,
        working_set: WorkingSetService,
        graph: GraphPort,
        media: MediaStore,
        ontology: OntologySchema,
        *,
        scheme: HandlingScheme | None = None,
        audit: PictureAudit | None = None,
    ) -> None:
        self._audit = audit
        self._working_set = working_set
        self._graph = graph
        self._media = media
        self._ontology = ontology
        self._scheme = scheme

    async def _entity(self, investigation_id: str, node_id: str, principal: Principal) -> Node:
        node = await self._working_set.visible_node(investigation_id, node_id, principal)
        if node is None:
            raise NodeNotFoundError(node_id)
        return node

    async def _current(
        self, node_ids: Sequence[str], principal: Principal
    ) -> dict[str, tuple[Edge, Node]]:
        """Each entity's picture as `principal` may see it: its link and its Document."""
        if not node_ids:
            return {}
        found = await self._graph.expand(
            ExpandRequest(node_ids=list(node_ids), depth=1, edge_types=[DEPICTS], direction="in"),
            principal,
        )
        documents = {
            n.id: n
            for n in found.nodes
            if n.type == DOCUMENT_TYPE
            and n.properties.get("media_kind") == "image"
            and isinstance(n.properties.get("object_ref"), str)
        }
        wanted = set(node_ids)
        current: dict[str, tuple[Edge, Node]] = {}
        for edge in found.edges:
            if edge.type != DEPICTS or edge.target not in wanted:
                continue
            if edge.properties.get("shown") is False or edge.source not in documents:
                continue
            held = current.get(edge.target)
            if held is None or edge.audit.created_at > held[0].audit.created_at:
                current[edge.target] = (edge, documents[edge.source])
        return current

    async def _has_picture_history(self, node_id: str, principal: Principal) -> bool:
        """Whether the subject has any current `DEPICTS` link as `principal` sees it: shown, or a
        removal record (`shown: false`) that `_current` leaves out. A link the adapter filters from
        `principal`, or has superseded, is not seen."""
        found = await self._graph.expand(
            ExpandRequest(node_ids=[node_id], depth=1, edge_types=[DEPICTS], direction="in"),
            principal,
        )
        return any(e.type == DEPICTS and e.target == node_id for e in found.edges)

    async def pictures(
        self, investigation_id: str, node_ids: Sequence[str], principal: Principal
    ) -> list[EntityPicture]:
        """The picture of each entity in `node_ids` that is in the case and has one the caller can
        see. An id not in the case, or above the caller, is simply not answered."""
        visible = [
            node_id
            for node_id in dict.fromkeys(node_ids)
            if await self._working_set.visible_node(investigation_id, node_id, principal)
        ]
        current = await self._current(visible, principal)
        return [
            EntityPicture(node_id=node_id, document_id=document.id)
            for node_id, (_, document) in current.items()
        ]

    async def file(
        self, investigation_id: str, node_id: str, principal: Principal
    ) -> tuple[bytes, str]:
        """The entity's picture's file and its content type."""
        await self._entity(investigation_id, node_id, principal)
        current = (await self._current([node_id], principal)).get(node_id)
        if current is None:
            raise PictureNotFoundError(node_id)
        ref = str(current[1].properties["object_ref"])
        try:
            return await self._media.get(ref), content_type_of(ref)
        except MediaNotFoundError as error:
            raise PictureNotFoundError(node_id) from error

    async def _attach(
        self,
        investigation_id: str,
        entity_of: Callable[[], Awaitable[Node]],
        principal: Principal,
        *,
        name: str,
        data: bytes,
        handling: Handling,
        legal_basis: str | None,
        before_write: Callable[[str, str], Awaitable[None]] | None = None,
        skip_if_picture_history: bool = False,
        source_document: str | None = None,
    ) -> _Attached | None:
        """The one path every picture takes, whoever asks (ADR-127 Amendment 23): the refusals, the
        supersession of the subject's current picture as `_current` finds it, the content-addressed
        Document, the media file, the audit entry (before the graph commit: a row without a picture
        records an attempt, a picture without a row could stay unaudited for good) and the `DEPICTS`
        link. It refuses on either path when the service holds no handling scheme. It
        touches no working set. `entity_of` finds the subject (the route through its working set,
        the seed in the graph); `before_write` is told the new Document's and link's ids after every
        refusal and before any write. Returns None only when `skip_if_picture_history` is set and
        the subject already has a `DEPICTS` link of any kind."""
        if self._scheme is None:
            raise RuntimeError("a picture is attached only by a service holding a handling scheme")
        extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        content_type = PICTURE_TYPES.get(extension)
        if content_type is None:
            raise UploadRefusedError(f"{name!r} is not a picture (a png, jpeg, webp or gif)")
        if not principal_may_view(handling, principal, self._scheme):
            raise UploadRefusedError(
                f"the marking {handling.classification} is one you could not read yourself"
            )
        entity = await entity_of()
        depicts = self._ontology.edge_type(DEPICTS)
        if depicts is None or entity.type not in depicts.to_types:
            raise UploadRefusedError(f"a {entity.type} cannot have a picture of its own")
        if self._audit is not None and legal_basis is None:
            raise UploadRefusedError("a picture needs a legal basis")
        node_id = entity.id
        if skip_if_picture_history and await self._has_picture_history(node_id, principal):
            return None
        before = (await self._current([node_id], principal)).get(node_id)

        ref = reference_for(data, content_type)
        document_id = f"content:{sha256(ref.encode()).hexdigest()[:32]}"
        edge_id = new_edge_id()
        if before_write is not None:
            await before_write(document_id, edge_id)

        await self._media.put(data, content_type)
        now = datetime.now(UTC)
        provenance = Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[
                SourceRef(
                    document_id=source_document or f"upload:{name}",
                    locator="whole file",
                    excerpt_hash="",
                )
            ],
            first_seen=now,
        )
        document = NodeWrite(
            id=document_id,
            type=DOCUMENT_TYPE,
            properties={"title": name, "media_kind": "image", "object_ref": ref},
            provenance=provenance,
            handling=handling,
            created_by=principal.id,
            created_at=now,
        )
        # The picture's marking, not the entity's: a reader who may not see the picture does not
        # see the link either.
        link = EdgeWrite(
            id=edge_id,
            type=DEPICTS,
            source=document_id,
            target=node_id,
            properties={"shown": True},
            provenance=provenance,
            handling=handling,
            created_by=principal.id,
            created_at=now,
        )
        if self._audit is not None:
            await self._audit.record(
                principal=principal,
                action="set_entity_picture",
                investigation_id=investigation_id,
                resolved_query={
                    "node_id": node_id,
                    "document_id": document_id,
                    "name": name,
                    "size": len(data),
                    "classification": handling.classification,
                    "legal_basis": legal_basis,
                },
                result_cardinality=1,
            )
        tx = await self._graph.begin_transaction()
        try:
            await self._graph.upsert_nodes([document], tx)
            if before is None:
                (link,) = as_stored([link], await self._graph.upsert_edges([link], tx))
            else:
                replaced = await self._graph.supersede_edge(before[0].id, link, tx)
                (link,) = as_stored([link], [replaced])
        except Exception:
            await self._graph.rollback_transaction(tx)
            raise
        await self._graph.commit_transaction(tx)
        return _Attached(document=document, link=link, before=before)

    async def set(
        self,
        investigation_id: str,
        node_id: str,
        principal: Principal,
        *,
        name: str,
        data: bytes,
        handling: Handling,
        legal_basis: str | None = None,
    ) -> PictureSetResult:
        """The route's path: the shared core, with the working-set lookup, the room check, the
        working-set add and the deltas around it. Every refusal comes before any write. When the
        service holds an audit writer, `legal_basis` is required and the core audits."""

        async def room(document_id: str, edge_id: str) -> None:
            await self._working_set.ensure_room(
                investigation_id, [document_id], [edge_id], principal
            )

        attached = await self._attach(
            investigation_id,
            lambda: self._entity(investigation_id, node_id, principal),
            principal,
            name=name,
            data=data,
            handling=handling,
            legal_basis=legal_basis,
            before_write=room,
        )
        assert attached is not None  # only the seed path may skip
        document, link, before = attached.document, attached.link, attached.before
        deltas: list[DeltaAdd | DeltaReplaceEdge]
        if before is None:
            deltas = [
                await self._working_set.add_written(
                    investigation_id, [_node_from_write(document)], [_edge_from(link)], principal
                )
            ]
        else:
            new = _edge_from(link, before[0].audit.revision + 1)
            deltas = [
                await self._working_set.add_written(
                    investigation_id, [_node_from_write(document)], [], principal
                ),
                await self._working_set.replace_edge(investigation_id, before[0], new),
            ]
        return PictureSetResult(document_id=document.id, deltas=deltas)

    async def attach_for_seed(
        self,
        investigation_id: str,
        subject_id: str,
        principal: Principal,
        *,
        name: str,
        data: bytes,
        legal_basis: str,
    ) -> bool:
        """The seed's path (ADR-127 Amendments 23 and 27). `principal` is the seed worker, scoped to
        a case (`datasets` set); the subject is re-read through `get_node` as the worker, so the
        adapter's own filter decides whether it is in the case's dataset and readable. The picture
        takes the stored subject's classification and handling code and the worker's unit, as the
        route sets them. No working set is touched.

        Refuses (before any write): an unscoped worker, a subject the re-read does not return
        (`NodeNotFoundError`), and a subject whose stored node carries a restricted or unknown
        handling code, an action code or a sanitisation code, since a picture marked with the
        worker's unit could not carry them faithfully. Returns True if it attached, False if the
        subject already has a `DEPICTS` link of any kind (a shown picture, or a removal record, of
        any name): the seed never writes to a subject's picture history."""
        if self._audit is None:
            raise RuntimeError("a seeded picture is audited, so the service needs an audit writer")
        if self._scheme is None:
            raise RuntimeError("a picture is attached only by a service holding a handling scheme")
        if principal.datasets is None:
            raise UploadRefusedError("a seeded picture needs a worker scoped to a case")
        subject = await self._graph.get_node(subject_id, principal)
        if subject is None:
            raise NodeNotFoundError(subject_id)
        held = subject.handling
        code = self._scheme.handling_codes.get(held.handling_code)
        if code is None or code.dissemination == "restricted":
            raise UploadRefusedError(
                f"a {subject.type} with handling code {held.handling_code!r} cannot take a seeded "
                "picture"
            )
        if held.action_code is not None or held.sanitisation_code is not None:
            raise UploadRefusedError(
                f"a {subject.type} with an action or sanitisation code cannot take a seeded picture"
            )
        handling = Handling(
            classification=held.classification,
            handling_code=held.handling_code,
            originator=principal.org_unit,
            owning_unit=principal.org_unit,
        )

        async def found() -> Node:
            return subject

        attached = await self._attach(
            investigation_id,
            found,
            principal,
            name=name,
            data=data,
            handling=handling,
            legal_basis=legal_basis,
            skip_if_picture_history=True,
            source_document=f"seed:{principal.id}:{name}",
        )
        return attached is not None

    async def remove(
        self, investigation_id: str, node_id: str, principal: Principal
    ) -> DeltaReplaceEdge:
        """Supersedes the entity's picture with a copy whose `shown` is false; the Document and the
        old link stay, as evidence and in the link's history."""
        await self._entity(investigation_id, node_id, principal)
        current = (await self._current([node_id], principal)).get(node_id)
        if current is None:
            raise PictureNotFoundError(node_id)
        old, _ = current
        now = datetime.now(UTC)
        write = EdgeWrite(
            id=new_edge_id(),
            type=DEPICTS,
            source=old.source,
            target=old.target,
            properties={**old.properties, "shown": False},
            provenance=Provenance(
                state=ProvenanceState.ASSERTED,
                sources=[
                    *without_link_ids(old.provenance.sources),
                    SourceRef(document_id=PICTURE_MARKER, locator=principal.id, excerpt_hash=""),
                ],
                first_seen=old.provenance.first_seen,
            ),
            handling=old.handling,
            created_by=principal.id,
            created_at=now,
        )
        tx = await self._graph.begin_transaction()
        try:
            await self._graph.supersede_edge(old.id, write, tx)
        except Exception:
            await self._graph.rollback_transaction(tx)
            raise
        await self._graph.commit_transaction(tx)
        return await self._working_set.replace_edge(
            investigation_id, old, _edge_from(write, old.audit.revision + 1)
        )
