"""ADR-147 Amendment 3 (CARRIES row 23, the strict reading), over real ArcadeDB: a gazetteer loaded
through the Studio arrives in a case's own dataset as a plain file, unmarked, so the six
identifiers only a gazetteer carries (`GAZETTEER_ONLY_IDENTIFIERS`) are withheld from every node
for every request reader, and no node is matched on one, whatever dataset it is in. A `uprn`, a
case's own identifier (Amendment 1 point 3a), is kept and still matched.

One module's plant, read by each case on its own, so each half is shown red by its own plant
(`plants.md`): a `Location` carrying an `osm_id`, an `os_place_id` and a `uprn` in a case's own
source dataset (no `gazetteer-*` dataset, no gazetteer provenance), twelve more whose `osm_id`s
share its prefix (more than a type-ahead page), and a place in a dataset the case does not read. -
The match (`builders.match_any_field`): the exact search and the type-ahead by the `osm_id` find
nothing and say no `more`; at the adapter, `search_nodes` and `suggest_nodes` too, and the step a
search on those fields alone is sent (`or(__.not(__.identity()))`) keeps no node in ArcadeDB, with
the Conduit's own read of the same store finding the place (the positive control). - The read
(`ontology.handling`): found by its name and its `uprn`, the place is sent with its `uprn` alone,
and the working set's seed sends neither identifier. - Decision 4: a load's own match (`find_node`
on a recipe's `match_on`) run as the reader's scoped principal reaches no node in a dataset the
case does not read, and the node it reaches comes without the six.

Runs the real `services.api.app` over ArcadeDB, Postgres and Valkey on a leased test stack, as
`test_gazetteer_ids_withheld_live.py` does. Everything it writes is removed in teardown, pass or
fail, the nodes first and by id (no app start needed), then its case and this run's dataset rows.
"""

from __future__ import annotations

import asyncio
import os
import secrets
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from services.api.config import PostgresConfig
from services.api.datasets import Dataset, PostgresDatasetStore

from adapters.graph_arcadedb.access_filter import AccessFilter
from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.builders import SearchNodesBuilder
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from conduit_common.identity import new_node_id, now_utc
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import Handling, NodeWrite, Principal, Provenance, ProvenanceState, SourceRef
from tests.conftest import default_claims, sign_token
from tests.services.api.case_dataset import new_case

UNIT = Principal(id="loader-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
#: This run's own names, identifiers and dataset, so a search finds this run's place alone and its
#: teardown removes this run's rows alone.
TAG = f"{secrets.randbelow(10**8):08d}"
OWN = f"case-own-am3-live-{TAG}"
NAME = f"Wrexbury {TAG}"
OSM_ID = f"7{TAG}"
OS_PLACE_ID = f"osgb{TAG}"
UPRN = f"9{TAG}"
#: A dataset the case does not read, holding a place a load might match on its `os_place_id`.
UNREAD = f"case-other-am3-live-{TAG}"
UNREAD_PLACE_ID = f"osgbx{TAG}"
PLANTED: list[str] = []


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _client() -> ArcadeDBClient:
    return ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))


async def _graph() -> tuple[ArcadeDBClient, GraphArcadeDBAdapter]:
    client = _client()
    await client.create_database_if_absent()
    graph = GraphArcadeDBAdapter(client, load_uk_le_scheme())
    await graph.apply_schema(load_default_ontology())
    return client, graph


async def _plant() -> str:
    """The case's own place, as a Studio load of a gazetteer file writes it, twelve alike, and a
    place in a dataset the case does not read."""
    client, graph = await _graph()
    handling = Handling(
        classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
    )
    provenance = Provenance(
        state=ProvenanceState.ASSERTED,
        sources=[SourceRef(document_id="studio-load", locator="1", excerpt_hash="f" * 64)],
        first_seen=now_utc(),
    )
    place = NodeWrite(
        id=new_node_id(), type="Location",
        properties={"name": NAME, "osm_id": OSM_ID, "os_place_id": OS_PLACE_ID, "uprn": UPRN},
        provenance=provenance, handling=handling, created_by="loader-1", created_at=now_utc(),
        datasets=[OWN],
    )  # fmt: skip
    alike = [
        place.model_copy(
            update={
                "id": new_node_id(),
                "properties": {"name": f"Otherwhere {i}", "osm_id": f"{OSM_ID}{i:02d}"},
            }
        )
        for i in range(12)
    ]
    unread = place.model_copy(
        update={
            "id": new_node_id(),
            "properties": {"name": f"Unread {TAG}", "os_place_id": UNREAD_PLACE_ID},
            "datasets": [UNREAD],
        }
    )
    # Every id recorded before anything is written: teardown removes what a part-way failure left.
    PLANTED.extend([place.id, unread.id, *(n.id for n in alike)])
    tx = await graph.begin_transaction()
    await graph.upsert_nodes([place, unread, *alike], tx)
    await graph.commit_transaction(tx)
    await client.aclose()
    return place.id


async def _remove(ids: list[str]) -> None:
    """By id, with a bare client: no schema applied in teardown."""
    if not ids:
        return
    client = _client()
    try:
        quoted = ",".join(f"'{i}'" for i in ids)
        await client.gremlin(f"g.V().has('id',within({quoted})).drop()")
        left = await client.gremlin(f"g.V().has('id',within({quoted})).values('id')")
        assert left == [], f"left behind in the shared database: {left}"
    finally:
        await client.aclose()


async def _give_case(investigation_id: str) -> None:
    """The case reads this run's own source dataset alone: no gazetteer anywhere."""
    store = await PostgresDatasetStore.connect(PostgresConfig.from_env().dsn)
    try:
        for dataset_id, name in ((OWN, "Studio load"), (UNREAD, "Another case's data")):
            await store.register(
                Dataset(
                    id=dataset_id, name=f"{name} (Amendment 3 live test {TAG})",
                    owning_unit=UNIT.org_unit, created_at=datetime(2026, 11, 10, tzinfo=UTC),
                    created_by="test",
                )
            )  # fmt: skip
        await store.set_for_case(investigation_id, [OWN], UNIT)
    finally:
        await store.close()


async def _remove_rows(case_ids: list[str]) -> None:
    import asyncpg

    connection = await asyncpg.connect(PostgresConfig.from_env().dsn)
    try:
        layers = [
            r["id"]
            for r in await connection.fetch(
                "SELECT id FROM datasets WHERE layer_of = ANY($1::text[])", case_ids
            )
        ]
        await connection.execute(
            "DELETE FROM investigation_datasets WHERE investigation_id = ANY($1::text[])", case_ids
        )
        await connection.execute(
            "DELETE FROM case_layer_reads WHERE investigation_id = ANY($1::text[])", case_ids
        )
        mine = [*layers, OWN, UNREAD]
        await connection.execute("DELETE FROM datasets WHERE id = ANY($1::text[])", mine)
        left = await connection.fetchval(
            "SELECT count(*) FROM datasets WHERE id = ANY($1::text[])", mine
        )
        assert left == 0, f"{left} dataset row(s) of this run were not removed"
    finally:
        await connection.close()


@pytest.fixture(scope="module")
def world(
    jwks_url: str, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> Iterator[dict[str, Any]]:
    """The plant, the case reading it, and the headers; all of it removed afterwards."""
    keys = ("OIDC_JWKS_URL", "OIDC_ALGORITHMS", "ARCADEDB_DATABASE")
    previous = {key: os.environ.get(key) for key in keys}
    os.environ.update(
        {"OIDC_JWKS_URL": jwks_url, "OIDC_ALGORITHMS": "RS256", "ARCADEDB_DATABASE": "ospreyflow"}
    )
    private_key, _ = keypair
    headers = {"Authorization": f"Bearer {sign_token(private_key, default_claims())}"}
    PLANTED.clear()
    cases: list[str] = []
    from services.api.app import app

    try:
        place_id = _run(_plant())
        with TestClient(app) as client:
            made = client.post("/v1/investigations", headers=headers, json=new_case())
            cases.append(made.json()["id"])
            _run(_give_case(cases[0]))
        yield {"app": app, "headers": headers, "case": cases[0], "place": place_id}
    finally:
        try:
            _run(_remove(list(PLANTED)))
        finally:
            refused: list[tuple[str, int]] = []
            try:
                with TestClient(app) as client:
                    for made_id in cases:
                        answer = client.delete(f"/v1/investigations/{made_id}", headers=headers)
                        if answer.status_code not in (200, 204):
                            refused.append((made_id, answer.status_code))
            finally:
                _run(_remove_rows(cases))
                for key, value in previous.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
            assert not refused, f"cases not removed: {refused}"


def _reader() -> Principal:
    """The case's scope, as a request carries it (ADR-099): its own dataset alone."""
    return Principal(
        id="reader-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"], datasets=[OWN]
    )


# --- the match (`builders.match_any_field`) -------------------------------------------------------


def test_the_exact_search_finds_no_node_by_a_gazetteer_only_identifier(
    world: dict[str, Any],
) -> None:
    with TestClient(world["app"]) as client:
        for query in (OSM_ID, OS_PLACE_ID):
            answer = client.post(
                f"/v1/investigations/{world['case']}/search",
                headers=world["headers"],
                json={"query": query},
            )
            assert answer.status_code == 200 and answer.json()["nodes"] == [], answer.text


def test_the_type_ahead_suggests_nothing_by_one_and_says_no_more(world: dict[str, Any]) -> None:
    """Twelve places share the prefix: under Amendment 1 they fill the page and say `more`."""
    with TestClient(world["app"]) as client:
        for body in (
            {"query": OSM_ID},
            {"query": OSM_ID, "mode": "contains", "ignore_case": True},
        ):
            hinted = client.post(
                f"/v1/investigations/{world['case']}/suggest", headers=world["headers"], json=body
            )
            assert hinted.status_code == 200, hinted.text
            assert hinted.json()["nodes"] == [] and hinted.json()["more"] is False, body


def test_at_the_adapter_no_node_is_matched_on_one_and_the_empty_step_keeps_none(
    world: dict[str, Any],
) -> None:
    async def check() -> None:
        client, graph = await _graph()
        try:
            reader = _reader()
            assert await graph.search_nodes(OSM_ID, reader) == []
            suggested = await graph.suggest_nodes(OSM_ID, reader)
            assert suggested.nodes == [] and suggested.more is False
            assert [n.id for n in await graph.search_nodes(UPRN, reader)] == [world["place"]]
            # The step a search on those fields alone is sent, run by ArcadeDB itself.
            access = AccessFilter(load_uk_le_scheme())
            empty = SearchNodesBuilder(("osm_id",), OSM_ID).render_gremlin(access, reader)
            assert "or(__.not(__.identity()))" in empty
            assert await client.gremlin(empty) == []
            unlimited = reader.model_copy(update={"datasets": None})
            control = SearchNodesBuilder(("osm_id",), OSM_ID).render_gremlin(access, unlimited)
            found = await client.gremlin(control)
            assert [row["id"] for row in found] == [world["place"]], found
        finally:
            await client.aclose()

    _run(check())


# --- the read (`ontology.handling`) ---------------------------------------------------------------


def test_found_by_name_and_uprn_the_place_is_sent_with_its_uprn_alone(
    world: dict[str, Any],
) -> None:
    with TestClient(world["app"]) as client:
        for query in (NAME, UPRN):
            found = client.post(
                f"/v1/investigations/{world['case']}/search",
                headers=world["headers"],
                json={"query": query},
            )
            assert found.status_code == 200, found.text
            assert [n["id"] for n in found.json()["nodes"]] == [world["place"]], (query, found.text)
            sent = found.json()["nodes"][0]["properties"]
            assert sent.get("uprn") == UPRN, sent
            assert "osm_id" not in sent and "os_place_id" not in sent, sent
            assert OSM_ID not in found.text and OS_PLACE_ID not in found.text, found.text


def test_the_working_set_s_seed_sends_neither(world: dict[str, Any]) -> None:
    with TestClient(world["app"]) as client:
        found = client.post(
            f"/v1/investigations/{world['case']}/search",
            headers=world["headers"],
            json={"query": NAME},
        )
        seeded = client.post(
            f"/v1/investigations/{world['case']}/seed",
            headers=world["headers"],
            json={"nodes": [found.json()["nodes"][0]], "edges": []},
        )
        assert seeded.status_code == 200, seeded.text
        assert OSM_ID not in seeded.text and OS_PLACE_ID not in seeded.text, seeded.text
        assert UPRN in seeded.text, seeded.text


# --- decision 4: a load's own match ---------------------------------------------------------------


def test_a_load_s_match_reaches_no_node_the_reader_cannot_see(world: dict[str, Any]) -> None:
    """`find_node` on a recipe's `match_on` (`services/ingest/engine.py`, a load's and the Test's
    lookup), run as the reader's scoped principal: a place in a dataset the case does not read is
    not matched, so neither the load nor the Test's `referenced` count reaches it; the case's own
    place is matched by its `os_place_id` (the load's own work) and comes back without the six."""

    async def check() -> None:
        client, graph = await _graph()
        try:
            reader = _reader()
            assert await graph.find_node("Location", "os_place_id", UNREAD_PLACE_ID, reader) is None
            unlimited = reader.model_copy(update={"datasets": None})
            hidden = await graph.find_node("Location", "os_place_id", UNREAD_PLACE_ID, unlimited)
            assert hidden is not None  # the positive control: it is there
            own = await graph.find_node("Location", "os_place_id", OS_PLACE_ID, reader)
            assert own is not None and own.id == world["place"]
            assert "osm_id" not in own.properties and "os_place_id" not in own.properties
            assert own.properties["uprn"] == UPRN
        finally:
            await client.aclose()

    _run(check())
