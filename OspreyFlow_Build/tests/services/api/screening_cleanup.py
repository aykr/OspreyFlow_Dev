"""A live file's screening lists, removed from the shared store (`06_DECISIONS.md` ADR-146 Amendment 7,
CARRIES row 113).

The lane stacks keep every earlier file's rows, and the KYC gate screens against every list the store
holds (`ScreeningListStore.entries`), so a list one live file leaves behind is screened by the next:
`test_screening_refresh.py`'s "Synthetic list" names the same synthetic people as `test_kyc_rules.py`'s
list, and each listed owner matched twice. Each live file that loads a list removes **its own** lists,
by name, in its fixture's teardown (after the `yield`, so on a failure too), never another file's:
`remove_screening_lists` deletes the named lists' entries, subscription, updates and each update's
per-unit counts and its kept marking, in one transaction. A file's setup clears its own names the same way, so a run killed
before its teardown leaves nothing the next run of that file trips on.

`test_kyc_rules.py::test_no_other_file_leaves_a_list_naming_this_files_people` is the case that sees a
list another file left in the same run (red before these teardowns, `process/lanes/rules/lists/`).
"""

from __future__ import annotations

from collections.abc import Sequence

import asyncpg
from services.api.screening import ListClearance

from ontology.handling import load_uk_le_scheme

_SCHEME = load_uk_le_scheme()
#: Every marking: the store read as an operator would, by a test that checks what a list holds, not
#: who may read it (those cases pass a reader's own `ListClearance.of(...)`).
EVERYTHING = ListClearance(tuple(_SCHEME.classification), tuple(_SCHEME.handling_codes))

#: The tables a list's rows live in (`services/api/screening.py`'s bootstrap), its kept marking too.
_REMOVE_SQL = """
DELETE FROM screening_list_update_units WHERE update_id IN (
    SELECT id FROM screening_list_updates WHERE list_name = ANY($1::text[]) OR list_name LIKE ANY($2::text[]));
DELETE FROM screening_list_updates WHERE list_name = ANY($1::text[]) OR list_name LIKE ANY($2::text[]);
DELETE FROM screening_lists WHERE list_name = ANY($1::text[]) OR list_name LIKE ANY($2::text[]);
DELETE FROM screening_entries WHERE list_name = ANY($1::text[]) OR list_name LIKE ANY($2::text[]);
DELETE FROM screening_list_markings WHERE list_name = ANY($1::text[]) OR list_name LIKE ANY($2::text[]);
"""


async def remove_screening_lists(
    dsn: str, *, names: Sequence[str] = (), prefixes: Sequence[str] = ()
) -> None:
    """The lists named, or whose names start with one of `prefixes`, removed whole. At least one
    name or prefix is required: this never empties the store."""
    if not names and not prefixes:
        raise ValueError("name the lists to remove; this never removes every list")
    if any(not p for p in prefixes):
        raise ValueError("an empty prefix would remove every list")
    likes = [p.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%" for p in prefixes]
    conn = await asyncpg.connect(dsn)
    try:
        async with conn.transaction():
            for statement in filter(None, (s.strip() for s in _REMOVE_SQL.split(";"))):
                await conn.execute(statement, list(names), likes)
    finally:
        await conn.close()
