"""Analyst-proposed relationship types, and the ontology they make — `06_DECISIONS.md` ADR-090 and
its Amendment 1 (step C of ADR-081).

An Editor proposes a type from the change form when none fits. It is usable at once in that case,
is probabilistic, and is kept here, never in `default.yaml`. Since ADR-143 decision 9 it is decided
on its dataset's Model tab (below); one made before ADR-099 Amendment 3, which names no dataset, is
still promoted (its basis chosen), rejected or retired by an `osprey-admin` holder of the proposing
unit, and is also offered where one of its links is in view. The proposer or an Author of the case
may withdraw a pending one.

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

**ADR-143 decision 9 and ADR-090 Amendment 4 (L3.5).** A proposal names its case's source dataset
(never the case's analyst layer) and is usable in that case alone until it is decided. A holder of
`accept_types` past the dataset's own gate decides it on the Studio's *1 Model* tab: *Add it to the
draft model* writes a `link_type` extension into the dataset's draft (status `accepted`), or
*Decline* (`rejected`). Its links can be promoted into the dataset (`promotion_refusals`, which
L3.4's promotion sheet calls) only once the version holding it is live; until then they stay in
the case's layer, and a declined type's stay there for good. Once live, the type is offered in
every case reading the dataset. ADR-090's deployment-wide promotion by an administrator stays only
for a proposal made before ADR-099 Amendment 3, which names no dataset.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal, Protocol

from pydantic import BaseModel, Field, ValidationError

from adapters.graph_arcadedb.naming import STORAGE_SEPARATOR
from conduit_common.identity import new_id
from schemas.domain import EdgeTypeDef, OntologySchema, Principal

from .dataset_scope import analyst_layer, refuse_in_a_composite_case
from .investigations import InvestigationStore

if TYPE_CHECKING:
    from .link_type_store import LinkTypeProposalStore
    from .target_models import TargetModelStore
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
    #: ADR-143 decision 9: added to its dataset's draft domain model by a data engineer on the
    #: Studio's Model tab; its links are promotable once that version is live.
    ACCEPTED = "accepted"


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
    #: The source dataset of its case at proposal (ADR-099 Amendment 3; never the case's layer).
    #: Offered in that case alone until a data engineer of the dataset accepts it and its version
    #: is live (ADR-143 decision 9). `None` for one made before, which keeps ADR-090's case rule.
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

    def in_force(self) -> EdgeTypeDef:
        """An accepted type as its dataset's live model has it: with the basis the data engineer
        chose, Direct only from `direct_since` (ADR-090 Amendment 4, decision 6 standing)."""
        return self.definition().model_copy(
            update={
                "basis": self.basis or "probabilistic",
                "direct_since": self.direct_since if self.basis == "direct" else None,
            }
        )

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
    """Proposals, the types a case may use, and the decisions on them (ADR-090; ADR-143 decision 9).

    `ontology` is the one shared `OntologySchema` every service holds; `refresh` rewrites it in
    place to `compose_ontology` of the authored types and every proposal, and applies it to the
    graph store, so the store accepts a proposal's label and reads it under its name. Routes check
    the case access level (Editor to propose, Author or the proposer to withdraw); a dataset's
    proposals are decided past the dataset's gate with `accept_types`, by its store reads that name
    the dataset; one with no dataset by `osprey-admin` through `get_authorized`, so another unit's
    is not found."""

    def __init__(
        self,
        store: LinkTypeProposalStore,
        ontology: OntologySchema,
        graph: _Schema,
        working_set: WorkingSetService,
        investigations: InvestigationStore,
        *,
        models: TargetModelStore | None = None,
    ) -> None:
        #: Each dataset's domain model (ADR-140 R12), where an accepted type is written; `None`
        #: only for a test of ADR-090's own rules, when nothing can be accepted.
        self._models = models
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

    async def _model_link_types(self, dataset_id: str | None) -> tuple[set[str], set[str], int]:
        """The link-type extensions in force in the dataset's live model, those in its draft, and
        the draft's version (0 for none)."""
        if self._models is None or dataset_id is None:
            return set(), set(), 0
        live = await self._models.live(dataset_id)
        draft = await self._models.draft(dataset_id)

        def named(model: Any) -> set[str]:
            if model is None:
                return set()
            return {
                e.name for e in model.extensions if e.kind == "link_type" and e.retired_in is None
            }

        return named(live), named(draft), draft.version if draft is not None else 0

    async def _accepted_in_force(self, principal: Principal) -> list[LinkTypeProposal]:
        """The accepted types of the datasets this case reads whose model version is live."""
        found: list[LinkTypeProposal] = []
        for dataset_id in _sources_of(principal):
            live, _, _ = await self._model_link_types(dataset_id)
            found += [
                p
                for p in await self._store.accepted_for_datasets([dataset_id])
                if p.status is ProposalStatus.ACCEPTED and p.name in live
            ]
        return found

    async def case_types(self, investigation_id: str, principal: Principal) -> dict[str, CaseType]:
        """Every type a link in this case may take: the ontology's (the OspreyFlow default
        dataset's); the types a data engineer accepted into the model of a dataset the case reads,
        once that version is live; then the proposals made in this case alone, pending or accepted
        and not yet live (ADR-143 decision 9; ADR-090 Amendment 4, "within the case"). Another case
        reading the same dataset is offered none of them (rule 3). A proposal made before ADR-099
        Amendment 3 names no dataset and keeps ADR-090's rule: also a case where one of its links
        is in view."""
        await self._current()
        offered = {
            t.name: CaseType(definition=t, storage_name=t.name)
            for t in self._ontology.edge_types
            if not t.hidden
        }
        for accepted in await self._accepted_in_force(principal):
            offered.setdefault(
                accepted.name,
                CaseType(definition=accepted.in_force(), storage_name=accepted.storage_name),
            )
        pending = list(await self._store.pending_for_cases([investigation_id]))
        pending += [
            p
            for p in await self._store.named_in_case(investigation_id, None)
            if p.status in _ACCEPTED_STATES and p.dataset_id is not None
        ]
        _, edges = await self._working_set.visible_membership(investigation_id, principal)
        in_view = sorted({e.type for e in edges} - set(offered))
        if in_view:
            pending += [p for p in await self._store.pending_named(in_view) if p.dataset_id is None]
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
        dataset_id = next(iter(_sources_of(principal)), None)
        if principal.datasets is not None and dataset_id is None:
            # A case that reads nothing has no dataset to decide it (ADR-143 Amendment 4).
            raise ProposalRefusedError(
                "This case reads no dataset, so a type proposed here has no data engineer to "
                "decide it: choose the case's dataset first."
            )
        await refuse_in_a_composite_case()
        # The live model alone: a draft is the data engineers' (`edit_target_model`), and naming
        # what it holds would tell this case of another's accepted proposal. A name only in the
        # draft is caught at acceptance instead.
        live, _, _ = await self._model_link_types(dataset_id)
        if name in live:
            raise ProposalRefusedError(
                f"{name} is already in this dataset's domain model: use it instead."
            )
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
                # Its case's source dataset, never the case's analyst layer (ADR-143 decision 9).
                dataset_id=dataset_id,
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
        """The proposer or an Author of its case withdraws a pending proposal, from its case alone:
        from another case, even one reading the same dataset, it is not found (rule 3)."""
        proposal = await self._store.get(proposal_id)
        in_reach = proposal.investigation_id == investigation_id
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
        if proposal.dataset_id is not None:
            # ADR-090 Amendment 4: decided on its dataset's Model tab, never deployment-wide.
            raise ProposalRefusedError(
                "This type belongs to a dataset: a data engineer of that dataset decides it on "
                "the Ingest Studio's Model tab."
            )
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
        """Records a decision, only from the status `proposal` was read with, so a decision made
        meanwhile by someone else is never overwritten."""
        _check_reason(reason)
        written = await self._store.decide(
            proposal.id,
            status=status,
            by=principal.id,
            at=datetime.now(UTC),
            reason=reason.strip(),
            only_from=proposal.status,
            **fields,  # type: ignore[arg-type]
        )
        if not written:
            raise ProposalRefusedError("Someone decided this proposal a moment ago: read it again.")

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
                # A proposal naming a dataset is its Model tab's alone (ADR-090 Amendment 4).
                if (
                    other.dataset_id is None
                    and other.owning_unit == principal.org_unit
                    and _fits(other, promoted)
                ):
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

    # --- ADR-143 decision 9: the Studio's Model tab, and what may be promoted ------------------

    async def dataset_proposals(self, dataset_id: str) -> list[LinkTypeProposal]:
        """The Model tab's list: every proposal of this dataset, newest first. The route has
        passed the dataset's own gate; the store's query names the dataset (rule 3)."""
        return await self._store.for_dataset(dataset_id)

    async def dataset_proposal_views(self, dataset_id: str) -> list[ModelProposalView]:
        """The Model tab's list, each proposal with where its type stands in the dataset's model."""
        live, drafted, _ = await self._model_link_types(dataset_id)
        views = []
        for proposal in await self._store.for_dataset(dataset_id):
            where: Literal["live", "draft"] | None = (
                "live" if proposal.name in live else "draft" if proposal.name in drafted else None
            )
            views.append(ModelProposalView.of(proposal, in_model=where))
        return views

    async def _decidable(self, dataset_id: str, proposal_id: str) -> LinkTypeProposal:
        """A proposal of this dataset still to decide: pending, or accepted and then lost from
        both the live model and the draft (the draft discarded, or saved without it), which may be
        added again rather than left stuck."""
        proposal = await self._store.get_for_dataset(proposal_id, dataset_id)
        if proposal.status is ProposalStatus.PENDING:
            return proposal
        live, drafted, _ = await self._model_link_types(dataset_id)
        if proposal.status is ProposalStatus.ACCEPTED and proposal.name not in live | drafted:
            return proposal
        word = _STATUS_WORDS.get(proposal.status, proposal.status.value)
        raise ProposalRefusedError(f"This proposal is already {word}.")

    async def accept(
        self,
        dataset_id: str,
        proposal_id: str,
        principal: Principal,
        *,
        basis: Literal["direct", "probabilistic"],
        reason: str,
    ) -> tuple[LinkTypeProposal, int]:
        """*Add it to the draft model*, with the basis the data engineer chooses (ADR-090
        Amendment 4, decision 6 standing): a `link_type` extension in the dataset's draft (opened
        if there is none), made live with the next model version (ADR-140 R12). Never by its own
        proposer (ADR-145 decision 7). The proposal is claimed first, by a write that succeeds only
        from the status read, so an acceptance racing a decline or a withdrawal loses cleanly; the
        extension is then appended under the dataset's model lock (`add_extension`), so two
        acceptances at once both land; if that is refused, the claim is given back. Pending
        proposals of the dataset of the same name whose links fit are merged into it. Answers the
        proposal and the draft's version."""
        await self._current()
        _check_reason(reason)
        proposal = await self._decidable(dataset_id, proposal_id)
        if proposal.proposed_by == principal.id:
            raise ProposalRefusedError(
                "You proposed this type, so another data engineer of the dataset decides it."
            )
        if self._models is None:
            raise ProposalRefusedError("This deployment keeps no domain models to add it to.")
        found = self._ontology.edge_type(proposal.name)
        live, drafted, _ = await self._model_link_types(dataset_id)
        if (found is not None and not found.hidden) or proposal.name in live | drafted:
            raise ProposalRefusedError(
                f"{proposal.name} is already in this dataset's domain model: decline this one, "
                "saying which type to use."
            )
        now = datetime.now(UTC)
        claimed = await self._store.decide(
            proposal.id,
            status=ProposalStatus.ACCEPTED,
            by=principal.id,
            at=now,
            reason=reason.strip(),
            basis=basis,
            promoted_name=proposal.name,
            direct_since=now if basis == "direct" else None,
            only_from=proposal.status,
        )
        if not claimed:
            raise ProposalRefusedError("Someone decided this proposal a moment ago: read it again.")
        try:
            draft = await self._models.add_extension(
                dataset_id, proposal.name, "link_type", principal
            )
        except BaseException:
            await self._store.decide(
                proposal.id,
                status=proposal.status,
                by=proposal.decided_by or principal.id,
                at=now,
                reason=proposal.decision_reason or "",
                only_from=ProposalStatus.ACCEPTED,
            )
            raise
        accepted = proposal.definition()
        for other in await self._store.for_dataset(dataset_id):
            if (
                other.id != proposal.id
                and other.name == proposal.name
                and other.status is ProposalStatus.PENDING
                and _fits(other, accepted)
            ):
                await self._store.decide(
                    other.id,
                    status=ProposalStatus.MERGED,
                    by=principal.id,
                    at=now,
                    reason=f"Merged into {proposal.name}: {reason.strip()}",
                    promoted_name=proposal.name,
                    only_from=ProposalStatus.PENDING,
                )
        await self.refresh()
        return await self._store.get(proposal_id), draft.version

    async def decline(
        self, dataset_id: str, proposal_id: str, principal: Principal, *, reason: str
    ) -> LinkTypeProposal:
        """*Decline*, with a reason: no longer offered; its links stay in its case's layer for
        good and keep reading as its name. Only from pending, by a write that checks it."""
        _check_reason(reason)
        proposal = await self._store.get_for_dataset(proposal_id, dataset_id)
        decided = proposal.status is ProposalStatus.PENDING and await self._store.decide(
            proposal.id,
            status=ProposalStatus.REJECTED,
            by=principal.id,
            at=datetime.now(UTC),
            reason=reason.strip(),
            only_from=ProposalStatus.PENDING,
        )
        if not decided:
            word = _STATUS_WORDS.get(proposal.status, proposal.status.value)
            raise ProposalRefusedError(f"This proposal is already {word}.")
        await self.refresh()
        return await self._store.get(proposal_id)

    async def promotion_refusals(
        self, investigation_id: str, principal: Principal, names: Sequence[str]
    ) -> dict[str, str | None]:
        """For each link type named, why its links cannot be promoted from this case into the
        case's source dataset, or `None` when they can (ADR-143 decisions 8 and 9). L3.4's
        promotion sheet calls this for every drawn link it lists. A type of the ontology is
        `None` here: whether the dataset's model holds it is the sheet's own check. A proposal of
        another case is answered exactly as a name that is no type at all (rule 3)."""
        await self._current()
        dataset_id = next(iter(_sources_of(principal)), None)
        live, drafted, draft_version = await self._model_link_types(dataset_id)
        mine = await self._store.named_in_case(investigation_id, list(names))
        in_force = {p.name for p in await self._accepted_in_force(principal)}
        answers: dict[str, str | None] = {}
        for name in names:
            found = self._ontology.edge_type(name)
            if found is not None and not found.hidden:
                answers[name] = None
                continue
            own = [p for p in mine if p.reads_as == name]
            accepted_here = any(p.status in _ACCEPTED_STATES for p in own)
            if name in live and (accepted_here or name in in_force):
                answers[name] = None
            elif not own:
                answers[name] = f"{name} is not a link type of this case."
            elif accepted_here:
                answers[name] = (
                    f"{name} is accepted into the draft domain model, version {draft_version}: "
                    "its links can be promoted once that version is made live."
                    if name in drafted
                    else f"{name} is accepted but is not in the dataset's domain model in force "
                    "or in its draft: a data engineer of the dataset adds it again on the Model "
                    "tab before its links can be promoted."
                )
            else:
                answers[name] = _why_not(name, own[-1].status)
        return answers


_STATUS_WORDS = {ProposalStatus.REJECTED: "declined", ProposalStatus.ACCEPTED: "accepted"}
_ACCEPTED_STATES = (ProposalStatus.ACCEPTED, ProposalStatus.MERGED)


def _why_not(name: str, status: ProposalStatus) -> str:
    if status is ProposalStatus.PENDING:
        return (
            f"{name} is proposed, not yet accepted by a data engineer of the dataset: its links "
            "stay in the case's layer until it is."
        )
    if status is ProposalStatus.REJECTED:
        return f"{name} was declined: its links stay in the case's layer for good."
    return f"{name} was {status.value}: its links stay in the case's layer."


def _check_reason(reason: str) -> None:
    reason = reason.strip()
    if not reason or len(reason) > MAX_REASON_CHARS:
        raise ProposalRefusedError(
            f"Say why: a reason of at most {MAX_REASON_CHARS} characters is required."
        )


def _sources_of(principal: Principal) -> list[str]:
    """The datasets a case-scoped principal reads, but the case's own analyst layer: a proposal
    joins its case's source dataset, never the layer (ADR-143 decisions 1 and 9). The layer is
    held beside the read set by `dataset_scope` for the request."""
    layer = analyst_layer()
    return [d for d in principal.datasets or [] if d != layer]


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


class AcceptLinkTypeRequest(BaseModel):
    """*Add it to the draft model*: what stands behind its links, no default (ADR-090 decision 6,
    standing for the accepting data engineer), and why."""

    basis: Literal["direct", "probabilistic"]
    reason: str


class LinkTypeProposalList(BaseModel):
    proposals: list[LinkTypeProposal]


class ModelProposalView(BaseModel):
    """A proposal as the Studio's Model tab shows it to a data engineer of its dataset (ADR-143
    decision 9): what it means and who proposed it, never the case it was proposed in (rule 3: the
    data engineer may be a member of none) nor the label its links are stored under (rule 7)."""

    id: str
    name: str
    label: str | None = None
    from_types: list[str]
    to_types: list[str]
    directed: bool
    proposed_by: str
    proposed_at: datetime
    reason: str
    status: ProposalStatus
    decided_by: str | None = None
    decided_at: datetime | None = None
    decision_reason: str | None = None
    basis: Literal["direct", "probabilistic"] | None = None
    #: Where its type stands in the dataset's model: `live`, in the `draft`, or neither (`None`:
    #: never added, or an accepted one lost from the draft, which may be added again).
    in_model: Literal["live", "draft"] | None = None

    @classmethod
    def of(
        cls, proposal: LinkTypeProposal, in_model: Literal["live", "draft"] | None = None
    ) -> ModelProposalView:
        fields = proposal.model_dump(include=set(cls.model_fields) - {"in_model"})
        return cls.model_validate({**fields, "in_model": in_model})


class ModelProposalList(BaseModel):
    proposals: list[ModelProposalView]


class PromotableRequest(BaseModel):
    """The link types of the links a promotion would carry, as the case reads them."""

    types: list[str] = Field(min_length=1, max_length=200)


class PromotableType(BaseModel):
    name: str
    promotable: bool
    #: Why not, in words the promotion sheet shows; `None` when it can go.
    reason: str | None = None


class PromotableResponse(BaseModel):
    types: list[PromotableType]


def public_ontology(ontology: OntologySchema) -> OntologySchema:
    """The ontology as `/v1/ontology` answers it: no proposal's own labels, and no aliases."""
    return ontology.model_copy(
        update={
            "edge_types": [t for t in ontology.edge_types if not t.hidden],
            "storage_aliases": {},
        }
    )
