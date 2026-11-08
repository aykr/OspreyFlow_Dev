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

**Not yet listed, L2.5b's seam** (`L38_OWNED_KINDS`, `l38_owned_items`): private views and boards,
promotions they proposed that wait for review, reviews waiting on them, and proposed types. Their
owner reads are the case lane's ownership route (L3.8); until it is on main the plan says, in words,
that they are not yet listed, and `l38_owned_items` returns none.

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

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, cast

import asyncpg

from schemas.admin import (
    AdminPeopleRows,
    AdminPersonRow,
    CaseWithoutAuthor,
    DisablePlan,
    OwnedItem,
    OwnedTransfer,
    PersonAccount,
    PersonCaseLevel,
)
from schemas.domain import Principal
from schemas.rights import CUSTOM_ROLE_PREFIX, Right, rights_for

from .audit import AuditWriter
from .investigations import AccessLevel, InvestigationStore

#: L2.5b's seam: the kinds a person owns that are read through the case lane's ownership route
#: (L3.8), not yet on main. Said in the plan, so an administrator is never told the list is whole.
L38_OWNED_KINDS: tuple[str, ...] = (
    "private views",
    "boards",
    "promotions waiting for review",
    "reviews waiting on them",
    "proposed types",
)

#: The right an item's runs are checked against, which its recipient must hold (`scheduler.py`,
#: `rule_schedule.py`, `list_schedule.py`; the watches' and hotlists' `keep_watches`).
NEEDS: Mapping[str, Right] = {
    "typology_rule": Right.DEPLOY_RULES,
    "pipeline_schedule": Right.SCHEDULE_PIPELINES,
    "list_schedule": Right.LOAD_SCREENING_LISTS,
    "hotlist": Right.KEEP_WATCHES,
    "monitor": Right.KEEP_WATCHES,
    "saved_pattern": Right.KEEP_WATCHES,
}


class DisableRefused(Exception):
    def __init__(self, error: str, words: str, items: Sequence[OwnedItem] = ()) -> None:
        super().__init__(words)
        self.error = error
        self.words = words
        self.items = list(items)


async def l38_owned_items(conn: asyncpg.Connection, person: str) -> list[OwnedItem]:
    """L2.5b's seam: what the case lane's ownership route (L3.8) will say the person owns. None
    until that route is on main; the plan names the kinds in `not_yet_listed` meanwhile."""
    del conn, person
    return []


_AUTHOR_ONLY_SQL = """
SELECT i.id, i.name, h.dataset_id, d.name AS dataset_name
FROM investigation_grants g
JOIN investigations i ON i.id = g.investigation_id AND i.removed_at IS NULL
LEFT JOIN home_cases h ON h.investigation_id = i.id
LEFT JOIN datasets d ON d.id = h.dataset_id
WHERE g.account_id = $1 AND g.level = 'author' AND i.owning_unit = $2
  AND NOT EXISTS (SELECT 1 FROM investigation_grants o
                  WHERE o.investigation_id = i.id AND o.level = 'author' AND o.account_id <> $1)
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
    #: The case a rule's or a pipeline schedule's runs are judged against, by item.
    case_of: dict[tuple[str, str], str]
    #: Items of the same kinds in another unit, counted only.
    elsewhere: int


async def _plan_items(conn: asyncpg.Connection, person: str, admin_unit: str | None) -> _Plan:
    """Everything the person owns in the administrator's unit, each read with the unit in its own
    statement (rule 3); hotlists, watches, saved patterns, team leads and list schedules have no
    unit and are the person's wherever they are. Never a hotlist's identifier, a saved pattern's
    or a rule's analyst-written name (rule 7): their kind, and the case or date that places
    them."""
    items: list[OwnedItem] = []
    case_of: dict[tuple[str, str], str] = {}
    for row in await conn.fetch(_AUTHOR_ONLY_SQL, person, admin_unit):
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
    for row in await conn.fetch(
        "SELECT list_name FROM screening_lists WHERE schedule_owner = $1 ORDER BY list_name", person
    ):
        items.append(
            OwnedItem(
                kind="list_schedule",
                id=row["list_name"],
                label=f"The refresh schedule of the list {row['list_name']}",
            )
        )
    items.extend(await l38_owned_items(conn, person))
    elsewhere = int(await conn.fetchval(_ELSEWHERE_SQL, person, admin_unit) or 0)
    return _Plan(items=items, case_of=case_of, elsewhere=elsewhere)


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
        held = await conn.fetchval(
            "SELECT 1 FROM investigation_grants WHERE investigation_id = $1 "
            "AND account_id = ANY($2::text[]) AND level = 'author'",
            case_id,
            [to, *teams],
        )
        if not held:
            item = next(i for i in plan.items if _key(i.kind, i.id) == key)
            raise DisableRefused(
                "recipient_refused",
                f"{item.label}: {to} is not an Author of its case, so its runs would be refused: "
                "make them its Author first, or in this same transfer",
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
        elif item.kind in ("case_author", "home_case_author") and account.org_unit != unit:
            why = f"{to} is of another unit, and a case's level is held only within its unit"
        elif item.kind == "team_lead" and to not in who.team_members.get(item.id, frozenset()):
            why = f"{to} is not a member of the team"
        elif item.kind in NEEDS and NEEDS[item.kind] not in who.rights.get(to, frozenset()):
            why = f"{to} does not hold {NEEDS[item.kind].value}, which its runs need"
        if why is not None:
            raise DisableRefused("recipient_refused", f"{item.label}: {why}", [item])
    return chosen


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

    async def plan(self, person: str, *, admin_unit: str | None) -> DisablePlan:
        """The plan of the administrator's own unit; another unit's items are counted at the
        disable (`transfer` answers `elsewhere`), never listed."""
        async with self._pool.acquire() as conn:
            plan = await _plan_items(conn, person, admin_unit)
        return DisablePlan(person=person, items=plan.items, not_yet_listed=list(L38_OWNED_KINDS))

    async def transfer(
        self,
        person: str,
        transfers: Sequence[OwnedTransfer],
        who: Recipients,
        *,
        by: Principal,
        audit: AuditWriter,
        admin_unit: str | None,
    ) -> tuple[list[tuple[OwnedItem, str]], int]:
        """Every item of the administrator's unit to its recipient, in one transaction with an
        audit row for each; the plan is read again inside it, so an item gained since the
        administrator looked is refused too. Answers the transfers and how many items the person
        still owns in another unit, which the disable is then refused for; the covers end only when
        nothing is left elsewhere, as the disable follows."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("LOCK TABLE investigation_grants IN SHARE ROW EXCLUSIVE MODE")
            plan = await _plan_items(conn, person, admin_unit)
            items = plan.items
            chosen = check_transfers(person, items, transfers, who, admin_unit)
            await _case_levels_hold(conn, plan, chosen, who)
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
                    resolved_query={"from": person, "to": to, "kind": item.kind, "id": item.id},
                    conn=conn,
                )
                done.append((item, to))
            if plan.elsewhere:
                return done, plan.elsewhere
            # A cover is no ownership: the person's covers end, each audited, and the lead acts.
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
        return done, 0


def recipients(
    people: Sequence[PersonAccount],
    custom: Mapping[str, frozenset[Right]],
    teams: Mapping[str, frozenset[str]],
) -> Recipients:
    # Keyed by the directory's id for the account, which is the token's `sub`: the principal id
    # every grant and owner column holds.
    by_account = {p.id: p for p in people}
    return Recipients(
        people=by_account,
        rights={a: rights_for(p.roles, custom) for a, p in by_account.items()},
        team_members=teams,
    )


__all__ = [
    "OTHER_UNIT",
    "L38_OWNED_KINDS",
    "NEEDS",
    "AdminPeopleStore",
    "DisableRefused",
    "Recipients",
    "check_transfers",
    "people_rows",
    "l38_owned_items",
    "recipients",
]
