"""A recorded Athena behind the real botocore client (L1.9 part 1; `process/CLAUDE.md` rule 15).

The client is botocore's own, built from Athena's real service model: it serialises each request,
signs it and parses each answer exactly as against Athena. Only the network is replaced, by a
`before-send` handler answering from `golden/athena/recorded.json`. **It refuses what Athena
refuses** (rule 15's second worked example), not only what it grants:

- a principal the workgroup does not grant (`AccessDeniedException`), and a key it does not know at
  all (`UnrecognizedClientException`);
- a workgroup that does not exist; a query with no results location where its workgroup names none;
- a page asked for over 1,000 rows, a page token it did not give, results of a query not finished;
- a named query or an execution it does not hold;
- a query that does not parse, and a catalog, database or table that does not exist, each
  **failing as an execution** (`FAILED`, with its `AthenaError`), as Athena reports them, not as a
  refused request. Every table after FROM or JOIN is resolved, not only the first: an unqualified
  one against the execution's database, a two-part one against its catalog, and the execution's
  own catalog (`QueryExecutionContext.Catalog`) is checked too (the orchestrator's review of L1.9,
  round 1, item 7: the fixture had ignored the catalog and looked only at the first FROM).

It also records every query it was sent, so a test can prove a statement was never sent at all.
Every value is synthetic (rule 9).
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import botocore.session
from botocore.awsrequest import AWSPreparedRequest, AWSResponse
from botocore.config import Config

RECORDED = json.loads((Path(__file__).parent / "golden" / "athena" / "recorded.json").read_text())
#: The fixture's own synthetic keys: one granted, one known but not granted the workgroup.
GRANTED_KEY = "AKIDSYNTHETICGRANTED"
REFUSED_KEY = "AKIDSYNTHETICREFUSED"
_KNOWN = {GRANTED_KEY, REFUSED_KEY}
_PART = r'(?:"[^"]+"|[A-Za-z_][A-Za-z0-9_]*)'
#: A relation's name at the start of a FROM list's item: one, two or three parts.
_NAME = re.compile(rf"^\s*({_PART}(?:\s*\.\s*{_PART}){{0,2}})")
_FROM = re.compile(r"\bFROM\b", re.IGNORECASE)
#: Where a FROM list ends, at its own depth.
_LIST_END = re.compile(r"\b(WHERE|GROUP|ORDER|LIMIT|HAVING|UNION|INTERSECT|EXCEPT|OFFSET|FETCH|"
                       r"WINDOW)\b", re.IGNORECASE)  # fmt: skip
#: What separates a FROM list's items: a comma, or a join's own words.
_ITEM = re.compile(r",|\b(?:NATURAL\s+|CROSS\s+|INNER\s+|(?:LEFT|RIGHT|FULL)\s+(?:OUTER\s+)?)?JOIN\b",
                   re.IGNORECASE)  # fmt: skip
#: A FROM that is no relation's: a function's own (`extract(year FROM d)`), or IS DISTINCT FROM.
_NOT_A_FROM = re.compile(r"\b(?:EXTRACT|SUBSTRING|TRIM)\s*\([^()]*\)|\bIS\s+(?:NOT\s+)?DISTINCT\s+FROM\b",
                         re.IGNORECASE)  # fmt: skip


def relations(query: str) -> list[str]:
    """Every relation's name in each FROM list, as Athena reads them: after FROM, after each comma
    and each JOIN at the list's own depth, up to the list's end (the lane's own reviewer, round 1:
    the fixture had read only the name after FROM or JOIN, so a missing table after a comma read as
    rows). String values are blanked first, and a function's FROM is none."""
    text = _NOT_A_FROM.sub(" x ", re.sub(r"'(?:[^']|'')*'", "''", query))
    found: list[str] = []
    for start in _FROM.finditer(text):
        depth, at, items, item = 0, start.end(), [], ""
        while at < len(text):
            char = text[at]
            if depth == 0 and (char == ")" or _LIST_END.match(text, at)):
                break
            if depth == 0 and (cut := _ITEM.match(text, at)):
                items.append(item)
                item, at = "", cut.end()
                continue
            depth += {"(": 1, ")": -1}.get(char, 0)
            item += char
            at += 1
        for piece in [*items, item]:
            if piece.strip().startswith("(") or not (name := _NAME.match(piece)):
                continue
            found.append(name.group(1))
    return found
#: A WITH's own names, which are no table.
_WITH_NAME = re.compile(r"(?:\bWITH|,)\s+([A-Za-z_][A-Za-z0-9_]*)\s+AS\s*\(", re.IGNORECASE)
#: What follows FROM or JOIN but is no table.
_NOT_TABLES = {"unnest", "lateral", "table", "select"}
#: The catalogs this Athena holds.
CATALOGS = {"awsdatacatalog"}


class _Raw:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def stream(self, **_: Any) -> Any:
        yield self.body


def _answer(status: int, body: dict[str, Any]) -> AWSResponse:
    data = json.dumps(body).encode()
    headers = {"Content-Type": "application/x-amz-json-1.1", "x-amzn-RequestId": str(uuid.uuid4())}
    return AWSResponse("https://athena.eu-west-2.amazonaws.com/", status, headers, _Raw(data))


def _error(name: str, **fill: Any) -> AWSResponse:
    recorded = RECORDED["errors"][name]
    body = {k: (v.format(**fill) if isinstance(v, str) else v) for k, v in recorded["body"].items()}
    return _answer(recorded["status"], body)


@dataclass
class _Execution:
    query: str
    database: str
    workgroup: str
    polls_left: int
    outcome: str  # "SUCCEEDED" or a failure's name in the recording
    table: tuple[str, str] | None = None
    fill: dict[str, str] = field(default_factory=dict)


@dataclass
class RecordedAthena:
    """Tables by database, named queries by id, workgroups by name (each with its own results
    location or none). Each execution answers RUNNING `polls` times before its outcome."""

    tables: dict[str, dict[str, tuple[list[str], list[list[str | None]]]]]
    named_queries: dict[str, dict[str, str]] = field(default_factory=dict)
    workgroups: dict[str, str | None] = field(
        default_factory=lambda: {"primary": "s3://synthetic-athena-results/out/", "bare": None}
    )
    polls: int = 1
    #: L1.9 part 2: a statement that does not parse is refused at StartQueryExecution
    #: (`InvalidRequestException`), the other answer Athena may give, rather than run and FAILED.
    syntax_refused_at_start: bool = False
    #: Tables whose objects the role may not read (their location not in its policy): each read
    #: fails as an execution, as Athena reads a table's objects as the caller.
    unreadable_data: set[str] = field(default_factory=set)
    #: Every QueryString sent to StartQueryExecution, in order.
    sent: list[str] = field(default_factory=list)
    #: Every operation asked, in order.
    asked: list[str] = field(default_factory=list)
    #: What GetQueryResults was asked for MaxResults, in order.
    page_sizes: list[int] = field(default_factory=list)
    _executions: dict[str, _Execution] = field(default_factory=dict)

    def client(self, key: str = GRANTED_KEY, region: str = "eu-west-2") -> Any:
        """botocore's own Athena client, with this fixture in place of the network."""
        session = botocore.session.get_session()
        client = session.create_client(
            "athena", region_name=region, aws_access_key_id=key,
            aws_secret_access_key="synthetic-secret-not-a-real-key",  # noqa: S106 (synthetic)
            config=Config(retries={"max_attempts": 1}),
        )  # fmt: skip
        return self.attach(client)

    def attach(self, client: Any) -> Any:
        """Any botocore Athena client, the deployment's own included (`cloud_athena_client`),
        answered by this fixture in place of the network."""
        client.meta.events.register("before-send.athena", self._send)
        return client

    def _send(self, request: AWSPreparedRequest, **_: Any) -> AWSResponse:
        target = str(
            request.headers.get("X-Amz-Target", b"").decode()
            if isinstance(request.headers.get("X-Amz-Target"), bytes)
            else request.headers.get("X-Amz-Target", "")
        )
        operation = target.split(".", 1)[-1]
        self.asked.append(operation)
        authorization = request.headers.get("Authorization", b"")
        authorization = (
            authorization.decode() if isinstance(authorization, bytes) else authorization
        )
        found = re.search(r"Credential=([A-Z0-9]+)/", authorization)
        key = found.group(1) if found else ""
        if key not in _KNOWN:
            return _error("unrecognised_client")
        body = json.loads(request.body or b"{}")
        workgroup = body.get("WorkGroup", "primary")
        if key != GRANTED_KEY:
            return _error("access_denied", action=f"athena:{operation}", workgroup=workgroup)
        return getattr(self, f"_{operation}")(body)

    # --- the operations ---------------------------------------------------------------------

    def _GetWorkGroup(self, body: dict[str, Any]) -> AWSResponse:
        name = body["WorkGroup"]
        if name not in self.workgroups:
            return _error("workgroup_not_found", workgroup=name)
        output = self.workgroups[name]
        configuration = {"ResultConfiguration": {"OutputLocation": output}} if output else {}
        return _answer(200, {"WorkGroup": {"Name": name, "State": "ENABLED",
                                           "Configuration": configuration}})  # fmt: skip

    def _GetNamedQuery(self, body: dict[str, Any]) -> AWSResponse:
        found = self.named_queries.get(body["NamedQueryId"])
        if found is None:
            return _error("named_query_not_found", id=body["NamedQueryId"])
        return _answer(200, {"NamedQuery": {"NamedQueryId": body["NamedQueryId"], **found}})

    def _StartQueryExecution(self, body: dict[str, Any]) -> AWSResponse:
        workgroup = body.get("WorkGroup", "primary")
        if workgroup not in self.workgroups:
            return _error("workgroup_not_found", workgroup=workgroup)
        output = (body.get("ResultConfiguration") or {}).get("OutputLocation")
        if output is None and self.workgroups[workgroup] is None:
            return _error("no_output_location")
        query = body["QueryString"]
        self.sent.append(query)
        context = body.get("QueryExecutionContext") or {}
        database = str(context.get("Database", "default")).lower()
        catalog = str(context.get("Catalog", "AwsDataCatalog")).lower()
        execution_id = str(uuid.uuid4())
        execution = _Execution(query, database, workgroup, self.polls, "SUCCEEDED")
        if re.match(r"^\s*SELECT\s+FROM\b", query, re.IGNORECASE):
            execution.outcome = "syntax"  # a SELECT naming nothing to select does not parse
        elif re.search(r"\bWHERE\s*;?\s*$", query, re.IGNORECASE):
            execution.outcome = "syntax_eof"  # a WHERE with no condition
            execution.fill = {"column": str(len(query.rstrip().rstrip(";")) + 1)}
        elif catalog not in CATALOGS:
            execution.outcome = "catalog_not_found"
            execution.fill = {"catalog": catalog}
        else:
            self._resolve(execution, query, catalog, database)
        if self.syntax_refused_at_start and execution.outcome in {"syntax", "syntax_eof"}:
            reason = RECORDED["failures"][execution.outcome]["StateChangeReason"]
            return _error("malformed_query", message=reason.format(**execution.fill))
        if output and "forbidden" in output:
            execution.outcome = "s3_access_denied"
            execution.fill = {"id": execution_id}
        self._executions[execution_id] = execution
        return _answer(200, {"QueryExecutionId": execution_id})

    def _resolve(self, execution: _Execution, query: str, catalog: str, database: str) -> None:
        """Every table after FROM or JOIN resolved as Athena resolves it: the first that does not
        exist fails the execution; the first that does is the one whose rows the results give."""
        own = {name.lower() for name in _WITH_NAME.findall(query)}
        for found in relations(query):
            parts = [p.strip().strip('"').lower() for p in found.split(".")]
            if len(parts) == 1 and (parts[0] in own or parts[0] in _NOT_TABLES):
                continue
            where = {1: [catalog, database], 2: [catalog], 3: []}[len(parts)] + parts
            in_catalog, db, table = where
            if in_catalog not in CATALOGS:
                execution.outcome, execution.fill = "catalog_not_found", {"catalog": in_catalog}
                return
            if db not in self.tables:
                execution.outcome, execution.fill = "schema_not_found", {"schema": db}
                return
            if table == "lake_formation_locked":
                execution.outcome = "lake_formation_denied"  # a FAILED reason naming the role
                return
            if table not in self.tables[db]:
                execution.outcome = "table_not_found"
                execution.fill = {"table": f"{in_catalog}.{db}.{table}"}
                return
            if table in self.unreadable_data:
                execution.outcome, execution.fill = "table_data_denied", {"table": table}
                return
            if execution.table is None:
                execution.table = (db, table)

    def _GetQueryExecution(self, body: dict[str, Any]) -> AWSResponse:
        execution = self._executions.get(body["QueryExecutionId"])
        if execution is None:
            return _error("execution_not_found", id=body["QueryExecutionId"])
        status: dict[str, Any]
        if execution.polls_left > 0:
            execution.polls_left -= 1
            status = {"State": "RUNNING"}
        elif execution.outcome == "SUCCEEDED":
            status = {"State": "SUCCEEDED"}
        elif execution.outcome == "cancelled":
            status = {"State": "CANCELLED", "StateChangeReason": "Query cancelled by user"}
        else:
            failure = RECORDED["failures"][execution.outcome]
            status = {
                "State": "FAILED",
                "StateChangeReason": failure["StateChangeReason"].format(**execution.fill),
                "AthenaError": {**failure["AthenaError"],
                                "ErrorMessage": failure["AthenaError"]["ErrorMessage"].format(
                                    **execution.fill)},
            }  # fmt: skip
        statement = "DML" if re.match(r"^\s*(SELECT|WITH)\b", execution.query, re.I) else "DDL"
        return _answer(200, {"QueryExecution": {
            "QueryExecutionId": body["QueryExecutionId"], "Query": execution.query,
            "StatementType": statement, "WorkGroup": execution.workgroup,
            "QueryExecutionContext": {"Database": execution.database},
            "Status": status,
        }})  # fmt: skip

    def _StopQueryExecution(self, body: dict[str, Any]) -> AWSResponse:
        execution = self._executions.get(body["QueryExecutionId"])
        if execution is None:
            return _error("execution_not_found", id=body["QueryExecutionId"])
        execution.polls_left, execution.outcome = 0, "cancelled"
        return _answer(200, {})

    def _GetQueryResults(self, body: dict[str, Any]) -> AWSResponse:
        execution = self._executions.get(body["QueryExecutionId"])
        if execution is None:
            return _error("execution_not_found", id=body["QueryExecutionId"])
        size = int(body.get("MaxResults", 1000))
        self.page_sizes.append(size)
        if size > 1000:
            return _error("max_results", value=size)
        if execution.polls_left > 0 or execution.outcome != "SUCCEEDED":
            return _error("not_finished", state="RUNNING" if execution.polls_left else "FAILED")
        assert execution.table is not None
        columns, rows = self.tables[execution.table[0]][execution.table[1]]
        every = [list(columns), *rows]  # the header is the first page's first row, as Athena gives
        token = body.get("NextToken")
        start = 0
        if token is not None:
            prefix = f"{body['QueryExecutionId']}:"
            if not token.startswith(prefix):
                return _error("bad_next_token")
            start = int(token[len(prefix) :])
        page = every[start : start + size]
        answer: dict[str, Any] = {
            "UpdateCount": 0,
            "ResultSet": {
                "Rows": [{"Data": [{} if v is None else {"VarCharValue": v} for v in row]}
                         for row in page],
                "ResultSetMetadata": {"ColumnInfo": [
                    {"CatalogName": "hive", "SchemaName": "", "TableName": "", "Name": c,
                     "Label": c, "Type": "varchar", "Precision": 2147483647, "Scale": 0,
                     "Nullable": "UNKNOWN", "CaseSensitive": True} for c in columns]},
            },
        }  # fmt: skip
        if start + size < len(every):
            answer["NextToken"] = f"{body['QueryExecutionId']}:{start + size}"
        return _answer(200, answer)
