"""Admin › People's reads and *Disable…* with transfers (`06_DECISIONS.md` ADR-145 decision 6:
R1, R3, A4; ADR-112 Amendment 5 decision 4).

**The rows** (`rows`, R3 and R1): each person's levels in the cases of the administrator's own
unit, their own and through a team, and the cases with no Author an enabled person holds, of that
unit only, which is the safety net's reach (ADR-052 §6): never another unit's case or its members.

**What a person owns today, on main** (`plan`), each needing a *Transfer to…* before *Transfer and
disable* is accepted: cases where they are the only Author, their dataset's home case among them
(the dataset's Authors, ADR-145 Amendment 4 decision 3); teams they lead; their active hotlists,
watches (saved-pattern monitors) and saved patterns; their active typology rules, whose scheduled
runs act as them (ADR-133 stage (d)); and the pipeline and screening-list schedules whose runs act
as them (ADR-110 decision 3).

**What the case lane keeps** (`l38_owned_items`, L2.5b): the views and boards they made, their
link-type proposals waiting for a decision and their open drawn-item watches, read by L3.8's own SQL
(`person_ownership.owned_items`) in the administrator's unit and within the markings they clear
(ADR-145 Amendment 8). An item they may not see is never offered: *Transfer and disable* is refused
for it after the visible transfers commit (409 `withheld_items`, `refuse_if_withheld`), naming
nothing. Promotions waiting for review, and reviews waiting on them, are still named as not yet
listed (`L38_OWNED_KINDS`, L3.4's seam `person_ownership.promotion_items`).

**Refused, in words, while any item is untransferred** (409 `untransferred`), or given to someone
who cannot take it (409 `recipient_refused`: the person themselves, a disabled account, an account
the directory does not hold as a person, a service account, a team's lead who is not a member, or
someone without the right the item's runs are checked against). Nothing is deleted: a case gains
its new Author and keeps every grant it had; every other item changes its owner. All the transfers
are one Postgres transaction, written with the audit entry of each (`transfer_owned_item`), before
the identity provider disables the account.

This module writes to tables the rules and Studio lanes own (`hotlists`, `monitors`,
`saved_patterns`, `typology_rules`, `studio_recipes`, `screening_lists`) and the case lane's
`investigation_grants`, because the transfers must commit together; each statement names the
owner column it changes and nothing else.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, cast

import asyncpg

from ontology.handling import HandlingScheme
from schemas.admin import (
    AdminPeopleRows,
    AdminPersonRow,
    CaseWithoutAuthor,
    ConvertedViews,
    DisablePlan,
    OwnedItem,
    OwnedTransfer,
    PersonAccount,
    PersonCaseLevel,
)
from schemas.domain import Principal
from schemas.rights import CUSTOM_ROLE_PREFIX, Right, rights_for

from .audit import AuditWriter
from .entra_people import STALE_ACCESS_WORDS, access_current
from .investigations import TEAM_GRANT_PREFIX, AccessLevel, InvestigationStore
from .screening import ListClearance, _admitted_sql, _markings_join

#: The kinds a person owns that the plan cannot list yet (L3.4's promotions, through L3.8's seam).
#: Said in the plan, so an administrator is never told the list is whole.
L38_OWNED_KINDS: tuple[str, ...] = ("promotions waiting for review", "reviews waiting on them")

#: The rights an item's runs, or its own routes, are checked against, which its recipient must hold
#: (`scheduler.py`, `rule_schedule.py`, `list_schedule.py`; the watches' and hotlists'
#: `keep_watches`; for L3.8's kinds, the view's save (`investigate`), the boards' `_DRAWS` and the
#: proposal route's `propose_types`).
NEEDS: Mapping[str, tuple[Right, ...]] = {
    "typology_rule": (Right.DEPLOY_RULES,),
    "pipeline_schedule": (Right.SCHEDULE_PIPELINES,),
    "list_schedule": (Right.LOAD_SCREENING_LISTS,),
    "hotlist": (Right.KEEP_WATCHES,),
    "monitor": (Right.KEEP_WATCHES,),
    "saved_pattern": (Right.KEEP_WATCHES,),
    "view": (Right.INVESTIGATE,),
    "board": (Right.DRAW_ON_BOARDS, Right.INVESTIGATE),
    "drawn_watch": (Right.DRAW_ON_BOARDS, Right.INVESTIGATE),
    "link_type_proposal": (Right.PROPOSE_TYPES,),
}

#: L3.8's kinds: each in a case of the administrator's unit, so held only within it.
CASE_KINDS: frozenset[str] = frozenset({"view", "board", "link_type_proposal", "drawn_watch"})
#: The level on its case each needs, as its own route asks it (Viewer saves a view; Editor draws and
#: proposes); a rule and a pipeline schedule need Author (`_case_levels_hold`).
LEVEL_NEEDED: Mapping[str, AccessLevel] = {
    "view": AccessLevel.VIEWER,
    "board": AccessLevel.EDITOR,
    "drawn_watch": AccessLevel.EDITOR,
    "link_type_proposal": AccessLevel.EDITOR,
}


class DisableRefused(Exception):
    def __init__(self, error: str, words: str, items: Sequence[OwnedItem] = ()) -> None:
        super().__init__(words)
        self.error = error
        self.words = words
        self.items = list(items)


async def l38_owned_items(
    conn: asyncpg.Connection, person: str, *, admin_unit: str | None, cleared: list[str], top: str
) -> list[OwnedItem]:
    """What the case lane's ownership route (L3.8) says the person owns, read by its own SQL with
    the administrator's unit and the markings they clear (`person_ownership.reach`), each placed by
    its case. Imported here, not at the top: `person_ownership` imports `DisableRefused` from this
    module."""
    from .person_ownership import owned_items

    found = await owned_items(conn, person, admin_unit=admin_unit, cleared=cleared, top=top)
    return [
        OwnedItem(kind=i.kind, id=i.id, label=i.label, investigation_id=i.investigation_id)
        for i in found
    ]


#: Every marking a case reads, for its highest (ADR-145 Amendment 9: a view's or a board's
#: recipient must clear it, since a view's count is not filtered per reader): each dataset it reads
#: but its own layer (capped at the ceiling already), a composite's members and its own marking
#: where set; an unmarked one reads as the scheme's highest (`$2`).
_CASE_MARKINGS_SQL = """
SELECT COALESCE(d.highest_marking, $2) AS marking FROM investigation_datasets c
JOIN datasets d ON d.id = c.dataset_id
WHERE c.investigation_id = $1 AND d.kind <> 'analyst_layer'
  AND NOT (d.kind = 'composite' AND d.highest_marking IS NULL)
UNION ALL
SELECT COALESCE(m.highest_marking, $2) FROM investigation_datasets c
JOIN composite_members cm ON cm.composite_id = c.dataset_id
JOIN datasets m ON m.id = cm.member_id
WHERE c.investigation_id = $1
"""


def case_highest(markings: Sequence[str], classification: Sequence[str]) -> str:
    """The highest of a case's markings; the scheme's highest for none, or one it does not know."""
    top = classification[-1]
    if not markings or any(m not in classification for m in markings):
        return top
    return max(markings, key=list(classification).index)


#: The marking a proposal's or a watch's recipient must clear: its dataset's highest, or the
#: scheme's highest where none is set or there is none (`$2`), as L3.8 reads it.
_MARKING_SQL: Mapping[str, str] = {
    "link_type_proposal": (
        "SELECT p.id, COALESCE(d.highest_marking, $2) AS marking FROM link_type_proposals p "
        "LEFT JOIN datasets d ON d.id = p.dataset_id WHERE p.id = ANY($1::text[])"
    ),
    "drawn_watch": (
        "SELECT w.id, COALESCE(d.highest_marking, $2) AS marking FROM drawn_watches w "
        "LEFT JOIN datasets d ON d.id = w.dataset_id WHERE w.id = ANY($1::text[])"
    ),
}


_AUTHOR_ONLY_SQL = """
SELECT i.id, i.name, h.dataset_id, d.name AS dataset_name,
       ARRAY(SELECT o.account_id FROM investigation_grants o
             WHERE o.investigation_id = i.id AND o.level = 'author' AND o.account_id <> $1
             ORDER BY o.account_id) AS others
FROM investigation_grants g
JOIN investigations i ON i.id = g.investigation_id AND i.removed_at IS NULL
LEFT JOIN home_cases h ON h.investigation_id = i.id
LEFT JOIN datasets d ON d.id = h.dataset_id
WHERE g.account_id = $1 AND g.level = 'author' AND i.owning_unit = $2
ORDER BY i.id
"""

#: How many of the same kinds the person owns in another unit: counted, never read, so a plan is
#: whole or refused (a case of another unit is that unit's administrator's to transfer).
_ELSEWHERE_SQL = """
SELECT
  (SELECT count(*) FROM investigation_grants g
     JOIN investigations i ON i.id = g.investigation_id AND i.removed_at IS NULL
    WHERE g.account_id = $1 AND g.level = 'author' AND i.owning_unit <> $2
      AND NOT EXISTS (SELECT 1 FROM investigation_grants o WHERE o.investigation_id = i.id
                      AND o.level = 'author' AND o.account_id <> $1))
+ (SELECT count(*) FROM typology_rules r JOIN investigations i ON i.id = r.investigation_id
    WHERE r.owner_id = $1 AND r.status = 'active' AND i.owning_unit <> $2)
+ (SELECT count(DISTINCT recipe_id) FROM studio_recipes
    WHERE schedule_owner = $1 AND owning_unit <> $2)
"""


@dataclass(frozen=True)
class _Plan:
    items: list[OwnedItem]
    #: The case a rule's or a pipeline schedule's runs are judged against, by item; and the case
    #: of each of L3.8's items, whose level its recipient must hold (`LEVEL_NEEDED`).
    case_of: dict[tuple[str, str], str]
    #: Items of the same kinds in another unit, counted only.
    elsewhere: int
    #: The marking each proposal's and watch's recipient must clear.
    marking_of: dict[tuple[str, str], str] = field(default_factory=dict)
    #: Each list schedule's list marking, by the list (only one the administrator is cleared for is
    #: listed), which its recipient must clear.
    list_marking_of: dict[str, tuple[str, str]] = field(default_factory=dict)


def answering(
    people: Sequence[PersonAccount], person: str, unit: str | None
) -> Callable[[str], bool]:
    """Whether another of a case's Author grants still answers for it once `person` is disabled
    (round 2's finding 6): an enabled person of the case's unit, or a team with an enabled member
    of that unit other than `person`. A disabled Author, or a team whose only member is `person`,
    answers for nothing, so the case is theirs to transfer."""
    by_id = {p.id: p for p in people}

    def answers(account: str) -> bool:
        if account.startswith(TEAM_GRANT_PREFIX):
            role = f"{CUSTOM_ROLE_PREFIX}{account[len(TEAM_GRANT_PREFIX) :]}"
            return any(
                role in p.roles
                and p.enabled
                and not p.system_account
                and p.org_unit == unit
                and p.id != person
                for p in people
            )
        other = by_id.get(account)
        return bool(other and other.enabled and not other.system_account and other.org_unit == unit)

    return answers


async def _plan_items(
    conn: asyncpg.Connection,
    person: str,
    admin_unit: str | None,
    answers: Callable[[str], bool] | None = None,
    *,
    cleared: list[str],
    top: str,
    lists_cleared: ListClearance,
    classification: Sequence[str] = (),
) -> _Plan:
    """Everything the person owns in the administrator's unit, each read with the unit in its own
    statement (rule 3); hotlists, watches, saved patterns, team leads and list schedules have no
    unit and are the person's wherever they are. Never a hotlist's identifier, a saved pattern's
    or a rule's analyst-written name (rule 7): their kind, and the case or date that places
    them."""
    items: list[OwnedItem] = []
    case_of: dict[tuple[str, str], str] = {}
    for row in await conn.fetch(_AUTHOR_ONLY_SQL, person, admin_unit):
        others = list(row["others"])
        if any(answers(o) for o in others) if answers is not None else others:
            continue
        if row["dataset_id"] is not None:
            label = f"Author of the home case of the dataset {row['dataset_name']}"
            items.append(OwnedItem(kind="home_case_author", id=row["id"], label=label))
        else:
            label = f"Only Author of the case {row['name'] or row['id']}"
            items.append(OwnedItem(kind="case_author", id=row["id"], label=label))
    for row in await conn.fetch(
        "SELECT role_id, display_name FROM teams WHERE lead = $1 ORDER BY role_id", person
    ):
        items.append(
            OwnedItem(
                kind="team_lead", id=row["role_id"], label=f"Lead of the team {row['display_name']}"
            )
        )
    for row in await conn.fetch(
        "SELECT id, review_date FROM hotlists WHERE owner_id = $1 AND status = 'active' "
        "ORDER BY id",
        person,
    ):
        items.append(
            OwnedItem(
                kind="hotlist", id=row["id"], label=f"A hotlist, for review by {row['review_date']}"
            )
        )
    for row in await conn.fetch(
        "SELECT id FROM monitors WHERE owner_id = $1 AND status = 'active' ORDER BY id", person
    ):
        items.append(OwnedItem(kind="monitor", id=row["id"], label="A watch on a saved pattern"))
    for row in await conn.fetch(
        "SELECT pattern_id, max(version) AS versions FROM saved_patterns WHERE owner_id = $1 "
        "GROUP BY pattern_id ORDER BY pattern_id",
        person,
    ):
        items.append(
            OwnedItem(
                kind="saved_pattern",
                id=row["pattern_id"],
                label=f"A saved pattern ({row['versions']} versions)",
            )
        )
    for row in await conn.fetch(
        "SELECT r.id, r.investigation_id, i.name AS case_name FROM typology_rules r "
        "JOIN investigations i ON i.id = r.investigation_id "
        "WHERE r.owner_id = $1 AND r.status = 'active' AND i.owning_unit = $2 ORDER BY r.id",
        person,
        admin_unit,
    ):
        case = row["case_name"] or row["investigation_id"]
        label = f"A rule of the case {case}, whose runs act as them"
        items.append(OwnedItem(kind="typology_rule", id=row["id"], label=label))
        case_of[("typology_rule", row["id"])] = row["investigation_id"]
    for row in await conn.fetch(
        "SELECT recipe_id, max(label) AS label, max(schedule_case) AS schedule_case "
        "FROM studio_recipes WHERE schedule_owner = $1 AND owning_unit = $2 "
        "GROUP BY recipe_id ORDER BY recipe_id",
        person,
        admin_unit,
    ):
        items.append(
            OwnedItem(
                kind="pipeline_schedule",
                id=row["recipe_id"],
                label=f"The schedule of the pipeline {row['label']}, which runs as them",
            )
        )
        if row["schedule_case"]:
            case_of[("pipeline_schedule", row["recipe_id"])] = row["schedule_case"]
    # A list's schedule, read through the lists' own clearance filter, in the query (ADR-146
    # Amendment 7 point 8; `screening._admitted_sql`). One the administrator is not cleared for is
    # left out, its kind, number and place unsaid: `person_ownership`'s withheld check refuses the
    # disable for it (409 `withheld_items`) until an administrator cleared for the list transfers it
    # (the owner's ruling of 9 November 2026; the orchestrator's verification of 7a1c760). Its
    # recipient must be cleared for the list too (`markings_hold`).
    list_marking_of: dict[str, tuple[str, str]] = {}
    for row in await conn.fetch(
        "SELECT l.list_name, COALESCE(m.classification, 'OFFICIAL') AS classification, "
        "COALESCE(m.handling_code, 'P') AS handling_code "
        f"FROM screening_lists l{_markings_join('l')} "
        f"WHERE l.schedule_owner = $1 AND {_admitted_sql('l', 2)} ORDER BY l.list_name",
        person,
        list(lists_cleared.classifications),
        list(lists_cleared.codes),
    ):
        label = f"The refresh schedule of the list {row['list_name']}"
        items.append(OwnedItem(kind="list_schedule", id=row["list_name"], label=label))
        list_marking_of[row["list_name"]] = (row["classification"], row["handling_code"])
    l38 = await l38_owned_items(conn, person, admin_unit=admin_unit, cleared=cleared, top=top)
    marking_of: dict[tuple[str, str], str] = {}
    for kind, sql in _MARKING_SQL.items():
        ids = [i.id for i in l38 if i.kind == kind]
        for row in await conn.fetch(sql, ids, top) if ids else []:
            marking_of[(kind, row["id"])] = row["marking"]
    highest: dict[str, str] = {}
    for item in l38:
        if item.kind in ("view", "board") and item.investigation_id is not None:
            case_id = item.investigation_id
            if case_id not in highest:
                rows = await conn.fetch(_CASE_MARKINGS_SQL, case_id, top)
                highest[case_id] = case_highest(
                    [r["marking"] for r in rows], classification or [top]
                )
            marking_of[(item.kind, item.id)] = highest[case_id]
    for item in l38:
        if item.investigation_id is not None:
            case_of[(item.kind, item.id)] = item.investigation_id
    l38 = [
        i.model_copy(update={"needs_clearance": marking_of.get((i.kind, i.id))}) for i in l38
    ]
    items.extend(l38)
    elsewhere = int(await conn.fetchval(_ELSEWHERE_SQL, person, admin_unit) or 0)
    return _Plan(items=items, case_of=case_of, elsewhere=elsewhere, marking_of=marking_of,
                 list_marking_of=list_marking_of)  # fmt: skip


_RANK = {level.value: level.rank for level in AccessLevel}


def people_rows(
    people: Sequence[PersonAccount],
    grants: Sequence[Mapping[str, object]],
    cases: Sequence[Mapping[str, object]],
    teams: Mapping[str, str],
) -> AdminPeopleRows:
    """The rows from one unit's grants: a level is the highest a person holds on the case, in their
    own name or through a team they are in now; `through` names the team when only it gives it."""
    team_of = {f"team:{rid}": rid for rid in teams}
    by_case: dict[str, list[Mapping[str, object]]] = {}
    for g in grants:
        by_case.setdefault(str(g["investigation_id"]), []).append(g)
    names = {str(c["id"]): str(c["name"] or c["id"]) for c in cases}
    rows: list[AdminPersonRow] = []
    authored: set[str] = set()
    for person in people:
        if person.system_account:
            continue
        mine = {
            r[len(CUSTOM_ROLE_PREFIX) :] for r in person.roles if r.startswith(CUSTOM_ROLE_PREFIX)
        }
        levels: list[PersonCaseLevel] = []
        for case_id, held in by_case.items():
            own = [str(g["level"]) for g in held if g["account_id"] == person.id]
            via = [
                (str(g["level"]), team_of[str(g["account_id"])])
                for g in held
                if team_of.get(str(g["account_id"])) in mine
            ]
            best_own = max(own, key=_RANK.__getitem__, default=None)
            best_via = max(via, key=lambda v: _RANK[v[0]], default=None)
            if best_own is None and best_via is None:
                continue
            if best_via is not None and (best_own is None or _RANK[best_via[0]] > _RANK[best_own]):
                level, through = best_via[0], teams[best_via[1]]
            else:
                level, through = str(best_own), None
            levels.append(
                PersonCaseLevel(
                    investigation_id=case_id,
                    name=names.get(case_id, case_id),
                    level=cast("Literal['viewer', 'editor', 'author']", level),
                    through=through,
                )
            )
            if level == "author" and person.enabled:
                authored.add(case_id)
        rows.append(AdminPersonRow(id=person.id, levels=levels))
    without = [
        CaseWithoutAuthor(investigation_id=cid, name=name)
        for cid, name in names.items()
        if cid not in authored
    ]
    return AdminPeopleRows(rows=rows, without_author=without)


#: Said when a person still answers for items of another unit: that they do, never how many
#: (rule 7). Each unit's administrator transfers their own unit's share, then either disables.
OTHER_UNIT = (
    "they still answer for cases, rules or pipeline schedules of another unit: that unit's "
    "administrator transfers those, and then either of you can disable them"
)


async def _case_levels_hold(
    conn: asyncpg.Connection,
    plan: _Plan,
    chosen: Mapping[tuple[str, str], str],
    who: Recipients,
) -> None:
    """A rule's or a pipeline schedule's runs are judged against its case (`rule_schedule.py`
    asks an Editor of a rule kept to its author, an Author otherwise; the scheduler, its case). The
    recipient is held to the stricter, Author, which every such run accepts: already, in their own
    name or through a team they are in now, or made its Author in this same transfer. A pipeline
    schedule naming no case has nothing to hold it to."""
    made_author = {
        (item_id, to)
        for (kind, item_id), to in chosen.items()
        if kind in ("case_author", "home_case_author")
    }
    for key, case_id in plan.case_of.items():
        to = chosen[key]
        if (case_id, to) in made_author:
            continue
        person = who.people.get(to)
        teams = [
            f"team:{r[len(CUSTOM_ROLE_PREFIX) :]}"
            for r in (person.roles if person else [])
            if r.startswith(CUSTOM_ROLE_PREFIX)
        ]
        needed = LEVEL_NEEDED.get(key[0], AccessLevel.AUTHOR)
        # The level `InvestigationStore` reads (`_LEVEL_SQL`): the highest grant in their own
        # name or a team's, or the case's unit-wide level for a member of its unit (the L2.5b
        # review's finding 4; `check_transfers` has already held the recipient to the unit).
        levels = await conn.fetch(
            "SELECT g.level FROM investigation_grants g WHERE g.investigation_id = $1 "
            "AND g.account_id = ANY($2::text[]) UNION ALL SELECT i.unit_level FROM "
            "investigations i WHERE i.id = $1 AND i.unit_level IS NOT NULL "
            "AND i.owning_unit = $3",
            case_id,
            [to, *teams],
            person.org_unit if person else None,
        )
        if any(AccessLevel(r["level"]).rank >= needed.rank for r in levels):
            continue
        item = next(i for i in plan.items if _key(i.kind, i.id) == key)
        if needed is AccessLevel.AUTHOR:
            words = (
                f"{item.label}: {to} is not an Author of its case, so its runs would be refused: "
                "make them its Author first, or in this same transfer"
            )
        else:
            words = (
                f"{item.label}: {to} holds no {needed.value.title()} level or higher on its case, "
                "which it needs: give them one first, or make them its Author in this same transfer"
            )
        raise DisableRefused("recipient_refused", words, [item])


def markings_hold(
    plan_markings: Mapping[tuple[str, str], str],
    items: Sequence[OwnedItem],
    chosen: Mapping[tuple[str, str], str],
    who: Recipients,
    scheme: HandlingScheme,
    list_markings: Mapping[str, tuple[str, str]] | None = None,
) -> None:
    """A proposal or a watch goes only to someone cleared to its dataset's marking (rule 3: a watch
    tells its owner of changes to an item they could not otherwise read), and a view or a board to
    someone cleared to its case's highest (ADR-145 Amendment 9: a view's count is not filtered per
    reader). A list's schedule goes only to someone cleared for the list's marking, its
    classification and its handling code (`list_markings`; the orchestrator's verification of
    e911b90, item 2: its refreshes run as them). The words name neither the marking nor the item's
    contents."""
    for item in items:
        key = _key(item.kind, item.id)
        if item.kind == "list_schedule" and list_markings is not None:
            list_marking = list_markings.get(item.id)
            account = who.people.get(chosen[key])
            if (
                list_marking is None
                or account is None
                or not ListClearance.of_clearance(
                    account.clearance, account.receivable_handling_codes, scheme
                ).admits(*list_marking)
            ):
                raise DisableRefused(
                    "recipient_refused",
                    f"{item.label}: {chosen[key]} is not cleared for the list; "
                    "choose someone who is",
                    [item],
                )
            continue
        marking = plan_markings.get(key)
        if marking is None:
            continue
        to = chosen[key]
        account = who.people.get(to)
        # A recipient whose clearance was read from Entra ID over a day ago never reaches here:
        # `check_transfers`, run first, refuses them (ADR-148 Amendment 8).
        clearance = account.clearance if account else None
        if (
            clearance is None
            or clearance not in scheme.classification
            or not scheme.clears(clearance, marking)
        ):
            raise DisableRefused(
                "recipient_refused",
                f"{item.label}: {to} is not cleared to the marking it needs; "
                "choose someone who is",
                [item],
            )


async def _watch_clash(
    conn: asyncpg.Connection, items: Sequence[OwnedItem], chosen: Mapping[tuple[str, str], str]
) -> None:
    """A person watches a saved pattern once (`monitors`' own key): a watch is never given to
    someone already watching the same pattern."""
    for item in items:
        if item.kind != "monitor":
            continue
        to = chosen[_key(item.kind, item.id)]
        if await conn.fetchval(
            "SELECT 1 FROM monitors m JOIN monitors w ON w.pattern_id = m.pattern_id "
            "WHERE m.id = $1 AND w.owner_id = $2",
            item.id,
            to,
        ):
            raise DisableRefused(
                "recipient_refused",
                f"{item.label}: {to} already watches the same pattern; choose someone else",
                [item],
            )


def _key(kind: str, item_id: str) -> tuple[str, str]:
    return (kind, item_id)


@dataclass(frozen=True)
class Recipients:
    """Who may receive: the directory's people, by account, with their rights read as now."""

    people: Mapping[str, PersonAccount]
    rights: Mapping[str, frozenset[Right]]
    team_members: Mapping[str, frozenset[str]]
    #: On Entra ID, the accounts whose clearance and unit were last read from a token over a day ago
    #: (`entra_people.access_current`): never given anything until they sign in again.
    stale: frozenset[str] = frozenset()


def check_transfers(
    person: str,
    items: Sequence[OwnedItem],
    transfers: Sequence[OwnedTransfer],
    who: Recipients,
    unit: str | None = None,
) -> dict[tuple[str, str], str]:
    """Every item given a recipient who may take it, or `DisableRefused` in words; nothing is
    written."""
    chosen = {_key(t.kind, t.id): t.to.strip() for t in transfers}
    missing = [i for i in items if not chosen.get(_key(i.kind, i.id))]
    if missing:
        raise DisableRefused(
            "untransferred",
            f"{len(missing)} of {len(items)} items have no one to transfer them to: "
            + "; ".join(i.label for i in missing),
            missing,
        )
    planned = {_key(i.kind, i.id) for i in items}
    unplanned = sorted(set(chosen) - planned)
    if unplanned:
        raise DisableRefused(
            "not_in_plan",
            "a transfer names something this person does not own: "
            + ", ".join(f"{k} {i}" for k, i in unplanned),
        )
    for item in items:
        to = chosen[_key(item.kind, item.id)]
        account = who.people.get(to)
        why = None
        if to == person:
            why = "it cannot go to the person being disabled"
        elif account is None:
            why = f"{to} is not a person the directory holds"
        elif account.system_account:
            why = f"{to} is a service account, which owns nothing"
        elif not account.enabled:
            why = f"{to} is disabled"
        elif to in who.stale:
            why = f"{to}: {STALE_ACCESS_WORDS}"
        elif (
            item.kind in ("case_author", "home_case_author") or item.kind in CASE_KINDS
        ) and account.org_unit != unit:
            why = f"{to} is of another unit, and a case's level is held only within its unit"
        elif item.kind == "team_lead" and to not in who.team_members.get(item.id, frozenset()):
            why = f"{to} is not a member of the team"
        elif lacking := [
            r.value for r in NEEDS.get(item.kind, ()) if r not in who.rights.get(to, frozenset())
        ]:
            needs = "it needs" if item.kind in CASE_KINDS else "its runs need"
            why = f"{to} does not hold {' and '.join(lacking)}, which {needs}"
        if why is not None:
            raise DisableRefused("recipient_refused", f"{item.label}: {why}", [item])
    return chosen


def _list_marking_words(marking: tuple[str, str] | None) -> dict[str, str]:
    if marking is None:
        return {}
    return {"list_classification": marking[0], "list_handling_code": marking[1]}


_TRANSFER_SQL: Mapping[str, str] = {
    "hotlist": "UPDATE hotlists SET owner_id = $2 WHERE id = $1 AND owner_id = $3",
    "monitor": "UPDATE monitors SET owner_id = $2 WHERE id = $1 AND owner_id = $3",
    "saved_pattern": (
        "UPDATE saved_patterns SET owner_id = $2 WHERE pattern_id = $1 AND owner_id = $3"
    ),
    "typology_rule": "UPDATE typology_rules SET owner_id = $2 WHERE id = $1 AND owner_id = $3",
    "pipeline_schedule": (
        "UPDATE studio_recipes SET schedule_owner = $2 WHERE recipe_id = $1 AND schedule_owner = $3"
    ),
    "list_schedule": (
        "UPDATE screening_lists SET schedule_owner = $2 "
        "WHERE list_name = $1 AND schedule_owner = $3"
    ),
    # L3.8's kinds: the creator, the proposer while it waits, the owner while it is open.
    "view": (
        "UPDATE case_views SET created_by = $2 WHERE id = $1 AND created_by = $3 AND NOT drawing"
    ),
    "board": (
        "UPDATE case_views SET created_by = $2 WHERE id = $1 AND created_by = $3 AND drawing"
    ),
    "link_type_proposal": (
        "UPDATE link_type_proposals SET proposed_by = $2 "
        "WHERE id = $1 AND proposed_by = $3 AND status = 'pending'"
    ),
    "drawn_watch": (
        "UPDATE drawn_watches SET owner = $2 WHERE id = $1 AND owner = $3 AND ended_at IS NULL"
    ),
    "team_lead": (
        "UPDATE teams SET lead = $2, "
        "cover = CASE WHEN cover = $2 THEN NULL ELSE cover END, "
        "cover_until = CASE WHEN cover = $2 THEN NULL ELSE cover_until END "
        "WHERE role_id = $1 AND lead = $3"
    ),
}


class AdminPeopleStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str) -> AdminPeopleStore:
        return cls(await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=2))

    async def close(self) -> None:
        await self._pool.close()

    async def rows(self, people: Sequence[PersonAccount], *, unit: str | None) -> AdminPeopleRows:
        """Each person's levels in the unit's open cases, and the cases no enabled person is Author
        of, in their own name or through a team with an enabled member. One read, scoped in SQL to
        the administrator's unit."""
        async with self._pool.acquire() as conn:
            grants = await conn.fetch(
                "SELECT g.investigation_id, i.name, g.account_id, g.level "
                "FROM investigation_grants g JOIN investigations i "
                "ON i.id = g.investigation_id AND i.removed_at IS NULL "
                "WHERE i.owning_unit = $1 ORDER BY lower(i.name), i.id",
                unit,
            )
            cases = await conn.fetch(
                "SELECT id, name FROM investigations WHERE owning_unit = $1 AND removed_at IS NULL "
                "ORDER BY lower(name), id",
                unit,
            )
            teams = {
                r["role_id"]: r["display_name"]
                for r in await conn.fetch("SELECT role_id, display_name FROM teams")
            }
        return people_rows(people, grants, cases, teams)

    async def plan(
        self,
        person: str,
        *,
        admin: Principal,
        scheme: HandlingScheme,
        people: Sequence[PersonAccount] | None = None,
    ) -> DisablePlan:
        """The plan of the administrator's own unit, within the markings they clear; another
        unit's items are counted at the disable (`transfer` answers `elsewhere`), and an item they
        may not see is never listed (`refuse_if_withheld` answers for it)."""
        from .person_ownership import reach

        unit, cleared, top = reach(admin, scheme)
        async with self._pool.acquire() as conn:
            plan = await _plan_items(
                conn,
                person,
                unit,
                None if people is None else answering(people, person, unit),
                cleared=cleared,
                top=top,
                lists_cleared=ListClearance.of(admin, scheme),
                classification=scheme.classification,
            )
        return DisablePlan(person=person, items=plan.items, not_yet_listed=list(L38_OWNED_KINDS))

    async def converted_views(self, unit: str | None) -> ConvertedViews:
        """*Admin › System*'s line for ADR-144 decision 6: how many views the migration made from
        cases made from another, and in how many cases. Counted in SQL within the administrator's
        own unit, open cases only (rule 7: never another unit's count). The cases it did not
        place are named by its dry-run report, not here: their marker is the migration's own
        column, which ADR-144 Amendment 1 keeps out of the Conduit."""
        async with self._pool.acquire() as conn:
            made = await conn.fetchrow(
                "SELECT count(*) AS views, count(DISTINCT v.case_id) AS cases FROM case_views v "
                "JOIN investigations i ON i.id = v.case_id AND i.removed_at IS NULL "
                "AND i.owning_unit = $1 WHERE v.converted_from_case IS NOT NULL",
                unit,
            )
        return ConvertedViews(views=made["views"], cases=made["cases"])

    async def refuse_if_withheld(
        self, person: str, *, admin: Principal, scheme: HandlingScheme
    ) -> None:
        """Asked by *Transfer and disable* after the visible transfers commit (ADR-145 Amendment
        8 decision 3): L3.8's `refuse_if_withheld`, on a connection of its own, so what it reads is
        what was committed. Raises `DisableRefused` (`withheld_items`), naming nothing."""
        from .person_ownership import refuse_if_withheld

        async with self._pool.acquire() as conn:
            await refuse_if_withheld(conn, person, admin=admin, scheme=scheme)

    async def transfer(
        self,
        person: str,
        transfers: Sequence[OwnedTransfer],
        who: Recipients,
        *,
        by: Principal,
        audit: AuditWriter,
        admin_unit: str | None,
        scheme: HandlingScheme,
    ) -> tuple[list[tuple[OwnedItem, str]], int]:
        """Every item of the administrator's unit to its recipient, in one transaction with an
        audit row for each; the plan is read again inside it, so an item gained since the
        administrator looked is refused too. Answers the transfers and how many items the person
        still owns in another unit, which the disable is then refused for. The covers are not
        ended here: the route asks `refuse_if_withheld` once this has committed, and only then
        `end_covers`, just before the identity provider."""
        from .person_ownership import reach

        _, cleared, top = reach(by, scheme)
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("LOCK TABLE investigation_grants IN SHARE ROW EXCLUSIVE MODE")
            plan = await _plan_items(
                conn,
                person,
                admin_unit,
                answering(list(who.people.values()), person, admin_unit),
                cleared=cleared,
                top=top,
                lists_cleared=ListClearance.of(by, scheme),
                classification=scheme.classification,
            )
            items = plan.items
            chosen = check_transfers(person, items, transfers, who, admin_unit)
            await _case_levels_hold(conn, plan, chosen, who)
            markings_hold(plan.marking_of, items, chosen, who, scheme, plan.list_marking_of)
            await _watch_clash(conn, items, chosen)
            done: list[tuple[OwnedItem, str]] = []
            for item in items:
                to = chosen[_key(item.kind, item.id)]
                if item.kind in ("case_author", "home_case_author"):
                    await conn.execute(
                        "INSERT INTO investigation_grants (investigation_id, account_id, level) "
                        "VALUES ($1, $2, 'author') ON CONFLICT (investigation_id, account_id) "
                        "DO UPDATE SET level = 'author'",
                        item.id,
                        to,
                    )
                    await InvestigationStore._record(
                        conn, item.id, by.id, "grant", to, AccessLevel.AUTHOR
                    )
                else:
                    changed = await conn.execute(_TRANSFER_SQL[item.kind], item.id, to, person)
                    if changed.endswith(" 0"):
                        raise DisableRefused(
                            "changed_meanwhile", f"{item.label} changed while it was transferred"
                        )
                await audit.record(
                    principal=by,
                    action="transfer_owned_item",
                    result_cardinality=1,
                    investigation_id=(
                        item.id if item.kind in ("case_author", "home_case_author") else None
                    ),
                    resolved_query={
                        "from": person, "to": to, "kind": item.kind, "id": item.id,
                        # A list's marking as it was moved, which the audit's read admits its
                        # reader by, beside the list's now (`audit_section._lists_clause`).
                        **_list_marking_words(plan.list_marking_of.get(item.id)
                                              if item.kind == "list_schedule" else None),
                    },  # fmt: skip
                    conn=conn,
                )
                done.append((item, to))
        return done, plan.elsewhere

    async def end_covers(self, person: str, *, by: Principal, audit: AuditWriter) -> None:
        """A cover is no ownership: the person's covers end, each audited, and the lead acts.
        Called by the disable route only once nothing is left elsewhere or withheld and the
        identity provider has disabled the account, so a refused disable never ends a cover, and
        a cover never
        outlives a disable that went ahead (the L2.5b review's finding 3: asked inside the
        transfer, a withheld item transferred meanwhile left a disabled person covering)."""
        async with self._pool.acquire() as conn, conn.transaction():
            for row in await conn.fetch(
                "UPDATE teams SET cover = NULL, cover_until = NULL WHERE cover = $1 "
                "RETURNING role_id",
                person,
            ):
                await audit.record(
                    principal=by,
                    action="set_team_cover",
                    result_cardinality=1,
                    resolved_query={
                        "role_id": row["role_id"],
                        "before": [person],
                        "after": [None],
                        "why": "the cover was disabled",
                    },
                    conn=conn,
                )


def recipients(
    people: Sequence[PersonAccount],
    custom: Mapping[str, frozenset[Right]],
    teams: Mapping[str, frozenset[str]],
    now: datetime | None = None,
) -> Recipients:
    # Keyed by the directory's id for the account, which is the token's `sub` (Keycloak) or object
    # id (Entra ID): the principal id every grant and owner column holds.
    by_account = {p.id: p for p in people}
    return Recipients(
        people=by_account,
        rights={a: rights_for(p.roles, custom) for a, p in by_account.items()},
        team_members=teams,
        stale=frozenset(a for a, p in by_account.items() if not access_current(p, now)),
    )


__all__ = [
    "CASE_KINDS",
    "LEVEL_NEEDED",
    "OTHER_UNIT",
    "L38_OWNED_KINDS",
    "NEEDS",
    "AdminPeopleStore",
    "DisableRefused",
    "Recipients",
    "check_transfers",
    "people_rows",
    "l38_owned_items",
    "case_highest",
    "markings_hold",
    "recipients",
]
