"""The `cyber-intrusion` demo pack (`06_DECISIONS.md` ADR-138): a small synthetic STIX 2.1
intrusion.

A fictional threat actor runs a campaign against a fictional water company, using a backdoor and two
command-and-control servers. The pack is a STIX 2.1 bundle — a threat actor, a campaign, a piece of
malware, infrastructure, indicators, observed data, the victim's identity, and the relationships
between them — and the graph the seed writes from it, in the STIX domain pack's types over the POLE
core (`packages/ontology/packs/stix.yaml`).

**Generated, deterministic and owned outright** (ADR-035 §C5). Every identifier is a UUIDv5 under
one fixed namespace and every timestamp is fixed, so `bundle()` is byte-for-byte the same on every
run (the golden test holds its SHA-256). Every address is from the documentation ranges (RFC 5737:
192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24) and every domain under `.example` (RFC 2606), so
nothing here names a real host, and the hashes are digests of the generator's own words, not of any
real file. Nothing is real data (rule 9).

**How STIX maps to the graph** (the pack's own header): SDOs are entity types (`ThreatActor`,
`Campaign`, `Malware`, `Infrastructure`); the victim's `identity` is an `Organisation`; an
`indicator` is a `Document` (its pattern its title) that `INDICATES` what it detects, and the
address or domain it watches for is an `Endpoint` that `INDICATES` the infrastructure;
`observed-data` is a `Document` the observed addresses are `MENTIONED_IN`, and each observed
connection is a temporal `COMMUNICATED_WITH` link from the victim's host to the server it reached.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from schemas.domain import (
    AuditStub,
    Edge,
    Handling,
    Interval,
    Node,
    Provenance,
    ProvenanceState,
    SourceRef,
)

#: Fixed, so every identifier is the same on every run.
NAMESPACE = uuid.UUID("5d1c8f3e-3b2a-5c7e-9a40-6f1b2d3c4e5f")
SOURCE = "cyber-intrusion-generator"
CREATED = "2026-03-02T09:00:00.000Z"
_CREATED_AT = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)
_HANDLING = Handling(
    classification="OFFICIAL",
    handling_code="P",
    originator="cyber-intrusion",
    owning_unit="cyber-intrusion",
)

ACTOR = "Harbour Kestrel"
CAMPAIGN = "Operation Tidewater"
MALWARE = "BRINELOADER"
VICTIM = "Northmere Water Services (fictional)"
#: The two command-and-control servers: (name, address, domain).
SERVERS = (
    ("Tidewater C2 one", "203.0.113.47", "update-check.northmere-water.example"),
    ("Tidewater C2 two", "198.51.100.23", "cdn-sync.tidewater.example"),
)
#: The victim's hosts seen talking to them: (host address, server index, when).
OBSERVATIONS = (
    ("192.0.2.14", 0, "2026-03-03T02:14:00Z"),
    ("192.0.2.14", 0, "2026-03-04T02:16:00Z"),
    ("192.0.2.31", 1, "2026-03-05T23:40:00Z"),
    ("192.0.2.57", 1, "2026-03-06T01:05:00Z"),
)


def stix_id(kind: str, key: str) -> str:
    return f"{kind}--{uuid.uuid5(NAMESPACE, f'{kind}:{key}')}"


def _sha256_of(words: str) -> str:
    """A digest of the generator's own words: shaped like a file hash, of no real file."""
    return hashlib.sha256(f"{SOURCE}:{words}".encode()).hexdigest()


def _sdo(kind: str, key: str, **fields: Any) -> dict[str, Any]:
    return {
        "type": kind,
        "spec_version": "2.1",
        "id": stix_id(kind, key),
        "created": CREATED,
        "modified": CREATED,
        **fields,
    }


def _relationship(kind: str, source: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    key = f"{kind}:{source['id']}->{target['id']}"
    return _sdo(
        "relationship", key,
        relationship_type=kind, source_ref=source["id"], target_ref=target["id"],
    )  # fmt: skip


def stix_objects() -> list[dict[str, Any]]:
    """Every object of the bundle, in a fixed order."""
    actor = _sdo(
        "threat-actor", ACTOR, name=ACTOR, threat_actor_types=["criminal"],
        sophistication="intermediate", primary_motivation="personal-gain",
        description="A fictional intrusion set, invented for the OspreyFlow demonstration.",
    )  # fmt: skip
    campaign = _sdo(
        "campaign", CAMPAIGN, name=CAMPAIGN, objective="Access to operational technology",
        first_seen="2026-03-03T02:14:00Z", last_seen="2026-03-06T01:05:00Z",
    )  # fmt: skip
    malware = _sdo(
        "malware", MALWARE, name=MALWARE, is_family=True,
        malware_types=["backdoor", "remote-access-trojan"],
    )  # fmt: skip
    victim = _sdo("identity", VICTIM, name=VICTIM, identity_class="organization",
                  sectors=["utilities"])  # fmt: skip
    servers = [
        _sdo("infrastructure", name, name=name, infrastructure_types=["command-and-control"])
        for name, _address, _domain in SERVERS
    ]
    objects: list[dict[str, Any]] = [actor, campaign, malware, victim, *servers]
    relationships = [
        _relationship("attributed-to", campaign, actor),
        _relationship("uses", actor, malware),
        _relationship("uses", campaign, malware),
        _relationship("targets", campaign, victim),
        *(_relationship("uses", campaign, server) for server in servers),
    ]
    hash_indicator = _sdo(
        "indicator", "brineloader-sha256", name=f"{MALWARE} loader",
        pattern=f"[file:hashes.'SHA-256' = '{_sha256_of(MALWARE)}']", pattern_type="stix",
        indicator_types=["malicious-activity"], valid_from=CREATED,
    )  # fmt: skip
    objects.append(hash_indicator)
    relationships.append(_relationship("indicates", hash_indicator, malware))
    for (name, address, domain), server in zip(SERVERS, servers, strict=True):
        for kind, value, pattern in (
            ("ipv4-addr", address, f"[ipv4-addr:value = '{address}']"),
            ("domain-name", domain, f"[domain-name:value = '{domain}']"),
        ):
            indicator = _sdo(
                "indicator", f"{kind}:{value}", name=f"{name}: {value}", pattern=pattern,
                pattern_type="stix", indicator_types=["malicious-activity"], valid_from=CREATED,
            )  # fmt: skip
            objects.append(indicator)
            relationships.append(_relationship("indicates", indicator, server))
    for index, (host, server_index, when) in enumerate(OBSERVATIONS):
        server_address = SERVERS[server_index][1]
        source = {"type": "ipv4-addr", "spec_version": "2.1",
                  "id": stix_id("ipv4-addr", host), "value": host}  # fmt: skip
        target = {"type": "ipv4-addr", "spec_version": "2.1",
                  "id": stix_id("ipv4-addr", server_address), "value": server_address}  # fmt: skip
        traffic = {
            "type": "network-traffic", "spec_version": "2.1",
            "id": stix_id("network-traffic", f"{index}:{host}->{server_address}"),
            "src_ref": source["id"], "dst_ref": target["id"], "protocols": ["ipv4", "tcp", "https"],
        }  # fmt: skip
        objects.append(
            _sdo(
                "observed-data", f"{index}:{host}", first_observed=when, last_observed=when,
                number_observed=1, object_refs=[source["id"], target["id"], traffic["id"]],
            )  # fmt: skip
        )
        for sco in (source, target, traffic):
            if sco not in objects:
                objects.append(sco)
    return objects + relationships


def bundle() -> dict[str, Any]:
    return {"type": "bundle", "id": stix_id("bundle", CAMPAIGN), "objects": stix_objects()}


def bundle_json() -> str:
    """The bundle as JSON, keys sorted: what the golden test hashes and the seed reports."""
    return json.dumps(bundle(), sort_keys=True, indent=2, ensure_ascii=False) + "\n"


# --- The graph ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class CyberGraph:
    nodes: list[Node]
    edges: list[Edge]


def _provenance(locator: str) -> Provenance:
    return Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id=SOURCE, locator=locator, excerpt_hash="")],
        first_seen=_CREATED_AT,
    )


def _audit() -> AuditStub:
    return AuditStub(created_at=_CREATED_AT, created_by=SOURCE)


def node_id(stix: str) -> str:
    return f"cyber-{stix.split('--', 1)[1]}"


def _node(kind: str, stix: str, properties: dict[str, Any]) -> Node:
    return Node(
        id=node_id(stix), type=kind, properties=properties, provenance=_provenance(stix),
        handling=_HANDLING, audit=_audit(),
    )  # fmt: skip


def _edge(kind: str, source: str, target: str, at: str | None = None) -> Edge:
    interval = (
        Interval(valid_from=datetime.fromisoformat(at.replace("Z", "+00:00"))) if at else None
    )
    key = f"{kind}:{source}->{target}:{at or ''}"
    return Edge(
        id=f"cyber-edge-{uuid.uuid5(NAMESPACE, key)}", type=kind, source=source, target=target,
        interval=interval, provenance=_provenance(key), handling=_HANDLING, audit=_audit(),
    )  # fmt: skip


def _endpoint(value: str, kind: str) -> Node:
    return _node(
        "Endpoint", stix_id("endpoint", value),
        {"value_raw": value, "value_normalised": value, "endpoint_kind": kind},
    )  # fmt: skip


def graph() -> CyberGraph:
    """The bundle as the graph the seed writes (the module's docstring says how)."""
    objects = {o["id"]: o for o in stix_objects()}
    nodes: dict[str, Node] = {}
    edges: list[Edge] = []

    def add(node: Node) -> str:
        nodes.setdefault(node.id, node)
        return node.id

    types = {"threat-actor": "ThreatActor", "campaign": "Campaign", "malware": "Malware",
             "infrastructure": "Infrastructure", "identity": "Organisation"}  # fmt: skip
    for stix, obj in objects.items():
        kind = types.get(obj["type"])
        if kind is None:
            continue
        properties: dict[str, Any] = {"name": obj["name"]}
        if kind == "ThreatActor":
            properties |= {"sophistication": obj["sophistication"],
                           "motivation": obj["primary_motivation"]}  # fmt: skip
        if kind == "Campaign":
            properties["objective"] = obj["objective"]
        if kind == "Malware":
            properties["malware_types"] = obj["malware_types"]
        if kind == "Infrastructure":
            properties["infrastructure_types"] = obj["infrastructure_types"]
        add(_node(kind, stix, properties))
    server_ids = [node_id(stix_id("infrastructure", name)) for name, _a, _d in SERVERS]
    for (_name, address, domain), server in zip(SERVERS, server_ids, strict=True):
        for value, kind in ((address, "ip"), (domain, "handle")):
            edges.append(_edge("INDICATES", add(_endpoint(value, kind)), server))
    for stix, obj in objects.items():
        if obj["type"] == "indicator":
            document = add(_node("Document", stix, {"title": obj["pattern"]}))
            for rel in objects.values():
                if rel["type"] == "relationship" and rel["source_ref"] == stix:
                    edges.append(_edge("INDICATES", document, node_id(rel["target_ref"])))
        if obj["type"] == "relationship" and obj["source_ref"].split("--")[0] != "indicator":
            kind = {"attributed-to": "ATTRIBUTED_TO", "uses": "USES", "targets": "TARGETS"}[
                obj["relationship_type"]
            ]
            edges.append(_edge(kind, node_id(obj["source_ref"]), node_id(obj["target_ref"])))
    malware = node_id(stix_id("malware", MALWARE))
    for index, (host, server_index, when) in enumerate(OBSERVATIONS):
        observed = objects[stix_id("observed-data", f"{index}:{host}")]
        document = add(
            _node("Document", observed["id"],
                  {"title": f"Observed data: {host} to {SERVERS[server_index][1]}",
                   "sent_at": when})  # fmt: skip
        )
        victim_host = add(_endpoint(host, "ip"))
        server_address = add(_endpoint(SERVERS[server_index][1], "ip"))
        edges.append(_edge("MENTIONED_IN", victim_host, document))
        edges.append(_edge("MENTIONED_IN", server_address, document))
        edges.append(_edge("COMMUNICATED_WITH", victim_host, server_address, at=when))
        compromised = _edge("COMPROMISES", malware, victim_host)
        if all(e.id != compromised.id for e in edges):
            edges.append(compromised)
    return CyberGraph(nodes=list(nodes.values()), edges=edges)
