"""Turns one `ExtractionResult` (`ModelPort.extract()`'s output, schema-shaped by
`profile.build_schema`) into `ExtractionCandidate`s — the review queue's own vocabulary
(`09_INGEST_STUDIO.md` §7: "extraction produces candidates, not graph"). Nothing here touches
`GraphPort` — that is `writer.py`'s job, once a human accepts one of these.

**A candidate with no locatable span is dropped here, not queued and flagged.**
`09_INGEST_STUDIO.md` §7: "A candidate with no locatable support is a defect in the extractor, not
a judgement call for the analyst" — so this module treats it as this pipeline's own defect to
absorb, not the review queue's problem to display. `01_DOMAIN_MODEL.md` §2.1's `SourceRef.locator`
is mandatory on every `Provenance`, so a spanless candidate could not become a graph element even
if queued; dropping it before the queue is honest about that rather than accepting it and failing
later at accept time.

**Locating happens against the raw extracted values, before any Knowledge Adapter runs** — found
directly, not assumed: a Knowledge Adapter's whole job is to transform a value away from its
literal source-text rendering (`msisdn` turns `"07911 123456"` into `"+447911123456"`), so
locating against the *post-adapter* properties would fail every value an adapter actually changed,
defeating the adapter-selection feature for exactly the values it exists to normalise.

**Below the per-type confidence floor, the same "discard, don't queue" rule applies**
(`09_INGEST_STUDIO.md` §4). Both this and the span rule happen before a `pending` candidate is
even created — a caller inspecting the review queue never sees either kind of drop; they were
never candidates.

**A configured Knowledge Adapter that fails to normalise a value discards the candidate too**,
following `09_INGEST_STUDIO.md` §5's structured-ingest rule applied to the same registry
(`services/ingest/transforms.py.apply_transform`, ADR-018's closed vocabulary): "rows are
rejected, never silently coerced" — an extracted phone number that does not actually parse as one
is not queued with its raw, unnormalised text standing in for the real thing.

**`confidence` is normalised to 0..1 here, defensively, not trusted from the model as-is** — found
live, not assumed: `profile.build_schema`'s own docstring has the full finding
(`qwen2.5:0.5b-instruct` reporting `97` for a value it was confident about, a 0–100 scale rather
than the 0..1 `01_DOMAIN_MODEL.md` §2.1 declares). A value greater than `1.0` is treated as a
percentage and divided by 100; the result is then clamped to `[0.0, 1.0]` as a hard floor against
whatever else a small model might emit. This is normalisation of the model's own self-reported
metadata, not a domain property — it does not go through the Knowledge Adapter registry, which
normalises extracted *values*, not the model's confidence in them.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel
from services.ingest.transforms import apply_transform

from conduit_common.identity import new_id
from knowledge_adapters.errors import NormalisationError
from schemas.domain import DocumentId, Handling, OntologySchema
from schemas.model import ExtractionResult

from .profile import ExtractionProfile, entity_type_def


class ExtractionCandidate(BaseModel):
    id: str
    document_id: DocumentId
    entity_type: str
    #: Adapter-normalised, confidence already extracted into its own field below.
    properties: dict[str, Any]
    confidence: float
    model: str
    #: `SourceRef.locator`'s own free-form shape (`01_DOMAIN_MODEL.md` §2.1) — a character-span
    #: locator into the source text this candidate was extracted from.
    locator: str
    excerpt_hash: str
    #: Fixed for the whole extraction run, the same "one `defaults.handling` for every row" shape
    #: a structured recipe already uses (`09_INGEST_STUDIO.md` §6) — `writer.write_candidate`
    #: carries this straight onto the accepted node, unchanged.
    handling: Handling


def _normalise_confidence(raw: float) -> float:
    value = raw / 100.0 if raw > 1.0 else raw
    return max(0.0, min(1.0, value))


def _flatten_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str)]
    return []


def _locate(properties: dict[str, Any], source_text: str) -> tuple[str, str] | None:
    """Tries every string-valued property, longest first (the most specific value is the least
    likely to false-positive against unrelated text), case-insensitively. Returns the locator and
    the *actual* matched substring (not the property's own casing) so `excerpt_hash` hashes what
    the source document really says, not what the model returned."""
    candidates = sorted(
        {s for v in properties.values() for s in _flatten_strings(v) if s},
        key=len,
        reverse=True,
    )
    lowered_text = source_text.lower()
    for value in candidates:
        start = lowered_text.find(value.lower())
        if start != -1:
            end = start + len(value)
            return f"char span {start}-{end}", source_text[start:end]
    return None


def _apply_adapters(
    entity_type: str, properties: dict[str, Any], profile: ExtractionProfile
) -> dict[str, Any] | None:
    adapter_map = profile.adapters.get(entity_type, {})
    if not adapter_map:
        return properties
    result = dict(properties)
    for property_name, adapter_name in adapter_map.items():
        if property_name not in result:
            continue
        try:
            result[property_name] = apply_transform(adapter_name, result[property_name])
        except NormalisationError:
            return None
    return result


def extract_candidates(
    result: ExtractionResult,
    profile: ExtractionProfile,
    ontology: OntologySchema,
    source_text: str,
    handling: Handling,
    *,
    candidate_ids: Sequence[str] | None = None,
) -> list[ExtractionCandidate]:
    """`candidate_ids` is a pre-generated sequence of ids for deterministic tests
    (`tests/extract/test_candidates.py`); a real caller omits it and gets fresh ULIDs
    (`conduit_common.identity.new_id`)."""
    id_iter = iter(candidate_ids) if candidate_ids is not None else None
    candidates: list[ExtractionCandidate] = []

    for entity_type in profile.entity_types:
        entity_type_def(ontology, entity_type)  # raises ExtractionProfileError if unknown
        items = result.data.get(entity_type, [])
        for item in items:
            item = dict(item)
            confidence = _normalise_confidence(float(item.pop("confidence")))
            if confidence < profile.confidence_floor_for(entity_type):
                continue

            # Locate against the *raw* extracted values, before any adapter runs — a Knowledge
            # Adapter's whole job is to transform a value away from its literal source-text
            # rendering (`msisdn` turns "07911 123456" into "+447911123456"), so locating against
            # the post-adapter properties would fail for exactly the values adapters exist for.
            located = _locate(item, source_text)
            if located is None:
                continue
            locator, matched_text = located

            normalised = _apply_adapters(entity_type, item, profile)
            if normalised is None:
                continue

            candidate_id = next(id_iter) if id_iter is not None else new_id()
            candidates.append(
                ExtractionCandidate(
                    id=candidate_id,
                    document_id=result.document_id,
                    entity_type=entity_type,
                    properties=normalised,
                    confidence=confidence,
                    model=result.model,
                    locator=locator,
                    excerpt_hash=hashlib.sha256(matched_text.encode()).hexdigest(),
                    handling=handling,
                )
            )

    return candidates
