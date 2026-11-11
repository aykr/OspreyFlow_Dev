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
- a query that does not parse, and a table that does not exist, each **failing as an execution**
  (`FAILED`, with its `AthenaError`), as Athena reports them, not as a refused request.

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
_SELECT_ALL = re.compile(r'^SELECT \* FROM "([a-z0-9_]+)"\."([a-z0-9_]+)"$')
_FROM = re.compile(r"\bFROM\s+\"?([a-z0-9_]+)\"?\.\"?([a-z0-9_]+)\"?", re.IGNORECASE)


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
        database = (body.get("QueryExecutionContext") or {}).get("Database", "default")
        execution_id = str(uuid.uuid4())
        execution = _Execution(query, database, workgroup, self.polls, "SUCCEEDED")
        if re.match(r"^\s*SELECT\s+FROM\b", query, re.IGNORECASE):
            execution.outcome = "syntax"  # a SELECT naming nothing to select does not parse
        if execution.outcome == "SUCCEEDED":
            match = _SELECT_ALL.match(query) or _FROM.search(query)
            if match:
                db, table = match.group(1).lower(), match.group(2).lower()
                if table not in self.tables.get(db, {}):
                    execution.outcome = "table_not_found"
                    execution.fill = {"table": f"awsdatacatalog.{db}.{table}"}
                else:
                    execution.table = (db, table)
        if output and "forbidden" in output:
            execution.outcome = "s3_access_denied"
            execution.fill = {"id": execution_id}
        self._executions[execution_id] = execution
        return _answer(200, {"QueryExecutionId": execution_id})

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
