"""A person's list schedules in *Disable…*'s plan and transfer, read by the lists' clearance (the
orchestrator's verification of lane/rules-lists at e911b90, item 2; ADR-146 Amendment 7 point 8;
rules 3 and 4).

The plan read every schedule the person owned by name, with no clearance filter, and a transfer
checked no list's marking. So an OFFICIAL administrator saw a SECRET list's name, and could hand
its schedule to an OFFICIAL person, whose scheduled refreshes then ran as someone not cleared for
it. Now the plan reads through `screening._admitted_sql`: a list the administrator is cleared for
by name, one they are not as "a list you can't see" under an id that names nothing; and a
schedule goes only to someone cleared for the list's classification and handling code
(`markings_hold`). Each case was shown red by a plant at its call site
(`process/lanes/rules/lists/AM7_RED_RECORD.txt`). Live: the real stores on a throwaway schema
(`test_custom_roles_store.world`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from services.api.admin_people import DisableRefused, recipients

from schemas.admin import OwnedTransfer
from schemas.domain import Principal
from tests.services.api.test_custom_roles_store import (  # noqa: F401 - `world` is a fixture
    ADMIN,
    SCHEME,
    UNIT,
    _person,
    world,
)

OFFICIAL_ADMIN = Principal(id="adm-o", clearance="OFFICIAL", org_unit=UNIT, roles=["osprey-admin"])
ENGINEER = ["analyst", "data_engineer"]
HIDDEN_LABEL = "The refresh schedule of a list you can't see"


async def _schedules(world: SimpleNamespace) -> None:
    """Ana sets the schedules of an unmarked list and of a SECRET one."""
    for name in ("Plain list", "Secret list"):
        await world.raw.execute(
            "INSERT INTO screening_lists (list_name, source, location, use_for, subscribed_by, "
            "subscribed_at, schedule_owner) VALUES ($1, 'csv', 'x', 'screening', 'ana', $2, 'ana')",
            name, datetime(2026, 11, 12, tzinfo=UTC),
        )  # fmt: skip
    await world.raw.execute(
        "INSERT INTO screening_list_markings (list_name, classification, handling_code) "
        "VALUES ('Secret list', 'SECRET', 'P')"
    )


async def test_the_plan_names_only_the_lists_its_administrator_is_cleared_for(world: SimpleNamespace) -> None:
    """Each way: the SECRET administrator is shown both lists by name; the OFFICIAL one the plain
    list by name and the other as one they can't see, its name nowhere in the plan. Red with the
    schedules read unfiltered: the OFFICIAL administrator was shown "Secret list"."""
    await _schedules(world)
    cleared = await world.people.plan("ana", admin=ADMIN, scheme=SCHEME)
    assert [(i.id, i.label) for i in cleared.items] == [
        ("Plain list", "The refresh schedule of the list Plain list"),
        ("Secret list", "The refresh schedule of the list Secret list"),
    ]
    official = await world.people.plan("ana", admin=OFFICIAL_ADMIN, scheme=SCHEME)
    assert [(i.id, i.label) for i in official.items] == [
        ("Plain list", "The refresh schedule of the list Plain list"),
        ("hidden-list-1", HIDDEN_LABEL),
    ]
    assert "Secret list" not in official.model_dump_json()


async def test_a_hidden_lists_schedule_goes_only_to_someone_cleared_for_it(world: SimpleNamespace) -> None:
    """The OFFICIAL administrator gives the hidden list's schedule to an OFFICIAL person: refused
    in words naming neither the list nor its marking, and nothing moved. To a SECRET person: moved,
    by the list's own name, which the administrator never saw. Red with no list marking checked:
    the OFFICIAL person was given it."""
    await _schedules(world)
    who = recipients([_person("bea", ENGINEER), _person("sam", ENGINEER, clearance="SECRET")], {}, {})
    plain = OwnedTransfer(kind="list_schedule", id="Plain list", to="bea")
    with pytest.raises(DisableRefused) as refused:
        await world.people.transfer(
            "ana", [plain, OwnedTransfer(kind="list_schedule", id="hidden-list-1", to="bea")], who,
            by=OFFICIAL_ADMIN, audit=world.audit, admin_unit=UNIT, scheme=SCHEME,
        )  # fmt: skip
    assert refused.value.words == f"{HIDDEN_LABEL}: bea is not cleared for the list; choose someone who is"
    assert "Secret" not in refused.value.words and "SECRET" not in refused.value.words
    owners = dict(await world.raw.fetch("SELECT list_name, schedule_owner FROM screening_lists"))
    assert owners == {"Plain list": "ana", "Secret list": "ana"}
    moved, _ = await world.people.transfer(
        "ana", [plain, OwnedTransfer(kind="list_schedule", id="hidden-list-1", to="sam")], who,
        by=OFFICIAL_ADMIN, audit=world.audit, admin_unit=UNIT, scheme=SCHEME,
    )  # fmt: skip
    assert [(i.id, to) for i, to in moved] == [("Plain list", "bea"), ("hidden-list-1", "sam")]
    owners = dict(await world.raw.fetch("SELECT list_name, schedule_owner FROM screening_lists"))
    assert owners == {"Plain list": "bea", "Secret list": "sam"}


async def test_a_lists_schedule_a_cleared_administrator_sees_still_goes_only_to_someone_cleared(
    world: SimpleNamespace,
) -> None:
    """The SECRET administrator sees the SECRET list, and still may not give its schedule to an
    OFFICIAL person (its refreshes would run as them). Red with `markings_hold` not reading the
    list's marking: given."""
    await _schedules(world)
    who = recipients([_person("bea", ENGINEER)], {}, {})
    transfers = [OwnedTransfer(kind="list_schedule", id=n, to="bea") for n in ("Plain list", "Secret list")]
    with pytest.raises(DisableRefused) as refused:
        await world.people.transfer("ana", transfers, who, by=ADMIN, audit=world.audit,
                                    admin_unit=UNIT, scheme=SCHEME)  # fmt: skip
    assert refused.value.words == (
        "The refresh schedule of the list Secret list: bea is not cleared for the list; choose someone who is")  # fmt: skip
