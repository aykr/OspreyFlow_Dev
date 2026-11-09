"""A case's gazetteers through the real routes (ADR-147 Amendment 2, the owner's ruling 6, option C):
`PUT /v1/datasets/{dataset}/gazetteers/{gazetteer}` copies the gazetteer's places into the case's
own dataset, and then, through the routes a case reads its nodes by:

- **the case stays one dataset and keeps its loads**: `GET .../datasets` names its own dataset alone
  (no composite), and a load a composite case refuses (`POST .../ingest/source-files`, the Studio's
  upload behind `NoLoadingInACompositeCase`, ADR-099 Amendment 15) is made; the same upload in the
  case made to read a composite is refused, so the check is the one a gazetteer composite trips;
- **no answer carries a copy's identifier**: search by name, the working set's seed and expansion;
- **the case's own searches never match a copy by an identifier**: `/search` by its `osm_id`, and
  `/suggest` on the identifier's prefix (twelve copies share it, more than a page) in both modes,
  find nothing and say no `more`;
- adding and removing are the dataset's (`PUT`/`DELETE /v1/datasets/{dataset}/gazetteers/...`,
  `run_pipelines`); **a removal deletes nothing** (the orchestrator's ruling (d), rule 3): a case
  whose copy has a SECRET link resting on it and a case whose copies have none are answered alike
  and then read alike; adding again re-links the same copies.

Runs the real `services.api.app` over real ArcadeDB, Postgres and Valkey on a leased test stack, as
`test_gazetteer_ids_withheld_live.py` does. Everything it writes is removed in teardown, pass or
fail: the planted nodes, their copies and the link, by id (the Conduit's database is always
`ospreyflow`, so not a throwaway one); its case, its delete checked; and in Postgres this run's
gazetteer dataset, the case's own dataset and layer, and the rows naming them.
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
from services.api.case_gazetteers import copy_id
from services.api.config import PostgresConfig
from services.api.datasets import Dataset, PostgresDatasetStore

from adapters.graph_arcadedb.adapter import GraphArcadeDBAdapter
from adapters.graph_arcadedb.client import ArcadeDBClient, ArcadeDBConfig
from conduit_common.identity import new_edge_id, new_node_id, now_utc
from ontology.handling import load_uk_le_scheme
from ontology.loader import load_default_ontology
from schemas.domain import (
    EdgeWrite,
    Handling,
    Interval,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)
from tests.conftest import default_claims, sign_token
from tests.services.api.case_dataset import new_case

UNIT = Principal(id="loader-1", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
TAG = f"{secrets.randbelow(10**8):08d}"
GAZETTEER = f"gazetteer-osm-p5-live-{TAG}"
NAME = f"Quillbury {TAG}"
#: Digits led by a 7, as an `osm_id` is written, never in the place's own name.
OSM_ID = f"7{TAG}"
UPRN = f"9{TAG}"
PLANTED: list[str] = []


@pytest.fixture
def api_env(jwks_url: str, tmp_path: Any) -> Iterator[None]:
    keys = ("OIDC_JWKS_URL", "OIDC_ALGORITHMS", "ARCADEDB_DATABASE", "OSPREY_INGEST_ROOT")
    previous = {key: os.environ.get(key) for key in keys}
    os.environ.update(
        {"OIDC_JWKS_URL": jwks_url, "OIDC_ALGORITHMS": "RS256", "ARCADEDB_DATABASE": "ospreyflow",
         # The upload lands in this run's own folder, removed with it.
         "OSPREY_INGEST_ROOT": str(tmp_path)}
    )  # fmt: skip
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _handling() -> Handling:
    return Handling(
        classification="OFFICIAL", handling_code="P", originator="unit-1", owning_unit="unit-1"
    )


def _provenance(state: ProvenanceState = ProvenanceState.ASSERTED) -> Provenance:
    return Provenance(
        state=state,
        sources=[SourceRef(document_id="osm-extract", locator="1", excerpt_hash="e" * 64)],
        first_seen=now_utc(),
        extracted_by="model:fixture" if state is ProvenanceState.INFERRED else None,
        extraction_confidence=0.6 if state is ProvenanceState.INFERRED else None,
    )


async def _graph() -> tuple[ArcadeDBClient, GraphArcadeDBAdapter]:
    client = ArcadeDBClient(ArcadeDBConfig.from_env(database="ospreyflow"))
    await client.create_database_if_absent()
    graph = GraphArcadeDBAdapter(client, load_uk_le_scheme())
    await graph.apply_schema(load_default_ontology())
    return client, graph


async def _plant_gazetteer() -> str:
    """A gazetteer place carrying its identifiers, and twelve more sharing its `osm_id`'s prefix, in
    this run's gazetteer dataset, registered for the unit."""
    client, graph = await _graph()
    place = NodeWrite(
        id=new_node_id(), type="Location",
        properties={"name": NAME, "osm_id": OSM_ID, "uprn": UPRN, "geometry_ref": f"g-{TAG}"},
        provenance=_provenance(), handling=_handling(), created_by="loader-1",
        created_at=now_utc(), datasets=[GAZETTEER],
    )  # fmt: skip
    alike = [
        place.model_copy(
            update={"id": new_node_id(),
                    "properties": {"name": f"Elsewhere {TAG} {i}", "osm_id": f"{OSM_ID}{i:02d}"}}
        )
        for i in range(12)
    ]  # fmt: skip
    secret = place.model_copy(
        update={"id": new_node_id(), "properties": {"name": f"Depot {TAG}", "osm_id": f"8{TAG}"},
                "handling": _handling().model_copy(update={"classification": "SECRET"})}
    )  # fmt: skip
    PLANTED.extend([place.id, *(n.id for n in alike), secret.id])
    tx = await graph.begin_transaction()
    await graph.upsert_nodes([place, *alike, secret], tx)
    await graph.commit_transaction(tx)
    await client.aclose()
    store = await PostgresDatasetStore.connect(PostgresConfig.from_env().dsn)
    try:
        await store.register(
            Dataset(
                id=GAZETTEER, name=f"Gazetteer: P5 live {TAG}", owning_unit=UNIT.org_unit,
                created_at=datetime(2026, 11, 9, tzinfo=UTC), created_by="test",
            )
        )  # fmt: skip
    finally:
        await store.close()
    return place.id


async def _plant_in_case(case_dataset: str, copy: str) -> tuple[str, dict[str, Any]]:
    """The case's own person, inferred (so a confirm is a write), present at the copy."""
    client, graph = await _graph()
    person = NodeWrite(
        id=new_node_id(), type="Person", properties={"family_name": f"Quillfeather{TAG}"},
        provenance=_provenance(ProvenanceState.INFERRED), handling=_handling(),
        created_by="loader-1", created_at=now_utc(), datasets=[case_dataset],
    )  # fmt: skip
    link = EdgeWrite(
        id=new_edge_id(), type="PRESENT_AT", source=person.id, target=copy,
        interval=Interval(valid_from=datetime(2026, 1, 1, tzinfo=UTC)),
        provenance=_provenance(), handling=_handling(), created_by="loader-1",
        created_at=now_utc(), datasets=[case_dataset],
    )  # fmt: skip
    PLANTED.extend([person.id, link.id])
    tx = await graph.begin_transaction()
    await graph.upsert_nodes([person], tx)
    await graph.upsert_edges([link], tx)
    await graph.commit_transaction(tx)
    stored = await graph.get_node(person.id, UNIT.model_copy(update={"datasets": None}))
    await client.aclose()
    assert stored is not None
    return person.id, stored.model_dump(mode="json")


async def _hidden_link(case_dataset: str, copy: str) -> None:
    """A SECRET person present at the copy, by a SECRET link: what an OFFICIAL Author may not
    read, resting on the copy."""
    client, graph = await _graph()
    secret = _handling().model_copy(update={"classification": "SECRET"})
    person = NodeWrite(
        id=new_node_id(), type="Person", properties={"family_name": f"Hidden{TAG}"},
        provenance=_provenance(), handling=secret, created_by="loader-1", created_at=now_utc(),
        datasets=[case_dataset],
    )  # fmt: skip
    link = EdgeWrite(
        id=new_edge_id(), type="PRESENT_AT", source=person.id, target=copy,
        interval=Interval(valid_from=datetime(2026, 1, 1, tzinfo=UTC)), provenance=_provenance(),
        handling=secret, created_by="loader-1", created_at=now_utc(), datasets=[case_dataset],
    )  # fmt: skip
    PLANTED.extend([person.id, link.id])
    tx = await graph.begin_transaction()
    await graph.upsert_nodes([person], tx)
    await graph.upsert_edges([link], tx)
    await graph.commit_transaction(tx)
    await client.aclose()


async def _remove(ids: list[str]) -> None:
    if not ids:
        return
    client, _graph_adapter = await _graph()
    try:
        quoted = ",".join(f"'{i}'" for i in ids)
        await client.gremlin(f"g.E().has('id',within({quoted})).drop()")
        await client.gremlin(f"g.V().has('id',within({quoted})).drop()")
        left = await client.gremlin(f"g.V().has('id',within({quoted})).values('id')")
        assert left == [], f"left behind in the shared database: {left}"
    finally:
        await client.aclose()


async def _remove_rows(case_ids: list[str], case_datasets: list[str]) -> None:
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
            "DELETE FROM dataset_gazetteers WHERE case_dataset = ANY($1::text[])", case_datasets
        )
        await connection.execute(
            "DELETE FROM composite_members WHERE composite_id = ANY($1::text[])", case_datasets
        )
        await connection.execute(
            "DELETE FROM investigation_datasets WHERE investigation_id = ANY($1::text[])", case_ids
        )
        await connection.execute(
            "DELETE FROM case_layer_reads WHERE investigation_id = ANY($1::text[])", case_ids
        )
        gone = [*layers, *case_datasets, GAZETTEER]
        await connection.execute("DELETE FROM datasets WHERE id = ANY($1::text[])", gone)
        left = await connection.fetchval(
            "SELECT count(*) FROM datasets WHERE id = ANY($1::text[])", gone
        )
        held = await connection.fetchval(
            "SELECT count(*) FROM dataset_gazetteers WHERE case_dataset = ANY($1::text[])",
            case_datasets,
        )
        assert (left, held) == (0, 0), f"rows of this run left: {left} datasets, {held} additions"
    finally:
        await connection.close()


def _carries_an_identifier(text: str) -> bool:
    return OSM_ID in text or UPRN in text or '"osm_id"' in text or '"uprn"' in text


def test_a_case_that_adds_a_gazetteer_reads_copies_without_identifiers_and_still_loads(
    api_env: None, keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]
) -> None:
    private_key, _ = keypair
    # A Source author too, so the Studio's upload (a load a composite case refuses) is theirs.
    claims = default_claims(roles=["analyst", "source_author", "loader"])
    headers = {"Authorization": f"Bearer {sign_token(private_key, claims)}"}
    PLANTED.clear()
    cases: list[str] = []
    case_datasets: list[str] = []

    from services.api.app import app

    try:
        place_id = _run(_plant_gazetteer())
        with TestClient(app) as client:
            made = client.post("/v1/investigations", headers=headers, json=new_case())
            assert made.status_code in (200, 201), made.text
            case_id = made.json()["id"]
            cases.append(case_id)
            reads = client.get(f"/v1/investigations/{case_id}/datasets", headers=headers).json()
            [own] = [d["id"] for d in reads if d["kind"] == "source"]
            case_datasets.append(own)
            # Every copy's id is known before anything is copied: teardown removes them all.
            alike = PLANTED[1:14]  # the twelve and the SECRET depot
            PLANTED.extend(copy_id(i, own) for i in [place_id, *alike])

            offered = client.get(f"/v1/investigations/{case_id}/map/gazetteers", headers=headers)
            assert {"dataset_id": GAZETTEER, "name": f"Gazetteer: P5 live {TAG}",
                    "added": False} in offered.json()["gazetteers"], offered.text  # fmt: skip
            # A dataset-level action (the review of P5, item 6): the dataset's route, `run_pipelines`.
            added = client.put(f"/v1/datasets/{own}/gazetteers/{GAZETTEER}", headers=headers)
            assert added.status_code == 200, added.text
            copy = copy_id(place_id, own)

            # The case stays one dataset: no composite.
            after = client.get(f"/v1/investigations/{case_id}/datasets", headers=headers).json()
            assert [d["id"] for d in after if d["kind"] in ("source", "composite")] == [own]

            # Decision 3b for a copy, at the routes.
            by_id = client.post(
                f"/v1/investigations/{case_id}/search", headers=headers, json={"query": OSM_ID}
            )
            assert by_id.status_code == 200 and by_id.json()["nodes"] == [], by_id.text
            for body in (
                {"query": OSM_ID},
                {"query": OSM_ID, "mode": "contains", "ignore_case": True},
            ):
                hinted = client.post(
                    f"/v1/investigations/{case_id}/suggest", headers=headers, json=body
                )
                assert hinted.status_code == 200, hinted.text
                assert hinted.json()["nodes"] == [] and hinted.json()["more"] is False, body
            found = client.post(
                f"/v1/investigations/{case_id}/search", headers=headers, json={"query": NAME}
            )
            assert found.status_code == 200, found.text
            assert [n["id"] for n in found.json()["nodes"]] == [copy]
            assert not _carries_an_identifier(found.text), found.text

            seeded = client.post(
                f"/v1/investigations/{case_id}/seed", headers=headers,
                json={"nodes": [found.json()["nodes"][0]], "edges": []},
            )  # fmt: skip
            assert seeded.status_code == 200, seeded.text
            assert not _carries_an_identifier(seeded.text), seeded.text

            # The case's own person, present at the copy: expanded from, the copy arrives without
            # its identifiers.
            person_id, person_body = _run(_plant_in_case(own, copy))
            put = client.post(
                f"/v1/investigations/{case_id}/seed", headers=headers,
                json={"nodes": [person_body], "edges": []},
            )  # fmt: skip
            assert put.status_code == 200, put.text
            expanded = client.post(
                f"/v1/investigations/{case_id}/expand", headers=headers,
                json={"request": {"node_ids": [person_id], "depth": 1}},
            )  # fmt: skip
            assert expanded.status_code == 200, expanded.text
            assert copy in {n["id"] for n in expanded.json()["delta"]["nodes"]}, expanded.text
            assert not _carries_an_identifier(expanded.text), expanded.text

            # It still loads: the Studio's upload, refused in a case reading a composite.
            uploaded = client.post(
                f"/v1/investigations/{case_id}/ingest/source-files", headers=headers,
                params={"name": f"p5-{TAG}.csv"}, content=b"name,town\nA,Oakham\n",
            )  # fmt: skip
            assert uploaded.status_code == 201, uploaded.text

            # Ruling (d), rule 3: a link the Author may not read (SECRET, from a SECRET person)
            # rests on one copy here; a second case's copies have none. Both removals answer alike
            # and leave the Author reading alike: nothing is deleted.
            _run(_hidden_link(own, copy_id(PLANTED[1], own)))
            removed = client.delete(f"/v1/datasets/{own}/gazetteers/{GAZETTEER}", headers=headers)
            assert removed.status_code == 200, removed.text
            assert removed.json()["said"].startswith("The gazetteer is removed: its places stay")
            assert "copies_kept" not in removed.json()
            other = client.post("/v1/investigations", headers=headers, json=new_case())
            other_id = other.json()["id"]
            cases.append(other_id)
            other_reads = client.get(
                f"/v1/investigations/{other_id}/datasets", headers=headers
            ).json()
            [own_2] = [d["id"] for d in other_reads if d["kind"] == "source"]
            case_datasets.append(own_2)
            PLANTED.extend(copy_id(i, own_2) for i in [place_id, *alike])
            assert client.put(
                f"/v1/datasets/{own_2}/gazetteers/{GAZETTEER}", headers=headers
            ).status_code == 200
            removed_2 = client.delete(
                f"/v1/datasets/{own_2}/gazetteers/{GAZETTEER}", headers=headers
            )
            assert removed_2.json() == removed.json()

            def seen(case: str) -> tuple[int, bool, int]:
                found = client.post(
                    f"/v1/investigations/{case}/search", headers=headers, json={"query": NAME}
                ).json()["nodes"]
                assert not any(_carries_an_identifier(str(n)) for n in found)
                hinted = client.post(
                    f"/v1/investigations/{case}/suggest", headers=headers,
                    json={"query": f"Elsewhere {TAG}", "mode": "contains"},
                ).json()  # fmt: skip
                listing = client.get(f"/v1/investigations/{case}/map/gazetteers", headers=headers)
                added = [g for g in listing.json()["gazetteers"] if g["dataset_id"] == GAZETTEER]
                return len(found), hinted["more"], len(hinted["nodes"]) + 10 * added[0]["added"]

            # Every copy stays in both: the place by its name, the twelve by theirs.
            assert seen(case_id) == seen(other_id) == (1, True, 10)
            # Added again: the same copies, re-linked, never a second set.
            assert client.put(
                f"/v1/datasets/{own}/gazetteers/{GAZETTEER}", headers=headers
            ).status_code == 200
            again = client.post(
                f"/v1/investigations/{case_id}/search", headers=headers, json={"query": NAME}
            )
            assert [n["id"] for n in again.json()["nodes"]] == [copy], again.text

            # The control: the same upload in a case reading a composite (what adding the gazetteer
            # as a dataset made, Amendment 1's option (b)) is refused.
            composite = client.post(
                "/v1/datasets/composites", headers=headers,
                json={"name": f"P5 composite {TAG}", "member_ids": [own, GAZETTEER]},
            )  # fmt: skip
            assert composite.status_code in (200, 201), composite.text
            case_datasets.append(composite.json()["id"])
            chose = client.put(
                f"/v1/investigations/{case_id}/datasets", headers=headers,
                json={"dataset_ids": [composite.json()["id"]]},
            )  # fmt: skip
            assert chose.status_code == 200, chose.text
            refused_load = client.post(
                f"/v1/investigations/{case_id}/ingest/source-files", headers=headers,
                params={"name": f"p5-{TAG}-b.csv"}, content=b"name\nB\n",
            )  # fmt: skip
            assert refused_load.status_code == 409, refused_load.text
    finally:
        refused: list[tuple[str, int]] = []
        with TestClient(app) as client:
            for made_id in cases:
                answer = client.delete(f"/v1/investigations/{made_id}", headers=headers)
                if answer.status_code not in (200, 204):
                    refused.append((made_id, answer.status_code))
        _run(_remove(list(PLANTED)))
        _run(_remove_rows(cases, case_datasets))
        assert not refused, f"cases not removed: {refused}"
