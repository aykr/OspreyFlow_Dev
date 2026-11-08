"""The restore test that names a layer (ADR-143 Amendment 2 decision 4; L3.3): back up, restore, and
a drawn item and its picture come back in the right case's layer and no other.

**Live, against a lane's leased stack** (`scripts/stack_lease.sh`): a throwaway ArcadeDB database
(`conformance_*`, dropped afterwards) on the leased ArcadeDB. The graph is backed up and restored
with the harness's own engine steps, run in the leased container as `harness.backup` and
`harness.restore` run them in a deployment's: ArcadeDB's `BACKUP DATABASE`, then the database
dropped, its directory removed, `bin/restore.sh` and `open database`. The drawing itself is made
through the board service (`services/api/boards.py`) under case K's real scope, so what is backed up
is what a board writes. The picture's file lives in the object store, whose own backup is
`tests/harness/test_object_backup.py`'s; here the `Document` and its `DEPICTS` are what must come
back, in K's layer.

What a mistake would do, and the case that catches it:
- a restore that brings the drawing back into no layer, the source, or case B's layer, or loses its
  picture or its assertion: `test_a_drawn_item_and_its_picture_come_back_in_their_cases_layer`;
- a check that could not see that loss: `test_the_restore_check_fails_with_the_layer_lost`, the
  same comparison run against a restore whose node lost its layer (rule 15).

Run with a lease (`OSPREY_LANE` set and the stack's ports pinned; the container is the lease's own,
read from `scripts/lane_stacks.tsv` by the pinned port), or in CI's `conformance` job, which names its
ArcadeDB service's container in `OSPREY_TEST_ARCADEDB_CONTAINER`.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from harness.backup import arcadedb_request
from services.api.board_store import InMemoryBoardItemStore
from services.api.boards import Boards
from services.api.case_views import InMemoryCaseViewStore
from services.api.dataset_scope import scope_to_case, stamping
from services.api.datasets import Dataset, InMemoryDatasetStore

from adapters.graph_arcadedb.testing import arcadedb_adapter
from adapters.media_objectstore.testing import InMemoryMediaStore
from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from schemas.boards import DrawnItemInput
from schemas.domain import Grading, Node, Principal

STACKS = Path(__file__).resolve().parents[2] / "scripts" / "lane_stacks.tsv"
UNIT = "unit-1"
K, B = "case-k", "case-b"
ALICE = Principal(id="alice", clearance="SECRET", org_unit=UNIT, roles=["analyst"])

#: The ArcadeDB container to back up and restore in: named outright (CI's `conformance` job names its
#: service's, `OSPREY_TEST_ARCADEDB_CONTAINER`), or a lane's leased one, found by its pinned port.
NAMED = os.environ.get("OSPREY_TEST_ARCADEDB_CONTAINER")

pytestmark = pytest.mark.skipif(
    not NAMED and (not os.environ.get("OSPREY_LANE") or "ARCADEDB_HTTP_PORT" not in os.environ),
    reason="needs an ArcadeDB container to restore in: OSPREY_TEST_ARCADEDB_CONTAINER, or a leased "
    "lane stack (OSPREY_LANE and its pinned ARCADEDB_HTTP_PORT)",
)


def _container() -> str:
    if NAMED:
        return NAMED
    port = os.environ["ARCADEDB_HTTP_PORT"]
    for line in STACKS.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if (
            not line.startswith("#")
            and len(parts) > 3
            and parts[1] == "arcadedb"
            and parts[3] == port
        ):
            return parts[2]
    raise AssertionError(f"no leased ArcadeDB on port {port} in {STACKS}")


def _in_container(command: str) -> str:
    done = subprocess.run(  # noqa: S603
        ["docker", "exec", _container(), "sh", "-c", command],  # noqa: S607
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr or done.stdout
    return done.stdout


def _password() -> str:
    return os.environ.get("ARCADEDB_ROOT_PASSWORD", "playwithdata123")


def back_up_and_restore(database: str) -> None:
    """`harness.backup.backup_graph_store`'s and `harness.restore.restore_graph_store`'s engine
    steps, in the leased container."""
    command = json.dumps({"language": "sql", "command": "BACKUP DATABASE"})
    raw = _in_container(arcadedb_request(_password(), f"/api/v1/command/{database}", command))
    backup_file = json.loads(raw)["result"][0]["backupFile"]
    held = f"/home/arcadedb/backups/{database}/{backup_file}"
    drop = json.dumps({"command": f"drop database {database}"})
    output = _in_container(
        f"{arcadedb_request(_password(), '/api/v1/server', drop)} > /dev/null 2>&1 || true; "
        f"rm -rf /home/arcadedb/databases/{database}; "
        f"cd /home/arcadedb && ./bin/restore.sh -f file://{held} "
        f"-d /home/arcadedb/databases/{database}"
    )
    assert "restore completed" in output.lower(), output[-400:]
    reopen = json.dumps({"command": f"open database {database}"})
    answer = _in_container(arcadedb_request(_password(), "/api/v1/server", reopen))
    assert '"error"' not in answer, answer


@pytest.fixture
async def drawn() -> AsyncIterator[SimpleNamespace]:
    """Case K and case B read the same source; Alice draws a person and its picture on a board of
    K, through the board service under K's real scope."""
    ontology, scheme = load_deployment_ontology(), load_uk_le_scheme()
    datasets = InMemoryDatasetStore()
    datasets.add(
        Dataset(id="src", name="Prison intel", owning_unit=UNIT, created_by="eng",
                created_at=datetime(2026, 11, 1, tzinfo=UTC))
    )  # fmt: skip
    datasets.cases[K], datasets.cases[B] = ["src"], ["src"]
    layer_k = await datasets.ensure_layer(K, unit=UNIT, created_by="alice")
    layer_b = await datasets.ensure_layer(B, unit=UNIT, created_by="carol")
    async with arcadedb_adapter(ontology, scheme) as adapter:
        graph = stamping(adapter, registry=datasets)
        views = InMemoryCaseViewStore()
        boards = Boards(
            graph=graph, views=views, items=InMemoryBoardItemStore(), datasets=datasets,
            ontology=ontology, scheme=scheme, media=InMemoryMediaStore(),
        )  # fmt: skip
        scoped = await scope_to_case(ALICE, K, datasets)
        board = await views.save_board(K, "Wing B", "alice", node_ids=[])
        made = await boards.declare(
            board,
            DrawnItemInput(
                type="Person", label="Unknown male “Tall”", marking="OFFICIAL",
                grading=Grading(source="B", intelligence="2", handling="1"),
                source_note="Wing officer report, 4 Nov", properties={"family_name": "Tall"},
            ),
            scoped,
        )  # fmt: skip
        picture = await boards.upload_picture(
            board, made.element_id, scoped, name="tall.png", data=b"\x89PNG tall",
            marking="OFFICIAL",
        )  # fmt: skip
        yield SimpleNamespace(
            adapter=adapter, database=adapter._client.database,  # noqa: SLF001
            node=made.element_id, depicts=picture.element_id,
            in_k=scoped,
            in_b=ALICE.model_copy(update={"datasets": ["src", layer_b]}),
            layer_k=layer_k,
        )  # fmt: skip


async def _seen(world: SimpleNamespace, reader: Principal) -> tuple[list[Node], list[str]]:
    nodes = await world.adapter.get_nodes([world.node], reader)
    links = await world.adapter.get_edges([world.depicts], reader)
    documents = await world.adapter.get_nodes([e.source for e in links], reader)
    return [*nodes, *documents], [e.id for e in links]


def _came_back(world: SimpleNamespace, seen_in_k: tuple[list[Node], list[str]],
               seen_in_b: tuple[list[Node], list[str]]) -> list[str]:  # fmt: skip
    """Every way the drawing could have failed to come back right, named."""
    wrong = []
    nodes, links = seen_in_k
    by_id = {n.id: n for n in nodes}
    drawn = by_id.get(world.node)
    if drawn is None or drawn.provenance.drawn is None:
        wrong.append("the drawn item or its assertion did not come back in K")
    elif drawn.datasets != [world.layer_k]:
        wrong.append(f"the drawn item came back in {drawn.datasets}, not K's layer")
    if links != [world.depicts]:
        wrong.append("its picture's DEPICTS did not come back in K")
    documents = [n for n in nodes if n.type == "Document"]
    if len(documents) != 1 or documents[0].datasets != [world.layer_k]:
        wrong.append("its picture's Document did not come back in K's layer")
    if seen_in_b != ([], []):
        wrong.append("case B reads the drawing")
    return wrong


async def test_a_drawn_item_and_its_picture_come_back_in_their_cases_layer(
    drawn: SimpleNamespace,
) -> None:
    before = _came_back(drawn, await _seen(drawn, drawn.in_k), await _seen(drawn, drawn.in_b))
    assert before == [], before
    back_up_and_restore(drawn.database)
    after = _came_back(drawn, await _seen(drawn, drawn.in_k), await _seen(drawn, drawn.in_b))
    assert after == [], after


async def test_the_restore_check_fails_with_the_layer_lost(drawn: SimpleNamespace) -> None:
    """Rule 15: a restore whose drawn node lost its layer (planted by rewriting the stored
    `datasets` to the source after the restore) is named by the same comparison."""
    back_up_and_restore(drawn.database)
    # The node's stored type, found as the adapter finds it (`_holders`), then its datasets set.
    adapter = drawn.adapter
    for type_name, _ in await adapter._holders("vertex", [drawn.node]):  # noqa: SLF001
        await adapter._client.sql(  # noqa: SLF001
            f"UPDATE `{type_name}` SET datasets = ['src'] WHERE id = :id",
            params={"id": drawn.node},
        )
    in_k = await _seen(drawn, drawn.in_k)
    in_b = await _seen(drawn, drawn.in_b)
    wrong = _came_back(drawn, in_k, in_b)
    assert any("not K's layer" in w for w in wrong) and "case B reads the drawing" in wrong, wrong
