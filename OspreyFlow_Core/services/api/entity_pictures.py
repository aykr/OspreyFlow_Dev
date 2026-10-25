"""One entity's own picture — `06_DECISIONS.md` ADR-105.

A picture of a person or a car is evidence about it, so it is held as content is (ADR-094): an
image `Document` in the graph, its file in the media store, and a `DEPICTS` link from it to the
entity, carrying the picture's own marking. The entity's picture is the newest `DEPICTS` link
that is not superseded, not `shown: false`, and comes from an image Document. Replacing a picture
supersedes that link with the new one; removing it supersedes it with a copy whose `shown` is
false. Nothing is deleted.

**Who may: whoever can see the entity in the case** (`visible_node`, one refusal for missing and
hidden). Every read of a picture goes through `GraphPort.expand`, so the adapter filters the link
and the Document by the reader's access (rule 3): a picture the reader may not see reads exactly
as no picture. Setting and removing need Editor, reading needs Viewer, checked by the routes.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from hashlib import sha256

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


class EntityPictureService:
    def __init__(
        self,
        working_set: WorkingSetService,
        graph: GraphPort,
        media: MediaStore,
        ontology: OntologySchema,
        *,
        scheme: HandlingScheme | None = None,
    ) -> None:
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

    async def set(
        self,
        investigation_id: str,
        node_id: str,
        principal: Principal,
        *,
        name: str,
        data: bytes,
        handling: Handling,
    ) -> PictureSetResult:
        """Keeps the file, writes its image Document and a `DEPICTS` link to the entity, and
        supersedes the picture the caller could see before. Every refusal comes before any
        write."""
        extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        content_type = PICTURE_TYPES.get(extension)
        if content_type is None:
            raise UploadRefusedError(f"{name!r} is not a picture (a png, jpeg, webp or gif)")
        if self._scheme is not None and not principal_may_view(handling, principal, self._scheme):
            raise UploadRefusedError(
                f"the marking {handling.classification} is one you could not read yourself"
            )
        entity = await self._entity(investigation_id, node_id, principal)
        depicts = self._ontology.edge_type(DEPICTS)
        if depicts is None or entity.type not in depicts.to_types:
            raise UploadRefusedError(f"a {entity.type} cannot have a picture of its own")
        before = (await self._current([node_id], principal)).get(node_id)

        ref = reference_for(data, content_type)
        document_id = f"content:{sha256(ref.encode()).hexdigest()[:32]}"
        edge_id = new_edge_id()
        await self._working_set.ensure_room(investigation_id, [document_id], [edge_id], principal)

        await self._media.put(data, content_type)
        now = datetime.now(UTC)
        provenance = Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[
                SourceRef(document_id=f"upload:{name}", locator="whole file", excerpt_hash="")
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
        tx = await self._graph.begin_transaction()
        try:
            await self._graph.upsert_nodes([document], tx)
            if before is None:
                await self._graph.upsert_edges([link], tx)
            else:
                await self._graph.supersede_edge(before[0].id, link, tx)
        except Exception:
            await self._graph.rollback_transaction(tx)
            raise
        await self._graph.commit_transaction(tx)

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
        return PictureSetResult(document_id=document_id, deltas=deltas)

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
