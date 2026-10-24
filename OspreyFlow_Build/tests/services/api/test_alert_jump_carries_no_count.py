"""The alert jump says how many referents it seeded and nothing about the rest (ADR-124 decision 1).

`AlertJumpResult.unreadable_count` counted the referents that became unreadable between the alert
firing and the jump: a figure for what the jumper may not read, which an alert whose referents are
known to its raiser could be used to measure. The route's answer is the new case and how many
nodes it holds. A referent the jumper cannot read, and one that does not exist, are left out of
the case the same way and leave no trace in the answer.
"""

from __future__ import annotations

from datetime import UTC, datetime

from services.api.watch_routes import AlertJumpResult, fetch_jumpable_referents

from schemas.domain import (
    Alert,
    AlertMode,
    AuditStub,
    Handling,
    Node,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
)

READER = Principal(id="analyst-1", clearance="OFFICIAL", org_unit="unit-1")
WHEN = datetime(2026, 1, 1, tzinfo=UTC)


def _node(node_id: str) -> Node:
    return Node(
        id=node_id,
        type="Person",
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="d", locator="l", excerpt_hash="a" * 64)],
            first_seen=WHEN,
        ),
        handling=Handling(
            classification="OFFICIAL", handling_code="P", originator="u", owning_unit="u"
        ),
        audit=AuditStub(created_at=WHEN, created_by="t"),
    )


class _Graph:
    """Holds `held` nodes; one it also holds in `hidden` is refused as the adapter refuses it."""

    def __init__(self, held: set[str], hidden: set[str]) -> None:
        self.held, self.hidden = held, hidden

    async def get_node(self, node_id: str, principal: Principal) -> Node | None:
        if node_id in self.hidden or node_id not in self.held:
            return None
        return _node(node_id)


def _alert(referents: list[str]) -> Alert:
    return Alert(
        id="al-1",
        rule_id="r-1",
        owner_id="analyst-1",
        mode=AlertMode.FULL,
        referent_node_ids=referents,
        investigation_id="case-1",
        created_at=WHEN,
    )


def test_the_jump_result_has_a_case_and_a_seeded_count_and_no_other_figure() -> None:
    assert set(AlertJumpResult.model_fields) == {"investigation", "seeded_count"}


async def test_a_hidden_referent_and_an_absent_one_leave_the_same_answer() -> None:
    """The referents come back as a list of what was readable and nothing else: not a pair with a
    count, and the same list whether the one left out is hidden or does not exist."""
    alert = _alert(["a", "x", "b"])
    hidden = await fetch_jumpable_referents(
        alert,
        principal=READER,
        graph=_Graph({"a", "x", "b"}, {"x"}),  # type: ignore[arg-type]
    )
    absent = await fetch_jumpable_referents(
        alert,
        principal=READER,
        graph=_Graph({"a", "b"}, set()),  # type: ignore[arg-type]
    )

    assert isinstance(hidden, list) and isinstance(absent, list)
    assert [n.id for n in hidden] == [n.id for n in absent] == ["a", "b"]
