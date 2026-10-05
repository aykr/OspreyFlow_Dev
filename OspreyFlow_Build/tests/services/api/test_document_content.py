"""ADR-094 step 2: a held Document's file, read and extracted from by kind. What a mistake would do,
and the case that catches it:

- a Document the caller cannot see would have its file served
  (`test_a_hidden_document_and_a_missing_one_refuse_alike`);
- an image's entities would be extracted from nothing, not from its description and visible text
  (`test_an_image_is_described_and_its_text_read_then_extracted_from`);
- a video's from nothing, not its transcript (`test_a_video_is_transcribed_then_extracted_from`);
- a finding would land in the graph as fact (`test_a_finding_is_inferred_until_accepted`)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from services.api.document_content import DocumentContentService
from services.api.review import DocumentNotFoundError
from services.api.working_set.service import WorkingSetService

from adapters.media_objectstore.testing import InMemoryMediaStore
from schemas.domain import AuditStub, Node, Provenance, ProvenanceState, SourceRef
from schemas.model import (
    ImageAnalysis,
    TranscribeRequest,
    Transcript,
    TranscriptSegment,
    VisionRequest,
)

from .test_email_extraction import (
    ANALYST,
    HANDLING,
    ONTOLOGY,
    FixedModel,
    InMemoryCandidates,
    WritingGraph,
)
from .working_set.fakes import FakeWorkingSetStore
from .working_set.test_visible_link import SCHEME, node

PNG = b"\x89PNG\r\n\x1a\n" + b"synthetic"
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"synthetic"


class MediaModel(FixedModel):
    def __init__(self) -> None:
        super().__init__(
            {"Person": [{"family_name": "WOLSKI", "given_names": "Tomasz", "confidence": 0.8}]}
        )
        self.vision: list[VisionRequest] = []
        self.transcriptions: list[TranscribeRequest] = []

    async def describe_image(self, req: VisionRequest) -> ImageAnalysis:
        self.vision.append(req)
        return ImageAnalysis(
            document_id=req.document_id,
            model=req.model,
            data={
                "description": "Tomasz WOLSKI beside a grey van at a dock gate.",
                "visible_text": "AB12 CDE",
            },
        )

    async def transcribe(self, req: TranscribeRequest) -> Transcript:
        self.transcriptions.append(req)
        return Transcript(
            document_id=req.document_id,
            model=req.model,
            language="en",
            segments=[
                TranscriptSegment(start=0, end=2, text="Tomasz is driving."),
                TranscriptSegment(start=2, end=4, text="Gate three."),
            ],
        )


def _document(doc_id: str, kind: str, ref: str, classification: str = "OFFICIAL") -> Node:
    return Node(
        id=doc_id,
        type="Document",
        properties={"title": doc_id, "media_kind": kind, "object_ref": ref},
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="export.csv", locator="row 1", excerpt_hash="")],
            first_seen=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        handling=HANDLING.model_copy(update={"classification": classification}),
        audit=AuditStub(created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="loader-1"),
    )


async def _service() -> tuple[
    DocumentContentService,
    InMemoryMediaStore,
    MediaModel,
    InMemoryCandidates,
    WritingGraph,
    FakeWorkingSetStore,
]:
    media = InMemoryMediaStore()
    image_ref = await media.put(PNG, "image/png")
    video_ref = await media.put(MP4, "video/mp4")
    text_ref = await media.put(b"Callum Price owes 4,500.", "text/plain")
    working = FakeWorkingSetStore()
    await working.add_nodes(
        "inv-1",
        [
            node("phone"),
            _document("image-1", "image", image_ref),
            _document("video-1", "video", video_ref),
            _document("text-1", "text", text_ref),
            _document("secret-1", "image", image_ref, "SECRET"),
        ],
    )
    graph = WritingGraph()
    model = MediaModel()
    candidates = InMemoryCandidates()
    service = DocumentContentService(
        WorkingSetService(graph, working, SCHEME),
        graph,
        media,
        model,  # type: ignore[arg-type]
        ONTOLOGY,
        candidates,  # type: ignore[arg-type]
        text_model="text-model",
        vision_model="vision-model",
        transcribe_model="speech-model",
    )
    return service, media, model, candidates, graph, working


async def test_a_documents_file_comes_back_with_its_type() -> None:
    service, _, _, _, _, _ = await _service()
    data, content_type = await service.file("inv-1", "image-1", ANALYST)
    assert (data, content_type) == (PNG, "image/png")


@pytest.mark.parametrize("document_id", ["secret-1", "no-such", "phone"])
async def test_a_hidden_document_and_a_missing_one_refuse_alike(document_id: str) -> None:
    service, _, model, _, _, _ = await _service()
    with pytest.raises(DocumentNotFoundError) as refused:
        await service.file("inv-1", document_id, ANALYST)
    assert str(refused.value) == str(DocumentNotFoundError(document_id))
    with pytest.raises(DocumentNotFoundError):
        await service.extract("inv-1", document_id, ANALYST)
    assert model.vision == [] and model.requests == []


async def test_an_image_is_described_and_its_text_read_then_extracted_from() -> None:
    service, _, model, candidates, graph, _ = await _service()
    result = await service.extract("inv-1", "image-1", ANALYST)
    (vision,) = model.vision
    assert vision.image == PNG and vision.model == "vision-model"
    (extraction,) = model.requests
    assert "beside a grey van at a dock gate." in extraction.text and "AB12 CDE" in extraction.text
    assert candidates.texts["image-1"][0] == extraction.text
    assert [c.status.value for c in result.candidates] == ["pending"]
    assert graph.nodes == {}  # nothing the model said is in the graph until a person accepts it


async def test_a_video_is_transcribed_then_extracted_from() -> None:
    service, _, model, _, _, _ = await _service()
    await service.extract("inv-1", "video-1", ANALYST)
    (transcription,) = model.transcriptions
    assert transcription.audio == MP4 and transcription.model == "speech-model"
    (extraction,) = model.requests
    assert extraction.text == "Tomasz is driving. Gate three."


async def test_a_text_document_is_extracted_from_its_kept_text() -> None:
    service, _, model, _, _, _ = await _service()
    await service.extract("inv-1", "text-1", ANALYST)
    (extraction,) = model.requests
    assert extraction.text == "Callum Price owes 4,500."
    assert extraction.model == "text-model"


async def test_a_finding_is_inferred_until_accepted() -> None:
    service, _, _, _, graph, working = await _service()
    result = await service.extract("inv-1", "image-1", ANALYST)
    accepted = await service.accept("inv-1", "image-1", result.candidates[0].id, ANALYST)
    written = graph.nodes[accepted.node_id]
    assert written.provenance.state == ProvenanceState.INFERRED
    (mention,) = [e for e in graph.committed_edges if e.source == accepted.node_id]
    assert (mention.type, mention.target) == ("MENTIONED_IN", "image-1")
    assert await working.get_node("inv-1", accepted.node_id) is not None
