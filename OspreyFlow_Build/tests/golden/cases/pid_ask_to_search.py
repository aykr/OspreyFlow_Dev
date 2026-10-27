"""Ask to search over the Prison Intelligence Demonstrator's vocabulary: Brief 3 item E3's twenty
questions (`06_DECISIONS.md` ADR-129 decision 2), each with the pattern a person would draw, or
none where the Conduit must refuse.

Sixteen are answerable and four are refused: question 6 needs a range and two properties that are
not indexed (below), 18 asks who is guilty, 19 asks for a prediction, and 20 asks for an absence
("a phone I have not seen"), which the query builder cannot draw (a condition is equality on one
value, ADR-121; there is no negation). Every expected pattern
is written against the deployment ontology (`ontology.packs.load_deployment_ontology`: the core
with the shipped packs), and `tests/test_ask_to_search_golden_gate.py` runs each one through the
Conduit's own validator, so an expected pattern the ontology would refuse fails there, not in a
model's score. `$selected_1` stands for what the analyst has selected (the principal, the
coordinator's number), as the route resolves it.

**How the PID is drawn here.** A prisoner's PIN account, a phone number and a bank or private-cash
account are `Endpoint`s of a kind (`endpoint_kind`: `handle`, `msisdn`, `account`), and the person
`USES` them; money moves `TRANSACTED` between two. `endpoint_kind` is an enum that is not indexed,
so a condition cannot name it, and the kind a question speaks of ("PIN account", "number") is left
to the link and the pinned node. A wing, a cell and a yard are `Location`s whose `name` is indexed,
so "Wing F" is a condition on it.

**Question 6 is a refusal (ADR-129 Amendment 2).** "Found with a mobile phone since 1 January"
needs `Incident.category = find`, `Incident.item = mobile phone` and a date from 1 January.
`category` and `item` are not indexed, so `check_pattern_conditions` refuses a condition on either
(`not_indexed`), and a date from is a range, which ADR-129 refuses. A narrowed pattern would
widen the match silently, so the Conduit must refuse it.
"""

from __future__ import annotations

from schemas.domain import PatternEdge, PatternNode, PatternQuery
from tests.golden.harness import PatternGoldenCase

#: The id `baseline.json` records the ask-to-search measurement under.
CASE_ID = "pid-ask-to-search"

SELECTED = "$selected_1"


def _node(
    var: str, entity_type: str, *, pinned: str | None = None, where: dict[str, str] | None = None
) -> PatternNode:
    return PatternNode(var=var, entity_type=entity_type, node_id=pinned, where=where or {})


def _link(edge_type: str, source: str, target: str) -> PatternEdge:
    return PatternEdge(edge_type=edge_type, from_var=source, to_var=target)


def _pattern(nodes: list[PatternNode], edges: list[PatternEdge]) -> PatternQuery:
    return PatternQuery(nodes=nodes, edges=edges)


def _case(
    number: int, question: str, expected: PatternQuery | None, selected: int = 0
) -> PatternGoldenCase:
    return PatternGoldenCase(
        id=f"{CASE_ID}-q{number:02d}", question=question, expected=expected, selected=selected
    )


#: The principal's own person node, pinned, in the patterns that start from them.
_PRINCIPAL = _node("s", "Person", pinned=SELECTED)

PID_ASK_TO_SEARCH_CASES: tuple[PatternGoldenCase, ...] = (
    _case(
        1,
        "Who shares a visitor with the principal?",
        _pattern(
            [_node("a", "Person"), _PRINCIPAL, _node("b", "Person")],
            [_link("VISITED", "a", "s"), _link("VISITED", "a", "b")],
        ),
        selected=1,
    ),
    _case(
        2,
        "Which prisoners are paid from the same account as the principal?",
        _pattern(
            [
                _PRINCIPAL,
                _node("a", "Endpoint"),
                _node("x", "Endpoint"),
                _node("b", "Endpoint"),
                _node("p", "Person"),
            ],
            [
                _link("USES", "s", "a"),
                _link("TRANSACTED", "x", "a"),
                _link("TRANSACTED", "x", "b"),
                _link("USES", "p", "b"),
            ],
        ),
        selected=1,
    ),
    _case(
        3,
        "Which outside numbers are called by more than one prisoner's PIN account?",
        _pattern(
            [_node("a", "Endpoint"), _node("b", "Endpoint"), _node("n", "Endpoint")],
            [_link("COMMUNICATED_WITH", "a", "n"), _link("COMMUNICATED_WITH", "b", "n")],
        ),
    ),
    _case(
        4,
        "Who has shared a cell with the principal?",
        _pattern([_node("p", "Person"), _PRINCIPAL], [_link("SHARED_CELL_WITH", "p", "s")]),
        selected=1,
    ),
    _case(
        5,
        "Who is in the same group as the principal?",
        _pattern(
            [_node("p", "Person"), _PRINCIPAL, _node("g", "Organisation")],
            [_link("MEMBER_OF", "p", "g"), _link("MEMBER_OF", "s", "g")],
        ),
        selected=1,
    ),
    _case(6, "Which prisoners were found with a mobile phone since 1 January?", None),
    _case(
        7,
        "Which prisoners are named in more than one report?",
        _pattern(
            [_node("p", "Person"), _node("a", "Document"), _node("b", "Document")],
            [_link("MENTIONED_IN", "p", "a"), _link("MENTIONED_IN", "p", "b")],
        ),
    ),
    _case(
        8,
        "Who are the principal's co-defendants?",
        _pattern([_node("p", "Person"), _PRINCIPAL], [_link("CO_DEFENDANT_OF", "p", "s")]),
        selected=1,
    ),
    _case(
        9,
        "Which visitors have visited more than one prisoner?",
        _pattern(
            [_node("v", "Person"), _node("a", "Person"), _node("b", "Person")],
            [_link("VISITED", "v", "a"), _link("VISITED", "v", "b")],
        ),
    ),
    _case(
        10,
        "Who calls the coordinator's number?",
        _pattern(
            [_node("p", "Endpoint"), _node("s", "Endpoint", pinned=SELECTED)],
            [_link("COMMUNICATED_WITH", "p", "s")],
        ),
        selected=1,
    ),
    _case(
        11,
        "Who is in conflict with the principal?",
        _pattern([_node("p", "Person"), _PRINCIPAL], [_link("IN_CONFLICT_WITH", "p", "s")]),
        selected=1,
    ),
    _case(
        12,
        "Which group members are on Wing F?",
        _pattern(
            [
                _node("p", "Person"),
                _node("g", "Organisation"),
                _node("c", "Location"),
                _node("w", "Location", where={"name": "Wing F"}),
            ],
            [
                _link("MEMBER_OF", "p", "g"),
                _link("PRESENT_AT", "p", "c"),
                _link("PART_OF", "c", "w"),
            ],
        ),
    ),
    _case(
        13,
        "Which prisoners were involved in an incident in one of the hotspot yards?",
        _pattern(
            [
                _node("p", "Person"),
                _node("i", "Incident"),
                _node("y", "Location"),
                _node("w", "Location", where={"name": "Wing F"}),
            ],
            [
                _link("ROLE_IN", "p", "i"),
                _link("OCCURRED_AT", "i", "y"),
                _link("USED_BY", "y", "w"),
            ],
        ),
    ),
    _case(
        14,
        "Which reports name the principal?",
        _pattern([_PRINCIPAL, _node("d", "Document")], [_link("MENTIONED_IN", "s", "d")]),
        selected=1,
    ),
    _case(
        15,
        "Which handsets are paired with a SIM that contacted the coordinator's number?",
        _pattern(
            [
                _node("d", "Device"),
                _node("m", "Endpoint"),
                _node("n", "Endpoint", pinned=SELECTED),
            ],
            [_link("PAIRED_WITH", "m", "d"), _link("COMMUNICATED_WITH", "m", "n")],
        ),
        selected=1,
    ),
    _case(
        16,
        "Who is a relative of someone in a group?",
        _pattern(
            [_node("a", "Person"), _node("b", "Person"), _node("g", "Organisation")],
            [_link("FAMILY_OF", "a", "b"), _link("MEMBER_OF", "b", "g")],
        ),
    ),
    _case(
        17,
        "Who shares a visitor with the principal and is paid from the same account?",
        _pattern(
            [
                _node("v", "Person"),
                _PRINCIPAL,
                _node("o", "Person"),
                _node("a", "Endpoint"),
                _node("x", "Endpoint"),
                _node("b", "Endpoint"),
            ],
            [
                _link("VISITED", "v", "s"),
                _link("VISITED", "v", "o"),
                _link("USES", "s", "a"),
                _link("TRANSACTED", "x", "a"),
                _link("TRANSACTED", "x", "b"),
                _link("USES", "o", "b"),
            ],
        ),
        selected=1,
    ),
    _case(18, "Who is guilty?", None),
    _case(19, "Who will throw the next package?", None),
    _case(20, "Which prisoners have a phone I have not seen?", None),
)
