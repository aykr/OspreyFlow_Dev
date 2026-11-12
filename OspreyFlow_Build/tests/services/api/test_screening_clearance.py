"""A screening list screened only by whom its marking clears, in the store's query (`06_DECISIONS.md`
ADR-146 Amendment 7 point 8; the orchestrator's review of 12 November 2026, items 1, 7 and 8; rule 3).

`ScreeningListStore.entries` takes the reader's `ListClearance` and filters in its `WHERE`
(`test_screening_list_store.py` proves the query live). These cases prove every caller passes the
right reader's clearance and nothing else, against a fake store that answers as the query does
(`_Lists`: a list's entries only for a clearance admitting its marking, rule 15's refusal modelled):
the KYC gate's judge and a sentence rule as their deployer, a sentence's preview as the previewer.
A sentence's words name no list; a load's report counts only the alerts its loader may read.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest
from services.api.kyc_rules import KycContext, judge_screening
from services.api.rule_evaluation import Finding, counted_for, handling_readable
from services.api.screening import ListClearance, ScreeningEntry, _lowers

from ontology.handling import load_uk_le_scheme
from schemas.domain import (
    AlertCitation,
    Handling,
    KycScreeningParams,
    NodeWrite,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
    TypologyRule,
)
from schemas.sentences import RuleSentence, SentenceRuleParams

SCHEME = load_uk_le_scheme()
OFFICIAL = Principal(id="official", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
SECRET = Principal(id="secret", clearance="SECRET", org_unit="unit-1", roles=["analyst"])
OPEN = ScreeningEntry(id="Open list:1", list_name="Open list", listing="sanction", entity_type="Person",
                      name="Elena PETROVA")  # fmt: skip
MARKED = ScreeningEntry(id="Marked list:1", list_name="Marked list", listing="sanction", entity_type="Person",
                        name="PETROVA, Elena", classification="SECRET", handling_code="P")  # fmt: skip


class _Lists:
    """`ScreeningListStore.entries` as its query answers: an entry only where `cleared` admits its
    list's marking. Every clearance asked with is kept."""

    def __init__(self, entries: list[ScreeningEntry]) -> None:
        self.held, self.asked = entries, []  # type: ignore[var-annotated]

    async def entries(self, entity_type: str, *, cleared: ListClearance) -> list[ScreeningEntry]:
        self.asked.append(cleared)
        return [e for e in self.held if e.entity_type == entity_type
                and cleared.admits(e.classification, e.handling_code)]  # fmt: skip


def test_a_list_clearance_admits_exactly_what_the_adapters_predicate_admits() -> None:
    """Over every classification and handling code of the scheme, for readers of every clearance,
    with and without a restricted code to receive: `ListClearance.admits` answers as
    `handling_readable` over the list's marking in the reader's own unit (`list_handling`)."""
    codes = list(SCHEME.handling_codes)
    for clearance in SCHEME.classification:
        for receivable in ([], codes):
            reader = Principal(id="r", clearance=clearance, org_unit="unit-1",
                               receivable_handling_codes=receivable)  # fmt: skip
            cleared = ListClearance.of(reader, SCHEME)
            for classification in SCHEME.classification:
                for code in codes:
                    marking = Handling(classification=classification, handling_code=code,
                                       owning_unit="unit-1", originator="unit-1")  # fmt: skip
                    assert cleared.admits(classification, code) == handling_readable(SCHEME, reader, marking), (
                        clearance, receivable, classification, code)  # fmt: skip


class _NoListed:
    async def find_node(self, *_: Any, **__: Any) -> None:
        return None


def _customer() -> NodeWrite:
    return NodeWrite(id="cust", type="Person", properties={"family_name": "Petrova", "given_names": "Elena"},
                     provenance=Provenance(state=ProvenanceState.ASSERTED, sources=[SourceRef(document_id="load", locator="1", excerpt_hash="")],
                                           first_seen=datetime(2026, 11, 12, tzinfo=UTC)),
                     handling=Handling(classification="OFFICIAL", handling_code="P", owning_unit="unit-1",
                                       originator="unit-1"),
                     created_by="loader", created_at=datetime(2026, 11, 12, tzinfo=UTC))  # fmt: skip


@pytest.mark.parametrize(("deployer", "lists"), [(OFFICIAL, ["Open list"]), (SECRET, ["Marked list", "Open list"])])
async def test_the_kyc_gate_screens_only_the_lists_its_deployer_is_cleared_for(
    deployer: Principal, lists: list[str]
) -> None:
    """Point 8, by the store's own query (the review's item 1: the gate filtered after reading every
    list). Red with the gate asking for every list: the OFFICIAL deployer's alert cited the SECRET
    list too."""
    store = _Lists([OPEN, MARKED])
    rule = TypologyRule(id="kyc", investigation_id="case", owner_id=deployer.id, name="Screening",
                        created_at=date(2026, 11, 12), trigger="pre_commit", params=KycScreeningParams())  # type: ignore[arg-type]  # fmt: skip
    ctx = KycContext(graph=_NoListed(), scheme=SCHEME, screening=store, compute=None, today=date(2026, 11, 12))  # type: ignore[arg-type]
    (finding,) = await judge_screening(rule, deployer, [_customer()], ctx)
    assert sorted(c.words.split("(")[1].split(")")[0] for c in finding.citations) == lists
    assert set(store.asked) == {ListClearance.of(deployer, SCHEME)}


SENTENCE = RuleSentence(subject="Person", relationship={"kind": "on_screening_list", "min_score": 0.8})  # type: ignore[arg-type]


async def test_a_sentence_rule_screens_only_the_lists_its_deployer_is_cleared_for() -> None:
    """The review's item 1: a sentence rule read every list, its deployer cleared or not. Red with
    the store asked without the deployer's clearance."""
    from services.api.sentence_rules import _context

    from tests.services.api.test_sentence_rules import _gate, _Graph, _Recorder

    rule = TypologyRule(id="rule-s", investigation_id="case", owner_id=OFFICIAL.id, name="Listed",
                        created_at=date(2026, 11, 12), trigger=SENTENCE.runs,
                        params=SentenceRuleParams(pattern_id="pat-1", sentence=SENTENCE))  # type: ignore[arg-type]  # fmt: skip
    gate = _gate(rule, _Graph([], []), _Recorder(), owner=OFFICIAL.id, author=OFFICIAL)  # type: ignore[call-arg]
    store = _Lists([OPEN, MARKED])
    gate.screening = store  # type: ignore[assignment]
    _, _, ctx = await _context(rule, OFFICIAL, gate)
    assert [e.list_name for e in ctx.screening_entries["Person"]] == ["Open list"]
    assert store.asked == [ListClearance.of(OFFICIAL, SCHEME)]


async def test_a_sentences_preview_screens_only_the_lists_the_previewer_is_cleared_for() -> None:
    """The preview and *Test* (`app._sentence_context`), as the person previewing. Red with the
    store asked for every list: an OFFICIAL previewer's count took in the SECRET list."""
    from services.api.app import _sentence_context

    from tests.services.api.test_rule_sentences import ONTOLOGY, _Graph

    class _Hotlists:
        async def list_authorized(self, principal: Principal) -> list[Any]:
            return []

    store = _Lists([OPEN, MARKED])
    ctx = await _sentence_context(
        SENTENCE, OFFICIAL, "case", graph=_Graph([], []), analytics=None, ontology=ONTOLOGY,  # type: ignore[arg-type]
        hotlists_store=_Hotlists(), screening_lists=store, influencers_store=None, scheme=SCHEME,  # type: ignore[arg-type]
    )  # fmt: skip
    assert [e.list_name for e in ctx.screening_entries["Person"]] == ["Open list"]
    assert store.asked == [ListClearance.of(OFFICIAL, SCHEME)]


async def test_a_sentences_words_name_no_list() -> None:
    """The review's item 1: "… a 0.97 match to an entry on <list>" was the alert's words, read by
    every reader of its subject. A sentence's alert cites no list, so its words name none."""
    from services.api.rule_sentences import SentenceContext, _meets_relationship

    from tests.services.api.test_rule_sentences import ONTOLOGY, _Graph, _node

    ctx = SentenceContext(graph=_Graph([], []), analytics=None, investigation_scope="case",  # type: ignore[arg-type]
                          ontology=ONTOLOGY, screening_entries={"Person": [MARKED]})  # fmt: skip
    node = _node("p-1", "Person", family_name="Petrova", given_names="Elena")
    said = await _meets_relationship(node, SENTENCE, SECRET, ctx)
    assert said is not None and "screening list" in said and "Marked list" not in said


def _finding(*markings: str) -> Finding:
    return Finding(rule=None, deployer=SECRET, typology="kyc_screening", subject="c", refs=(), words="w",  # type: ignore[arg-type]
                   node_ids=[], citations=tuple(AlertCitation(words=m) for m in markings),
                   citation_handlings=tuple(Handling(classification=m, handling_code="P", owning_unit="unit-1",
                                                     originator="unit-1") for m in markings))  # fmt: skip


def test_a_loads_report_counts_only_the_alerts_its_loader_may_read() -> None:
    """The review's item 7: "raised N alert(s)" counted alerts citing only a list the loader may
    not read. An alert is counted for them where they are cleared for at least one of its lists
    (the queue shows it to them then), and one without citations always."""
    assert not counted_for(_finding("SECRET"), OFFICIAL, SCHEME)
    assert counted_for(_finding("OFFICIAL", "SECRET"), OFFICIAL, SCHEME)
    assert counted_for(_finding("SECRET"), SECRET, SCHEME)
    assert counted_for(_finding(), OFFICIAL, SCHEME)


@pytest.mark.parametrize(
    ("kept", "new", "lowers"),
    [
        (("SECRET", "P"), ("OFFICIAL", "P"), True),
        (("SECRET", "P"), ("SECRET", "C"), True),
        (("SECRET", "P"), ("SECRET", "P"), False),
        (("OFFICIAL", "P"), ("SECRET", "P"), False),
    ],
)
def test_a_reload_that_would_lower_a_lists_marking_is_refused(
    kept: tuple[str, str], new: tuple[str, str], lowers: bool
) -> None:
    """The review's item 8 (`replace_list`; live, `test_screening_list_store.py`): below the kept
    marking, or another code at the same classification (a code is not ranked: strict)."""
    if new[1] not in SCHEME.handling_codes:
        pytest.skip(f"{new[1]} is not a code of this scheme")
    assert _lowers(SCHEME, kept, new) is lowers


async def test_a_sentence_alert_resting_on_a_marked_list_is_marked_as_the_list_is() -> None:
    """The lane review of the second pass, defect 6: a sentence's alert cites no list, so it was
    shown to every reader of its subject, and "a 0.97 match to an entry on a screening list" told
    a reader cleared only for OFFICIAL lists that a SECRET one had matched. Its node is now marked at
    least as the list is, so such a reader is shown nothing of it (the queue reads the node). Red
    with the node marked by its subject alone: OFFICIAL."""
    from tests.services.api.test_rule_sentences import _node
    from tests.services.api.test_sentence_rules import _gate, _Recorder, _rule, _write, _WritingGraph

    author = SECRET.model_copy(update={"id": "author", "roles": ["analyst"]})
    graph = _WritingGraph([_node("p1", "Person", family_name="Petrova", given_names="Elena")])
    recorder = _Recorder()
    gate = _gate(_rule(SENTENCE), graph, recorder, author=author)
    gate.screening = _Lists([MARKED])  # type: ignore[assignment]
    await gate.post_commit([], load_id="load-1", written=[_write("p1", family_name="Petrova", given_names="Elena")])
    (alert,) = recorder.alerts
    (node,) = [w for w in graph.written if getattr(w, "type", None) == "Alert"]
    assert node.handling.classification == "SECRET" and "Marked list" not in (alert.words or "")
