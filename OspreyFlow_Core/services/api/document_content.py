"""A held Document's file, read and extracted from by kind — `06_DECISIONS.md` ADR-094 step 2.

A Document written from content an entity holds carries `media_kind` (text, image, video) and
`object_ref`, the file's name in the media store; the file itself is never in the graph. This
reads the file back for the reader, and extracts entities from it:

- **text**: from the kept text;
- **image**: the vision model describes it and reads the text in it, and entities are extracted
  from that description and text;
- **video**: its audio is transcribed and entities are extracted from the transcript; frames are
  not analysed, and face matching is out of scope (spec 09 §7).

The text extracted from is kept as the document's text (`run_extraction`), so the reader shows it
with the accepted entities marked. Every finding is inferred until a person accepts it (rule 5).

**Who may: whoever can see the Document in the case.** A Document above the caller, one not in the
case and a node that is not a Document all answer `DocumentNotFoundError`, and the store and the
model are asked nothing (rules 3 and 4). Reading needs Viewer; extracting and accepting need Editor,
checked by the routes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

from pydantic import BaseModel
from services.extract.profile import ExtractionProfile

from adapters.media_objectstore import content_type_of, reference_for
from conduit_common.identity import new_edge_id
from ontology.handling import HandlingScheme, principal_may_view
from ports.graph import GraphPort
from ports.media import MediaNotFoundError, MediaStore
from ports.model import ModelPort
from schemas.domain import (
    EdgeWrite,
    Handling,
    Node,
    NodeWrite,
    OntologySchema,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)
from schemas.model import TranscribeRequest, VisionRequest

from .email_extraction import MENTIONED_IN, _edge_from_write, _node_from_write
from .review import (
    DocumentNotFoundError,
    ExtractionCandidateRecord,
    ExtractionCandidateStore,
    accept_candidate,
    reject_candidate,
    run_extraction,
)
from .working_set.models import DeltaAdd
from .working_set.service import WorkingSetService

DOCUMENT_TYPE = "Document"
HOLDS = "HOLDS"

#: What the vision model is asked of an image, and the shape of its answer.
VISION_PROMPT = (
    "Describe this image for an investigator: the scene, the people, vehicles, places and objects "
    "in it. Then transcribe exactly any text that is visible in it (signs, number plates, screens, "
    "documents). Do not identify anyone by their face."
)
VISION_SCHEMA = {
    "type": "object",
    "properties": {"description": {"type": "string"}, "visible_text": {"type": "string"}},
    "required": ["description", "visible_text"],
}


class DocumentExtractionResult(BaseModel):
    document_id: str
    #: The text the entities were extracted from: kept text, an image's description and visible
    #: text, or a video's transcript.
    text: str
    candidates: list[ExtractionCandidateRecord]


class DocumentAcceptResult(BaseModel):
    node_id: str
    delta: DeltaAdd


class HolderNotFoundError(Exception):
    """The node named to hold an upload is not in the case, or not visible to the caller: one
    refusal for both (rules 3 and 4)."""


class UploadRefusedError(Exception):
    """An upload the rules refuse: a file of a kind the reader cannot show, a holder `HOLDS` does
    not allow, or a marking the uploader could not read themselves."""


class DocumentUploadResult(BaseModel):
    document_id: str
    delta: DeltaAdd


#: What an uploaded file may be, by its extension, and the content type it is kept under.
_UPLOAD_TYPES: dict[str, tuple[str, str]] = {
    "png": ("image", "image/png"),
    "jpg": ("image", "image/jpeg"),
    "jpeg": ("image", "image/jpeg"),
    "gif": ("image", "image/gif"),
    "webp": ("image", "image/webp"),
    "tif": ("image", "image/tiff"),
    "tiff": ("image", "image/tiff"),
    "heic": ("image", "image/heic"),
    "mp4": ("video", "video/mp4"),
    "mov": ("video", "video/quicktime"),
    "webm": ("video", "video/webm"),
    "txt": ("text", "text/plain"),
}


#: The extensions a content upload's name may carry, for the shared name check.
UPLOAD_CONTENT_EXTENSIONS = frozenset(f".{ext}" for ext in _UPLOAD_TYPES)


class DocumentContentService:
    def __init__(
        self,
        working_set: WorkingSetService,
        graph: GraphPort,
        media: MediaStore,
        model: ModelPort,
        ontology: OntologySchema,
        candidates: ExtractionCandidateStore,
        *,
        text_model: str,
        vision_model: str,
        transcribe_model: str,
        scheme: HandlingScheme | None = None,
    ) -> None:
        self._working_set = working_set
        self._graph = graph
        self._media = media
        self._model = model
        self._ontology = ontology
        self._candidates = candidates
        self._text_model = text_model
        self._vision_model = vision_model
        self._transcribe_model = transcribe_model
        self._scheme = scheme

    async def _held_document(
        self, investigation_id: str, document_id: str, principal: Principal
    ) -> tuple[Node, str]:
        node = await self._working_set.visible_node(investigation_id, document_id, principal)
        ref = node.properties.get("object_ref") if node is not None else None
        if node is None or node.type != DOCUMENT_TYPE or not isinstance(ref, str):
            raise DocumentNotFoundError(document_id)
        return node, ref

    async def file(
        self, investigation_id: str, document_id: str, principal: Principal
    ) -> tuple[bytes, str]:
        """The Document's file and its content type, for the reader."""
        _, ref = await self._held_document(investigation_id, document_id, principal)
        try:
            return await self._media.get(ref), content_type_of(ref)
        except MediaNotFoundError as error:
            raise DocumentNotFoundError(document_id) from error

    async def _text_of(self, node: Node, data: bytes) -> str:
        kind = node.properties.get("media_kind")
        if kind == "image":
            analysis = await self._model.describe_image(
                VisionRequest(
                    document_id=node.id,
                    image=data,
                    text=VISION_PROMPT,
                    json_schema=VISION_SCHEMA,
                    model=self._vision_model,
                )
            )
            description = str(analysis.data.get("description") or "").strip()
            visible = str(analysis.data.get("visible_text") or "").strip()
            return f"{description}\n\nText in the image: {visible}" if visible else description
        if kind == "video":
            transcript = await self._model.transcribe(
                TranscribeRequest(document_id=node.id, audio=data, model=self._transcribe_model)
            )
            return " ".join(segment.text.strip() for segment in transcript.segments).strip()
        return data.decode("utf-8", errors="replace")

    async def extract(
        self, investigation_id: str, document_id: str, principal: Principal
    ) -> DocumentExtractionResult:
        node, ref = await self._held_document(investigation_id, document_id, principal)
        try:
            data = await self._media.get(ref)
        except MediaNotFoundError as error:
            raise DocumentNotFoundError(document_id) from error
        text = await self._text_of(node, data)
        profile = ExtractionProfile(
            [t.name for t in self._ontology.entity_types if t.name != DOCUMENT_TYPE]
        )
        candidates = await run_extraction(
            self._model,
            self._ontology,
            self._candidates,
            document_id=node.id,
            text=text,
            profile=profile,
            handling=node.handling,
            principal=principal,
            extraction_model=self._text_model,
        )
        return DocumentExtractionResult(document_id=node.id, text=text, candidates=candidates)

    async def upload(
        self,
        investigation_id: str,
        principal: Principal,
        *,
        name: str,
        data: bytes,
        holder_id: str | None,
        handling: Handling,
    ) -> DocumentUploadResult:
        """A file added straight to a case (ADR-094 step 3, spec 09 §7): kept in the media store, a
        `Document` naming it, and, given a holder, a `HOLDS` link from it; all into the view, or
        nothing. Every refusal comes before any write."""
        extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if extension not in _UPLOAD_TYPES:
            raise UploadRefusedError(
                f"{name!r} is not a kind of file the reader can show (images, videos, .txt)"
            )
        media_kind, content_type = _UPLOAD_TYPES[extension]
        if self._scheme is not None and not principal_may_view(handling, principal, self._scheme):
            raise UploadRefusedError(
                f"the marking {handling.classification} is one you could not read yourself"
            )
        holder: Node | None = None
        if holder_id is not None:
            holder = await self._working_set.visible_node(investigation_id, holder_id, principal)
            if holder is None:
                raise HolderNotFoundError(holder_id)
            holds = self._ontology.edge_type(HOLDS)
            if holds is None or holder.type not in holds.from_types:
                raise UploadRefusedError(f"a {holder.type} cannot hold a file ({HOLDS})")

        ref = reference_for(data, content_type)
        document_id = f"content:{sha256(ref.encode()).hexdigest()[:32]}"
        edge_ids = [f"{document_id}:held-by:{holder.id}"] if holder else []
        await self._working_set.ensure_room(investigation_id, [document_id], edge_ids)

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
            properties={"title": name, "media_kind": media_kind, "object_ref": ref},
            provenance=provenance,
            handling=handling,
            created_by=principal.id,
            created_at=now,
        )
        edges = (
            [
                EdgeWrite(
                    id=edge_ids[0],
                    type=HOLDS,
                    source=holder.id,
                    target=document_id,
                    provenance=provenance,
                    handling=handling,
                    created_by=principal.id,
                    created_at=now,
                )
            ]
            if holder
            else []
        )
        tx = await self._graph.begin_transaction()
        try:
            await self._graph.upsert_nodes([document], tx)
            if edges:
                await self._graph.upsert_edges(edges, tx)
        except Exception:
            await self._graph.rollback_transaction(tx)
            raise
        await self._graph.commit_transaction(tx)
        delta = await self._working_set.add_written(
            investigation_id, [_node_from_write(document)], [_edge_from_write(e) for e in edges]
        )
        return DocumentUploadResult(document_id=document_id, delta=delta)

    async def reject(
        self, investigation_id: str, document_id: str, candidate_id: str, principal: Principal
    ) -> None:
        """One finding rejected (owner, 6 October 2026): marked so, and nothing written."""
        await self._held_document(investigation_id, document_id, principal)
        record = await self._candidates.get_authorized(candidate_id, principal)
        if record.document_id != document_id:
            raise DocumentNotFoundError(document_id)
        await reject_candidate(self._candidates, candidate_id, principal)

    async def accept(
        self, investigation_id: str, document_id: str, candidate_id: str, principal: Principal
    ) -> DocumentAcceptResult:
        """One finding accepted: an inferred node and its `MENTIONED_IN` link to the Document."""
        await self._held_document(investigation_id, document_id, principal)
        record = await self._candidates.get_authorized(candidate_id, principal)
        if record.document_id != document_id:
            raise DocumentNotFoundError(document_id)
        await self._working_set.ensure_room(
            investigation_id, [f"accepting:{candidate_id}"], [f"accepting:{candidate_id}:mention"]
        )
        node_id = await accept_candidate(self._candidates, self._graph, candidate_id, principal)
        now = datetime.now(UTC)
        mention = EdgeWrite(
            id=new_edge_id(),
            type=MENTIONED_IN,
            source=node_id,
            target=document_id,
            provenance=Provenance(
                state=ProvenanceState.INFERRED,
                sources=[
                    SourceRef(
                        document_id=document_id,
                        locator=record.locator,
                        excerpt_hash=record.excerpt_hash,
                    )
                ],
                extracted_by=f"model:{record.model}",
                extraction_confidence=record.confidence,
                first_seen=now,
            ),
            handling=record.handling,
            created_by=principal.id,
            created_at=now,
        )
        tx = await self._graph.begin_transaction()
        try:
            await self._graph.upsert_edges([mention], tx)
        except Exception:
            await self._graph.rollback_transaction(tx)
            raise
        await self._graph.commit_transaction(tx)
        node = await self._graph.get_node(node_id, principal)
        if node is None:
            raise DocumentNotFoundError(document_id)
        delta = await self._working_set.add_written(
            investigation_id, [node], [_edge_from_write(mention)]
        )
        return DocumentAcceptResult(node_id=node_id, delta=delta)
