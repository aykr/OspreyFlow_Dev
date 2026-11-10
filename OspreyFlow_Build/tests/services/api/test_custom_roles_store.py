"""L2.5's stores on real Postgres (ADR-145 Amendment 5; ADR-112 Amendments 4 and 5): custom roles and
their versions, a team's level in a case gained and lost with membership, the People rows, and
*Disable…*'s plan and transfers in one transaction. A fresh schema per test, the other lanes' own
stores connected so their tables are exactly as their code makes them.

Each is shown red at its real call site (`process/lanes/admin/L2.5_RED_RECORD.md`):
- a person's team grants read once and kept (`investigations.grant_subjects` cached by account):
  `test_a_teams_level_is_gained_and_lost_with_membership`;
- a transfer skipping one kind of item: `test_disable_moves_every_item_and_audits_each`;
- a refused transfer leaving part of it written: `test_a_refused_transfer_changes_nothing`;
- the rows reading another unit's grants: `test_the_rows_name_levels_through_a_team_and_cases_with_no_author`;
- a hotlist named by what it watches for:
  `test_the_plan_lists_every_kind_owned_today_and_not_a_shared_case`.
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
from services.api.custom_roles import CustomRoleStore, RoleRefused
from services.api.datasets import PostgresDatasetStore
from services.api.hotlists import HotlistStore
from services.api.investigations import AccessLevel, InvestigationNotFoundError, InvestigationStore
from services.api.link_type_store import LinkTypeProposalStore
from services.api.monitors import MonitorStore
from services.api.pattern_store import PatternStore
from services.api.screening import ScreeningListStore
from services.api.studio_recipes import StudioRecipeStore
from services.api.typology_rules import TypologyRuleStore

from ontology.handling import load_uk_le_scheme
from schemas.admin import OwnedTransfer, PersonAccount, TeamInput
from schemas.domain import Principal
from schemas.rights import Right

T0 = datetime(2026, 11, 8, tzinfo=UTC)
UNIT = "unit-1"
ADMIN = Principal(id="adm-1", clearance="SECRET", org_unit=UNIT, roles=["osprey-admin"])
SCHEME = load_uk_le_scheme()


def _who(pid: str, roles: list[str]) -> Principal:
    return Principal(id=pid, clearance="SECRET", org_unit=UNIT, roles=roles)


@pytest.fixture
async def world() -> AsyncIterator[SimpleNamespace]:
    name = "l25_" + uuid.uuid4().hex[:10]
    base = PostgresConfig.from_env().dsn
    conn = await asyncpg.connect(dsn=base)
    await conn.execute(f'CREATE SCHEMA "{name}"')
    await conn.close()
    dsn = f"{base}?search_path={name}"
    stores = [
        await InvestigationStore.connect(dsn), await PostgresDatasetStore.connect(dsn),
        await HotlistStore.connect(dsn), await MonitorStore.connect(dsn),
        await PatternStore.connect(dsn), await TypologyRuleStore.connect(dsn),
        await ScreeningListStore.connect(dsn), await StudioRecipeStore.connect(dsn),
        # L2.5b: the plan reads L3.8's kinds, so the case lane's tables are made by their stores.
        await PostgresCaseViewStore.connect(dsn), await PostgresBoardItemStore.connect(dsn),
        await LinkTypeProposalStore.connect(dsn),
        await AuditWriter.connect(dsn),
    ]  # fmt: skip
    roles = await CustomRoleStore.connect(dsn)
    people = await AdminPeopleStore.connect(dsn)
    raw = await asyncpg.connect(dsn=dsn)
    yield SimpleNamespace(cases=stores[0], audit=stores[-1], roles=roles, people=people, raw=raw)
    await raw.close()
    for store in [*stores, roles, people]:
        await store.close()
    conn = await asyncpg.connect(dsn=base)
    await conn.execute(f'DROP SCHEMA "{name}" CASCADE')
    await conn.close()


# --- custom roles -----------------------------------------------------------------------------------


async def test_a_role_is_versioned_and_its_rights_are_read_as_they_are_now(world: SimpleNamespace) -> None:
    made = await world.roles.create("Intel desk", [Right.INVESTIGATE], by="adm-1")
    assert made.version == 1
    before, after = await world.roles.update(made.id, "Intel desk", [Right.READ_REPORTS], by="adm-2")
    assert (before.version, after.version) == (1, 2)
    assert [v.rights for v in await world.roles.versions(made.id)] == [[Right.INVESTIGATE],
                                                                      [Right.READ_REPORTS]]  # fmt: skip
    expanded = await world.roles.expand(_who("p", [f"role:{made.id}"]))
    assert "right:read_reports" in expanded.roles and "right:investigate" not in expanded.roles


async def test_the_store_refuses_a_second_role_of_the_same_name(world: SimpleNamespace) -> None:
    """The route's check reads names first; two at once still meet the store's own key."""
    await world.roles.create("Intel desk", [Right.INVESTIGATE], by="adm-1")
    with pytest.raises(RoleRefused) as raised:
        await world.roles.create("  intel   DESK", [Right.INVESTIGATE], by="adm-1")
    assert raised.value.error == "name_taken"


# --- a team's level in a case ---------------------------------------------------------------------


async def test_a_teams_level_is_gained_and_lost_with_membership(world: SimpleNamespace) -> None:
    role = await world.roles.create("Intel desk", [Right.INVESTIGATE], by="adm-1")
    await world.roles.make_team(role.id, TeamInput(display_name="Intel", mailbox="i@example.org"),
                                date(2026, 11, 8))  # fmt: skip
    author = _who("alice", [])
    case = await world.cases.create(author, name="Kestrel")
    await world.cases.set_grant(case.id, f"team:{role.id}", AccessLevel.EDITOR, by=author)
    member = _who("bob", [f"role:{role.id}"])
    assert await world.cases.effective_level(case.id, member) is AccessLevel.EDITOR
    assert [c.id for c, _ in await world.cases.list_for(member)] == [case.id]
    await world.cases.get_authorized(case.id, member, need=AccessLevel.EDITOR)
    left = _who("bob", [])
    assert await world.cases.effective_level(case.id, left) is None
    assert await world.cases.list_for(left) == []
    with pytest.raises(InvestigationNotFoundError):
        await world.cases.get_authorized(case.id, left, need=AccessLevel.VIEWER)


async def test_a_persons_level_is_the_highest_they_hold_in_their_name_or_a_teams(
    world: SimpleNamespace,
) -> None:
    author = _who("alice", [])
    case = await world.cases.create(author, name="Kestrel")
    await world.cases.set_grant(case.id, "team:r9", AccessLevel.AUTHOR, by=author)
    await world.cases.set_grant(case.id, "bob", AccessLevel.VIEWER, by=author)
    assert await world.cases.effective_level(case.id, _who("bob", ["role:r9"])) is AccessLevel.AUTHOR
    assert await world.cases.effective_level(case.id, _who("bob", [])) is AccessLevel.VIEWER


# --- the People rows --------------------------------------------------------------------------------


def _person(pid: str, roles: list[str], *, enabled: bool = True, system: bool = False,
            unit: str = UNIT) -> PersonAccount:  # fmt: skip
    return PersonAccount(id=pid, username=pid, name=pid, enabled=enabled, roles=roles,
                         system_account=system, org_unit=unit)  # fmt: skip


async def test_the_rows_name_levels_through_a_team_and_cases_with_no_author(
    world: SimpleNamespace,
) -> None:
    role = await world.roles.create("Intel desk", [Right.INVESTIGATE], by="adm-1")
    await world.roles.make_team(role.id, TeamInput(display_name="Intel", mailbox="i@example.org"),
                                date(2026, 11, 8))  # fmt: skip
    alice, gone = _who("alice", []), _who("gone", [])
    kestrel = await world.cases.create(alice, name="Kestrel")
    await world.cases.set_grant(kestrel.id, f"team:{role.id}", AccessLevel.EDITOR, by=alice)
    orphan = await world.cases.create(gone, name="Heron")
    other_unit = await world.cases.create(Principal(id="zed", clearance="SECRET", org_unit="unit-2"),
                                          name="Elsewhere")  # fmt: skip
    rows = await world.people.rows(
        # zed, of another unit, is in the realm's people: their case must still not be named.
        [_person("alice", []), _person("bob", [f"role:{role.id}"]), _person("gone", [], enabled=False),
         _person("zed", [])],
        unit=UNIT,
    )
    by_id = {r.id: r for r in rows.rows}
    assert [(lv.name, lv.level, lv.through) for lv in by_id["bob"].levels] == [("Kestrel", "editor", "Intel")]
    assert [(lv.name, lv.level) for lv in by_id["alice"].levels] == [("Kestrel", "author")]
    assert [c.name for c in rows.without_author] == ["Heron"]
    named = {lv.investigation_id for r in rows.rows for lv in r.levels} | {
        c.investigation_id for c in rows.without_author}
    assert other_unit.id not in named and orphan.id in named


# --- Disable… ---------------------------------------------------------------------------------------


async def _owns_one_of_each(world: SimpleNamespace, role_id: str) -> dict[str, str]:
    raw, ana = world.raw, _who("ana", [])
    case = await world.cases.create(ana, name="Kestrel")
    shared = await world.cases.create(ana, name="Shared")
    await world.cases.set_grant(shared.id, "bea", AccessLevel.AUTHOR, by=ana)
    await raw.execute("INSERT INTO hotlists (id, identifier, owner_id, review_date, created_at) "
                      "VALUES ('h1', '07700 900123', 'ana', '2026-12-01', $1)", T0)  # fmt: skip
    await raw.execute("INSERT INTO monitors (id, pattern_id, owner_id, created_at) "
                      "VALUES ('m1', 'p1', 'ana', $1)", T0)  # fmt: skip
    await raw.execute("INSERT INTO saved_patterns (id, pattern_id, version, name, owner_id, created_at, "
                      "definition) VALUES ('s1', 'p1', 1, 'Fan-out', 'ana', $1, '{}'), "
                      "('s2', 'p1', 2, 'Fan-out', 'ana', $1, '{}')", T0)  # fmt: skip
    await raw.execute("INSERT INTO typology_rules (id, investigation_id, owner_id, name, params, trigger, "
                      "budget_ms, created_at) VALUES ('t1', $1, 'ana', 'Structuring', '{}', 'load', 100, $2)",
                      case.id, T0)  # fmt: skip
    await raw.execute("INSERT INTO studio_recipes (recipe_id, version, label, status, content, owning_unit, "
                      "created_by, created_at, schedule_owner) VALUES ('feed', 1, 'Custody', 'published', "
                      "'', $1, 'ana', $2, 'ana')", UNIT, T0)  # fmt: skip
    await raw.execute("INSERT INTO screening_lists (list_name, source, location, use_for, subscribed_by, "
                      "subscribed_at, schedule_owner) VALUES ('ofsi', 'csv', 'x', 'screening', 'ana', $1, 'ana')",
                      T0)  # fmt: skip
    await raw.execute("UPDATE teams SET lead = 'ana' WHERE role_id = $1", role_id)
    return {"case": case.id, "shared": shared.id}


def _directory(role_id: str) -> list[PersonAccount]:
    every = ["analyst", "data_engineer", "right:keep_watches", f"role:{role_id}"]
    return [_person("ana", every), _person("bea", every), _person("robot", every, system=True),
            _person("viewer", ["reports_viewer", f"role:{role_id}"])]  # fmt: skip


async def _team(world: SimpleNamespace) -> str:
    role = await world.roles.create("Intel desk", [Right.INVESTIGATE], by="adm-1")
    await world.roles.make_team(role.id, TeamInput(display_name="Intel", mailbox="i@example.org"),
                                date(2026, 11, 8))  # fmt: skip
    return str(role.id)


async def test_the_plan_lists_every_kind_owned_today_and_not_a_shared_case(world: SimpleNamespace) -> None:
    role_id = await _team(world)
    ids = await _owns_one_of_each(world, role_id)
    plan = await world.people.plan("ana", admin=ADMIN, scheme=SCHEME)
    assert sorted((i.kind, i.id) for i in plan.items) == sorted([
        ("case_author", ids["case"]), ("team_lead", role_id), ("hotlist", "h1"), ("monitor", "m1"),
        ("saved_pattern", "p1"), ("typology_rule", "t1"), ("pipeline_schedule", "feed"),
        ("list_schedule", "ofsi")])  # fmt: skip
    assert not any("07700" in i.label for i in plan.items), "a hotlist's identifier is never named"
    assert plan.not_yet_listed == ["promotions waiting for review", "reviews waiting on them"]


async def test_disable_moves_every_item_and_audits_each(world: SimpleNamespace) -> None:
    role_id = await _team(world)
    ids = await _owns_one_of_each(world, role_id)
    plan = await world.people.plan("ana", admin=ADMIN, scheme=SCHEME)
    who = recipients(_directory(role_id), {}, {role_id: frozenset({"ana", "bea"})})
    transfers = [OwnedTransfer(kind=i.kind, id=i.id, to="bea") for i in plan.items]
    moved, left = await world.people.transfer("ana", transfers, who, by=ADMIN, audit=world.audit,
                                              admin_unit=UNIT, scheme=SCHEME)  # fmt: skip
    assert len(moved) == len(plan.items) == 8 and left == 0
    raw = world.raw
    owners = {
        "hotlist": await raw.fetchval("SELECT owner_id FROM hotlists WHERE id = 'h1'"),
        "monitor": await raw.fetchval("SELECT owner_id FROM monitors WHERE id = 'm1'"),
        "patterns": await raw.fetch("SELECT DISTINCT owner_id FROM saved_patterns"),
        "rule": await raw.fetchval("SELECT owner_id FROM typology_rules WHERE id = 't1'"),
        "feed": await raw.fetchval("SELECT schedule_owner FROM studio_recipes WHERE recipe_id = 'feed'"),
        "list": await raw.fetchval("SELECT schedule_owner FROM screening_lists WHERE list_name = 'ofsi'"),
        "lead": await raw.fetchval("SELECT lead FROM teams WHERE role_id = $1", role_id),
    }
    assert owners["patterns"] and [r["owner_id"] for r in owners["patterns"]] == ["bea"]
    assert {k: v for k, v in owners.items() if k != "patterns"} == dict.fromkeys(
        ["hotlist", "monitor", "rule", "feed", "list", "lead"], "bea")
    grants = await world.cases.list_grants(ids["case"])
    assert grants == {"ana": AccessLevel.AUTHOR, "bea": AccessLevel.AUTHOR}, "nothing is deleted"
    audited = await raw.fetch("SELECT resolved_query FROM audit_log WHERE action = 'transfer_owned_item'")
    assert len(audited) == 8
    assert (await world.people.plan("ana", admin=ADMIN, scheme=SCHEME)).items == []


async def test_a_refused_transfer_changes_nothing(world: SimpleNamespace) -> None:
    role_id = await _team(world)
    await _owns_one_of_each(world, role_id)
    plan = await world.people.plan("ana", admin=ADMIN, scheme=SCHEME)
    who = recipients(_directory(role_id), {}, {role_id: frozenset({"ana", "bea"})})
    # Every item to bea but the rule, which goes to someone without deploy_rules.
    transfers = [OwnedTransfer(kind=i.kind, id=i.id, to="viewer" if i.kind == "typology_rule" else "bea")
                 for i in plan.items]  # fmt: skip
    with pytest.raises(DisableRefused) as raised:
        await world.people.transfer("ana", transfers, who, by=ADMIN, audit=world.audit, admin_unit=UNIT, scheme=SCHEME)
    assert raised.value.error == "recipient_refused" and "deploy_rules" in raised.value.words
    assert await world.raw.fetchval("SELECT owner_id FROM hotlists WHERE id = 'h1'") == "ana"
    assert await world.raw.fetchval("SELECT count(*) FROM audit_log") == 0
    with pytest.raises(DisableRefused) as untransferred:
        await world.people.transfer("ana", transfers[:-1], who, by=ADMIN, audit=world.audit,
                                    admin_unit=UNIT, scheme=SCHEME)  # fmt: skip
    assert untransferred.value.error == "untransferred"
    assert await world.raw.fetchval("SELECT lead FROM teams WHERE role_id = $1", role_id) == "ana"


async def test_a_lead_is_handed_to_a_member_only(world: SimpleNamespace) -> None:
    role_id = await _team(world)
    await world.raw.execute("UPDATE teams SET lead = 'ana' WHERE role_id = $1", role_id)
    who = recipients(_directory(role_id), {}, {role_id: frozenset({"ana", "bea"})})
    with pytest.raises(DisableRefused) as raised:
        await world.people.transfer("ana", [OwnedTransfer(kind="team_lead", id=role_id, to="viewer")],
                                    who, by=ADMIN, audit=world.audit, admin_unit=UNIT, scheme=SCHEME)  # fmt: skip
    assert "not a member" in raised.value.words


async def test_the_cover_ends_on_its_day_and_the_lead_acts_again(world: SimpleNamespace) -> None:
    role_id = await _team(world)
    await world.roles.set_lead(role_id, "ana", date(2026, 11, 8))
    await world.roles.set_cover(role_id, "bea", date(2026, 11, 14), date(2026, 11, 8))
    assert (await world.roles.team(role_id, date(2026, 11, 14))).acting_lead == "bea"
    assert (await world.roles.team(role_id, date(2026, 11, 15))).acting_lead == "ana"
    _, handed = await world.roles.set_lead(role_id, "bea", date(2026, 11, 9))
    assert (handed.lead, handed.cover) == ("bea", None), "a cover who becomes lead stops covering"


# --- the lane review's findings ----------------------------------------------------------------------


async def test_two_units_each_transfer_their_share_and_only_then_is_nothing_left(
    world: SimpleNamespace,
) -> None:
    """Rule 3: another unit's case is counted in SQL, never read. A person owning cases in two
    units has each unit's share transferred by that unit's administrator; until both have, the
    transfer answers what is left elsewhere, and the covers stay."""
    ana_1, ana_2 = _who("ana", []), Principal(id="ana", clearance="SECRET", org_unit="unit-2")
    here = await world.cases.create(ana_1, name="Here")
    there = await world.cases.create(ana_2, name="There")
    from services.api.admin_people import _plan_items

    async with world.people._pool.acquire() as conn:
        listed = await _plan_items(conn, "ana", UNIT, cleared=list(SCHEME.classification),
                                    top=SCHEME.classification[-1])
    assert listed.elsewhere == 1 and [i.id for i in listed.items] == [here.id]
    directory = [_person("bea", ["analyst"]), _person("bob", ["analyst"], unit="unit-2")]
    who = recipients(directory, {}, {})
    moved, left = await world.people.transfer(
        "ana", [OwnedTransfer(kind="case_author", id=here.id, to="bea")], who, by=ADMIN,
        audit=world.audit, admin_unit=UNIT, scheme=SCHEME)  # fmt: skip
    assert (len(moved), left) == (1, 1)
    admin_2 = Principal(id="adm-9", clearance="SECRET", org_unit="unit-2", roles=["osprey-admin"])
    moved, left = await world.people.transfer(
        "ana", [OwnedTransfer(kind="case_author", id=there.id, to="bob")], who, by=admin_2,
        audit=world.audit, admin_unit="unit-2", scheme=SCHEME)  # fmt: skip
    assert (len(moved), left) == (1, 0)
    assert (await world.cases.list_grants(there.id))["bob"] is AccessLevel.AUTHOR


async def test_a_rule_goes_only_to_an_author_of_its_case(world: SimpleNamespace) -> None:
    role_id = await _team(world)
    ids = await _owns_one_of_each(world, role_id)
    plan = await world.people.plan("ana", admin=ADMIN, scheme=SCHEME)
    # The case to cas, who is not bea; the rule of that case to bea, who is no Author of it.
    directory = [*_directory(role_id), _person("cas", ["analyst"])]
    who = recipients(directory, {}, {role_id: frozenset({"ana", "bea"})})
    transfers = [OwnedTransfer(kind=i.kind, id=i.id, to="cas" if i.kind == "case_author" else "bea")
                 for i in plan.items]  # fmt: skip
    with pytest.raises(DisableRefused) as raised:
        await world.people.transfer("ana", transfers, who, by=ADMIN, audit=world.audit, admin_unit=UNIT, scheme=SCHEME)
    assert raised.value.error == "recipient_refused" and "not an Author of its case" in raised.value.words
    # With bea an Author of the case, ana is no longer its only Author: the plan drops the case,
    # and the rule may go to bea.
    await world.cases.set_grant(ids["case"], "bea", AccessLevel.AUTHOR, by=_who("ana", []))
    again = await world.people.plan("ana", admin=ADMIN, scheme=SCHEME)
    assert "case_author" not in {i.kind for i in again.items}
    moved, _ = await world.people.transfer(
        "ana", [OwnedTransfer(kind=i.kind, id=i.id, to="bea") for i in again.items], who,
        by=ADMIN, audit=world.audit, admin_unit=UNIT, scheme=SCHEME)  # fmt: skip
    assert len(moved) == len(again.items)


async def test_a_watch_never_goes_to_someone_already_watching_its_pattern(
    world: SimpleNamespace,
) -> None:
    await world.raw.execute("INSERT INTO monitors (id, pattern_id, owner_id, created_at) VALUES "
                            "('m1', 'p1', 'ana', $1), ('m2', 'p1', 'bea', $1)", T0)  # fmt: skip
    who = recipients(_directory("r0"), {}, {})
    with pytest.raises(DisableRefused) as raised:
        await world.people.transfer("ana", [OwnedTransfer(kind="monitor", id="m1", to="bea")], who,
                                    by=ADMIN, audit=world.audit, admin_unit=UNIT, scheme=SCHEME)  # fmt: skip
    assert "already watches" in raised.value.words
    assert await world.raw.fetchval("SELECT owner_id FROM monitors WHERE id = 'm1'") == "ana"


async def test_the_persons_covers_end_with_the_disable_and_are_audited(world: SimpleNamespace) -> None:
    role_id = await _team(world)
    await world.roles.set_lead(role_id, "bea", date(2026, 11, 8))
    await world.roles.set_cover(role_id, "ana", date(2026, 11, 30), date(2026, 11, 8))
    _, left = await world.people.transfer("ana", [], recipients(_directory(role_id), {}, {}),
                                          by=ADMIN, audit=world.audit, admin_unit=UNIT, scheme=SCHEME)  # fmt: skip
    assert left == 0
    assert (await world.roles.team(role_id, date(2026, 11, 9))).cover == "ana", (
        "the transfer ends no cover: the route ends them once the disable goes ahead (L2.5b)"
    )
    await world.people.end_covers("ana", by=ADMIN, audit=world.audit)
    team = await world.roles.team(role_id, date(2026, 11, 9))
    assert (team.cover, team.acting_lead) == (None, "bea")
    assert await world.raw.fetchval("SELECT count(*) FROM audit_log WHERE action = 'set_team_cover'") == 1


async def test_a_write_that_finds_its_item_changed_rolls_every_transfer_back(
    world: SimpleNamespace,
) -> None:
    """`changed_meanwhile`: an owner column already moved by the time its UPDATE runs (a concurrent
    transfer) leaves every earlier write of the same transaction undone."""
    role_id = await _team(world)
    await _owns_one_of_each(world, role_id)
    plan = await world.people.plan("ana", admin=ADMIN, scheme=SCHEME)
    who = recipients(_directory(role_id), {}, {role_id: frozenset({"ana", "bea"})})
    transfers = [OwnedTransfer(kind=i.kind, id=i.id, to="bea") for i in plan.items]
    # The list schedule is the last item written; another session moves it first, after the plan
    # is read inside the transfer's own transaction (a trigger stands in for that session).
    await world.raw.execute(
        "CREATE FUNCTION steal() RETURNS trigger AS $$ BEGIN "
        "UPDATE screening_lists SET schedule_owner = 'zed' WHERE list_name = 'ofsi'; RETURN NEW; END "
        "$$ LANGUAGE plpgsql; CREATE TRIGGER steal AFTER UPDATE ON studio_recipes "
        "FOR EACH ROW EXECUTE FUNCTION steal()")  # fmt: skip
    with pytest.raises(DisableRefused) as raised:
        await world.people.transfer("ana", transfers, who, by=ADMIN, audit=world.audit, admin_unit=UNIT, scheme=SCHEME)
    assert raised.value.error == "changed_meanwhile"
    assert await world.raw.fetchval("SELECT owner_id FROM hotlists WHERE id = 'h1'") == "ana"
    assert await world.raw.fetchval("SELECT count(*) FROM audit_log") == 0


# --- round 2 of the independent review --------------------------------------------------------------


async def test_a_case_whose_other_author_answers_for_nothing_is_still_the_persons_to_transfer(
    world: SimpleNamespace,
) -> None:
    """Finding 6: a disabled Author, or a team whose only member is the person, leaves the case
    the person's alone; an enabled Author of the unit does not."""
    role_id = await _team(world)
    ana = _who("ana", [])
    left = await world.cases.create(ana, name="Left by a leaver")
    await world.cases.set_grant(left.id, "gone", AccessLevel.AUTHOR, by=ana)
    teamed = await world.cases.create(ana, name="Only through ana's team")
    await world.cases.set_grant(teamed.id, f"team:{role_id}", AccessLevel.AUTHOR, by=ana)
    shared = await world.cases.create(ana, name="Shared")
    await world.cases.set_grant(shared.id, "bea", AccessLevel.AUTHOR, by=ana)
    people = [_person("ana", [f"role:{role_id}"]), _person("bea", ["analyst"]),
              _person("gone", ["analyst"], enabled=False)]  # fmt: skip
    plan = await world.people.plan("ana", admin=ADMIN, scheme=SCHEME, people=people)
    listed = {i.id for i in plan.items if i.kind == "case_author"}
    assert listed == {left.id, teamed.id}


async def test_two_teams_never_share_a_name(world: SimpleNamespace) -> None:
    first = await world.roles.create("Intel desk", [Right.INVESTIGATE], by="adm-1")
    second = await world.roles.create("Intel desk two", [Right.INVESTIGATE], by="adm-1")
    await world.roles.make_team(first.id, TeamInput(display_name="Intel", mailbox="i@example.org"),
                                date(2026, 11, 8))  # fmt: skip
    with pytest.raises(RoleRefused) as raised:
        await world.roles.make_team(second.id, TeamInput(display_name=" intel ", mailbox="j@example.org"),
                                    date(2026, 11, 8))  # fmt: skip
    assert raised.value.error == "team_name_taken"


async def test_the_people_lock_lets_one_holder_in_at_a_time(world: SimpleNamespace) -> None:
    """Finding 3: the advisory lock itself, across two connections (two replicas alike)."""
    import asyncio

    order: list[str] = []

    async def hold(name: str, wait: float) -> None:
        async with world.roles.people_lock():
            order.append(f"{name} in")
            await asyncio.sleep(wait)
            order.append(f"{name} out")

    await asyncio.gather(hold("a", 0.3), hold("b", 0.0))
    assert order in (["a in", "a out", "b in", "b out"], ["b in", "b out", "a in", "a out"])
