"""Analyst-proposed relationship types, and the ontology they make — `06_DECISIONS.md` ADR-090 and
its Amendment 1 (step C of ADR-081).

An Editor proposes a type from the change form when none fits. It is usable at once in that case
(and its branches, and any case where one of its links is in view), is probabilistic, and is kept
here, never in `default.yaml`. An `osprey-admin` holder of the proposing unit promotes it (choosing
its basis), rejects it, or later retires it; the proposer or an Author of the case may withdraw it.

**Nothing is ever rewritten.** Each proposal's links are stored under a label of its own,
`<name>__<proposal id>` (its `storage_name`), declared as a hidden type so the graph store accepts
the writes, and that label is an alias (`OntologySchema.storage_aliases`) of the name the links read
as: the proposal's own name while it is pending, and after it is rejected, withdrawn or retired; the
promoted name once it is promoted, merged into a type of its name, or renamed at promotion. So
renaming, merging and retiring change one mapping, and every link answers to it, restricted ones
included. A type promoted as Direct is Direct only from `direct_since`; links written before stay
probabilistic (ADR-081 decision 2).

`compose_ontology` is the one function that builds the ontology in force from `default.yaml` and
every proposal; `test_link_type_overlay.py` checks each rule of it.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Literal, Protocol

from pydantic import BaseModel, Field, ValidationError

from adapters.graph_arcadedb.naming import STORAGE_SEPARATOR
from conduit_common.identity import new_id
from schemas.domain import EdgeTypeDef, OntologySchema, Principal

from .event_scope import visible_ancestors
from .investigations import InvestigationStore

if TYPE_CHECKING:
    from .link_type_store import LinkTypeProposalStore
    from .working_set.service import WorkingSetService


class ProposalStatus(StrEnum):
    PENDING = "pending"
    PROMOTED = "promoted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    #: A same-name proposal whose links all fit a promoted type, recorded as merged into it.
    MERGED = "merged"
    #: Promoted, then retired by an administrator: no longer offered; its links stay.
    RETIRED = "retired"


class LinkTypeProposal(BaseModel):
    id: str
    name: str
    label: str | None = None
    from_types: list[str]
    to_types: list[str]
    directed: bool = True
    colour: str | None = None
    thickness: int | None = Field(default=None, ge=1, le=5)
    investigation_id: str
    owning_unit: str
    proposed_by: str
    proposed_at: datetime
    reason: str
    status: ProposalStatus = ProposalStatus.PENDING
    decided_by: str | None = None
    decided_at: datetime | None = None
    decision_reason: str | None = None
    #: Chosen by the administrator at promotion.
    basis: Literal["direct", "probabilistic"] | None = None
    #: The name it was promoted, merged or renamed under.
    promoted_name: str | None = None
    direct_since: datetime | None = None
    #: ADR-099 Amendment 3: the dataset it belongs to, the first of its case's at proposal; usable
    #: in every case reading it. `None` for one made before, which keeps ADR-090's case rule.
    dataset_id: str | None = None

    @property
    def storage_name(self) -> str:
        """The label this proposal's links are stored under, its own, never shared."""
        return f"{self.name}{STORAGE_SEPARATOR}{self.id}"

    @property
    def reads_as(self) -> str:
        """The name this proposal's links answer to now."""
        if self.status in (ProposalStatus.PROMOTED, ProposalStatus.MERGED, ProposalStatus.RETIRED):
            return self.promoted_name or self.name
        return self.name

    def definition(self, name: str | None = None) -> EdgeTypeDef:
        """The type this proposal declares, under `name` (its own by default), probabilistic."""
        return EdgeTypeDef.model_validate(
            {
                "name": name or self.name,
                "from": list(self.from_types),
                "to": list(self.to_types),
                "directed": self.directed,
                "basis": "probabilistic",
                "colour": self.colour,
                "thickness": self.thickness,
                "label": self.label,
                "analyst_defined": True,
            }
        )


def compose_ontology(
    base: OntologySchema, proposals: Sequence[LinkTypeProposal], *, revision: int
) -> OntologySchema:
    """`default.yaml` plus every proposal: each proposal's hidden storage type and its alias, and
    a visible type for each name promoted and not retired. The version is the base's (ADR-090
    decision 2); `revision` is the overlay's own."""
    authored = [t for t in base.edge_types if not t.analyst_defined and not t.hidden]
    taken = {t.name for t in authored}
    promoted: dict[str, EdgeTypeDef] = {}
    storage: list[EdgeTypeDef] = []
    aliases: dict[str, str] = {}
    for proposal in sorted(proposals, key=lambda p: (p.proposed_at, p.id)):
        stored = proposal.definition(proposal.storage_name).model_copy(update={"hidden": True})
        storage.append(stored)
        aliases[proposal.storage_name] = proposal.reads_as
        if proposal.status is ProposalStatus.PROMOTED:
            name = proposal.reads_as
            if name in taken or name in promoted:
                continue  # a second promotion under one name is a merge, not a second type
            promoted[name] = proposal.definition(name).model_copy(
                update={
                    "basis": proposal.basis or "probabilistic",
                    "direct_since": proposal.direct_since if proposal.basis == "direct" else None,
                }
            )
    return base.model_copy(
        update={
            "edge_types": [*authored, *promoted.values(), *storage],
            "storage_aliases": aliases,
            "overlay_revision": revision,
        }
    )


#: A relationship type's name: capitals, digits and single underscores, as `default.yaml`'s are.
_NAME = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*$")
MAX_NAME_CHARS = 48
MAX_REASON_CHARS = 2000


class ProposalNotFoundError(Exception):
    """No such proposal, or one of another unit: one refusal for both (ADR-090 decision 9)."""


class ProposalRefusedError(Exception):
    """A proposal or a decision the rules refuse, said in words the analyst can act on."""


class CaseType(BaseModel):
    """A relationship type a link in a case may take, and the label its links are written under:
    its own name for a type in the ontology, the proposal's own label for a pending one."""

    definition: EdgeTypeDef
    storage_name: str
    #: Set for a pending proposal: who may act on it, and that it is not yet in the ontology.
    proposal_id: str | None = None


class _Schema(Protocol):
    async def apply_schema(self, schema: OntologySchema) -> object: ...


def _fits(proposal: LinkTypeProposal, definition: EdgeTypeDef) -> bool:
    """Every link a proposal could hold is a valid link of `definition`."""
    wild = "*" in definition.from_types
    return (
        proposal.directed == definition.directed
        and (wild or set(proposal.from_types) <= set(definition.from_types))
        and ("*" in definition.to_types or set(proposal.to_types) <= set(definition.to_types))
    )


class LinkTypeService:
    """Proposals, the types a case may use, and the administrator's decisions (ADR-090).

    `ontology` is the one shared `OntologySchema` every service holds; `refresh` rewrites it in
    place to `compose_ontology` of the authored types and every proposal, and applies it to the
    graph store, so the store accepts a proposal's label and reads it under its name. Routes check
    the case access level (Editor to propose, Author or the proposer to withdraw) and `osprey-admin`
    for decisions; a decision reads the proposal through `get_authorized`, so another unit's is not
    found."""

    def __init__(
        self,
        store: LinkTypeProposalStore,
        ontology: OntologySchema,
        graph: _Schema,
        working_set: WorkingSetService,
        investigations: InvestigationStore,
    ) -> None:
        self._store = store
        self._ontology = ontology
        self._base = ontology.model_copy(deep=True)
        self._graph = graph
        self._working_set = working_set
        self._investigations = investigations
        self._proposals: list[LinkTypeProposal] = []

    async def refresh(self) -> None:
        """Compose the ontology in force from the store and apply it."""
        self._proposals = await self._store.all()
        composed = compose_ontology(
            self._base, self._proposals, revision=await self._store.revision()
        )
        for field in ("edge_types", "storage_aliases", "overlay_revision"):
            setattr(self._ontology, field, getattr(composed, field))
        await self._graph.apply_schema(self._ontology)

    async def _current(self) -> None:
        """Another process may have decided since this one composed: catch up if so."""
        if await self._store.revision() != self._ontology.overlay_revision:
            await self.refresh()

    def type_named(self, name: str) -> CaseType | None:
        """The type a link read as `name` has, offered or not: one in the ontology, or the latest
        proposal its links read as (pending, rejected, withdrawn or retired). A link already of a
        type no longer offered can still be corrected in other ways (`link_changes.py`)."""
        found = self._ontology.edge_type(name)
        if found is not None and not found.hidden:
            return CaseType(definition=found, storage_name=name)
        for proposal in reversed(self._proposals):
            if proposal.reads_as == name:
                return CaseType(
                    definition=proposal.definition(name),
                    storage_name=proposal.storage_name,
                    proposal_id=proposal.id if proposal.status is ProposalStatus.PENDING else None,
                )
        return None

    async def case_types(self, investigation_id: str, principal: Principal) -> dict[str, CaseType]:
        """Every type a link in this case may take: the ontology's (the OspreyFlow default
        dataset's), then the pending proposals of the datasets the case reads (ADR-099 Amendment
        3). A proposal made before that amendment names no dataset and keeps ADR-090's rule: the
        case and the cases it was branched from that `principal` may see, then a case where one of
        its links is in view; `scripts.stamp_datasets` gives it its case's dataset."""
        await self._current()
        offered = {
            t.name: CaseType(definition=t, storage_name=t.name)
            for t in self._ontology.edge_types
            if not t.hidden
        }
        pending: list[LinkTypeProposal] = []
        if principal.datasets:
            pending += await self._store.pending_for_datasets(principal.datasets)
        case = await self._investigations.get(investigation_id)
        lineage = [case.id, *await visible_ancestors(self._investigations, case, principal)]
        pending += [p for p in await self._store.pending_for_cases(lineage) if p.dataset_id is None]
        _, edges = await self._working_set.visible_membership(investigation_id, principal)
        in_view = sorted({e.type for e in edges} - set(offered))
        if in_view:
            pending += [
                p for p in await self._store.pending_named(in_view) if p.dataset_id is None
            ]
        for proposal in pending:
            if proposal.name not in offered:
                offered[proposal.name] = CaseType(
                    definition=proposal.definition(),
                    storage_name=proposal.storage_name,
                    proposal_id=proposal.id,
                )
        return offered

    def _check_name(self, name: str) -> None:
        if len(name) > MAX_NAME_CHARS or not _NAME.match(name) or len(name) < 3:
            raise ProposalRefusedError(
                "A type name is three or more capital letters, digits and single underscores, "
                f"such as KNOWN_TO, at most {MAX_NAME_CHARS} characters."
            )
        if self._ontology.edge_type(name) is not None:
            raise ProposalRefusedError(f"{name} is already a type in the ontology: use it instead.")

    async def propose(
        self,
        investigation_id: str,
        principal: Principal,
        *,
        name: str,
        from_types: list[str],
        to_types: list[str],
        directed: bool,
        colour: str | None,
        thickness: int | None,
        label: str | None,
        reason: str,
    ) -> LinkTypeProposal:
        await self._current()
        name = name.strip()
        self._check_name(name)
        reason = reason.strip()
        if not reason or len(reason) > MAX_REASON_CHARS:
            raise ProposalRefusedError(
                f"Say why no type fits: a reason of at most {MAX_REASON_CHARS} characters."
            )
        known = {t.name for t in self._ontology.entity_types}
        for ends in (from_types, to_types):
            if not ends or any(t not in known for t in ends):
                raise ProposalRefusedError(
                    "Each end names one or more entity types of the ontology."
                )
        case = await self._investigations.get(investigation_id)
        if name in await self.case_types(case.id, principal):
            raise ProposalRefusedError(f"{name} is already offered in this case: use it instead.")
        try:
            proposal = LinkTypeProposal(
                id=new_id(),
                name=name,
                label=(label or "").strip() or None,
                from_types=sorted(set(from_types)),
                to_types=sorted(set(to_types)),
                directed=directed,
                colour=colour,
                thickness=thickness,
                investigation_id=case.id,
                owning_unit=case.owning_unit,
                dataset_id=principal.datasets[0] if principal.datasets else None,
                proposed_by=principal.id,
                proposed_at=datetime.now(UTC),
                reason=reason,
            )
            proposal.definition()  # the colour and thickness rules of every type
        except ValidationError as error:
            raise ProposalRefusedError(str(error.errors()[0]["msg"])) from error
        await self._store.create(proposal)
        await self.refresh()
        return proposal

    async def withdraw(
        self,
        investigation_id: str,
        proposal_id: str,
        principal: Principal,
        *,
        reason: str,
        is_author: bool,
    ) -> LinkTypeProposal:
        """The proposer or an Author of a case reading its dataset withdraws a pending proposal."""
        proposal = await self._store.get(proposal_id)
        # ADR-099 Amendment 3: from any case reading its dataset; one made before, from its case.
        in_reach = (
            proposal.dataset_id in (principal.datasets or [])
            if proposal.dataset_id is not None
            else proposal.investigation_id == investigation_id
        )
        if not in_reach or proposal.status is not ProposalStatus.PENDING:
            raise ProposalNotFoundError(proposal_id)
        if proposal.proposed_by != principal.id and not is_author:
            raise ProposalRefusedError(
                "Only its proposer or an Author of the case may withdraw it."
            )
        await self._decide(proposal, ProposalStatus.WITHDRAWN, principal, reason)
        await self.refresh()
        return await self._store.get(proposal_id)

    async def proposals(self, principal: Principal) -> list[LinkTypeProposal]:
        """The administrator's list: their own unit's proposals, newest first."""
        return await self._store.list_authorized(principal)

    async def _pending_for_decision(
        self, proposal_id: str, principal: Principal
    ) -> LinkTypeProposal:
        proposal = await self._store.get_authorized(proposal_id, principal)
        if proposal.status is not ProposalStatus.PENDING:
            raise ProposalRefusedError(f"This proposal is already {proposal.status.value}.")
        return proposal

    async def _decide(
        self,
        proposal: LinkTypeProposal,
        status: ProposalStatus,
        principal: Principal,
        reason: str,
        **fields: object,
    ) -> None:
        reason = reason.strip()
        if not reason or len(reason) > MAX_REASON_CHARS:
            raise ProposalRefusedError(
                f"Say why: a reason of at most {MAX_REASON_CHARS} characters is required."
            )
        await self._store.decide(
            proposal.id,
            status=status,
            by=principal.id,
            at=datetime.now(UTC),
            reason=reason,
            **fields,  # type: ignore[arg-type]
        )

    async def promote(
        self,
        proposal_id: str,
        principal: Principal,
        *,
        basis: Literal["direct", "probabilistic"],
        reason: str,
        rename_to: str | None = None,
    ) -> LinkTypeProposal:
        """Into the ontology for every case, under its name or `rename_to`, with the basis the
        administrator chooses; Direct only from now on (`direct_since`). A type of that name
        already promoted takes it as merged if its links fit, and is refused otherwise: rename it.
        Pending proposals of the same name in the unit whose links fit are merged into it."""
        await self._current()
        proposal = await self._pending_for_decision(proposal_id, principal)
        name = (rename_to or proposal.name).strip()
        existing = self._ontology.edge_type(name)
        if existing is not None and not existing.analyst_defined:
            raise ProposalRefusedError(f"{name} is an authored type: promote under another name.")
        now = datetime.now(UTC)
        if existing is not None:
            if not _fits(proposal, existing):
                raise ProposalRefusedError(
                    f"Its links do not all fit {name} as promoted: promote it under a new name."
                )
            await self._decide(
                proposal, ProposalStatus.MERGED, principal, reason, promoted_name=name
            )
        else:
            if rename_to is not None:
                self._check_name(name)
            await self._decide(
                proposal,
                ProposalStatus.PROMOTED,
                principal,
                reason,
                basis=basis,
                promoted_name=name,
                direct_since=now if basis == "direct" else None,
            )
            promoted = proposal.definition(name)
            for other in await self._store.pending_named([proposal.name]):
                if other.owning_unit == principal.org_unit and _fits(other, promoted):
                    await self._decide(
                        other,
                        ProposalStatus.MERGED,
                        principal,
                        f"Merged into {name}: {reason}",
                        promoted_name=name,
                    )
        await self._store.bump_revision()
        await self.refresh()
        return await self._store.get(proposal_id)

    async def reject(
        self, proposal_id: str, principal: Principal, *, reason: str
    ) -> LinkTypeProposal:
        """No longer offered; its links keep reading as its name."""
        proposal = await self._pending_for_decision(proposal_id, principal)
        await self._decide(proposal, ProposalStatus.REJECTED, principal, reason)
        await self.refresh()
        return await self._store.get(proposal_id)

    async def retire(
        self, name: str, principal: Principal, *, reason: str
    ) -> list[LinkTypeProposal]:
        """A type the unit promoted, no longer offered anywhere; its links stay and read as it."""
        await self._current()
        promoted = [
            p
            for p in await self._store.list_authorized(principal)
            if p.status is ProposalStatus.PROMOTED and p.reads_as == name
        ]
        if not promoted:
            raise ProposalNotFoundError(name)
        for proposal in promoted:
            await self._decide(proposal, ProposalStatus.RETIRED, principal, reason)
        await self._store.bump_revision()
        await self.refresh()
        return [await self._store.get(p.id) for p in promoted]


# --- The routes' bodies and answers ---------------------------------------------------------


class ProposeLinkTypeRequest(BaseModel):
    name: str
    label: str | None = None
    from_types: list[str]
    to_types: list[str]
    directed: bool = True
    colour: str | None = None
    thickness: int | None = None
    reason: str


class LinkTypeOption(BaseModel):
    """A type the change form offers in a case. `proposal_id` is set for one proposed and not yet
    decided, which the form marks as proposed. The label a link is stored under is never sent."""

    definition: EdgeTypeDef
    proposal_id: str | None = None


class CaseLinkTypesResponse(BaseModel):
    types: list[LinkTypeOption]


class LinkTypeDecisionRequest(BaseModel):
    reason: str


class PromoteLinkTypeRequest(BaseModel):
    basis: Literal["direct", "probabilistic"]
    reason: str
    #: Promote under another name: needed when a type of its name is promoted and its links do
    #: not all fit it.
    rename_to: str | None = None


class RetireLinkTypeRequest(BaseModel):
    name: str
    reason: str


class LinkTypeProposalList(BaseModel):
    proposals: list[LinkTypeProposal]


def public_ontology(ontology: OntologySchema) -> OntologySchema:
    """The ontology as `/v1/ontology` answers it: no proposal's own labels, and no aliases."""
    return ontology.model_copy(
        update={
            "edge_types": [t for t in ontology.edge_types if not t.hidden],
            "storage_aliases": {},
        }
    )
