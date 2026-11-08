"""ADR-146 decision 10 (gap map G2, and the orchestrator's item ii) against the real stores: live
ArcadeDB (the graph's own access step, `get_nodes`/`get_edges`), Postgres (`AlertStore`, the audit),
Valkey and the real DuckDB analytics adapter (`list_events`), with the hidden link and transactions
written the way the loader writes them (`load_with_rules`), never hand-marked. The hermetic cases
are `tests/services/api/test_alert_evidence_withheld.py` and `test_alert_node_marking.py`.

What the loader can and cannot produce, measured here (`test_the_loader_writes_a_link_and_its_
transactions_above_their_ends`): a SECRET load over accounts an OFFICIAL load already wrote resolves
onto those OFFICIAL accounts and writes its own SECRET `TRANSACTED` link and SECRET transactions
between them (the adapter matches a link by its audience, so it never folds into a readable one). A
link and its transactions always carry the row's one marking, so the loader cannot write a link
marked above its own transactions; and since ed8b0aa a rule's `Alert` node is never marked below
anything it cites. The queue's link and transaction check therefore changes the answer for an alert
**raised without its node**: its referents' units conflict, a referent unseen in its load, or a link
it cites unreadable when it is raised (b21f316). Those rows are raised here through the real
`RuleGate` (`raise_committed` for the reverted link; `_raise_row`, the one function every no-node
raise goes through, for the marked link and the marked transactions), over the loader's own link
and transactions.

Every red was shown with the queue's check put back to nodes alone
(`ReadableEvidence.whole` without its two link and transaction lines), and the marking's with the
cited links left out of `_referent_handlings`; the outputs are kept with the lane's record.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from services.api import alert_queue
from services.api.alerts import AlertNotFoundError
from services.api.rule_evaluation import Finding, PreCommitVerdict, RuleGate, RuleWrites

from conduit_common.identity import new_id
from ports.analytics import AnalyticsPort
from schemas.analytics import EventFilter, EventListRequest
from schemas.domain import Alert, Principal, TypologyRuleInput
from tests.ingest import test_typology_rules as _rules_suite
from tests.ingest.test_typology_rules import (
    ANALYST,
    ONTOLOGY,
    RECIPE,
    SCHEME,
    SECRET_LOADER,
    T0,
    _case_alerts,
    _gate,
    _load,
    _marked,
    _raised,
    _row,
    _structuring,
    arcadedb_adapter,
)
from tests.services.api.repoint_journal_cleanup import remove_repoint_records  # noqa: F401 - autouse teardown

#: The rules suite's own live stores and DuckDB analytics, as fixtures of this file.
stores = _rules_suite.stores
analytics = _rules_suite.analytics

#: A case teammate who may read OFFICIAL: everything the alerts here name, but none of the SECRET.
TEAMMATE = Principal(id="analyst-teammate-live", clearance="OFFICIAL", org_unit="verify")


async def _hidden_world(stores: dict[str, Any], graph: Any, analytics: AnalyticsPort, case: str,
                        tag: str) -> tuple[Alert, list[Any]]:  # fmt: skip
    """An OFFICIAL load writes two accounts (each with a quiet payment elsewhere); a SECRET load of
    structuring between them raises its alert, as a SECRET deployer's pre-commit rule does. The
    alert and the SECRET transactions it cites, as the loader wrote them."""
    quiet = _gate(stores, graph, analytics, [], case)
    await _load(graph, analytics, quiet,
                [_row(f"GB{tag}MULE", f"GB{tag}X", 10, T0 - timedelta(days=30)),
                 _row(f"GB{tag}HUB", f"GB{tag}Y", 10, T0 - timedelta(days=30))])  # fmt: skip
    rule = await stores["rules"].create(SECRET_LOADER, case, _structuring("pre_commit"))
    rows = [
        _row(f"GB{tag}MULE", f"GB{tag}HUB", 9_500, T0 + timedelta(hours=6 * i)) for i in range(4)
    ]
    await _load(graph, analytics, _gate(stores, graph, analytics, [rule], case, loader=SECRET_LOADER),
                rows, recipe=_marked(RECIPE, "SECRET"), loader=SECRET_LOADER)  # fmt: skip
    (alert,) = await _case_alerts(stores, SECRET_LOADER, case)
    page = await analytics.list_events(
        EventListRequest(filter=EventFilter(investigation_scope=case, event_ids=alert.event_ids),
                         limit=200), SECRET_LOADER)  # fmt: skip
    return alert, list(page.events)


async def _rule_of(stores: dict[str, Any], case: str, alert: Alert) -> Any:
    """The rule that raised `alert` in the case, found by its own id. Never by unpacking the case's
    active rules: `list_active_for_case` also lists every deployment-wide rule active in the
    store, which other live files leave in a shared database (found by the case lane, L2.8b)."""
    rule_id = alert.rule_id.removeprefix("typology:")
    (rule,) = [r for r in await stores["rules"].list_active_for_case(case) if r.id == rule_id]
    return rule


async def _refused_as_missing(stores: dict[str, Any], graph: Any, analytics: AnalyticsPort, case: str,
                              alert_id: str, reader: Principal) -> None:  # fmt: skip
    """The explanation, the canvas and a claim each refuse the alert exactly as they refuse an id
    that never existed: the same error, carrying only the id asked for."""
    missing = new_id()
    for path in (alert_queue.explain, alert_queue.canvas_elements, alert_queue.claim):
        answers = []
        for asked in (alert_id, missing):
            with pytest.raises(AlertNotFoundError) as refused:
                await path(stores["alerts"], graph, analytics, case, asked, reader)
            answers.append((type(refused.value), refused.value.args == (asked,)))
        assert answers[0] == answers[1] == (AlertNotFoundError, True), path.__name__


async def _listed(stores: dict[str, Any], graph: Any, analytics: AnalyticsPort, case: str,
                  reader: Principal) -> list[str]:  # fmt: skip
    return sorted(
        q.alert.id
        for q in await alert_queue.queue(stores["alerts"], graph, analytics, case, reader)
    )


async def test_the_loader_writes_a_link_and_its_transactions_above_their_ends(
    stores: dict[str, Any], analytics: AnalyticsPort
) -> None:
    """The measurement: what the loader itself can produce. Its alert is withheld whole, and by its
    own SECRET node too, which is why the cases below raise rows without one."""
    case = f"case-{new_id()}"
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        alert, events = await _hidden_world(stores, graph, analytics, case, "LW")
        ends = await graph.get_nodes(alert.referent_node_ids, TEAMMATE)
        assert {n.handling.classification for n in ends} == {"OFFICIAL"} and len(ends) == 2
        (link,) = await graph.get_edges(alert.edge_ids, SECRET_LOADER)
        assert link.handling.classification == "SECRET" and {link.source, link.target} == {
            n.id for n in ends
        }
        assert await graph.get_edges(alert.edge_ids, TEAMMATE) == []
        assert {e.handling.classification for e in events} == {"SECRET"} and len(events) == 4
        node = await graph.get_node(alert.alert_node_id, SECRET_LOADER)  # type: ignore[arg-type]
        assert node is not None and node.handling.classification == "SECRET"
        assert await _listed(stores, graph, analytics, case, TEAMMATE) == []
        await _refused_as_missing(stores, graph, analytics, case, alert.id, TEAMMATE)


async def test_an_alert_raised_without_its_node_over_a_hidden_link_or_transactions_is_withheld_whole(
    stores: dict[str, Any], analytics: AnalyticsPort
) -> None:
    """Two no-node rows over what the loader wrote: one citing only the SECRET link, one only the
    SECRET transactions; each between the two OFFICIAL accounts the teammate can read. The teammate
    is told of neither, and each is refused as a missing id; the SECRET deployer has both. Red with
    nodes alone: the teammate was listed both and could open each."""
    case = f"case-{new_id()}"
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        loaded, events = await _hidden_world(stores, graph, analytics, case, "NN")
        gate = _gate(stores, graph, analytics, [], case, loader=SECRET_LOADER)
        rule = await _rule_of(stores, case, loaded)

        def finding(**cited: Any) -> Finding:
            return Finding(rule=rule, deployer=SECRET_LOADER, typology="structuring",
                           subject=loaded.referent_node_ids[0], refs=(), words=loaded.words or "",
                           node_ids=list(loaded.referent_node_ids), **cited)  # fmt: skip

        by_link = await gate._raise_row(
            finding(edge_ids=list(loaded.edge_ids)), None, withheld="units"
        )
        by_transactions = await gate._raise_row(
            finding(events=tuple(events)), None, withheld="units"
        )
        assert by_link.alert_node_id is None and by_transactions.alert_node_id is None
        assert by_link.event_ids == [] and by_transactions.edge_ids == []

        assert await _listed(stores, graph, analytics, case, TEAMMATE) == []
        for withheld in (by_link, by_transactions):
            await _refused_as_missing(stores, graph, analytics, case, withheld.id, TEAMMATE)
        assert await _listed(stores, graph, analytics, case, SECRET_LOADER) == sorted(
            [loaded.id, by_link.id, by_transactions.id])  # fmt: skip


async def test_a_row_raised_over_a_link_reverted_since_the_judgement_is_listed_for_no_one(
    stores: dict[str, Any], analytics: AnalyticsPort
) -> None:
    """b21f316's fallback through the real gate: the finding cites a link the loader wrote and a
    revert then took back; `raise_committed` raises the row with no node. A reverted link is hidden
    from every reader, so the row is listed for no one and refused to each as missing. Red with
    nodes alone: both readers were listed it and could open it."""
    case = f"case-{new_id()}"
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        loaded, _ = await _hidden_world(stores, graph, analytics, case, "RV")
        around = await graph.expand(_expand(loaded.referent_node_ids), TEAMMATE)
        quiet_link = next(e for e in around.edges if e.type == "TRANSACTED")
        tx = await graph.begin_transaction()
        await graph.revert_elements([], [quiet_link.id], tx)
        await graph.commit_transaction(tx)

        gate = _gate(stores, graph, analytics, [], case, loader=ANALYST)
        rule = await stores["rules"].create(ANALYST, case, _structuring("post_commit"))
        raised = await gate.raise_committed(
            Finding(rule=rule, deployer=ANALYST, typology="structuring", subject=quiet_link.source,
                    refs=("finding",), words="A quiet payment", node_ids=[quiet_link.source, quiet_link.target],
                    edge_ids=[quiet_link.id]))  # fmt: skip
        assert raised.alert_node_id is None
        for reader in (TEAMMATE, SECRET_LOADER):
            assert raised.id not in await _listed(stores, graph, analytics, case, reader), reader.id
            await _refused_as_missing(stores, graph, analytics, case, raised.id, reader)


def _expand(node_ids: list[str]) -> Any:
    from schemas.domain import ExpandRequest

    return ExpandRequest(node_ids=node_ids, depth=1, direction="both")


async def test_an_alert_over_a_link_marked_above_its_ends_is_not_readable_as_a_node(
    stores: dict[str, Any], analytics: AnalyticsPort
) -> None:
    """Item ii live. The loader cannot write a link marked above its own transactions (above), so
    the finding is the shape a KYC finding has, nodes and links and no transactions: the two
    OFFICIAL accounts and the loader's SECRET link between them, raised by the real gate. Its node
    is SECRET: the teammate cannot read it by id, nor find it among the `Alert` nodes listed to them
    (`list_nodes`, the bulk read; `search_nodes` matches declared identifiers, and `Alert` declares
    none), nor open it on the canvas. Red with the links left out of the marking: the node was
    OFFICIAL, and read and listed to the teammate, the finding's words with it."""
    case = f"case-{new_id()}"
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        loaded, _ = await _hidden_world(stores, graph, analytics, case, "MK")
        rule = await _rule_of(stores, case, loaded)
        gate = _gate(stores, graph, analytics, [], case, loader=SECRET_LOADER)
        raised = await gate.raise_committed(
            Finding(rule=rule, deployer=SECRET_LOADER, typology="structuring",
                    subject=loaded.referent_node_ids[0], refs=("finding",), words="Paid across a SECRET link",
                    node_ids=list(loaded.referent_node_ids), edge_ids=list(loaded.edge_ids)))  # fmt: skip
        assert raised.alert_node_id is not None
        node = await graph.get_node(raised.alert_node_id, SECRET_LOADER)
        assert node is not None and node.handling.classification == "SECRET"
        assert await graph.get_node(raised.alert_node_id, TEAMMATE) is None
        listed: list[str] = []
        cursor = None
        while True:
            page = await graph.list_nodes("Alert", TEAMMATE, cursor=cursor)
            listed.extend(n.id for n in page.nodes)
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
        assert raised.alert_node_id not in listed
        with pytest.raises(AlertNotFoundError):
            await alert_queue.canvas_elements(
                stores["alerts"], graph, analytics, case, raised.id, TEAMMATE
            )


async def test_in_a_load_a_cited_link_that_cannot_be_read_writes_no_node_and_still_raises_the_row(
    stores: dict[str, Any], analytics: AnalyticsPort
) -> None:
    """`_alert_node_in_load`'s own contract, the companion the orchestrator asked for: in the
    load's transaction, a cited link whose marking cannot be read and no highest marking to stand
    in (`unseen=None`) writes no node, rather than one marked below the link; the row is still
    raised after the commit, and the audit says why. No real load reaches this today: every load
    that runs rules passes `unseen` (`studio_publish.py`, `recipe_handlings`), and a link the load
    writes stands in at its marking as written (the test below). Red with the fallback removed
    (the link skipped, not refused): a node was written at the accounts' OFFICIAL."""
    case = f"case-{new_id()}"
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        loaded, _ = await _hidden_world(stores, graph, analytics, case, "IL")
        tx = await graph.begin_transaction()
        await graph.revert_elements([], list(loaded.edge_ids), tx)
        await graph.commit_transaction(tx)
        rule = await _rule_of(stores, case, loaded)
        gate: RuleGate = _gate(stores, graph, analytics, [], case, loader=SECRET_LOADER)
        finding = Finding(rule=rule, deployer=SECRET_LOADER, typology="structuring",
                          subject=loaded.referent_node_ids[0], refs=("finding",), words="In the load",
                          node_ids=list(loaded.referent_node_ids), edge_ids=list(loaded.edge_ids))  # fmt: skip
        tx = await graph.begin_transaction()
        node_id, why, _ = await gate._alert_node_in_load(finding, tx, unseen=None, load_id=new_id(),
                                                      known={}, writes=RuleWrites())  # fmt: skip
        await graph.commit_transaction(tx)
        assert (node_id, why) == (None, "unreadable_link")
        (raised,) = await gate.after_commit(
            PreCommitVerdict(findings=[(finding, None)], withheld={0: why})
        )
        assert raised.alert_node_id is None
        assert raised.id in [a.id for a in await _case_alerts(stores, SECRET_LOADER, case)]


def _referencing_with_a_secret_override() -> Any:
    """The ledger recipe, with its payee given a SECRET override it never writes: the payee is a
    reference (`on_match: reference`) to an account already loaded, so every row's link, its
    transactions and both its ends are OFFICIAL, while the highest marking the recipe could give
    a row (`recipe_handlings`, the load's `unseen`) is SECRET."""
    template = RECIPE.row_template.model_copy(deep=True)
    payee = next(e for e in template.entities if e.ref == "payee")
    payee.handling = {"classification": "SECRET"}
    return RECIPE.model_copy(update={"row_template": template})


async def test_in_a_load_a_link_the_load_writes_is_marked_as_written_not_at_the_recipes_highest(
    stores: dict[str, Any], analytics: AnalyticsPort
) -> None:
    """The lane-reviewer's finding 2, at the real call site (`load_with_rules` → `pre_commit`,
    `unseen` set from the recipe): the link a load writes cannot be read back before the commit, so
    its marking as written stands in, as a node's does. Red before the fix: `known` held the
    nodes' markings alone, the link took the recipe's highest (SECRET), and the alert's node with
    it, so a teammate who may read every account, link and transaction the alert cites was told
    nothing of it."""
    case = f"case-{new_id()}"
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        quiet = _gate(stores, graph, analytics, [], case)
        await _load(graph, analytics, quiet,
                    [_row("GBOVMULE", "GBOVX", 10, T0 - timedelta(days=30)),
                     _row("GBOVY", "GBOVHUB", 10, T0 - timedelta(days=30))])  # fmt: skip
        rule = await stores["rules"].create(ANALYST, case, _structuring("pre_commit"))
        rows = [_row("GBOVMULE", "GBOVHUB", 9_500, T0 + timedelta(hours=6 * i)) for i in range(4)]
        await _load(graph, analytics, _gate(stores, graph, analytics, [rule], case), rows,
                    recipe=_referencing_with_a_secret_override())  # fmt: skip
        (alert,) = await _case_alerts(stores, ANALYST, case)
        (link,) = await graph.get_edges(alert.edge_ids, TEAMMATE)
        assert link.handling.classification == "OFFICIAL"
        node = await graph.get_node(alert.alert_node_id, ANALYST)  # type: ignore[arg-type]
        assert node is not None and node.handling.classification == "OFFICIAL"
        assert await _listed(stores, graph, analytics, case, TEAMMATE) == [alert.id]


async def test_a_confirmed_match_repoints_every_alert_citing_it_so_none_leaves_the_queue(
    stores: dict[str, Any], analytics: AnalyticsPort
) -> None:
    """The orchestrator's Q2 (the lane-reviewer's finding 5). A true positive on a screening alert
    confirms its inferred `SAME_AS`, which the graph supersedes with a new revision, and the
    closed alert cites the new one. A second open alert citing the same match cited the old
    revision, which `get_edges` no longer returns, so G2's link check withheld it from every reader
    while its trend fact still counted it open. Now every alert citing a confirmed link is
    repointed in the close's own transaction (`AlertStore.set_queue_triage`). Red without the
    repoint: the second alert was gone from the queue.

    The readers (rule 3: the repoint must never widen what anyone reads). The match is SECRET; the
    two people it joins are OFFICIAL. The reader who closes the first alert and keeps the second,
    SECRET-cleared, may read the new revision, and could read the old one, which carried nothing
    more (a confirmed revision keeps the match's marking). The OFFICIAL teammate may read both
    people but not the match, old or new: the queue's full check still runs on the repointed row
    for them, and they are never given it. Red for that half with the link check skipped
    (`ReadableEvidence.whole` without its links): the teammate was given the repointed alert."""
    from conduit_common.identity import new_edge_id, new_node_id
    from schemas.domain import (
        AlertMode,
        EdgeWrite,
        Handling,
        NodeWrite,
        Provenance,
        ProvenanceState,
        SourceRef,
    )

    case = f"case-{new_id()}"
    now = T0
    official = Handling(classification="OFFICIAL", handling_code="P", originator="verify",
                        owning_unit="verify")  # fmt: skip
    secret = official.model_copy(update={"classification": "SECRET"})
    cleared = SECRET_LOADER
    asserted = Provenance(state=ProvenanceState.ASSERTED, first_seen=now,
                          sources=[SourceRef(document_id="t", locator="r", excerpt_hash="")])  # fmt: skip
    person, listed = (
        NodeWrite(id=new_node_id(), type="Person", properties={"family_name": n}, provenance=asserted,
                  handling=official, created_by="t", created_at=now)
        for n in ("Petrov", "PETROVA")
    )  # fmt: skip
    match = EdgeWrite(
        id=new_edge_id(), type="SAME_AS", source=person.id, target=listed.id,
        properties={"score": 0.98, "model_version": "screening:Synthetic list"}, basis="probabilistic",
        provenance=Provenance(state=ProvenanceState.INFERRED, first_seen=now, extracted_by="screening:t",
                              sources=[SourceRef(document_id="list", locator="e-1", excerpt_hash="")]),
        handling=secret, created_by="t", created_at=now,
    )  # fmt: skip
    facts: list[Any] = []

    async def keep(batch: list[Any]) -> None:
        facts.extend(batch)

    stores["alerts"].fact_sink = keep
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        tx = await graph.begin_transaction()
        await graph.upsert_nodes([person, listed], tx)
        (link,) = await graph.upsert_edges([match], tx)
        await graph.commit_transaction(tx)
        first, second = (
            Alert(id=new_id(), rule_id=f"typology:{new_id()}", owner_id=ANALYST.id, mode=AlertMode.FULL,
                  referent_node_ids=[person.id, listed.id], edge_ids=[link], investigation_id=case,
                  created_at=now, typology="kyc_screening", words=f"Petrov matches PETROVA ({i})",
                  severity="medium")
            for i in (1, 2)
        )  # fmt: skip
        for alert in (first, second):
            await stores["alerts"].save(alert, handlings=[official, secret])
        assert await _listed(stores, graph, analytics, case, cleared) == sorted([first.id, second.id])
        assert await _listed(stores, graph, analytics, case, TEAMMATE) == []

        closed = await alert_queue.dispose(stores["alerts"], graph, analytics, case, first.id, cleared,
                                           disposition="true_positive", reason="matches the entry")  # fmt: skip
        (revision,) = closed.edge_ids
        assert revision != link, "the confirmed match is a new revision"
        queued = {q.alert.id: q.alert for q in await alert_queue.queue(stores["alerts"], graph, analytics,
                                                                         case, cleared)}  # fmt: skip
        assert second.id in queued, "the second alert citing the match is still in the queue"
        assert queued[second.id].edge_ids == [revision]
        (fact,) = [f for f in facts if f.alert_id == second.id][-1:]
        assert fact.outcome == "open", "and its trend fact agrees: open"
        assert await _listed(stores, graph, analytics, case, TEAMMATE) == [], (
            "the repointed alert is still checked whole: one who may not read the match is not given it"
        )
        with pytest.raises(AlertNotFoundError):
            await alert_queue.explain(stores["alerts"], graph, analytics, case, second.id, TEAMMATE)


def _people_and_matches(n_matches: int) -> tuple[list[Any], list[Any], Any]:
    """`n_matches + 1` OFFICIAL people and `n_matches` inferred `SAME_AS` links, the i-th from the
    first person to person i + 1, as the screening rule writes a match (a score,
    `basis="probabilistic"`, inferred, sourced to the list entry). Each joins its own pair: the
    adapter merges same-pair links of one audience into one, which would make two matches one."""
    from conduit_common.identity import new_edge_id, new_node_id
    from schemas.domain import (
        EdgeWrite,
        Handling,
        NodeWrite,
        Provenance,
        ProvenanceState,
        SourceRef,
    )

    official = Handling(classification="OFFICIAL", handling_code="P", originator="verify",
                        owning_unit="verify")  # fmt: skip
    asserted = Provenance(state=ProvenanceState.ASSERTED, first_seen=T0,
                          sources=[SourceRef(document_id="t", locator="r", excerpt_hash="")])  # fmt: skip
    names = ["Petrov", *(f"PETROVA {i}" for i in range(max(n_matches, 1)))]
    people = [NodeWrite(id=new_node_id(), type="Person", properties={"family_name": n}, provenance=asserted,
                        handling=official, created_by="t", created_at=T0) for n in names]  # fmt: skip
    matches = [
        EdgeWrite(id=new_edge_id(), type="SAME_AS", source=people[0].id, target=people[i + 1].id,
                  properties={"score": 0.9 + i / 100, "model_version": f"screening:list-{i}"},
                  basis="probabilistic", handling=official, created_by="t", created_at=T0,
                  provenance=Provenance(state=ProvenanceState.INFERRED, first_seen=T0, extracted_by="screening:t",
                                        sources=[SourceRef(document_id=f"list-{i}", locator="e-1", excerpt_hash="")]))
        for i in range(n_matches)
    ]  # fmt: skip
    return people, matches, official


def _screening_alert(case: str, people: list[Any], edge_ids: list[str], words: str) -> Alert:
    from schemas.domain import AlertMode

    return Alert(id=new_id(), rule_id=f"typology:{new_id()}", owner_id=ANALYST.id, mode=AlertMode.FULL,
                 referent_node_ids=[p.id for p in people], edge_ids=edge_ids, investigation_id=case,
                 created_at=T0, typology="kyc_screening", words=words, severity="medium")  # fmt: skip


async def test_a_close_never_writes_back_a_list_another_close_has_repointed_since(
    stores: dict[str, Any], analytics: AnalyticsPort
) -> None:
    """Round 1's point 1. Alert A cites two matches, L and M; alert B cites L. A's close read A's
    links (unlocked) before B's close confirmed L and repointed A to L's new revision; A's close then
    confirms M. Writing back the list A's close had read put the superseded L back, hiding A for
    good. Now the rename is applied in SQL to the locked row as it stands. Red with the stale
    write-back (`edge_ids=` the list read before): A cited L again and could not be opened."""
    case = f"case-{new_id()}"
    people, (l_match, m_match), official = _people_and_matches(2)
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        tx = await graph.begin_transaction()
        await graph.upsert_nodes(people, tx)
        l_id, m_id = await graph.upsert_edges([l_match, m_match], tx)
        await graph.commit_transaction(tx)
        assert l_id != m_id, "two matches, two links"
        a = _screening_alert(case, people, [l_id, m_id], "A: Petrov matches two entries")
        b = _screening_alert(case, people[:2], [l_id], "B: Petrov matches PETROVA 0")
        for alert in (a, b):
            await stores["alerts"].save(alert, handlings=[official])
        read_before = a  # A as its close read it, before B's close
        nodes = {n.id: n for n in await graph.get_nodes(read_before.referent_node_ids, ANALYST)}

        closed_b = await alert_queue.dispose(stores["alerts"], graph, analytics, case, b.id, ANALYST,
                                             disposition="true_positive", reason="B matches")  # fmt: skip
        (l_new,) = closed_b.edge_ids
        closed_a = await alert_queue._close(stores["alerts"], graph, case, read_before, nodes, ANALYST,
                                            disposition="true_positive", reason="A matches",
                                            expect=["open", "claimed"])  # fmt: skip
        assert l_id not in closed_a.edge_ids and m_id not in closed_a.edge_ids, closed_a.edge_ids
        assert closed_a.edge_ids[0] == l_new
        why = await alert_queue.explain(stores["alerts"], graph, analytics, case, a.id, ANALYST)
        assert {e.id for e in why.edges if e.type == "SAME_AS"} == set(closed_a.edge_ids)


async def test_two_closes_confirming_one_match_both_complete(
    stores: dict[str, Any], analytics: AnalyticsPort
) -> None:
    """Round 1's point 2: two closes sharing one match, at once. Each locked its own row first and
    then the rows citing the match, in no order, so each could hold the row the other waited for: a
    deadlock, one close refused after its graph commit. Now every row is locked in one id-ordered
    statement. Twenty pairs at once, each pair two alerts citing one match, at the store, with no
    graph: both of every pair complete and cite the new revision. Red with the old locking (16629dc,
    the closing row locked first and the rest after, unordered): Postgres found deadlocks and
    refused 11 of 40 closes."""
    import asyncio

    _, _, official = _people_and_matches(0)
    case = f"case-{new_id()}"
    pairs = []
    for i in range(20):
        old, new = f"link-{new_id()}", f"link-{new_id()}"
        pair = [_screening_alert(case, [], [old], f"pair {i}") for _ in range(2)]
        for alert in pair:
            alert = alert.model_copy(update={"referent_node_ids": []})
            await stores["alerts"].save(alert, handlings=[official])
        pairs.append((pair, old, new))

    async def close(old: str, new: str) -> list[str]:
        """Each close's repoint of the match it confirmed (`AlertStore.apply_repoints`, since L2.8b
        the repoint of the supersede itself, not of the triage write)."""
        return await stores["alerts"].apply_repoints({old: new})

    done = await asyncio.gather(*(close(old, new) for _pair, old, new in pairs for _ in range(2)),
                                return_exceptions=True)  # fmt: skip
    refused = [d for d in done if isinstance(d, BaseException)]
    assert refused == [], f"{len(refused)} of {len(done)} closes refused: {refused[:2]}"
    for pair, _old, new in pairs:
        for alert in pair:
            (row,) = [a for a in await stores["alerts"].list_case_queue(case, ANALYST) if a.id == alert.id]
            assert row.edge_ids == [new], pair[0].words


# ---- L2.8b items 6 and 7: a repoint across the graph and Postgres (ADR-109 Amendment 10) ---------


async def _two_alerts_on_one_secret_match(stores: dict[str, Any], graph: Any, case: str) -> tuple[Alert, Alert, str]:
    """Two screening alerts citing one SECRET match between two OFFICIAL people: the cleared reader
    may read both, the OFFICIAL teammate neither (the match is cited)."""
    people, (match,), official = _people_and_matches(1)
    secret = official.model_copy(update={"classification": "SECRET"})
    match = match.model_copy(update={"handling": secret})
    tx = await graph.begin_transaction()
    await graph.upsert_nodes(people, tx)
    (link,) = await graph.upsert_edges([match], tx)
    await graph.commit_transaction(tx)
    first, second = (_screening_alert(case, people, [link], f"Petrov matches PETROVA ({i})") for i in (1, 2))
    for alert in (first, second):
        await stores["alerts"].save(alert, handlings=[official, secret])
    return first, second, link


async def _pending(stores: dict[str, Any], *old_links: str) -> list[tuple[str, str]]:
    """The repoint pairs this test's records hold for its own links (`alert_repoint_records`): the
    table is shared with every other run, so only this test's links are read."""
    async with stores["alerts"]._pool.acquire() as conn:
        rows = await conn.fetch("SELECT links FROM alert_repoint_records")
    pairs = []
    for row in rows:
        links = __import__("json").loads(row["links"]) if isinstance(row["links"], str) else row["links"]
        pairs.extend((old, new) for old, new in links if old in old_links)
    return sorted(pairs)


#: Seconds a concurrent settle may take before its test fails rather than stalls the run.
SETTLE_TIMEOUT = 90


async def _plant_record(stores: dict[str, Any], links: dict[str, str], *, recorded_at: Any = None) -> str:
    """A record as `AlertStore.repointing` writes one."""
    from datetime import UTC, datetime

    record = new_id()
    async with stores["alerts"]._pool.acquire() as conn:
        await conn.execute("INSERT INTO alert_repoint_records (id, recorded_at) VALUES ($1, $2)", record,
                           recorded_at or datetime.now(UTC))  # fmt: skip
    await stores["alerts"]._add_to_record(record, links=list(links.items()))
    return record


async def test_a_failure_between_the_graph_commit_and_the_repoint_hides_no_alert(
    stores: dict[str, Any], analytics: AnalyticsPort, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Item 6, the hard part. The graph commits the confirmed match and then the Postgres repoint
    fails (here, on purpose, once). The close is refused; the repoint is recorded, so the very next
    read settles it from the graph's own stored states: the second alert is listed to the cleared
    reader citing the new revision, the record is cleared, and the OFFICIAL teammate, who may not
    read the match, is still not given it (the settle changes which revision is cited, nothing a
    reader is answered). Red with no record (the repoint inside the triage write, as in L2.8): the
    second alert was gone from the queue for every reader."""
    case = f"case-{new_id()}"
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        first, second, link = await _two_alerts_on_one_secret_match(stores, graph, case)
        real = stores["alerts"].apply_repoints
        failed: list[bool] = []

        async def fails_once(pairs: Any) -> list[str]:
            if pairs and not failed:
                failed.append(True)
                raise ConnectionError("Postgres went away between the two stores")
            return await real(pairs)

        monkeypatch.setattr(stores["alerts"], "apply_repoints", fails_once)
        with pytest.raises(ConnectionError):
            await alert_queue.dispose(stores["alerts"], graph, analytics, case, first.id, SECRET_LOADER,
                                      disposition="true_positive", reason="matches")  # fmt: skip
        (now,) = await graph.get_edges([e.id for e in await graph.edges_among(first.referent_node_ids, SECRET_LOADER)
                                        if e.type == "SAME_AS"], SECRET_LOADER)  # fmt: skip
        assert now.id != link, "the graph committed the confirmed revision"
        queued = {q.alert.id: q.alert for q in await alert_queue.queue(stores["alerts"], graph, analytics,
                                                                         case, SECRET_LOADER)}  # fmt: skip
        assert second.id in queued and queued[second.id].edge_ids == [now.id]
        assert await _pending(stores, link) == []
        assert second.id not in await _listed(stores, graph, analytics, case, TEAMMATE)


async def test_a_graph_failure_leaves_every_alert_on_the_live_link(
    stores: dict[str, Any], analytics: AnalyticsPort, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other side: the graph's commit fails, so the match was never superseded. The record
    waits, unapplied (the writer never drops one; only the stale threshold does), and both alerts
    still cite the live link and are listed."""
    case = f"case-{new_id()}"
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        first, second, link = await _two_alerts_on_one_secret_match(stores, graph, case)
        rollback = graph.rollback_transaction

        async def refuses(tx: Any) -> None:
            await rollback(tx)
            raise ConnectionError("ArcadeDB refused the commit")

        monkeypatch.setattr(graph, "commit_transaction", refuses)
        with pytest.raises(ConnectionError):
            await alert_queue.dispose(stores["alerts"], graph, analytics, case, first.id, SECRET_LOADER,
                                      disposition="true_positive", reason="matches")  # fmt: skip
        monkeypatch.undo()
        # The writer never drops its record (its commit might yet land): it waits, unapplied, for
        # the stale threshold, and changes nothing while the old link is live.
        assert await _listed(stores, graph, analytics, case, SECRET_LOADER) == sorted([first.id, second.id])
        for queued in await alert_queue.queue(stores["alerts"], graph, analytics, case, SECRET_LOADER):
            assert queued.alert.edge_ids == [link]


async def test_a_triage_refused_after_the_graph_commit_still_repoints_every_citing_alert(
    stores: dict[str, Any], analytics: AnalyticsPort, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Item 6 as the brief names it: the close's triage write is refused after the graph committed
    (another member's triage of the same alert at that moment, `AlertTriageConflict`). The match is
    superseded; the second alert cites the new revision and stays listed. Red with the repoint in the
    triage write (L2.8): it was rolled back with the triage, and the second alert was hidden."""
    from services.api.alerts import AlertTriageConflict

    case = f"case-{new_id()}"
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        first, second, link = await _two_alerts_on_one_secret_match(stores, graph, case)

        async def taken(alert_id: str, *_: Any, **__: Any) -> Alert:
            raise AlertTriageConflict(alert_id)

        monkeypatch.setattr(stores["alerts"], "set_queue_triage", taken)
        with pytest.raises(AlertTriageConflict):
            await alert_queue.dispose(stores["alerts"], graph, analytics, case, first.id, SECRET_LOADER,
                                      disposition="true_positive", reason="matches")  # fmt: skip
        monkeypatch.undo()
        queued = {q.alert.id: q.alert for q in await alert_queue.queue(stores["alerts"], graph, analytics,
                                                                         case, SECRET_LOADER)}  # fmt: skip
        assert second.id in queued and queued[second.id].edge_ids != [link]
        assert first.id in queued and queued[first.id].edge_ids == queued[second.id].edge_ids


async def test_a_stale_record_is_dropped_if_its_link_is_live_and_applied_if_superseded(
    stores: dict[str, Any], analytics: AnalyticsPort
) -> None:
    """The settle's threshold, `STALE_REPOINT_AFTER` (an hour): a record older than it has lost its
    writer. One whose old link is still live is dropped (its write never happened) and changes
    nothing; one whose old link the graph superseded is applied. A fresh record whose old link is
    live is left alone, since its writer may still be running."""
    from datetime import UTC, datetime

    from services.api.alerts import STALE_REPOINT_AFTER

    from conduit_common.identity import new_edge_id
    from schemas.domain import EdgeWrite

    case = f"case-{new_id()}"
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        first, second, link = await _two_alerts_on_one_secret_match(stores, graph, case)
        (old,) = await graph.get_edges([link], SECRET_LOADER)
        tx = await graph.begin_transaction()
        superseding = old.model_dump(include={"type", "source", "target", "properties", "basis",
                                              "provenance", "handling"})  # fmt: skip
        moved = await graph.supersede_edge(link, EdgeWrite(id=new_edge_id(), created_by="t", created_at=T0,
                                                           **superseding), tx)  # fmt: skip
        await graph.commit_transaction(tx)
        (live_link,) = [e for e in await graph.edges_among(first.referent_node_ids, SECRET_LOADER)
                        if e.id == moved]  # fmt: skip
        long_ago = datetime.now(UTC) - STALE_REPOINT_AFTER * 2
        planted = [await _plant_record(stores, {link: moved}, recorded_at=long_ago),
                   await _plant_record(stores, {live_link.id: f"never-{new_id()}"}, recorded_at=long_ago),
                   await _plant_record(stores, {live_link.id: f"fresh-{new_id()}"})]  # fmt: skip
        try:
            await stores["alerts"].settle_pending(graph)
            async with stores["alerts"]._pool.acquire() as conn:
                left = {r["id"] for r in await conn.fetch(
                    "SELECT id FROM alert_repoint_records WHERE id = ANY($1::text[])", planted)}  # fmt: skip
            assert left == {planted[2]}, "the applied and the stale-and-live are gone; the fresh one waits"
            cited = {a.id: a.edge_ids for a in await stores["alerts"].list_case_queue(case, SECRET_LOADER)}
            assert cited[first.id] == cited[second.id] == [moved]
        finally:  # this test's own records, whatever happened: the table is shared
            async with stores["alerts"]._pool.acquire() as conn:
                await conn.execute("DELETE FROM alert_repoint_records WHERE id = ANY($1::text[])", planted)


# ---- L2.8b item 1: the rule audit ---------------------------------------------------------------


async def test_a_firing_over_a_hidden_link_or_transaction_is_withheld_from_the_rule_audit(
    stores: dict[str, Any], analytics: AnalyticsPort
) -> None:
    """The loader's SECRET structuring between two OFFICIAL accounts: its `rule_fired` entry names
    the two accounts (both readable to the OFFICIAL teammate) and, since L2.8b, the SECRET link and
    transactions it cites. The teammate is given neither the entry nor its words, and the total
    does not count it; the SECRET loader reads it. Red with the audit checking nodes alone: the
    teammate read the entry, words included."""
    from services.api.rule_holds import readable_rule_audit

    case = f"case-{new_id()}"
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        alert, _ = await _hidden_world(stores, graph, analytics, case, "RA")

        async def fired(reader: Principal) -> list[Any]:
            page = await readable_rule_audit(stores["audit"], graph, case, reader, analytics=analytics, alerts=stores["alerts"])
            return [e for e in page.entries if e.action == "rule_fired"]

        (entry,) = await fired(SECRET_LOADER)
        assert entry.detail["alert_id"] == alert.id and entry.detail["edge_ids"] == alert.edge_ids
        assert sorted(entry.detail["event_ids"]) == sorted(alert.event_ids)
        assert await fired(TEAMMATE) == []
        teammate = await readable_rule_audit(stores["audit"], graph, case, TEAMMATE, analytics=analytics, alerts=stores["alerts"])
        cleared = await readable_rule_audit(stores["audit"], graph, case, SECRET_LOADER, analytics=analytics, alerts=stores["alerts"])
        assert teammate.total < cleared.total
        assert all(e.detail.get("alert_id") != alert.id for e in teammate.entries)


async def test_a_firing_recorded_before_its_links_were_keeps_its_entry_without_its_words(
    stores: dict[str, Any], analytics: AnalyticsPort
) -> None:
    """An entry as `RuleGate._raise_row` wrote it before L2.8b (rule, alert, trigger, words, nodes;
    no links or transactions): whether the reader may see what its alert cites cannot be known, so
    the entry is kept and its words withheld, from every reader (fail closed). Red with the words
    shown."""
    from services.api.rule_holds import readable_rule_audit

    case = f"case-{new_id()}"
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        loaded, _ = await _hidden_world(stores, graph, analytics, case, "OS")
        gate = _gate(stores, graph, analytics, [], case, loader=SECRET_LOADER)
        await gate._audit("rule_fired", {"rule_id": loaded.rule_id, "alert_id": loaded.id,
                                         "trigger": "pre_commit", "words": loaded.words,
                                         "node_ids": list(loaded.referent_node_ids)}, 1)  # fmt: skip
        # Checked by what its alert cites now (L2.8b's B7): the SECRET loader keeps the entry, its
        # words withheld; the OFFICIAL teammate, who may not see that alert, is not given it.
        page = await readable_rule_audit(stores["audit"], graph, case, SECRET_LOADER, analytics=analytics,
                                         alerts=stores["alerts"])  # fmt: skip
        old = [e for e in page.entries if e.action == "rule_fired" and "edge_ids" not in e.detail]
        assert len(old) == 1
        assert "words" not in old[0].detail and old[0].detail["alert_id"] == loaded.id
        teammate = await readable_rule_audit(stores["audit"], graph, case, TEAMMATE, analytics=analytics,
                                             alerts=stores["alerts"])  # fmt: skip
        assert all(e.detail.get("alert_id") != loaded.id for e in teammate.entries)


# ---- L2.8b item 2: held rows' reasons -----------------------------------------------------------


async def test_a_row_held_with_the_findings_words_is_shown_with_the_rules_name_alone(
    stores: dict[str, Any],
) -> None:
    """A row held before L2.8b carries "it matched: {the finding's words}", which name what the
    rule's deployer read and a reviewer of the row may not. Read through the store as the
    reviewer, it is shown as the rule's name alone (fail closed; L2.8b's Q2), by list and by id;
    a rule the store cannot name is "the rule". Red with the words shown."""
    from tests.ingest.test_typology_rules import _held

    case = f"case-{new_id()}"
    rule = await stores["rules"].create(ANALYST, case, _structuring("pre_commit"))
    words = "it matched: GBSECRETMULE paid GBSECRETHUB 9,500 four times"
    named = _held(case, "OFFICIAL").model_copy(update={"rule_id": rule.id, "reason": words})
    unnamed = _held(case, "OFFICIAL").model_copy(update={"rule_id": f"gone-{new_id()}", "reason": words})
    await stores["held"].hold([named, unnamed])
    shown = {h.id: h.reason for h in await stores["held"].list_authorized(case, ANALYST)}
    assert shown == {named.id: f"it matched “{rule.name}”", unnamed.id: "it matched the rule"}
    one = await stores["held"].get_authorized(named.id, case, ANALYST)
    assert one.reason == f"it matched “{rule.name}”" and "GBSECRET" not in one.reason


# ---- L2.8b item 4: re-marking the Alert nodes written before 7fac778 ---------------------------


async def test_the_re_marking_script_raises_an_old_alert_node_to_its_links_marking(
    stores: dict[str, Any], analytics: AnalyticsPort
) -> None:
    """An alert as the code before `7fac778` left it: its node marked by its two OFFICIAL accounts
    alone, while the alert cites the loader's SECRET link between them, so the OFFICIAL teammate
    reads the node and the finding's words on it. `--dry-run` lists it and changes nothing; the run
    supersedes the node at SECRET and points the alert at the revision, which the teammate cannot
    read; a second run changes nothing. Red with the re-mark not written (the run left as a dry
    run): the teammate still read the node; and with the purge left out, the case's working set
    still held the old node's OFFICIAL copy, served from the store to the teammate."""
    from scripts.remark_alert_nodes import remark

    case = f"case-{new_id()}"
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        loaded, _ = await _hidden_world(stores, graph, analytics, case, "RM")
        rule = await _rule_of(stores, case, loaded)
        gate = _gate(stores, graph, analytics, [], case, loader=SECRET_LOADER)
        old = await gate.raise_committed(
            Finding(rule=rule, deployer=SECRET_LOADER, typology="structuring",
                    subject=loaded.referent_node_ids[0], refs=("finding",), words="Paid across a SECRET link",
                    node_ids=list(loaded.referent_node_ids)))  # fmt: skip
        async with stores["alerts"]._pool.acquire() as conn:  # as the code before 7fac778 left it
            await conn.execute("UPDATE alerts SET edge_ids = $2 WHERE id = $1", old.id,
                               __import__("json").dumps(list(loaded.edge_ids)))  # fmt: skip
        assert old.alert_node_id is not None
        assert await graph.get_node(old.alert_node_id, TEAMMATE) is not None, "the planted gap"

        dry = await remark(graph, stores["alerts"], SCHEME, dry_run=True, investigation_id=case)
        assert old.id in dry.remarked
        assert await graph.get_node(old.alert_node_id, TEAMMATE) is not None, "a dry run writes nothing"

        # A case's working set holds a copy of the old node and its ALERTED_ON link, as the canvas
        # left them: the run removes both (`WorkingSetService.remove_reverted`).
        from services.api.working_set.store import ValkeyWorkingSetStore

        working = ValkeyWorkingSetStore(stores["valkey"])
        old_node = await graph.get_node(old.alert_node_id, SECRET_LOADER)
        alerted = [e for e in await graph.edges_among([old.alert_node_id, *old.referent_node_ids], SECRET_LOADER)
                   if e.type == "ALERTED_ON"]  # fmt: skip
        await working.add_nodes(case, [old_node, *await graph.get_nodes(old.referent_node_ids, SECRET_LOADER)])  # type: ignore[list-item]
        await working.add_edges(case, alerted)
        await stores["valkey"].xadd(f"ws:{case}:deltas", {"d": "a delta naming the old node"})
        from services.api.working_set.service import WorkingSetService

        done = await remark(graph, stores["alerts"], SCHEME, dry_run=False, investigation_id=case,
                            working_set=WorkingSetService(graph, working, SCHEME))  # fmt: skip
        assert old.alert_node_id not in await working.node_ids(case)
        assert not ({e.id for e in alerted} & await working.edge_ids(case))
        assert done.cases_purged >= 1
        assert old.id in done.remarked
        (row,) = [a for a in await stores["alerts"].with_alert_nodes(investigation_id=case) if a.id == old.id]
        assert row.alert_node_id != old.alert_node_id
        assert await graph.get_node(row.alert_node_id, TEAMMATE) is None
        assert await graph.get_node(old.alert_node_id, TEAMMATE) is None, "the old revision is superseded"
        revision = await graph.get_node(row.alert_node_id, SECRET_LOADER)  # type: ignore[arg-type]
        assert revision is not None and revision.handling.classification == "SECRET"

        again = await remark(graph, stores["alerts"], SCHEME, dry_run=False, investigation_id=case)
        assert again.remarked == []


# ---- L2.8b item 8: G2's hidden-link row through a real path ------------------------------------


async def test_an_alert_whose_link_an_analyst_re_marks_above_the_reader_is_withheld_whole(
    stores: dict[str, Any], analytics: AnalyticsPort
) -> None:
    """G2's hidden-link row through the real paths, replacing the hand-planted one: an OFFICIAL load
    raises the alert (its node, accounts, link and transactions all OFFICIAL); an analyst cleared
    for SECRET then raises the link's handling to SECRET through the link change route's service
    (ADR-102), which since L2.8b repoints the alert to the successor (ADR-109 Amendment 10). The
    OFFICIAL teammate, who may still read both accounts and every transaction, is told nothing of
    the alert, and its explanation is refused as a missing id. Red with the queue checking nodes
    alone: the teammate was listed it, and could open it."""
    from services.api.link_changes import LinkChangeRequest, LinkChangeService
    from services.api.working_set.service import WorkingSetService

    from tests.services.api.test_link_changes import InMemoryChanges, MovedNotes
    from tests.services.api.working_set.fakes import FakeWorkingSetStore

    case = f"case-{new_id()}"
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        await _raised(stores, graph, analytics, case, "LC")
        (alert,) = await _case_alerts(stores, ANALYST, case)
        assert await _listed(stores, graph, analytics, case, TEAMMATE) == [alert.id]
        (link,) = await graph.get_edges(alert.edge_ids, ANALYST)
        working = FakeWorkingSetStore()
        await working.add_nodes(case, await graph.get_nodes(alert.referent_node_ids, ANALYST))
        await working.add_edges(case, [link])
        # The case has the alert's node on its canvas, at its OFFICIAL marking.
        await working.add_nodes(case, [await graph.get_node(alert.alert_node_id, ANALYST)])  # type: ignore[arg-type, list-item]
        service = LinkChangeService(InMemoryChanges(), WorkingSetService(graph, working, SCHEME), graph,
                                    ONTOLOGY, MovedNotes(), scheme=SCHEME, alerts=stores["alerts"])  # fmt: skip
        secret = link.handling.model_copy(update={"classification": "SECRET"})
        changed = await service.change(case, link.id, SECRET_LOADER,
                                       LinkChangeRequest(reason="the call is SECRET", handling=secret))  # fmt: skip
        (row,) = [a for a in await stores["alerts"].list_case_queue(case, SECRET_LOADER) if a.id == alert.id]
        assert row.edge_ids == [changed.edge.id], "the alert follows its link to the successor"
        assert await _listed(stores, graph, analytics, case, TEAMMATE) == []
        await _refused_as_missing(stores, graph, analytics, case, alert.id, TEAMMATE)
        assert await _listed(stores, graph, analytics, case, SECRET_LOADER) == [alert.id]
        # ADR-109 Amendment 10: the repoint re-marks the alert's node to its new evidence, so the
        # node, and the finding's words on it, are not read, expanded to or listed by the teammate.
        # Red without the re-mark: the node stayed OFFICIAL and the teammate expanded to it.
        assert row.alert_node_id != alert.alert_node_id, "the node was re-marked into a revision"
        for node_id in (alert.alert_node_id, row.alert_node_id):
            assert await graph.get_node(node_id, TEAMMATE) is None  # type: ignore[arg-type]
        around = await graph.expand(_expand(list(alert.referent_node_ids)), TEAMMATE)
        assert [n.id for n in around.nodes if n.type == "Alert"] == []
        listed_nodes = await graph.list_nodes("Alert", TEAMMATE)
        assert {alert.alert_node_id, row.alert_node_id}.isdisjoint(n.id for n in listed_nodes.nodes)
        # And the case's canvas no longer holds the weaker copy, which the store would serve as it
        # is (red without the purge: the OFFICIAL copy was still stored).
        assert alert.alert_node_id not in await working.node_ids(case)
        revision = await graph.get_node(row.alert_node_id, SECRET_LOADER)  # type: ignore[arg-type]
        assert revision is not None and revision.handling.classification == "SECRET"


# ---- this file never assumes it is alone in the store --------------------------------------------


async def test_the_file_finds_its_own_rule_whatever_else_is_active_in_the_store(
    stores: dict[str, Any], analytics: AnalyticsPort
) -> None:
    """Found by the case lane on a shared database: `list_active_for_case` lists every active
    deployment-wide rule with the case's own, so a `(rule,) =` unpack of it failed ("too many values
    to unpack") once another live file had left one. With one planted first, `_rule_of` still finds
    the rule that raised this test's alert, by its id. Red with the unpack by position. The planted
    rule is retired at the end, so this test leaves nothing behind."""
    from schemas.sentences import RuleSentence, SentenceRuleParams

    elsewhere = f"case-{new_id()}"
    sentence = RuleSentence.model_validate({"subject": "Person", "scope": "deployment", "conditions": [
        {"op": "one_of", "property": "listing", "values": ["sanction", "pep"]}]})  # fmt: skip
    planted = await stores["rules"].create(SECRET_LOADER, elsewhere, TypologyRuleInput(
        name="A deployment-wide rule another file left", trigger="post_commit",
        params=SentenceRuleParams(pattern_id=f"pat-{new_id()}", sentence=sentence)))  # fmt: skip
    # A deployment-wide rule waits for a second person (ADR-133 decision 7) before it is active.
    planted = await stores["rules"].approve(planted.id, elsewhere, ANALYST)
    try:
        case = f"case-{new_id()}"
        async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
            loaded, _ = await _hidden_world(stores, graph, analytics, case, "AL")
            assert len(await stores["rules"].list_active_for_case(case)) >= 2, "the planted rule is listed"
            rule = await _rule_of(stores, case, loaded)
            assert loaded.rule_id == f"typology:{rule.id}" and rule.id != planted.id
    finally:
        await stores["rules"].retire(planted.id, elsewhere, SECRET_LOADER)


# ---- L2.8b item 7: a link an alert cites is repointed when an analyst changes it -----------------


async def test_an_alert_citing_a_changed_link_follows_it_to_its_successor() -> None:
    """(Moved from `test_link_changes.py`, whose other cases need no store.) `link_changes.py`'s supersede: an analyst changes a link an alert cites; the alert cites the
    successor (ADR-109 Amendment 10), against the real alert store (the repoint is its SQL). Red
    with the repoint recording nothing (`repointing_alerts` a no-op): the alert still cited the
    superseded link, which the queue's link check withholds it for."""
    from datetime import UTC, datetime

    from services.api.alerts import AlertStore
    from services.api.config import PostgresConfig
    from services.api.link_changes import LinkChangeRequest, LinkChangeService
    from services.api.working_set.service import WorkingSetService

    from schemas.domain import AlertMode
    from tests.services.api.test_link_changes import ANALYST as CHANGER
    from tests.services.api.test_link_changes import ONTOLOGY as LINK_ONTOLOGY
    from tests.services.api.test_link_changes import _build, _edge
    from tests.services.api.working_set.test_visible_link import SCHEME as LINK_SCHEME

    link_id = f"e-{new_id()}"
    service, graph, store, changes, notes = await _build([_edge(link_id, "a", "b", occurrences=3)])
    alerts = await AlertStore.connect(PostgresConfig.from_env().dsn)
    try:
        service = LinkChangeService(changes, WorkingSetService(graph, store, LINK_SCHEME), graph,
                                    LINK_ONTOLOGY, notes, alerts=alerts)  # fmt: skip
        case = f"case-{new_id()}"
        alert = Alert(id=new_id(), rule_id=f"typology:{new_id()}", owner_id=CHANGER.id, mode=AlertMode.FULL,
                      referent_node_ids=["a", "b"], edge_ids=[link_id], investigation_id=case,
                      created_at=datetime.now(UTC), typology="structuring", words="a paid b")  # fmt: skip
        await alerts.save(alert)
        result = await service.change("inv-1", link_id, CHANGER,
                                      LinkChangeRequest(type="FAMILY_OF", properties={"relation": "cousin"},
                                                        reason="Told so"))  # fmt: skip
        (row,) = [a for a in await alerts.list_case_queue(case, CHANGER) if a.id == alert.id]
        assert row.edge_ids == [result.edge.id] != [link_id]
    finally:
        await alerts.close()



# ---- L2.8b's B2 and B7: audit entries about an alert, by what it cites now ----------------------


async def test_an_entry_saying_an_alerts_node_was_withheld_is_withheld_with_the_alert(
    stores: dict[str, Any], analytics: AnalyticsPort
) -> None:
    """B2: a row raised with no node over a link a revert took back writes `alert_node_withheld`,
    naming its alert and its accounts, which the teammate may read. The queue withholds that alert
    from everyone; so does the audit, checking the entry by what its alert cites. Red with the
    entry checked by the nodes it names: the teammate learnt an alert existed over the accounts."""
    from services.api.rule_holds import readable_rule_audit

    case = f"case-{new_id()}"
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        loaded, _ = await _hidden_world(stores, graph, analytics, case, "WH")
        around = await graph.expand(_expand(list(loaded.referent_node_ids)), TEAMMATE)
        quiet = next(e for e in around.edges if e.type == "TRANSACTED")
        tx = await graph.begin_transaction()
        await graph.revert_elements([], [quiet.id], tx)
        await graph.commit_transaction(tx)
        rule = await stores["rules"].create(ANALYST, case, _structuring("post_commit"))
        raised = await _gate(stores, graph, analytics, [], case, loader=ANALYST).raise_committed(
            Finding(rule=rule, deployer=ANALYST, typology="structuring", subject=quiet.source,
                    refs=("finding",), words="A quiet payment", node_ids=[quiet.source, quiet.target],
                    edge_ids=[quiet.id]))  # fmt: skip
        assert raised.alert_node_id is None
        page = await readable_rule_audit(stores["audit"], graph, case, TEAMMATE, analytics=analytics,
                                         alerts=stores["alerts"])  # fmt: skip
        assert all(e.detail.get("alert_id") != raised.id for e in page.entries)


async def test_a_firing_stays_in_the_audit_when_its_alert_follows_a_link_to_its_successor(
    stores: dict[str, Any], analytics: AnalyticsPort
) -> None:
    """B7: an analyst changes the link an OFFICIAL alert cites (its details, not its marking): the
    alert follows the successor (ADR-109 Amendment 10), and its firing stays in the audit, read by
    what the alert cites now. Red with the entry checked by the link it named when raised: the
    firing vanished for every reader, and from the total."""
    from services.api.link_changes import LinkChangeRequest, LinkChangeService
    from services.api.rule_holds import readable_rule_audit
    from services.api.working_set.service import WorkingSetService

    from tests.services.api.test_link_changes import InMemoryChanges, MovedNotes
    from tests.services.api.working_set.fakes import FakeWorkingSetStore

    case = f"case-{new_id()}"
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        await _raised(stores, graph, analytics, case, "FS")
        (alert,) = await _case_alerts(stores, ANALYST, case)
        (link,) = await graph.get_edges(alert.edge_ids, ANALYST)
        working = FakeWorkingSetStore()
        await working.add_nodes(case, await graph.get_nodes(alert.referent_node_ids, ANALYST))
        await working.add_edges(case, [link])
        service = LinkChangeService(InMemoryChanges(), WorkingSetService(graph, working, SCHEME), graph,
                                    ONTOLOGY, MovedNotes(), scheme=SCHEME, alerts=stores["alerts"])  # fmt: skip
        await service.change(case, link.id, ANALYST,
                             LinkChangeRequest(reason="the amount was wrong", properties={**link.properties,
                                                                                          "amount": 9_600.0}))  # fmt: skip
        page = await readable_rule_audit(stores["audit"], graph, case, ANALYST, analytics=analytics,
                                         alerts=stores["alerts"])  # fmt: skip
        assert [e.detail["alert_id"] for e in page.entries if e.action == "rule_fired"] == [alert.id]


async def test_an_evaluations_count_is_withheld_from_a_reader_who_cannot_see_every_finding(
    stores: dict[str, Any], analytics: AnalyticsPort
) -> None:
    """B2's count: the SECRET rule's evaluation counted one finding, which the OFFICIAL teammate may
    not see. The teammate is given the evaluation without its count; the SECRET loader, who sees
    every finding, keeps the figure. Red with the count served to both."""
    from services.api.rule_holds import readable_rule_audit

    case = f"case-{new_id()}"
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        loaded, _ = await _hidden_world(stores, graph, analytics, case, "CT")
        rule_id = loaded.rule_id.removeprefix("typology:")

        async def evaluated(reader: Principal) -> list[Any]:
            page = await readable_rule_audit(stores["audit"], graph, case, reader, analytics=analytics,
                                             alerts=stores["alerts"])  # fmt: skip
            return [e for e in page.entries if e.action == "rule_evaluated" and e.detail.get("rule_id") == rule_id]

        (cleared,) = await evaluated(SECRET_LOADER)
        assert cleared.detail["findings"] == 1 and cleared.result_cardinality == 1
        given = await evaluated(TEAMMATE)
        assert given, "the teammate is given the evaluation, only not its count"
        for entry in given:
            assert "findings" not in entry.detail and entry.detail["findings_withheld"] is True
            assert entry.result_cardinality == 0


# ---- L2.8b round 2: the journal redesign (B3–B6, R2) --------------------------------------------


async def _changing_world(stores: dict[str, Any], graph: Any, analytics: AnalyticsPort, case: str,
                          tag: str) -> tuple[Alert, Any, Any, Any]:  # fmt: skip
    """An OFFICIAL alert over a loader-written link, and a link-change service over the real graph and
    alert store, with the case's working set holding the accounts, the link and the alert's node."""
    from services.api.link_changes import LinkChangeService
    from services.api.working_set.service import WorkingSetService

    from tests.services.api.test_link_changes import InMemoryChanges, MovedNotes
    from tests.services.api.working_set.fakes import FakeWorkingSetStore

    await _raised(stores, graph, analytics, case, tag)
    (alert,) = await _case_alerts(stores, ANALYST, case)
    (link,) = await graph.get_edges(alert.edge_ids, ANALYST)
    working = FakeWorkingSetStore()
    await working.add_nodes(case, await graph.get_nodes(alert.referent_node_ids, ANALYST))
    await working.add_edges(case, [link])
    await working.add_nodes(case, [await graph.get_node(alert.alert_node_id, ANALYST)])  # type: ignore[arg-type, list-item]
    service = LinkChangeService(InMemoryChanges(), WorkingSetService(graph, working, SCHEME), graph, ONTOLOGY,
                                MovedNotes(), scheme=SCHEME, alerts=stores["alerts"])  # fmt: skip
    return alert, link, service, working


def _detail_change(link: Any, amount: float) -> Any:
    from services.api.link_changes import LinkChangeRequest

    return LinkChangeRequest(reason="the amount was wrong", properties={**link.properties, "amount": amount})


@pytest.mark.parametrize("interruption", ["timeout", "cancellation"])
async def test_a_commit_that_lands_after_the_writer_failed_is_still_repointed(
    stores: dict[str, Any], analytics: AnalyticsPort, monkeypatch: pytest.MonkeyPatch, interruption: str
) -> None:
    """B3: the graph's commit is reported failed (a timeout; or the request cancelled) and lands
    afterwards. The writer never drops its record, so the next read finds the link superseded and
    repoints the alert. A cancellation stays a cancellation. Red with the record dropped on the
    writer's failure path (it read the link still live and dropped it): the alert stayed on the
    superseded link, hidden from every reader."""
    import asyncio

    case = f"case-{new_id()}"
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        alert, link, service, _ = await _changing_world(stores, graph, analytics, case, "AM")
        real_commit = graph.commit_transaction
        held: list[Any] = []
        raised: type[BaseException] = TimeoutError if interruption == "timeout" else asyncio.CancelledError

        async def reported_failed(tx: Any) -> None:
            held.append(tx)
            raise raised("the commit's answer never came")

        monkeypatch.setattr(graph, "commit_transaction", reported_failed)
        with pytest.raises(raised):
            await service.change(case, link.id, ANALYST, _detail_change(link, 9_700.0))
        monkeypatch.undo()
        await real_commit(held[0])  # it lands
        listed = {q.alert.id: q.alert for q in await alert_queue.queue(stores["alerts"], graph, analytics,
                                                                         case, ANALYST)}  # fmt: skip
        assert alert.id in listed and listed[alert.id].edge_ids != [link.id]


async def test_a_chain_of_writes_brings_the_alert_to_the_newest_revision(
    stores: dict[str, Any], analytics: AnalyticsPort, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B4: a first change's graph commit lands and its repoint fails; a second change then supersedes
    the first's revision and applies (moving nothing: the alert still cites the original). The next
    read follows the recorded successors to the newest revision. Red with one-level renames and no
    kept successors: the alert was moved onto the first revision, itself superseded, and hidden."""
    case = f"case-{new_id()}"
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        alert, link, service, working = await _changing_world(stores, graph, analytics, case, "CH")
        real_apply = stores["alerts"].apply_repoints

        async def fails(finals: Any) -> list[str]:
            raise ConnectionError("Postgres went away after the graph's commit")

        monkeypatch.setattr(stores["alerts"], "apply_repoints", fails)
        with pytest.raises(ConnectionError):
            await service.change(case, link.id, ANALYST, _detail_change(link, 9_700.0))
        monkeypatch.setattr(stores["alerts"], "apply_repoints", real_apply)
        (first,) = [e for e in await graph.edges_among(alert.referent_node_ids, ANALYST) if e.type == "TRANSACTED"
                    and e.id != link.id]  # fmt: skip
        await working.add_edges(case, [first])  # as the case's next read of it would hold it
        second = await service.change(case, first.id, ANALYST, _detail_change(first, 9_800.0))
        listed = {q.alert.id: q.alert for q in await alert_queue.queue(stores["alerts"], graph, analytics,
                                                                         case, ANALYST)}  # fmt: skip
        assert alert.id in listed and listed[alert.id].edge_ids == [second.edge.id]


async def test_a_re_mark_that_fails_is_retried_by_the_next_read(
    stores: dict[str, Any], analytics: AnalyticsPort, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B5: an analyst raises the cited link to SECRET; the repoint applies and the re-mark commits
    the node's SECRET revision in the graph, and then pointing the alert at it fails. The re-mark was
    recorded before its commit, so the next read renames the alert's node to the revision the graph
    holds, which the OFFICIAL teammate cannot read. Red with the re-mark unrecorded (no
    `on_supersede`): the alert named the superseded OFFICIAL node, gone from every read."""
    from services.api.link_changes import LinkChangeRequest

    case = f"case-{new_id()}"
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        alert, link, service, _ = await _changing_world(stores, graph, analytics, case, "RT")
        real = stores["alerts"].set_alert_node

        async def fails_once(*args: Any, **kwargs: Any) -> bool:
            monkeypatch.setattr(stores["alerts"], "set_alert_node", real)
            raise ConnectionError("Postgres went away after the re-mark's graph commit")

        monkeypatch.setattr(stores["alerts"], "set_alert_node", fails_once)
        secret = link.handling.model_copy(update={"classification": "SECRET"})
        with pytest.raises(ConnectionError):
            await service.change(case, link.id, SECRET_LOADER, LinkChangeRequest(reason="SECRET", handling=secret))
        await alert_queue.queue(stores["alerts"], graph, analytics, case, SECRET_LOADER)  # a read settles
        (row,) = [a for a in await stores["alerts"].list_case_queue(case, SECRET_LOADER) if a.id == alert.id]
        assert row.alert_node_id != alert.alert_node_id
        revision = await graph.get_node(row.alert_node_id, SECRET_LOADER)  # type: ignore[arg-type]
        assert revision is not None and revision.handling.classification == "SECRET"
        assert await graph.get_node(row.alert_node_id, TEAMMATE) is None  # type: ignore[arg-type]


async def test_a_node_a_settle_re_marked_leaves_the_working_sets_at_their_next_read(
    stores: dict[str, Any], analytics: AnalyticsPort, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R2: the re-mark ran on a read path's settle (the link change's own repoint failed), which holds
    no working sets; the node's OFFICIAL copy stays in the case's working set until the next
    working-set read, which purges it (`purge_remarked_copies`) and closes the record. Red with the
    purge left out: the copy was still stored, served to the teammate."""
    from services.api.alerts import purge_remarked_copies
    from services.api.link_changes import LinkChangeRequest
    from services.api.working_set.service import WorkingSetService

    case = f"case-{new_id()}"
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        alert, link, service, working = await _changing_world(stores, graph, analytics, case, "PG")
        real_apply = stores["alerts"].apply_repoints

        async def fails_once(finals: Any) -> list[str]:
            monkeypatch.setattr(stores["alerts"], "apply_repoints", real_apply)
            raise ConnectionError("Postgres went away after the graph's commit")

        monkeypatch.setattr(stores["alerts"], "apply_repoints", fails_once)
        secret = link.handling.model_copy(update={"classification": "SECRET"})
        with pytest.raises(ConnectionError):
            await service.change(case, link.id, SECRET_LOADER, LinkChangeRequest(reason="SECRET", handling=secret))
        await alert_queue.queue(stores["alerts"], graph, analytics, case, SECRET_LOADER)  # settled, re-marked
        assert alert.alert_node_id in await working.node_ids(case), "the read path cannot purge"
        await purge_remarked_copies(stores["alerts"], WorkingSetService(graph, working, SCHEME))
        assert alert.alert_node_id not in await working.node_ids(case)


async def test_a_record_another_test_left_never_breaks_an_unrelated_read(
    stores: dict[str, Any], analytics: AnalyticsPort
) -> None:
    """The journal lives in a shared store: a record another test or run left (its links in no
    graph this read reaches) waits for the stale threshold and never breaks a read. An unrelated
    queue read answers as ever, with the real graph and with one whose stored-state lookup refuses
    outright (the settle logs it and leaves the record). Red with the settle letting a record's
    failure through: the read failed."""
    left = await _plant_record(stores, {f"gone-{new_id()}": f"gone-{new_id()}-new"})
    try:
        case = f"case-{new_id()}"
        async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
            await _raised(stores, graph, analytics, case, "LO")
            (alert,) = await _case_alerts(stores, ANALYST, case)
            assert await _listed(stores, graph, analytics, case, TEAMMATE) == [alert.id]

            class Refusing:
                """The graph, but its stored-state lookup refuses (an outage of that one read)."""

                def __getattr__(self, name: str) -> Any:
                    return getattr(graph, name)

                async def stored_link_states(self, edge_ids: Any) -> Any:
                    raise ConnectionError("the stored-state lookup is unavailable")

            assert await _listed(stores, Refusing(), analytics, case, TEAMMATE) == [alert.id]
        async with stores["alerts"]._pool.acquire() as conn:
            kept = await conn.fetchval("SELECT count(*) FROM alert_repoint_records WHERE id = $1", left)
        assert kept == 1, "the leftover waits for the stale threshold, neither applied nor dropped"
    finally:
        async with stores["alerts"]._pool.acquire() as conn:
            await conn.execute("DELETE FROM alert_repoint_records WHERE id = $1", left)


async def test_a_close_never_puts_back_the_node_its_own_record_re_marked(
    stores: dict[str, Any], analytics: AnalyticsPort
) -> None:
    """Round 3, item 1: an alert whose link sits above its node (a link superseded outside the
    journal, as L2.8c's paths still leave it) is closed a true positive. The close confirms the node
    (N to C) in its record, the record's re-mark raises C to the link's marking (C to R) and points
    the alert at R; the triage write then names no node, so the alert stays on R. Red with the
    triage writing the confirmed node back: the alert named C, superseded, hidden from every read."""
    from conduit_common.identity import new_edge_id
    from schemas.domain import EdgeWrite

    case = f"case-{new_id()}"
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        await _raised(stores, graph, analytics, case, "PB")
        (alert,) = await _case_alerts(stores, ANALYST, case)
        (link,) = await graph.get_edges(alert.edge_ids, ANALYST)
        secret = link.handling.model_copy(update={"classification": "SECRET"})
        tx = await graph.begin_transaction()
        raised = await graph.supersede_edge(link.id, EdgeWrite(
            id=new_edge_id(), type=link.type, source=link.source, target=link.target, properties=link.properties,
            interval=link.interval, occurrences=link.occurrences, provenance=link.provenance, handling=secret,
            created_by="t", created_at=T0), tx)  # fmt: skip
        await graph.commit_transaction(tx)
        await stores["alerts"].apply_repoints({link.id: raised})  # cited, its node not re-marked
        closed = await alert_queue.dispose(stores["alerts"], graph, analytics, case, alert.id, SECRET_LOADER,
                                           disposition="true_positive", reason="confirmed")  # fmt: skip
        assert closed.status == "closed"
        (row,) = [a for a in await stores["alerts"].list_case_queue(case, SECRET_LOADER) if a.id == alert.id]
        node = await graph.get_node(row.alert_node_id, SECRET_LOADER)  # type: ignore[arg-type]
        assert node is not None, "the alert names a live node"
        assert node.handling.classification == "SECRET"


async def _link_above_node(stores: dict[str, Any], graph: Any, analytics: AnalyticsPort, case: str,
                           tag: str) -> tuple[Alert, str, str]:  # fmt: skip
    """An OFFICIAL alert whose cited link is then superseded at SECRET outside the journal (as
    L2.8c's paths still do): the alert cites the SECRET revision, its node still OFFICIAL. Returns
    the alert, the old link and the SECRET revision."""
    from conduit_common.identity import new_edge_id
    from schemas.domain import EdgeWrite

    await _raised(stores, graph, analytics, case, tag)
    (alert,) = await _case_alerts(stores, ANALYST, case)
    (link,) = await graph.get_edges(alert.edge_ids, ANALYST)
    tx = await graph.begin_transaction()
    raised = await graph.supersede_edge(link.id, EdgeWrite(
        id=new_edge_id(), type=link.type, source=link.source, target=link.target, properties=link.properties,
        interval=link.interval, occurrences=link.occurrences, provenance=link.provenance,
        handling=link.handling.model_copy(update={"classification": "SECRET"}), created_by="t",
        created_at=T0), tx)  # fmt: skip
    await graph.commit_transaction(tx)
    return alert, link.id, raised


async def _live_alert_nodes(graph: Any, alert_id: str, rule_id: str) -> list[str]:
    listed: list[str] = []
    cursor = None
    while True:
        page = await graph.list_nodes("Alert", SECRET_LOADER, cursor=cursor)
        listed.extend(n.id for n in page.nodes if n.properties.get("rule_id") == rule_id)
        if page.next_cursor is None:
            return listed
        cursor = page.next_cursor


async def test_a_record_follows_its_node_to_the_newest_revision_the_graph_holds(
    stores: dict[str, Any], analytics: AnalyticsPort
) -> None:
    """Round 3, item 2 (the node half of item 4): a record holds an alert's node rename (N to C),
    and C is then superseded to R by a write outside the record (as `retract_node` and
    `supersede_node`'s other callers still do until L2.8c). The next read follows the graph's own
    `superseded_by` from N (`stored_writes`, unfiltered) to R, and the alert names R. Red with the
    recorded successor trusted: the alert named C, superseded, which no read answers."""
    from datetime import UTC, datetime

    from conduit_common.identity import new_node_id
    from schemas.domain import NodeWrite

    case = f"case-{new_id()}"
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        await _raised(stores, graph, analytics, case, "NC")
        (alert,) = await _case_alerts(stores, ANALYST, case)
        assert alert.alert_node_id is not None

        async def superseded(node_id: str) -> str:
            node = await graph.get_node(node_id, SECRET_LOADER)
            assert node is not None
            tx = await graph.begin_transaction()
            new = await graph.supersede_node(node_id, NodeWrite(
                id=new_node_id(), type=node.type, properties=node.properties, provenance=node.provenance,
                handling=node.handling, created_by="t", created_at=datetime.now(UTC),
                datasets=node.datasets), tx)  # fmt: skip
            await graph.commit_transaction(tx)
            return str(new)

        n = alert.alert_node_id
        c = await superseded(n)
        record = await _plant_record(stores, {})
        await stores["alerts"]._add_to_record(record, alert_nodes=[(n, c)])
        r = await superseded(c)  # outside the record
        await alert_queue.queue(stores["alerts"], graph, analytics, case, SECRET_LOADER)  # a read settles
        (row,) = [a for a in await stores["alerts"].list_case_queue(case, SECRET_LOADER) if a.id == alert.id]
        assert row.alert_node_id == r != c


async def test_two_settles_of_one_record_at_once_leave_one_live_alert_node(
    stores: dict[str, Any], analytics: AnalyticsPort
) -> None:
    """Round 3, item 3: two reads settle the same record at once. The record is settled under a lock
    (a settle another holds is skipped), so its re-mark runs once: one live revision of the alert's
    node, the alert naming it. Red with the lock released as soon as it is taken (the settles
    overlapping, neither waiting on the other): both re-marked, two live Alert revisions. A hang
    fails at `SETTLE_TIMEOUT` rather than stalling the run."""
    import asyncio

    case = f"case-{new_id()}"
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        alert, old, raised = await _link_above_node(stores, graph, analytics, case, "LK")
        await _plant_record(stores, {old: raised})
        await asyncio.wait_for(
            asyncio.gather(*(stores["alerts"].settle_pending(graph) for _ in range(4))), SETTLE_TIMEOUT
        )
        await asyncio.wait_for(stores["alerts"].settle_pending(graph), SETTLE_TIMEOUT)
        live = await _live_alert_nodes(graph, alert.id, alert.rule_id.removeprefix("typology:"))
        (row,) = [a for a in await stores["alerts"].list_case_queue(case, SECRET_LOADER) if a.id == alert.id]
        assert live == [row.alert_node_id], f"one live revision, named by the alert: {live}"


async def test_more_records_settled_at_once_than_the_store_holds_connections_all_finish(
    stores: dict[str, Any], analytics: AnalyticsPort
) -> None:
    """Round 3, item 3, found by the hang of its first red: a settle holds its record's lock while
    its steps take connections from the store's pool. Six reads settling six records at once each
    hold a lock and finish, every alert moved to its link's newest revision, within
    `SETTLE_TIMEOUT`. Red with the locks drawn from the store's own pool (four connections): four
    settles each held one for a lock and waited for another, for ever, so the run timed out."""
    import asyncio

    cases = [f"case-{new_id()}" for _ in range(6)]
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        moved = [await _link_above_node(stores, graph, analytics, case, f"MR{i}") for i, case in enumerate(cases)]
        for _, old, raised in moved:
            await _plant_record(stores, {old: raised})
        await asyncio.wait_for(
            asyncio.gather(*(stores["alerts"].settle_pending(graph) for _ in range(6))), SETTLE_TIMEOUT
        )
        for case, (alert, _, raised) in zip(cases, moved, strict=True):
            (row,) = [a for a in await stores["alerts"].list_case_queue(case, SECRET_LOADER) if a.id == alert.id]
            assert row.edge_ids == [raised]


async def test_a_record_follows_what_the_graph_committed_not_what_it_recorded(
    stores: dict[str, Any], analytics: AnalyticsPort
) -> None:
    """Round 3, item 4: a record names a successor its write never committed (a writer that recorded
    then failed), while the graph holds the link superseded by another write that did. The settle
    follows the graph's own `superseded_by`, so the alert cites the revision the graph holds. Red
    with the recorded successor trusted: the alert cited a link no store holds, hidden from all."""
    case = f"case-{new_id()}"
    async with arcadedb_adapter(ONTOLOGY, SCHEME) as graph:
        alert, old, raised = await _link_above_node(stores, graph, analytics, case, "GT")
        await _plant_record(stores, {old: f"never-committed-{new_id()}"})
        await alert_queue.queue(stores["alerts"], graph, analytics, case, SECRET_LOADER)
        (row,) = [a for a in await stores["alerts"].list_case_queue(case, SECRET_LOADER) if a.id == alert.id]
        assert row.edge_ids == [raised]
