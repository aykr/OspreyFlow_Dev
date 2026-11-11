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
_FINISHED = {"SUCCEEDED", "FAILED", "CANCELLED"}

#: One pass over the statement, so a comment's marker inside a string value (`'--'`) is a string,
#: and a string's quote inside a comment is a comment (the orchestrator's review of L1.9, round 1:
#: comments stripped first by their own pattern took `'--'` as the start of one, and the text after
#: it, a second statement or a table, was never checked).
_TOKEN = re.compile(
    # A `--` comment ends at a carriage return as at a newline, as Trino's lexer ends it
    # (SIMPLE_COMMENT); read to the newline alone, the rest of a line after `--\r` was a comment
    # here and a query to Athena (the lane's own reviewer, round 1).
    r"""(?P<comment>--[^\r\n]*|/\*.*?\*/)"""
    r"""|(?P<string>'(?:[^']|'')*')"""
    r"""|(?P<quoted>"(?:[^"]|"")*"|`[^`]*`)"""
    r"""|(?P<word>[A-Za-z_][A-Za-z0-9_$]*)"""
    r"""|(?P<number>[0-9]+(?:\.[0-9]*)?(?:[eE][+-]?[0-9]+)?)"""
    r"""|(?P<punct>[()\[\],.;])"""
    r"""|(?P<other>\S)""",
    re.DOTALL,
)
_WRITES = {"insert", "unload", "create", "drop", "delete", "update", "merge", "alter"}

Token = tuple[str, str]


def _tokens(statement: str) -> list[Token]:
    """The statement as (kind, text) tokens, comments set aside. A keyword is a `word`, lower-cased;
    a quoted identifier is a `quoted` name, unquoted and lower-cased (Athena folds both), and never
    a keyword (`"where"` is a name); a string value is one `string` token, kept whole."""
    found: list[Token] = []
    for match in _TOKEN.finditer(statement):
        kind = match.lastgroup or "other"
        text = match.group()
        if kind == "comment":
            continue
        if kind == "quoted":
            found.append(("quoted", text[1:-1].replace('""', '"').lower()))
        elif kind == "word":
            found.append(("word", text.lower()))
        else:
            found.append((kind, text))
    return found


def one_select(statement: str) -> str:
    """The named query's statement if it is one SELECT (or WITH … SELECT); refused otherwise.
    Comments are set aside first, so one cannot hide a statement's first word. A `;` anywhere but at
    the end is refused even inside a quoted value: failing closed costs a client one re-saved
    query, failing open would run a second statement."""
    tokens = _tokens(statement)
    first = tokens[0] if tokens else ("end", "")
    ends = [n for n, token in enumerate(tokens) if token == ("punct", ";")]
    second = bool(ends) and any(token != ("punct", ";") for token in tokens[ends[0] :])
    hidden = any(";" in text for kind, text in tokens if kind in {"string", "quoted"})
    # A WITH's body is a SELECT; one naming a writing statement anywhere is refused too.
    writes = first == ("word", "with") and any(
        kind == "word" and text in _WRITES for kind, text in tokens
    )
    if first not in {("word", "select"), ("word", "with")} or second or hidden or writes:
        raise ConnectorRefused(
            "the named query is not a read: a source runs only a single SELECT (or WITH … SELECT), "
            "never a statement that writes; nothing was sent or read"
        )
    return statement


class _Outside(Exception):
    """A relation outside the connection's databases, or a table function."""


class _Unsure(Exception):
    """A shape the checker does not follow."""


#: Words a SELECT's clauses end at.
_SELECT_STOPS = frozenset({
    "from", "where", "group", "having", "window", "union", "intersect", "except", "order",
    "offset", "limit", "fetch",
})  # fmt: skip
#: What may follow a whole SELECT (besides `)`, `;` and the end).
_AFTER_SELECT = frozenset({"union", "intersect", "except", "order", "offset", "limit", "fetch"})
_JOINS = frozenset({"join", "inner", "left", "right", "full", "cross", "natural"})
#: Where a join's ON condition, or a time-travel point, ends.
_RELATION_END = _SELECT_STOPS | _JOINS | {"on", "using", "as", "tablesample"}
#: Words that bring in a relation: outside a FROM list, or not where one belongs, not followed.
_RELATION_WORDS = frozenset({"from", "join", "lateral", "unnest", "table", "select", "values",
                             "with"})  # fmt: skip
#: Words never read as a name: Athena's (Trino's) reserved words and this checker's clause words.
_RESERVED = _SELECT_STOPS | _JOINS | _RELATION_WORDS | {
    "all", "alter", "and", "as", "between", "by", "case", "cast", "constraint", "create", "cube",
    "current_date", "current_time", "current_timestamp", "deallocate", "delete", "describe",
    "distinct", "drop", "else", "end", "escape", "execute", "exists", "extract", "false", "for",
    "grouping", "in", "insert", "into", "is", "like", "localtime", "localtimestamp", "normalize",
    "not", "null", "on", "or", "outer", "prepare", "recursive", "rollup", "skip", "then", "true",
    "uescape", "using", "when", "tablesample", "match_recognize",
}  # fmt: skip


class _Relations:
    """A recursive-descent reading of one query, as far as its relations go: every query (the
    statement, each WITH, each subquery at any depth, each side of a set operation), every FROM
    list and every relation in it (a table, a parenthesised join, a subquery, LATERAL, UNNEST),
    each join and each comma. Expressions are passed over, except that every subquery in them is
    read as a query. A table outside the connection's databases raises `_Outside`; anything not
    followed raises `_Unsure` (the orchestrator's review of L1.9, round 1: the scan this replaces
    went back to looking for FROM or JOIN after a subquery, a join or a TABLESAMPLE, so a later
    `, db.table` was never checked)."""

    def __init__(self, tokens: list[Token], settings: AthenaConnectionSettings) -> None:
        self.tokens, self.i = tokens, 0
        self.databases = {d.lower() for d in settings.databases}
        self.catalog = settings.catalog.lower()

    # --- reading tokens -----------------------------------------------------------------------

    def _peek(self, ahead: int = 0) -> Token:
        at = self.i + ahead
        return self.tokens[at] if at < len(self.tokens) else ("end", "")

    def _word(self, *words: str, ahead: int = 0) -> bool:
        kind, text = self._peek(ahead)
        return kind == "word" and text in words

    def _punct(self, mark: str, ahead: int = 0) -> bool:
        return self._peek(ahead) == ("punct", mark)

    def _expect_word(self, word: str) -> None:
        if not self._word(word):
            raise _Unsure
        self.i += 1

    def _expect_punct(self, mark: str) -> None:
        if not self._punct(mark):
            raise _Unsure
        self.i += 1

    def _is_name(self, ahead: int = 0) -> bool:
        kind, text = self._peek(ahead)
        return kind == "quoted" or (kind == "word" and text not in _RESERVED)

    def _name(self) -> str:
        if not self._is_name():
            raise _Unsure
        self.i += 1
        return self.tokens[self.i - 1][1]

    # --- queries ------------------------------------------------------------------------------

    def statement(self) -> None:
        if any(t == ("other", q) for t in self.tokens for q in ("'", '"', "`")):
            raise _Unsure  # a quote never closed
        self.query()
        while self._punct(";"):
            self.i += 1
        if self._peek()[0] != "end":
            raise _Unsure

    def query(self) -> None:
        if self._word("with"):
            self.i += 1
            if self._word("recursive"):
                self.i += 1
            while True:
                self._name()
                if self._punct("("):
                    self._column_names()
                self._expect_word("as")
                self._expect_punct("(")
                self.query()
                self._expect_punct(")")
                if not self._punct(","):
                    break
                self.i += 1
        self._query_term()
        while self._word("union", "intersect", "except"):
            self.i += 1
            if self._word("all", "distinct"):
                self.i += 1
            self._query_term()
        while self._word("order", "offset", "limit", "fetch"):
            commas = self._word("order")
            self.i += 1
            self._expression(commas=commas, stops=_AFTER_SELECT)

    def _query_term(self) -> None:
        if self._word("select"):
            self._select()
        elif self._word("values"):
            self.i += 1
            self._expression(commas=True, stops=_SELECT_STOPS)
        elif self._punct("("):
            self.i += 1
            self.query()
            self._expect_punct(")")
        else:
            raise _Unsure  # `TABLE t`, or anything else

    def _select(self) -> None:
        self.i += 1
        self._expression(commas=True, stops=_SELECT_STOPS)
        if self._word("from"):
            self.i += 1
            self._relation_list()
        while self._word("where", "group", "having", "window"):
            commas = self._word("group", "window")
            self.i += 1
            self._expression(commas=commas, stops=_SELECT_STOPS)
        kind, text = self._peek()
        ends = kind == "end" or (kind == "punct" and text in {")", ";"})
        if not ends and not (kind == "word" and text in _AFTER_SELECT):
            raise _Unsure  # a comma, a word or a relation the clauses above do not account for

    # --- relations ----------------------------------------------------------------------------

    def _relation_list(self) -> None:
        while True:
            self._joined()
            if not self._punct(","):
                return
            self.i += 1

    def _joined(self) -> None:
        self._relation()
        while True:
            start = self.i
            natural = self._word("natural")
            if natural:
                self.i += 1
            if self._word("cross"):
                self.i += 1
                self._expect_word("join")
                self._relation()
                continue
            if self._word("inner"):
                self.i += 1
            elif self._word("left", "right", "full"):
                self.i += 1
                if self._word("outer"):
                    self.i += 1
            if not self._word("join"):
                if self.i != start:
                    raise _Unsure
                return
            self.i += 1
            self._relation()
            if natural:
                continue
            if self._word("on"):
                self.i += 1
                self._expression(commas=False, stops=_RELATION_END)
            elif self._word("using"):
                self.i += 1
                self._column_names()
            else:
                raise _Unsure  # a join with no condition

    def _relation(self) -> None:
        kind, text = self._peek()
        if (kind, text) == ("punct", "("):
            ahead = 0
            while self._punct("(", ahead):
                ahead += 1
            self.i += 1
            if self._word("select", "with", "values", ahead=ahead - 1):
                self.query()
            else:
                self._joined()
            self._expect_punct(")")
        elif self._word("lateral"):
            self.i += 1
            self._expect_punct("(")
            self.query()
            self._expect_punct(")")
        elif self._word("unnest"):
            self.i += 1
            if not self._punct("("):
                raise _Unsure
            self._group()
            if self._word("with") and self._word("ordinality", ahead=1):
                self.i += 2
        elif self._word("table"):
            raise _Outside  # a table function reads what its arguments say
        elif self._is_name():
            self._table()
        else:
            raise _Unsure
        self._alias()
        if self._word("tablesample"):
            self.i += 1
            if not self._word("bernoulli", "system"):
                raise _Unsure
            self.i += 1
            if not self._punct("("):
                raise _Unsure
            self._group()

    def _table(self) -> None:
        parts = [self._name()]
        while self._punct(".") and self._peek(1)[0] in {"word", "quoted"}:
            parts.append(self._peek(1)[1])
            self.i += 2
        if self._punct("("):
            raise _Outside  # a table function (`system.query(…)`)
        if len(parts) == 2 and parts[0] not in self.databases:
            raise _Outside
        if len(parts) == 3 and (parts[0] != self.catalog or parts[1] not in self.databases):
            raise _Outside
        if len(parts) > 3:
            raise _Outside
        # One part: the query's own database, already checked, or a WITH's name.
        if self._word("for"):  # an Iceberg table's time travel
            self.i += 1
            if not self._word("timestamp", "version", "system_time", "system_version"):
                raise _Unsure
            self.i += 1
            self._expect_word("as")
            self._expect_word("of")
            self._expression(commas=False, stops=_RELATION_END)

    def _alias(self) -> None:
        if self._word("as"):
            self.i += 1
            self._name()
        elif self._is_name():
            self.i += 1
        else:
            return
        if self._punct("("):
            self._column_names()

    def _column_names(self) -> None:
        self._expect_punct("(")
        self._name()
        while self._punct(","):
            self.i += 1
            self._name()
        self._expect_punct(")")

    # --- expressions --------------------------------------------------------------------------

    def _expression(self, *, commas: bool, stops: frozenset[str]) -> None:
        """Passes over an expression (or a list of them, with `commas`) up to a stop word, `)`,
        `;` or the end; every bracketed group in it through `_group`."""
        while True:
            kind, text = self._peek()
            if kind == "end" or (kind == "punct" and text in {")", "]", ";"}):
                return
            if (kind, text) == ("punct", ",") and not commas:
                return
            if kind == "punct" and text in {"(", "["}:
                self._group()
                continue
            if kind == "word":
                if text in stops:
                    return
                if text == "is":  # IS [NOT] DISTINCT FROM: an operator, not a FROM
                    skip = 2 if self._word("not", ahead=1) else 1
                    if self._word("distinct", ahead=skip) and self._word("from", ahead=skip + 1):
                        self.i += skip + 2
                        continue
                if text == "with" and self._word("ties", ahead=1):
                    self.i += 2
                    continue
                if text in _RELATION_WORDS:
                    raise _Unsure
            self.i += 1

    def _group(self) -> None:
        """A bracketed group: a subquery is read as a query; anything else is passed over, a
        function's own FROM (`extract(year FROM d)`, `trim(' ' FROM s)`) being no relation."""
        close = ")" if self._peek()[1] == "(" else "]"
        self.i += 1
        if close == ")" and self._word("select", "with", "values"):
            self.query()
            self._expect_punct(")")
            return
        while True:
            kind, text = self._peek()
            if kind == "end":
                raise _Unsure
            if kind == "punct" and text == close:
                self.i += 1
                return
            if kind == "punct" and text in {")", "]", ";"}:
                raise _Unsure
            if kind == "punct" and text in {"(", "["}:
                self._group()
                continue
            if kind == "word" and text in _RELATION_WORDS - {"from", "with"}:
                raise _Unsure
            self.i += 1


def refuse_relations_outside(statement: str, settings: AthenaConnectionSettings) -> None:
    """Every table a named query reads, in every FROM list at every depth, must be in one of the
    connection's databases and its catalog: `table` (the query's own database, already checked),
    `database.table`, or `catalog.database.table`. A table function is refused. **Fails closed**:
    a shape `_Relations` does not follow is refused, never passed over; that costs a client a
    re-saved query, where failing open would read a database the administrator did not name
    (rule 3; the orchestrator's review of L1.9, round 1). The role's own IAM policy is the second
    line, not the first."""
    try:
        _Relations(_tokens(statement), settings).statement()
    except _Outside as outside:
        raise ConnectorRefused(
            "the named query reads a table outside the databases this connection names "
            f"({', '.join(settings.databases)}); nothing was sent or read"
        ) from outside
    except (_Unsure, RecursionError) as unsure:
        raise ConnectorRefused(
            "the named query is written in a shape this check cannot follow, so it is not shown to "
            f"read only the databases this connection names ({', '.join(settings.databases)}): "
            "save it more plainly; nothing was sent or read"
        ) from unsure


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


def _refuse_a_column_named_twice(columns: list[str], where: str) -> None:
    """`SELECT a.id, b.id` gives two columns named `id`. A row is kept by column name, so the second
    value would be written in both cells (the orchestrator's review of L1.9, round 1, item 3; rule
    2): refused, as S3 refuses a header naming a column twice."""
    seen: set[str] = set()
    for name in columns:
        if name in seen:
            raise ConnectorRefused(
                f"{where} names the column {name!r} twice: give each column its own name (AS) in "
                "the query; nothing was written"
            )
        seen.add(name)


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
            _refuse_a_column_named_twice(columns, where)
        found = result.get("Rows", [])
        for number, row in enumerate(found):
            values = [d.get("VarCharValue") for d in row.get("Data", [])]
            if first and number == 0 and values == columns:
                continue  # the header Athena puts first
            if len(values) != len(columns):
                # Never a value dropped, nor a cell made up (rule 2; the review, round 1, item 3).
                raise ConnectorRefused(
                    f"row {len(rows) + 1} of {where} has {len(values)} values for its "
                    f"{len(columns)} columns; nothing was written"
                )
            taken += sum(len(v.encode("utf-8")) for v in values if v is not None)
            rows.append({c: (v if v != "" else None) for c, v in zip(columns, values, strict=True)})
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
