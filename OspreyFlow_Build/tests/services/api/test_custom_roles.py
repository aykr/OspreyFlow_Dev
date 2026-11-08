"""Custom roles' and teams' rules, as functions (ADR-145 decision 7 and Amendment 5; ADR-112
Amendments 4 and 5). The routes that call them are `test_admin_roles_routes.py`'s; each refusal is
shown red there, at the route, with its check removed (`L2.5_RED_RECORD.md`).

The owner's answer to L2.5 Q3b is pending: (a) is built. `giver_may_give` alone decides it, and the
three cases below say what each answer decides; the two not built are `xfail(strict=True)`, so
changing the answer is the function and the markers.
"""

from __future__ import annotations

from datetime import date

import pytest
from services.api.custom_roles import (
    RoleRefused,
    acting_lead,
    expand,
    giver_may_give,
    leaves_no_people_manager,
    people_managers,
    role_refusal,
)

from schemas.admin import PersonAccount, Team
from schemas.domain import Principal
from schemas.rights import ROLE_RIGHTS, Right, rights_for

ADMIN = rights_for(["osprey-admin"])
PEOPLE_ONLY = frozenset({Right.MANAGE_PEOPLE})


def _refused(error: str, name: str = "Desk", rights: list[str] | None = None,
             giver: frozenset[Right] = ADMIN, taken: tuple[str, ...] = ()) -> RoleRefused:  # fmt: skip
    with pytest.raises(RoleRefused) as raised:
        role_refusal(name, ["investigate"] if rights is None else rights, giver_rights=giver,
                     names_taken=taken)  # fmt: skip
    assert raised.value.error == error, raised.value.words
    return raised.value


def test_a_name_already_used_is_refused_case_and_spacing_aside() -> None:
    _refused("name_taken", name="  intel   DESK ", taken=("Intel desk",))
    _refused("name_taken", name="Analyst")
    _refused("name_taken", name="super user")


def test_no_rights_is_refused() -> None:
    _refused("no_rights", rights=[])


def test_a_right_that_is_not_one_is_refused() -> None:
    assert _refused("unknown_right", rights=["investigate", "fly"]).detail["rights"] == ["fly"]


@pytest.mark.parametrize("pair", [("promote_to_dataset", "review_promotions"),
                                  ("propose_types", "accept_types")])  # fmt: skip
def test_both_rights_of_a_propose_and_approve_pair_are_refused(pair: tuple[str, str]) -> None:
    assert _refused("forbidden_pair", rights=["investigate", *pair]).detail["pair"] == list(pair)


def test_each_half_of_a_pair_alone_is_accepted() -> None:
    for half in ("promote_to_dataset", "review_promotions", "propose_types", "accept_types"):
        assert role_refusal("Desk", [half], giver_rights=ADMIN, names_taken=()) == [Right(half)]


def test_a_role_has_exactly_the_rights_given_once_each() -> None:
    assert role_refusal("Desk", ["run_analysis", "investigate", "investigate"], giver_rights=ADMIN,
                        names_taken=()) == [Right.INVESTIGATE, Right.RUN_ANALYSIS]  # fmt: skip


# --- L2.5 Q3b: which rights a giver must hold (pending the owner; (a) built) ---------------------


def test_q3b_a_an_administration_right_needs_its_holder() -> None:
    """(a): `administer_system` only from someone who holds it; any other right from anyone."""
    assert not giver_may_give(Right.ADMINISTER_SYSTEM, PEOPLE_ONLY)
    assert giver_may_give(Right.ADMINISTER_SYSTEM, ADMIN)
    assert giver_may_give(Right.INVESTIGATE, PEOPLE_ONLY)
    _refused("beyond_your_rights", rights=["administer_system"], giver=PEOPLE_ONLY)


@pytest.mark.xfail(strict=True, reason="L2.5 Q3b (b), not the answer built")
def test_q3b_b_no_right_needs_its_holder() -> None:
    assert giver_may_give(Right.ADMINISTER_SYSTEM, PEOPLE_ONLY)


@pytest.mark.xfail(strict=True, reason="L2.5 Q3b (c), not the answer built")
def test_q3b_c_every_right_needs_its_holder() -> None:
    assert not giver_may_give(Right.INVESTIGATE, ADMIN)


def test_an_administrator_may_bundle_an_analysts_rights() -> None:
    """Why (c) was questioned: the Admin role holds none of the Analyst's rights."""
    assert role_refusal("Desk", sorted(r.value for r in ROLE_RIGHTS["analyst"]),
                        giver_rights=ADMIN, names_taken=())  # fmt: skip


# --- the lock-out (ADR-145 Amendment 5) -----------------------------------------------------------


def _person(pid: str, roles: list[str], *, enabled: bool = True, system: bool = False) -> PersonAccount:
    return PersonAccount(id=pid, username=pid, name=pid, enabled=enabled, roles=roles,
                         system_account=system)  # fmt: skip


def test_only_enabled_people_count_as_people_managers() -> None:
    people = [_person("a", ["osprey-admin"], enabled=False), _person("b", ["role:r1"]),
              _person("c", ["osprey-admin"], system=True)]  # fmt: skip
    assert people_managers(people, {"r1": [Right.MANAGE_PEOPLE]}) == ["b"]
    assert people_managers(people, {"r1": [Right.INVESTIGATE]}) == []


def test_a_change_leaving_no_people_manager_is_refused() -> None:
    people = [_person("b", ["role:r1"]), _person("d", ["analyst"])]
    with pytest.raises(RoleRefused) as raised:
        leaves_no_people_manager(people, {"r1": [Right.INVESTIGATE]})
    assert raised.value.error == "locks_out_administrators"
    leaves_no_people_manager(people, {"r1": [Right.MANAGE_PEOPLE]})


# --- a custom role in a request -------------------------------------------------------------------


def test_a_custom_role_adds_exactly_its_current_rights_and_keeps_its_name() -> None:
    who = Principal(id="p", clearance="OFFICIAL", org_unit="u", roles=["role:r1", "reports_viewer"])
    expanded = expand(who, {"r1": frozenset({Right.RUN_ANALYSIS})})
    assert "role:r1" in expanded.roles
    assert rights_for(expanded.roles) == rights_for(["reports_viewer"]) | {Right.RUN_ANALYSIS}
    assert expand(who, {}).roles == who.roles


# --- the acting lead (ADR-112 Amendment 5 decision 4, ADR-146 Amendment 1) -----------------------


def test_the_cover_acts_through_their_last_day_and_then_the_lead_again() -> None:
    team = Team(role_id="r1", display_name="Intel", mailbox="intel@example.org", lead="lead",
                cover="cover", cover_until=date(2026, 11, 14))  # fmt: skip
    assert acting_lead(team, date(2026, 11, 14)) == "cover"
    assert acting_lead(team, date(2026, 11, 15)) == "lead"
    assert acting_lead(team.model_copy(update={"cover": None}), date(2026, 11, 1)) == "lead"
