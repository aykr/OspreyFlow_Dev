"""ADR-090: the ontology in force is `default.yaml` plus what analysts proposed and administrators
decided. Composed by one pure function, so every rule of it is checked here. What a mistake would
do, and the case that catches it:

- a pending proposal offered in every case as if promoted
  (`test_a_pending_proposal_is_storage_only`);
- a type promoted as Direct turning its earlier links solid
  (`test_promoted_as_direct_is_direct_only_from_then`);
- a renamed proposal's links reading under a name the ontology no longer has
  (`test_a_renamed_proposal_answers_to_its_new_name`);
- a promotion moving the ontology version and so flagging every recipe
  (`test_the_version_never_moves_and_the_revision_is_carried`)."""

from __future__ import annotations

from datetime import UTC, datetime

from services.api.link_types import LinkTypeProposal, ProposalStatus, compose_ontology

from ontology.loader import load_default_ontology

BASE = load_default_ontology()
T0 = datetime(2026, 10, 5, 9, tzinfo=UTC)


def proposal(pid: str, name: str = "KNOWN_TO", **over: object) -> LinkTypeProposal:
    fields: dict[str, object] = {
        "id": pid,
        "name": name,
        "from_types": ["Person"],
        "to_types": ["Person"],
        "directed": False,
        "investigation_id": "inv-1",
        "owning_unit": "unit-1",
        "proposed_by": "analyst-1",
        "proposed_at": T0,
        "reason": "Neighbours who know each other by sight",
        "status": ProposalStatus.PENDING,
        "colour": "jade",
        "thickness": 2,
    }
    fields.update(over)
    return LinkTypeProposal.model_validate(fields)


def visible(ontology) -> set[str]:  # type: ignore[no-untyped-def]
    return {t.name for t in ontology.edge_types if not t.hidden}


def test_a_pending_proposal_is_storage_only() -> None:
    p = proposal("P1")
    composed = compose_ontology(BASE, [p], revision=0)
    storage = composed.edge_type(p.storage_name)
    assert storage is not None and storage.hidden and storage.basis == "probabilistic"
    assert (storage.from_types, storage.to_types) == (["Person"], ["Person"])
    assert composed.storage_aliases == {p.storage_name: "KNOWN_TO"}
    assert "KNOWN_TO" not in visible(composed)


def test_promoted_as_direct_is_direct_only_from_then() -> None:
    p = proposal(
        "P1",
        status=ProposalStatus.PROMOTED,
        basis="direct",
        promoted_name="KNOWN_TO",
        direct_since=T0,
    )
    composed = compose_ontology(BASE, [p], revision=1)
    promoted = composed.edge_type("KNOWN_TO")
    assert promoted is not None and not promoted.hidden
    assert (promoted.basis, promoted.direct_since, promoted.analyst_defined) == ("direct", T0, True)
    assert (promoted.colour, promoted.thickness) == ("jade", 2)
    assert composed.storage_aliases[p.storage_name] == "KNOWN_TO"


def test_a_renamed_proposal_answers_to_its_new_name() -> None:
    first = proposal(
        "P1", status=ProposalStatus.PROMOTED, basis="probabilistic", promoted_name="KNOWN_TO"
    )
    renamed = proposal(
        "P2",
        from_types=["Person"],
        to_types=["Organisation"],
        status=ProposalStatus.PROMOTED,
        basis="probabilistic",
        promoted_name="WORKS_NEAR",
    )
    composed = compose_ontology(BASE, [first, renamed], revision=2)
    assert {"KNOWN_TO", "WORKS_NEAR"} <= visible(composed)
    assert composed.storage_aliases[renamed.storage_name] == "WORKS_NEAR"
    assert composed.edge_type("WORKS_NEAR").to_types == ["Organisation"]  # type: ignore[union-attr]


def test_a_merged_proposal_answers_to_the_promoted_name() -> None:
    first = proposal(
        "P1", status=ProposalStatus.PROMOTED, basis="probabilistic", promoted_name="KNOWN_TO"
    )
    merged = proposal("P3", status=ProposalStatus.MERGED, promoted_name="KNOWN_TO")
    composed = compose_ontology(BASE, [first, merged], revision=1)
    assert composed.storage_aliases[merged.storage_name] == "KNOWN_TO"
    assert [t.name for t in composed.edge_types].count("KNOWN_TO") == 1


def test_rejected_withdrawn_and_retired_types_are_not_offered_but_their_links_still_read() -> None:
    rejected = proposal("P1", status=ProposalStatus.REJECTED)
    withdrawn = proposal("P2", name="SEEN_WITH", status=ProposalStatus.WITHDRAWN)
    retired = proposal(
        "P3",
        name="WORKED_WITH",
        status=ProposalStatus.RETIRED,
        promoted_name="WORKED_WITH",
        basis="direct",
    )
    composed = compose_ontology(BASE, [rejected, withdrawn, retired], revision=3)
    assert not {"KNOWN_TO", "SEEN_WITH", "WORKED_WITH"} & visible(composed)
    assert composed.storage_aliases == {
        rejected.storage_name: "KNOWN_TO",
        withdrawn.storage_name: "SEEN_WITH",
        retired.storage_name: "WORKED_WITH",
    }


def test_the_version_never_moves_and_the_revision_is_carried() -> None:
    p = proposal(
        "P1", status=ProposalStatus.PROMOTED, basis="probabilistic", promoted_name="KNOWN_TO"
    )
    composed = compose_ontology(BASE, [p], revision=4)
    assert composed.version == BASE.version
    assert composed.overlay_revision == 4
    authored = {t.name for t in BASE.edge_types}
    assert authored <= visible(composed)
