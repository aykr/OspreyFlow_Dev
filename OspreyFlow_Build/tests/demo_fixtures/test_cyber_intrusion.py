"""Golden tests for the `cyber-intrusion` demo pack (ADR-138): a synthetic STIX 2.1 intrusion.

What a mistake would do, and the case that catches it (rule 12):
- a generator that changes between runs (a random id, a clock) — `test_the_bundle_is_the_same_on_every_run`;
- an object that is not well-formed STIX 2.1, or a reference to nothing —
  `test_every_object_is_stix_2_1_and_every_reference_resolves`;
- a real address or domain in the demo — `test_every_address_and_domain_is_reserved_for_documentation`;
- a graph the store would refuse (a type or link end the ontology does not have) —
  `test_the_seeds_writes_are_valid_against_the_deployment_ontology`;
- the case not set to STIX — `test_the_pack_is_registered_and_its_case_is_stix`.
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import re

from scripts import demo_packs, seed_cyber_intrusion
from scripts.demo_registry import REGISTRY
from scripts.seed_internal import DATASETS

from demo_fixtures import cyber_intrusion
from demo_fixtures.datasets import CYBER_INTRUSION
from ontology.packs import load_deployment_ontology
from tests.ingest.recipe_test_support import ValidatingGraph

#: The bundle's SHA-256. A change to the pack is a change to this line, made on purpose.
BUNDLE_SHA256 = "52e10c9aac98d8095face592a911fb7f1023e117d18d0ce82a059b0e33f99672"
_ID = re.compile(r"^[a-z0-9-]+--[0-9a-f]{8}-[0-9a-f]{4}-5[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_SCO = {"ipv4-addr", "network-traffic"}


def test_the_bundle_is_the_same_on_every_run() -> None:
    first = cyber_intrusion.bundle_json()
    assert first == cyber_intrusion.bundle_json()
    assert hashlib.sha256(first.encode()).hexdigest() == BUNDLE_SHA256
    assert [n.id for n in cyber_intrusion.graph().nodes] == [
        n.id for n in cyber_intrusion.graph().nodes
    ]


def test_every_object_is_stix_2_1_and_every_reference_resolves() -> None:
    bundle = cyber_intrusion.bundle()
    assert bundle["type"] == "bundle" and _ID.match(bundle["id"])
    objects = bundle["objects"]
    ids = [o["id"] for o in objects]
    assert len(ids) == len(set(ids))
    kinds = {o["type"] for o in objects}
    assert {"threat-actor", "campaign", "malware", "infrastructure", "indicator",
            "observed-data", "identity", "relationship"} <= kinds  # fmt: skip
    for obj in objects:
        assert obj["spec_version"] == "2.1" and _ID.match(obj["id"])
        assert obj["id"].startswith(obj["type"] + "--")
        if obj["type"] not in _SCO:
            assert obj["created"] == obj["modified"] == cyber_intrusion.CREATED
        for ref in ("source_ref", "target_ref", "src_ref", "dst_ref"):
            if ref in obj:
                assert obj[ref] in ids
        for ref in obj.get("object_refs", []):
            assert ref in ids
        if obj["type"] == "indicator":
            assert obj["pattern_type"] == "stix" and obj["pattern"].startswith("[")


def test_every_address_and_domain_is_reserved_for_documentation() -> None:
    documentation = [ipaddress.ip_network(n) for n in
                     ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")]  # fmt: skip
    text = cyber_intrusion.bundle_json()
    for address in set(re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", text)):
        assert any(ipaddress.ip_address(address) in net for net in documentation), address
    for domain in set(re.findall(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+\.example\b|\b[a-z-]+\.(?:com|net|org|uk)\b", text)):
        assert domain.endswith(".example"), domain


def test_the_seeds_writes_are_valid_against_the_deployment_ontology() -> None:
    graph = ValidatingGraph(load_deployment_ontology())

    async def write() -> None:
        tx = await graph.begin_transaction()
        await graph.upsert_nodes(seed_cyber_intrusion.node_writes("load-1"), tx)  # type: ignore[arg-type]
        await graph.upsert_edges(seed_cyber_intrusion.edge_writes("load-1"), tx)  # type: ignore[arg-type]
        await graph.commit_transaction(tx)

    asyncio.run(write())
    types = {n.type for n in graph.nodes.values()}
    assert {"ThreatActor", "Campaign", "Malware", "Infrastructure", "Organisation",
            "Endpoint", "Document"} == types  # fmt: skip
    links = {e.type for e in graph.edges}
    assert {"ATTRIBUTED_TO", "USES", "TARGETS", "INDICATES", "COMPROMISES", "MENTIONED_IN",
            "COMMUNICATED_WITH"} == links  # fmt: skip
    timed = [e for e in graph.edges if e.type == "COMMUNICATED_WITH"]
    assert len(timed) == len(cyber_intrusion.OBSERVATIONS) and all(e.interval for e in timed)


def test_the_pack_is_registered_and_its_case_is_stix() -> None:
    assert CYBER_INTRUSION.domains == ("stix",)
    (manifest,) = [m for m in REGISTRY if m.id == "cyber-intrusion"]
    assert manifest.is_shipped and manifest.is_seeded
    assert manifest.seed_module == "scripts.seed_cyber_intrusion"
    assert DATASETS["cyber-intrusion"].script == "scripts.seed_cyber_intrusion"
    pack = demo_packs.pack("cyber-intrusion")
    assert pack.case_name == DATASETS["cyber-intrusion"].case_name == CYBER_INTRUSION.case_name
