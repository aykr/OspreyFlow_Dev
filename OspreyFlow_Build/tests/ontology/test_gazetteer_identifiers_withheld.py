"""A gazetteer's identifiers are source-system identifiers (rule 7; the orchestrator's ruling of 9
November 2026, ADR-147 Amendment 1): `ontology.handling.withhold_sources`, the per-reader projection
every node read passes through (the adapter's serialisation and the working set's projection),
leaves them off a gazetteer's place for a request reader. The Conduit's own work keeps them, and so
does a read written back (`sources_in_full`), so a rebuild still finds a place by its `osm_id` and a
correction does not lose it. Through the real routes: `tests/ingest/test_gazetteer_ids_withheld_live.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ontology.handling import sources_in_full, withhold_sources
from schemas.domain import AuditStub, Node, Principal, Provenance, ProvenanceState, SourceRef
from schemas.mapconfig import GAZETTEER_ONLY_IDENTIFIERS, GAZETTEER_SOURCE_IDENTIFIERS

IDS = {"osm_id": "node/31337", "uprn": "100023336956", "os_place_id": "osgb4000000074564391",
       "gss_code": "E05000001", "gnis_feature_id": "1", "tiger_geoid": "2", "nad_address_id": "3"}  # fmt: skip
READER = Principal(
    id="a", clearance="OFFICIAL", org_unit="unit-1", datasets=["case-a", "gazetteer-osm-rutland"]
)


def _place(dataset: str, *, copied_from: str | None = None) -> Node:
    return Node(
        id="p1",
        type="Location",
        properties={"name": "Cranford", "geometry_ref": "g1", "postcode": "TW5 9QQ", **IDS},
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="osm", locator="1", excerpt_hash="a" * 64)],
            first_seen=datetime(2026, 1, 1, tzinfo=UTC),
            gazetteer=copied_from,
        ),
        handling={  # type: ignore[arg-type]
            "classification": "OFFICIAL",
            "handling_code": "P",
            "originator": "unit-1",
            "owning_unit": "unit-1",
        },
        audit=AuditStub(created_at=datetime(2026, 1, 1, tzinfo=UTC), created_by="loader"),
        datasets=[dataset],
    )


def test_every_gazetteer_identifier_is_named() -> None:
    assert set(GAZETTEER_SOURCE_IDENTIFIERS) == set(IDS)


def test_a_request_reader_is_sent_a_gazetteer_place_without_its_identifiers() -> None:
    sent = withhold_sources(_place("gazetteer-osm-rutland"), READER)
    assert sent.properties == {"name": "Cranford", "geometry_ref": "g1", "postcode": "TW5 9QQ"}


def test_the_conduits_own_work_and_a_read_written_back_keep_them() -> None:
    unlimited = READER.model_copy(update={"datasets": None})
    assert withhold_sources(_place("gazetteer-osm-rutland"), unlimited).properties["osm_id"]
    with sources_in_full():
        assert withhold_sources(_place("gazetteer-osm-rutland"), READER).properties["uprn"]


def test_a_case_s_own_location_keeps_its_uprn_and_loses_the_gazetteer_only_identifiers() -> None:
    """ADR-147 Amendment 3 (CARRIES row 23, the strict reading): a gazetteer loaded through the
    Studio arrives in the case's own dataset as a plain file, unmarked, so the six identifiers only
    a gazetteer carries are withheld from every node for every request reader, whatever dataset it
    is in. A `uprn` an analyst loaded into the case is the case's data and is kept (Amendment 1
    point 3a), and `postcode` is an address."""
    # A case that reads no gazetteer at all, and one that reads one beside its own dataset.
    for reader in (READER.model_copy(update={"datasets": ["case-a"]}), READER):
        sent = withhold_sources(_place("case-a"), reader)
        assert sent.properties == {
            "name": "Cranford", "geometry_ref": "g1", "postcode": "TW5 9QQ", "uprn": IDS["uprn"],
        }  # fmt: skip


def test_the_gazetteer_only_identifiers_are_the_seven_less_uprn() -> None:
    assert set(GAZETTEER_ONLY_IDENTIFIERS) == set(GAZETTEER_SOURCE_IDENTIFIERS) - {"uprn"}


def test_any_type_of_node_loses_them_and_the_conduit_keeps_them() -> None:
    """Not only a Location: a node of any type carrying one is sent without it."""
    person = _place("case-a").model_copy(
        update={"type": "Person", "properties": {"family_name": "Smith", "osm_id": "node/1"}}
    )
    assert withhold_sources(person, READER).properties == {"family_name": "Smith"}
    unlimited = READER.model_copy(update={"datasets": None})
    assert withhold_sources(_place("case-a"), unlimited).properties["os_place_id"]
    with sources_in_full():
        assert withhold_sources(_place("case-a"), READER).properties["osm_id"]


def test_a_case_s_copy_of_a_gazetteer_place_is_sent_without_its_identifiers() -> None:
    """ADR-147 Amendment 2 (the owner's ruling 6): a copy is in the case's own dataset, not a
    `gazetteer-*` one, so it is known by its provenance, which names the gazetteer."""
    sent = withhold_sources(_place("case-a", copied_from="gazetteer-osm-rutland"), READER)
    assert sent.properties == {"name": "Cranford", "geometry_ref": "g1", "postcode": "TW5 9QQ"}
    # Its provenance still says it is a copy, so the Glass and a later write know it.
    assert sent.provenance.gazetteer == "gazetteer-osm-rutland"


def test_a_copy_stays_one_through_a_case_s_own_later_write() -> None:
    """A case's own load that matches a copy and writes it again (its provenance has no gazetteer)
    must not make it a case location: the identifiers would be sent and matched again."""
    from schemas.merge import merge_provenance

    copy = _place("case-a", copied_from="gazetteer-osm-rutland").provenance
    later = Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id="case-load", locator="row 3", excerpt_hash="")],
        first_seen=datetime(2026, 2, 1, tzinfo=UTC),
    )
    assert merge_provenance(copy, later).gazetteer == "gazetteer-osm-rutland"
    assert merge_provenance(None, later).gazetteer is None
