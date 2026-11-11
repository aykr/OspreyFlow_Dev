"""The Athena connector (L1.9 part 1; ADR-148 decisions 4 and 7; `09_INGEST_STUDIO.md` §2).

A source on an Athena connection reads **a table** of one of the connection's databases, whole, or
**a named query** saved in the connection's workgroup. Its rows land, through
`reads.write_snapshot`, as the source's one CSV file, so everything after is the path every
connector source takes.

- **No expression is written here** (rule 8). A table's statement is made from its two checked
  names, quoted: `SELECT * FROM "db"."table"`. A named query is the client's own, saved in Athena;
  it is run only if it is saved in the connection's workgroup, against one of its databases, and is
  one SELECT (or WITH … SELECT): anything else (DDL, CTAS, INSERT, UNLOAD, a second statement) is
  refused **before it is sent**, since a read-only connector must never ask Athena to write.
- **No key** (ADR-148): the client is botocore's, signed in as the deployment's own cloud identity
  (`connector_reads.Readers`).
- **Results are paged**, 1,000 rows a page (Athena's most), header first. **Never truncated
  silently** (rule 2): past the row, byte or page cap the read is refused whole and paging stops;
  nothing is written. A query not finished within `DEADLINE_SECONDS` is stopped and refused.
- **Athena's refusals are refused in words**, never read as no rows: a query that does not parse
  or names a table that does not exist fails as an execution (`FAILED`, with its reason); a
  principal the workgroup does not grant is refused at the request. The words never carry the
  principal's ARN.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from schemas.sources import AthenaConnectionSettings, AthenaRead

from . import reads
from .reads import ConnectorRefused, ReadOverCap, ReadRows

#: Athena's most rows a page.
PAGE_ROWS = 1_000
#: The most pages one read follows (rule 2), as for an API.
MAX_PAGES = 1_000
#: How long a query may run before it is stopped and the read refused.
DEADLINE_SECONDS = 300.0
_POLL_SECONDS = 1.0
_COMMENT = re.compile(r"--[^\n]*(\n|$)|/\*.*?\*/", re.DOTALL)
_FINISHED = {"SUCCEEDED", "FAILED", "CANCELLED"}


def one_select(statement: str) -> str:
    """The named query's statement if it is one SELECT (or WITH … SELECT); refused otherwise.
    Comments are set aside first, so one cannot hide a statement's first word. A `;` anywhere but at
    the end is refused even inside a quoted value: failing closed costs a client one re-saved
    query, failing open would run a second statement."""
    bare = _COMMENT.sub(" ", statement).strip().rstrip(";").strip()
    first = bare.split(None, 1)[0].upper() if bare else ""
    # A WITH's body is a SELECT; one naming a writing statement anywhere is refused too.
    writes = first == "WITH" and re.search(
        r"\b(INSERT|UNLOAD|CREATE|DROP|DELETE|UPDATE|MERGE|ALTER)\b", bare, re.IGNORECASE
    )
    if first not in {"SELECT", "WITH"} or ";" in bare or writes:
        raise ConnectorRefused(
            "the named query is not a read: a source runs only a single SELECT (or WITH … SELECT), "
            "never a statement that writes; nothing was sent or read"
        )
    return statement


_TOKEN = re.compile(
    r"""(?P<string>'(?:[^']|'')*')|(?P<quoted>"(?:[^"]|"")*"|`[^`]*`)|(?P<word>[A-Za-z_][A-Za-z0-9_$]*)"""
    r"""|(?P<punct>[(),.])|(?P<other>\S)""",
    re.DOTALL,
)
#: After FROM or JOIN, what is not a table: an array unnested, a lateral subquery.
_NOT_A_TABLE = {"unnest", "lateral"}


def _tokens(statement: str) -> list[tuple[str, str]]:
    """The statement as (kind, text) tokens, comments set aside, string values kept whole (a FROM
    inside a quoted value is no relation), identifiers lower-cased and unquoted."""
    found: list[tuple[str, str]] = []
    for match in _TOKEN.finditer(_COMMENT.sub(" ", statement)):
        kind = match.lastgroup or "other"
        text = match.group()
        if kind == "quoted":
            found.append(("name", text[1:-1].replace('""', '"').lower()))
        elif kind == "word":
            found.append(("name", text.lower()))
        elif kind != "string":
            found.append((kind, text))
    return found


def refuse_relations_outside(statement: str, settings: AthenaConnectionSettings) -> None:
    """Every table a named query reads (each name after FROM or JOIN, and each in a FROM's comma
    list) must be in one of the connection's databases and its catalog: `table` (the query's own
    database, already checked), `database.table`, or `catalog.database.table`. A table function
    (`TABLE(…)`) is refused. Anything not understood is refused: failing closed costs a client a
    re-saved query; failing open would read a database the administrator did not name (the lane
    review of L1.9; rule 3). The role's own IAM policy is the second line, not the first."""
    tokens = _tokens(statement)
    databases = {d.lower() for d in settings.databases}
    outside = ConnectorRefused(
        "the named query reads a table outside the databases this connection names "
        f"({', '.join(settings.databases)}); nothing was sent or read"
    )
    # Whether each open parenthesis is a function's arguments (`extract(year FROM t.col)`, whose
    # FROM is no relation) or a query or a relation group.
    parens: list[bool] = []
    i = 0
    while i < len(tokens):
        kind, text = tokens[i]
        if text == "(":
            before = tokens[i - 1] if i else ("punct", "")
            after = tokens[i + 1][1] if i + 1 < len(tokens) else ""
            function = before[0] == "name" and before[1] not in {
                "from", "join", "in", "exists", "as", "lateral", "unnest",
            } and after not in {"select", "with"}  # fmt: skip
            parens.append(function)
        elif text == ")" and parens:
            parens.pop()
        if kind == "name" and text in {"from", "join"} and not any(parens[-1:]):
            i = _relations(tokens, i + 1, text == "from", databases, settings, outside)
            continue
        i += 1


def _relations(
    tokens: list[tuple[str, str]],
    i: int,
    comma_list: bool,
    databases: set[str],
    settings: AthenaConnectionSettings,
    outside: ConnectorRefused,
) -> int:
    """Checks the relation (or, after FROM, the comma list of relations) starting at `i`; returns
    where scanning goes on."""
    while i < len(tokens):
        kind, text = tokens[i]
        if text == "(" or (kind == "name" and text in _NOT_A_TABLE):
            return i  # a subquery or an unnested array: its own FROMs are scanned in turn
        if kind != "name" or text == "table":
            raise outside
        parts = [text]
        i += 1
        while i + 1 < len(tokens) and tokens[i][1] == "." and tokens[i + 1][0] == "name":
            parts.append(tokens[i + 1][1])
            i += 2
        if len(parts) == 2 and parts[0] not in databases:
            raise outside
        if len(parts) == 3 and (parts[0] != settings.catalog.lower() or parts[1] not in databases):
            raise outside
        if len(parts) > 3:
            raise outside
        # An alias, with or without AS, and its column list.
        if i < len(tokens) and tokens[i][1] == "as":
            i += 1
        if i < len(tokens) and tokens[i][0] == "name" and tokens[i][1] not in _CLAUSE:
            i += 1
        if i < len(tokens) and tokens[i][1] == "(":
            depth = 0
            while i < len(tokens):
                depth += {"(": 1, ")": -1}.get(tokens[i][1], 0)
                i += 1
                if depth == 0:
                    break
        if comma_list and i < len(tokens) and tokens[i][1] == ",":
            i += 1
            continue
        return i
    return i


#: Words that end a relation (so are never read as its alias).
_CLAUSE = {
    "where", "group", "order", "having", "limit", "offset", "join", "inner", "left", "right",
    "full", "cross", "natural", "on", "using", "union", "intersect", "except", "window",
    "fetch", "tablesample", "for", "with", "select",
}  # fmt: skip
_ARN = re.compile(r"arn:aws[a-z-]*:[^\s'\",;)]+")
_KEY_ID = re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{12,}\b")


def without_identities(words: str) -> str:
    """Athena's own words with any ARN or access key id taken out: a FAILED reason from Glue or Lake
    Formation names the role it refused (`User: arn:aws:sts::…:assumed-role/…`)."""
    return _KEY_ID.sub("(an access key)", _ARN.sub("(a cloud identity)", words))


def _code(error: ClientError) -> str:
    return str(error.response.get("Error", {}).get("Code", ""))


def _message(error: ClientError) -> str:
    return str(error.response.get("Error", {}).get("Message", ""))


def refused_request(error: ClientError | BotoCoreError) -> ConnectorRefused:
    """Athena's refusal of a request, in words: never an ARN or an access key id."""
    if isinstance(error, BotoCoreError):
        return ConnectorRefused(
            f"Athena could not be reached ({type(error).__name__}); nothing was read"
        )
    code = _code(error)
    if code == "AccessDeniedException":
        return ConnectorRefused(
            "Athena refused the deployment's cloud role (access denied): the role may not use this "
            "workgroup or database; nothing was read"
        )
    if code in {"UnrecognizedClientException", "InvalidSignatureException",
                "ExpiredTokenException", "InvalidClientTokenId"}:  # fmt: skip
        return ConnectorRefused(
            "Athena did not recognise the deployment's cloud identity (its credentials are "
            "missing, wrong or expired); nothing was read"
        )
    if code == "InvalidRequestException":
        return ConnectorRefused(
            f"Athena refused the request: {without_identities(_message(error))}; nothing was read"
        )
    return ConnectorRefused(f"Athena refused the request ({code or 'unknown'}); nothing was read")


def _statement(
    client: Any, settings: AthenaConnectionSettings, read: AthenaRead
) -> tuple[str, str]:
    """The statement to run and its database, every check made before anything is sent."""
    outside = (
        "the source reads a database this connection does not name ({}); nothing was sent or read"
    )
    if read.table is not None:
        database, table = read.table.split(".")
        if database not in settings.databases:
            raise ConnectorRefused(outside.format(", ".join(settings.databases)))
        return f'SELECT * FROM "{database}"."{table}"', database
    try:
        found = client.get_named_query(NamedQueryId=read.named_query)["NamedQuery"]
    except ClientError as error:
        if _code(error) == "InvalidRequestException" and "not found" in _message(error).lower():
            raise ConnectorRefused(
                "Athena holds no named query of that id; nothing was sent or read"
            ) from error
        raise refused_request(error) from error
    except BotoCoreError as error:
        raise refused_request(error) from error
    if found.get("WorkGroup", "primary") != settings.workgroup:
        raise ConnectorRefused(
            "the named query is saved in another workgroup than this connection's; nothing was "
            "sent or read"
        )
    if found.get("Database") not in settings.databases:
        raise ConnectorRefused(outside.format(", ".join(settings.databases)))
    statement = one_select(str(found.get("QueryString", "")))
    refuse_relations_outside(statement, settings)
    return statement, str(found["Database"])


def _wait(
    client: Any,
    execution_id: str,
    *,
    sleep: Callable[[float], None],
    clock: Callable[[], float],
) -> None:
    """Until the query finishes; a failure refused with Athena's own reason, a query past the
    deadline stopped and refused."""
    started = clock()
    while True:
        status = client.get_query_execution(QueryExecutionId=execution_id)["QueryExecution"]
        state = status["Status"]["State"]
        if state == "SUCCEEDED":
            return
        if state in _FINISHED:
            reason = without_identities(status["Status"].get("StateChangeReason") or state.lower())
            raise ConnectorRefused(f"Athena could not run the query: {reason}; nothing was read")
        if clock() - started > DEADLINE_SECONDS:
            try:
                client.stop_query_execution(QueryExecutionId=execution_id)
            finally:
                raise ConnectorRefused(  # noqa: B012 (the refusal is the answer either way)
                    f"Athena's query did not finish within {DEADLINE_SECONDS:.0f} seconds, so it "
                    "was stopped; nothing was read"
                )
        sleep(_POLL_SECONDS)


def _results(client: Any, execution_id: str, where: str) -> ReadRows:
    """Every page of the results, the header taken from the first page's first row."""
    columns: list[str] = []
    rows: list[dict[str, str | None]] = []
    taken, token, first = 0, None, True
    for _ in range(MAX_PAGES):
        ask: dict[str, Any] = {"QueryExecutionId": execution_id, "MaxResults": PAGE_ROWS}
        if token is not None:
            ask["NextToken"] = token
        page = client.get_query_results(**ask)
        result = page["ResultSet"]
        if first:
            columns = [c["Name"] for c in result["ResultSetMetadata"]["ColumnInfo"]]
        found = result.get("Rows", [])
        for number, row in enumerate(found):
            values = [d.get("VarCharValue") for d in row.get("Data", [])]
            if first and number == 0 and values == columns:
                continue  # the header Athena puts first
            taken += sum(len(v.encode("utf-8")) for v in values if v is not None)
            rows.append(
                {c: (v if v != "" else None) for c, v in zip(columns, values, strict=False)}
            )
        first = False
        if len(rows) > reads.MAX_ROWS:
            raise ReadOverCap(
                f"{where} holds more than {reads.MAX_ROWS} rows, more than one read may hold; "
                "nothing was written (rule 2)"
            )
        if taken > reads.MAX_BYTES:
            raise ReadOverCap(
                f"{where} comes to more than {reads.MAX_BYTES} bytes, more than one read may take; "
                "nothing was written (rule 2)"
            )
        token = page.get("NextToken")
        if not token:
            return ReadRows(columns=columns, rows=rows)
    raise ReadOverCap(
        f"{where} gave more than {MAX_PAGES} pages, more than one read may follow; nothing was "
        "written (rule 2)"
    )


def read_athena(
    client: Any,
    settings: AthenaConnectionSettings,
    read: AthenaRead,
    *,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> ReadRows:
    """Every row the table or named query gives, through `client` (botocore's Athena client)."""
    statement, database = _statement(client, settings, read)
    start: dict[str, Any] = {
        "QueryString": statement,
        "QueryExecutionContext": {"Database": database, "Catalog": settings.catalog},
        "WorkGroup": settings.workgroup,
    }
    if settings.results_location:
        start["ResultConfiguration"] = {"OutputLocation": settings.results_location}
    where = f"Athena's {'table ' + read.table if read.table else 'named query'}"
    try:
        execution_id = client.start_query_execution(**start)["QueryExecutionId"]
        _wait(client, execution_id, sleep=sleep, clock=clock)
        return _results(client, execution_id, where)
    except (ClientError, BotoCoreError) as error:
        raise refused_request(error) from error
