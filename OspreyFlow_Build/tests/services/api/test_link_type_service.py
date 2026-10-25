"""ADR-090 and Amendment 1: proposing, using, deciding. The service against an in-memory store that
refuses as the Postgres one does (`test_link_type_store.py` proves that half: an administrator reads
only their own unit's proposals). What a mistake would do, and the case that catches it, for each
test ADR-090 names:"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from services.api.investigations import Investigation
from services.api.link_changes import InvalidChangeError, LinkChangeRequest, LinkChangeService
from services.api.link_type_store import ProposalNotFoundError
from services.api.link_types import (
    LinkTypeProposal,
    LinkTypeService,
    ProposalRefusedError,
    ProposalStatus,
)
from services.api.working_set.service import WorkingSetService

from ontology.errors import OntologyError
from ontology.loader import load_default_ontology
from schemas.domain import Principal, Subgraph

from .test_link_events import _Cases
from .working_set.fakes import FakeGraphPort, FakeWorkingSetStore
from .working_set.test_visible_link import SCHEME, edge, node

EDITOR = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
ADMIN = Principal(id="admin-1", clearance="OFFICIAL", org_unit="unit-1", roles=["osprey-admin"])
OTHER_ADMIN = Principal(
    id="admin-9", clearance="OFFICIAL", org_unit="unit-9", roles=["osprey-admin"]
)


class MemoryStore:
    def __init__(self) -> None:
        self.rows: dict[str, LinkTypeProposal] = {}
        self.revision_value = 0

    async def create(self, p: LinkTypeProposal) -> None:
        self.rows[p.id] = p

    async def all(self) -> list[LinkTypeProposal]:
        return sorted(self.rows.values(), key=lambda p: (p.proposed_at, p.id))

    async def pending_for_cases(self, ids: list[str]) -> list[LinkTypeProposal]:
        return [
            p
            for p in await self.all()
            if p.investigation_id in ids and p.status is ProposalStatus.PENDING
        ]

    async def pending_for_datasets(self, ids: list[str]) -> list[LinkTypeProposal]:
        return [
            p
            for p in await self.all()
            if p.dataset_id in ids and p.status is ProposalStatus.PENDING
        ]

    async def pending_named(self, names: list[str]) -> list[LinkTypeProposal]:
        return [
            p for p in await self.all() if p.name in names and p.status is ProposalStatus.PENDING
        ]

    async def get(self, pid: str) -> LinkTypeProposal:
        if pid not in self.rows:
            raise ProposalNotFoundError(pid)
        return self.rows[pid]

    async def get_authorized(self, pid: str, principal: Principal) -> LinkTypeProposal:
        p = self.rows.get(pid)
        if p is None or p.owning_unit != principal.org_unit:
            raise ProposalNotFoundError(pid)
        return p

    async def list_authorized(self, principal: Principal) -> list[LinkTypeProposal]:
        return [p for p in await self.all() if p.owning_unit == principal.org_unit]

    async def decide(self, pid: str, **kw: Any) -> None:
        p = self.rows[pid]
        update = {
            "status": kw["status"],
            "decided_by": kw["by"],
            "decided_at": kw["at"],
            "decision_reason": kw["reason"],
        }
        for k in ("basis", "promoted_name", "direct_since"):
            if kw.get(k) is not None:
                update[k] = kw[k]
        self.rows[pid] = p.model_copy(update=update)

    async def bump_revision(self) -> int:
        self.revision_value += 1
        return self.revision_value

    async def revision(self) -> int:
        return self.revision_value


class Graph:
    def __init__(self) -> None:
        self.applied: list[Any] = []

    async def apply_schema(self, schema: Any) -> None:
        self.applied.append(schema)


def WorkingSet() -> WorkingSetService:  # noqa: N802 - the real service over the in-memory store
    return WorkingSetService(
        FakeGraphPort(Subgraph(nodes=[], edges=[])),
        FakeWorkingSetStore(),
        SCHEME,
    )


async def _link_in_view(
    working: WorkingSetService, case: str, classification: str = "OFFICIAL"
) -> None:
    store = working._store  # noqa: SLF001
    await store.add_nodes(case, [node("a"), node("b")])
    await store.add_edges(
        case, [edge("e1", "a", "b", classification).model_copy(update={"type": "KNOWN_TO"})]
    )


def _cases() -> _Cases:
    cases = _Cases({"inv-1", "branch-1"})
    for case in ("inv-2", "inv-3"):
        cases.cases[case] = Investigation(
            id=case,
            name="Another",
            created_at=datetime(2026, 1, 3, tzinfo=UTC),
            created_by="b",
            owning_unit="unit-1",
        )
        cases.visible.add(case)
    return cases


async def _service() -> tuple[LinkTypeService, MemoryStore, Graph, WorkingSetService, Any]:
    store, graph, working = MemoryStore(), Graph(), WorkingSet()
    ontology = load_default_ontology()
    service = LinkTypeService(store, ontology, graph, working, _cases())  # type: ignore[arg-type]
    await service.refresh()
    return service, store, graph, working, ontology


async def _propose(
    service: LinkTypeService, case: str = "inv-1", name: str = "KNOWN_TO", **over: Any
) -> LinkTypeProposal:
    fields: dict[str, Any] = {
        "name": name,
        "from_types": ["Person"],
        "to_types": ["Person"],
        "directed": False,
        "colour": "jade",
        "thickness": 2,
        "label": None,
        "reason": "They know each other by sight",
    }
    fields.update(over)
    return await service.propose(case, EDITOR, **fields)


def names(table: dict[str, Any]) -> set[str]:
    return set(table)


async def test_a_proposal_is_usable_at_once_in_its_case_and_its_branch_and_nowhere_else() -> None:
    service, _, graph, _, _ = await _service()
    p = await _propose(service)
    assert "KNOWN_TO" in names(await service.case_types("inv-1", EDITOR))
    assert "KNOWN_TO" in names(await service.case_types("branch-1", EDITOR))  # a branch inherits
    assert "KNOWN_TO" not in names(await service.case_types("inv-2", EDITOR))
    entry = (await service.case_types("inv-1", EDITOR))["KNOWN_TO"]
    assert entry.storage_name == p.storage_name and entry.definition.basis == "probabilistic"
    assert graph.applied[-1].edge_type(p.storage_name) is not None  # the store can take its links


async def test_a_proposal_is_offered_where_one_of_its_links_is_in_view() -> None:
    service, _, _, working, _ = await _service()
    await _propose(service)
    await _link_in_view(working, "inv-2")
    assert "KNOWN_TO" in names(await service.case_types("inv-2", EDITOR))


async def test_a_link_the_caller_cannot_see_does_not_offer_its_type() -> None:
    """Offering the type would say a link of it is in the case (rule 3)."""
    service, _, _, working, _ = await _service()
    await _propose(service)
    await _link_in_view(working, "inv-2", "SECRET")
    assert "KNOWN_TO" not in names(await service.case_types("inv-2", EDITOR))


@pytest.mark.parametrize("name", ["ASSOCIATE_OF", "SAME_AS", "NOT_SAME_AS", "lower_case", "X"])
async def test_a_name_in_the_ontology_or_not_a_type_name_is_refused(name: str) -> None:
    service, store, _, _, _ = await _service()
    with pytest.raises(ProposalRefusedError):
        await _propose(service, name=name)
    assert store.rows == {}


async def test_a_name_already_offered_in_the_case_is_refused() -> None:
    service, _, _, _, _ = await _service()
    await _propose(service)
    with pytest.raises(ProposalRefusedError):
        await _propose(service, case="branch-1")  # inherited from inv-1


async def test_a_promoted_name_is_refused_to_a_new_proposal() -> None:
    service, _, _, _, _ = await _service()
    p = await _propose(service)
    await service.promote(p.id, ADMIN, basis="probabilistic", reason="Useful")
    with pytest.raises(ProposalRefusedError):
        await _propose(service, case="inv-2")


async def test_promotion_raises_the_revision_by_one_and_leaves_the_version() -> None:
    service, _, _, _, ontology = await _service()
    version = ontology.version
    p = await _propose(service)
    await service.promote(p.id, ADMIN, basis="direct", reason="A loader backs it")
    assert ontology.overlay_revision == 1 and ontology.version == version
    promoted = ontology.edge_type("KNOWN_TO")
    assert promoted is not None and promoted.basis == "direct" and promoted.direct_since is not None
    assert "KNOWN_TO" in names(await service.case_types("inv-2", EDITOR))  # in every case now


async def test_an_administrator_cannot_act_on_another_units_proposal() -> None:
    service, store, _, _, _ = await _service()
    p = await _propose(service)
    for act in (
        service.promote(p.id, OTHER_ADMIN, basis="probabilistic", reason="x"),
        service.reject(p.id, OTHER_ADMIN, reason="x"),
    ):
        with pytest.raises(ProposalNotFoundError):
            await act
    assert store.rows[p.id].status is ProposalStatus.PENDING


async def test_a_same_name_proposal_that_fits_is_merged_and_one_that_does_not_is_renamed() -> None:
    service, store, _, _, ontology = await _service()
    first = await _propose(service)
    fits = await _propose(service, case="inv-2")
    misfit = await _propose(service, case="inv-3", to_types=["Organisation"])
    await service.promote(first.id, ADMIN, basis="probabilistic", reason="Seen often")
    assert store.rows[fits.id].status is ProposalStatus.MERGED
    assert store.rows[misfit.id].status is ProposalStatus.PENDING
    with pytest.raises(ProposalRefusedError):  # its links do not fit KNOWN_TO
        await service.promote(misfit.id, ADMIN, basis="probabilistic", reason="x")
    await service.promote(
        misfit.id, ADMIN, basis="probabilistic", reason="Its own type", rename_to="KNOWS_STAFF_AT"
    )
    assert ontology.storage_aliases[misfit.storage_name] == "KNOWS_STAFF_AT"
    assert ontology.storage_aliases[fits.storage_name] == "KNOWN_TO"


async def test_a_rejected_or_withdrawn_proposal_is_no_longer_offered_and_its_links_still_read() -> (
    None
):
    service, _, _, _, ontology = await _service()
    rejected = await _propose(service)
    withdrawn = await _propose(service, name="SEEN_WITH")
    await service.reject(rejected.id, ADMIN, reason="Use ASSOCIATE_OF")
    await service.withdraw("inv-1", withdrawn.id, EDITOR, reason="Mistake", is_author=False)
    offered = names(await service.case_types("inv-1", EDITOR))
    assert "KNOWN_TO" not in offered and "SEEN_WITH" not in offered
    assert ontology.storage_aliases[rejected.storage_name] == "KNOWN_TO"


async def test_only_the_proposer_or_an_author_withdraws() -> None:
    service, _, _, _, _ = await _service()
    p = await _propose(service)
    someone_else = Principal(id="analyst-2", clearance="OFFICIAL", org_unit="unit-1")
    with pytest.raises(ProposalRefusedError):
        await service.withdraw("inv-1", p.id, someone_else, reason="x", is_author=False)
    await service.withdraw("inv-1", p.id, someone_else, reason="Not needed", is_author=True)
    with pytest.raises(ProposalNotFoundError):  # from another case it is not there
        await service.withdraw("inv-2", p.id, EDITOR, reason="x", is_author=True)


async def test_retiring_a_promoted_type_keeps_its_links_and_offers_it_no_more() -> None:
    service, _, _, _, ontology = await _service()
    p = await _propose(service)
    await service.promote(p.id, ADMIN, basis="probabilistic", reason="Useful")
    await service.retire("KNOWN_TO", ADMIN, reason="Superseded")
    assert ontology.overlay_revision == 2
    assert ontology.edge_type("KNOWN_TO") is None
    assert ontology.storage_aliases[p.storage_name] == "KNOWN_TO"
    with pytest.raises(ProposalNotFoundError):
        await service.retire("ASSOCIATE_OF", ADMIN, reason="Not an analyst's type")


async def test_the_overlay_survives_a_restart() -> None:
    service, store, _, _, _ = await _service()
    p = await _propose(service)
    await service.promote(p.id, ADMIN, basis="probabilistic", reason="Useful")
    fresh = load_default_ontology()
    restarted = LinkTypeService(store, fresh, Graph(), WorkingSet(), _cases())  # type: ignore[arg-type]
    await restarted.refresh()
    assert fresh.edge_type("KNOWN_TO") is not None and fresh.overlay_revision == 1


# --- The change form uses them (ADR-090 decision 3, Amendment 1's labels) ---------------------


class _Supersede:
    """Refuses a write of a type the ontology in force does not declare, as ArcadeDB does: a write
    under a pending proposal's bare name, rather than its own label, is refused here as there."""

    def __init__(self, ontology: Any) -> None:
        self.ontology = ontology
        self.written: list[Any] = []

    async def begin_transaction(self) -> str:
        return "tx"

    async def supersede_edge(self, edge_id: str, write: Any, tx: str) -> str:
        found = self.ontology.edge_type(write.type)
        if found is None:
            raise OntologyError(f"{write.type!r} is not a type in the active ontology")
        self.written.append(write)
        return write.id

    async def commit_transaction(self, tx: str) -> None:
        return None

    async def rollback_transaction(self, tx: str) -> None:
        return None


class _NoNotes:
    async def rekey(self, *_: str) -> int:
        return 0


async def _changes() -> tuple[LinkChangeService, LinkTypeService, _Supersede, WorkingSetService]:
    service, _, _, working, ontology = await _service()
    for case in ("inv-1", "inv-2"):
        await working._store.add_nodes(case, [node("a"), node("b")])  # noqa: SLF001
        await working._store.add_edges(  # noqa: SLF001
            case, [edge("e1", "a", "b").model_copy(update={"type": "ASSOCIATE_OF"})]
        )
    graph = _Supersede(ontology)
    changes = LinkChangeService(
        _Rows(),
        working,
        graph,
        ontology,
        _NoNotes(),
        service,  # type: ignore[arg-type]
    )
    return changes, service, graph, working


class _Rows:
    async def add(self, change: Any) -> None:
        return None

    async def produced(self, *_: str) -> None:
        return None


async def test_a_link_changed_to_a_pending_type_is_written_under_the_proposals_own_label() -> None:
    changes, service, graph, _ = await _changes()
    p = await _propose(service)
    result = await changes.change(
        "inv-1", "e1", EDITOR, LinkChangeRequest(type="KNOWN_TO", reason="Only by sight")
    )
    assert graph.written[0].type == p.storage_name
    assert result.edge.type == "KNOWN_TO"  # read as its name, as the adapter reads it back
    assert result.change.after["basis"] == "probabilistic"


async def test_a_pending_type_of_another_case_is_refused_in_this_one() -> None:
    changes, service, graph, _ = await _changes()
    await _propose(service)
    with pytest.raises(InvalidChangeError):
        await changes.change(
            "inv-2", "e1", EDITOR, LinkChangeRequest(type="KNOWN_TO", reason="Only by sight")
        )
    assert graph.written == []


async def test_a_link_of_a_rejected_type_can_still_be_corrected_without_retyping() -> None:
    changes, service, _, working = await _changes()
    p = await _propose(service)
    first = await changes.change(
        "inv-1", "e1", EDITOR, LinkChangeRequest(type="KNOWN_TO", reason="Only by sight")
    )
    await service.reject(p.id, ADMIN, reason="Use ASSOCIATE_OF")
    again = await changes.change(
        "inv-1", first.edge.id, EDITOR, LinkChangeRequest(occurrences=2, reason="Seen twice")
    )
    assert again.edge.type == "KNOWN_TO" and again.edge.occurrences == 2


# --- ADR-099 Amendment 3: a proposal belongs to its dataset --------------------------------------
#
# A type an analyst defines is usable in every case reading the dataset of the case it was defined
# in, and in no other, until an administrator promotes it. `inv-2` and `inv-3` stand for two other
# cases: one reading the same dataset, one reading another. A principal scoped to a case carries
# its datasets (`app.get_principal`), which is all the service reads them from.


def _in(*datasets: str) -> Principal:
    return EDITOR.model_copy(update={"datasets": list(datasets)})


async def test_a_proposal_is_offered_in_every_case_reading_its_dataset_and_no_other() -> None:
    service, _, _, _, _ = await _service()
    p = await service.propose(
        "inv-1",
        _in("fixture-corp"),
        name="KNOWN_TO",
        from_types=["Person"],
        to_types=["Person"],
        directed=False,
        colour="jade",
        thickness=2,
        label=None,
        reason="They know each other by sight",
    )
    assert p.dataset_id == "fixture-corp"
    assert "KNOWN_TO" in names(await service.case_types("inv-2", _in("fixture-corp")))
    assert "KNOWN_TO" in names(await service.case_types("inv-3", _in("enron", "fixture-corp")))
    assert "KNOWN_TO" not in names(await service.case_types("inv-3", _in("enron")))
    # Its own branch reads the same datasets, so it has it; not because it is a branch.
    assert "KNOWN_TO" not in names(await service.case_types("branch-1", _in("enron")))


async def test_a_proposal_of_another_dataset_is_not_offered_where_its_link_is_in_view() -> None:
    """The in-view rule of ADR-090 belonged to case scope; a link in view is the case's dataset's,
    so a proposal of another dataset is not offered by it."""
    service, _, _, working, _ = await _service()
    await service.propose(
        "inv-1",
        _in("fixture-corp"),
        name="KNOWN_TO",
        from_types=["Person"],
        to_types=["Person"],
        directed=False,
        colour="jade",
        thickness=2,
        label=None,
        reason="x",
    )
    store = working._store  # noqa: SLF001
    in_enron = {"datasets": ["enron"]}
    await store.add_nodes(
        "inv-2", [node("a").model_copy(update=in_enron), node("b").model_copy(update=in_enron)]
    )
    await store.add_edges(
        "inv-2",
        [edge("e1", "a", "b").model_copy(update={"type": "KNOWN_TO", **in_enron})],
    )
    # The link is in view to the case: the rule under test, not the projection, decides.
    _, in_view = await working.visible_membership("inv-2", _in("enron"))
    assert [e.id for e in in_view] == ["e1"]
    assert "KNOWN_TO" not in names(await service.case_types("inv-2", _in("enron")))


async def test_the_proposer_withdraws_from_any_case_reading_its_dataset() -> None:
    service, _, _, _, _ = await _service()
    p = await service.propose(
        "inv-1",
        _in("fixture-corp"),
        name="KNOWN_TO",
        from_types=["Person"],
        to_types=["Person"],
        directed=False,
        colour="jade",
        thickness=2,
        label=None,
        reason="x",
    )
    with pytest.raises(ProposalNotFoundError):
        await service.withdraw("inv-3", p.id, _in("enron"), reason="no", is_author=False)
    withdrawn = await service.withdraw(
        "inv-2", p.id, _in("fixture-corp"), reason="not needed", is_author=False
    )
    assert withdrawn.status is ProposalStatus.WITHDRAWN

