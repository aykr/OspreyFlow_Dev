"""Handling scheme loader and evaluator — `spec/01_DOMAIN_MODEL.md` §2.2.

The enforcement logic reads the booleans a scheme declares (`dissemination`,
`direct_action`, `consult_originator`), never the code letters, so swapping
`uk-le.yaml` for `us-criminal-intelligence.yaml` — or enabling both — is a
configuration change with nothing above this module to touch.
"""

from __future__ import annotations

import logging
from collections.abc import (
    Awaitable,
    Callable,
    Container,
    Iterable,
    Iterator,
    Mapping,
    Sequence,
)
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Literal, Protocol

import yaml
from pydantic import BaseModel, ValidationError

from schemas.domain import (
    DrawnAssertion,
    Edge,
    Handling,
    Node,
    Principal,
    Provenance,
    SourceRef,
)
from schemas.mapconfig import (
    GAZETTEER_DATASET_PREFIX,
    GAZETTEER_ONLY_IDENTIFIERS,
    GAZETTEER_SOURCE_IDENTIFIERS,
)

from .errors import HandlingSchemeError

_SCHEME_DIR = Path(__file__).resolve().parent / "handling"
_log = logging.getLogger(__name__)

#: The locator of every source a drawing board writes (`services/api/boards.py`). It is how a source
#: the board wrote, which may name a cited document, is told from any other.
BOARD_SOURCE_LOCATOR = "a drawing board of the case"
#: The type a cited id must be: the question drawing asks (ADR-143 decision 4).
_CITABLE_TYPE = "Document"

Dissemination = Literal["permitted", "conditional", "restricted"]


class HandlingCode(BaseModel):
    label: str
    dissemination: Dissemination


class ActionCode(BaseModel):
    label: str
    direct_action: bool
    originator_permission: bool = False


class SanitisationCode(BaseModel):
    label: str
    consult_originator: bool


class HandlingScheme(BaseModel):
    name: str
    classification: list[str]
    handling_codes: dict[str, HandlingCode]
    action_codes: dict[str, ActionCode]
    sanitisation_codes: dict[str, SanitisationCode]

    def clears(self, principal_clearance: str, classification: str) -> bool:
        """The classification dominance rule (`01_DOMAIN_MODEL.md` §2.2),
        for a single check rather than `AccessFilter`'s per-query
        `within(...)` list — the source profiler's shape-masking decision
        (`09_INGEST_STUDIO.md` §3) is the caller, since it has no
        traversal to inject a predicate into.

        An unrecognised *principal* clearance clears nothing — the same
        default-deny `AccessFilter.allowed_classifications` applies,
        since a malformed or stale clearance is a security posture
        question, not a configuration bug. An unrecognised
        *classification* is different in kind: it means the marking being
        checked is not in this scheme at all, the same scheme mismatch
        `evaluate_handling` treats as a hard error rather than silently
        denying or allowing."""
        if classification not in self.classification:
            raise HandlingSchemeError(
                f"classification {classification!r} is not defined in scheme {self.name!r}"
            )
        try:
            principal_rank = self.classification.index(principal_clearance)
        except ValueError:
            return False
        return self.classification.index(classification) <= principal_rank


class HandlingDecision(BaseModel):
    """What the export gate and every dissemination decision branch on —
    never the raw code letters."""

    dissemination: Dissemination
    direct_action_permitted: bool
    originator_permission_required: bool
    consult_originator: bool


def load_handling_scheme(path: str | Path) -> HandlingScheme:
    path = Path(path)
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise HandlingSchemeError(f"{path}: handling scheme must be a YAML mapping")
    try:
        return HandlingScheme.model_validate({"name": path.stem, **raw})
    except ValidationError as exc:
        raise HandlingSchemeError(f"{path}: {exc}") from exc


def load_uk_le_scheme() -> HandlingScheme:
    return load_handling_scheme(_SCHEME_DIR / "uk-le.yaml")


def load_us_criminal_intelligence_scheme() -> HandlingScheme:
    return load_handling_scheme(_SCHEME_DIR / "us-criminal-intelligence.yaml")


_DISSEMINATION_RANK: dict[str, int] = {"permitted": 0, "conditional": 1, "restricted": 2}


def _known(
    codes: Mapping[str, object], code: str | None, kind: str, scheme: HandlingScheme
) -> None:
    if code is not None and code not in codes:
        raise HandlingSchemeError(f"{kind} {code!r} is not defined in scheme {scheme.name!r}")


def is_restricted(code: str, scheme: HandlingScheme) -> bool:
    """Whether `code` is a restricted handling code in `scheme`: the one place that decides it, for
    the access step (`graph_arcadedb/access_filter.py`) and for what a link merges into
    (`audience_of`). A code the scheme does not define is not restricted."""
    defined = scheme.handling_codes.get(code)
    return defined is not None and defined.dissemination == "restricted"


def audience_of(
    handling: Handling, datasets: Iterable[str], scheme: HandlingScheme
) -> tuple[str, str, tuple[str, ...], str | None, str | None]:
    """The key two link writes share exactly when the same principals see both (ADR-102
    Amendment 3): every part the access step reads. The classification, the handling code, the set
    of datasets (ADR-099) and, only where the code is restricted, the originator and the owning
    unit, which decide visibility only then (`access_filter.py`). The action and sanitisation codes
    decide no visibility and are not in it. A write merges into an existing link only with an equal
    key."""
    return audience_parts(
        handling.classification,
        handling.handling_code,
        datasets,
        handling.originator,
        handling.owning_unit,
        scheme,
    )


def audience_parts(
    classification: str,
    handling_code: str,
    datasets: Iterable[str],
    originator: str,
    owning_unit: str,
    scheme: HandlingScheme,
) -> tuple[str, str, tuple[str, ...], str | None, str | None]:
    """`audience_of` from the parts themselves, for a stored link read back as flat properties."""
    restricted = is_restricted(handling_code, scheme)
    return (
        classification,
        handling_code,
        tuple(sorted(set(datasets))),
        originator if restricted else None,
        owning_unit if restricted else None,
    )


def merge_handling(existing: Handling, incoming: Handling, scheme: HandlingScheme) -> Handling:
    """The handling of an element written again (ADR-102): never lower than either write's. The
    higher classification; the handling code with the narrower dissemination; the action code that
    forbids direct action (then the one needing the originator's permission) over one that permits
    it, and any over none; the sanitisation code that consults the originator over one that does
    not, and any over none; the earlier review date; a legal basis once given. The owning unit and
    originator stay the existing element's: the restricted-code check rests on them, and a later
    write does not move the element to another unit. Lowering handling is an analyst's explicit
    change, never a merge.

    The same order whichever write came first, except the units, which are the first's. A code
    the scheme does not define is refused rather than ranked by guesswork."""
    for h in (existing, incoming):
        if h.classification not in scheme.classification:
            raise HandlingSchemeError(
                f"classification {h.classification!r} is not defined in scheme {scheme.name!r}"
            )
        _known(scheme.handling_codes, h.handling_code, "handling code", scheme)
        _known(scheme.action_codes, h.action_code, "action code", scheme)
        _known(scheme.sanitisation_codes, h.sanitisation_code, "sanitisation code", scheme)

    classification = max(
        (existing.classification, incoming.classification), key=scheme.classification.index
    )
    handling_code = max(
        (existing.handling_code, incoming.handling_code),
        key=lambda c: _DISSEMINATION_RANK[scheme.handling_codes[c].dissemination],
    )

    def action_rank(code: str | None) -> tuple[int, int]:
        if code is None:
            return (0, 0)
        a = scheme.action_codes[code]
        return (2 if not a.direct_action else 1, 1 if a.originator_permission else 0)

    def sanitisation_rank(code: str | None) -> int:
        if code is None:
            return 0
        return 2 if scheme.sanitisation_codes[code].consult_originator else 1

    reviews = [d for d in (existing.review_date, incoming.review_date) if d is not None]
    return existing.model_copy(
        update={
            "classification": classification,
            "handling_code": handling_code,
            "action_code": max((existing.action_code, incoming.action_code), key=action_rank),
            "sanitisation_code": max(
                (existing.sanitisation_code, incoming.sanitisation_code), key=sanitisation_rank
            ),
            "review_date": min(reviews) if reviews else None,
            "legal_basis": existing.legal_basis or incoming.legal_basis,
        }
    )


def evaluate_handling(handling: Handling, scheme: HandlingScheme) -> HandlingDecision:
    """Evaluate one node/edge's `Handling` block against the active scheme."""
    if handling.classification not in scheme.classification:
        raise HandlingSchemeError(
            f"classification {handling.classification!r} is not defined in scheme {scheme.name!r}"
        )
    handling_code = scheme.handling_codes.get(handling.handling_code)
    if handling_code is None:
        raise HandlingSchemeError(
            f"handling code {handling.handling_code!r} is not defined in scheme {scheme.name!r}"
        )

    direct_action_permitted = False
    originator_permission_required = False
    if handling.action_code is not None:
        action_code = scheme.action_codes.get(handling.action_code)
        if action_code is None:
            raise HandlingSchemeError(
                f"action code {handling.action_code!r} is not defined in scheme {scheme.name!r}"
            )
        direct_action_permitted = action_code.direct_action
        originator_permission_required = action_code.originator_permission

    consult_originator = False
    if handling.sanitisation_code is not None:
        sanitisation_code = scheme.sanitisation_codes.get(handling.sanitisation_code)
        if sanitisation_code is None:
            raise HandlingSchemeError(
                f"sanitisation code {handling.sanitisation_code!r} is not defined in "
                f"scheme {scheme.name!r}"
            )
        consult_originator = sanitisation_code.consult_originator

    return HandlingDecision(
        dissemination=handling_code.dissemination,
        direct_action_permitted=direct_action_permitted,
        originator_permission_required=originator_permission_required,
        consult_originator=consult_originator,
    )


def principal_may_view(handling: Handling, principal: Principal, scheme: HandlingScheme) -> bool:
    """The same two axes `AccessFilter.gremlin_has_step` compiles into a
    traversal predicate (`01_DOMAIN_MODEL.md` §2.2), evaluated directly
    for one `Handling` block instead of injected into a query — for a
    caller with no traversal to inject a predicate into, such as the
    source profiler's shape-masking decision (`09_INGEST_STUDIO.md` §3).
    `action_code`/`sanitisation_code` never gate a read, only classification
    and a restricted `handling_code` do."""
    if not scheme.clears(principal.clearance, handling.classification):
        return False
    code = scheme.handling_codes.get(handling.handling_code)
    if code is None:
        raise HandlingSchemeError(
            f"handling code {handling.handling_code!r} is not defined in scheme {scheme.name!r}"
        )
    if code.dissemination != "restricted":
        return True
    return handling.handling_code in principal.receivable_handling_codes and principal.org_unit in (
        handling.owning_unit,
        handling.originator,
    )


def in_case_datasets(datasets: Sequence[str], principal: Principal) -> bool:
    """ADR-099's third axis for one element: it belongs to one of the case's datasets, or the
    principal is the Conduit's own unlimited background work (`datasets is None`). The same rule
    `AccessFilter.gremlin_dataset_step` compiles into a traversal."""
    if principal.datasets is None:
        return True
    return not set(datasets).isdisjoint(principal.datasets)


def principal_may_read(
    handling: Handling, datasets: Sequence[str], principal: Principal, scheme: HandlingScheme
) -> bool:
    """All three axes for one stored element, for a caller holding its body already (the working
    set's projection, export): its handling and its datasets."""
    return in_case_datasets(datasets, principal) and principal_may_view(handling, principal, scheme)


def sources_within_case(datasets: Sequence[str], principal: Principal) -> bool:
    """ADR-130 Amendments 1 and 2 (rule 3, ADR-099): every dataset the element belongs to is one
    the reader's case reads. An element may be read through any one of its datasets, and its
    sources name no dataset, so only this lets them be said. `principal.datasets is None` is the
    Conduit's own unlimited work, which reads every dataset. A scoped reader with an element that
    names no dataset cannot be confirmed, so it is not within."""
    if principal.datasets is None:
        return True
    if not datasets:
        return False
    return set(datasets) <= set(principal.datasets)


_SOURCES_IN_FULL: ContextVar[bool] = ContextVar("sources_in_full", default=False)
_CITED_DOCUMENTS_KEPT: ContextVar[bool] = ContextVar("cited_documents_kept", default=False)


@contextmanager
def sources_in_full() -> Iterator[None]:
    """ADR-130 Amendment 2, "a read that is written back": inside this scope `withhold_sources`
    returns every element unchanged. For a writer that reads an element and writes its provenance
    back, which would otherwise rebuild it from a withheld list. The read is still made with the
    request's principal, so the access filter applies as before (rule 3); only the sources are left
    in. A context variable, so it holds for the calling task alone. Never wrap a read whose result
    goes to the Glass."""
    token = _SOURCES_IN_FULL.set(True)
    try:
        yield
    finally:
        _SOURCES_IN_FULL.reset(token)


@contextmanager
def cited_documents_kept() -> Iterator[None]:
    """ADR-143 Amendment 8 item 5: inside this scope `withhold_sources` leaves a drawn element's
    cited documents as stored, and applies every other rule. For a read that fills the working set,
    or whose result is written back: otherwise one person's view would be stored as everyone's, and
    an author who may no longer read a document would erase it by changing a label. No document read
    is made inside it. The read is still made with the request's principal (rule 3). A context
    variable, so it holds for the calling task alone. What such a read returns goes to no one
    without the rule: every send applies `withhold_sources` outside this scope."""
    token = _CITED_DOCUMENTS_KEPT.set(True)
    try:
        yield
    finally:
        _CITED_DOCUMENTS_KEPT.reset(token)


def withhold_sources[Element: (Node, Edge)](
    element: Element, principal: Principal, readable_documents: Container[str] | None = None
) -> Element:
    """`element` as `principal` may be sent it: where its sources are not within the case, a copy
    with them emptied and `provenance.sources_withheld` set. Otherwise `element` itself. Nothing
    stored is changed; the working set holds the full body and projects this for each reader.

    `readable_documents` is the result of the one batched read for the answer
    (`readable_cited_documents`): the documents its drawn elements cite that this reader may read
    now (ADR-143 Amendment 8). A cited document not in it is withheld, and **given none, every one
    is**, so a caller that makes no read fails closed. This function makes no read itself."""
    if _SOURCES_IN_FULL.get():
        return element
    element = _board_as_known(element, principal)
    element = _gazetteer_identifiers_withheld(element, principal)
    if not _CITED_DOCUMENTS_KEPT.get():
        element = _cited_documents_as_known(element, readable_documents or frozenset())
    if sources_within_case(element.datasets, principal):
        return element
    provenance = element.provenance.model_copy(update={"sources": [], "sources_withheld": True})
    return element.model_copy(update={"provenance": provenance})


def _note_source_id(drawn: DrawnAssertion) -> str:
    """The id of the source of an item drawn from a note alone: it names no document."""
    return f"drawn:{drawn.item_id}"


def _cites(source: SourceRef, drawn: DrawnAssertion) -> bool:
    """Whether a drawn element's source names a cited document: one the board wrote, other than the
    note's own, or one naming the document the assertion cites now. Any other source (a loaded
    row's, merged onto a promoted item) is not the board's, and not this rule's."""
    if source.document_id == drawn.source_document:
        return True
    return source.locator == BOARD_SOURCE_LOCATOR and source.document_id != _note_source_id(drawn)


class Provenanced(Protocol):
    """Anything that says what it cites: a node, a link, or a stored record's provenance."""

    @property
    def provenance(self) -> Provenance: ...


def cited_documents(elements: Iterable[Provenanced]) -> set[str]:
    """Every document the drawn elements among `elements` cite: the one each assertion names now,
    and each a source the board wrote names, which after an edit may be one cited before (the edit
    leaves the stored sources as they were, and a second write keeps every stored source)."""
    cited: set[str] = set()
    for element in elements:
        drawn = element.provenance.drawn
        if drawn is None:
            continue
        if drawn.source_document is not None:
            cited.add(drawn.source_document)
        cited |= {s.document_id for s in element.provenance.sources if _cites(s, drawn)}
    return cited


async def readable_cited_documents(
    elements: Iterable[Provenanced],
    principal: Principal,
    read: Callable[[list[str], Principal], Awaitable[Iterable[Node]]],
) -> frozenset[str]:
    """ADR-143 Amendment 8 items 2 and 3: the one batched read for an answer. Of the documents the
    drawn elements among `elements` cite, those `principal` may read **now**: the ids `read` (the
    graph adapter's own access step, with this reader's principal: its handling and the case's
    datasets) finds that are a `Document`. One call of `read` for the whole answer, never one for
    each element, and none where nothing is cited or the caller's own scope keeps every document
    (a read that fills the working set or is written back). **A read that fails keeps nothing.**
    No answer is kept for a later one."""
    if _SOURCES_IN_FULL.get() or _CITED_DOCUMENTS_KEPT.get():
        return frozenset()
    cited = cited_documents(elements)
    if not cited:
        return frozenset()
    try:
        # The documents are asked for only to know that they are read: their own provenance is not
        # looked at, so no further read follows from this one.
        with cited_documents_kept():
            found = await read(sorted(cited), principal)
    except Exception:
        _log.warning(
            "the documents an answer's drawn items cite could not be read, so none is sent",
            exc_info=True,
        )
        return frozenset()
    return frozenset(n.id for n in found if n.type == _CITABLE_TYPE and n.id in cited)


def _cited_documents_as_known[Element: (Node, Edge)](
    element: Element, readable: Container[str]
) -> Element:
    """ADR-143 Amendment 8 items 1 and 8 (rule 3): a drawn element is sent without each cited
    document that is not among `readable`. `drawn.source_document` is sent empty; the sources that
    named a withheld document become one `drawn:<item_id>` source, never repeated, the source of an
    item drawn from a note alone, so that what is sent does not say how many documents were
    withheld, or that any was. A note is never blanked; an empty one beside a withheld document is
    sent as none, whatever was stored. It changes which fields of an element the reader already
    sees are sent, and no traversal, degree, path or count."""
    drawn = element.provenance.drawn
    if drawn is None:
        return element
    placeholder = _note_source_id(drawn)
    withheld = {i for i in cited_documents([element]) if i not in readable}
    if not withheld:
        return element
    sources: list[SourceRef] = []
    placed = False
    for source in element.provenance.sources:
        named = _cites(source, drawn) and source.document_id in withheld
        if not named and source.document_id != placeholder:
            sources.append(source)
        elif not placed:
            sources.append(
                SourceRef(document_id=placeholder, locator=BOARD_SOURCE_LOCATOR, excerpt_hash="")
            )
            placed = True
    update: dict[str, object] = {}
    if drawn.source_document in withheld:
        update["source_document"] = None
        if not (drawn.source_note and drawn.source_note.strip()):
            update["source_note"] = None
    provenance = element.provenance.model_copy(
        update={"sources": sources, "drawn": drawn.model_copy(update=update)}
    )
    return element.model_copy(update={"provenance": provenance})


def is_gazetteer_held(node: Node) -> bool:
    """A gazetteer's place: a case's own copy of one (`provenance.gazetteer`, ADR-147 Amendment 2,
    the owner's ruling 6), keyed on the copy's provenance, or the place itself in a gazetteer
    dataset (`gazetteer-*`, Amendment 1)."""
    return node.provenance.gazetteer is not None or any(
        d.startswith(GAZETTEER_DATASET_PREFIX) for d in node.datasets
    )


def _gazetteer_identifiers_withheld[Element: (Node, Edge)](
    element: Element, principal: Principal
) -> Element:
    """ADR-147 Amendment 1 (rule 7, the orchestrator's ruling of 9 November 2026): a gazetteer's
    place (a node in a `gazetteer-*` dataset, or a case's copy of one: `is_gazetteer_held`) comes to
    a request reader without its gazetteer's own
    identifiers (`osm_id`, `uprn`, …), which are source-system identifiers. Amendment 3: every
    other node comes without the six only a gazetteer carries (`GAZETTEER_ONLY_IDENTIFIERS`), and
    keeps a `uprn`, which is a case's own. A case that adds the
    gazetteer reads its places through search, expansion and every other node read, all of which
    pass here. The Conduit's own work (`datasets is None`: resolution) keeps them, and so does a
    read inside `sources_in_full`: a read written back, and a gazetteer load, which reads its places
    whole (`load_gazetteer`). A rebuild matches a place by its `osm_id` inside the store anyway."""
    if principal.datasets is None or not isinstance(element, Node):
        return element
    # ADR-147 Amendment 3 (CARRIES row 23, the strict reading): the six only a gazetteer carries
    # leave every node, whatever dataset it is in, as a gazetteer loaded through the Studio sits in
    # a case's own dataset unmarked; a gazetteer's place loses `uprn` too, a case's own keeps it.
    withheld = (
        GAZETTEER_SOURCE_IDENTIFIERS if is_gazetteer_held(element) else GAZETTEER_ONLY_IDENTIFIERS
    )
    if not any(name in element.properties for name in withheld):
        return element
    kept = {k: v for k, v in element.properties.items() if k not in withheld}
    return element.model_copy(update={"properties": kept})


def _board_as_known[Element: (Node, Edge)](element: Element, principal: Principal) -> Element:
    """ADR-143 decision 4's board, as `principal` may know it (rule 3; the orchestrator's review of
    L3.3): a drawn element's `board_id` is kept for its author alone. Only a board's creator draws
    on it, so its author made the board; to anyone else it is given empty, so the id of a private
    board tells no other member of the case it exists. A shared board's id is not needed to read
    what was drawn: the board routes list the boards a reader may open. Every read path is sent
    elements through here: the adapter's serialisation and the working set's projection."""
    drawn = element.provenance.drawn
    if drawn is None or drawn.asserted_by == principal.id or not drawn.board_id:
        return element
    provenance = element.provenance.model_copy(
        update={"drawn": drawn.model_copy(update={"board_id": ""})}
    )
    return element.model_copy(update={"provenance": provenance})
