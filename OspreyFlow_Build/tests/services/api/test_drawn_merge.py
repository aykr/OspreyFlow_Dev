"""A drawn dataset merged into another, through the real app (ADR-143 Amendment 2 decisions 6 and 7;
Amendment 3 decision 2; L3.9).

The world is `test_promotions.py`'s (case K and B on the source dataset `src`, its home case with
Dana (SECRET), Erin (OFFICIAL) and Sam as Authors, Fred a data engineer who is no Author of it),
and here: Alice's drawing *Night visits*, a drawn dataset with its home case, shared (Viewer) with
the people below so that each reads it as any reader does; Ann, an analyst who is an Author of
`src` (no `merge_datasets`); Olga, an administrator who is neither; and a loaded Mercer of another
dataset, `other`.

What a mistake here would do, and the case that catches it (each red by its plant, below or in
`process/lanes/case/L3.9_RED_RECORD.md`):

- a merge by someone Amendment 3 does not name: `test_every_step_names_merge_datasets`,
  `test_a_holder_of_merge_datasets_who_is_no_author_of_the_target_is_answered_as_for_no_target`;
- a dataset's existence or kind told by the refusal (rule 3):
  `test_a_composite_a_gazetteer_and_another_units_dataset_are_answered_as_for_none`;
- an item above the target's highest marking merged: `test_an_item_above_the_targets_highest_...`;
- a match offered, counted or ordered across a node the merger may not see, or another dataset
  (rules 3 and 7): `test_no_match_is_offered_from_a_node_the_merger_may_not_see_or_another_dataset`,
  red with the candidates read unscoped (`test_the_match_check_fails_with_the_candidates_unscoped`);
- a dry run that writes, or counts what the merger may not see: `test_the_dry_run_...`;
- a match collapsed in storage or promoted past a person (rules 5, 6): `test_author_promotes_...`;
- the drawing not becoming a case view with its annotations (decision 7): the same, and
  `test_an_annotation_is_withheld_from_a_reader_who_may_not_see_its_item`;
- a merge written before a second person approves: `test_under_second_person_reviews_...`.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from schemas.dataset_model import HomeCase
from schemas.domain import SAME_AS, Principal, ProvenanceState
from services.api.boards import Boards
from services.api.datasets import COMPOSITE, Dataset
from services.api.investigations import AccessLevel

from .test_boards import GRADE, PEOPLE, UNIT, _as, _item, _loaded
from .test_promotions import HOME, pw, world  # noqa: F401  (the fixtures)

PEOPLE.update(
    {
        "ann": Principal(id="ann", clearance="SECRET", org_unit=UNIT, roles=["analyst"]),
        "olga": Principal(id="olga", clearance="SECRET", org_unit=UNIT, roles=["osprey-admin"]),
        # A data engineer holding a level on the target's home case below Author.
        "vic": Principal(id="vic", clearance="SECRET", org_unit=UNIT, roles=["data_engineer"]),
    }
)
STEPS = ("targets", "sheet", "dry_run", "merge")
OTHER_HOME = "home-other"


@pytest.fixture
def mw(pw: SimpleNamespace) -> Iterator[SimpleNamespace]:  # noqa: F811
    pw.cases.grants[HOME]["ann"] = AccessLevel.AUTHOR
    pw.cases.grants[HOME]["vic"] = AccessLevel.EDITOR
    # Another dataset Dana reads too, holding a Mercer of its own.
    pw.datasets.add(
        Dataset(id="other", name="Other intel", owning_unit=UNIT, created_by="eng",
                created_at=datetime(2026, 11, 1, tzinfo=UTC))
    )  # fmt: skip
    pw.cases.seed(OTHER_HOME, {"dana": AccessLevel.AUTHOR})
    pw.datasets.cases[OTHER_HOME] = ["other"]
    pw.graph._graph_nodes["p-other"] = _loaded("p-other", family_name="Mercer").model_copy(
        update={"datasets": ["other"]}
    )
    made = _as("alice").post(
        "/v1/drawings", json={"name": "Night visits", "highest_marking": "SECRET"}
    )
    assert made.status_code == 201, made.text
    body = made.json()
    home = body["investigation_id"]
    for who in ("dana", "erin", "fred", "ann", "olga", "sam", "vic"):
        pw.cases.grants[home][who] = AccessLevel.VIEWER
    yield SimpleNamespace(
        **vars(pw), drawn=body["dataset_id"], home=home, board=body["board"]["id"]
    )


def _draw(mw: SimpleNamespace, **over: Any) -> dict[str, Any]:
    return _item(mw.board, case=mw.home, **over)


def _three(mw: SimpleNamespace) -> SimpleNamespace:
    """A drawn Mercer (alike the loaded one), a drawn Tall, and a link between them."""
    mercer = _draw(mw, label="Mercer", properties={"family_name": "Mercer"})
    tall = _draw(mw)
    linked = _as("alice").post(
        f"/v1/investigations/{mw.home}/boards/{mw.board}/links",
        json={"type": "ASSOCIATE_OF", "label": "seen together", "marking": "OFFICIAL",
              "grading": GRADE, "source_note": "Visits log", "source": mercer["element_id"],
              "target": tall["element_id"]},
    )  # fmt: skip
    assert linked.status_code == 201, linked.text
    return SimpleNamespace(mercer=mercer, tall=tall, link=linked.json())


def _step(mw: SimpleNamespace, step: str, who: str, target: str = "src", **body: Any) -> Any:
    client = _as(who)
    base = f"/v1/datasets/{mw.drawn}"
    sent = {"target_dataset_id": target, "item_ids": ["x"], "matches": [], **body}
    if step == "targets":
        return client.get(f"{base}/merge-targets")
    if step == "sheet":
        return client.get(f"{base}/merge-sheet", params={"target": target})
    if step == "dry_run":
        return client.post(f"{base}/merges/dry-run", json=sent)
    return client.post(f"{base}/merges", json=sent)


def _nothing_written(mw: SimpleNamespace, *element_ids: str) -> None:
    assert mw.graph.promotions == 0
    assert mw.store.records == {}
    assert not [e for e in mw.graph.edges() if e.type == SAME_AS]
    for element in element_ids:
        assert mw.graph.node(element).datasets == [mw.drawn]
    assert mw.datasets.cases[mw.home] == [mw.drawn]
    assert mw.datasets.merged == {}


def _ids(drawn: SimpleNamespace) -> list[str]:
    return [drawn.mercer["item_id"], drawn.tall["item_id"], drawn.link["item_id"]]


# --- who may merge (Amendment 3 decision 2; rule 4) -------------------------------------------


@pytest.mark.parametrize("who", ["ann", "olga"])
@pytest.mark.parametrize("step", STEPS)
def test_every_step_names_merge_datasets(mw: SimpleNamespace, step: str, who: str) -> None:
    """Ann is an Author of the target without `merge_datasets`; Olga, an administrator who is
    neither: both refused before anything is read."""
    drawn = _three(mw)
    answer = _step(mw, step, who, item_ids=_ids(drawn))
    assert answer.status_code == 403, answer.text
    _nothing_written(mw, drawn.mercer["element_id"])


@pytest.mark.parametrize("who", ["fred", "vic"])
@pytest.mark.parametrize("step", ["sheet", "dry_run", "merge"])
def test_a_holder_of_merge_datasets_who_is_no_author_of_the_target_is_answered_as_for_no_target(
    mw: SimpleNamespace, step: str, who: str
) -> None:
    """Fred reads `src` through a case of his own; Vic is an Editor of its home case: neither is
    one of its Authors."""
    drawn = _three(mw)
    assert _step(mw, "targets", who).json()["targets"] == []
    into_src = _step(mw, step, who, item_ids=_ids(drawn))
    into_none = _step(mw, step, who, target="no-such-dataset", item_ids=_ids(drawn))
    assert into_src.status_code == 404, into_src.text
    # Rule 3: the same answer as for a dataset that does not exist.
    assert into_src.json() == into_none.json()
    _nothing_written(mw, drawn.mercer["element_id"])


@pytest.mark.parametrize("step", STEPS)
def test_a_reader_the_drawing_is_not_shared_with_is_answered_as_for_no_dataset(
    mw: SimpleNamespace, step: str
) -> None:
    drawn = _three(mw)
    del mw.cases.grants[mw.home]["dana"]
    answer = _step(mw, step, "dana", item_ids=_ids(drawn))
    assert answer.status_code == 404, answer.text
    _nothing_written(mw, drawn.mercer["element_id"])


def test_a_composite_a_gazetteer_and_another_units_dataset_are_answered_as_for_none(
    mw: SimpleNamespace,
) -> None:
    drawn = _three(mw)
    made = datetime(2026, 11, 1, tzinfo=UTC)
    others = [
        Dataset(id="comp", name="Both", owning_unit=UNIT, created_by="eng", created_at=made,
                kind=COMPOSITE, members=["src", "other"]),
        Dataset(id="gazetteer-uk", name="Places", owning_unit=UNIT, created_by="eng",
                created_at=made),
        Dataset(id="far", name="Far", owning_unit="unit-2", created_by="eng", created_at=made),
    ]  # fmt: skip
    for dataset in others:
        mw.datasets.add(dataset)
        home = f"home-{dataset.id}"
        mw.cases.seed(home, {"dana": AccessLevel.AUTHOR})
        mw.datasets.cases[home] = [dataset.id]
        mw.datasets.homes[dataset.id] = HomeCase(
            dataset_id=dataset.id, investigation_id=home, made_at=made, made_by="dana"
        )
    listed = [t["dataset_id"] for t in _step(mw, "targets", "dana").json()["targets"]]
    assert listed == ["src"]  # `other` has no home case: Dana is no Author of it
    none = _step(mw, "merge", "dana", target="no-such-dataset", item_ids=_ids(drawn))
    for dataset in [*others, mw.datasets.datasets["other"]]:
        answer = _step(mw, "merge", "dana", target=dataset.id, item_ids=_ids(drawn))
        assert (answer.status_code, answer.json()) == (404, none.json()), dataset.id
    _nothing_written(mw, drawn.mercer["element_id"])


# --- the target's highest marking (ADR-145 decision 8) ---------------------------------------


def test_an_item_above_the_targets_highest_marking_refuses_the_merge_and_writes_nothing(
    mw: SimpleNamespace,
) -> None:
    """`src` holds nothing above OFFICIAL-SENSITIVE; the drawing, up to SECRET."""
    drawn = _three(mw)
    secret = _draw(mw, label="Courier", marking="SECRET")
    sheet = _step(mw, "sheet", "dana").json()
    (shown,) = [i for i in sheet["items"] if i["item_id"] == secret["item_id"]]
    assert shown["problems"] == [
        "Marked SECRET, above Prison intel's highest allowed marking, OFFICIAL-SENSITIVE."
    ]
    # The route's own check (the sheet bypassed), and the dry run's.
    for step in ("dry_run", "merge"):
        answer = _step(mw, step, "dana", item_ids=[*_ids(drawn), secret["item_id"]])
        assert answer.status_code == 422, answer.text
        assert answer.json()["error"] == "check_failed"
    _nothing_written(mw, drawn.mercer["element_id"], secret["element_id"])


# --- matching (decision 6; rules 3, 5, 6, 7) --------------------------------------------------


def _drawn_hidden(mw: SimpleNamespace) -> dict[str, Any]:
    """A drawn person alike the SECRET loaded `p-secret` (family name Hidden)."""
    return _draw(mw, label="Hidden", properties={"family_name": "Hidden"})


class _Calls:
    """Every graph read the merge makes, by name and arguments, the reader left out."""

    def __init__(self, graph: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        self.calls: list[tuple[str, str]] = []
        for name in ("search_nodes", "suggest_nodes", "edges_among"):
            inner = getattr(graph, name)

            async def logged(*args: Any, _n: str = name, _f: Any = inner, **kw: Any) -> Any:
                shown = [a for a in args if not isinstance(a, Principal)]
                self.calls.append((_n, repr(shown)))
                return await _f(*args, **kw)

            monkeypatch.setattr(graph, name, logged)


def _sheet_for(mw: SimpleNamespace, who: str) -> dict[str, Any]:
    answer = _step(mw, "sheet", who)
    assert answer.status_code == 200, answer.text
    return dict(answer.json())


def test_no_match_is_offered_from_a_node_the_merger_may_not_see_or_another_dataset(
    mw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Erin (OFFICIAL) is offered Mercer alone: never the SECRET Hidden, never `other`'s Mercer.
    Her sheet, and the reads that make it, are the same with both of those absent from the store:
    neither is told by a count, an order or a timing (rule 7)."""
    drawn = _three(mw)
    hidden = _drawn_hidden(mw)
    calls = _Calls(mw.graph, monkeypatch)
    with_them = _sheet_for(mw, "erin")
    pairs = [(m["drawn"], m["loaded"]) for m in with_them["matches"]]
    assert pairs == [(drawn.mercer["element_id"], "p-loaded")]
    reads_with = list(calls.calls)

    secret, other = mw.graph._graph_nodes.pop("p-secret"), mw.graph._graph_nodes.pop("p-other")
    calls.calls.clear()
    without = _sheet_for(mw, "erin")
    assert json.dumps(without, sort_keys=True) == json.dumps(with_them, sort_keys=True)
    assert calls.calls == reads_with
    mw.graph._graph_nodes |= {"p-secret": secret, "p-other": other}

    # Dana (SECRET) is offered the Hidden match: the path works for whoever may see it; `other`'s
    # Mercer is offered to no one, Dana included, who may read `other`.
    dana = {(m["drawn"], m["loaded"]) for m in _sheet_for(mw, "dana")["matches"]}
    assert (hidden["element_id"], "p-secret") in dana
    assert not [p for p in dana if p[1] == "p-other"]


def test_the_match_check_fails_with_the_candidates_unscoped(
    mw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The plant, at `alike`'s own call: the candidates read through a principal of no dataset
    scope (the shape the code takes if the target scope is dropped)."""
    drawn = _three(mw)
    real = Boards.alike

    async def unscoped(self: Boards, nodes: Any, reading: Principal, decided: Principal) -> Any:
        return await real(self, nodes, reading.model_copy(update={"datasets": None}), decided)

    monkeypatch.setattr(Boards, "alike", unscoped)
    offered = {(m["drawn"], m["loaded"]) for m in _sheet_for(mw, "dana")["matches"]}
    assert (drawn.mercer["element_id"], "p-other") in offered


def test_a_chosen_match_not_offered_is_refused_alike_and_writes_nothing(
    mw: SimpleNamespace,
) -> None:
    drawn = _three(mw)
    hidden = _drawn_hidden(mw)
    ids = [*_ids(drawn), hidden["item_id"]]
    answers = [
        _step(mw, "merge", "erin", item_ids=ids, matches=[{"drawn": d, "loaded": n}])
        for d, n in [
            (hidden["element_id"], "p-secret"),  # above Erin
            (drawn.mercer["element_id"], "p-other"),  # another dataset
            (drawn.mercer["element_id"], "no-such-node"),  # none at all
        ]
    ]
    assert {(a.status_code, a.json()["error"]) for a in answers} == {(422, "not_a_match")}
    assert len({json.dumps(a.json()) for a in answers}) == 1
    _nothing_written(mw, drawn.mercer["element_id"])


# --- the dry run (decision 6 step 3) ----------------------------------------------------------


def test_the_dry_run_counts_only_what_the_merger_may_see_and_writes_nothing(
    mw: SimpleNamespace,
) -> None:
    mw.datasets.datasets["src"] = mw.datasets.datasets["src"].model_copy(
        update={"highest_marking": "SECRET"}
    )
    drawn = _three(mw)
    secret = _draw(mw, label="Courier", marking="SECRET")
    match = [{"drawn": drawn.mercer["element_id"], "loaded": "p-loaded"}]
    nodes_before, edges_before = dict(mw.graph._graph_nodes), list(mw.graph.edges())

    erin = _step(mw, "dry_run", "erin", item_ids=_ids(drawn), matches=match)
    assert erin.status_code == 200, erin.text
    assert (erin.json()["nodes"], erin.json()["links"], erin.json()["matches"]) == (2, 1, 1)
    # The SECRET item is neither counted nor named for Erin: not even among what is left out.
    assert "Courier" not in json.dumps(erin.json())
    assert erin.json()["left_out"] == []
    # Named by its id, it is as an id that does not exist.
    named = _step(mw, "dry_run", "erin", item_ids=[secret["item_id"]])
    unknown = _step(mw, "dry_run", "erin", item_ids=["no-such-item"])
    assert (named.status_code, named.json()) == (unknown.status_code, unknown.json())

    dana = _step(mw, "dry_run", "dana", item_ids=_ids(drawn), matches=match)
    assert [x["label"] for x in dana.json()["left_out"]] == ["Courier"]
    assert mw.graph._graph_nodes == nodes_before and mw.graph.edges() == edges_before
    _nothing_written(mw, drawn.mercer["element_id"], secret["element_id"])


# --- the merge, and the drawing after it (decisions 6 and 7) ----------------------------------


def _merge(mw: SimpleNamespace, drawn: SimpleNamespace, who: str = "dana", **over: Any) -> Any:
    match = [{"drawn": drawn.mercer["element_id"], "loaded": "p-loaded"}]
    return _step(mw, "merge", who, item_ids=_ids(drawn), matches=match, **over)


def _open_board_as_view(mw: SimpleNamespace, who: str = "alice") -> dict[str, Any]:
    opened = _as(who).get(f"/v1/investigations/{mw.home}/views/{mw.board}")
    assert opened.status_code == 200, opened.text
    return dict(opened.json())


def test_author_promotes_one_load_matches_inferred_and_the_drawing_becomes_a_view(
    mw: SimpleNamespace,
) -> None:
    drawn = _three(mw)
    left = _draw(mw, label="Unticked", source_note="Seen once")
    nodes_before = len(mw.graph._graph_nodes)

    answer = _merge(mw, drawn)

    assert answer.status_code == 201, answer.text
    body = answer.json()
    assert (body["trigger"], body["status"], body["nodes"], body["links"]) == (
        "drawn_merge", "committed", 2, 1,
    )  # fmt: skip
    assert mw.graph.promotions == 1
    for element in (drawn.mercer, drawn.tall):
        assert mw.graph.node(element["element_id"]).datasets == sorted([mw.drawn, "src"])
    assert mw.graph.node(left["element_id"]).datasets == [mw.drawn]
    # Rules 5 and 6: one scored, inferred SAME_AS in the target; both nodes stay, never merged.
    assert len(mw.graph._graph_nodes) == nodes_before
    (same,) = [e for e in mw.graph.edges() if e.type == SAME_AS]
    assert (same.source, same.target) == (drawn.mercer["element_id"], "p-loaded")
    assert same.provenance.state == ProvenanceState.INFERRED
    assert same.properties["score"] == 1.0 and same.datasets == ["src"]
    assert mw.store.matches[body["id"]][0].edge_id == same.id

    # Decision 7: the case reads the target (and its drawing, read-only); the board is a view.
    assert mw.datasets.cases[mw.home] == ["src"]
    assert mw.datasets.merged[mw.drawn].load_id == body["load_id"]
    view = mw.views.views[mw.board]
    assert (view.drawing, view.merged_load) == (False, body["load_id"])
    opened = _open_board_as_view(mw)
    shown = {n["id"] for n in opened["nodes"]}
    assert {drawn.mercer["element_id"], drawn.tall["element_id"], left["element_id"]} <= shown
    notes = {a["label"]: a for a in opened["annotations"]}
    assert set(notes) == {"Mercer", "Unknown male “Tall”", "seen together", "Unticked"}
    assert notes["Mercer"]["words"] == f"Drawn by alice, merged as load {body['load_id']}"
    assert notes["Mercer"]["source_note"] == "Wing officer report, 4 Nov"
    assert notes["Mercer"]["grading"] == "B21" and notes["Mercer"]["marking"] == "OFFICIAL"
    assert notes["Unticked"]["merged"] is False
    assert notes["Unticked"]["words"].startswith("Drawn by alice, not merged")
    assert notes["Unticked"]["source_note"] == "Seen once"


def test_a_merged_drawing_is_merged_no_more_and_draws_no_more(mw: SimpleNamespace) -> None:
    drawn = _three(mw)
    assert _merge(mw, drawn).status_code == 201
    # Read-only for its audit: no case loads into it now, so the Studio reaches it no more, for
    # any step, as a dataset no case of the reader's loads into.
    for step in STEPS:
        answer = _step(mw, step, "dana", item_ids=_ids(drawn))
        assert answer.status_code == 404, (step, answer.text)
    assert mw.graph.promotions == 1
    # The board is a view now: nothing more is drawn on it.
    more = _as("alice").post(
        f"/v1/investigations/{mw.home}/boards/{mw.board}/items",
        json={"type": "Person", "label": "Late", "marking": "OFFICIAL", "grading": GRADE,
              "source_note": "n", "properties": {"family_name": "Late"}},
    )  # fmt: skip
    assert more.status_code == 404, more.text


def test_an_annotation_is_withheld_from_a_reader_who_may_not_see_its_item(
    mw: SimpleNamespace,
) -> None:
    drawn = _three(mw)
    _draw(mw, label="Courier", marking="SECRET", source_note="Informant 7")
    assert _merge(mw, drawn).status_code == 201
    shared = _as("alice").post(f"/v1/investigations/{mw.home}/views/{mw.board}/share")
    assert shared.status_code == 200, shared.text
    erin = _open_board_as_view(mw, "erin")
    assert "Courier" not in json.dumps(erin) and "Informant 7" not in json.dumps(erin)
    assert {a["label"] for a in erin["annotations"]} == {
        "Mercer", "Unknown male “Tall”", "seen together",
    }  # fmt: skip
    assert "Courier" in {a["label"] for a in _open_board_as_view(mw)["annotations"]}


def test_under_second_person_reviews_nothing_is_written_until_an_author_approves(
    mw: SimpleNamespace,
) -> None:
    mw.datasets.datasets["src"] = mw.datasets.datasets["src"].model_copy(
        update={"promotion_policy": "second_person_reviews"}
    )
    drawn = _three(mw)
    sent = _merge(mw, drawn)
    assert sent.status_code == 201, sent.text
    assert sent.json()["status"] == "awaiting_review"
    assert mw.graph.promotions == 0 and not [e for e in mw.graph.edges() if e.type == SAME_AS]
    assert mw.graph.node(drawn.mercer["element_id"]).datasets == [mw.drawn]
    assert mw.datasets.cases[mw.home] == [mw.drawn]
    # A second merge waits for this one; its proposer may not approve it.
    again = _merge(mw, drawn)
    assert (again.status_code, again.json()["error"]) == (409, "merge_waiting")
    decision = f"/v1/datasets/src/promotions/{sent.json()['id']}/decision"
    own = _as("dana").post(decision, json={"approve": True})
    assert own.status_code == 403, own.text

    approved = _as("erin").post(decision, json={"approve": True})

    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "committed"
    assert mw.graph.node(drawn.mercer["element_id"]).datasets == sorted([mw.drawn, "src"])
    assert len([e for e in mw.graph.edges() if e.type == SAME_AS]) == 1
    assert mw.datasets.cases[mw.home] == ["src"]
    assert mw.views.views[mw.board].drawing is False


# --- the revert (decision 6 step 4: reverted as a promotion is) -------------------------------


def _merge_commit(mw: SimpleNamespace) -> Any:
    from services.api.app import app, get_boards  # the board service as a route builds it
    from services.api.dataset_scope import stamping
    from services.api.drawn_merge import MergeCommit

    boards = get_boards(SimpleNamespace(app=app), stamping(mw.graph, registry=mw.datasets),
                        mw.views, mw.items, mw.datasets, app.state.ontology,
                        app.state.handling_scheme, mw.models)  # type: ignore[arg-type]  # fmt: skip
    return boards, MergeCommit(
        promotions_store=mw.store, graph=boards.graph, datasets=mw.datasets, views=mw.views,
        items=mw.items, scheme=boards.scheme,
    )  # fmt: skip


async def test_reverting_a_merge_takes_back_the_load_its_matches_and_decision_7(
    mw: SimpleNamespace,
) -> None:
    from scripts.revert_promotion import revert_promotion  # the operator module's own core

    drawn = _three(mw)
    body = _merge(mw, drawn).json()
    boards, merge = _merge_commit(mw)
    record = mw.store.records[body["id"]]
    from services.api.promotions import PromotionRefused

    # Without its stores, a drawn merge's revert is refused before anything is written.
    with pytest.raises(PromotionRefused) as refused:
        await revert_promotion(record, boards.graph, mw.store, boards.items)
    assert refused.value.code == "no_merge"
    assert mw.graph.node(drawn.mercer["element_id"]).datasets == sorted([mw.drawn, "src"])

    reverted = await revert_promotion(record, boards.graph, mw.store, boards.items, merge)

    assert reverted.status == "reverted"
    assert mw.graph.node(drawn.mercer["element_id"]).datasets == [mw.drawn]
    (same,) = [e for e in mw.graph.edges() if e.type == SAME_AS]
    assert same.audit.reverted  # withdrawn with it, never deleted
    assert mw.datasets.cases[mw.home] == [mw.drawn] and mw.datasets.merged == {}
    view = mw.views.views[mw.board]
    assert (view.drawing, view.merged_load, view.merged_added) == (True, None, [])
    # Drawing again goes into the drawing, as before the merge.
    again = _draw(mw, label="After")
    assert mw.graph.node(again["element_id"]).datasets == [mw.drawn]
