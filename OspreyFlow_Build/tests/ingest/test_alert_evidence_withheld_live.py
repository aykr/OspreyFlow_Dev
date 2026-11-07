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
from schemas.domain import Alert, Principal
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
    _row,
    _structuring,
    arcadedb_adapter,
)

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


async def _rule_of(stores: dict[str, Any], case: str) -> Any:
    """The one rule `_hidden_world` deployed in the case."""
    (rule,) = await stores["rules"].list_active_for_case(case)
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
        rule = await _rule_of(stores, case)

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
        rule = await _rule_of(stores, case)
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
        rule = await _rule_of(stores, case)
        gate: RuleGate = _gate(stores, graph, analytics, [], case, loader=SECRET_LOADER)
        finding = Finding(rule=rule, deployer=SECRET_LOADER, typology="structuring",
                          subject=loaded.referent_node_ids[0], refs=("finding",), words="In the load",
                          node_ids=list(loaded.referent_node_ids), edge_ids=list(loaded.edge_ids))  # fmt: skip
        tx = await graph.begin_transaction()
        node_id, why = await gate._alert_node_in_load(finding, tx, unseen=None, load_id=new_id(),
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
