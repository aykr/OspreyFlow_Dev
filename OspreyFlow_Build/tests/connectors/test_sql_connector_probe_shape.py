"""The shape of the SQL connector's read-only probe (slice SE6c), pure: it reads one named file,
`services/ingest/connectors/sql_connector.py`, and walks no folder.

**The fault.** The probe `_WRITES` asked `has_table_privilege(current_user, <name>, ...)` about
every table of the database, the name built from `schemaname` and `tablename`. Postgres looks a
name up by schema, and refuses a schema the login has no USAGE on (`permission denied for schema
<name>`), so a read-only login on any database that holds a schema it cannot use was refused with a
database error instead of being checked. SE6b's mart makes exactly such a schema
(`osprey_report_control`), and twelve live tests of `test_sql_connector_live.py` failed on GitHub
from SE6b's merge on.

**The shape that is right.** The probe asks about each table by its OID (`pg_class.oid`), which
looks no schema up by name, and so asks the same question of every table whether or not the login
may use its schema. It must also stay as strict as it was: the same four privileges, still counted
for any table of any schema, and the owner and superuser branches untouched. The live proof of that
is in `test_sql_connector_live.py` (a Postgres is needed; this file has none).

What a mistake would do, and the case that catches it (rule 15: each planted fault is the text the
code really has, or a spelling of the same fault, and each is checked to be refused *for the reason
it claims*, not by a fall-through):
- today's probe, by name, left in place —
  `test_the_probe_as_main_had_it_is_refused_for_asking_by_name`
  (the planted text is main's `_WRITES` verbatim, set in a module as the connector holds it);
- the same fault spelt another way (`format`, `to_regclass`, a `::regclass` cast) —
  `test_other_spellings_of_asking_by_name_are_refused_for_asking_by_name`;
- the fix made by dropping a privilege, or the check —
  `test_a_probe_that_asks_about_fewer_privileges_is_refused`,
  `test_a_probe_with_no_privilege_check_is_refused`;
- the fixed text — `test_the_probe_by_oid_is_accepted`; and the connector's own file —
  `test_the_connectors_probe_asks_by_oid`.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

CONNECTOR = (
    Path(__file__).parents[3] / "OspreyFlow_Core/services/ingest/connectors/sql_connector.py"
)

#: The four privileges the probe has always asked about; none may be dropped.
PRIVILEGES = ("INSERT", "UPDATE", "DELETE", "TRUNCATE")
#: What builds a table's name in SQL: a column that holds one, quoting it, joining parts, a cast of
#: text to a relation, or a function that does either.
_BY_NAME = re.compile(
    r"schemaname|tablename|relname|nspname|quote_ident|\|\||regclass|format\s*\(|concat",
    re.IGNORECASE,
)
_OID = re.compile(r"^\w+\.oid$|^oid$", re.IGNORECASE)

BY_NAME = "asks has_table_privilege about a table by a name built from its schema and its table"
NOT_OID = "asks has_table_privilege about something that is not a table's OID"
NO_CHECK = "has no has_table_privilege check of the tables"
NO_PROBE = "has no _WRITES probe"


def _probe_text(source: str) -> str | None:
    """The string `_WRITES` is set to at module level, read from the syntax, not by pattern."""
    for node in ast.parse(source).body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "_WRITES" for t in node.targets)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            return node.value.value
    return None


def _calls(sql: str, function: str) -> list[list[str]]:
    """Each call of `function` in `sql`, as its arguments split at the commas that are not inside
    brackets or quotes."""
    found: list[list[str]] = []
    for opening in re.finditer(rf"\b{function}\s*\(", sql, re.IGNORECASE):
        depth, quote, current, args = 1, "", "", []
        for char in sql[opening.end() :]:
            if quote:
                quote = "" if char == quote else quote
            elif char in "'\"":
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    break
            elif char == "," and depth == 1:
                args.append(current.strip())
                current = ""
                continue
            current += char
        args.append(current.strip())
        found.append(args)
    return found


def probe_violations(source: str) -> list[str]:
    """What is wrong with the probe in this connector source, as reasons (none: nothing)."""
    sql = _probe_text(source)
    if sql is None:
        return [NO_PROBE]
    calls = _calls(sql, "has_table_privilege")
    if not calls:
        return [NO_CHECK]
    wrong: list[str] = []
    for args in calls:
        # (table, privilege) or (user, table, privilege): the table is the one before the privilege.
        table, privilege = (args[-2] if len(args) > 1 else ""), args[-1]
        if _BY_NAME.search(table):
            wrong.append(f"{BY_NAME}: {table}")
        elif not _OID.match(table):
            wrong.append(f"{NOT_OID}: {table!r}")
        missing = [p for p in PRIVILEGES if p not in privilege.upper()]
        if missing:
            wrong.append(f"asks about fewer privileges than before; missing {missing}")
    return wrong


def _module(sql: str) -> str:
    """The probe set in a module the way the connector sets it."""
    return f'import asyncpg\n\n_WRITES = """{sql}"""\n\n\ndef other() -> None:\n    return None\n'


#: `_WRITES` as main has it (the text this slice replaces), verbatim.
MAIN_PROBE = """
SELECT
  (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) AS superuser,
  (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relowner = (SELECT oid FROM pg_roles WHERE rolname = current_user)
      AND c.relkind IN ('r', 'p') AND n.nspname NOT IN ('pg_catalog', 'information_schema')
      AND n.nspname NOT LIKE 'pg_temp%') AS owned,
  (SELECT count(*) FROM pg_tables
    WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
      AND has_table_privilege(
        current_user, quote_ident(schemaname) || '.' || quote_ident(tablename),
        'INSERT, UPDATE, DELETE, TRUNCATE')) AS writable
"""

#: The same question asked of each table by its OID.
FIXED_PROBE = """
SELECT
  (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) AS superuser,
  (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relowner = (SELECT oid FROM pg_roles WHERE rolname = current_user)
      AND c.relkind IN ('r', 'p') AND n.nspname NOT IN ('pg_catalog', 'information_schema')
      AND n.nspname NOT LIKE 'pg_temp%') AS owned,
  (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind IN ('r', 'p') AND n.nspname NOT IN ('pg_catalog', 'information_schema')
      AND has_table_privilege(current_user, c.oid, 'INSERT, UPDATE, DELETE, TRUNCATE')) AS writable
"""


def test_the_connectors_probe_asks_by_oid() -> None:
    assert CONNECTOR.is_file(), CONNECTOR
    assert probe_violations(CONNECTOR.read_text(encoding="utf-8")) == []


def test_the_probe_as_main_had_it_is_refused_for_asking_by_name() -> None:
    wrong = probe_violations(_module(MAIN_PROBE))
    assert len(wrong) == 1 and wrong[0].startswith(BY_NAME), wrong


@pytest.mark.parametrize(
    "table",
    [
        "format('%I.%I', schemaname, tablename)::regclass",
        "to_regclass(schemaname || '.' || tablename)",
        "(quote_ident(schemaname) || '.' || quote_ident(tablename))::regclass",
        "concat(schemaname, '.', tablename)",
    ],
)
def test_other_spellings_of_asking_by_name_are_refused_for_asking_by_name(table: str) -> None:
    sql = MAIN_PROBE.replace("quote_ident(schemaname) || '.' || quote_ident(tablename)", table)
    assert table in sql
    wrong = probe_violations(_module(sql))
    assert len(wrong) == 1 and wrong[0].startswith(BY_NAME), wrong


def test_the_probe_by_oid_is_accepted() -> None:
    assert probe_violations(_module(FIXED_PROBE)) == []


@pytest.mark.parametrize("dropped", PRIVILEGES)
def test_a_probe_that_asks_about_fewer_privileges_is_refused(dropped: str) -> None:
    privileges = ", ".join(p for p in PRIVILEGES if p != dropped)
    sql = FIXED_PROBE.replace("INSERT, UPDATE, DELETE, TRUNCATE", privileges)
    assert dropped not in sql.split("has_table_privilege")[1]
    wrong = probe_violations(_module(sql))
    assert len(wrong) == 1 and wrong[0].startswith("asks about fewer privileges"), wrong


def test_a_probe_that_asks_about_something_that_is_not_an_oid_is_refused() -> None:
    sql = FIXED_PROBE.replace("current_user, c.oid,", "current_user, c.relname,")
    wrong = probe_violations(_module(sql))
    assert len(wrong) == 1 and wrong[0].startswith(BY_NAME), wrong
    sql = FIXED_PROBE.replace("current_user, c.oid,", "current_user, 42,")
    wrong = probe_violations(_module(sql))
    assert len(wrong) == 1 and wrong[0].startswith(NOT_OID), wrong


def test_a_probe_with_no_privilege_check_is_refused() -> None:
    sql = re.sub(r"AND has_table_privilege\([^)]*\)", "", FIXED_PROBE)
    assert "has_table_privilege" not in sql
    assert probe_violations(_module(sql)) == [NO_CHECK]


def test_a_source_with_no_probe_is_refused() -> None:
    assert probe_violations("import asyncpg\n") == [NO_PROBE]
    # A probe moved into a function, or built from pieces, is not read as one: refused.
    assert probe_violations('def probe() -> str:\n    _WRITES = "x"\n    return _WRITES\n') == [
        NO_PROBE
    ]
