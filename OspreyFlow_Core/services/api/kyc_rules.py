"""The KYC gate as rules (`06_DECISIONS.md` ADR-109 phase F, ruling 6; the KYC addendum's
Components 6 and 7): three typologies judged over the customers a load created, at the trigger
point the rule declares — so "halting onboarding" is a pre-commit rule's alert, raised with the
load, in the case team's queue (OspreyFlow activates no accounts).

- **`kyc_screening`** — each new person or organisation's name screened against the deployment's
  screening lists (`screening.py`), and, for an organisation, each natural person who ultimately
  owns at least the rule's threshold of it or controls it (`ComputePort.ownership`, phase C). A hit
  writes the listed party (asserted: the list says so) and a scored `SAME_AS` from the customer to
  it (`inferred`: that they are the same is a suggestion, rule 5; rule 6 — never a merge).
- **`shared_attributes`** — a new customer's phone, email, IP address or handle already used by at
  least the rule's number of other customers (a synthetic identity's tell).
- **`document_verification`** — a new customer with no valid verifying document: none at all, or
  each one expired or marked fraudulent. `document_state` is the one definition of "valid", read by
  the KYC status too, so a status and an alert never disagree.

**What is judged, and as whom.** The load's own writes are judged from what the engine wrote
(a pre-commit rule cannot read the open transaction back), filtered by the deployer's access
(`handling_readable`, rule 3); everything already in the store is read through `GraphPort` as the
deployer. A customer the deployer cannot read is not judged, so no alert discloses it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

from conduit_common.identity import new_edge_id, new_node_id
from ontology.handling import HandlingScheme, merge_handling
from ports.compute import ComputePort
from ports.graph import GraphPort
from schemas.compute import OwnershipLink, OwnershipRequest, OwnershipTrace, StructureNode
from schemas.domain import (
    DocumentVerificationParams,
    EdgeWrite,
    ExpandRequest,
    Handling,
    KycScreeningParams,
    Node,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SharedAttributesParams,
    SourceRef,
    TypologyRule,
)

from .ownership import OWNERSHIP_EDGE_TYPES, read_structure
from .rule_evaluation import Finding, handling_readable
from .screening import ScreeningHit, ScreeningListStore, screen

CUSTOMER_TYPES = ("Person", "Organisation")

Written = Sequence[NodeWrite | EdgeWrite]
Party = Node | NodeWrite


@dataclass(frozen=True)
class KycContext:
    graph: GraphPort
    scheme: HandlingScheme
    screening: ScreeningListStore | None
    compute: ComputePort | None
    today: date


# --- what a party is called, and what a document says ------------------------


def party_name(party: Party) -> str:
    props = party.properties
    if party.type == "Person":
        given = str(props.get("given_names") or "").strip()
        family = str(props.get("family_name") or "").strip()
        return f"{given} {family}".strip() or party.id
    return str(props.get("name") or props.get("value_normalised") or party.id)


def _date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def document_state(document: Party, today: date) -> str:
    """`valid`, `expired` or `fraudulent` — the one definition both the gate and the KYC status
    read. Marked fraudulent wins over anything; a document with no expiry does not expire."""
    props = document.properties
    if props.get("fraudulent") is True:
        return "fraudulent"
    expires = _date(props.get("expires_on"))
    if expires is not None and expires < today:
        return "expired"
    return "valid"


def _document_words(document: Party, state: str) -> str:
    kind = str(document.properties.get("document_kind") or "document").replace("_", " ")
    if state == "expired":
        return f"{kind} expired on {_date(document.properties.get('expires_on'))}"
    if state == "fraudulent":
        return f"{kind} marked fraudulent"
    return kind


# --- the load's own writes, as the deployer may read them ---------------------


def customers_in(written: Written, scheme: HandlingScheme, deployer: Principal) -> list[NodeWrite]:
    """New persons and organisations the deployer may read, not themselves a screening list's
    entries."""
    return [
        w
        for w in written
        if isinstance(w, NodeWrite)
        and w.type in CUSTOMER_TYPES
        and not w.properties.get("listing")
        and handling_readable(scheme, deployer, w.handling)
    ]


def _edges(written: Written, scheme: HandlingScheme, deployer: Principal) -> list[EdgeWrite]:
    return [
        w
        for w in written
        if isinstance(w, EdgeWrite) and handling_readable(scheme, deployer, w.handling)
    ]


def _nodes(written: Written, scheme: HandlingScheme, deployer: Principal) -> dict[str, NodeWrite]:
    return {
        w.id: w
        for w in written
        if isinstance(w, NodeWrite) and handling_readable(scheme, deployer, w.handling)
    }


async def _party(
    node_id: str, new: dict[str, NodeWrite], ctx: KycContext, deployer: Principal
) -> Party | None:
    return new.get(node_id) or await ctx.graph.get_node(node_id, deployer)


def customer_rows(customers: Sequence[NodeWrite]) -> list[int]:
    """The source rows that created these customers (`row N` in their provenance), for a failing
    pre-commit rule to hold."""
    rows: set[int] = set()
    for customer in customers:
        for source in customer.provenance.sources:
            locator = source.locator
            if locator.startswith("row ") and locator[4:].isdigit():
                rows.add(int(locator[4:]))
    return sorted(rows)


# --- screening ----------------------------------------------------------------


def _listed_write(hit: ScreeningHit, deployer: Principal, now: datetime) -> NodeWrite:
    entry = hit.entry
    if entry.entity_type == "Person":
        family, _, given = entry.name.partition(",")
        if not given:
            *first, last = entry.name.split() or [entry.name]
            family, given = last, " ".join(first)
        properties: dict[str, object] = {
            "family_name": family.strip().title(),
            "given_names": given.strip(),
        }
        if entry.date_of_birth:
            properties["date_of_birth"] = entry.date_of_birth.isoformat()
    else:
        properties = {"name": entry.name}
        if entry.country:
            properties["country"] = entry.country
    properties.update({"listing": entry.listing, "list_name": entry.list_name})
    return NodeWrite(
        id=new_node_id(),
        type=entry.entity_type,
        properties=properties,
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id=entry.list_name, locator=entry.id, excerpt_hash="")],
            first_seen=now,
        ),
        handling=Handling(
            classification="OFFICIAL",
            handling_code="P",
            originator=deployer.org_unit,
            owning_unit=deployer.org_unit,
        ),
        created_by=deployer.id,
        created_at=now,
    )


async def _listed_party(
    hit: ScreeningHit, ctx: KycContext, deployer: Principal, now: datetime
) -> tuple[str, NodeWrite | None, Handling]:
    """The listed party's node: the one already written for this entry if the deployer can read
    it, else a new one to write with the alert."""
    candidate = _listed_write(hit, deployer, now)
    key = "family_name" if hit.entry.entity_type == "Person" else "name"
    found = await ctx.graph.find_node(
        hit.entry.entity_type, key, str(candidate.properties[key]), deployer
    )
    if found is not None and found.properties.get("list_name") == hit.entry.list_name:
        return found.id, None, found.handling
    return candidate.id, candidate, candidate.handling


_LISTING_WORDS = {"sanction": "a sanctions list", "pep": "a politically exposed persons list",
                  "adverse_media": "an adverse-media list"}  # fmt: skip


async def _screening_finding(
    rule: TypologyRule,
    deployer: Principal,
    customer: Party,
    screened: Party,
    hit: ScreeningHit,
    ctx: KycContext,
    *,
    chain_words: str = "",
    chain_nodes: Sequence[str] = (),
    chain_edges: Sequence[str] = (),
) -> Finding:
    now = datetime.now(UTC)
    listed_id, listed_write, listed_handling = await _listed_party(hit, ctx, deployer, now)
    same_as = EdgeWrite(
        id=new_edge_id(),
        type="SAME_AS",
        source=screened.id,
        target=listed_id,
        properties={"score": hit.score, "model_version": f"screening:{hit.entry.list_name}"},
        basis="probabilistic",
        provenance=Provenance(
            state=ProvenanceState.INFERRED,
            sources=[
                SourceRef(document_id=hit.entry.list_name, locator=hit.entry.id, excerpt_hash="")
            ],
            extracted_by=f"screening:{hit.entry.list_name}",
            extraction_confidence=min(hit.score, 1.0),
            first_seen=now,
        ),
        handling=merge_handling(screened.handling, listed_handling, ctx.scheme),
        created_by=deployer.id,
        created_at=now,
    )
    who = party_name(screened)
    words = (
        f"{party_name(customer)}{chain_words}: {who} matches “{hit.entry.name}” on "
        f"{_LISTING_WORDS.get(hit.entry.listing, 'a screening list')} ({hit.entry.list_name}), "
        f"score {hit.score:.2f} — a suggestion to confirm, not a finding"
    )
    return Finding(
        rule=rule,
        deployer=deployer,
        typology="kyc_screening",
        subject=customer.id,
        refs=(screened.id, hit.entry.id),
        words=words,
        node_ids=sorted({customer.id, screened.id, listed_id, *chain_nodes}),
        edge_ids=sorted({same_as.id, *chain_edges}),
        pending=tuple(w for w in (listed_write, same_as) if w is not None),
    )


async def _owners(
    customer: NodeWrite, written: Written, ctx: KycContext, deployer: Principal, threshold: float
) -> tuple[OwnershipTrace, dict[str, Party], dict[str, OwnershipLink]]:
    """The customer's ownership trace, from the load's own ownership links and, above any owner
    already in the store, the stored structure read as the deployer."""
    assert ctx.compute is not None
    new = _nodes(written, ctx.scheme, deployer)
    links: dict[str, OwnershipLink] = {}
    parties: dict[str, Party] = {customer.id: customer}
    frontier = [customer.id]
    seen = {customer.id}
    while frontier:
        target = frontier.pop()
        for edge in _edges(written, ctx.scheme, deployer):
            if edge.target != target or edge.type not in OWNERSHIP_EDGE_TYPES:
                continue
            links[edge.id] = _link(edge.id, edge.type, edge.source, edge.target, edge.properties)
            if edge.source in seen:
                continue
            seen.add(edge.source)
            owner = await _party(edge.source, new, ctx, deployer)
            if owner is None:
                continue
            parties[owner.id] = owner
            if owner.id in new:
                frontier.append(owner.id)
            else:
                stored_nodes, stored_edges = await read_structure(
                    ctx.graph, owner.id, deployer, max_depth=10
                )
                parties.update(stored_nodes)
                for stored in stored_edges.values():
                    links[stored.id] = _link(
                        stored.id, stored.type, stored.source, stored.target, stored.properties
                    )
    trace = await ctx.compute.ownership(
        OwnershipRequest(
            target=customer.id,
            nodes=[StructureNode(id=p.id, type=p.type) for p in parties.values()],
            links=[k for k in links.values() if k.source in parties and k.target in parties],
            threshold=threshold,
        )
    )
    return trace, parties, links


def _link(link_id: str, edge_type: str, source: str, target: str, props: dict) -> OwnershipLink:  # type: ignore[type-arg]
    percent = props.get("percent")
    try:
        value = None if edge_type == "CONTROLS" or percent is None else float(percent)
    except (TypeError, ValueError):
        value = None
    return OwnershipLink(
        id=link_id,
        source=source,
        target=target,
        kind="controls" if edge_type == "CONTROLS" else "owns",
        percent=value if value is None or 0 <= value <= 100 else None,
    )


async def judge_screening(
    rule: TypologyRule, deployer: Principal, written: Written, ctx: KycContext
) -> list[Finding]:
    params = rule.params
    assert isinstance(params, KycScreeningParams)
    if ctx.screening is None:
        raise RuntimeError("this deployment has no screening list store")
    entries = {t: await ctx.screening.entries(t) for t in CUSTOMER_TYPES}
    findings: list[Finding] = []
    for customer in customers_in(written, ctx.scheme, deployer):
        dob = _date(customer.properties.get("date_of_birth"))
        for hit in screen(
            party_name(customer), dob, entries[customer.type], min_score=params.min_score
        ):
            findings.append(await _screening_finding(rule, deployer, customer, customer, hit, ctx))
        if customer.type != "Organisation" or not params.screen_owners or ctx.compute is None:
            continue
        trace, parties, links = await _owners(
            customer, written, ctx, deployer, params.owner_threshold
        )
        for owner in trace.owners:
            party = parties.get(owner.node_id)
            if party is None or party.type != "Person" or not owner.beneficial_owner:
                continue
            owner_dob = _date(party.properties.get("date_of_birth"))
            chain_edges = sorted({e for p in owner.paths for e in p.link_ids})
            chain_nodes = sorted(
                {links[e].source for e in chain_edges} | {links[e].target for e in chain_edges}
            )
            share = f"{owner.cumulative_percent:.4g}%" + (
                ", with control" if owner.controls else ""
            )
            for hit in screen(
                party_name(party), owner_dob, entries["Person"], min_score=params.min_score
            ):
                findings.append(
                    await _screening_finding(
                        rule,
                        deployer,
                        customer,
                        party,
                        hit,
                        ctx,
                        chain_words=f" is ultimately owned {share} by {party_name(party)}",
                        chain_nodes=chain_nodes,
                        chain_edges=chain_edges,
                    )  # fmt: skip
                )
    return findings


# --- shared attributes ----------------------------------------------------------


async def judge_shared_attributes(
    rule: TypologyRule, deployer: Principal, written: Written, ctx: KycContext
) -> list[Finding]:
    params = rule.params
    assert isinstance(params, SharedAttributesParams)
    new = _nodes(written, ctx.scheme, deployer)
    edges = _edges(written, ctx.scheme, deployer)
    customers = customers_in(written, ctx.scheme, deployer)
    findings: list[Finding] = []
    for customer in customers:
        for uses in (e for e in edges if e.type == "USES" and e.source == customer.id):
            endpoint = await _party(uses.target, new, ctx, deployer)
            if endpoint is None or endpoint.type != "Endpoint":
                continue
            kind = endpoint.properties.get("endpoint_kind")
            if kind not in params.kinds:
                continue
            others: dict[str, Party] = {}
            other_edges: set[str] = set()
            stored = await ctx.graph.expand(
                ExpandRequest(node_ids=[endpoint.id], direction="in", edge_types=["USES"]), deployer
            )
            for node in stored.nodes:
                if node.type in CUSTOMER_TYPES and node.id != customer.id:
                    others[node.id] = node
            other_edges.update(e.id for e in stored.edges if e.source in others)
            for edge in edges:  # other customers in this same load
                if (
                    edge.type == "USES"
                    and edge.target == endpoint.id
                    and edge.source != customer.id
                ):
                    other = new.get(edge.source)
                    if other is not None and other.type in CUSTOMER_TYPES:
                        others[other.id] = other
                        other_edges.add(edge.id)
            if len(others) < params.min_others:
                continue
            value = endpoint.properties.get("value_normalised") or endpoint.id
            named = ", ".join(sorted(party_name(o) for o in others.values()))
            findings.append(
                Finding(
                    rule=rule,
                    deployer=deployer,
                    typology="shared_attributes",
                    subject=customer.id,
                    refs=(endpoint.id, *sorted(others)),
                    words=(
                        f"{party_name(customer)} uses {kind} {value}, already used by "
                        f"{len(others)} other customer(s): {named}"
                    ),
                    node_ids=sorted({customer.id, endpoint.id, *others}),
                    edge_ids=sorted({uses.id, *other_edges}),
                )
            )
    return findings


# --- documents ------------------------------------------------------------------


async def judge_documents(
    rule: TypologyRule, deployer: Principal, written: Written, ctx: KycContext
) -> list[Finding]:
    assert isinstance(rule.params, DocumentVerificationParams)
    new = _nodes(written, ctx.scheme, deployer)
    edges = _edges(written, ctx.scheme, deployer)
    findings: list[Finding] = []
    for customer in customers_in(written, ctx.scheme, deployer):
        verifying = [e for e in edges if e.type == "VERIFIED_BY" and e.source == customer.id]
        documents: list[tuple[EdgeWrite, Party, str]] = []
        for edge in verifying:
            document = await _party(edge.target, new, ctx, deployer)
            if document is not None:
                documents.append((edge, document, document_state(document, ctx.today)))
        if any(state == "valid" for _, _, state in documents):
            continue
        detail = "; ".join(_document_words(d, s) for _, d, s in documents) or "none on record"
        findings.append(
            Finding(
                rule=rule,
                deployer=deployer,
                typology="document_verification",
                subject=customer.id,
                refs=(customer.id, *sorted(f"{d.id}:{s}" for _, d, s in documents)),
                words=f"{party_name(customer)} has no valid verifying document: {detail}",
                node_ids=sorted({customer.id, *(d.id for _, d, _ in documents)}),
                edge_ids=sorted(e.id for e, _, _ in documents),
            )
        )
    return findings


JUDGES = {
    "kyc_screening": judge_screening,
    "shared_attributes": judge_shared_attributes,
    "document_verification": judge_documents,
}


async def judge_kyc(
    rule: TypologyRule, deployer: Principal, written: Written, ctx: KycContext
) -> list[Finding]:
    return await JUDGES[rule.params.typology](rule, deployer, written, ctx)


__all__ = [
    "CUSTOMER_TYPES",
    "KycContext",
    "customer_rows",
    "customers_in",
    "document_state",
    "judge_kyc",
    "party_name",
]


async def judge_lapsed(
    rule: TypologyRule,
    deployer: Principal,
    customer_id: str,
    lapsed_document_ids: Sequence[str],
    ctx: KycContext,
) -> list[Finding]:
    """The daily sweep's question (ruling 7): a customer one of whose verifying documents has just
    lapsed — does any valid one remain? Read entirely from the store, as the deployer; a customer
    or document they cannot read is not judged."""
    customer = await ctx.graph.get_node(customer_id, deployer)
    if customer is None or customer.type not in CUSTOMER_TYPES:
        return []
    found = await ctx.graph.expand(
        ExpandRequest(node_ids=[customer.id], direction="out", edge_types=["VERIFIED_BY"]),
        deployer,
    )
    documents = [(d, document_state(d, ctx.today)) for d in found.nodes if d.type == "Document"]
    if any(state == "valid" for _, state in documents):
        return []
    lapsed = [d for d, _ in documents if d.id in lapsed_document_ids]
    if not lapsed:
        return []
    detail = "; ".join(_document_words(d, s) for d, s in documents)
    return [
        Finding(
            rule=rule,
            deployer=deployer,
            typology="document_verification",
            subject=customer.id,
            refs=(customer.id, *sorted(f"lapsed:{d.id}" for d in lapsed)),
            words=(
                f"{party_name(customer)} is no longer verified: {detail} — "
                "no valid verifying document remains; review"
            ),
            node_ids=sorted({customer.id, *(d.id for d, _ in documents)}),
            edge_ids=sorted(e.id for e in found.edges),
        )
    ]
