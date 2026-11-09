"""Promotion into a dataset, and a removed case's layer merged or deleted, through the real app
(ADR-143 decisions 8 and 10; Amendment 2 decision 1; ADR-145 decision 8; L3.4).

The world is `test_boards.py`'s: case K (Alice its Author) and case B (Carol) read the source
dataset `src` (highest allowed marking OFFICIAL-SENSITIVE). Added here: `src`'s home case, whose
Authors are Dana (a data engineer, SECRET), Erin (a data engineer, cleared to OFFICIAL) and Sam (the
Super user preset, also K's Author); Fred, a data engineer reading `src` through case F but no
Author of it; and Zed, of another unit.

What a mistake here would do, and the case that catches it (each red by its plant below, and in
`process/lanes/case/L3.4_RED_RECORD.md`):

- a promotion written as several loads, or half of one (decision 8): `test_author_promotes_...`
  and `test_a_promotion_with_an_item_changed_writes_nothing`, red with the load committed item by
  item;
- a link promoted without both its ends: `test_a_link_whose_drawn_end_does_not_go_...`, red with
  the end check removed;
- a marking above the dataset's highest allowed promoted: `test_a_marking_above_...`, red with the
  route's check removed (the sheet bypassed: the test posts with no sheet);
- a promoted item readable before review where the policy asks for one: `test_under_review_...`,
  red with the commit made at once whatever the policy;
- the proposer approving their own promotion: `test_the_proposer_cannot_approve_...`, red with the
  check removed;
- a reviewer approving what they may not see: `test_a_reviewer_who_may_not_see_...`, red with the
  check removed;
- the merge's read grant outliving the merge (Amendment 2 decision 1): `test_the_merge_grant_...`,
  red with the grant kept;
- a delete touching what was promoted: `test_deleting_a_layer_leaves_...`, red with the layer
  withdrawn whole;
- any route reachable by a non-member, a member of another case of the same dataset, or someone
  the dataset's gate is not for (rule 4): `test_every_promotion_route_refuses_...`.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from ports.graph import DatasetFootprint, PromotionReverted
from schemas.dataset_model import HomeCase
from schemas.domain import Principal
from services.api import promotions as promotions_module
from services.api.app import app
from services.api.datasets import COMPOSITE, Dataset
from services.api.investigations import AccessLevel
from services.api.promotion_store import InMemoryPromotionStore
from services.api.promotions import Promotions

from .test_boards import (
    B,
    K,
    PEOPLE,
    UNIT,
    _as,
    _board,
    _carol_sees_it_from_b,
    _item,
    _link,
    world,  # noqa: F401  (the fixture)
)

HOME, F = "home-src", "case-f"
PEOPLE.update(
    {
        "dana": Principal(id="dana", clearance="SECRET", org_unit=UNIT, roles=["data_engineer"]),
        "erin": Principal(id="erin", clearance="OFFICIAL", org_unit=UNIT, roles=["data_engineer"]),
        "fred": Principal(id="fred", clearance="SECRET", org_unit=UNIT, roles=["data_engineer"]),
        "sam": Principal(
            id="sam", clearance="SECRET", org_unit=UNIT, roles=["analyst", "data_engineer"]
        ),
        "zed": Principal(id="zed", clearance="SECRET", org_unit="unit-2", roles=["data_engineer"]),
    }
)


@pytest.fixture
def pw(world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:  # noqa: F811
    cases, datasets = world.cases, world.datasets
    cases.seed(HOME, {"dana": AccessLevel.AUTHOR, "erin": AccessLevel.AUTHOR,
                      "sam": AccessLevel.AUTHOR})  # fmt: skip
    cases.seed(F, {"fred": AccessLevel.VIEWER})
    cases.grants[K]["sam"] = AccessLevel.AUTHOR
    datasets.cases[HOME] = ["src"]
    datasets.cases[F] = ["src"]
    datasets.homes["src"] = HomeCase(
        dataset_id="src", investigation_id=HOME, made_at=datetime.now(UTC), made_by="dana"
    )
    removed: set[str] = set()

    async def admin_states(ids: Sequence[str]) -> dict[str, tuple[str, bool]]:
        return {c: (c, c in removed) for c in ids if c in cases.made}

    cases.admin_states = admin_states
    graph = world.graph

    async def dataset_footprints(
        ids: Sequence[str], reader: Principal
    ) -> dict[str, DatasetFootprint]:
        # As the adapter: only what the reader's own handling may read is counted.
        from ontology.handling import load_uk_le_scheme

        scheme = load_uk_le_scheme()
        out = {}
        for d in ids:
            nodes = [n for n in graph._graph_nodes.values() if not n.audit.reverted
                     and d in n.datasets
                     and scheme.clears(reader.clearance, n.handling.classification)]  # fmt: skip
            edges = [e for e in graph._graph_edges if not e.audit.reverted and d in e.datasets
                     and scheme.clears(reader.clearance, e.handling.classification)]  # fmt: skip
            out[d] = DatasetFootprint(nodes=len(nodes), edges=len(edges))
        return out

    graph.dataset_footprints = dataset_footprints
    store = InMemoryPromotionStore()
    monkeypatch.setattr(app.state, "promotions", store, raising=False)
    monkeypatch.setattr(app.state, "link_types", None, raising=False)
    yield SimpleNamespace(**vars(world), store=store, removed=removed)


def _policy(pw: SimpleNamespace, policy: str) -> None:
    held = pw.datasets.datasets["src"]
    pw.datasets.datasets["src"] = held.model_copy(update={"promotion_policy": policy})


def _drawn(who: str = "alice") -> tuple[str, dict[str, Any], str, str]:
    """A board of K from a selection holding the loaded Mercer; a drawn person linked to him."""
    board = _board(who, start="selection", node_ids=["p-loaded"])
    made = _item(board, who)
    linked = _as(who).post(
        f"/v1/investigations/{K}/boards/{board}/links",
        json={"type": "ASSOCIATE_OF", "label": "seen together", "marking": "OFFICIAL",
              "grading": {"source": "B", "intelligence": "2", "handling": "1"},
              "source_note": "Visits log", "source": made["element_id"], "target": "p-loaded"},
    )  # fmt: skip
    assert linked.status_code == 201, linked.text
    return board, made, linked.json()["item_id"], linked.json()["element_id"]


def _sheet(board: str, who: str = "alice") -> dict[str, Any]:
    answer = _as(who).get(f"/v1/investigations/{K}/boards/{board}/promotion-sheet")
    assert answer.status_code == 200, answer.text
    return dict(answer.json())


def _promote(board: str, *item_ids: str, who: str = "alice") -> Any:
    return _as(who).post(
        f"/v1/investigations/{K}/boards/{board}/promotions", json={"item_ids": list(item_ids)}
    )


def _studio(who: str, path: str = "", method: str = "get", **body: Any) -> Any:
    client = _as(who)
    url = f"/v1/datasets/src/promotions{path}"
    return client.post(url, json=body) if method == "post" else client.get(url)


def _node_datasets(pw: SimpleNamespace, node_id: str) -> list[str]:
    return list(pw.graph.node(node_id).datasets)


# --- one load, the same element (decision 8; rule 6) -----------------------------------------


def test_author_promotes_commits_one_load_and_case_b_reads_the_same_element(
    pw: SimpleNamespace,
) -> None:
    board, made, link_item, link = _drawn()
    assert not _carol_sees_it_from_b(made["element_id"])
    sheet = _sheet(board)
    assert {i["item_id"] for i in sheet["items"]} == {made["item_id"], link_item}
    assert all(not i["problems"] for i in sheet["items"]) and all(
        c["passed"] for c in sheet["checks"]
    )
    nodes_before = len(pw.graph._graph_nodes)

    answer = _promote(board, made["item_id"], link_item)

    assert answer.status_code == 201, answer.text
    body = answer.json()
    assert body["status"] == "committed" and (body["nodes"], body["links"]) == (1, 1)
    assert pw.graph.promotions == 1
    assert len(pw.graph._graph_nodes) == nodes_before  # the same element, never a copy
    layer = pw.items.items[made["item_id"]].dataset_id
    assert _node_datasets(pw, made["element_id"]) == sorted([layer, "src"])
    assert _carol_sees_it_from_b(made["element_id"])
    # The withdrawal rule's input (spec 03): the registry says it was promoted.
    assert pw.items.items[made["item_id"]].promoted_at is not None
    assert pw.items.items[link_item].promoted_at is not None
    # It stays drawn for good.
    assert pw.graph.node(made["element_id"]).provenance.drawn is not None


def _item_by_item(monkeypatch: pytest.MonkeyPatch) -> None:
    """The plant: the load committed item by item, each element in its own transaction."""

    async def by_item(self: Promotions, record: Any, *, by: str | None) -> Any:
        graph = self.boards.graph
        for node in record.node_ids:
            tx = await graph.begin_transaction()
            try:
                await graph.promote_elements([node], [], record.dataset_id, record.load_id, tx)
            except Exception:
                await graph.rollback_transaction(tx)
                continue
            await graph.commit_transaction(tx)
        for edge in record.edge_ids:
            tx = await graph.begin_transaction()
            await graph.promote_elements([], [edge], record.dataset_id, record.load_id, tx)
            await graph.commit_transaction(tx)
        await self.store.decide(record.id, was="awaiting_review", now="committed", by=by,
                                at=datetime.now(UTC))  # fmt: skip
        return await self.store.get(record.id)

    monkeypatch.setattr(Promotions, "_commit", by_item)


def test_the_one_load_check_fails_with_the_load_committed_item_by_item(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    _item_by_item(monkeypatch)
    board, made, link_item, _ = _drawn()
    assert _promote(board, made["item_id"], link_item).status_code == 201
    assert pw.graph.promotions != 1


def _withdrawn_behind_the_sheet(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, node_id: str
) -> None:
    """The element taken out after the route's checks and before the load is written (another
    tab's withdrawal, say), so only the graph's own all-or-nothing can catch it."""
    graph = pw.graph
    real = type(graph).promote_elements

    async def racing(*args: Any) -> None:
        held = graph.node(node_id)
        graph._graph_nodes[node_id] = held.model_copy(
            update={"audit": held.audit.model_copy(update={"reverted": True})}
        )
        await real(graph, *args)

    monkeypatch.setattr(graph, "promote_elements", racing)


def test_a_promotion_with_an_item_changed_writes_nothing(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    board, made, _, _ = _drawn()
    other = _item(board, label="Other", properties={"family_name": "Other"})
    _withdrawn_behind_the_sheet(pw, monkeypatch, other["element_id"])
    answer = _promote(board, made["item_id"], other["item_id"])
    assert answer.status_code == 409 and answer.json()["error"] == "items_changed"
    assert _node_datasets(pw, made["element_id"]) == [pw.items.items[made["item_id"]].dataset_id]
    assert not _carol_sees_it_from_b(made["element_id"])
    (record,) = pw.store.records.values()
    assert record.status == "rejected" and "Nothing was written" in (record.reason or "")


def test_the_all_or_nothing_check_fails_with_the_load_committed_item_by_item(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    _item_by_item(monkeypatch)
    board, made, _, _ = _drawn()
    other = _item(board, label="Other", properties={"family_name": "Other"})
    _withdrawn_behind_the_sheet(pw, monkeypatch, other["element_id"])
    _promote(board, made["item_id"], other["item_id"])
    assert _carol_sees_it_from_b(made["element_id"])


# --- links follow their ends (decision 8; rule 2) --------------------------------------------


def _two_drawn_and_a_link(pw: SimpleNamespace) -> tuple[str, dict[str, Any], dict[str, Any], str]:
    board = _board()
    x, y = _item(board), _item(board, label="Unknown female", properties={"family_name": "Y"})
    linked = _link(board, x["element_id"], y["element_id"])
    assert linked.status_code == 201, linked.text
    return board, x, y, linked.json()["item_id"]


def test_a_link_whose_drawn_end_does_not_go_is_left_out_and_listed(pw: SimpleNamespace) -> None:
    board, x, _, link_item = _two_drawn_and_a_link(pw)
    answer = _promote(board, x["item_id"], link_item)
    assert answer.status_code == 201, answer.text
    left = {i["item_id"]: i["why"] for i in answer.json()["left_out"]}
    assert "will not be in the dataset" in left[link_item]
    (record,) = pw.store.records.values()
    assert record.edge_ids == ()


def test_the_end_check_fails_with_the_end_check_removed(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Promotions, "ends_land", staticmethod(lambda item, lands, going: True))
    board, x, _, link_item = _two_drawn_and_a_link(pw)
    _promote(board, x["item_id"], link_item)
    (record,) = pw.store.records.values()
    assert record.edge_ids != ()


def test_a_link_to_a_loaded_item_goes_and_an_unticked_item_is_listed(pw: SimpleNamespace) -> None:
    board, made, link_item, _ = _drawn()
    spare = _item(board, label="Spare", properties={"family_name": "Spare"})
    answer = _promote(board, made["item_id"], link_item)
    assert answer.json()["links"] == 1
    assert {i["item_id"]: i["why"] for i in answer.json()["left_out"]} == {
        spare["item_id"]: "Not ticked."
    }


# --- the dataset's highest allowed marking (ADR-145 decision 8) ------------------------------


def _lowered(pw: SimpleNamespace) -> tuple[str, dict[str, Any]]:
    """An item drawn at OFFICIAL-SENSITIVE; then an administrator lowers `src`'s highest allowed
    marking to OFFICIAL, so the item is above it."""
    board = _board()
    made = _item(board, marking="OFFICIAL-SENSITIVE")
    held = pw.datasets.datasets["src"]
    pw.datasets.datasets["src"] = held.model_copy(update={"highest_marking": "OFFICIAL"})
    return board, made


def test_a_marking_above_the_datasets_highest_is_refused_at_the_sheet_and_at_the_route(
    pw: SimpleNamespace,
) -> None:
    board, made = _lowered(pw)
    sheet = _sheet(board)
    (item,) = sheet["items"]
    assert "above Prison intel's highest allowed marking, OFFICIAL" in item["problems"][0]
    assert not next(c for c in sheet["checks"] if c["name"] == "marking")["passed"]
    # The sheet bypassed: posted with no sheet, refused at the route in words.
    answer = _promote(board, made["item_id"])
    assert answer.status_code == 422 and answer.json()["error"] == "check_failed"
    assert "highest allowed marking" in answer.json()["detail"]
    assert not pw.store.records and pw.graph.promotions == 0


def test_the_route_check_fails_with_the_check_removed(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def no_problems(self: Promotions, reads: Any, *_: Any) -> dict[str, list[str]]:
        return {r.item.item_id: [] for r in reads}

    monkeypatch.setattr(Promotions, "_problems", no_problems)
    board, made = _lowered(pw)
    assert _promote(board, made["item_id"]).status_code == 201


# --- types (decision 9; ADR-143 Amendment 4 decision 3) -------------------------------------


class _LinkTypes:
    def __init__(self, why: str | None) -> None:
        self.why = why

    async def promotion_refusals(
        self, case_id: str, principal: Principal, names: Sequence[str]
    ) -> dict[str, str | None]:
        return dict.fromkeys(names, self.why)

    async def case_types(self, case_id: str, principal: Principal) -> dict[str, Any]:
        return {}  # its type is an ontology type, written under its own name


def test_a_link_of_a_type_not_yet_live_is_refused_and_promotable_once_live(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    board, made, link_item, _ = _drawn()
    why = "ASSOCIATE_OF is accepted into the draft domain model, version 2: its links can be promoted once that version is made live."  # noqa: E501
    monkeypatch.setattr(app.state, "link_types", _LinkTypes(why), raising=False)
    (link,) = [i for i in _sheet(board)["items"] if i["item_id"] == link_item]
    assert link["problems"] == [why]
    assert _promote(board, made["item_id"], link_item).status_code == 422
    monkeypatch.setattr(app.state, "link_types", _LinkTypes(None), raising=False)
    assert _promote(board, made["item_id"], link_item).json()["links"] == 1


# --- the policy and its review (ADR-145 decision 8; ADR-133 Amendment 8) ---------------------


def test_under_review_nothing_is_readable_outside_the_case_until_a_second_person_approves(
    pw: SimpleNamespace,
) -> None:
    _policy(pw, "second_person_reviews")
    board, made, link_item, _ = _drawn()
    answer = _promote(board, made["item_id"], link_item)
    assert answer.json()["status"] == "awaiting_review"
    assert not _carol_sees_it_from_b(made["element_id"]) and pw.graph.promotions == 0

    (listed,) = _studio("dana").json()["promotions"]
    assert listed["may_review"] and listed["board_id"] is None and listed["case_name"] == K
    details = _studio("dana", f"/{listed['id']}").json()
    assert {i["label"] for i in details["items"]} >= {"Unknown male “Tall”"}
    assert not details["withheld"]
    decided = _studio("dana", f"/{listed['id']}/decision", "post", approve=True)
    assert decided.status_code == 200 and decided.json()["status"] == "committed"
    assert decided.json()["reviewed_by"] == "dana"
    assert _carol_sees_it_from_b(made["element_id"])
    board_list = _as("alice").get(f"/v1/investigations/{K}/boards/{board}/promotions").json()
    assert board_list["promotions"][0]["status"] == "committed"


def test_the_review_check_fails_with_the_commit_made_at_once(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Promotions, "commits_at_once", staticmethod(lambda dataset: True))
    _policy(pw, "second_person_reviews")
    board, made, link_item, _ = _drawn()
    _promote(board, made["item_id"], link_item)
    assert _carol_sees_it_from_b(made["element_id"])


def test_a_rejection_writes_nothing_and_says_why(pw: SimpleNamespace) -> None:
    _policy(pw, "second_person_reviews")
    board, made, link_item, _ = _drawn()
    promotion = _promote(board, made["item_id"], link_item).json()["id"]
    assert _studio("dana", f"/{promotion}/decision", "post", approve=False).status_code == 422
    rejected = _studio("dana", f"/{promotion}/decision", "post", approve=False,
                       reason="Source note too thin")  # fmt: skip
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["reason"] == "Source note too thin"
    assert pw.graph.promotions == 0 and not _carol_sees_it_from_b(made["element_id"])
    again = _studio("dana", f"/{promotion}/decision", "post", approve=True)
    assert again.status_code == 409 and again.json()["error"] == "already_decided"


def _sams_promotion(pw: SimpleNamespace) -> str:
    _policy(pw, "second_person_reviews")
    board = _board("sam")
    made = _item(board, "sam")
    return str(_promote(board, made["item_id"], who="sam").json()["id"])


def test_the_proposer_cannot_approve_their_own_promotion(pw: SimpleNamespace) -> None:
    promotion = _sams_promotion(pw)
    (listed,) = _studio("sam").json()["promotions"]
    assert not listed["may_review"] and "a second person" in listed["why_not"]
    answer = _studio("sam", f"/{promotion}/decision", "post", approve=True)
    assert answer.status_code == 403 and answer.json()["error"] == "own_promotion"
    assert pw.graph.promotions == 0


def test_the_own_promotion_check_fails_with_the_check_removed(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Promotions, "refuse_own_promotion", staticmethod(lambda r, p: None))
    promotion = _sams_promotion(pw)
    assert _studio("sam", f"/{promotion}/decision", "post", approve=True).status_code == 200


def test_only_an_author_of_the_dataset_holding_review_promotions_decides(
    pw: SimpleNamespace,
) -> None:
    _policy(pw, "second_person_reviews")
    board, made, link_item, _ = _drawn()
    promotion = _promote(board, made["item_id"], link_item).json()["id"]
    # Fred: a data engineer reading `src`, no Author of it.
    (listed,) = _studio("fred").json()["promotions"]
    assert not listed["may_review"] and "not one of its Authors" in listed["why_not"]
    assert _studio("fred", f"/{promotion}").status_code == 403
    assert _studio("fred", f"/{promotion}/decision", "post", approve=True).status_code == 403
    # Alice: K's Author, but without `review_promotions`.
    assert _studio("alice").status_code == 403
    assert pw.graph.promotions == 0


def _sent_for_review(pw: SimpleNamespace) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Two items sent for review at OFFICIAL: Erin (cleared to OFFICIAL) and Dana may both read
    it."""
    _policy(pw, "second_person_reviews")
    board = _board()
    seen = _item(board)
    raised = _item(board, label="Hidden", properties={"family_name": "Hidden"})
    promotion = _promote(board, seen["item_id"], raised["item_id"]).json()["id"]
    return promotion, seen, raised


def _raised_by_its_author(raised: dict[str, Any]) -> None:
    """An item waiting for review is not yet promoted, so its author may still edit it: raised to
    OFFICIAL-SENSITIVE, above Erin's clearance."""
    edited = _as("alice").patch(f"/v1/investigations/{K}/board-items/{raised['item_id']}",
                                json={"marking": "OFFICIAL-SENSITIVE"})  # fmt: skip
    assert edited.status_code == 200, edited.text


def _raised_out_of_band(pw: SimpleNamespace, raised: dict[str, Any]) -> None:
    """The element's marking raised in the graph by no route of this module (the case's own
    marking tool, a migration): the promotion's record still says OFFICIAL, so only the read
    itself can say what Erin may see."""
    node = pw.graph.node(raised["element_id"])
    pw.graph._graph_nodes[raised["element_id"]] = node.model_copy(
        update={
            "handling": node.handling.model_copy(update={"classification": "OFFICIAL-SENSITIVE"})
        }
    )


def test_an_item_raised_while_waiting_takes_its_promotion_out_of_a_lower_reviewers_reach(
    pw: SimpleNamespace,
) -> None:
    promotion, _, raised = _sent_for_review(pw)
    assert [p["id"] for p in _studio("erin").json()["promotions"]] == [promotion]
    _raised_by_its_author(raised)
    assert pw.store.records[promotion].marking == "OFFICIAL-SENSITIVE"
    # Rule 3: to Erin it is no promotion at all, in the list, in Details and at a decision.
    assert _studio("erin").json()["promotions"] == []
    assert _studio("erin", f"/{promotion}").status_code == 404
    assert _studio("erin", f"/{promotion}/decision", "post", approve=True).status_code == 404
    # Dana, cleared for it, still reads it whole.
    (dana,) = _studio("dana").json()["promotions"]
    assert (dana["nodes"], dana["links"]) == (2, 0)


def test_the_raised_marking_check_fails_with_the_promotion_left_as_sent(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def kept(self: Any, *args: Any) -> None:
        return None

    monkeypatch.setattr(InMemoryPromotionStore, "raise_marking", kept)  # the plant
    promotion, _, raised = _sent_for_review(pw)
    _raised_by_its_author(raised)
    assert [p["id"] for p in _studio("erin").json()["promotions"]] == [promotion]


def test_the_lists_clearance_check_fails_with_every_marking_passed_to_the_query(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    from services.api import app as app_module

    promotion, _, raised = _sent_for_review(pw)
    _raised_by_its_author(raised)
    # The plant at the route's call site: the query given every marking, whatever the reader's.
    monkeypatch.setattr(
        app_module, "_markings_cleared",
        lambda promotions, principal: list(promotions.boards.scheme.classification),
    )  # fmt: skip
    assert [p["id"] for p in _studio("erin").json()["promotions"]] == [promotion]


def test_the_details_clearance_check_fails_with_the_check_removed(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    from services.api import app as app_module

    promotion, _, raised = _sent_for_review(pw)
    _raised_by_its_author(raised)
    monkeypatch.setattr(app_module, "_cleared_for", lambda *args: True)  # the plant
    assert _studio("erin", f"/{promotion}").status_code == 200


def _bob_reads_the_boards_promotions(pw: SimpleNamespace) -> list[Any]:
    _policy(pw, "second_person_reviews")
    board = _board()
    assert _as("alice").post(f"/v1/investigations/{K}/boards/{board}/share").status_code == 200
    high = _item(board, marking="OFFICIAL-SENSITIVE", label="High", properties={"family_name": "H"})
    assert _promote(board, high["item_id"]).status_code == 201
    # Bob: K's Editor, cleared to OFFICIAL, reading the shared board.
    answer = _as("bob").get(f"/v1/investigations/{K}/boards/{board}/promotions")
    assert answer.status_code == 200, answer.text
    return list(answer.json()["promotions"])


def test_a_boards_promotions_are_filtered_by_clearance_in_the_query(pw: SimpleNamespace) -> None:
    assert _bob_reads_the_boards_promotions(pw) == []


def test_the_boards_clearance_check_fails_with_every_marking_passed_to_the_query(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    from services.api import app as app_module

    monkeypatch.setattr(
        app_module, "_markings_cleared",
        lambda promotions, principal: list(promotions.boards.scheme.classification),
    )  # fmt: skip
    assert _bob_reads_the_boards_promotions(pw) != []


def test_a_reviewer_who_may_not_see_every_item_may_not_approve(pw: SimpleNamespace) -> None:
    promotion, _, raised = _sent_for_review(pw)
    _raised_out_of_band(pw, raised)
    (listed,) = _studio("erin").json()["promotions"]
    details = _studio("erin", f"/{promotion}").json()
    assert details["withheld"]
    assert {i["label"] for i in details["items"]} == {"Unknown male “Tall”"}
    # Rule 7 (Amendment 5 decision 6a): the counts of what is shown, the same in the list as in
    # Details, never beside a difference.
    assert (details["promotion"]["nodes"], details["promotion"]["links"]) == (1, 0)
    assert (listed["nodes"], listed["links"]) == (1, 0)
    answer = _studio("erin", f"/{promotion}/decision", "post", approve=True)
    assert answer.status_code == 403 and answer.json()["error"] == "not_all_seen"
    assert pw.graph.promotions == 0
    # The promotion still waits: another Author may see it all.
    assert pw.store.records[promotion].status == "awaiting_review"


def test_the_shown_counts_check_fails_with_the_recorded_counts_listed(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def recorded(self: Promotions, records: Any, reader: Any) -> dict[str, Any]:
        return {r.id: (len(r.node_ids), len(r.edge_ids)) for r in records}

    monkeypatch.setattr(Promotions, "shown_counts", recorded)  # the plant
    promotion, _, raised = _sent_for_review(pw)
    _raised_out_of_band(pw, raised)
    (listed,) = _studio("erin").json()["promotions"]
    assert listed["nodes"] == 2  # the difference against Details' 1: what the check refuses


def test_the_unseen_check_fails_with_the_check_removed(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Promotions, "reviewer_sees_all", staticmethod(lambda reads: True))
    promotion, _, raised = _sent_for_review(pw)
    _raised_out_of_band(pw, raised)
    assert _studio("erin", f"/{promotion}/decision", "post", approve=True).status_code != 403


def test_a_decided_promotions_details_read_none_of_its_layer(pw: SimpleNamespace) -> None:
    promotion, seen, _ = _sent_for_review(pw)
    rejected = _studio("dana", f"/{promotion}/decision", "post", approve=False, reason="No.")
    assert rejected.status_code == 200, rejected.text
    # The items are the case's layer's alone again: nothing of them is read for a reviewer.
    _as("alice").patch(f"/v1/investigations/{K}/board-items/{seen['item_id']}",
                       json={"label": "Renamed since"})  # fmt: skip
    details = _studio("sam", f"/{promotion}").json()
    assert details["items"] == [] and not details["withheld"]
    assert details["promotion"]["status"] == "rejected"


def test_the_decided_details_check_fails_with_the_layer_read_whatever_the_status(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    def always(self: Promotions, record: Any, reviewer: Principal) -> Principal:
        return reviewer.model_copy(update={"datasets": [record.dataset_id, record.layer_id]})

    monkeypatch.setattr(Promotions, "_reviewer_read", always)  # the plant
    promotion, _, _ = _sent_for_review(pw)
    _studio("dana", f"/{promotion}/decision", "post", approve=False, reason="No.")
    assert _studio("sam", f"/{promotion}").json()["items"] != []


def test_an_approval_runs_every_check_again_on_the_items_as_they_are_now(
    pw: SimpleNamespace,
) -> None:
    _policy(pw, "second_person_reviews")
    board = _board()
    made = _item(board, marking="OFFICIAL-SENSITIVE")
    promotion = _promote(board, made["item_id"]).json()["id"]
    # An administrator lowers the dataset's highest allowed marking while it waits.
    held = pw.datasets.datasets["src"]
    pw.datasets.datasets["src"] = held.model_copy(update={"highest_marking": "OFFICIAL"})
    answer = _studio("dana", f"/{promotion}/decision", "post", approve=True)
    assert answer.status_code == 409 and answer.json()["error"] == "items_changed"
    assert "highest allowed marking" in answer.json()["detail"]
    assert pw.store.records[promotion].status == "rejected"
    assert pw.graph.promotions == 0 and not _carol_sees_it_from_b(made["element_id"])


def test_the_recheck_fails_with_the_recheck_removed(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def nothing(self: Promotions, record: Any, reviewer: Any) -> None:
        return None

    monkeypatch.setattr(Promotions, "recheck", nothing)
    _policy(pw, "second_person_reviews")
    board = _board()
    made = _item(board, marking="OFFICIAL-SENSITIVE")
    promotion = _promote(board, made["item_id"]).json()["id"]
    held = pw.datasets.datasets["src"]
    pw.datasets.datasets["src"] = held.model_copy(update={"highest_marking": "OFFICIAL"})
    _studio("dana", f"/{promotion}/decision", "post", approve=True)
    assert _carol_sees_it_from_b(made["element_id"])


def test_what_was_left_out_goes_to_its_proposer_alone_and_the_case_to_whom_may_know_it(
    pw: SimpleNamespace,
) -> None:
    _policy(pw, "second_person_reviews")
    board, made, link_item, _ = _drawn()
    spare = _item(board, marking="OFFICIAL-SENSITIVE", label="Secret spare",
                  properties={"family_name": "Spare"})  # fmt: skip
    promotion = _promote(board, made["item_id"], link_item).json()
    assert {i["item_id"] for i in promotion["left_out"]} == {spare["item_id"]}  # the proposer
    (for_dana,) = _studio("dana").json()["promotions"]
    assert for_dana["left_out"] == [] and for_dana["case_name"] == K
    assert _studio("dana", f"/{for_dana['id']}").json()["promotion"]["left_out"] == []
    (for_fred,) = _studio("fred").json()["promotions"]
    assert for_fred["left_out"] == [] and for_fred["case_id"] == ""
    assert for_fred["case_name"] == "a case reading this dataset"
    assert "Secret spare" not in str(_studio("fred").json())


def test_the_boards_promotions_are_listed_only_as_the_reader_may_see_them(
    pw: SimpleNamespace,
) -> None:
    board = _board()
    assert _as("alice").post(f"/v1/investigations/{K}/boards/{board}/share").status_code == 200
    low = _item(board)
    high = _item(board, marking="OFFICIAL-SENSITIVE", label="High", properties={"family_name": "H"})
    _promote(board, low["item_id"])
    _promote(board, high["item_id"])
    alices = _as("alice").get(f"/v1/investigations/{K}/boards/{board}/promotions").json()
    bobs = _as("bob").get(f"/v1/investigations/{K}/boards/{board}/promotions").json()
    assert len(alices["promotions"]) == 2
    assert len(bobs["promotions"]) == 1 and bobs["promotions"][0]["left_out"] == []


def test_an_item_waiting_for_review_is_in_no_second_promotion(pw: SimpleNamespace) -> None:
    _policy(pw, "second_person_reviews")
    board = _board()
    made = _item(board)
    _promote(board, made["item_id"])
    assert made["item_id"] not in {i["item_id"] for i in _sheet(board)["items"]}
    again = _promote(board, made["item_id"])
    assert again.status_code == 404 and again.json()["error"] == "item_not_found"


def test_a_load_refused_for_any_reason_leaves_no_promotion_waiting(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def refused(*args: Any) -> None:
        raise RuntimeError("the store refused the load")

    monkeypatch.setattr(pw.graph, "promote_elements", refused)
    board = _board()
    made = _item(board)
    with pytest.raises(RuntimeError):
        _promote(board, made["item_id"])
    (record,) = pw.store.records.values()
    assert record.status == "rejected" and "nothing was written" in (record.reason or "")


def test_a_link_type_outside_the_datasets_live_model_is_not_promoted(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    board = _board()
    x, y = _item(board), _item(board, label="Y", properties={"family_name": "Y"})
    # Drawn while the dataset had no live model yet (every type offered) ...
    linked = _link(board, x["element_id"], y["element_id"], type="CO_DEFENDANT_OF")
    assert linked.status_code == 201, linked.text
    # ... and the model made live since without the NIEM pack that type belongs to.

    async def live(dataset_id: str) -> Any:
        return SimpleNamespace(packs=[])

    monkeypatch.setattr(pw.models, "live", live)
    (link,) = [i for i in _sheet(board)["items"] if i["kind"] == "link"]
    assert link["problems"] == ["CO_DEFENDANT_OF is not a link type of Prison intel's model."]
    refused = _promote(board, x["item_id"], y["item_id"], linked.json()["item_id"])
    assert refused.status_code == 422 and refused.json()["error"] == "check_failed"


def _the_real_link_types(pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Case-b's `LinkTypeService` itself, the shape production has (ADR-143 Amendment 5 decision
    9): its `promotion_refusals` answers `None` for every ontology type."""
    import asyncio

    from services.api.link_types import LinkTypeService

    from .test_link_type_service import Graph, MemoryStore, WorkingSet

    # On the app's own ontology, its packs included, as the lifespan builds it.
    service = LinkTypeService(
        MemoryStore(), app.state.ontology, Graph(), WorkingSet(), pw.cases,  # type: ignore[arg-type]
        models=pw.models,
    )  # fmt: skip
    asyncio.run(service.refresh())
    monkeypatch.setattr(app.state, "link_types", service, raising=False)
    return service


def _an_ontology_type_outside_the_model(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> tuple[str, list[str]]:
    board = _board()
    x, y = _item(board), _item(board, label="Y", properties={"family_name": "Y"})
    linked = _link(board, x["element_id"], y["element_id"], type="CO_DEFENDANT_OF")
    assert linked.status_code == 201, linked.text

    async def live(dataset_id: str) -> Any:
        # The model made live without the NIEM pack that type belongs to, as the real store's
        # `TargetModel` reads (the real service reads its extensions too).
        return SimpleNamespace(packs=[], extensions=[])

    monkeypatch.setattr(pw.models, "live", live)
    _the_real_link_types(pw, monkeypatch)
    return board, [x["item_id"], y["item_id"], linked.json()["item_id"]]


def test_c14_holds_through_the_real_link_type_service(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Blocker 1 of the independent review: the real service answers `None` for an ontology
    type, which must not stand in for the model's own check."""
    board, ticked = _an_ontology_type_outside_the_model(pw, monkeypatch)
    (link,) = [i for i in _sheet(board)["items"] if i["kind"] == "link"]
    assert link["problems"] == ["CO_DEFENDANT_OF is not a link type of Prison intel's model."]
    refused = _promote(board, *ticked)
    assert refused.status_code == 422 and refused.json()["error"] == "check_failed"
    assert pw.graph.promotions == 0


def test_the_c14_check_fails_with_refusals_standing_in_for_the_model(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The plant: the shape before the review, any type `promotion_refusals` answered skipping
    # the model's check.
    monkeypatch.setattr(
        Promotions, "model_check_applies", lambda self, name, refusals: name not in refusals
    )
    board, ticked = _an_ontology_type_outside_the_model(pw, monkeypatch)
    assert _promote(board, *ticked).status_code == 201


# --- rule 4: every route refuses whom it is not for ------------------------------------------


def test_every_promotion_route_refuses_a_non_member_as_a_missing_case(pw: SimpleNamespace) -> None:
    _policy(pw, "second_person_reviews")
    board, made, link_item, _ = _drawn()
    promotion = _promote(board, made["item_id"], link_item).json()["id"]
    # Carol: a member of B, reading the same source, no level on K.
    for answer in (
        _as("carol").get(f"/v1/investigations/{K}/boards/{board}/promotion-sheet"),
        _as("carol").post(f"/v1/investigations/{K}/boards/{board}/promotions",
                          json={"item_ids": [made["item_id"]]}),
        _as("carol").get(f"/v1/investigations/{K}/boards/{board}/promotions"),
    ):  # fmt: skip
        assert answer.status_code == 404, answer.text
    # Zed: another unit; the dataset's gate is not for him, whatever the id.
    for path in ("", f"/{promotion}"):
        assert _studio("zed", path).status_code == 404
    assert _studio("zed", f"/{promotion}/decision", "post", approve=True).status_code == 404
    assert _as("zed").get("/v1/datasets/src/removed-cases").status_code == 404
    # ...and every removed-case route of the dataset, whatever the ids (the independent review).
    for method, path in (
        ("post", f"/v1/datasets/src/removed-cases/{K}/merge-sheet"),
        ("delete", f"/v1/datasets/src/removed-cases/{K}/layer"),
        ("get", "/v1/datasets/src/layer-merges/any-grant"),
        ("post", "/v1/datasets/src/layer-merges/any-grant"),
        ("delete", "/v1/datasets/src/layer-merges/any-grant"),
    ):
        kwargs = {"json": {"item_ids": []}} if path.endswith("any-grant") and method == "post" else {}
        assert getattr(_as("zed"), method)(path, **kwargs).status_code == 404, (method, path)
    # A promotion of another dataset is not found through this one.
    assert _as("dana").get("/v1/datasets/src/promotions/no-such").status_code == 404
    # Bob, K's Editor, may not promote (Author level, I12); Rita, a Viewer, neither.
    assert (
        _as("bob").get(f"/v1/investigations/{K}/boards/{board}/promotion-sheet").status_code == 403
    )
    bob_sends = _as("bob").post(f"/v1/investigations/{K}/boards/{board}/promotions",
                                json={"item_ids": [made["item_id"]]})  # fmt: skip
    assert bob_sends.status_code == 403 and len(pw.store.records) == 1


# --- a removed case's layer (Amendment 2 decision 1) -----------------------------------------


def _removed_with_items(pw: SimpleNamespace) -> tuple[dict[str, Any], dict[str, Any]]:
    board = _board()
    first, second = _item(board), _item(board, label="Second", properties={"family_name": "S"})
    pw.removed.add(K)
    return first, second


def test_an_author_merges_a_removed_cases_layer_through_a_grant_that_ends_with_the_merge(
    pw: SimpleNamespace,
) -> None:
    first, second = _removed_with_items(pw)
    (row,) = _as("dana").get("/v1/datasets/src/removed-cases").json()["cases"]
    assert row["investigation_id"] == K and row["mergeable"] and row["items"] == 2
    # Read across cases Dana is no member of: audited, as Admin's own list is (review item 8).
    assert "list_removed_case_layers" in [r["action"] for r in pw.audit.records]
    sheet = _as("dana").post(f"/v1/datasets/src/removed-cases/{K}/merge-sheet").json()
    assert {i["item_id"] for i in sheet["items"]} == {first["item_id"], second["item_id"]}
    assert "open_layer_merge" in [r["action"] for r in pw.audit.records]
    grant = sheet["grant_id"]
    merged = _as("dana").post(f"/v1/datasets/src/layer-merges/{grant}",
                              json={"item_ids": [first["item_id"]]})  # fmt: skip
    assert merged.status_code == 201 and merged.json()["trigger"] == "layer_merge"
    assert merged.json()["status"] == "committed"
    assert _carol_sees_it_from_b(first["element_id"])
    assert not _carol_sees_it_from_b(second["element_id"])
    reread = _as("dana").get(f"/v1/datasets/src/layer-merges/{grant}")
    assert reread.status_code == 403 and reread.json()["error"] == "no_open_grant"


def test_the_merge_grant_check_fails_with_the_grant_kept(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def kept(self: InMemoryPromotionStore, grant_id: str, at: datetime) -> None:
        return None

    monkeypatch.setattr(InMemoryPromotionStore, "close_grant", kept)
    first, _ = _removed_with_items(pw)
    grant = _as("dana").post(f"/v1/datasets/src/removed-cases/{K}/merge-sheet").json()["grant_id"]
    _as("dana").post(
        f"/v1/datasets/src/layer-merges/{grant}", json={"item_ids": [first["item_id"]]}
    )
    assert _as("dana").get(f"/v1/datasets/src/layer-merges/{grant}").status_code == 200


def test_a_merge_waits_for_review_under_the_policy_and_its_grant_ends_when_it_is_sent(
    pw: SimpleNamespace,
) -> None:
    """One grant, one merge (spec 03, Amendment 5 decision 7): sent for review, the grant is
    closed to a second merge and to reading the layer through it; the reviewer approves as a
    reviewer reads."""
    _policy(pw, "second_person_reviews")
    first, second = _removed_with_items(pw)
    grant = _as("dana").post(f"/v1/datasets/src/removed-cases/{K}/merge-sheet").json()["grant_id"]
    merged = _as("dana").post(f"/v1/datasets/src/layer-merges/{grant}",
                              json={"item_ids": [first["item_id"]]}).json()  # fmt: skip
    assert merged["status"] == "awaiting_review" and not _carol_sees_it_from_b(first["element_id"])
    again = _as("dana").post(f"/v1/datasets/src/layer-merges/{grant}",
                             json={"item_ids": [second["item_id"]]})  # fmt: skip
    assert again.status_code == 403 and again.json()["error"] == "no_open_grant"
    assert [r.trigger for r in pw.store.records.values()] == ["layer_merge"]
    reread = _as("dana").get(f"/v1/datasets/src/layer-merges/{grant}")
    assert reread.status_code == 403 and reread.json()["error"] == "no_open_grant"
    assert _studio("dana", f"/{merged['id']}/decision", "post", approve=True).status_code == 403
    assert _studio("sam", f"/{merged['id']}/decision", "post", approve=True).status_code == 200
    assert _carol_sees_it_from_b(first["element_id"])


def test_a_layer_merge_is_refused_to_a_non_author_and_for_an_open_case(pw: SimpleNamespace) -> None:
    _board()
    # Strict (minor 12): an open case answers exactly as an id no case reading the dataset has.
    opened = _as("dana").post(f"/v1/datasets/src/removed-cases/{K}/merge-sheet")
    unknown = _as("dana").post("/v1/datasets/src/removed-cases/no-such-case/merge-sheet")
    assert opened.status_code == unknown.status_code == 404
    assert opened.json() == unknown.json()
    assert _as("dana").post(f"/v1/datasets/src/removed-cases/{K}/delete/dry-run").json() == _as(
        "dana"
    ).post("/v1/datasets/src/removed-cases/no-such-case/delete/dry-run").json()


def test_an_open_cases_layer_is_never_deleted_from_the_studio(pw: SimpleNamespace) -> None:
    """The destructive path (the lane review, finding 6): Delete on an open case answers as an
    unknown id does, 404, and withdraws nothing."""
    board = _board()
    drawn = _item(board)
    deleted = _as("dana").delete(f"/v1/datasets/src/removed-cases/{K}/layer")
    unknown = _as("dana").delete("/v1/datasets/src/removed-cases/no-such-case/layer")
    assert deleted.status_code == unknown.status_code == 404
    assert deleted.json() == unknown.json()
    assert not pw.graph.node(drawn["element_id"]).audit.reverted
    assert pw.items.items[drawn["item_id"]].withdrawn_at is None
    assert "delete_layer" not in [r["action"] for r in pw.audit.records]
    pw.removed.add(K)
    answer = _as("fred").post(f"/v1/datasets/src/removed-cases/{K}/merge-sheet")
    assert answer.status_code == 403 and answer.json()["error"] == "not_an_author"
    assert "open_layer_merge" not in [r["action"] for r in pw.audit.records]


def test_a_reports_viewer_who_is_an_author_writes_nothing_to_a_removed_cases_layer(
    pw: SimpleNamespace,
) -> None:
    """ADR-112 (a Reports Viewer is refused every write) and ADR-146 decision 10 (read-only): one
    of the dataset's Authors holding only `reports_viewer` opens no merge, merges, cancels, deletes
    nor runs the delete's dry run (403 `right_required`, before anything is read or granted). The
    round 2 review's item 2; whether owning alone should do is the owner's open question."""
    PEOPLE["vic"] = Principal(id="vic", clearance="SECRET", org_unit=UNIT, roles=["reports_viewer"])
    pw.cases.grants[HOME]["vic"] = AccessLevel.AUTHOR
    try:
        first, _ = _removed_with_items(pw)
        for method, path in (
            ("post", f"/v1/datasets/src/removed-cases/{K}/merge-sheet"),
            ("post", f"/v1/datasets/src/removed-cases/{K}/delete/dry-run"),
            ("delete", f"/v1/datasets/src/removed-cases/{K}/layer"),
            ("post", "/v1/datasets/src/layer-merges/any-grant"),
            ("delete", "/v1/datasets/src/layer-merges/any-grant"),
        ):
            kwargs = {"json": {"item_ids": []}} if method == "post" and "layer-merges" in path else {}
            answer = getattr(_as("vic"), method)(path, **kwargs)
            assert answer.status_code == 403, (method, path, answer.text)
        assert not pw.store.grants
        assert not pw.graph.node(first["element_id"]).audit.reverted
    finally:
        del PEOPLE["vic"]


def _composite(pw: SimpleNamespace, case: str) -> None:
    """`mix`, a composite of `src` with its own home case (Dana an Author of both), read by `case`."""
    pw.datasets.add(
        Dataset(id="mix", name="Mixed", owning_unit=UNIT, created_by="eng",
                created_at=datetime(2026, 11, 1, tzinfo=UTC), kind=COMPOSITE, members=["src"])
    )  # fmt: skip
    pw.datasets.cases[HOME + "-mix"] = ["mix"]
    pw.cases.seed(HOME + "-mix", {"dana": AccessLevel.AUTHOR})
    pw.datasets.homes["mix"] = HomeCase(
        dataset_id="mix", investigation_id=HOME + "-mix", made_at=datetime.now(UTC), made_by="dana"
    )
    if case not in pw.cases.grants:
        pw.cases.seed(case, {"alice": AccessLevel.AUTHOR})
    pw.datasets.cases[case] = ["mix"]


def _removed_composite_case(pw: SimpleNamespace) -> None:
    _composite(pw, "case-c")
    board = _board(case="case-c")
    _item(board, case="case-c")
    pw.removed.add("case-c")


def test_a_composite_cases_layer_is_never_merged_only_deleted(pw: SimpleNamespace) -> None:
    _removed_composite_case(pw)
    (row,) = _as("dana").get("/v1/datasets/mix/removed-cases").json()["cases"]
    assert not row["mergeable"] and "never merged" in row["why_not"]
    refused = _as("dana").post("/v1/datasets/mix/removed-cases/case-c/merge-sheet")
    assert refused.status_code == 409 and refused.json()["error"] == "composite_never_merged"
    assert not pw.store.grants and "open_layer_merge" not in [r["action"] for r in pw.audit.records]
    deleted = _as("dana").delete("/v1/datasets/mix/removed-cases/case-c/layer")
    assert deleted.status_code == 200 and "deleted" in deleted.json()["words"]


def test_the_composite_merge_check_fails_with_the_check_removed(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The plant at the route's call site (`open_layer_merge`'s `is_composite`)."""
    from services.api import app as app_module

    monkeypatch.setattr(app_module, "is_composite", lambda _d: False)
    _removed_composite_case(pw)
    opened = _as("dana").post("/v1/datasets/mix/removed-cases/case-c/merge-sheet")
    assert opened.status_code == 200, opened.text


def test_a_composite_cases_layer_is_not_merged_from_a_member_datasets_studio(
    pw: SimpleNamespace,
) -> None:
    """The realistic path: case-c reads `mix`, of which `src` is a member, and `src`'s Author tries
    the merge from `src`'s own Studio. case-c reads `src` only through `mix`, so `src` lists it not
    and answers it as an id no case reading it has: nothing granted, nothing audited as opened."""
    _removed_composite_case(pw)
    assert _as("dana").get("/v1/datasets/src/removed-cases").json()["cases"] == []
    refused = _as("dana").post("/v1/datasets/src/removed-cases/case-c/merge-sheet")
    assert refused.status_code == 404 and refused.json()["error"] == "case_not_linked"
    assert not pw.store.grants and "open_layer_merge" not in [r["action"] for r in pw.audit.records]


def test_the_member_path_check_fails_with_a_case_through_a_composite_taken(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The plant at its call site: `_removed_case` taking a case that reads the dataset through a
    composite as one reading it directly."""
    from services.api import app as app_module

    real = app_module._linked_cases

    async def direct(*args: Any, **kwargs: Any) -> Any:
        return [c.model_copy(update={"through": None}) for c in await real(*args, **kwargs)]

    monkeypatch.setattr(app_module, "_linked_cases", direct)
    _removed_composite_case(pw)
    opened = _as("dana").post("/v1/datasets/src/removed-cases/case-c/merge-sheet")
    assert opened.status_code == 200, opened.text


def test_a_case_reading_a_composite_promotes_nothing_from_its_boards(pw: SimpleNamespace) -> None:
    """`Promotions._target`: a composite holds none of its members' data, so a case reading one is
    offered no promotion and refused one at the route."""
    _composite(pw, K)
    board = _board()
    made = _item(board)
    sheet = _sheet(board)
    assert not sheet["items"] and "promotes nothing" in sheet["refused"]
    answer = _promote(board, made["item_id"])
    assert answer.status_code == 409 and answer.json()["error"] == "nothing_to_promote_into"
    assert not pw.store.records and pw.graph.promotions == 0
    assert "mix" not in _node_datasets(pw, made["element_id"])


def test_the_board_composite_check_fails_with_the_check_removed(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The plant at `_target`'s call site."""
    monkeypatch.setattr(promotions_module, "is_composite", lambda _d: False)
    _composite(pw, K)
    board = _board()
    assert _sheet(board).get("refused") is None


def test_deleting_a_layer_leaves_what_was_promoted_from_it(pw: SimpleNamespace) -> None:
    board, made, link_item, _ = _drawn()
    assert _promote(board, made["item_id"], link_item).json()["status"] == "committed"
    spare = _item(board, label="Spare", properties={"family_name": "Spare"})
    pw.removed.add(K)
    deleted = _as("dana").delete(f"/v1/datasets/src/removed-cases/{K}/layer")
    assert deleted.status_code == 200, deleted.text
    assert set(deleted.json()) == {"investigation_id", "words"}  # rule 7: no count
    assert pw.graph.node(spare["element_id"]).audit.reverted
    assert _carol_sees_it_from_b(made["element_id"])
    assert pw.items.items[spare["item_id"]].withdrawn_at is not None
    actions = [r["action"] for r in pw.audit.records]
    assert "delete_layer" in actions


def test_the_delete_check_fails_with_the_layer_withdrawn_whole(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph = pw.graph

    async def whole(dataset_id: str, withdrawal: str, tx: str) -> PromotionReverted:
        nodes = [n.id for n in graph._graph_nodes.values() if dataset_id in n.datasets]
        edges = [e.id for e in graph._graph_edges if dataset_id in e.datasets]
        graph._pending[tx][2].append((nodes, edges, withdrawal))
        return PromotionReverted(nodes=len(nodes), edges=len(edges))

    monkeypatch.setattr(graph, "withdraw_layer", whole)
    board, made, link_item, _ = _drawn()
    _promote(board, made["item_id"], link_item)
    pw.removed.add(K)
    _as("dana").delete(f"/v1/datasets/src/removed-cases/{K}/layer")
    assert not _carol_sees_it_from_b(made["element_id"])


# --- revert (the operator command's core) ----------------------------------------------------


async def test_reverting_a_promotion_leaves_the_items_in_the_layer_and_clears_the_registry(
    pw: SimpleNamespace,
) -> None:
    board, made, link_item, _ = _drawn()
    promotion = _promote(board, made["item_id"], link_item).json()["id"]
    from services.api.app import get_boards  # the board service as a route builds it
    from services.api.dataset_scope import stamping

    boards = get_boards(SimpleNamespace(app=app), stamping(pw.graph, registry=pw.datasets),
                        pw.views, pw.items, pw.datasets, app.state.ontology,
                        app.state.handling_scheme, pw.models)  # type: ignore[arg-type]  # fmt: skip
    from scripts.revert_promotion import revert_promotion  # the operator module's own core

    async def revert(record: Any) -> Any:
        return await revert_promotion(record, boards.graph, pw.store, boards.items)

    reverted = await revert(pw.store.records[promotion])
    assert reverted.status == "reverted"
    layer = pw.items.items[made["item_id"]].dataset_id
    assert _node_datasets(pw, made["element_id"]) == [layer]
    assert not _carol_sees_it_from_b(made["element_id"])
    assert pw.items.items[made["item_id"]].promoted_at is None
    with pytest.raises(promotions_module.PromotionRefused):
        await revert(pw.store.records[promotion])


# --- admin's ageing seam (ADR-145 Amendment 6) -----------------------------------------------


def _seam(pw: SimpleNamespace) -> Any:
    """The seam as the lifespan builds it (`app.waiting_promotions_seam`)."""
    from services.api import app as app_module

    return app_module.waiting_promotions_seam(
        pw.store, pw.datasets, pw.cases, None, app.state.handling_scheme
    )


async def test_the_waiting_seam_lists_only_those_who_may_review_it(pw: SimpleNamespace) -> None:
    """ADR-145 Amendment 4 decision 11 through the lifespan's own wiring: dana (an Author of the
    home case, holding review_promotions, cleared) is listed it; erin (an Author, below the
    dataset's highest marking), fred (holding review_promotions, not an Author) and zed (another
    unit) are not, though the items themselves are OFFICIAL. The contract's nine readers are
    `test_waiting_promotions_contract.py`'s."""
    _policy(pw, "second_person_reviews")
    board = _board()
    _promote(board, _item(board)["item_id"])
    pw.datasets.datasets["src"] = pw.datasets.datasets["src"].model_copy(update={"highest_marking": "SECRET"})
    seam = _seam(pw)
    assert len(await seam.waiting_for_review(PEOPLE["dana"])) == 1
    for who in ("erin", "fred", "zed"):
        assert await seam.waiting_for_review(PEOPLE[who]) == [], who
    (waiting,) = await seam.all_waiting()
    assert (waiting.dataset_name, waiting.proposed_by, waiting.dataset_marking) == (
        "Prison intel", "alice", "SECRET"
    )


async def test_the_waiting_seam_reads_the_datasets_unit_as_it_is_now(pw: SimpleNamespace) -> None:
    """A dataset moved to another unit after the promotion was sent is reviewed by the new unit's
    people, not the old: the seam reads the dataset's owning unit now, never the one recorded."""
    _policy(pw, "second_person_reviews")
    board = _board()
    _promote(board, _item(board)["item_id"])
    pw.datasets.datasets["src"] = pw.datasets.datasets["src"].model_copy(update={"owning_unit": "unit-2"})
    assert await _seam(pw).waiting_for_review(PEOPLE["dana"]) == []
    (waiting,) = await _seam(pw).all_waiting()
    assert waiting.dataset_unit == "unit-2"


async def test_a_waiting_promotion_whose_dataset_is_gone_is_said_not_dropped(
    pw: SimpleNamespace, caplog: pytest.LogCaptureFixture
) -> None:
    """Rule 2: the sweep is not handed a promotion whose dataset is no longer held, and the log
    says which one."""
    _policy(pw, "second_person_reviews")
    board = _board()
    _promote(board, _item(board)["item_id"])
    del pw.datasets.datasets["src"]
    with caplog.at_level("WARNING", logger="services.api.promotion_store"):
        assert await _seam(pw).all_waiting() == []
    assert "no longer held" in caplog.text


# --- the operator command (scripts.revert_promotion) -----------------------------------------


async def _run_the_command(
    pw: SimpleNamespace, load_id: str, *, dry_run: bool, conduit: str = "stopped"
) -> int:
    from scripts.revert_promotion import run
    from services.api.dataset_scope import stamping

    cleared: list[bool] = []

    async def invalidate() -> None:
        cleared.append(True)

    code = await run(
        load_id, reverted_by="ops", dry_run=dry_run, store=pw.store,
        graph=stamping(pw.graph, registry=pw.datasets), items=pw.items, audit=pw.audit,
        invalidate=invalidate, conduit=lambda: _answers((conduit, "planted")),
    )  # fmt: skip
    pw.cleared = cleared
    return code


async def _answers(value: Any) -> Any:
    return value


async def test_the_commands_dry_run_writes_nothing_and_the_real_run_reverts(
    pw: SimpleNamespace,
) -> None:
    board, made, link_item, _ = _drawn()
    promoted = _promote(board, made["item_id"], link_item).json()

    assert await _run_the_command(pw, promoted["load_id"], dry_run=True) == 0
    assert "revert_promotion" not in [r["action"] for r in pw.audit.records] and not pw.cleared
    assert _carol_sees_it_from_b(made["element_id"])
    assert pw.store.records[promoted["id"]].status == "committed"

    assert await _run_the_command(pw, promoted["load_id"], dry_run=False) == 0
    assert not _carol_sees_it_from_b(made["element_id"])
    assert pw.store.records[promoted["id"]].status == "reverted" and pw.cleared
    assert "revert_promotion" in [r["action"] for r in pw.audit.records]
    assert await _run_the_command(pw, promoted["load_id"], dry_run=False) == 1
    assert await _run_the_command(pw, "promotion-none", dry_run=False) == 1


async def test_the_dry_run_check_fails_with_the_dry_run_writing(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.revert_promotion as command

    # The plant: the command's one dry-run stop made to stop nothing, as a dry run that writes.
    monkeypatch.setattr(command, "stop_if_dry", lambda dry_run, says: False)
    board, made, link_item, _ = _drawn()
    promoted = _promote(board, made["item_id"], link_item).json()
    await _run_the_command(pw, promoted["load_id"], dry_run=True)
    assert not _carol_sees_it_from_b(made["element_id"])


# --- the review's findings: the layer routes, the grant, the revert's guards -------------------


def test_every_layer_route_refuses_whom_it_is_not_for(pw: SimpleNamespace) -> None:
    _removed_with_items(pw)
    grant = _as("dana").post(f"/v1/datasets/src/removed-cases/{K}/merge-sheet").json()["grant_id"]
    layer = f"/v1/datasets/src/layer-merges/{grant}"
    # Fred: a data engineer reading `src`, no Author of it.
    for answer in (
        _as("fred").get("/v1/datasets/src/removed-cases"),
        _as("fred").post(f"/v1/datasets/src/removed-cases/{K}/delete/dry-run"),
        _as("fred").delete(f"/v1/datasets/src/removed-cases/{K}/layer"),
        _as("fred").get(layer),
    ):
        assert answer.status_code == 403 and answer.json()["error"] == "not_an_author", answer.text
    # Sam: another of the dataset's Authors, who does not hold this merge's grant.
    for answer in (_as("sam").get(layer), _as("sam").post(layer, json={"item_ids": ["x"]}),
                   _as("sam").delete(layer)):  # fmt: skip
        assert answer.status_code == 403 and answer.json()["error"] == "no_open_grant", answer.text
    # Zed: another unit; the dataset's gate answers as for no dataset.
    for answer in (_as("zed").get(layer), _as("zed").delete(f"/v1/datasets/src/removed-cases/{K}/layer"),
                   _as("zed").post(f"/v1/datasets/src/removed-cases/{K}/delete/dry-run")):  # fmt: skip
        assert answer.status_code == 404, answer.text
    assert not any(pw.graph.node(n).audit.reverted for n in pw.graph._graph_nodes)


def test_an_authors_delete_has_its_dry_run_first_which_writes_nothing(pw: SimpleNamespace) -> None:
    first, _ = _removed_with_items(pw)
    dry = _as("dana").post(f"/v1/datasets/src/removed-cases/{K}/delete/dry-run")
    assert dry.status_code == 200, dry.text
    assert dry.json()["items"] == 2 and "Nothing has been written" in dry.json()["would"]
    assert not pw.graph.node(first["element_id"]).audit.reverted
    assert "dry_run_layer_delete" in [r["action"] for r in pw.audit.records]


def test_the_removed_cases_count_is_only_what_the_author_may_see(pw: SimpleNamespace) -> None:
    board = _board()
    _item(board)
    _item(board, marking="OFFICIAL-SENSITIVE", label="High", properties={"family_name": "H"})
    pw.removed.add(K)
    (dana,) = _as("dana").get("/v1/datasets/src/removed-cases").json()["cases"]
    (erin,) = _as("erin").get("/v1/datasets/src/removed-cases").json()["cases"]
    assert (dana["items"], erin["items"]) == (2, 1)
    sheet = _as("erin").post(f"/v1/datasets/src/removed-cases/{K}/merge-sheet").json()
    assert [i["label"] for i in sheet["items"]] == ["Unknown male “Tall”"]


def test_a_merge_grant_ends_after_a_working_day(pw: SimpleNamespace) -> None:
    from datetime import timedelta

    _removed_with_items(pw)
    grant = _as("dana").post(f"/v1/datasets/src/removed-cases/{K}/merge-sheet").json()["grant_id"]
    held = pw.store.grants[grant]
    pw.store.grants[grant] = replace(held, opened_at=held.opened_at - timedelta(hours=9))
    stale = _as("dana").get(f"/v1/datasets/src/layer-merges/{grant}")
    assert stale.status_code == 403 and stale.json()["error"] == "no_open_grant"


def test_a_case_restored_since_its_sheet_was_opened_is_not_merged(pw: SimpleNamespace) -> None:
    first, _ = _removed_with_items(pw)
    grant = _as("dana").post(f"/v1/datasets/src/removed-cases/{K}/merge-sheet").json()["grant_id"]
    pw.removed.discard(K)  # the case is restored
    answer = _as("dana").post(f"/v1/datasets/src/layer-merges/{grant}",
                              json={"item_ids": [first["item_id"]]})  # fmt: skip
    assert answer.status_code == 404 and answer.json()["error"] == "case_not_linked"
    assert pw.store.grants[grant].closed_at is not None and pw.graph.promotions == 0


def test_deleting_a_layer_closes_its_open_merge(pw: SimpleNamespace) -> None:
    _removed_with_items(pw)
    grant = _as("dana").post(f"/v1/datasets/src/removed-cases/{K}/merge-sheet").json()["grant_id"]
    assert _as("sam").delete(f"/v1/datasets/src/removed-cases/{K}/layer").status_code == 200
    assert _as("dana").get(f"/v1/datasets/src/layer-merges/{grant}").status_code == 403


async def test_a_revert_is_refused_while_another_link_rests_on_its_items(
    pw: SimpleNamespace,
) -> None:
    board, made, link_item, _ = _drawn()
    promoted = _promote(board, made["item_id"], link_item).json()
    # Carol, in case B, reads the promoted node now and draws a link to it in B's layer.
    b_board = _board("carol", B, start="selection", node_ids=[made["element_id"]])
    b_drawn = _item(b_board, "carol", B)["element_id"]
    linked = _as("carol").post(
        f"/v1/investigations/{B}/boards/{b_board}/links",
        json={"type": "ASSOCIATE_OF", "label": "x", "marking": "OFFICIAL",
              "grading": {"source": "B", "intelligence": "2", "handling": "1"},
              "source_note": "n", "source": b_drawn, "target": made["element_id"]},
    )  # fmt: skip
    assert linked.status_code == 201, linked.text
    assert await _run_the_command(pw, promoted["load_id"], dry_run=False) == 1
    assert pw.store.records[promoted["id"]].status == "committed"
    assert _carol_sees_it_from_b(made["element_id"])
    # Audited before it was tried, so its refusal is audited too (the trail says it did not
    # happen).
    actions = [r["action"] for r in pw.audit.records]
    assert actions.index("revert_promotion") < actions.index("revert_promotion_refused")


async def test_the_resting_link_check_fails_with_the_check_removed(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    board, made, link_item, _ = _drawn()
    promoted = _promote(board, made["item_id"], link_item).json()
    b_board = _board("carol", B, start="selection", node_ids=[made["element_id"]])
    b_drawn = _item(b_board, "carol", B)["element_id"]
    _as("carol").post(
        f"/v1/investigations/{B}/boards/{b_board}/links",
        json={"type": "ASSOCIATE_OF", "label": "x", "marking": "OFFICIAL",
              "grading": {"source": "B", "intelligence": "2", "handling": "1"},
              "source_note": "n", "source": b_drawn, "target": made["element_id"]},
    )  # fmt: skip

    async def none(node_ids: Any, tx: Any = None) -> set[str]:
        return set()

    monkeypatch.setattr(pw.graph, "live_edges_touching", none)  # the plant
    assert await _run_the_command(pw, promoted["load_id"], dry_run=False) == 0


async def test_a_revert_after_its_layer_was_deleted_takes_the_items_out_with_it(
    pw: SimpleNamespace,
) -> None:
    board, made, link_item, _ = _drawn()
    promoted = _promote(board, made["item_id"], link_item).json()
    pw.removed.add(K)
    assert _as("dana").delete(f"/v1/datasets/src/removed-cases/{K}/layer").status_code == 200
    assert not pw.graph.node(made["element_id"]).audit.reverted  # promoted: untouched
    assert await _run_the_command(pw, promoted["load_id"], dry_run=False) == 0
    assert pw.graph.node(made["element_id"]).audit.reverted
    assert pw.items.items[made["item_id"]].withdrawn_at is not None


# --- a gazetteer dataset takes nothing drawn (ADR-147 Amendment 1 decision 2; P4) ------------

GAZ = "gazetteer-osm-test"


def _gazetteer(pw: SimpleNamespace, case: str) -> None:
    pw.datasets.add(
        Dataset(id=GAZ, name="Places", owning_unit=UNIT, created_by="eng",
                created_at=datetime(2026, 11, 1, tzinfo=UTC))
    )  # fmt: skip
    pw.datasets.cases[HOME + "-gaz"] = [GAZ]
    pw.cases.seed(HOME + "-gaz", {"dana": AccessLevel.AUTHOR})
    pw.datasets.homes[GAZ] = HomeCase(
        dataset_id=GAZ, investigation_id=HOME + "-gaz", made_at=datetime.now(UTC), made_by="dana"
    )
    pw.datasets.cases[case] = [GAZ]


def test_nothing_drawn_is_promoted_into_a_gazetteer_dataset(pw: SimpleNamespace) -> None:
    _gazetteer(pw, K)
    board = _board()
    made = _item(board)
    sheet = _sheet(board)
    assert not sheet["items"] and "gazetteer dataset holds only the places" in sheet["refused"]
    answer = _promote(board, made["item_id"])
    assert answer.status_code == 409 and answer.json()["error"] == "nothing_to_promote_into"
    assert not pw.store.records and pw.graph.promotions == 0
    assert GAZ not in _node_datasets(pw, made["element_id"])


def test_the_gazetteer_check_fails_with_the_check_removed(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(promotions_module, "is_gazetteer", lambda _d: False)
    _gazetteer(pw, K)
    board = _board()
    made = _item(board)
    assert _promote(board, made["item_id"]).status_code == 201


def test_a_removed_cases_layer_is_never_merged_into_a_gazetteer_dataset(
    pw: SimpleNamespace,
) -> None:
    pw.cases.seed("case-g", {"alice": AccessLevel.AUTHOR})
    _gazetteer(pw, "case-g")
    board = _board(case="case-g")
    _item(board, case="case-g")
    pw.removed.add("case-g")
    (row,) = _as("dana").get(f"/v1/datasets/{GAZ}/removed-cases").json()["cases"]
    assert not row["mergeable"] and "gazetteer dataset" in row["why_not"]
    refused = _as("dana").post(f"/v1/datasets/{GAZ}/removed-cases/case-g/merge-sheet")
    assert refused.status_code == 409 and refused.json()["error"] == "gazetteer_never_merged"
    assert "open_layer_merge" not in [r["action"] for r in pw.audit.records]
    deleted = _as("dana").delete(f"/v1/datasets/{GAZ}/removed-cases/case-g/layer")
    assert deleted.status_code == 200 and "deleted" in deleted.json()["words"]


def test_the_gazetteer_merge_check_fails_with_the_check_removed(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    from services.api import app as app_module

    monkeypatch.setattr(app_module, "is_gazetteer", lambda _d: False)
    pw.cases.seed("case-g", {"alice": AccessLevel.AUTHOR})
    _gazetteer(pw, "case-g")
    board = _board(case="case-g")
    _item(board, case="case-g")
    pw.removed.add("case-g")
    opened = _as("dana").post(f"/v1/datasets/{GAZ}/removed-cases/case-g/merge-sheet")
    assert opened.status_code == 200, opened.text


# --- a restored case, and the grant's end whatever ends the merge (round 2) -----------------


def test_a_case_restored_since_its_sheet_was_opened_is_not_read_through_its_grant(
    pw: SimpleNamespace,
) -> None:
    _removed_with_items(pw)
    grant = _as("dana").post(f"/v1/datasets/src/removed-cases/{K}/merge-sheet").json()["grant_id"]
    pw.removed.discard(K)  # the case is restored: its layer is its members' alone again
    answer = _as("dana").get(f"/v1/datasets/src/layer-merges/{grant}")
    assert answer.status_code == 404 and answer.json()["error"] == "case_not_linked"
    assert pw.store.grants[grant].closed_at is not None
    # Removed again, the old grant stays closed: it is never reopened.
    pw.removed.add(K)
    assert _as("dana").get(f"/v1/datasets/src/layer-merges/{grant}").status_code == 403


def test_the_restored_read_check_fails_with_the_check_removed(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def always(self: Promotions, case_id: str) -> bool:
        return True

    monkeypatch.setattr(Promotions, "case_still_removed", always)  # the plant
    _removed_with_items(pw)
    grant = _as("dana").post(f"/v1/datasets/src/removed-cases/{K}/merge-sheet").json()["grant_id"]
    pw.removed.discard(K)
    assert _as("dana").get(f"/v1/datasets/src/layer-merges/{grant}").status_code == 200


def _merge_waiting(pw: SimpleNamespace, **item: Any) -> tuple[str, str, dict[str, Any]]:
    _policy(pw, "second_person_reviews")
    board = _board()
    first = _item(board, **item)
    pw.removed.add(K)
    grant = _as("dana").post(f"/v1/datasets/src/removed-cases/{K}/merge-sheet").json()["grant_id"]
    merged = _as("dana").post(f"/v1/datasets/src/layer-merges/{grant}",
                              json={"item_ids": [first["item_id"]]})  # fmt: skip
    assert merged.status_code == 201 and merged.json()["status"] == "awaiting_review", merged.text
    return merged.json()["id"], grant, first


def test_a_merge_waiting_for_review_is_not_approved_once_its_case_is_restored(
    pw: SimpleNamespace,
) -> None:
    promotion, grant, first = _merge_waiting(pw)
    pw.removed.discard(K)
    answer = _studio("sam", f"/{promotion}/decision", "post", approve=True)
    assert answer.status_code == 409 and answer.json()["error"] == "case_open"
    assert pw.store.records[promotion].status == "rejected"
    assert pw.store.grants[grant].closed_at is not None
    assert pw.graph.promotions == 0 and not _carol_sees_it_from_b(first["element_id"])
    # The state change has its audit entry.
    assert "promotion_rejected" in [r["action"] for r in pw.audit.records]


def test_the_restored_approval_check_fails_with_the_check_removed(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    promotion, _, first = _merge_waiting(pw)
    pw.removed.discard(K)

    async def always(self: Promotions, case_id: str) -> bool:
        return True

    monkeypatch.setattr(Promotions, "case_still_removed", always)  # the plant
    assert _studio("sam", f"/{promotion}/decision", "post", approve=True).status_code == 200
    assert _carol_sees_it_from_b(first["element_id"])


def test_a_merge_rejected_by_the_approvals_recheck_closes_its_grant(pw: SimpleNamespace) -> None:
    promotion, grant, _ = _merge_waiting(pw, marking="OFFICIAL-SENSITIVE")
    held = pw.datasets.datasets["src"]
    pw.datasets.datasets["src"] = held.model_copy(update={"highest_marking": "OFFICIAL"})
    answer = _studio("sam", f"/{promotion}/decision", "post", approve=True)
    assert answer.status_code == 409 and answer.json()["error"] == "items_changed"
    assert pw.store.records[promotion].status == "rejected"
    assert pw.store.grants[grant].closed_at is not None
    stale = _as("dana").get(f"/v1/datasets/src/layer-merges/{grant}")
    assert stale.status_code == 403 and stale.json()["error"] == "no_open_grant"
    assert "promotion_rejected" in [r["action"] for r in pw.audit.records]


def _reject_keeping_the_grant(monkeypatch: pytest.MonkeyPatch) -> None:
    """The plant: a rejection recorded without its grant closed, as before round 2."""

    async def kept(self: Promotions, record: Any, *, was: str, by: Any, reason: str,
                   audited_by_route: bool = False, check: Any = None) -> bool:  # fmt: skip
        return await self.store.decide(record.id, was=was, now="rejected", by=by,
                                       at=datetime.now(UTC), reason=reason)  # fmt: skip

    monkeypatch.setattr(Promotions, "reject", kept)


def test_the_one_merge_check_fails_with_the_grant_kept_at_send(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The plant for blocker 2: a grant not closed when its merge is sent for review lets a second
    merge through it, a second promotion of the same layer."""

    async def kept(self: InMemoryPromotionStore, grant_id: str, at: datetime) -> None:
        return None

    monkeypatch.setattr(InMemoryPromotionStore, "close_grant", kept)
    _policy(pw, "second_person_reviews")
    first, second = _removed_with_items(pw)
    grant = _as("dana").post(f"/v1/datasets/src/removed-cases/{K}/merge-sheet").json()["grant_id"]
    for item in (first, second):
        _as("dana").post(f"/v1/datasets/src/layer-merges/{grant}", json={"item_ids": [item["item_id"]]})
    assert len(pw.store.records) == 2


def test_a_merge_whose_load_is_refused_closes_its_grant(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, _ = _removed_with_items(pw)
    grant = _as("dana").post(f"/v1/datasets/src/removed-cases/{K}/merge-sheet").json()["grant_id"]
    _withdrawn_behind_the_sheet(pw, monkeypatch, first["element_id"])
    answer = _as("dana").post(f"/v1/datasets/src/layer-merges/{grant}",
                              json={"item_ids": [first["item_id"]]})  # fmt: skip
    assert answer.status_code == 409 and answer.json()["error"] == "items_changed"
    assert pw.store.grants[grant].closed_at is not None
    assert "promotion_rejected" in [r["action"] for r in pw.audit.records]


def test_the_refused_load_grant_check_fails_with_the_grant_kept(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reject_keeping_the_grant(monkeypatch)
    first, _ = _removed_with_items(pw)
    grant = _as("dana").post(f"/v1/datasets/src/removed-cases/{K}/merge-sheet").json()["grant_id"]
    _withdrawn_behind_the_sheet(pw, monkeypatch, first["element_id"])
    _as("dana").post(
        f"/v1/datasets/src/layer-merges/{grant}", json={"item_ids": [first["item_id"]]}
    )
    assert pw.store.grants[grant].closed_at is None


def test_deleting_a_layer_rejects_what_still_waits_from_it(pw: SimpleNamespace) -> None:
    promotion, _, _ = _merge_waiting(pw)
    assert _as("sam").delete(f"/v1/datasets/src/removed-cases/{K}/layer").status_code == 200
    record = pw.store.records[promotion]
    assert record.status == "rejected" and "layer was deleted" in (record.reason or "")
    assert not [r for r in await_waiting(pw)]


def await_waiting(pw: SimpleNamespace) -> list[Any]:
    return [r for r in pw.store.records.values() if r.status == "awaiting_review"]


def test_the_deleted_layer_check_fails_with_nothing_found_waiting(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def none(self: Any, layer_id: str) -> list[Any]:
        return []

    monkeypatch.setattr(InMemoryPromotionStore, "waiting_from_layer", none)  # the plant
    promotion, _, _ = _merge_waiting(pw)
    _as("sam").delete(f"/v1/datasets/src/removed-cases/{K}/layer")
    assert pw.store.records[promotion].status == "awaiting_review"


def test_reading_a_merge_sheet_through_its_grant_is_audited(pw: SimpleNamespace) -> None:
    _removed_with_items(pw)
    grant = _as("dana").post(f"/v1/datasets/src/removed-cases/{K}/merge-sheet").json()["grant_id"]
    assert _as("dana").get(f"/v1/datasets/src/layer-merges/{grant}").status_code == 200
    assert "read_layer_merge" in [r["action"] for r in pw.audit.records]


def test_the_delete_dry_run_says_what_goes_not_a_count_deleted(pw: SimpleNamespace) -> None:
    _removed_with_items(pw)
    dry = _as("dana").post(f"/v1/datasets/src/removed-cases/{K}/delete/dry-run").json()
    assert "Would delete" not in dry["would"] and "withdraws those not promoted" in dry["would"]


# --- what follows a node, and only its own (round 1's fix, its test in round 2) -------------


def _picture(board: str, node_id: str) -> None:
    uploaded = _as("alice").put(
        f"/v1/investigations/{K}/boards/{board}/nodes/{node_id}/picture",
        params={"name": "tall.png", "marking": "OFFICIAL", "source_note": "Gate camera"},
        content=b"\x89PNG drawn",
    )
    assert uploaded.status_code == 201, uploaded.text


def _depicts(pw: SimpleNamespace) -> str:
    (depicts,) = [e for e in pw.graph.edges() if e.type == "DEPICTS"]
    return str(depicts.id)


def test_a_picture_goes_with_its_own_node_and_never_with_another(pw: SimpleNamespace) -> None:
    board = _board()
    x = _item(board)
    y = _item(board, label="Y", properties={"family_name": "Y"})
    _picture(board, x["element_id"])
    # Y alone: X's picture stays behind with X.
    alone = _promote(board, y["item_id"]).json()
    assert _depicts(pw) not in pw.store.records[alone["id"]].edge_ids
    # X: its picture goes with it, Document and all.
    with_x = pw.store.records[_promote(board, x["item_id"]).json()["id"]]
    assert _depicts(pw) in with_x.edge_ids


def _picture_follows_any_landed_node(monkeypatch: pytest.MonkeyPatch) -> None:
    real = Promotions.ends_land

    def loose(item: Any, lands: set[str], going: set[str]) -> bool:
        if item.kind == "picture":
            return item.target in lands  # the plant: any node in the dataset, going or not
        return real(item, lands, going)

    monkeypatch.setattr(Promotions, "ends_land", staticmethod(loose))


def test_a_picture_added_after_its_node_went_waits_for_its_own_promotion(
    pw: SimpleNamespace,
) -> None:
    board = _board()
    x = _item(board)
    y = _item(board, label="Y", properties={"family_name": "Y"})
    assert _promote(board, x["item_id"]).status_code == 201
    _picture(board, x["element_id"])
    later = pw.store.records[_promote(board, y["item_id"]).json()["id"]]
    assert _depicts(pw) not in later.edge_ids


def test_the_picture_check_fails_with_a_picture_following_any_landed_node(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    _picture_follows_any_landed_node(monkeypatch)
    board = _board()
    x = _item(board)
    y = _item(board, label="Y", properties={"family_name": "Y"})
    assert _promote(board, x["item_id"]).status_code == 201
    _picture(board, x["element_id"])
    later = pw.store.records[_promote(board, y["item_id"]).json()["id"]]
    assert _depicts(pw) in later.edge_ids


def _same_decided_after_its_node_went(pw: SimpleNamespace) -> tuple[str, dict[str, Any]]:
    board = _board(start="selection", node_ids=["p-loaded"])
    mercer = _item(board, label="Mercer", properties={"family_name": "Mercer"})
    assert _promote(board, mercer["item_id"]).status_code == 201
    decided = _as("alice").post(
        f"/v1/investigations/{K}/boards/{board}/matches",
        json={"drawn": mercer["element_id"], "loaded": "p-loaded", "same": True},
    )
    assert decided.status_code == 201, decided.text
    other = _item(board, label="Other", properties={"family_name": "Other"})
    return board, other


def test_a_same_decided_later_never_goes_with_an_unrelated_promotion(pw: SimpleNamespace) -> None:
    board, other = _same_decided_after_its_node_went(pw)
    (same,) = [e.id for e in pw.graph.edges() if e.type == "SAME_AS"]
    later = pw.store.records[_promote(board, other["item_id"]).json()["id"]]
    assert same not in later.edge_ids


def test_the_match_check_fails_with_a_match_following_any_promotion(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = Promotions.ends_land

    def loose(item: Any, lands: set[str], going: set[str]) -> bool:
        if item.kind == "match":
            return item.source in lands and item.target in lands  # the plant: `going` dropped
        return real(item, lands, going)

    monkeypatch.setattr(Promotions, "ends_land", staticmethod(loose))
    board, other = _same_decided_after_its_node_went(pw)
    (same,) = [e.id for e in pw.graph.edges() if e.type == "SAME_AS"]
    later = pw.store.records[_promote(board, other["item_id"]).json()["id"]]
    assert same in later.edge_ids


# --- the sheet lists only what its proposer may see now (round 1's fix) --------------------


def _above_alices_clearance(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Two of Alice's items; one raised in the graph to SECRET, and Alice's clearance lowered to
    OFFICIAL-SENSITIVE since (vetting reviewed): she may not see that one now."""
    board = _board()
    seen = _item(board)
    hidden = _item(board, label="Hidden", properties={"family_name": "Hidden"})
    node = pw.graph.node(hidden["element_id"])
    pw.graph._graph_nodes[hidden["element_id"]] = node.model_copy(
        update={"handling": node.handling.model_copy(update={"classification": "SECRET"})}
    )
    lowered = PEOPLE["alice"].model_copy(update={"clearance": "OFFICIAL-SENSITIVE"})
    monkeypatch.setitem(PEOPLE, "alice", lowered)
    return board, seen, hidden


def test_the_sheet_lists_only_what_its_proposer_may_see_now(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    board, seen, hidden = _above_alices_clearance(pw, monkeypatch)
    sheet = _sheet(board)
    assert [i["item_id"] for i in sheet["items"]] == [seen["item_id"]]
    assert all("Hidden" not in i["label"] for i in sheet["items"])
    # Ticked by id all the same, it is no item of theirs.
    assert _promote(board, hidden["item_id"]).status_code == 404


def test_the_seen_check_fails_with_every_item_listed(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def every(self: Promotions, case_id: str, board_id: Any, reader: Principal) -> Any:
        return await self._read(await self._pending_items(case_id, board_id), reader)

    monkeypatch.setattr(Promotions, "_seen", every)  # the plant
    board, seen, hidden = _above_alices_clearance(pw, monkeypatch)
    assert hidden["item_id"] in [i["item_id"] for i in _sheet(board)["items"]]


# --- the independent review of L3.4 ---------------------------------------------------------


def _rejected_with_words(pw: SimpleNamespace) -> str:
    """Sent for review, then rejected by Dana with free words naming the item."""
    _policy(pw, "second_person_reviews")
    board = _board()
    made = _item(board, label="Hidden Name", properties={"family_name": "Hidden"})
    promotion = _promote(board, made["item_id"]).json()["id"]
    rejected = _studio("dana", f"/{promotion}/decision", "post", approve=False,
                       reason="Hidden Name is not who we think")  # fmt: skip
    assert rejected.status_code == 200, rejected.text
    return promotion


def test_a_rejections_words_and_proposer_reach_no_reader_who_may_not_know_the_case(
    pw: SimpleNamespace,
) -> None:
    """Blocker 2 (rule 3): Fred reads `src` but is none of its Authors and no member of K."""
    promotion = _rejected_with_words(pw)
    (freds,) = _studio("fred").json()["promotions"]
    assert freds["id"] == promotion and freds["status"] == "rejected"
    assert freds["reason"] is None and freds["proposed_by"] == ""
    assert "alice" not in freds["proposed_by_name"] and "Hidden" not in str(freds)
    # The dataset's Authors, who answer for it, read the reason and who sent it.
    (danas,) = _studio("dana").json()["promotions"]
    assert danas["reason"] == "Hidden Name is not who we think" and danas["proposed_by"] == "alice"


def test_the_withheld_reason_check_fails_with_every_reader_shown_the_case(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = Promotions.view

    async def everyone(self: Promotions, record: Any, reader: Any, **kw: Any) -> Any:
        return await real(self, record, reader, **{**kw, "show_case": True})

    monkeypatch.setattr(Promotions, "view", everyone)  # the plant, at the routes' call
    _rejected_with_words(pw)
    (freds,) = _studio("fred").json()["promotions"]
    assert freds["reason"] == "Hidden Name is not who we think"


def test_a_rejection_by_a_check_records_fixed_words(pw: SimpleNamespace) -> None:
    """The record keeps no label, count or check's words: the reviewer is told which and why."""
    _policy(pw, "second_person_reviews")
    board = _board()
    made = _item(board, marking="OFFICIAL-SENSITIVE", label="Hidden Name",
                 properties={"family_name": "Hidden"})  # fmt: skip
    promotion = _promote(board, made["item_id"]).json()["id"]
    held = pw.datasets.datasets["src"]
    pw.datasets.datasets["src"] = held.model_copy(update={"highest_marking": "OFFICIAL"})
    answer = _studio("dana", f"/{promotion}/decision", "post", approve=True)
    assert answer.status_code == 409 and "Hidden Name" in answer.json()["detail"]
    reason = pw.store.records[promotion].reason or ""
    assert reason == promotions_module._CHANGED
    assert "Hidden" not in reason and "OFFICIAL" not in reason
    # The audit says which check, for the dataset's other Authors; never the label.
    (entry,) = [r for r in pw.audit.records if r["action"] == "promotion_rejected"]
    assert entry["resolved_query"]["check"] == "marking" and "Hidden" not in str(entry)


async def test_the_revert_is_refused_unless_the_conduit_is_known_stopped(
    pw: SimpleNamespace,
) -> None:
    board, made, link_item, _ = _drawn()
    promoted = _promote(board, made["item_id"], link_item).json()
    for state in ("running", "unknown"):
        code = await _run_the_command(pw, promoted["load_id"], dry_run=False, conduit=state)
        assert code == 1, state
    assert pw.store.records[promoted["id"]].status == "committed"
    assert _carol_sees_it_from_b(made["element_id"])
    assert "revert_promotion" not in [r["action"] for r in pw.audit.records]
    # Its dry run writes nothing and needs no stop.
    assert await _run_the_command(pw, promoted["load_id"], dry_run=True, conduit="running") == 0


async def test_the_conduit_is_stopped_only_where_its_host_resolves_and_nothing_listens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`conduit_state` itself, never stubbed: fails closed (the lane review, finding 2)."""
    import asyncio
    import socket

    from scripts.revert_promotion import conduit_state

    with socket.socket() as probe:  # a port nothing listens on
        probe.bind(("127.0.0.1", 0))
        free = probe.getsockname()[1]
    monkeypatch.setenv("OSPREY_CONDUIT_URL", f"http://127.0.0.1:{free}")
    assert (await conduit_state())[0] == "stopped"
    monkeypatch.setenv("OSPREY_CONDUIT_URL", "http://no-such-conduit.invalid:8000")
    assert (await conduit_state())[0] == "unknown"

    async def answer(reader: Any, writer: Any) -> None:
        await reader.read(1024)
        writer.write(b"HTTP/1.1 200 OK\r\ncontent-length: 2\r\n\r\nok")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(answer, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    monkeypatch.setenv("OSPREY_CONDUIT_URL", f"http://127.0.0.1:{port}")
    try:
        assert (await conduit_state())[0] == "running"
    finally:
        server.close()
        await server.wait_closed()


async def test_the_revert_reads_its_resting_links_inside_its_own_transaction(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """At the command's call site (the lane review, finding 4): the resting-link read is given
    the very transaction the revert then writes and commits in."""
    board, made, link_item, _ = _drawn()
    promoted = _promote(board, made["item_id"], link_item).json()
    graph = pw.graph
    opened: list[Any] = []
    asked: list[Any] = []
    real_begin, real_touching = graph.begin_transaction, graph.live_edges_touching

    async def begin() -> Any:
        opened.append(await real_begin())
        return opened[-1]

    async def touching(node_ids: Any, tx: Any = None) -> Any:
        asked.append(tx)
        return await real_touching(node_ids, tx=tx)

    monkeypatch.setattr(graph, "begin_transaction", begin)
    monkeypatch.setattr(graph, "live_edges_touching", touching)
    assert await _run_the_command(pw, promoted["load_id"], dry_run=False) == 0
    assert asked and asked[0] is not None and asked[0] in opened


def test_a_promotion_with_an_ambiguous_link_id_writes_nothing(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """As the adapter's `_holders`: an id two stored links hold refuses the whole load. The second
    holder appears after the route's checks (another type's link written under the same id), so
    only the graph's own refusal can catch it."""
    board, made, link_item, link = _drawn()
    graph = pw.graph
    real = type(graph).promote_elements

    async def racing(*args: Any) -> None:
        held = next(e for e in graph._graph_edges if e.id == link)
        graph._graph_edges.append(held.model_copy(update={"type": "KNOWS"}))
        await real(graph, *args)

    monkeypatch.setattr(graph, "promote_elements", racing)
    answer = _promote(board, made["item_id"], link_item)
    assert answer.status_code == 409 and answer.json()["error"] == "ambiguous_item"
    (record,) = pw.store.records.values()
    assert record.status == "rejected" and record.reason == "The load was refused, and nothing was written."
    assert not _carol_sees_it_from_b(made["element_id"])


def test_a_promotion_with_an_ambiguous_node_id_writes_nothing(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The node half of `_holders`' refusal, the fake refusing what the adapter refuses (the lane
    review, finding 8): a second stored type comes to hold the drawn node's id after the checks."""
    board, made, link_item, _ = _drawn()
    graph = pw.graph
    real = type(graph).promote_elements

    async def racing(*args: Any) -> None:
        graph.second_type_node_ids.add(made["element_id"])
        await real(graph, *args)

    monkeypatch.setattr(graph, "promote_elements", racing)
    answer = _promote(board, made["item_id"], link_item)
    assert answer.status_code == 409 and answer.json()["error"] == "ambiguous_item"
    (record,) = pw.store.records.values()
    assert record.status == "rejected" and not _carol_sees_it_from_b(made["element_id"])


def _a_cases_own_type_accepted_and_live(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> tuple[str, list[str]]:
    """K's own proposal, BRIBED (outside the ontology), and a BRIBED link drawn on a board of K
    while it waits (under its storage label, as decision 9 writes it); then accepted by Dana for
    `src` and made live in its model, through case-b's real service."""
    import asyncio

    from services.api.dataset_scope import set_case_datasets

    async def get(case_id: str) -> Any:
        return pw.cases.made[case_id]

    monkeypatch.setattr(pw.cases, "get", get, raising=False)  # what the real service also asks
    service = _the_real_link_types(pw, monkeypatch)
    board = _board()
    x, y = _item(board), _item(board, label="Y", properties={"family_name": "Y"})
    layer = pw.items.items[x["item_id"]].dataset_id
    alice = PEOPLE["alice"].model_copy(update={"datasets": ["src", layer]})
    set_case_datasets(["src", layer], layer=layer)
    try:
        proposal = asyncio.run(service.propose(
            K, alice, name="BRIBED", from_types=["Person"], to_types=["Person"], directed=True,
            colour=None, thickness=None, label=None, reason="Paid an officer to carry items in",
        ))  # fmt: skip
    finally:
        set_case_datasets(None)
    linked = _link(board, x["element_id"], y["element_id"], type="BRIBED")
    assert linked.status_code == 201, linked.text
    # Waiting, it does not go: decision 9's refusal, through the real service.
    (waiting,) = [i for i in _sheet(board)["items"] if i["kind"] == "link"]
    assert waiting["problems"] and "not yet accepted" in waiting["problems"][0]
    dana = PEOPLE["dana"].model_copy(update={"datasets": ["src"]})
    asyncio.run(service.accept("src", proposal.id, dana, basis="probabilistic", reason="Useful"))
    draft = asyncio.run(pw.models.draft("src"))
    assert draft is not None
    asyncio.run(pw.models.make_live("src", draft.version, dana))
    return board, [x["item_id"], y["item_id"], linked.json()["item_id"]]


def test_a_cases_own_accepted_and_live_type_is_promoted_through_the_real_service(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other branch of C14 (the lane review, finding 1): the case's own type, outside the
    ontology, accepted and live, goes; the ontology types' model check never refuses it."""
    board, ticked = _a_cases_own_type_accepted_and_live(pw, monkeypatch)
    (link,) = [i for i in _sheet(board)["items"] if i["kind"] == "link"]
    assert link["problems"] == [], link
    answer = _promote(board, *ticked)
    assert answer.status_code == 201, answer.text
    assert answer.json()["links"] == 1


def test_the_proposed_type_branch_fails_with_the_model_check_applied_to_every_type(
    pw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    board, ticked = _a_cases_own_type_accepted_and_live(pw, monkeypatch)
    monkeypatch.setattr(Promotions, "model_check_applies", lambda self, name, refusals: True)
    refused = _promote(board, *ticked)
    assert refused.status_code == 422 and refused.json()["error"] == "check_failed"
