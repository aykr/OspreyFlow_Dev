"""A customer's KYC status and baseline risk assessment (`06_DECISIONS.md` ADR-109 phase F, rulings
7 and 10; the KYC addendum's Components 6 and 7).

**Computed at each read, never stored.** Status is `verified` while at least one document the
customer is `VERIFIED_BY` is valid (`kyc_rules.document_state`: not marked fraudulent, not past its
expiry) — so it reads *unverified* the moment a document lapses or is marked, with nothing written.
The risk assessment sums weighted factors from `kyc_risk_factors.yaml` (country, industry, a
screening match on the customer or on a beneficial owner, a shared phone or address, an unverified
status) and names each with its words. **As the reader (rule 3):** every fact read through
`GraphPort` with the reader's principal, so a factor resting on something the reader cannot see is
not there for them — the score is the one their visible graph supports.
"""

from __future__ import annotations

from datetime import date
from functools import cache
from pathlib import Path
from typing import Any, Literal

import yaml

from ports.compute import ComputePort
from ports.graph import GraphPort
from schemas.domain import ExpandRequest, KycDocument, KycStatus, Node, Principal, RiskFactor

from .kyc_rules import CUSTOMER_TYPES, document_state, party_name
from .ownership import trace_for
from .suppression import NodeNotVisibleError

_CONFIG = Path(__file__).with_name("kyc_risk_factors.yaml")
_LISTING_WORDS = {"sanction": "a sanctions list", "pep": "a politically exposed persons list",
                  "adverse_media": "an adverse-media list"}  # fmt: skip
SHARED_ATTRIBUTE_OTHERS = 3


class KycNotApplicable(Exception):
    """KYC is about a person or an organisation; this is neither."""


@cache
def risk_config() -> dict[str, Any]:
    raw: dict[str, Any] = yaml.safe_load(_CONFIG.read_text(encoding="utf-8"))
    return raw


async def _neighbours(
    graph: GraphPort, node_id: str, reader: Principal, edge_type: str, direction: str
) -> list[Node]:
    found = await graph.expand(
        ExpandRequest(node_ids=[node_id], edge_types=[edge_type], direction=direction),  # type: ignore[arg-type]
        reader,
    )
    return [n for n in found.nodes if n.id != node_id]


async def _listed(graph: GraphPort, node_id: str, reader: Principal) -> list[Node]:
    return [
        n
        for n in await _neighbours(graph, node_id, reader, "SAME_AS", "both")
        if n.properties.get("listing")
    ]


async def assess(
    graph: GraphPort,
    compute: ComputePort,
    node_id: str,
    reader: Principal,
    *,
    today: date,
) -> KycStatus:
    customer = await graph.get_node(node_id, reader)
    if customer is None:
        raise NodeNotVisibleError(node_id)
    if customer.type not in CUSTOMER_TYPES:
        raise KycNotApplicable(customer.type)
    config = risk_config()
    weights: dict[str, int] = config["weights"]
    factors: list[RiskFactor] = []

    documents = [
        KycDocument(
            node_id=d.id,
            title=d.properties.get("title"),
            document_kind=d.properties.get("document_kind"),
            expires_on=d.properties.get("expires_on"),
            state=document_state(d, today),  # type: ignore[arg-type]
        )
        for d in await _neighbours(graph, customer.id, reader, "VERIFIED_BY", "out")
    ]
    verified = any(d.state == "valid" for d in documents)
    if not verified:
        lapsed = [
            f"{(d.document_kind or 'document').replace('_', ' ')} {d.state}" for d in documents
        ]
        factors.append(
            RiskFactor(
                factor="unverified",
                weight=weights["unverified"],
                words="No valid verifying document" + (f" ({'; '.join(lapsed)})" if lapsed else ""),
            )
        )

    country = str(customer.properties.get("country") or "").upper()
    for level in ("high", "medium"):
        if country and country in config["countries"][level]:
            factors.append(
                RiskFactor(
                    factor=f"country_{level}",
                    weight=weights[f"country_{level}"],
                    words=f"Registered in {country}, a {level}-risk jurisdiction",
                )
            )
            break
    industry = str(customer.properties.get("industry") or "")
    for level in ("high", "medium"):
        if industry and industry in config["industries"][level]:
            factors.append(
                RiskFactor(
                    factor=f"industry_{level}",
                    weight=weights[f"industry_{level}"],
                    words=f"{industry}, a {level}-risk industry",
                )
            )
            break

    for listed in await _listed(graph, customer.id, reader):
        kind = str(listed.properties["listing"])
        factors.append(RiskFactor(
            factor=f"listed_{kind}", weight=weights[f"listed_{kind}"],
            words=f"Possibly {party_name(listed)} on {_LISTING_WORDS.get(kind, 'a list')} "
                  f"({listed.properties.get('list_name')}) — a suggestion to confirm",
        ))  # fmt: skip

    if customer.type == "Organisation":
        view = await trace_for(graph, compute, customer.id, reader)
        names = {n.id: n for n in view.nodes}
        for owner in view.trace.owners:
            party = names.get(owner.node_id)
            if party is None or not owner.beneficial_owner:
                continue
            for listed in await _listed(graph, owner.node_id, reader):
                factors.append(RiskFactor(
                    factor="owner_listed", weight=weights["owner_listed"],
                    words=f"Beneficial owner {party_name(party)} ({owner.cumulative_percent:.4g}%) "
                          f"possibly {party_name(listed)} on "
                          f"{_LISTING_WORDS.get(str(listed.properties['listing']), 'a list')}",
                ))  # fmt: skip

    for endpoint in await _neighbours(graph, customer.id, reader, "USES", "out"):
        if endpoint.type != "Endpoint":
            continue
        others = [
            n for n in await _neighbours(graph, endpoint.id, reader, "USES", "in")
            if n.type in CUSTOMER_TYPES and n.id != customer.id
        ]  # fmt: skip
        if len(others) >= SHARED_ATTRIBUTE_OTHERS:
            factors.append(RiskFactor(
                factor="shared_attribute", weight=weights["shared_attribute"],
                words=f"{endpoint.properties.get('endpoint_kind', 'contact')} "
                      f"{endpoint.properties.get('value_normalised', '')} also used by "
                      f"{len(others)} other customer(s)",
            ))  # fmt: skip

    score = sum(f.weight for f in factors)
    bands = config["bands"]
    band: Literal["low", "medium", "high"] = (
        "high" if score >= bands["high"] else "medium" if score >= bands["medium"] else "low"
    )
    return KycStatus(
        node_id=customer.id,
        name=party_name(customer),
        status="verified" if verified else "unverified",
        documents=documents,
        risk_score=score,
        risk_band=band,
        factors=factors,
        assessed_on=today,
    )


__all__ = ["KycNotApplicable", "assess", "risk_config"]
