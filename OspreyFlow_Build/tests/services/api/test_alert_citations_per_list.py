"""One owner on two screening lists: one alert citing both, each list's match shown only to a reader
cleared for that list (`06_DECISIONS.md` ADR-146 Amendment 7, the owner's ruling of 12 November 2026;
rules 3 and 4).

The alert below cites the customer and its owner (what every reader of it must read) and two
matches, one on "Synthetic list A" (its listed party `l-a`, its `SAME_AS` `s-a`) and one on
"Synthetic list B" (`l-b`, `s-b`). A reader cleared for A and not for B reads `l-b` and `s-b` as
hidden, as the adapters answer them (`get_nodes`/`get_edges` leave a hidden id out). On every read
path the reader is given the alert with A's match alone: B's name is nowhere in what is served, nor
its ids, nor the number of matches (the alert served is the one an alert citing A alone would be).
A reader cleared for neither is not shown the alert at all, as for an alert that does not exist; a
reader cleared for both is shown both.

These run the real `alert_queue` functions against the fakes `test_alert_evidence_withheld.py`
answers as the adapters do. The live counterpart, with the lists marked and the alert raised by the
gate, is `tests/ingest/test_kyc_rules.py`'s Amendment 7 cases. Each was shown red by a plant at its
real call site (`process/lanes/rules/lists/AM7_RED_RECORD.txt`).
"""

from __future__ import annotations

from typing import Any

import pytest
from services.api import alert_queue, packs
from services.api.alerts import (
    SCREENING_MATCH_WORDS,
    AlertNotFoundError,
    ReadableEvidence,
    as_read,
    edges_shown_with,
)

from ontology.handling import load_uk_le_scheme
from schemas.domain import Alert, AlertCitation, AlertMode
from tests.services.api.test_alert_evidence_withheld import (
    CASE,
    NOW,
    READER,
    TriageStore,
    _path,
    _world,
)

A_WORDS = "“PETROVA, Elena” on a sanctions list (Synthetic list A), score 0.97"
B_WORDS = "“Elena PETROVA” on a sanctions list (Synthetic list B), score 0.95"
CITE_A = AlertCitation(words=A_WORDS, node_ids=["l-a"], edge_ids=["s-a"])
CITE_B = AlertCitation(words=B_WORDS, node_ids=["l-b"], edge_ids=["s-b"])
#: What a reader not cleared for list B cannot read: its listed party and its `SAME_AS`.
NOT_B = {"l-b", "s-b"}


def _screening(name: str, citations: list[AlertCitation], **more: Any) -> Alert:
    nodes = ["n-a", "n-b", *(i for c in citations for i in c.node_ids)]
    edges = ["e-1", *(i for c in citations for i in c.edge_ids)]
    return Alert(
        id=name, rule_id="typology:kyc", owner_id="deployer", mode=AlertMode.FULL,
        referent_node_ids=nodes, edge_ids=edges, investigation_id=CASE, created_at=NOW,
        typology="kyc_screening", citations=citations,
        words=f"Halcyon Marine Ltd is ultimately owned 48% by Elena Petrov: Elena Petrov "
              f"{SCREENING_MATCH_WORDS} — a suggestion to confirm, not a finding",
        **more,
    )  # fmt: skip


BOTH = _screening("both", [CITE_A, CITE_B])
ONLY_A = _screening("both", [CITE_A])


def _says_nothing_of_b(served: Alert) -> None:
    """Nothing of list B in an alert as served: its name, its ids, or a second citation."""
    text = served.model_dump_json()
    assert "Synthetic list B" not in text and B_WORDS not in text, text
    assert not NOT_B & {*served.referent_node_ids, *served.edge_ids}, served
    assert [c.words for c in served.citations] == [A_WORDS]


def _comparable(served: Alert) -> dict[str, Any]:
    return served.model_dump(exclude={"status", "assignee", "disposition", "disposition_reason",
                                      "decided_by", "close_proposed_by"})  # fmt: skip


# --- the reader's view, as each path serves it -----------------------------------------------------


async def test_the_queue_shows_a_reader_cleared_for_one_list_that_list_alone() -> None:
    store, graph, analytics, _ = _world(NOT_B, [BOTH])
    (queued,) = await alert_queue.monitoring_queue(store, graph, analytics, CASE, READER)  # type: ignore[arg-type]
    _says_nothing_of_b(queued.alert)
    assert "Synthetic list B" not in queued.summary and "Synthetic list A" in queued.summary
    assert "matches “PETROVA, Elena” on a sanctions list (Synthetic list A)" in queued.summary


async def test_what_the_queue_serves_is_what_an_alert_citing_that_list_alone_would_be() -> None:
    """No count: the alert citing both lists, served to a reader cleared for one, is the alert
    citing that one alone, its summary too."""
    served = []
    for alert in (BOTH, ONLY_A):
        store, graph, analytics, _ = _world(NOT_B, [alert])
        (queued,) = await alert_queue.monitoring_queue(store, graph, analytics, CASE, READER)  # type: ignore[arg-type]
        served.append((queued.alert.model_dump(), queued.summary))
    assert served[0] == served[1]


async def test_a_reader_cleared_for_both_is_shown_both() -> None:
    store, graph, analytics, _ = _world(set(), [BOTH])
    (queued,) = await alert_queue.monitoring_queue(store, graph, analytics, CASE, READER)  # type: ignore[arg-type]
    assert [c.words for c in queued.alert.citations] == [A_WORDS, B_WORDS]
    assert f"matches {A_WORDS}; and {B_WORDS}" in queued.summary


async def test_a_reader_cleared_for_neither_list_is_not_shown_the_alert() -> None:
    store, graph, analytics, _ = _world({"l-a", "s-a", *NOT_B}, [BOTH])
    assert await alert_queue.monitoring_queue(store, graph, analytics, CASE, READER) == []  # type: ignore[arg-type]
    with pytest.raises(AlertNotFoundError):
        await alert_queue.explain(TriageStore([BOTH]), graph, analytics, CASE, BOTH.id, READER)  # type: ignore[arg-type]


async def test_an_alert_whose_owner_the_reader_may_not_read_is_not_shown_whatever_the_lists() -> None:
    """The citations are the only part read one by one: what the alert rests on besides them is
    all or nothing, as before (ADR-039)."""
    store, graph, analytics, _ = _world({"n-b"}, [BOTH])
    assert await alert_queue.monitoring_queue(store, graph, analytics, CASE, READER) == []  # type: ignore[arg-type]


async def test_the_explanation_shows_a_reader_cleared_for_one_list_that_list_alone() -> None:
    _, graph, analytics, _ = _world(NOT_B, [BOTH])
    explained = await alert_queue.explain(TriageStore([BOTH]), graph, analytics, CASE, BOTH.id, READER)  # type: ignore[arg-type]
    _says_nothing_of_b(explained.alert)
    assert "Synthetic list B" not in explained.summary
    assert not NOT_B & {*(n.id for n in explained.nodes), *(e.id for e in explained.edges)}
    assert {"l-a"} <= {n.id for n in explained.nodes} and "s-a" in {e.id for e in explained.edges}


async def test_the_canvas_draws_for_a_reader_cleared_for_one_list_that_list_alone() -> None:
    _, graph, analytics, _ = _world(NOT_B, [BOTH])
    alert, nodes, edges = await alert_queue.canvas_elements(
        TriageStore([BOTH]), graph, analytics, CASE, BOTH.id, READER  # type: ignore[arg-type]
    )
    _says_nothing_of_b(alert)
    assert not NOT_B & {*(n.id for n in nodes), *(e.id for e in edges)}


TRIAGE = ["claim", "release", "dispose", "approve_close", "send_back", "assign"]


@pytest.mark.parametrize("path", TRIAGE)
async def test_each_triage_returns_to_a_reader_cleared_for_one_list_that_list_alone(path: str) -> None:
    """What a claim, release, close (proposed, approved or sent back) or assignment returns is the
    stored row as the triage left it, served as the reader was shown the alert."""
    alert = BOTH.model_copy(
        update={"status": "closing" if path in ("approve_close", "send_back") else "claimed"
                if path == "release" else "open", "close_proposed_by": "other", "disposition":
                "false_positive", "assignee": READER.id if path == "release" else None}
    )  # fmt: skip
    _, graph, analytics, _ = _world(NOT_B, [alert])
    store = TriageStore([alert])
    returned = await _path(path)(store, graph, analytics, alert.id)
    assert store.writes == [f"triage {alert.id}"]
    _says_nothing_of_b(returned)


async def test_a_suppression_returns_to_a_reader_cleared_for_one_list_that_list_alone() -> None:
    """*Suppress until…* by the team's lead returns the stored row, served as the lead was shown it."""

    class _Suppressing(TriageStore):
        async def set_suppression(self, alert_id: str, *_: Any, **__: Any) -> Alert:
            self.writes.append(f"suppress {alert_id}")
            return next(a for a in self.alerts if a.id == alert_id)

    alert = BOTH.model_copy(update={"routed_team": "team-1"})
    _, graph, analytics, _ = _world(NOT_B, [alert])
    store = _Suppressing([alert])
    returned = await alert_queue.suppress(
        store, graph, analytics, CASE, alert.id, READER,  # type: ignore[arg-type]
        until=NOW.date(), reason="Known", lead_of={"team-1"}, today=NOW.date(),
    )  # fmt: skip
    assert store.writes == [f"suppress {alert.id}"]
    _says_nothing_of_b(returned)


@pytest.mark.parametrize("path", [*TRIAGE, "canvas_elements"])
async def test_each_path_refuses_a_reader_cleared_for_neither_list_as_for_a_missing_alert(
    path: str,
) -> None:
    alert = BOTH.model_copy(
        update={"status": "closing" if path in ("approve_close", "send_back") else "claimed"
                if path == "release" else "open", "close_proposed_by": "other", "disposition":
                "false_positive", "assignee": READER.id if path == "release" else None}
    )  # fmt: skip
    _, graph, analytics, _ = _world({"l-a", "s-a", *NOT_B}, [alert])
    store = TriageStore([alert])
    with pytest.raises(AlertNotFoundError):
        await _path(path)(store, graph, analytics, alert.id)
    assert store.writes == []


class _PackAlerts(TriageStore):
    """What `packs.readable` asks of the alert store: the alerts by id as stored, and which the
    reader's routing admits (every one here: none is routed to a team)."""

    async def cited_by_ids(self, alert_ids: Any) -> dict[str, Alert]:
        return {a.id: a for a in self.alerts if a.id in set(alert_ids)}

    async def routed_readable(self, alert_ids: Any, reader: Any) -> set[str]:
        return set(alert_ids)


async def _pack_item(adder_cannot_read: set[str]) -> packs.StoredPackItem:
    """The alert added to a pack by a reader who cannot read `adder_cannot_read`, as the route
    builds it: from the explanation as they are shown it."""
    _, graph, analytics, _ = _world(adder_cannot_read, [BOTH])
    explained, events = await alert_queue.explain_with_evidence(
        TriageStore([BOTH]), graph, analytics, CASE, BOTH.id, READER  # type: ignore[arg-type]
    )
    return packs.alert_item(explained, events, READER, load_uk_le_scheme())


async def _pack_shows(item: packs.StoredPackItem, reader_cannot_read: set[str]) -> bool:
    _, graph, analytics, _ = _world(reader_cannot_read, [BOTH])
    shown, _withheld = await packs.readable(
        [item], READER, load_uk_le_scheme(), graph, CASE,  # type: ignore[arg-type]
        alerts=_PackAlerts([BOTH]), analytics=analytics,  # type: ignore[arg-type]
    )  # fmt: skip
    return bool(shown)


async def test_a_pack_item_added_by_a_reader_cleared_for_one_list_holds_that_list_alone() -> None:
    item = await _pack_item(NOT_B)
    assert item.alert is not None
    text = item.served().model_dump_json()
    assert "Synthetic list B" not in text and not NOT_B & set(item.alert.node_ids), text
    assert "Synthetic list A" in item.alert.explanation


async def test_a_pack_item_is_read_by_the_matches_it_shows() -> None:
    """Its adder, cleared for A alone, reads it back; an item showing both lists is withheld from
    a reader cleared for A alone, and shown to one cleared for both."""
    one, both = await _pack_item(NOT_B), await _pack_item(set())
    assert await _pack_shows(one, NOT_B)
    assert not await _pack_shows(both, NOT_B)
    assert await _pack_shows(both, set())


class _Audit:
    def __init__(self, entries: list[Any]) -> None:
        self.entries = entries

    async def list_for_case(self, investigation_id: str, actions: Any) -> list[Any]:
        return list(self.entries)


async def test_the_rule_audit_withholds_a_firing_citing_a_list_the_reader_may_not_read() -> None:
    """Strict, and the spec's "Not changed": an entry about an alert is read by everything the
    alert cites, its citations included, so its ids (which name every list's match) reach only a
    reader cleared for every list; one cleared for A alone is given no entry about it, and no count
    (`total`)."""
    from services.api.rule_holds import readable_rule_audit

    from schemas.domain import RuleAuditEntry

    firing = RuleAuditEntry(recorded_at=NOW, principal_id="deployer", action="rule_fired", result_cardinality=1,
                            detail={"rule_id": "kyc", "alert_id": BOTH.id, "words": BOTH.words,
                                    "node_ids": BOTH.referent_node_ids, "edge_ids": BOTH.edge_ids})  # fmt: skip
    pages = []
    for hidden in (NOT_B, set()):
        _, graph, analytics, _ = _world(hidden, [BOTH])
        page = await readable_rule_audit(
            _Audit([firing]), graph, CASE, READER, analytics=analytics,  # type: ignore[arg-type]
            alerts=_PackAlerts([BOTH]),  # type: ignore[arg-type]
        )  # fmt: skip
        pages.append((len(page.entries), page.total))
    assert pages == [(0, 0), (1, 1)]


# --- the pieces each path is built from ------------------------------------------------------------


def test_as_read_keeps_the_stored_order_and_drops_a_hidden_citation_whole() -> None:
    readable = ReadableEvidence(
        {i: object() for i in ("n-a", "n-b", "l-b")},  # type: ignore[misc]
        frozenset({"e-1", "s-b"}),
        frozenset(),
    )
    assert readable.whole(BOTH) and readable.citations_read(BOTH) == [1]
    served = as_read(BOTH, readable.citations_read(BOTH))
    assert [c.words for c in served.citations] == [B_WORDS]
    assert "l-a" not in served.referent_node_ids and "s-a" not in served.edge_ids
    assert served.words is not None and "Synthetic list A" not in served.words


def test_a_citation_is_read_whole_or_not_at_all() -> None:
    """Its listed party readable but not its `SAME_AS`: the citation is hidden."""
    readable = ReadableEvidence(
        {i: object() for i in ("n-a", "n-b", "l-a", "l-b")},  # type: ignore[misc]
        frozenset({"e-1", "s-a"}),
        frozenset(),
    )
    assert readable.citations_read(BOTH) == [0]


def test_an_alert_without_citations_is_served_as_stored() -> None:
    plain = BOTH.model_copy(update={"citations": []})
    assert as_read(plain, []) is plain


def test_a_pack_item_asks_its_reader_for_the_matches_it_shows_and_no_other() -> None:
    """A pack's alert item is frozen as its adder was shown it: one made by a reader cleared for A
    alone asks a later reader for A's match, and one showing both asks for both."""
    assert edges_shown_with(BOTH, ["n-a", "n-b", "l-a"]) == ["e-1", "s-a"]
    assert edges_shown_with(BOTH, ["n-a", "n-b", "l-a", "l-b"]) == ["e-1", "s-a", "s-b"]


def test_the_stored_words_name_no_list_and_say_no_count() -> None:
    """What the alert is stored with (its row, its `Alert` node, its audit entry) names neither
    list; only `as_read` puts the matches a reader may see in place."""
    assert BOTH.words is not None
    assert "Synthetic list" not in BOTH.words and SCREENING_MATCH_WORDS in BOTH.words
