"""The reader's *Needs you* route, L2.7 (`06_DECISIONS.md` ADR-145 decision 11, A2; Amendment 4
decision 11, R7; ADR-090 Amendment 4; ADR-143 Amendment 4's *Open*, the strict reading). The real
app, `get_principal`, the route, `_promotion_recipients`, `_reads_proposal_words` and `needs_you.py`
run; the stores are stood in for, each answering as its real one does (`alerts_for` as
`InMemoryAgeingStore`'s, which `test_promotion_ageing.py` holds to the Postgres one's contract).

What a mistake would do, and the case that catches it (each shown red at its call site,
`process/lanes/admin/L2.7_RED_RECORD.md`):

- an overdue promotion shown to someone who is no longer a recipient (`still` bypassed, the stored
  list trusted): `test_an_overdue_promotion_is_shown_only_to_a_current_recipient`;
- a proposal above the reader's clearance counted or described (the clearance filter removed):
  `test_the_count_leaves_out_proposals_the_reader_cannot_read`;
- a dataset reached by no case of the reader's asked or listed:
  `test_only_the_datasets_the_readers_cases_load_into_are_asked`;
- proposals counted for someone without `accept_types`:
  `test_no_proposal_is_counted_without_accept_types`.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from services.api.app import app
from services.api.datasets import Dataset
from services.api.investigations import AccessLevel, Investigation
from services.api.link_types import ModelProposalView
from services.api.needs_you import to_decide
from services.api.promotion_ageing import InMemoryAgeingStore, PendingPromotion

from ontology.handling import HandlingScheme
from schemas.admin import PersonAccount, PromotionOverdueAlert
from schemas.dataset_model import HomeCase
from schemas.domain import Principal

T0 = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
SCHEME = HandlingScheme(name="t", classification=["OFFICIAL", "SECRET", "TOP SECRET"],
                        handling_codes={}, action_codes={}, sanitisation_codes={})  # fmt: skip
TOKENS: dict[str, Principal] = {}


def _account(pid: str, roles: list[str], *, unit: str = "unit-1", clearance: str = "SECRET",
             enabled: bool = True) -> PersonAccount:  # fmt: skip
    return PersonAccount(id=pid, username=pid, name=pid, enabled=enabled, roles=roles,
                         org_unit=unit, clearance=clearance)  # fmt: skip


def _token(account: PersonAccount) -> None:
    TOKENS[account.id] = Principal(id=account.id, clearance=account.clearance or "OFFICIAL",
                                   org_unit=account.org_unit or "unit-1",
                                   roles=list(account.roles))  # fmt: skip


class _Resolver:
    def resolve(self, token: str) -> Principal:
        return TOKENS[token]


def _dataset(did: str, name: str, marking: str | None = None, unit: str = "unit-1") -> Dataset:
    return Dataset(id=did, name=name, owning_unit=unit, created_at=T0, created_by="seed",
                   highest_marking=marking)  # fmt: skip


class _Datasets:
    """The dataset store's reads the route and `_promotion_recipients` make, as the real one answers
    them: a case's datasets in order, a dataset's home case, and the datasets held by id."""

    def __init__(self) -> None:
        self.held = {
            "ds-a": _dataset("ds-a", "Prison records", "SECRET"),
            "ds-top": _dataset("ds-top", "Border watch", "TOP SECRET"),
            "ds-c": _dataset("ds-c", "Someone else's data", "OFFICIAL"),
            "ds-x": _dataset("ds-x", "Intake extract", "OFFICIAL"),
        }
        self.cases = {"case-a": ["ds-a"], "case-top": ["ds-top"], "case-c": ["ds-c"],
                      "case-reads": ["ds-x", "ds-a"]}  # loads into ds-x, only reads ds-a
        self.homes = {"ds-a": HomeCase(dataset_id="ds-a", investigation_id="home-a",
                                    made_at=T0, made_by="seed")}

    async def egress_of(self, ids: Any) -> dict[str, Dataset]:
        return {i: self.held[i] for i in ids if i in self.held}

    async def ids_of_case(self, case_id: str) -> list[str]:
        return list(self.cases.get(case_id, []))

    async def home_case_of(self, dataset_id: str) -> HomeCase | None:
        return self.homes.get(dataset_id)

    async def list_for(self, principal: Principal) -> list[Dataset]:
        """Every dataset of the reader's unit (the real `list_for`), wider than the Studio's reach:
        `test_only_the_datasets_the_readers_cases_load_into_are_asked`'s plant reads it."""
        return [d for d in self.held.values() if d.owning_unit == principal.org_unit]


class _Cases:
    """`list_for` as the real store answers it: the cases the principal holds a level on."""

    def __init__(self) -> None:
        self.levels: dict[str, dict[str, AccessLevel]] = {
            "eng-1": {"case-a": AccessLevel.EDITOR, "case-top": AccessLevel.EDITOR},
            "rev-1": {"case-a": AccessLevel.AUTHOR},
            "gone-1": {"case-a": AccessLevel.AUTHOR},
            "ana-1": {"case-a": AccessLevel.EDITOR},
            "other-eng": {"case-c": AccessLevel.EDITOR},
            "reader-eng": {"case-reads": AccessLevel.EDITOR},
        }
        self.grants = {"home-a": {"rev-1": AccessLevel.AUTHOR, "gone-1": AccessLevel.AUTHOR}}

    async def list_for(self, principal: Principal) -> list[tuple[Investigation, AccessLevel]]:
        return [
            (Investigation(id=cid, name=cid, created_at=T0, created_by="seed",
                           owning_unit=principal.org_unit), level)
            for cid, level in self.levels.get(principal.id, {}).items()
        ]  # fmt: skip

    async def list_grants(self, case_id: str) -> dict[str, AccessLevel]:
        return dict(self.grants.get(case_id, {}))


class _People:
    def __init__(self, people: list[PersonAccount]) -> None:
        self.people = people
        self.reads = 0

    async def list_people(self) -> list[PersonAccount]:
        self.reads += 1
        return list(self.people)


def _proposal(pid: str, status: str, in_model: str | None = None) -> ModelProposalView:
    return ModelProposalView(id=pid, name=f"WORDS_OF_{pid}", label=f"Label of {pid}",
                             from_types=["Person"], to_types=["Vehicle"], directed=True,
                             proposed_by="ana-1", proposed_at=T0, reason=f"Reason of {pid}",
                             status=status, in_model=in_model)  # type: ignore[arg-type]  # fmt: skip


class _LinkTypes:
    """`dataset_proposal_views` as the real service answers it: each proposal of the dataset, and
    to a reader who may not read the words, each `without_words()` (`link_types.py`)."""

    def __init__(self) -> None:
        self.of: dict[str, list[ModelProposalView]] = {
            "ds-a": [_proposal("p1", "pending"), _proposal("p2", "pending"),
                     _proposal("p3", "rejected"), _proposal("p4", "accepted", "live"),
                     _proposal("p5", "accepted")],
            "ds-top": [_proposal("t1", "pending"), _proposal("t2", "pending")],
            "ds-c": [_proposal("c1", "pending")],
            "ds-x": [],
        }  # fmt: skip
        self.asked: list[tuple[str, bool]] = []

    async def dataset_proposal_views(
        self, dataset_id: str, *, may_read_words: bool = True
    ) -> list[ModelProposalView]:
        self.asked.append((dataset_id, may_read_words))
        views = self.of.get(dataset_id, [])
        return list(views) if may_read_words else [v.without_words() for v in views]


PROMOTION = PendingPromotion(promotion_id="pr-1", load_id="load-7", dataset_id="ds-a",
                             dataset_name="Prison records", dataset_unit="unit-1",
                             proposed_by="ana-1", proposed_at=T0,
                             dataset_marking="SECRET")  # fmt: skip


class _Waiting:
    """The seam L3.4 fills (`WaitingPromotions`): the promotions waiting now."""

    recorded = True

    def __init__(self, waiting: list[PendingPromotion]) -> None:
        self.waiting = waiting

    async def waiting_for_review(self, reader: Principal) -> list[PendingPromotion]:
        return list(self.waiting)

    async def all_waiting(self) -> list[PendingPromotion]:
        return list(self.waiting)


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    TOKENS.clear()
    people = [
        _account("rev-1", ["data_engineer"]),
        _account("gone-1", ["data_engineer"]),
        _account("adm-1", ["osprey-admin"]),
        _account("eng-1", ["data_engineer"]),
        _account("ana-1", ["analyst"]),
        _account("other-eng", ["data_engineer"]),
        _account("reader-eng", ["data_engineer"]),
    ]
    for person in people:
        _token(person)
    ageing = InMemoryAgeingStore()
    waiting = _Waiting([PROMOTION])
    state = {"principal_resolver": _Resolver(), "promotion_ageing": ageing,
             "waiting_promotions": waiting,
             "investigations": _Cases(), "datasets": _Datasets(), "link_types": _LinkTypes(),
             "identity_admin": _People(people), "custom_roles": None,
             "handling_scheme": SCHEME, "graph": object(), "analytics": object(),
             "alerts_store": object()}  # fmt: skip
    for name, value in state.items():
        monkeypatch.setattr(app.state, name, value, raising=False)
    yield SimpleNamespace(client=TestClient(app), ageing=ageing, people=people, waiting=waiting,
                          **state)  # fmt: skip


def _read(world: SimpleNamespace, who: str) -> dict[str, Any]:
    answer = world.client.get("/v1/me/needs-you", headers={"Authorization": f"Bearer {who}"})
    assert answer.status_code == 200, answer.text
    return answer.json()  # type: ignore[no-any-return]


async def _raise(world: SimpleNamespace, recipients: list[str]) -> None:
    alert = PromotionOverdueAlert(promotion_id="pr-1", load_id="load-7", dataset_id="ds-a",
                                  raised_at=T0 + timedelta(days=3), recipients=recipients,
                                  words="Promotion load-7 into Prison records has waited 3 days "
                                        "for review.")  # fmt: skip
    assert await world.ageing.raise_once(alert, PROMOTION)


def test_an_overdue_promotion_is_shown_only_to_a_current_recipient(world: SimpleNamespace) -> None:
    """Raised to an Author holding `review_promotions`, another since disabled, and the unit's
    administrator. At the read, each recipient who is still one sees it, and the one disabled since
    does not: the route asks `_promotion_recipients` again rather than trusting the stored list.
    No one else sees it, and nobody is told who else was alerted. Red with `still` bypassed
    (the route passing every stored recipient)."""
    import asyncio

    asyncio.run(_raise(world, ["adm-1", "gone-1", "rev-1"]))
    world.people[1] = _account("gone-1", ["data_engineer"], enabled=False)
    for who in ("rev-1", "adm-1"):
        [notice] = _read(world, who)["promotions_overdue"]
        assert notice["promotion_id"] == "pr-1" and notice["load_id"] == "load-7"
        assert "recipients" not in notice and "gone-1" not in str(notice)
    for who in ("gone-1", "ana-1", "eng-1"):
        assert _read(world, who)["promotions_overdue"] == [], who


def test_a_recipient_cleared_below_the_marking_since_is_shown_nothing(
    world: SimpleNamespace,
) -> None:
    """The same read, the recipient's clearance lowered below the dataset's marking since: the
    alert names the dataset, so it is not served (Amendment 4 decision 11). Red with `still`
    bypassed."""
    import asyncio

    asyncio.run(_raise(world, ["rev-1"]))
    world.people[0] = _account("rev-1", ["data_engineer"], clearance="OFFICIAL")
    assert _read(world, "rev-1")["promotions_overdue"] == []


def test_the_count_leaves_out_proposals_the_reader_cannot_read(world: SimpleNamespace) -> None:
    """eng-1 (SECRET, `accept_types`) reaches ds-a (SECRET) and ds-top (TOP SECRET). ds-a's count
    is its pending proposals and the accepted one lost from the model (3), never the declined one
    or the one in the live model. ds-top's two are above eng-1's clearance, so they are neither
    counted nor described: the entry says only that one or more exist. Red with the clearance
    filter removed (`_reads_proposal_words` answering True)."""
    body = _read(world, "eng-1")
    by = {p["dataset_id"]: p for p in body["proposals"]}
    assert by["ds-a"] == {"dataset_id": "ds-a", "dataset_name": "Prison records",
                          "to_decide": 3, "above_clearance": False}  # fmt: skip
    assert by["ds-top"] == {"dataset_id": "ds-top", "dataset_name": "Border watch",
                            "to_decide": 0, "above_clearance": True}  # fmt: skip
    assert "WORDS_OF_t" not in str(body) and "Label of t" not in str(body)
    assert "Reason of t" not in str(body)


def test_only_the_datasets_the_readers_cases_load_into_are_asked(world: SimpleNamespace) -> None:
    """ds-c is reached only by other-eng's case: eng-1's read neither asks for its proposals nor
    names it, and other-eng's names ds-c alone. Red with the reach widened to every dataset held."""
    body = _read(world, "eng-1")
    assert "ds-c" not in str(body) and "Someone else" not in str(body)
    assert all(d != "ds-c" for d, _ in world.link_types.asked)
    world.link_types.asked.clear()
    other = _read(world, "other-eng")
    assert [p["dataset_id"] for p in other["proposals"]] == ["ds-c"]
    assert {d for d, _ in world.link_types.asked} == {"ds-c"}


def test_no_proposal_is_counted_without_accept_types(world: SimpleNamespace) -> None:
    """ana-1 reaches ds-a through case-a but holds no `accept_types`: no proposal is counted or
    asked for. Red with the right check removed."""
    assert _read(world, "ana-1") == {"promotions_overdue": [], "proposals": []}
    assert world.link_types.asked == []


def test_a_promotion_no_longer_waiting_is_not_shown(world: SimpleNamespace) -> None:
    """Approved, rejected or withdrawn since its alert, a promotion leaves the seam's waiting list,
    and *Needs you* no longer serves it: the alert's store keeps it, the read asks the seam. Its
    words are said as they stand now, not as they stood when raised. Red with the waiting list not
    asked."""
    import asyncio

    asyncio.run(_raise(world, ["rev-1"]))
    [notice] = _read(world, "rev-1")["promotions_overdue"]
    assert "has waited" in notice["words"] and "3 days" not in notice["words"]  # its age now
    world.waiting.waiting = []
    assert _read(world, "rev-1")["promotions_overdue"] == []


def test_the_people_are_read_once_a_read(world: SimpleNamespace) -> None:
    """The recipients of every stored alert are asked from one read of the people (the top bar
    reads every minute)."""
    import asyncio

    from dataclasses import replace

    asyncio.run(_raise(world, ["rev-1"]))
    second = replace(PROMOTION, promotion_id="pr-2", load_id="load-8")
    world.waiting.waiting = [PROMOTION, second]
    alert = PromotionOverdueAlert(promotion_id="pr-2", load_id="load-8", dataset_id="ds-a",
                                  raised_at=T0 + timedelta(days=3), recipients=["rev-1"],
                                  words="Promotion load-8 into Prison records has waited 3 days.")  # fmt: skip
    assert asyncio.run(world.ageing.raise_once(alert, second))
    world.identity_admin.reads = 0
    assert len(_read(world, "rev-1")["promotions_overdue"]) == 2
    assert world.identity_admin.reads == 1


def test_a_dataset_whose_above_clearance_proposals_are_decided_is_not_flagged(
    world: SimpleNamespace,
) -> None:
    """ds-top's two proposals, above eng-1's clearance, both declined since: nothing is left to
    decide there, so nothing is said of it. Red with the flag raised by any withheld proposal,
    whatever its status."""
    world.link_types.of["ds-top"] = [_proposal("t1", "rejected"), _proposal("t2", "promoted")]
    body = _read(world, "eng-1")
    assert "ds-top" not in [p["dataset_id"] for p in body["proposals"]]


def test_a_dataset_a_case_only_reads_is_not_reached(world: SimpleNamespace) -> None:
    """reader-eng's case loads into ds-x and only reads ds-a: as the Studio's own reach
    (`scope_to_dataset`, its first dataset alone), ds-a's proposals are neither asked nor counted.
    Red with every dataset of the case taken."""
    body = _read(world, "reader-eng")
    assert "ds-a" not in str(body)
    assert {d for d, _ in world.link_types.asked} <= {"ds-x"}


@pytest.mark.parametrize(
    ("status", "in_model", "withheld", "counted"),
    [
        ("pending", None, False, True),
        ("accepted", None, False, True),
        ("accepted", "draft", False, False),
        ("accepted", "live", False, False),
        ("rejected", None, False, False),
        ("withdrawn", None, False, False),
        ("pending", None, True, False),
    ],
)
def test_to_decide_is_the_model_tabs_own_rule(
    status: str, in_model: str | None, withheld: bool, counted: bool
) -> None:
    """The count is `ModelProposals.tsx`'s `decidable`: pending, or accepted and lost from the
    model, and never a withheld one."""
    view = _proposal("x", status, in_model)
    if withheld:
        view = view.without_words().model_copy(update={"status": status})
    assert to_decide(view) is counted
