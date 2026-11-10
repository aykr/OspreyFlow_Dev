"""L2.5b on real Postgres (a lane's leased test stack): *Disable…*'s plan offers the views, boards,
link-type proposals and drawn-item watches L3.8's ownership read names (`person_ownership.py`), each
transferred with an audit row, and *Transfer and disable* refused while anything is withheld from
the administrator (`06_DECISIONS.md` ADR-145 Amendment 8, the owner's ruling of 9 November 2026).
A schema of its own per test, dropped in teardown whether it passes or fails.

What a mistake would do, and the case that catches it (each shown red by a plant at its call site,
`process/lanes/admin/L2.5b_RED_RECORD.md`):

- one of the four kinds left out of the plan, or its owner column not changed:
  `test_each_of_the_four_kinds_is_offered_moved_and_audited`;
- the plan reading L3.8's items without the administrator's unit or clearance (an item named that
  they may not see): `test_an_item_above_the_administrator_is_never_offered_and_refuses_the_disable`;
- the transfers rolled back when something is withheld, or a cover ended by the transfer: the same
  case's "those stand" and cover assertions (the route's order, `refuse_if_withheld` then
  `end_covers`, is `test_admin_roles_routes.py`'s);
- a recipient without a level on the item's case, or not cleared to its dataset's marking, given
  it anyway: `test_a_recipient_without_the_case_level_or_the_marking_is_refused_and_nothing_moves`;
  a dataset with no marking, or a watch with none, read as cleared:
  `test_an_unmarked_dataset_or_none_is_read_at_the_schemes_highest_for_the_recipient`;
- a view or a board given to someone not cleared to its case's highest marking (ADR-145
  Amendment 9: a view's count is unfiltered), or the highest read as the lowest, or a composite's
  members missed: `test_a_view_or_board_goes_only_to_someone_cleared_to_its_cases_highest`;
- the case's unit-wide level not counted (a unit member refused a view they hold Viewer on):
  `test_a_recipient_holding_the_cases_unit_wide_level_may_take_a_view`.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from types import SimpleNamespace

import asyncpg
import pytest
from services.api.admin_people import AdminPeopleStore, DisableRefused, recipients
from services.api.audit import AuditWriter
from services.api.board_store import PostgresBoardItemStore
from services.api.case_views import PostgresCaseViewStore
from services.api.config import PostgresConfig
from services.api.custom_roles import CustomRoleStore
from services.api.datasets import PostgresDatasetStore
from services.api.hotlists import HotlistStore
from services.api.investigations import InvestigationStore
from services.api.link_type_store import LinkTypeProposalStore
from services.api.monitors import MonitorStore
from services.api.pattern_store import PatternStore
from services.api.person_ownership import WITHHELD_ERROR
from services.api.screening import ScreeningListStore
from services.api.studio_recipes import StudioRecipeStore
from services.api.typology_rules import TypologyRuleStore

from ontology.handling import load_uk_le_scheme
from schemas.admin import OwnedTransfer, PersonAccount, TeamInput
from schemas.domain import Principal
from schemas.rights import Right

T0 = datetime(2026, 11, 10, tzinfo=UTC)
UNIT = "unit-1"
SCHEME = load_uk_le_scheme()
#: Below the scheme's highest, so a SECRET dataset's items are withheld from them (rule 15: markings
#: the scheme itself holds).
ADMIN = Principal(id="adm-1", clearance="OFFICIAL-SENSITIVE", org_unit=UNIT, roles=["osprey-admin"])
CLEARED = Principal(id="adm-2", clearance="SECRET", org_unit=UNIT, roles=["osprey-admin"])
SECRET_WORDS = "Operation Nightjar contacts"


def _person(pid: str, roles: list[str], *, clearance: str = "SECRET", unit: str = UNIT) -> PersonAccount:
    return PersonAccount(id=pid, username=pid, name=f"Name {pid}", enabled=True, roles=roles,
                         clearance=clearance, org_unit=unit)  # fmt: skip


@pytest.fixture
async def world() -> AsyncIterator[SimpleNamespace]:
    name = "l25b_" + uuid.uuid4().hex[:10]
    base = PostgresConfig.from_env().dsn
    conn = await asyncpg.connect(dsn=base)
    await conn.execute(f'CREATE SCHEMA "{name}"')
    await conn.close()
    dsn = f"{base}{'&' if '?' in base else '?'}search_path={name}"
    stores: list[object] = []
    try:
        for store in (InvestigationStore, PostgresDatasetStore, PostgresCaseViewStore,
                      PostgresBoardItemStore, LinkTypeProposalStore, HotlistStore, MonitorStore,
                      PatternStore, TypologyRuleStore, ScreeningListStore, StudioRecipeStore,
                      AuditWriter, CustomRoleStore, AdminPeopleStore):  # fmt: skip
            stores.append(await store.connect(dsn))  # type: ignore[attr-defined]
        raw = await asyncpg.connect(dsn=dsn)
        try:
            yield SimpleNamespace(raw=raw, audit=stores[-3], roles=stores[-2], people=stores[-1])
        finally:
            await raw.close()
    finally:
        for held in stores:
            await held.close()  # type: ignore[attr-defined]
        conn = await asyncpg.connect(dsn=base)
        await conn.execute(f'DROP SCHEMA "{name}" CASCADE')
        await conn.close()


async def _case(raw: asyncpg.Connection, case_id: str, name: str, grants: dict[str, str]) -> None:
    await raw.execute(
        "INSERT INTO investigations (id, created_at, created_by, owning_unit, name) "
        "VALUES ($1, $2, 'seed', $3, $4)",
        case_id, T0, UNIT, name,
    )  # fmt: skip
    for account, level in grants.items():
        await raw.execute(
            "INSERT INTO investigation_grants (investigation_id, account_id, level) VALUES ($1, $2, $3)",
            case_id, account, level,
        )  # fmt: skip


async def _dataset(raw: asyncpg.Connection, dataset_id: str, marking: str | None) -> None:
    assert marking is None or marking in SCHEME.classification, marking
    await raw.execute(
        "INSERT INTO datasets (id, name, owning_unit, created_at, created_by, highest_marking) "
        "VALUES ($1, $1, $2, $3, 'seed', $4)",
        dataset_id, UNIT, T0, marking,
    )  # fmt: skip


async def _view(raw: asyncpg.Connection, case_id: str, by: str, *, board: bool = False) -> str:
    view_id = f"v-{uuid.uuid4().hex[:8]}"
    await raw.execute(
        "INSERT INTO case_views (id, case_id, name, created_by, created_at, shared, lens, drawing) "
        "VALUES ($1, $2, $3, $4, $5, FALSE, '{}'::jsonb, $6)",
        view_id, case_id, SECRET_WORDS, by, T0, board,
    )  # fmt: skip
    return view_id


async def _proposal(raw: asyncpg.Connection, case_id: str, by: str, dataset: str) -> str:
    proposal_id = f"p-{uuid.uuid4().hex[:8]}"
    await raw.execute(
        "INSERT INTO link_type_proposals (id, name, label, from_types, to_types, directed, "
        "investigation_id, owning_unit, proposed_by, proposed_at, reason, status, dataset_id) "
        "VALUES ($1, 'NIGHTJAR_CONTACT', $2, ARRAY['Person'], ARRAY['Person'], TRUE, $3, $4, $5, "
        "$6, $2, 'pending', $7)",
        proposal_id, SECRET_WORDS, case_id, UNIT, by, T0, dataset,
    )  # fmt: skip
    return proposal_id


async def _watch(raw: asyncpg.Connection, case_id: str, owner: str, dataset: str) -> str:
    item_id, watch_id = f"i-{uuid.uuid4().hex[:8]}", f"w-{uuid.uuid4().hex[:8]}"
    await raw.execute(
        "INSERT INTO board_items (item_id, board_id, case_id, kind, element_id, author, "
        "dataset_id, created_at) VALUES ($1, 'b-1', $2, 'node', 'el-1', $3, $4, $5)",
        item_id, case_id, owner, dataset, T0,
    )  # fmt: skip
    await raw.execute(
        "INSERT INTO drawn_watches (id, item_id, element_id, case_id, dataset_id, owner, created_at) "
        "VALUES ($1, $2, 'el-1', $3, $4, $5, $6)",
        watch_id, item_id, case_id, dataset, owner, T0,
    )  # fmt: skip
    return watch_id


async def _owners(raw: asyncpg.Connection) -> dict[str, str]:
    rows = [
        *await raw.fetch("SELECT id, created_by AS who FROM case_views"),
        *await raw.fetch("SELECT id, proposed_by AS who FROM link_type_proposals"),
        *await raw.fetch("SELECT id, owner AS who FROM drawn_watches"),
    ]
    return {r["id"]: r["who"] for r in rows}


EVERY = ["analyst", "data_engineer"]


async def _four(raw: asyncpg.Connection, dataset: str = "ds-off") -> dict[str, str]:
    return {
        "view": await _view(raw, "c-k", "ana"),
        "board": await _view(raw, "c-k", "ana", board=True),
        "link_type_proposal": await _proposal(raw, "c-k", "ana", dataset),
        "drawn_watch": await _watch(raw, "c-k", "ana", dataset),
    }


async def test_each_of_the_four_kinds_is_offered_moved_and_audited(world: SimpleNamespace) -> None:
    raw = world.raw
    await _case(raw, "c-k", "Kestrel", {"ana": "editor", "bea": "editor"})
    await _dataset(raw, "ds-off", "OFFICIAL")
    ids = await _four(raw)
    plan = await world.people.plan("ana", admin=ADMIN, scheme=SCHEME)
    assert sorted((i.kind, i.id, i.investigation_id) for i in plan.items) == sorted(
        (k, v, "c-k") for k, v in ids.items()
    )
    assert all("Kestrel" in i.label and SECRET_WORDS not in i.label for i in plan.items)
    assert plan.not_yet_listed == ["promotions waiting for review", "reviews waiting on them"]
    who = recipients([_person("ana", EVERY), _person("bea", EVERY)], {}, {})
    moved, left = await world.people.transfer(
        "ana", [OwnedTransfer(kind=i.kind, id=i.id, to="bea") for i in plan.items], who,
        by=ADMIN, audit=world.audit, admin_unit=UNIT, scheme=SCHEME,
    )  # fmt: skip
    assert len(moved) == 4 and left == 0
    assert await _owners(raw) == dict.fromkeys(ids.values(), "bea")
    audited = await raw.fetch(
        "SELECT resolved_query->>'kind' AS kind FROM audit_log WHERE action = 'transfer_owned_item'"
    )
    assert sorted(r["kind"] for r in audited) == sorted(ids)
    assert (await world.people.plan("ana", admin=ADMIN, scheme=SCHEME)).items == []
    await world.people.refuse_if_withheld("ana", admin=ADMIN, scheme=SCHEME)  # nothing withheld


async def test_an_item_above_the_administrator_is_never_offered_and_refuses_the_disable(
    world: SimpleNamespace,
) -> None:
    raw = world.raw
    await _case(raw, "c-k", "Kestrel", {"ana": "editor", "bea": "editor"})
    await _dataset(raw, "ds-off", "OFFICIAL")
    await _dataset(raw, "ds-secret", "SECRET")
    visible = await _four(raw)
    hidden = await _watch(raw, "c-k", "ana", "ds-secret")
    role = await world.roles.create("Intel desk", [Right.INVESTIGATE], by="adm-1")
    await world.roles.make_team(role.id, TeamInput(display_name="Intel", mailbox="i@example.org"),
                                date(2026, 11, 10))  # fmt: skip
    await raw.execute("UPDATE teams SET cover = 'ana', cover_until = $2 WHERE role_id = $1",
                      role.id, date(2026, 11, 30))  # fmt: skip

    plan = await world.people.plan("ana", admin=ADMIN, scheme=SCHEME)
    assert hidden not in {i.id for i in plan.items}
    assert {i.id for i in plan.items} == set(visible.values())
    who = recipients([_person("ana", EVERY), _person("bea", EVERY)], {}, {})
    moved, left = await world.people.transfer(
        "ana", [OwnedTransfer(kind=i.kind, id=i.id, to="bea") for i in plan.items], who,
        by=ADMIN, audit=world.audit, admin_unit=UNIT, scheme=SCHEME,
    )  # fmt: skip
    assert len(moved) == 4 and left == 0
    with pytest.raises(DisableRefused) as refused:
        await world.people.refuse_if_withheld("ana", admin=ADMIN, scheme=SCHEME)
    assert refused.value.error == WITHHELD_ERROR and refused.value.items == []
    words = refused.value.words.lower()
    for said in ("watch", "secret", "kestrel", "nightjar", "1"):
        assert said not in words, said
    owners = await _owners(raw)
    assert owners.pop(hidden) == "ana", "nothing is moved by anyone who cannot see it"
    assert owners == dict.fromkeys(visible.values(), "bea"), "the visible transfers stand"
    assert await raw.fetchval("SELECT cover FROM teams WHERE role_id = $1", role.id) == "ana", (
        "a cover ends only with the disable, which is refused"
    )

    # An administrator cleared to the item's marking sees and transfers it; then the disable goes.
    plan = await world.people.plan("ana", admin=ADMIN, scheme=SCHEME)
    assert plan.items == []
    cleared = await world.people.plan("ana", admin=CLEARED, scheme=SCHEME)
    assert [i.id for i in cleared.items] == [hidden]
    await world.people.transfer("ana", [OwnedTransfer(kind="drawn_watch", id=hidden, to="bea")],
                                who, by=CLEARED, audit=world.audit, admin_unit=UNIT,
                                scheme=SCHEME)  # fmt: skip
    await world.people.refuse_if_withheld("ana", admin=ADMIN, scheme=SCHEME)
    assert await raw.fetchval("SELECT cover FROM teams WHERE role_id = $1", role.id) == "ana"
    await world.people.end_covers("ana", by=ADMIN, audit=world.audit)
    assert await raw.fetchval("SELECT cover FROM teams WHERE role_id = $1", role.id) is None


@pytest.mark.parametrize(
    ("kind", "grants", "clearance", "why"),
    [
        ("view", {"ana": "editor"}, "SECRET", "Viewer"),
        ("board", {"ana": "editor", "bea": "viewer"}, "SECRET", "Editor"),
        ("link_type_proposal", {"ana": "editor", "bea": "viewer"}, "SECRET", "Editor"),
        ("drawn_watch", {"ana": "editor", "bea": "editor"}, "OFFICIAL", "cleared"),
        ("link_type_proposal", {"ana": "editor", "bea": "editor"}, "OFFICIAL", "cleared"),
    ],
)
async def test_a_recipient_without_the_case_level_or_the_marking_is_refused_and_nothing_moves(
    world: SimpleNamespace, kind: str, grants: dict[str, str], clearance: str, why: str
) -> None:
    """Each item's recipient holds what its own route asks: a level on its case (Viewer for a view,
    Editor to draw or propose), and for a proposal or a watch, the clearance of its dataset's
    marking, an unmarked one read at the scheme's highest (as L3.8 reads it)."""
    raw = world.raw
    await _case(raw, "c-k", "Kestrel", grants)
    await _dataset(raw, "ds-os", "OFFICIAL-SENSITIVE")
    ids = await _four(raw, "ds-os")
    plan = await world.people.plan("ana", admin=ADMIN, scheme=SCHEME)
    bea = _person("bea", EVERY, clearance=clearance)
    who = recipients([_person("ana", EVERY), bea, _person("cal", EVERY)], {}, {})
    transfers = [OwnedTransfer(kind=i.kind, id=i.id, to="bea" if i.kind == kind else "ana-none")
                 for i in plan.items]  # fmt: skip
    # Every other item goes to someone able to take it, so the refusal is this item's.
    await raw.execute(
        "INSERT INTO investigation_grants (investigation_id, account_id, level) "
        "VALUES ('c-k', 'cal', 'editor') ON CONFLICT DO NOTHING"
    )
    transfers = [t.model_copy(update={"to": "cal"}) if t.to == "ana-none" else t for t in transfers]
    with pytest.raises(DisableRefused) as refused:
        await world.people.transfer("ana", transfers, who, by=ADMIN, audit=world.audit,
                                    admin_unit=UNIT, scheme=SCHEME)  # fmt: skip
    assert refused.value.error == "recipient_refused", refused.value.words
    assert why in refused.value.words and [i.kind for i in refused.value.items] == [kind]
    assert SECRET_WORDS not in refused.value.words
    assert await _owners(raw) == dict.fromkeys(ids.values(), "ana")
    assert await raw.fetchval("SELECT count(*) FROM audit_log") == 0


async def test_a_recipient_made_its_cases_author_in_the_same_transfer_may_take_it(
    world: SimpleNamespace,
) -> None:
    raw = world.raw
    await _case(raw, "c-k", "Kestrel", {"ana": "author"})
    await _dataset(raw, "ds-off", "OFFICIAL")
    view = await _view(raw, "c-k", "ana")
    plan = await world.people.plan("ana", admin=ADMIN, scheme=SCHEME)
    assert sorted(i.kind for i in plan.items) == ["case_author", "view"]
    who = recipients([_person("ana", EVERY), _person("bea", EVERY)], {}, {})
    await world.people.transfer(
        "ana", [OwnedTransfer(kind=i.kind, id=i.id, to="bea") for i in plan.items], who,
        by=ADMIN, audit=world.audit, admin_unit=UNIT, scheme=SCHEME,
    )  # fmt: skip
    assert (await _owners(raw))[view] == "bea"


@pytest.mark.parametrize("dataset", [None, "ds-unmarked"])
async def test_an_unmarked_dataset_or_none_is_read_at_the_schemes_highest_for_the_recipient(
    world: SimpleNamespace, dataset: str | None
) -> None:
    """Rule 12 for `_MARKING_SQL`'s COALESCE: a watch on a dataset with no marking, or on none,
    goes only to a recipient cleared to the scheme's highest (the administrator reading it must be
    too, as L3.8 reads it)."""
    raw = world.raw
    await _case(raw, "c-k", "Kestrel", {"ana": "editor", "bea": "editor", "cal": "editor"})
    if dataset is not None:
        await _dataset(raw, dataset, None)
    item_id, watch = f"i-{uuid.uuid4().hex[:8]}", f"w-{uuid.uuid4().hex[:8]}"
    await raw.execute(
        "INSERT INTO board_items (item_id, board_id, case_id, kind, element_id, author, "
        "dataset_id, created_at) VALUES ($1, 'b-1', 'c-k', 'node', 'el-1', 'ana', $2, $3)",
        item_id, dataset or "ds-none", T0,
    )  # fmt: skip
    await raw.execute(
        "INSERT INTO drawn_watches (id, item_id, element_id, case_id, dataset_id, owner, created_at) "
        "VALUES ($1, $2, 'el-1', 'c-k', $3, 'ana', $4)",
        watch, item_id, dataset, T0,
    )  # fmt: skip
    plan = await world.people.plan("ana", admin=CLEARED, scheme=SCHEME)
    assert [i.id for i in plan.items] == [watch]
    who = recipients([_person("ana", EVERY), _person("bea", EVERY, clearance="OFFICIAL-SENSITIVE"),
                      _person("cal", EVERY)], {}, {})  # fmt: skip
    with pytest.raises(DisableRefused) as refused:
        await world.people.transfer("ana", [OwnedTransfer(kind="drawn_watch", id=watch, to="bea")],
                                    who, by=CLEARED, audit=world.audit, admin_unit=UNIT,
                                    scheme=SCHEME)  # fmt: skip
    assert "cleared" in refused.value.words
    await world.people.transfer("ana", [OwnedTransfer(kind="drawn_watch", id=watch, to="cal")],
                                who, by=CLEARED, audit=world.audit, admin_unit=UNIT,
                                scheme=SCHEME)  # fmt: skip
    assert (await _owners(raw))[watch] == "cal"


async def test_a_recipient_holding_the_cases_unit_wide_level_may_take_a_view(
    world: SimpleNamespace,
) -> None:
    """The level `InvestigationStore` reads: a grant, or the case's unit-wide level for a member
    of its unit (review finding 4). Editor through the unit is not asked of a view; a board, which
    needs Editor, is still refused to a Viewer through the unit."""
    raw = world.raw
    await _case(raw, "c-k", "Kestrel", {"ana": "editor"})
    await raw.execute("UPDATE investigations SET unit_level = 'viewer' WHERE id = 'c-k'")
    view = await _view(raw, "c-k", "ana")
    board = await _view(raw, "c-k", "ana", board=True)
    who = recipients([_person("ana", EVERY), _person("bea", EVERY)], {}, {})
    with pytest.raises(DisableRefused) as refused:
        await world.people.transfer(
            "ana", [OwnedTransfer(kind="view", id=view, to="bea"),
                    OwnedTransfer(kind="board", id=board, to="bea")], who,
            by=ADMIN, audit=world.audit, admin_unit=UNIT, scheme=SCHEME,
        )  # fmt: skip
    assert "Editor" in refused.value.words and [i.kind for i in refused.value.items] == ["board"]
    await raw.execute("DELETE FROM case_views WHERE id = $1", board)
    await world.people.transfer("ana", [OwnedTransfer(kind="view", id=view, to="bea")], who,
                                by=ADMIN, audit=world.audit, admin_unit=UNIT, scheme=SCHEME)  # fmt: skip
    assert (await _owners(raw))[view] == "bea"


async def _reads(raw: asyncpg.Connection, case_id: str, *datasets: str) -> None:
    for position, dataset in enumerate(datasets):
        await raw.execute(
            "INSERT INTO investigation_datasets (investigation_id, dataset_id, position) "
            "VALUES ($1, $2, $3)",
            case_id, dataset, position,
        )  # fmt: skip


@pytest.mark.parametrize(
    ("reads", "highest"),
    # A case reads one dataset (`investigation_datasets_one_per_case`): several are a composite's.
    [(("ds-secret",), "SECRET"), (("ds-off",), "OFFICIAL"), ((), "SECRET"), (("cmp",), "SECRET")],
)  # fmt: skip
async def test_a_view_or_board_goes_only_to_someone_cleared_to_its_cases_highest(
    world: SimpleNamespace, reads: tuple[str, ...], highest: str
) -> None:
    """ADR-145 Amendment 9 (the strict reading, MORNING item 8): a view sends its node count
    unfiltered, so its recipient must clear the highest marking its case reads: its dataset's, or
    the highest of a composite's members; a case reading none, at the scheme's highest. Each
    item says the marking its *Transfer to…* is offered by; a recipient below it is refused,
    naming nothing."""
    raw = world.raw
    await _case(raw, "c-k", "Kestrel", {"ana": "editor", "bea": "editor", "cal": "editor"})
    await _dataset(raw, "ds-off", "OFFICIAL")
    await _dataset(raw, "ds-secret", "SECRET")
    await _dataset(raw, "cmp", None)
    await raw.execute("UPDATE datasets SET kind = 'composite' WHERE id = 'cmp'")
    await raw.execute(
        "INSERT INTO composite_members (composite_id, member_id, position) VALUES "
        "('cmp', 'ds-off', 0), ('cmp', 'ds-secret', 1)"
    )
    await _reads(raw, "c-k", *reads)
    view = await _view(raw, "c-k", "ana")
    board = await _view(raw, "c-k", "ana", board=True)
    plan = await world.people.plan("ana", admin=ADMIN, scheme=SCHEME)
    assert {(i.id, i.needs_clearance) for i in plan.items} == {(view, highest), (board, highest)}
    below = "OFFICIAL" if highest != "OFFICIAL" else None
    cleared = _person("cal", EVERY, clearance=highest)
    people = [_person("ana", EVERY), cleared]
    if below is not None:
        people.append(_person("bea", EVERY, clearance=below))
        who = recipients(people, {}, {})
        for kind, item in (("view", view), ("board", board)):
            others = [OwnedTransfer(kind=i.kind, id=i.id, to="cal") for i in plan.items if i.id != item]
            with pytest.raises(DisableRefused) as refused:
                await world.people.transfer(
                    "ana", [*others, OwnedTransfer(kind=kind, id=item, to="bea")], who,
                    by=ADMIN, audit=world.audit, admin_unit=UNIT, scheme=SCHEME,
                )  # fmt: skip
            assert "not cleared to the marking it needs" in refused.value.words
            assert highest not in refused.value.words and SECRET_WORDS not in refused.value.words
        assert await _owners(raw) == {view: "ana", board: "ana"}
    who = recipients(people, {}, {})
    await world.people.transfer(
        "ana", [OwnedTransfer(kind=i.kind, id=i.id, to="cal") for i in plan.items], who,
        by=ADMIN, audit=world.audit, admin_unit=UNIT, scheme=SCHEME,
    )  # fmt: skip
    assert await _owners(raw) == {view: "cal", board: "cal"}
