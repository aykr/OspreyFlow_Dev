"""A drawn dataset merged into another, through the real app (ADR-143 Amendment 2 decisions 6 and 7;
Amendment 3 decision 2; L3.9).

The world is `test_promotions.py`'s (case K and B on the source dataset `src`, its home case with
Dana (SECRET), Erin (OFFICIAL) and Sam as Authors, Fred a data engineer who is no Author of it),
and here: Alice's drawing *Night visits*, a drawn dataset with its home case, shared (Viewer) with
the people below so that each reads it as any reader does; Ann, an analyst who is an Author of
`src` (no `merge_datasets`); Olga, an administrator who is neither; and a loaded Mercer of another
dataset, `other`.

What a mistake here would do, and the case that catches it (each red by its plant, below or in
`process/lanes/case/gates/L3.9-plants.txt`):

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
from services.api.boards import Boards
from services.api.datasets import COMPOSITE, Dataset
from services.api.investigations import AccessLevel

from schemas.dataset_model import HomeCase
from schemas.domain import SAME_AS, Principal, ProvenanceState

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


def _said(answer: Any) -> tuple[int, str | None]:
    """The status and the refusal's code, read so that an answer with none (a write that went
    through) fails on the comparison, never on a missing key."""
    return answer.status_code, answer.json().get("error")


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
        assert _said(answer) == (422, "check_failed"), answer.text
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
            (drawn.tall["element_id"], "p-loaded"),  # both seen, not alike: never offered
        ]
    ]
    assert {_said(a) for a in answers} == {(422, "not_a_match")}
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
    # Nothing written by it (checked here, before any other step reads the drawing again).
    assert mw.store.records == {} and mw.graph.node(drawn.mercer["element_id"]).datasets == [
        mw.drawn
    ]
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


def _share_view(mw: SimpleNamespace) -> None:
    shared = _as("alice").post(f"/v1/investigations/{mw.home}/views/{mw.board}/share")
    assert shared.status_code == 200, shared.text


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
    assert same.audit.load_id == body["load_id"]  # written with the load, read as the load's
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
    assert _said(again) == (409, "merge_waiting")
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


# --- the lane review's findings, each red by its plant (`gates/L3.9-plants.txt`) -------------


def test_after_a_merge_what_was_not_merged_is_edited_and_withdrawn_by_no_one(
    mw: SimpleNamespace,
) -> None:
    """Decision 7: the drawing is kept read-only for its audit (review item 3)."""
    drawn = _three(mw)
    left = _draw(mw, label="Unticked")
    assert _merge(mw, drawn).status_code == 201
    edited = _as("alice").patch(f"/v1/investigations/{mw.home}/board-items/{left['item_id']}",
                                json={"label": "Changed"})  # fmt: skip
    withdrawn = _as("alice").post(
        f"/v1/investigations/{mw.home}/board-items/{left['item_id']}/withdraw"
    )
    for answer in (edited, withdrawn):
        assert _said(answer) == (409, "drawing_merged"), answer.text
    held = mw.graph.node(left["element_id"])
    assert held.provenance.drawn.label == "Unticked" and not held.audit.reverted


def _target_packs(mw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, packs: list[str]) -> None:
    """`src`'s live model holds `packs` alone; the drawing's, NIEM (its starter pack)."""
    real = mw.models.live

    async def live(dataset_id: str) -> Any:
        if dataset_id == "src":
            return SimpleNamespace(packs=packs)
        if dataset_id == mw.drawn:
            return SimpleNamespace(packs=["niem"])
        return await real(dataset_id)

    monkeypatch.setattr(mw.models, "live", live)


def test_a_drawn_type_the_target_lacks_is_left_out_and_said(
    mw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    _target_packs(mw, monkeypatch, ["fibo"])
    drawn = _three(mw)
    incident = _draw(mw, type="Incident", label="Night fight", properties={})
    sheet = _sheet_for(mw, "dana")
    (row,) = [m for m in sheet["mapping"] if m["drawn_type"] == "Incident"]
    assert row["target_type"] is None and "Incident is not a type of Prison intel" in row["why_not"]
    person = [m for m in sheet["mapping"] if m["drawn_type"] == "Person"]
    assert person and person[0]["target_type"] == "Person"
    # The owner's ruling (Amendment 7): a type mapped onto none is left out with its reason, the
    # rest merged; never refused for it.
    answer = _step(mw, "merge", "dana", item_ids=[*_ids(drawn), incident["item_id"]])
    assert answer.status_code == 201, answer.text
    (why,) = [x["why"] for x in answer.json()["left_out"] if x["item_id"] == incident["item_id"]]
    assert "Its type, Incident, goes into no type of Prison intel (Map)" in why
    assert mw.graph.node(incident["element_id"]).datasets == [mw.drawn]
    assert "src" in mw.graph.node(drawn.mercer["element_id"]).datasets


def test_a_link_is_checked_against_the_targets_model_whatever_the_drawings_proposals_say(
    mw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review item 4: the drawing's own proposals answer for the drawing's model; a link of a type
    they answer for (`model_check_applies` false, as for a case's own proposed type) is still
    checked against the target's."""
    from services.api.promotions import Promotions

    from .test_promotions import _LinkTypes

    _target_packs(mw, monkeypatch, ["fibo"])
    mercer = _draw(mw, label="Mercer", properties={"family_name": "Mercer"})
    tall = _draw(mw)
    cell = _as("alice").post(
        f"/v1/investigations/{mw.home}/boards/{mw.board}/links",
        json={"type": "SHARED_CELL_WITH", "label": "same cell", "marking": "OFFICIAL",
              "grading": GRADE, "source_note": "Wing roll", "source": mercer["element_id"],
              "target": tall["element_id"]},
    )  # fmt: skip
    assert cell.status_code == 201, cell.text
    monkeypatch.setattr(app_state(), "link_types", _LinkTypes(None), raising=False)
    monkeypatch.setattr(Promotions, "model_check_applies", lambda self, name, refusals: False)
    # The owner's ruling (Amendment 7): what the target's model lacks is mapped onto none, and
    # said at Map; never proposed as itself because the drawing's proposals answer for it.
    sheet = _sheet_for(mw, "dana")
    (row,) = [m for m in sheet["mapping"] if m["drawn_type"] == "SHARED_CELL_WITH"]
    assert row["target_type"] is None
    assert "SHARED_CELL_WITH is not a link type of Prison intel's model" in row["why_not"]


def app_state() -> Any:
    from services.api.app import app

    return app.state


def _second_person(mw: SimpleNamespace) -> None:
    mw.datasets.datasets["src"] = mw.datasets.datasets["src"].model_copy(
        update={"promotion_policy": "second_person_reviews"}
    )


def test_a_reviewer_reads_the_matches_they_approve(mw: SimpleNamespace) -> None:
    """Review item 5: the matches are approved with the merge, so *Details* lists them."""
    _second_person(mw)
    drawn = _three(mw)
    sent = _merge(mw, drawn).json()
    details = _as("erin").get(f"/v1/datasets/src/promotions/{sent['id']}")
    assert details.status_code == 200, details.text
    shown = [(m["drawn"], m["loaded"], m["loaded_label"]) for m in details.json()["matches"]]
    assert shown == [(drawn.mercer["element_id"], "p-loaded", "Mercer")]
    assert details.json()["withheld"] is False


def test_a_waiting_merge_whose_match_changed_is_rejected_never_left_waiting(
    mw: SimpleNamespace,
) -> None:
    """Review item 6: the loaded end withdrawn while the merge waits refuses the load and records
    it rejected (Amendment 5 decision 6), so the drawing may be merged again."""
    _second_person(mw)
    drawn = _three(mw)
    sent = _merge(mw, drawn).json()
    loaded = mw.graph._graph_nodes["p-loaded"]
    mw.graph._graph_nodes["p-loaded"] = loaded.model_copy(
        update={"audit": loaded.audit.model_copy(update={"reverted": True})}
    )
    approved = _as("erin").post(f"/v1/datasets/src/promotions/{sent['id']}/decision",
                                json={"approve": True})  # fmt: skip
    assert _said(approved) == (409, "items_changed")
    assert mw.store.records[sent["id"]].status == "rejected"
    assert mw.graph.node(drawn.mercer["element_id"]).datasets == [mw.drawn]
    assert _step(mw, "merge", "dana", item_ids=_ids(drawn)).status_code == 201


def test_a_merge_whose_claim_fails_writes_no_graph_and_says_so(
    mw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review items 7 and 8: the drawing's one merge is claimed before the graph commits, so a
    second merge at once (the claim refused) writes nothing, and the case is not moved."""
    from services.api.datasets import DrawnAlreadyMerged

    drawn = _three(mw)

    async def taken(merged: Any) -> None:
        raise DrawnAlreadyMerged(merged.dataset_id)

    monkeypatch.setattr(mw.datasets, "merge_drawn", taken)
    answer = _merge(mw, drawn)
    assert _said(answer) == (409, "already_merged")
    assert mw.graph.node(drawn.mercer["element_id"]).datasets == [mw.drawn]
    assert not [e for e in mw.graph.edges() if e.type == SAME_AS]
    assert [r.status for r in mw.store.records.values()] == ["rejected"]
    assert mw.datasets.cases[mw.home] == [mw.drawn]


def test_a_merge_whose_graph_commit_fails_leaves_its_case_on_the_drawing(
    mw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    drawn = _three(mw)
    real = type(mw.graph).commit_transaction

    async def fails(self: Any, tx: str) -> None:
        if self.promotions:
            raise RuntimeError("the store went away")
        await real(self, tx)

    monkeypatch.setattr(type(mw.graph), "commit_transaction", fails)
    with pytest.raises(RuntimeError):
        _merge(mw, drawn)
    assert mw.datasets.cases[mw.home] == [mw.drawn] and mw.datasets.merged == {}
    assert [r.status for r in mw.store.records.values()] == ["rejected"]


def test_a_match_marked_above_the_targets_highest_or_of_an_unticked_item_is_refused(
    mw: SimpleNamespace,
) -> None:
    drawn = _three(mw)
    hidden = _drawn_hidden(mw)  # alike p-secret, SECRET, above src's OFFICIAL-SENSITIVE
    above = _step(mw, "merge", "dana", item_ids=[*_ids(drawn), hidden["item_id"]],
                  matches=[{"drawn": hidden["element_id"], "loaded": "p-secret"}])  # fmt: skip
    assert _said(above) == (422, "check_failed")
    assert "above Prison intel's highest allowed marking" in above.json()["detail"]
    mercer_match = [{"drawn": drawn.mercer["element_id"], "loaded": "p-loaded"}]
    unticked = _step(mw, "merge", "dana", item_ids=[drawn.tall["item_id"]], matches=mercer_match)
    assert _said(unticked) == (422, "not_a_match")
    tall_match = [{"drawn": drawn.tall["element_id"], "loaded": "p-loaded"}]
    alike_not = _step(mw, "merge", "dana", item_ids=_ids(drawn), matches=tall_match)
    assert _said(alike_not) == (422, "not_a_match")
    _nothing_written(mw, drawn.mercer["element_id"])


def test_the_view_keeps_its_sharing_and_drawing_again_opens_a_new_board_from_it(
    mw: SimpleNamespace,
) -> None:
    drawn = _three(mw)
    shared = _as("alice").post(f"/v1/investigations/{mw.home}/boards/{mw.board}/share")
    assert shared.status_code == 200, shared.text
    body = _merge(mw, drawn).json()
    assert mw.views.views[mw.board].shared is True
    assert _open_board_as_view(mw, "erin")["view"]["merged_load"] == body["load_id"]
    again = _as("alice").post(
        f"/v1/investigations/{mw.home}/boards",
        json={"name": "Again", "start": "view", "view_id": mw.board},
    )
    assert again.status_code == 201, again.text
    item = _item(again.json()["id"], case=mw.home, label="Later")
    # Into the case's layer now: the drawing is read-only, the target is loaded data.
    datasets = mw.graph.node(item["element_id"]).datasets
    assert mw.drawn not in datasets and "src" not in datasets


def test_a_merged_view_counts_nothing_a_reader_may_not_see(mw: SimpleNamespace) -> None:
    """Review item 13 (rule 7): the drawn nodes the merge adds to the view are shown when seen and
    never counted when not."""
    drawn = _three(mw)
    _draw(mw, label="Courier", marking="SECRET")
    assert _merge(mw, drawn).status_code == 201
    _share_view(mw)
    erin, alice = _open_board_as_view(mw, "erin"), _open_board_as_view(mw)
    assert erin["missing"] == alice["missing"] == 0
    assert erin["view"]["chosen"] == alice["view"]["chosen"]


# --- the second review's findings --------------------------------------------------------------


def test_a_link_the_targets_model_lacks_is_left_out_by_the_merge_itself(
    mw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Item 4 at the merge's own write path (`DrawnMerges._plan`), not the sheet's alone."""
    from services.api.promotions import Promotions

    from .test_promotions import _LinkTypes

    _target_packs(mw, monkeypatch, ["fibo"])
    mercer = _draw(mw, label="Mercer", properties={"family_name": "Mercer"})
    tall = _draw(mw)
    cell = _as("alice").post(
        f"/v1/investigations/{mw.home}/boards/{mw.board}/links",
        json={"type": "SHARED_CELL_WITH", "label": "same cell", "marking": "OFFICIAL",
              "grading": GRADE, "source_note": "Wing roll", "source": mercer["element_id"],
              "target": tall["element_id"]},
    )  # fmt: skip
    assert cell.status_code == 201, cell.text
    monkeypatch.setattr(app_state(), "link_types", _LinkTypes(None), raising=False)
    monkeypatch.setattr(Promotions, "model_check_applies", lambda self, name, refusals: False)
    ticked = [mercer["item_id"], tall["item_id"], cell.json()["item_id"]]
    # Asked for by name, it is refused: the target's model does not hold it.
    again = _step(
        mw,
        "dry_run",
        "dana",
        item_ids=ticked,
        mapping=[
            {"kind": "link", "drawn_type": "SHARED_CELL_WITH", "target_type": "SHARED_CELL_WITH"}
        ],
    )
    assert _said(again) == (422, "not_a_type"), again.text
    answer = _step(mw, "merge", "dana", item_ids=ticked)
    assert answer.status_code == 201, answer.text
    (why,) = [x["why"] for x in answer.json()["left_out"] if x["item_id"] == ticked[2]]
    assert "Its type, SHARED_CELL_WITH, goes into no type of Prison intel (Map)" in why
    held = next(e for e in mw.graph.edges() if e.id == cell.json()["element_id"])
    assert held.datasets == [mw.drawn]


def test_an_approval_checks_each_link_against_the_targets_model_again(
    mw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Item 4 at the approval's re-check (`Promotions.recheck`): the target's model narrowed while
    the merge waits refuses it, whatever the drawing's proposals say."""
    from services.api.promotions import Promotions

    from .test_promotions import _LinkTypes

    _second_person(mw)
    packs = {"src": ["niem"], mw.drawn: ["niem"]}
    real = mw.models.live

    async def live(dataset_id: str) -> Any:
        held = packs.get(dataset_id)
        return SimpleNamespace(packs=held) if held is not None else await real(dataset_id)

    monkeypatch.setattr(mw.models, "live", live)
    mercer = _draw(mw, label="Mercer", properties={"family_name": "Mercer"})
    tall = _draw(mw)
    cell = _as("alice").post(
        f"/v1/investigations/{mw.home}/boards/{mw.board}/links",
        json={"type": "SHARED_CELL_WITH", "label": "same cell", "marking": "OFFICIAL",
              "grading": GRADE, "source_note": "Wing roll", "source": mercer["element_id"],
              "target": tall["element_id"]},
    )  # fmt: skip
    sent = _step(mw, "merge", "dana",
                 item_ids=[mercer["item_id"], tall["item_id"], cell.json()["item_id"]])  # fmt: skip
    assert sent.status_code == 201, sent.text
    packs["src"] = ["fibo"]  # the target's model narrowed while the merge waits
    monkeypatch.setattr(app_state(), "link_types", _LinkTypes(None), raising=False)
    monkeypatch.setattr(Promotions, "model_check_applies", lambda self, name, refusals: False)
    approved = _as("erin").post(f"/v1/datasets/src/promotions/{sent.json()['id']}/decision",
                                json={"approve": True})  # fmt: skip
    assert _said(approved) == (409, "items_changed"), approved.text
    assert mw.store.records[sent.json()["id"]].status == "rejected"


def _restricted(mw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A loaded person in `src` under the restricted code R, which Dana may receive and Erin and
    Sam may not; and a drawn person alike it."""
    held = _loaded("p-restricted", family_name="Restricted")
    mw.graph._graph_nodes["p-restricted"] = held.model_copy(
        update={"handling": held.handling.model_copy(update={"handling_code": "R"})}
    )
    monkeypatch.setitem(PEOPLE, "dana", PEOPLE["dana"].model_copy(
        update={"receivable_handling_codes": ["R"]}))  # fmt: skip
    return _draw(mw, label="Restricted", properties={"family_name": "Restricted"})


def test_a_reviewer_who_may_not_receive_a_match_may_not_approve_and_the_merge_waits(
    mw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Item 1: a match end the reviewer may not receive (a restricted code, not only a marking)
    is 403 `not_all_seen`, the merge waiting for another reviewer, never rejected for them."""
    _second_person(mw)
    drawn = _restricted(mw, monkeypatch)
    sent = _step(mw, "merge", "dana", item_ids=[drawn["item_id"]],
                 matches=[{"drawn": drawn["element_id"], "loaded": "p-restricted"}])  # fmt: skip
    assert sent.status_code == 201, sent.text
    decision = f"/v1/datasets/src/promotions/{sent.json()['id']}/decision"
    refused = _as("erin").post(decision, json={"approve": True})
    assert _said(refused) == (403, "not_all_seen"), refused.text
    assert mw.store.records[sent.json()["id"]].status == "awaiting_review"
    monkeypatch.setitem(PEOPLE, "sam", PEOPLE["sam"].model_copy(
        update={"receivable_handling_codes": ["R"]}))  # fmt: skip
    approved = _as("sam").post(decision, json={"approve": True})
    assert approved.status_code == 200, approved.text


def _sent_and_waiting(mw: SimpleNamespace) -> tuple[SimpleNamespace, str]:
    _second_person(mw)
    drawn = _three(mw)
    sent = _merge(mw, drawn)
    assert sent.status_code == 201, sent.text
    return drawn, sent.json()["id"]


def _approved_by_sam(mw: SimpleNamespace, promotion_id: str) -> Any:
    return _as("sam").post(f"/v1/datasets/src/promotions/{promotion_id}/decision",
                           json={"approve": True})  # fmt: skip


def test_a_match_whose_marking_rose_while_waiting_rejects_the_merge(mw: SimpleNamespace) -> None:
    """Item 5: the loaded end raised within the reviewer's clearance (Sam, SECRET)."""
    drawn, promotion = _sent_and_waiting(mw)
    loaded = mw.graph._graph_nodes["p-loaded"]
    mw.graph._graph_nodes["p-loaded"] = loaded.model_copy(
        update={"handling": loaded.handling.model_copy(
            update={"classification": "OFFICIAL-SENSITIVE"})}
    )  # fmt: skip
    assert _said(_approved_by_sam(mw, promotion)) == (409, "items_changed")
    assert mw.store.records[promotion].status == "rejected"
    assert mw.graph.node(drawn.mercer["element_id"]).datasets == [mw.drawn]


def test_a_match_above_the_targets_highest_once_lowered_rejects_the_merge(
    mw: SimpleNamespace,
) -> None:
    """Item 5: the target's highest lowered below a match while it waits."""
    loaded = mw.graph._graph_nodes["p-loaded"]
    mw.graph._graph_nodes["p-loaded"] = loaded.model_copy(
        update={"handling": loaded.handling.model_copy(
            update={"classification": "OFFICIAL-SENSITIVE"})}
    )  # fmt: skip
    drawn, promotion = _sent_and_waiting(mw)
    mw.datasets.datasets["src"] = mw.datasets.datasets["src"].model_copy(
        update={"highest_marking": "OFFICIAL"}
    )
    assert _said(_approved_by_sam(mw, promotion)) == (409, "items_changed")
    assert mw.store.records[promotion].status == "rejected"


def test_a_merged_view_chosen_counts_the_boards_own_references_alone(mw: SimpleNamespace) -> None:
    """Item 3 (rule 7): `chosen` is the board's own references (none: it began blank), never the
    drawn nodes the merge added, some of which a reader may not see."""
    drawn = _three(mw)
    _draw(mw, label="Courier", marking="SECRET")
    assert _merge(mw, drawn).status_code == 201
    _share_view(mw)
    assert _open_board_as_view(mw, "erin")["view"]["chosen"] == 0
    listed = _as("erin").get(f"/v1/investigations/{mw.home}/views").json()
    assert [v["chosen"] for v in listed if v["id"] == mw.board] == [0]


def test_boards_a_failed_view_step_left_promote_nothing_of_the_drawing(
    mw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Item 8: the boards' step after the commit fails (logged, the merge standing and audited);
    the boards stay boards, and none of the drawing's items is offered to a promotion from one."""

    async def fails(*args: Any, **kwargs: Any) -> int:
        raise RuntimeError("views store unavailable")

    drawn = _three(mw)
    _draw(mw, label="Unticked")
    monkeypatch.setattr(mw.views, "merge_boards", fails)
    answer = _merge(mw, drawn)
    assert answer.status_code == 201, answer.text
    assert "merge_drawn_dataset" in [r["action"] for r in mw.audit.records]
    assert mw.views.views[mw.board].drawing is True
    sheet = _as("alice").get(f"/v1/investigations/{mw.home}/boards/{mw.board}/promotion-sheet")
    assert sheet.status_code == 200, sheet.text
    assert sheet.json()["items"] == []


# --- the owner's ruling: a drawn type mapped onto any of the target's types (Amendment 7) ------

#: The incident goes in as an Organisation, its name carried; where it happened (its OCCURRED_AT,
#: to a drawn Location that goes as itself) as where the Organisation is REGISTERED_AT. Every link
#: here is drawable (none has a required property: the adapter refuses a link without one).
RETYPE = [
    {"kind": "node", "drawn_type": "Incident", "target_type": "Organisation",
     "properties": [{"drawn_property": "name", "target_property": "name"},
                    {"drawn_property": "category", "target_property": None}]},
    {"kind": "link", "drawn_type": "OCCURRED_AT", "target_type": "REGISTERED_AT", "properties": []},
]  # fmt: skip


def _incident_model(mw: SimpleNamespace) -> None:
    """The drawing's model NIEM (its starter pack); `src`'s every pack."""
    real = mw.models.live

    async def live(dataset_id: str) -> Any:
        if dataset_id == "src":
            return SimpleNamespace(packs=["niem", "fibo", "stix"])
        if dataset_id == mw.drawn:
            return SimpleNamespace(packs=["niem"])
        return await real(dataset_id)

    mw.models.live = live


def _incident(mw: SimpleNamespace, **over: Any) -> SimpleNamespace:
    """A drawn Mercer (a Person, which goes as itself), a drawn incident, a drawn place (a Location,
    which goes as itself) and where the incident occurred (`role`, its OCCURRED_AT). The drawing's
    model is NIEM; `src`'s holds every pack."""
    _incident_model(mw)
    mercer = _draw(mw, label="Mercer", properties={"family_name": "Mercer"})
    fight = _draw(mw, type="Incident", label="Night fight",
                  properties={"name": "Night fight", "category": "assault"}, **over)  # fmt: skip
    place = _draw(mw, type="Location", label="B wing", properties={"name": "B wing"})
    role = _as("alice").post(
        f"/v1/investigations/{mw.home}/boards/{mw.board}/links",
        json={"type": "OCCURRED_AT", "label": "happened on", "marking": "OFFICIAL",
              "grading": GRADE, "source_note": "Wing log", "source": fight["element_id"],
              "target": place["element_id"]},
    )  # fmt: skip
    assert role.status_code == 201, role.text
    return SimpleNamespace(
        mercer=mercer, fight=fight, place=place, role=role.json(),
        ids=[mercer["item_id"], fight["item_id"], place["item_id"], role.json()["item_id"]],
    )  # fmt: skip


def _copy_of(mw: SimpleNamespace, original: str) -> Any:
    (back,) = [
        e for e in mw.graph.edges()
        if e.type == SAME_AS and e.target == original
        and e.properties.get("model_version") == "drawn_merge_retype"
    ]  # fmt: skip
    return back, mw.graph.node(back.source)


def test_the_sheet_offers_every_type_of_the_targets_model_to_map_onto(mw: SimpleNamespace) -> None:
    _incident(mw)
    sheet = _sheet_for(mw, "dana")
    (row,) = [m for m in sheet["mapping"] if m["drawn_type"] == "Incident"]
    assert {"Organisation", "Person", "Incident"} <= set(row["choices"])
    assert row["target_type"] == "Incident"  # the same name, proposed while the target has it
    assert row["drawn_properties"] == ["category", "name"]
    (org,) = [
        t for t in sheet["target_types"] if (t["kind"], t["name"]) == ("node", "Organisation")
    ]
    assert "name" in org["properties"] and "org_ref" in org["properties"]
    (link,) = [m for m in sheet["mapping"] if m["drawn_type"] == "OCCURRED_AT"]
    assert "REGISTERED_AT" in link["choices"]


def test_a_retyped_item_goes_in_as_a_new_element_of_its_mapped_type_with_an_inferred_same_as_back(
    mw: SimpleNamespace,
) -> None:
    """The owner's ruling: the merge maps each drawn type onto a type of the target's model and
    writes the items as the mapped types: new elements, as a load writes them, with their
    provenance and an inferred `SAME_AS` back to the drawn original (rules 5 and 6); a type mapped
    onto itself still goes as the same element (L3.4)."""
    drawn = _incident(mw)
    answer = _step(mw, "merge", "dana", item_ids=drawn.ids, mapping=RETYPE)
    assert answer.status_code == 201, answer.text
    body = answer.json()
    assert (body["status"], body["nodes"], body["links"]) == ("committed", 3, 1)
    original = mw.graph.node(drawn.fight["element_id"])
    # The original stays in the drawing alone, unchanged; Mercer, a Person, gains the target.
    assert original.datasets == [mw.drawn] and original.type == "Incident"
    assert mw.graph.node(drawn.mercer["element_id"]).datasets == sorted([mw.drawn, "src"])
    back, copy = _copy_of(mw, original.id)
    assert (copy.type, copy.properties, copy.datasets) == ("Organisation", {"name": "Night fight"},
                                                           ["src"])  # fmt: skip
    assert copy.provenance.drawn is not None and copy.provenance.drawn.label == "Night fight"
    # Written back whole (ADR-130 Amendment 2), not as Dana is shown it: Alice's board kept.
    assert copy.provenance.drawn.board_id == mw.board
    assert copy.provenance == original.provenance
    assert copy.audit.load_id == body["load_id"]
    # Rule 5: inferred, a person confirms it; rule 6: two nodes, never one.
    # ADR-099 Amendment 2 decision 3: the copy and its original share no dataset, so neither does
    # the link between them: no case reads it, nothing is joined at query time.
    assert back.provenance.state == ProvenanceState.INFERRED
    assert back.datasets == []
    assert back.audit.load_id == body["load_id"]
    (member,) = [e for e in mw.graph.edges() if e.type == "REGISTERED_AT"]
    assert (member.source, member.target, member.datasets) == (
        copy.id, drawn.place["element_id"], ["src"],
    )  # fmt: skip
    role = next(e for e in mw.graph.edges() if e.id == drawn.role["element_id"])
    assert role.datasets == [mw.drawn]  # the drawn link stays drawn, read-only
    record = mw.store.records[body["id"]]
    assert set(record.node_ids) == {drawn.mercer["element_id"], drawn.place["element_id"]}
    assert record.edge_ids == ()
    assert [(c.original, c.written_id) for c in mw.store.copies[body["id"]]] == [
        (original.id, copy.id), (role.id, member.id),
    ]  # fmt: skip


def test_a_copy_is_never_marked_below_its_original(mw: SimpleNamespace) -> None:
    """The orchestrator's condition: a copy keeps its original's handling, never lower."""
    mw.datasets.datasets["src"] = mw.datasets.datasets["src"].model_copy(
        update={"highest_marking": "SECRET"}
    )
    drawn = _incident(mw, marking="SECRET")
    answer = _step(mw, "merge", "dana", item_ids=drawn.ids, mapping=RETYPE)
    assert answer.status_code == 201, answer.text
    back, copy = _copy_of(mw, drawn.fight["element_id"])
    original = mw.graph.node(drawn.fight["element_id"])
    assert copy.handling == original.handling and copy.handling.classification == "SECRET"
    assert back.handling.classification == "SECRET"
    assert mw.store.records[answer.json()["id"]].marking == "SECRET"


def test_only_an_original_the_merger_reads_is_copied(mw: SimpleNamespace) -> None:
    """The orchestrator's condition, and rule 3: Erin (OFFICIAL) may not read a SECRET incident, so
    it is not copied, counted or named, and its id is answered as one that does not exist."""
    mw.datasets.datasets["src"] = mw.datasets.datasets["src"].model_copy(
        update={"highest_marking": "SECRET"}
    )
    drawn = _three(mw)
    _incident_model(mw)
    hidden = _draw(mw, type="Incident", label="Courier run", marking="SECRET",
                   properties={"name": "Courier run"})  # fmt: skip
    # Ticked by its id, alone: nothing is copied from it (the condition itself, asked first).
    named = _step(mw, "merge", "erin", item_ids=[hidden["item_id"]], mapping=RETYPE)
    assert not [n for n in mw.graph._graph_nodes.values() if n.type == "Organisation"]
    unknown = _step(mw, "merge", "erin", item_ids=["no-such-item"], mapping=RETYPE)
    assert (named.status_code, named.json()) == (unknown.status_code, unknown.json())
    dry = _step(mw, "dry_run", "erin", item_ids=_ids(drawn), mapping=RETYPE)
    assert dry.status_code == 200, dry.text
    assert (dry.json()["nodes"], dry.json()["retyped"]) == (2, 0)
    assert "Courier" not in json.dumps(dry.json())
    answer = _step(mw, "merge", "erin", item_ids=_ids(drawn), mapping=RETYPE)
    assert answer.status_code == 201, answer.text
    assert not [n for n in mw.graph._graph_nodes.values() if n.type == "Organisation"]
    assert mw.store.copies.get(answer.json()["id"], []) == []


@pytest.mark.parametrize(
    ("mapping", "code"),
    [
        ([{"kind": "node", "drawn_type": "Incident", "target_type": "NoSuchType"}], "not_a_type"),
        ([{"kind": "link", "drawn_type": "OCCURRED_AT", "target_type": "Organisation"}],
         "not_a_type"),
        ([{"kind": "node", "drawn_type": "Incident", "target_type": "Organisation",
           "properties": [{"drawn_property": "name", "target_property": "nickname"}]}],
         "not_a_property"),
        ([{"kind": "node", "drawn_type": "Incident", "target_type": "Organisation",
           "properties": [{"drawn_property": "name", "target_property": "name"},
                          {"drawn_property": "category", "target_property": "name"}]}],
         "not_a_property"),
    ],
)  # fmt: skip
@pytest.mark.parametrize("step", ["dry_run", "merge"])
def test_a_mapping_outside_the_targets_model_is_refused_with_nothing_written(
    mw: SimpleNamespace, mapping: list[dict[str, Any]], code: str, step: str
) -> None:
    drawn = _incident(mw)
    answer = _step(mw, step, "dana", item_ids=drawn.ids, mapping=mapping)
    assert _said(answer) == (422, code), answer.text
    _nothing_written(mw, drawn.mercer["element_id"], drawn.fight["element_id"])


@pytest.mark.parametrize(
    ("mapping", "words"),
    [
        # An Establishment requires a name and a reference: the incident carries no reference.
        ([{"kind": "node", "drawn_type": "Incident", "target_type": "Establishment",
           "properties": [{"drawn_property": "name", "target_property": "name"}]}],
         "Mapped onto Establishment"),
        # Its OCCURRED_AT kept, its incident an Organisation: an OCCURRED_AT runs from an Incident.
        ([RETYPE[0]], "A OCCURRED_AT link runs from Incident to Location, not from Organisation"),
    ],
)  # fmt: skip
def test_a_copy_that_breaks_its_new_types_rules_is_refused_with_nothing_written(
    mw: SimpleNamespace, mapping: list[dict[str, Any]], words: str
) -> None:
    drawn = _incident(mw)
    # The node's own rule asked alone (its link not ticked), the link's with it.
    ticked = drawn.ids if mapping[0]["target_type"] == "Organisation" else drawn.ids[:3]
    answer = _step(mw, "merge", "dana", item_ids=ticked, mapping=mapping)
    assert _said(answer) == (422, "check_failed"), answer.text
    assert words in answer.json()["detail"]
    _nothing_written(mw, drawn.mercer["element_id"], drawn.fight["element_id"])


def test_a_type_mapped_onto_none_is_left_out_by_choice_with_its_reason(mw: SimpleNamespace) -> None:
    drawn = _incident(mw)
    leave = [{"kind": "node", "drawn_type": "Incident", "target_type": None}]
    answer = _step(mw, "merge", "dana", item_ids=drawn.ids, mapping=leave)
    assert answer.status_code == 201, answer.text
    why = {x["item_id"]: x["why"] for x in answer.json()["left_out"]}
    assert "goes into no type of Prison intel (Map)" in why[drawn.fight["item_id"]]
    assert "One of its ends will not be in the dataset" in why[drawn.role["item_id"]]
    assert mw.graph.node(drawn.fight["element_id"]).datasets == [mw.drawn]


def test_a_match_on_a_retyped_node_is_looked_for_as_its_new_type_and_written_from_its_copy(
    mw: SimpleNamespace,
) -> None:
    loaded = _loaded("o-loaded").model_copy(
        update={"type": "Organisation", "properties": {"name": "Night fight"}}
    )
    mw.graph._graph_nodes["o-loaded"] = loaded
    drawn = _incident(mw)
    as_drawn = _sheet_for(mw, "dana")["matches"]
    assert "o-loaded" not in {m["loaded"] for m in as_drawn}  # an Incident is no Organisation
    # The sheet under the mapping offers it (the review, item 7): what Match shows, the merge takes.
    mapped = _as("dana").get(f"/v1/datasets/{mw.drawn}/merge-sheet",
                             params={"target": "src", "mapping": json.dumps(RETYPE)})  # fmt: skip
    assert mapped.status_code == 200, mapped.text
    assert "o-loaded" in {m["loaded"] for m in mapped.json()["matches"]}
    (row,) = [m for m in mapped.json()["mapping"] if m["drawn_type"] == "Incident"]
    assert row["target_type"] == "Organisation"
    pick = [{"drawn": drawn.fight["element_id"], "loaded": "o-loaded"}]
    answer = _step(mw, "merge", "dana", item_ids=drawn.ids, mapping=RETYPE, matches=pick)
    assert answer.status_code == 201, answer.text
    _, copy = _copy_of(mw, drawn.fight["element_id"])
    (same,) = [e for e in mw.graph.edges()
               if e.type == SAME_AS
               and e.properties.get("model_version") == "drawn_merge"]  # fmt: skip
    assert (same.source, same.target, same.datasets) == (copy.id, "o-loaded", ["src"])
    assert same.provenance.state == ProvenanceState.INFERRED


def test_a_picture_of_a_retyped_node_is_left_out_with_its_reason(mw: SimpleNamespace) -> None:
    """A Person retyped as an Organisation: its picture rests on the drawn original, so it stays."""
    tall = _draw(mw)
    uploaded = _as("alice").put(
        f"/v1/investigations/{mw.home}/boards/{mw.board}/nodes/{tall['element_id']}/picture",
        params={"name": "tall.png", "marking": "OFFICIAL", "source_note": "Gate camera"},
        content=b"\x89PNG drawn",
    )
    assert uploaded.status_code == 201, uploaded.text
    (picture,) = [i for i in _sheet_for(mw, "dana")["items"] if i["kind"] == "picture"]
    as_org = [{"kind": "node", "drawn_type": "Person", "target_type": "Organisation",
               "properties": [
                   {"drawn_property": "family_name", "target_property": "name"}]}]  # fmt: skip
    answer = _step(mw, "merge", "dana", item_ids=[tall["item_id"]], mapping=as_org)
    assert answer.status_code == 201, answer.text
    why = {x["item_id"]: x["why"] for x in answer.json()["left_out"]}
    assert "the picture stays on the drawing" in why.get(picture["item_id"], "")
    assert not [e for e in mw.graph.edges() if e.type == "DEPICTS" and "src" in e.datasets]
    _, copy = _copy_of(mw, tall["element_id"])
    assert (copy.type, copy.properties) == ("Organisation", {"name": "Tall"})


def test_a_reviewer_reads_each_copy_while_it_waits_and_once_committed(mw: SimpleNamespace) -> None:
    _second_person(mw)
    drawn = _incident(mw)
    sent = _step(mw, "merge", "dana", item_ids=drawn.ids, mapping=RETYPE)
    assert sent.status_code == 201, sent.text
    details = _as("erin").get(f"/v1/datasets/src/promotions/{sent.json()['id']}").json()
    goes = {i["element_id"]: i.get("goes_in_as") for i in details["items"]}
    assert goes == {
        drawn.fight["element_id"]: "Organisation", drawn.role["element_id"]: "REGISTERED_AT",
        drawn.mercer["element_id"]: None, drawn.place["element_id"]: None,
    }  # fmt: skip
    assert (details["promotion"]["nodes"], details["promotion"]["links"]) == (3, 1)
    listed = _as("erin").get("/v1/datasets/src/promotions").json()["promotions"]
    assert [(p["nodes"], p["links"]) for p in listed if p["id"] == sent.json()["id"]] == [(3, 1)]
    decided = _as("erin").post(
        f"/v1/datasets/src/promotions/{sent.json()['id']}/decision", json={"approve": True}
    )
    assert decided.status_code == 200, decided.text
    _, copy = _copy_of(mw, drawn.fight["element_id"])
    after = _as("erin").get(f"/v1/datasets/src/promotions/{sent.json()['id']}").json()
    assert copy.id in {i["element_id"] for i in after["items"]} and after["withheld"] is False


def test_a_waiting_merge_whose_original_changed_is_rejected(mw: SimpleNamespace) -> None:
    """An original edited after it was chosen would be copied as it no longer is: rejected at the
    approval (Amendment 5 decision 6), never left waiting, nothing written."""
    _second_person(mw)
    drawn = _incident(mw)
    sent = _step(mw, "merge", "dana", item_ids=drawn.ids, mapping=RETYPE)
    edited = _as("alice").patch(
        f"/v1/investigations/{mw.home}/board-items/{drawn.fight['item_id']}",
        json={"properties": {"name": "Day fight", "category": "assault"}},
    )
    assert edited.status_code == 200, edited.text
    decided = _as("erin").post(
        f"/v1/datasets/src/promotions/{sent.json()['id']}/decision", json={"approve": True}
    )
    assert _said(decided) == (409, "items_changed"), decided.text
    assert mw.store.records[sent.json()["id"]].status == "rejected"
    assert not [n for n in mw.graph._graph_nodes.values() if n.type == "Organisation"]


def test_a_waiting_merge_whose_mapped_type_left_the_targets_model_is_rejected(
    mw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    _second_person(mw)
    drawn = _incident(mw)
    sent = _step(mw, "merge", "dana", item_ids=drawn.ids, mapping=RETYPE)
    assert sent.status_code == 201, sent.text
    real = Boards.dataset_node_types

    async def without_organisation(self: Boards, dataset_id: str) -> list[str]:
        return [t for t in await real(self, dataset_id) if t != "Organisation"]

    monkeypatch.setattr(Boards, "dataset_node_types", without_organisation)
    decided = _as("erin").post(
        f"/v1/datasets/src/promotions/{sent.json()['id']}/decision", json={"approve": True}
    )
    assert _said(decided) == (409, "items_changed"), decided.text
    assert "Organisation is not a type of Prison intel" in decided.json()["detail"]
    assert mw.store.records[sent.json()["id"]].status == "rejected"


async def test_reverting_a_retyped_merge_withdraws_its_copies_their_links_and_same_as(
    mw: SimpleNamespace,
) -> None:
    from scripts.revert_promotion import revert_promotion
    from services.api.promotions import PromotionRefused

    from schemas.domain import EdgeWrite, Provenance, SourceRef

    drawn = _incident(mw)
    body = _step(mw, "merge", "dana", item_ids=drawn.ids, mapping=RETYPE).json()
    boards, merge = _merge_commit(mw)
    record = mw.store.records[body["id"]]
    back, copy = _copy_of(mw, drawn.fight["element_id"])
    # A link written since onto the copy refuses the revert, as one onto a promoted node does.
    tx = await mw.graph.begin_transaction()
    later = EdgeWrite(
        id="later", type="MEMBER_OF", source="p-loaded", target=copy.id, properties={},
        provenance=Provenance(
            state=ProvenanceState.ASSERTED, first_seen=datetime.now(UTC),
            sources=[SourceRef(document_id="later-load", locator="", excerpt_hash="")],
        ),
        handling=copy.handling, created_by="eng", created_at=datetime.now(UTC),
        datasets=["src"],
    )  # fmt: skip
    (later_id,) = await mw.graph.upsert_edges([later], tx)
    await mw.graph.commit_transaction(tx)
    with pytest.raises(PromotionRefused) as refused:
        await revert_promotion(record, boards.graph, mw.store, boards.items, merge)
    assert refused.value.code == "links_rest_on_it"
    mw.graph._graph_edges = [e for e in mw.graph._graph_edges if e.id != later_id]

    await revert_promotion(record, boards.graph, mw.store, boards.items, merge)
    (member,) = [e for e in mw.graph.edges() if e.type == "REGISTERED_AT"]
    assert mw.graph.node(copy.id).audit.reverted and member.audit.reverted
    # Reverted as the load's own writes, never stamped withdrawn by a load (a refresh's record,
    # which `restore_withdrawn` would bring back: the review, minor 21).
    assert mw.graph.node(copy.id).audit.withdrawn_by_load is None
    assert next(e for e in mw.graph.edges() if e.id == back.id).audit.reverted
    assert mw.graph.node(drawn.fight["element_id"]).datasets == [mw.drawn]
    assert not mw.graph.node(drawn.fight["element_id"]).audit.reverted


def test_a_sheet_given_a_mapping_it_cannot_read_is_refused(mw: SimpleNamespace) -> None:
    _incident(mw)
    for given in ("not json", json.dumps([{"kind": "node"}])):
        answer = _as("dana").get(f"/v1/datasets/{mw.drawn}/merge-sheet",
                                 params={"target": "src", "mapping": given})  # fmt: skip
        assert _said(answer) == (422, "not_a_mapping"), answer.text


def test_a_type_or_property_mapped_twice_is_refused(mw: SimpleNamespace) -> None:
    """The review, minor 19: nothing taken silently, so a repeated choice is refused."""
    drawn = _incident(mw)
    twice = [RETYPE[0], {**RETYPE[0], "target_type": "Person"}]
    once_each = [{**RETYPE[0], "properties": [
        {"drawn_property": "name", "target_property": "name"},
        {"drawn_property": "name", "target_property": None}]}]  # fmt: skip
    for mapping in (twice, once_each):
        answer = _step(mw, "dry_run", "dana", item_ids=drawn.ids, mapping=mapping)
        assert _said(answer) == (422, "mapping_repeated"), answer.text


def test_the_dry_run_says_what_a_retyped_item_does_not_carry(mw: SimpleNamespace) -> None:
    """The review, minor 16 (rule 2): an unplaced property is said, never dropped silently."""
    drawn = _incident(mw)
    answer = _step(mw, "dry_run", "dana", item_ids=drawn.ids, mapping=RETYPE)
    assert answer.status_code == 200, answer.text
    assert answer.json()["not_carried"] == [
        "Incident's category is not carried into Organisation: it stays on the drawing."
    ]
    # The incident and its link (an OCCURRED_AT going in as a REGISTERED_AT) are of another type.
    assert answer.json()["retyped"] == 2


def test_a_link_only_touching_a_retyped_node_is_not_counted_as_retyped(mw: SimpleNamespace) -> None:
    """The review, minor 15: written new for its end, it keeps its own type. Mercer goes in as a
    Vehicle; his PRESENT_AT on B wing, which may run from one, is kept as itself."""
    drawn = _incident(mw)
    present = _as("alice").post(
        f"/v1/investigations/{mw.home}/boards/{mw.board}/links",
        json={"type": "PRESENT_AT", "label": "seen on", "marking": "OFFICIAL", "grading": GRADE,
              "source_note": "Wing log", "source": drawn.mercer["element_id"],
              "target": drawn.place["element_id"]},
    )  # fmt: skip
    assert present.status_code == 201, present.text
    as_vehicle = [
        {"kind": "node", "drawn_type": "Person", "target_type": "Vehicle",
         "properties": [{"drawn_property": "family_name", "target_property": None}]},
    ]  # fmt: skip
    ticked = [drawn.mercer["item_id"], drawn.place["item_id"], present.json()["item_id"]]
    answer = _step(mw, "dry_run", "dana", item_ids=ticked, mapping=as_vehicle)
    assert answer.status_code == 200, answer.text
    assert (answer.json()["nodes"], answer.json()["links"], answer.json()["retyped"]) == (2, 1, 1)


def test_a_waiting_merge_whose_original_was_raised_is_rejected(mw: SimpleNamespace) -> None:
    """The orchestrator's condition on the waiting path (the review, item 2): an original raised
    since it was sent is not copied at the marking sent."""
    _second_person(mw)
    drawn = _incident(mw)
    sent = _step(mw, "merge", "dana", item_ids=drawn.ids, mapping=RETYPE)
    assert sent.status_code == 201, sent.text
    raised = _as("alice").patch(
        f"/v1/investigations/{mw.home}/board-items/{drawn.fight['item_id']}",
        json={"marking": "OFFICIAL-SENSITIVE"},
    )
    assert raised.status_code == 200, raised.text
    decided = _as("sam").post(
        f"/v1/datasets/src/promotions/{sent.json()['id']}/decision", json={"approve": True}
    )
    assert _said(decided) == (409, "items_changed"), decided.text
    assert not [n for n in mw.graph._graph_nodes.values() if n.type == "Organisation"]


@pytest.mark.parametrize(
    ("which", "edit"),
    [("fight", {"source_note": "Wing log, corrected"}), ("role", {"label": "led it"})],
)
def test_a_waiting_merge_whose_originals_drawn_assertion_changed_is_rejected(
    mw: SimpleNamespace, which: str, edit: dict[str, Any]
) -> None:
    """The review, item 4: a source note, a label (a link's only edit) changed since it was sent
    would be copied as it no longer is."""
    _second_person(mw)
    drawn = _incident(mw)
    sent = _step(mw, "merge", "dana", item_ids=drawn.ids, mapping=RETYPE)
    item = getattr(drawn, which)["item_id"]
    edited = _as("alice").patch(f"/v1/investigations/{mw.home}/board-items/{item}", json=edit)
    assert edited.status_code == 200, edited.text
    decided = _as("erin").post(
        f"/v1/datasets/src/promotions/{sent.json()['id']}/decision", json={"approve": True}
    )
    assert _said(decided) == (409, "items_changed"), decided.text
    assert mw.store.records[sent.json()["id"]].status == "rejected"


async def test_a_copy_the_model_refuses_at_the_commit_rejects_the_merge_in_words(
    mw: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The review, item 4, and the orchestrator's item 2: the store's own refusal of a copy at the
    commit (the model changed while the merge waited: REGISTERED_AT now requires a property its
    copy lacks) is the merge's `items_changed`, rejected, nothing written; never a bare error. The
    refusal is the fake graph's own, as the adapter's `upsert_edges` makes it (rule 15)."""
    from schemas.domain import PropertyDef, PropertyType

    _second_person(mw)
    drawn = _incident(mw)
    sent = _step(mw, "merge", "dana", item_ids=drawn.ids, mapping=RETYPE)
    assert sent.status_code == 201, sent.text
    held = mw.graph.ontology
    edges = [
        e.model_copy(update={"properties": [*e.properties, PropertyDef(
            name="since", type=PropertyType.DATE, required=True)]})
        if e.name == "REGISTERED_AT" else e
        for e in held.edge_types
    ]  # fmt: skip
    monkeypatch.setattr(mw.graph, "ontology", held.model_copy(update={"edge_types": edges}))
    decided = _as("erin").post(
        f"/v1/datasets/src/promotions/{sent.json()['id']}/decision", json={"approve": True}
    )
    assert _said(decided) == (409, "items_changed"), decided.text
    assert mw.store.records[sent.json()["id"]].status == "rejected"
    # Nothing written: no copy, nothing promoted, the drawing still its case's.
    assert not [n for n in mw.graph._graph_nodes.values() if n.type == "Organisation"]
    assert mw.graph.node(drawn.mercer["element_id"]).datasets == [mw.drawn]
    assert all(c.written_id is None for c in mw.store.copies[sent.json()["id"]])
    assert mw.datasets.merged == {}


async def test_two_copies_written_as_one_link_are_shown_once_and_withheld_from_no_one(
    mw: SimpleNamespace,
) -> None:
    """The review, item 8: the adapter merges two links of one pair and audience written in one
    transaction (ADR-102), so two copies may share one written id."""
    from dataclasses import replace

    drawn = _incident(mw)
    body = _step(mw, "merge", "dana", item_ids=drawn.ids, mapping=RETYPE).json()
    rows = mw.store.copies[body["id"]]
    (link,) = [c for c in rows if c.kind == "link"]
    mw.store.copies[body["id"]] = [*rows, replace(link, original="another-drawn-link")]
    _, merge = _merge_commit(mw)
    shown, withheld = await merge.copies_shown(mw.store.records[body["id"]], PEOPLE["erin"])
    assert [i.element_id for i in shown if i.kind == "link"] == [link.written_id]
    assert withheld is False


async def test_the_board_fake_merges_a_link_written_twice_in_one_transaction() -> None:
    """Rule 15: the fake refuses, and merges, what the adapter does (`_find_existing_edge(...,
    session_id=tx)`)."""
    from .board_fakes import BoardGraph
    from .test_boards import ONTOLOGY, node

    graph = BoardGraph(ONTOLOGY)
    for n in ("a", "b"):
        graph._graph_nodes[n] = node(n, "OFFICIAL").model_copy(update={"datasets": ["src"]})
    tx = await graph.begin_transaction()
    from schemas.domain import EdgeWrite, Provenance, SourceRef

    def write(edge_id: str) -> EdgeWrite:
        return EdgeWrite(
            id=edge_id, type="ASSOCIATE_OF", source="a", target="b", properties={},
            provenance=Provenance(
                state=ProvenanceState.ASSERTED, first_seen=datetime.now(UTC),
                sources=[SourceRef(document_id="d", locator="", excerpt_hash="")],
            ),
            handling=graph.node("a").handling, created_by="eng", created_at=datetime.now(UTC),
            datasets=["src"],
        )  # fmt: skip

    reversed_ = write("e-3").model_copy(update={"source": "b", "target": "a"})
    first, second, third = await graph.upsert_edges([write("e-1"), write("e-2"), reversed_], tx)
    await graph.commit_transaction(tx)
    # ASSOCIATE_OF is not directed: the reversed pair is the same link, as the adapter's
    # `bothE`/`otherV` finds it (the fourth review, minor 9).
    assert first == second == third == "e-1"
    assert [e.id for e in graph.edges()] == ["e-1"]


def test_a_rejected_drawn_merge_is_counted_alike_in_the_list_and_its_details(
    mw: SimpleNamespace,
) -> None:
    """The review, item 12: Amendment 5 decision 6a, the same counts in both."""
    _second_person(mw)
    drawn = _incident(mw)
    sent = _step(mw, "merge", "dana", item_ids=drawn.ids, mapping=RETYPE).json()
    rejected = _as("erin").post(f"/v1/datasets/src/promotions/{sent['id']}/decision",
                                json={"approve": False, "reason": "Not this one"})  # fmt: skip
    assert rejected.status_code == 200, rejected.text
    listed = _as("erin").get("/v1/datasets/src/promotions").json()["promotions"]
    (row,) = [(p["nodes"], p["links"]) for p in listed if p["id"] == sent["id"]]
    details = _as("erin").get(f"/v1/datasets/src/promotions/{sent['id']}").json()["promotion"]
    assert row == (details["nodes"], details["links"]) == (3, 1)


def test_the_merge_audits_its_mapping_and_its_copies(mw: SimpleNamespace) -> None:
    """The review, item 11: the trail says what was chosen and what was written for it."""
    drawn = _incident(mw)
    body = _step(mw, "merge", "dana", item_ids=drawn.ids, mapping=RETYPE).json()
    (entry,) = [e for e in mw.audit.records if e["action"] == "merge_drawn_dataset"]
    query = entry["resolved_query"]
    assert [m["target_type"] for m in query.get("mapping", [])] == ["Organisation", "REGISTERED_AT"]
    copies = {c["original"]: c for c in query.get("copies", [])}
    assert set(copies) == {drawn.fight["element_id"], drawn.role["element_id"]}
    assert all(c["written"] for c in copies.values())
    assert entry["result_cardinality"] == body["nodes"] + body["links"]


@pytest.mark.parametrize("who", ["erin", "alice"])
async def test_the_same_as_back_is_read_by_no_reader_of_the_target_or_of_the_drawing(
    mw: SimpleNamespace, who: str
) -> None:
    """The orchestrator's review, item 5: Erin reads the target (through its home case), Alice the
    drawing's home case (the target and the drawing, read-only, after the merge). The links among
    the copy and its original, a seed naming the link, the view's links among, and a working set's
    sync never bring it; each read brings what it should (the control), so none is empty. Expanding
    is the adapter's own (the fake answers a canned one): `conformance/graph_port/test_promotion.py`
    proves it there."""
    from services.api.app import app

    drawn = _incident(mw)
    body = _step(mw, "merge", "dana", item_ids=drawn.ids, mapping=RETYPE).json()
    assert body["status"] == "committed"
    back, copy = _copy_of(mw, drawn.fight["element_id"])
    original, place = drawn.fight["element_id"], drawn.place["element_id"]
    (registered,) = [e for e in mw.graph.edges() if e.type == "REGISTERED_AT"]
    case = HOME if who == "erin" else mw.home
    # As the app scopes a case's reader: its datasets, the merged drawing among them (read-only).
    reader = PEOPLE[who].model_copy(update={"datasets": await mw.datasets.ids_of_case(case)})
    # The control: what this reader does read between the copy, its original and the place.
    control = registered.id if who == "erin" else drawn.role["element_id"]
    among = await mw.graph.edges_among([copy.id, original, place], reader)
    assert control in {e.id for e in among}
    assert back.id not in {e.id for e in among}
    service = app.state.working_set
    nodes = await mw.graph.get_nodes([copy.id, original, place], reader)
    edges = await mw.graph.get_edges([back.id, control], reader)
    await service.seed(case, nodes, edges, reader)
    links = await service.links_among(case, reader)
    assert back.id not in {e.id for e in getattr(links, "delta", links).edges}
    held = [e.id for sent in await service.sync(case, reader, last_acknowledged_seq=None)
            for e in getattr(sent, "edges", [])]  # fmt: skip
    assert control in held
    assert back.id not in held


@pytest.mark.parametrize(
    "moved",
    [{"owning_unit": "unit-2"}, {"kind": COMPOSITE, "members": ["other"]}],
    ids=["its-unit", "its-kind"],
)
def test_a_waiting_merge_whose_target_is_no_longer_one_it_may_go_into_is_rejected(
    mw: SimpleNamespace, moved: dict[str, Any]
) -> None:
    """The orchestrator's review, item 6: the approval asks again what `targets()` asked (a source
    dataset of the drawing's unit, not a gazetteer): one moved while the merge waits refuses it."""
    _second_person(mw)
    drawn = _incident(mw)
    sent = _step(mw, "merge", "dana", item_ids=drawn.ids, mapping=RETYPE)
    assert sent.status_code == 201, sent.text
    mw.datasets.datasets["src"] = mw.datasets.datasets["src"].model_copy(update=moved)
    decided = _as("erin").post(
        f"/v1/datasets/src/promotions/{sent.json()['id']}/decision", json={"approve": True}
    )
    assert _said(decided) == (409, "items_changed"), decided.text
    assert "no longer one this drawing may be merged into" in decided.json()["detail"]
    assert mw.store.records[sent.json()["id"]].status == "rejected"
    assert mw.datasets.merged == {}


def test_a_retyped_link_between_two_items_going_as_themselves_is_refused(
    mw: SimpleNamespace,
) -> None:
    """The fourth review, item 1: a link of the new type may already be loaded between them, which
    the adapter would merge the copy into and the revert would then revert. Refused whenever it
    could be, since whether it is so is not the merger's to know (rule 3)."""
    drawn = _three(mw)
    _incident_model(mw)
    as_family = [{"kind": "link", "drawn_type": "ASSOCIATE_OF", "target_type": "FAMILY_OF"}]
    answer = _step(mw, "merge", "dana", item_ids=_ids(drawn), mapping=as_family)
    assert _said(answer) == (422, "check_failed"), answer.text
    assert "could join a link loaded between them" in answer.json()["detail"]
    _nothing_written(mw, drawn.mercer["element_id"])


def test_a_property_placed_nowhere_is_not_carried(mw: SimpleNamespace) -> None:
    """Its value stays on the drawing: the copy holds only what was placed (a plant carrying each
    drawn property by its name is red here, not refused elsewhere: the fourth review, item 2)."""
    _incident_model(mw)
    # An incident holding only a name, which an Organisation also has: carried by its name, it
    # would be written and the copy hold it.
    quiet = _draw(mw, type="Incident", label="Quiet night", properties={"name": "Quiet night"})
    nowhere = [{**RETYPE[0], "properties": [{"drawn_property": "name", "target_property": None}]}]
    answer = _step(mw, "merge", "dana", item_ids=[quiet["item_id"]], mapping=nowhere)
    assert answer.status_code == 201, answer.text
    _, copy = _copy_of(mw, quiet["element_id"])
    assert copy.properties == {}


def test_a_waiting_merge_whose_original_changed_says_so_in_words(mw: SimpleNamespace) -> None:
    """The fourth review, minor 4: the reviewer is told an item changed, not a match."""
    _second_person(mw)
    drawn = _incident(mw)
    sent = _step(mw, "merge", "dana", item_ids=drawn.ids, mapping=RETYPE)
    edited = _as("alice").patch(
        f"/v1/investigations/{mw.home}/board-items/{drawn.fight['item_id']}",
        json={"source_note": "Corrected"},
    )
    assert edited.status_code == 200, edited.text
    decided = _as("erin").post(
        f"/v1/datasets/src/promotions/{sent.json()['id']}/decision", json={"approve": True}
    )
    assert "One of its items going in as another type has changed" in decided.json()["detail"]
    checks = [e["resolved_query"].get("check") for e in mw.audit.records
              if e["action"] == "promotion_rejected"]  # fmt: skip
    assert checks == ["copies"]


async def test_a_grading_change_moves_a_merges_copies_too(mw: SimpleNamespace) -> None:
    """The orchestrator's review, item 4: ADR-143 decision 11 (every drawn item graded in the
    deployment's one scheme) holds for a copy, which no board's registry holds."""
    from services.api.grading import BoardGradedItems, operator_reader

    from .test_grading_change import SCHEME as GRADING_SCHEME

    drawn = _incident(mw)
    assert _step(mw, "merge", "dana", item_ids=drawn.ids, mapping=RETYPE).status_code == 201
    _, copy = _copy_of(mw, drawn.fight["element_id"])
    (link,) = [e for e in mw.graph.edges() if e.type == "REGISTERED_AT"]

    async def registered() -> list[Any]:
        return list(mw.items.items.values())

    port = BoardGradedItems(
        mw.graph, registered, operator_reader(GRADING_SCHEME, org_unit=UNIT),
        copies=mw.store.committed_copies,
    )  # fmt: skip
    found = await port.inventory()
    assert {copy.id, link.id} <= {i.id for i in found.items}
    assert found.unread == []


async def test_reverting_a_retyped_merge_takes_its_copies_out_of_every_working_set(
    mw: SimpleNamespace,
) -> None:
    """The fourth review, item 3: stored bodies are projected as stored, so a reverted copy left
    on a canvas would stay there; the revert removes it as a load's revert does."""
    from dataclasses import replace

    from scripts.revert_promotion import revert_promotion

    drawn = _incident(mw)
    body = _step(mw, "merge", "dana", item_ids=drawn.ids, mapping=RETYPE).json()
    _, merge = _merge_commit(mw)
    removed: list[tuple[list[str], list[str]]] = []

    class _Sets:
        async def remove(self, nodes: Any, edges: Any, *, final_pass: bool = False) -> int:
            removed.append((list(nodes), list(edges)))
            return 1

    merge = replace(merge, working_sets=_Sets())
    boards, _ = _merge_commit(mw)
    await revert_promotion(
        mw.store.records[body["id"]], boards.graph, mw.store, boards.items, merge
    )
    back, copy = _copy_of(mw, drawn.fight["element_id"])
    (link,) = [e for e in mw.graph.edges() if e.type == "REGISTERED_AT"]
    assert removed == [([copy.id], sorted({link.id, back.id}))]


def test_the_sheet_under_a_mapping_says_what_a_copy_would_break(mw: SimpleNamespace) -> None:
    """The fourth review, minor 5: the sheet's checks are the merge's, so a mapping that breaks
    the new type's rules is said on the sheet, not only refused at the dry run."""
    drawn = _incident(mw)
    onto = [{"kind": "node", "drawn_type": "Incident", "target_type": "Establishment",
             "properties": [{"drawn_property": "name", "target_property": "name"}]}]  # fmt: skip
    sheet = _as("dana").get(f"/v1/datasets/{mw.drawn}/merge-sheet",
                            params={"target": "src", "mapping": json.dumps(onto)})  # fmt: skip
    assert sheet.status_code == 200, sheet.text
    (fight,) = [i for i in sheet.json()["items"] if i["item_id"] == drawn.fight["item_id"]]
    assert any("Mapped onto Establishment" in words for words in fight["problems"])
