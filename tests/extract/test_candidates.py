"""`services/extract/candidates.py` — `docs/09_INGEST_STUDIO.md` §4/§7. No `ModelPort` call here:
these tests build `ExtractionResult`s directly, the same "test the pure transform, not the model"
split `tests/resolve/test_resolver.py` uses for Splink.
"""

from __future__ import annotations

from services.extract.candidates import extract_candidates
from services.extract.profile import ExtractionProfile

from ontology.loader import load_default_ontology
from schemas.domain import Handling
from schemas.model import ExtractionResult

ONTOLOGY = load_default_ontology()
SOURCE_TEXT = (
    "Statement of: Dana MERCER. I received a call about Callum PRICE, who gave a number of "
    "07911 123456 as a contact."
)


def _handling() -> Handling:
    return Handling(classification="OFFICIAL", handling_code="P", originator="u", owning_unit="u")


def test_a_high_confidence_locatable_candidate_is_kept() -> None:
    profile = ExtractionProfile(["Person"])
    result = ExtractionResult(
        document_id="doc-1",
        model="qwen2.5:0.5b-instruct",
        data={"Person": [{"family_name": "MERCER", "given_names": "Dana", "confidence": 0.9}]},
    )

    candidates = extract_candidates(
        result, profile, ONTOLOGY, SOURCE_TEXT, _handling(), candidate_ids=["c1"]
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.id == "c1"
    assert candidate.entity_type == "Person"
    assert candidate.properties == {"family_name": "MERCER", "given_names": "Dana"}
    assert candidate.confidence == 0.9
    assert candidate.model == "qwen2.5:0.5b-instruct"
    assert candidate.handling == _handling()
    # "Dana" (4 chars) is shorter than "MERCER" (6) — the longer, more specific value wins, and
    # both happen to appear verbatim in `SOURCE_TEXT` so this also proves the tie isn't accidental.
    start, end = SOURCE_TEXT.index("MERCER"), SOURCE_TEXT.index("MERCER") + len("MERCER")
    assert candidate.locator == f"char span {start}-{end}"


def test_below_the_confidence_floor_is_discarded() -> None:
    profile = ExtractionProfile(["Person"], default_confidence_floor=0.8)
    result = ExtractionResult(
        document_id="doc-1",
        model="m",
        data={"Person": [{"family_name": "MERCER", "confidence": 0.5}]},
    )

    assert extract_candidates(result, profile, ONTOLOGY, SOURCE_TEXT, _handling()) == []


def test_a_percentage_scale_confidence_is_normalised_to_0_1() -> None:
    """Found live against the real CI-pinned model, not a hypothetical:
    `qwen2.5:0.5b-instruct` reported `97` for a confident extraction, a 0–100 scale rather than
    the 0..1 `01_DOMAIN_MODEL.md` §2.1 declares (`profile.py`'s own module docstring has the full
    finding)."""
    profile = ExtractionProfile(["Person"])
    result = ExtractionResult(
        document_id="doc-1",
        model="m",
        data={"Person": [{"family_name": "MERCER", "confidence": 97}]},
    )

    candidates = extract_candidates(result, profile, ONTOLOGY, SOURCE_TEXT, _handling())

    assert len(candidates) == 1
    assert candidates[0].confidence == 0.97


def test_a_confidence_above_100_is_clamped_to_1() -> None:
    profile = ExtractionProfile(["Person"], default_confidence_floor=0.0)
    result = ExtractionResult(
        document_id="doc-1",
        model="m",
        data={"Person": [{"family_name": "MERCER", "confidence": 150}]},
    )

    candidates = extract_candidates(result, profile, ONTOLOGY, SOURCE_TEXT, _handling())

    assert candidates[0].confidence == 1.0


def test_per_type_confidence_floor_overrides_the_default() -> None:
    profile = ExtractionProfile(
        ["Person", "Event"], default_confidence_floor=0.9, confidence_floors={"Person": 0.3}
    )
    result = ExtractionResult(
        document_id="doc-1",
        model="m",
        data={
            "Person": [{"family_name": "MERCER", "confidence": 0.5}],
            "Event": [{"confidence": 0.5}],
        },
    )

    candidates = extract_candidates(result, profile, ONTOLOGY, SOURCE_TEXT, _handling())

    assert len(candidates) == 1
    assert candidates[0].entity_type == "Person"


def test_a_candidate_with_no_locatable_span_is_dropped() -> None:
    profile = ExtractionProfile(["Person"])
    result = ExtractionResult(
        document_id="doc-1",
        model="m",
        data={"Person": [{"family_name": "NOBODY-IN-THE-TEXT", "confidence": 0.9}]},
    )

    assert extract_candidates(result, profile, ONTOLOGY, SOURCE_TEXT, _handling()) == []


def test_a_configured_adapter_normalises_the_property() -> None:
    profile = ExtractionProfile(["Endpoint"], adapters={"Endpoint": {"value_raw": "msisdn"}})
    result = ExtractionResult(
        document_id="doc-1",
        model="m",
        data={
            "Endpoint": [
                {
                    "value_raw": "07911 123456",
                    "value_normalised": "irrelevant",
                    "endpoint_kind": "msisdn",
                    "confidence": 0.9,
                }
            ]
        },
    )

    candidates = extract_candidates(result, profile, ONTOLOGY, SOURCE_TEXT, _handling())

    assert len(candidates) == 1
    assert candidates[0].properties["value_raw"] == "+447911123456"


def test_a_candidate_whose_configured_adapter_fails_is_discarded_not_coerced() -> None:
    """`09_INGEST_STUDIO.md` §5's structured-ingest rule ("rows are rejected, never silently
    coerced") applied to the same Knowledge Adapter registry — a value the adapter cannot
    normalise does not reach the queue with its raw text standing in for a real one."""
    profile = ExtractionProfile(["Endpoint"], adapters={"Endpoint": {"value_raw": "msisdn"}})
    result = ExtractionResult(
        document_id="doc-1",
        model="m",
        data={
            "Endpoint": [
                {
                    "value_raw": "not a phone number",
                    "value_normalised": "x",
                    "endpoint_kind": "msisdn",
                    "confidence": 0.9,
                }
            ]
        },
    )

    assert extract_candidates(result, profile, ONTOLOGY, SOURCE_TEXT, _handling()) == []


def test_an_unmentioned_entity_type_key_is_treated_as_empty() -> None:
    profile = ExtractionProfile(["Person", "Event"])
    result = ExtractionResult(document_id="doc-1", model="m", data={"Person": []})

    assert extract_candidates(result, profile, ONTOLOGY, SOURCE_TEXT, _handling()) == []


def test_excerpt_hash_is_sha256_of_the_actual_matched_source_text() -> None:
    import hashlib

    profile = ExtractionProfile(["Person"])
    result = ExtractionResult(
        document_id="doc-1",
        model="m",
        # Model renders the surname in a different case than the source text — the excerpt hash
        # must reflect what the *document* says, not what the model returned.
        data={"Person": [{"family_name": "mercer", "confidence": 0.9}]},
    )

    candidates = extract_candidates(result, profile, ONTOLOGY, SOURCE_TEXT, _handling())

    assert len(candidates) == 1
    assert candidates[0].excerpt_hash == hashlib.sha256(b"MERCER").hexdigest()
