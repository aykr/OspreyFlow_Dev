"""Golden tests for the VAST Challenge catalogue's recipes (ADR-138 decision 3).

Each recipe is run through the Ingest Studio's own engine (`load_with_rules`, what
`scripts.seed_public` runs) against the graph stand-in that merges as the store does, with the
deployment ontology, on a tiny **synthetic** file written here in the challenge's documented column
shape. No VAST data is downloaded, committed or read (rule 9; ADR-026: the published files are never
admitted into this repository).

- a recipe the engine refuses, or one that drops rows — each test's `rejections == []`;
- addresses or phones loaded as the wrong kind, or calls without their time —
  `test_the_firewall_log_loads_each_connection_between_two_ip_endpoints`,
  `test_the_call_records_load_each_call_with_its_time_and_duration`;
- a `yyyymmdd` date read day first (1 June read as 6 January) —
  `test_the_call_records_load_each_call_with_its_time_and_duration`.
"""

from __future__ import annotations

import asyncio
import csv
import io
from datetime import UTC, datetime

from scripts import public_dataset
from services.api.studio_publish import load_with_rules

from adapters.media_objectstore.testing import InMemoryMediaStore
from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from schemas.domain import Principal
from tests.ingest.recipe_test_support import (  # noqa: F401 (the autouse fixture)
    MergingGraph,
    local_staging,
)

ONTOLOGY = load_deployment_ontology()
LOADER = Principal(id="engineer-1", clearance="SECRET", org_unit="verify")

#: The 15 columns of the 2012 MC2 firewall log, in order (COMIDDS, vast_2012), with synthetic rows:
#: documentation-range addresses only.
FIREWALL = (
    "Date/time,Syslog priority,Operation,Message code,Protocol,Source IP,Destination IP,"
    "Source hostname,Destination hostname,Source port,Destination port,Destination service,"
    "Direction,Connections built,Connections torn down\n"
    "05/Apr/2012 17:51:26,Info,Built,ASA-6-302013,TCP,192.0.2.10,198.51.100.5,,,6000,80,http,"
    "outbound,1,0\n"
    "05/Apr/2012 17:51:27,Info,Teardown,ASA-6-302014,TCP,192.0.2.10,198.51.100.5,,,6000,80,http,"
    "outbound,0,1\n"
    "06/Apr/2012 08:02:00,Info,Built,ASA-6-302013,UDP,192.0.2.11,203.0.113.9,,,53001,53,domain,"
    "outbound,1,0\n"
)
#: The five fields the 2008 tasks page documents, with synthetic rows.
CALLS = (
    "From,To,Datetime,Duration,Cell Tower\n"
    "200,201,20060601 0815,94,12\n"
    "201,202,20060602 2340,15,3\n"
    "200,201,20060610 1200,60,12\n"
)


def _rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def _load(dataset: str, text: str) -> MergingGraph:
    manifest_path = public_dataset.find_manifest(dataset)
    manifest = public_dataset.load_manifest(manifest_path)
    recipe = public_dataset.load_recipe(public_dataset.recipe_path(manifest, manifest_path))
    graph = MergingGraph(ONTOLOGY)
    report, events, _held = asyncio.run(
        load_with_rules(
            recipe, _rows(text), LOADER, graph=graph,  # type: ignore[arg-type]
            ontology=ONTOLOGY, load_id=f"load-{dataset}", investigation_scope="case-1",
            source=manifest.file.name, media=InMemoryMediaStore(), scheme=load_uk_le_scheme(),
        )
    )  # fmt: skip
    assert report.rejections == []
    return graph


def test_the_firewall_log_loads_each_connection_between_two_ip_endpoints() -> None:
    graph = _load("vast-2012-mc2", FIREWALL)
    endpoints = {n.properties["value_normalised"]: n for n in graph.nodes.values()}
    assert set(endpoints) == {"192.0.2.10", "198.51.100.5", "192.0.2.11", "203.0.113.9"}
    assert {n.type for n in endpoints.values()} == {"Endpoint"}
    assert {n.properties["endpoint_kind"] for n in endpoints.values()} == {"ip"}
    links = [e for e in graph.edges if e.type == "COMMUNICATED_WITH"]
    pairs = {(graph.nodes[e.source].properties["value_normalised"],
              graph.nodes[e.target].properties["value_normalised"]) for e in links}  # fmt: skip
    assert pairs == {("192.0.2.10", "198.51.100.5"), ("192.0.2.11", "203.0.113.9")}
    starts = sorted(e.interval.valid_from for e in links if e.interval is not None)
    assert starts[0] == datetime(2012, 4, 5, 17, 51, 26, tzinfo=UTC)


def test_the_call_records_load_each_call_with_its_time_and_duration() -> None:
    graph = _load("vast-2008-mc3", CALLS)
    phones = {n.properties["value_normalised"] for n in graph.nodes.values()}
    assert phones == {"200", "201", "202"}
    assert {n.properties["endpoint_kind"] for n in graph.nodes.values()} == {"handle"}
    links = [e for e in graph.edges if e.type == "COMMUNICATED_WITH"]
    first = min(e.interval.valid_from for e in links if e.interval is not None)
    assert first == datetime(2006, 6, 1, 8, 15, tzinfo=UTC)  # 1 June, never 6 January
    # The two calls 200 -> 201 are one link of two occurrences, as the store merges them.
    pair = [e for e in links if graph.nodes[e.source].properties["value_normalised"] == "200"]
    assert len(pair) == 1 and pair[0].occurrences == 2
