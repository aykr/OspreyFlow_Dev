"""Every export writes its ledger row, an export with no case included (SE8b; the owner's ruling of
21 November 2026: "an export with no case (the dataset release, the rule file) writes its ledger row
with who, what and the dataset or rule it concerns, and the case left empty. A test fails if any
export route writes no row").

**What the scan walks** (`test_the_scan_walks_what_it_says`): every `*.py` under
`OspreyFlow_Core/services/api`, recursively (`working_set/` included), read as syntax trees. A route
is a function carrying `@app.<method>("/…")` (or `@router.…`). Route files elsewhere under
`services/` and `harness/` are not walked for exports; they are *pinned* instead
(`OTHER_ROUTE_FILES`: each with the reason it sends nothing out of the product), so a new route file
anywhere fails until it is weighed. The runtime app's own routes are compared with the scan's
(`test_the_scan_sees_every_route_the_app_serves`), so a route registered in a way the syntax cannot
see (`add_api_route`, an included router) fails too.

**What it asks**, in three steps, each a test with its planted fault red:

1. *Which routes send data out?* A route whose name or path says export, download, feed, backup,
   release, bundle or archive; or that returns a file, a stream or a body with a `media_type`
   (`Response`, `FileResponse`, `StreamingResponse`, `PlainTextResponse`, `HTMLResponse`,
   `response_class=`, a `Content-Disposition`); or that calls one of the builders an export is made
   of. Each such route is in `EXPORT_ROUTES` (it must write a ledger row) or in `NOT_EXPORTS` (it is
   argued not to be one, with the reason): a route in neither fails. A plain JSON read under a
   neutral name is not detectable by shape; that limit is stated in the report, and `NOT_EXPORTS`
   names the routes that came closest.
2. *Does each reach a ledger write?* From the handler, through the plain-named functions it calls
   (by name, across the whole walked tree), to a `….record(…)` on a name containing `ledger`. A
   handler whose reached functions hold none fails.
3. *Does each write the row the owner asked for?* Through the test client, with the real ledger
   store over a fake pool that refuses what Postgres refuses (a NULL in a NOT NULL column): one row
   with who, kind, subject, the case (or none), and nothing of the artefact's content.

**For SE8d** (the completeness gate over every route): `Surface` is what one gate needs, the
detector of its routes, the predicate of its write and the reviewed lists. SE8d adds a `Surface` for
model calls (writer: `model_calls`' record) and one for sign-in events (writer: `sign_in_events`'),
and passes it to the same `unreviewed`/`unwritten`; nothing in the walk is export-specific.
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import pathlib
import re
import uuid
from collections.abc import Callable, Iterable, Iterator, Sequence
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import Response
from fastapi.testclient import TestClient

from schemas.domain import Principal

CORE = pathlib.Path(__file__).resolve().parents[4] / "OspreyFlow_Core"
API = CORE / "services" / "api"
#: The folders the scan walks for routes: this one, recursively.
WALKED = (API,)

# --- the scan ------------------------------------------------------------------------------------

_METHODS = {"get", "post", "put", "delete", "patch"}
_Fn = ast.FunctionDef | ast.AsyncFunctionDef


@dataclasses.dataclass(frozen=True)
class Handler:
    file: str
    name: str
    method: str
    path: str
    node: _Fn = dataclasses.field(compare=False, repr=False)


def handlers_in(tree: ast.AST, file: str) -> list[Handler]:
    found: list[Handler] = []
    for node in ast.walk(tree):
        if not isinstance(node, _Fn):
            continue
        for dec in node.decorator_list:
            if (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                    and dec.func.attr in _METHODS and dec.args
                    and isinstance(dec.args[0], ast.Constant)
                    and isinstance(dec.args[0].value, str)
                    and dec.args[0].value.startswith("/")):  # fmt: skip
                found.append(Handler(file, node.name, dec.func.attr, dec.args[0].value, node))
    return found


def parse_tree(roots: Iterable[pathlib.Path] = WALKED) -> dict[pathlib.Path, ast.Module]:
    return {p: ast.parse(p.read_text()) for r in roots for p in sorted(r.rglob("*.py"))}


def definitions(trees: dict[Any, ast.AST]) -> dict[str, list[_Fn]]:
    out: dict[str, list[_Fn]] = {}
    for tree in trees.values():
        for node in ast.walk(tree):
            if isinstance(node, _Fn):
                out.setdefault(node.name, []).append(node)
    return out


def _last_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def is_ledger_write(node: ast.AST) -> bool:
    """`<anything named *ledger*>.record(...)`: the export ledger's writer, by its receiver."""
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "record"
            and "ledger" in _last_name(node.func.value).lower())  # fmt: skip


def _calls(fn: _Fn) -> Iterator[ast.Call]:
    return (n for n in ast.walk(fn) if isinstance(n, ast.Call))


def reached(fn: _Fn, defs: dict[str, list[_Fn]]) -> list[_Fn]:
    """`fn` and every function it calls by plain name, transitively (by name, over the whole tree:
    it can reach too much, never too little, which is the safe side for "writes a row"; the planted
    drops below show it still finds a route that writes none)."""
    seen: list[_Fn] = []
    todo = [fn]
    while todo:
        cur = todo.pop()
        if any(cur is s for s in seen):
            continue
        seen.append(cur)
        for call in _calls(cur):
            if isinstance(call.func, ast.Name):
                todo.extend(defs.get(call.func.id, []))
    return seen


_NAMED_LIKE_AN_EXPORT = re.compile(r"export|download|feed|backup|release|bundle|archive", re.I)
_BODIES = {"Response", "FileResponse", "StreamingResponse", "PlainTextResponse", "HTMLResponse"}
#: What an export is made of: the functions whose result leaves as the artefact.
_BUILDERS = {"submit_export", "export_pack", "export_release", "export_rule_file", "feed_rows",
             "build_bundle", "export_rows"}  # fmt: skip


def export_shaped(h: Handler) -> bool:
    if _NAMED_LIKE_AN_EXPORT.search(h.name) or _NAMED_LIKE_AN_EXPORT.search(h.path):
        return True
    for dec in h.node.decorator_list:
        if isinstance(dec, ast.Call) and any(k.arg == "response_class" for k in dec.keywords):
            return True
    if h.node.returns is not None and any(
        _last_name(n) in _BODIES - {"Response"} for n in ast.walk(h.node.returns)
    ):  # a bare `-> Response` is every 204 too: its call is what is looked at below
        return True
    for call in _calls(h.node):
        name = _last_name(call.func)
        if name in _BUILDERS:
            return True
        if name in _BODIES and (
            name != "Response" or any(k.arg in {"media_type", "headers"} for k in call.keywords)
        ):  # `Response(status_code=204)` carries nothing
            return True
    return any(
        isinstance(n, ast.Constant) and isinstance(n.value, str)
        and ("Content-Disposition" in n.value or n.value.startswith("attachment"))
        for n in ast.walk(h.node)
    )  # fmt: skip


@dataclasses.dataclass(frozen=True)
class Surface:
    """What one completeness gate needs: which routes it covers, and what counts as a write."""

    name: str
    detect: Callable[[Handler], bool]
    writes: Callable[[ast.AST], bool]
    reviewed_yes: dict[str, Any]
    reviewed_no: dict[str, str]


def unreviewed(surface: Surface, handlers: Sequence[Handler]) -> list[str]:
    """Routes the surface's detector finds that no reviewed list names."""
    return sorted(
        h.name for h in handlers
        if surface.detect(h) and h.name not in surface.reviewed_yes
        and h.name not in surface.reviewed_no
    )  # fmt: skip


def unwritten(
    surface: Surface, handlers: Sequence[Handler], defs: dict[str, list[_Fn]]
) -> list[str]:
    """Reviewed routes of the surface that reach no write."""
    return sorted(
        h.name for h in handlers
        if h.name in surface.reviewed_yes
        and not any(surface.writes(c) for f in reached(h.node, defs) for c in _calls(f))
    )  # fmt: skip


def strip_writes(fn: _Fn, writes: Callable[[ast.AST], bool]) -> _Fn:
    """A copy of `fn` with each statement that is a write (awaited or not) turned into `pass`."""

    class _Drop(ast.NodeTransformer):
        def visit_Expr(self, node: ast.Expr) -> ast.AST:
            value = node.value.value if isinstance(node.value, ast.Await) else node.value
            return ast.copy_location(ast.Pass(), node) if writes(value) else node

    return _Drop().visit(copy.deepcopy(fn))  # type: ignore[no-any-return]


# --- the reviewed lists -------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Export:
    """A route that is an export: the row it writes (`kind`, `subject`) and why it is one."""

    kind: str
    subject_kind: str
    subject_id: str
    case: str | None
    why: str
    #: False for a route no shape gives away (a plain JSON body under a neutral name): it is in the
    #: list because the owner named it, and only the list and the reach test hold it.
    by_shape: bool = True


CASE, DATASET, RULE, PACK = "case-1", "ds-1", "rule-1", "pack-1"

EXPORT_ROUTES: dict[str, Export] = {
    "submit_export_route": Export(
        "subgraph",
        "case",
        CASE,
        CASE,
        "the gated chart, subgraph or report with its mark (ADR-045 to 047)",
    ),
    "export_pack_route": Export(
        "report_pack",
        "pack",
        PACK,
        CASE,
        "a published pack's manifest, through the same gate (ADR-113 decision 6)",
    ),
    "read_report_feed": Export(
        "report_feed",
        "report",
        CASE,
        CASE,
        "the figures as JSON or CSV for a dashboard (ADR-111 decisions 6 to 8)",
    ),
    "read_case_report": Export(
        "case_report",
        "report",
        CASE,
        CASE,
        "the Reports view's figures: the same body as the feed, handed to the Glass, which prints"
        " and saves it (the owner's ruling of 21 November 2026 names it)",
        by_shape=False,
    ),
    "export_dataset_release": Export(
        "dataset_release",
        "dataset",
        DATASET,
        None,
        "a dataset's release as its bundle's files: no case, the dataset it concerns",
    ),
    "export_rule_standard_file": Export(
        "rule_file",
        "rule",
        RULE,
        CASE,
        "a rule's .bpmn or .dmn as an attachment: the rule it concerns; its case is the route's",
    ),
}

#: Routes that look like an export by shape and are argued not to be. Every entry says why.
NOT_EXPORTS: dict[str, str] = {
    # Images and held files shown in the Glass, read by someone who can read the case.
    "document_file_route": "a held document's file shown in the document reader to someone who "
    "can see the document in the case: an access, audited per read (`read_document_file`), not "
    "an artefact with a mark leaving through the export gate. Weighed in the owner's report",
    "entity_picture_file_route": "a person's picture drawn on the canvas, an access audited per "
    "read (`read_entity_picture`); the picture is part of the case's own view",
    "board_picture_file": "a picture drawn on the analyst's own board, shown on it; part of the "
    "board's view. It writes no audit row today: access, SE8d's, not an export",
    "get_site_image": "a site's floor-plan image shown on the map; the case's own view. It writes "
    "no audit row today: access, SE8d's, not an export",
    # Reference data and the deployment's own files, no case.
    "get_map_tile_route": "a map tile: reference data, tier 1 map data, no case and no record "
    "(the guides name it outside 'access')",
    "get_map_local_source_route": "the deployment's own basemap file served to the map: "
    "reference data, no case",
    "read_guide_route": "a guide's PDF, the product's own documentation: no record of any case",
    "build_basemap_route": "writes the basemap from the deployment's own map sources: it brings "
    "reference data in, sends nothing out (audited `geospatial_build_basemap`)",
    # Names that say release, feed or export and are not one.
    "list_exports_route": "reads the ledger itself, by the ledger's own role (ADR-047 Gap 2): "
    "it lists metadata rows, ids and counts, no content; not an export of case data",
    "import_dataset_release": "brings a release in (writes the draft model and pipelines): "
    "nothing leaves",
    "release_alert": "puts a claimed alert back in the queue: 'release' as in let go",
    "release_held_rows_route": "lets held rows through into the load: inward, into the graph",
    "data_feeds_route": "lists the pipelines that feed the case's datasets, their schedules and "
    "last outcomes: data coming in, read-only, audited `list_data_feeds`; no figure of a record",
}

#: Route files outside `services/api` (found by the scan of `services/` and `harness/`), each argued
#: not to send case data out of the product.
OTHER_ROUTE_FILES: dict[str, str] = {
    "services/laurium/app.py": "a model service inside the deployment: it receives text to read "
    "and answers; it holds no case and sends nothing out (its calls are SE8a's model-call record)",
    "services/ner/app.py": "the same: a recogniser inside the deployment, answering what it is "
    "asked (SE8a's)",
    "harness/webapp.py": "the installer's page on the operator's own machine, before any case "
    "exists: its downloads are the deployment's own configuration files, never case data",
    "harness/webapp_signin.py": "the installer page's sign-in; no data",
    "harness/install_page.py": "the first-install page: settings and a check of the machine; "
    "no case data",
}

#: Not routes: what leaves the product as a file, by an operator's command or the chart's cron job.
#: Neither is reachable from a route (`test_the_backup_and_the_object_transfer_are_outside_routes`).
OUTSIDE_THE_CONDUIT = {
    "services/api/platform_backup.py": "the cloud profile's CronJob (`python -m ...`): ArcadeDB's "
    "and ClickHouse's own backups to the deployment's bucket, with no principal and no database "
    "of the Conduit's",
    "services/api/object_transfer.py": "the operator's command moving the object store as files "
    "(backup, restore, the move between stores); no route, no principal",
    "harness/backup.py": "the `ospreyflow backup` command on the operator's host",
}


def export_surface() -> Surface:
    return Surface("export", export_shaped, is_ledger_write, EXPORT_ROUTES, NOT_EXPORTS)


@pytest.fixture(scope="module")
def trees() -> dict[pathlib.Path, ast.Module]:
    return parse_tree()


@pytest.fixture(scope="module")
def handlers(trees: dict[pathlib.Path, ast.Module]) -> list[Handler]:
    return [h for p, t in trees.items() for h in handlers_in(t, p.name)]


@pytest.fixture(scope="module")
def defs(trees: dict[pathlib.Path, ast.Module]) -> dict[str, list[_Fn]]:
    return definitions(trees)


# --- the gate ----------------------------------------------------------------------------------


def test_the_scan_walks_what_it_says(trees: dict[pathlib.Path, ast.Module]) -> None:
    """The folder is real and the walk reaches the sub-folder and the big file: a scan over an
    empty or moved folder would pass everything."""
    names = {p.relative_to(API).as_posix() for p in trees}
    assert {
        "app.py",
        "export.py",
        "packs.py",
        "studio_release.py",
        "working_set/service.py",
    } <= names
    assert len(trees) > 150


def test_the_scan_sees_every_route_the_app_serves(handlers: list[Handler]) -> None:
    """The runtime app against the syntax: a route added in a way the scan cannot read is a failure
    here, not a silent gap."""
    from fastapi.routing import APIRoute
    from services.api.app import app

    served = {r.endpoint.__name__ for r in app.routes if isinstance(r, APIRoute)}
    scanned = {h.name for h in handlers if h.file == "app.py"}
    assert served - scanned == set(), (
        f"served but not found by the scan: {sorted(served - scanned)}"
    )
    assert scanned - served == set(), (
        f"found by the scan but not served: {sorted(scanned - served)}"
    )


def test_other_route_files_are_pinned() -> None:
    """Route files outside the walked folder are named, each with its reason, so a new one fails
    until it is weighed."""
    found: set[str] = set()
    for folder in (CORE / "services", CORE / "harness"):
        for path in folder.rglob("*.py"):
            rel = path.relative_to(CORE).as_posix()
            if rel.startswith("services/api/") or "/.venv" in rel or "node_modules" in rel:
                continue
            if handlers_in(ast.parse(path.read_text()), path.name):
                found.add(rel)
    assert found == set(OTHER_ROUTE_FILES), found ^ set(OTHER_ROUTE_FILES)


def test_every_export_shaped_route_is_reviewed(handlers: list[Handler]) -> None:
    assert unreviewed(export_surface(), handlers) == []


def test_the_reviewed_lists_name_real_routes_and_the_detector_finds_the_exports(
    handlers: list[Handler],
) -> None:
    names = {h.name for h in handlers}
    assert set(EXPORT_ROUTES) <= names, set(EXPORT_ROUTES) - names
    assert set(NOT_EXPORTS) <= names, set(NOT_EXPORTS) - names
    assert not set(EXPORT_ROUTES) & set(NOT_EXPORTS)
    surface = export_surface()
    found = {h.name for h in handlers if surface.detect(h)}
    by_shape = {n for n, e in EXPORT_ROUTES.items() if e.by_shape}
    assert by_shape <= found, f"the detector misses {by_shape - found}"
    assert all(NOT_EXPORTS[n] for n in NOT_EXPORTS), "every route argued not an export says why"


def test_every_export_route_reaches_a_ledger_write(
    handlers: list[Handler], defs: dict[str, list[_Fn]]
) -> None:
    assert unwritten(export_surface(), handlers, defs) == []


# --- the planted faults, each red --------------------------------------------------------------

_PLANTED_ROUTES = {
    "a CSV body": """
@app.get("/v1/investigations/{investigation_id}/people-list")
async def people_list(investigation: InvestigationViewerDep) -> Response:
    return Response(content="a,b", media_type="text/csv; charset=utf-8")
""",
    "a file": """
@app.get("/v1/things/{thing_id}/bytes")
async def thing_bytes(thing_id: str):
    return FileResponse(path, media_type="application/pdf")
""",
    "a stream": """
@app.get("/v1/things/stream")
async def things(thing_id: str):
    return StreamingResponse(rows(), media_type="text/plain")
""",
    "an attachment header": """
@app.get("/v1/things/{thing_id}/save")
async def save_it(thing_id: str):
    return JSONResponse({}, headers={"Content-Disposition": 'attachment; filename="x.json"'})
""",
    "a name that says export": """
@app.post("/v1/investigations/{investigation_id}/everything")
async def export_everything(investigation: InvestigationEditorDep):
    return {"all": []}
""",
    "a builder an export is made of": """
@app.get("/v1/investigations/{investigation_id}/sheet")
async def sheet(figures: ReportFigures):
    return {"rows": feed_rows(figures)}
""",
    "a response class on the decorator": """
@app.get("/v1/things/doc", response_class=PlainTextResponse)
async def doc():
    return "x"
""",
}


@pytest.mark.parametrize("shape", sorted(_PLANTED_ROUTES))
def test_a_new_export_route_is_found_unreviewed(shape: str) -> None:
    """Red for the first half: a route added with an export's shape, in a reviewed list of neither
    kind, is named by the scan."""
    planted = handlers_in(ast.parse(_PLANTED_ROUTES[shape]), "planted.py")
    assert len(planted) == 1
    assert unreviewed(export_surface(), planted) == [planted[0].name], shape


def test_a_real_export_removed_from_the_reviewed_list_is_found(handlers: list[Handler]) -> None:
    """The planted fault at the shape the code really has: the real feed route, its own source,
    with its reviewed entry taken away."""
    surface = dataclasses.replace(
        export_surface(),
        reviewed_yes={k: v for k, v in EXPORT_ROUTES.items() if k != "read_report_feed"},
    )
    assert "read_report_feed" in unreviewed(surface, handlers)


@pytest.mark.parametrize("route", sorted(EXPORT_ROUTES))
def test_an_export_route_that_drops_its_ledger_write_is_found(
    route: str, handlers: list[Handler], defs: dict[str, list[_Fn]]
) -> None:
    """Red for the second half, at each real route: every ledger write the handler reaches (in its
    own body or in the gate it calls) is removed from a copy of the real source, and the gate names
    the route. The count of writes removed is asserted, so a route that never wrote one could not
    pass this by finding nothing to remove."""
    surface = export_surface()
    (handler,) = [h for h in handlers if h.name == route]
    removed = 0
    swapped = {name: list(nodes) for name, nodes in defs.items()}
    for fn in reached(handler.node, defs):
        removed += sum(1 for c in _calls(fn) if is_ledger_write(c))
        stripped = strip_writes(fn, is_ledger_write)
        swapped[fn.name] = [stripped if n is fn else n for n in swapped[fn.name]]
    assert removed >= 1, f"{route} reaches no ledger write to drop"
    planted = Handler(handler.file, route, handler.method, handler.path,
                      strip_writes(handler.node, is_ledger_write))  # fmt: skip
    assert route in unwritten(surface, [planted], swapped)


def test_the_unwritten_check_passes_a_route_that_writes_through_a_helper() -> None:
    """The green half of the same check, at a planted helper shape, so it is not red by default."""
    source = ast.parse("""
async def gate(ledger):
    await ledger.record(entry)

@app.get("/v1/x/export")
async def export_x(ledger):
    return await gate(ledger)
""")
    surface = Surface("t", export_shaped, is_ledger_write, {"export_x": 1}, {})
    assert unwritten(surface, handlers_in(source, "t.py"), definitions({"t": source})) == []


# --- what is outside the Conduit ----------------------------------------------------------------


def test_the_backup_and_the_object_transfer_are_outside_routes(
    trees: dict[pathlib.Path, ast.Module],
) -> None:
    """Each is a command, not a route: no module of the Conduit imports it, no route handler names
    it, and neither holds a route or a database connection (the CLI never calls the database)."""
    for rel in OUTSIDE_THE_CONDUIT:
        assert (CORE / rel).exists(), rel
    for rel in ("services/api/platform_backup.py", "services/api/object_transfer.py"):
        path = CORE / rel
        module = path.stem
        tree = ast.parse(path.read_text())
        assert handlers_in(tree, path.name) == []
        imported = {
            a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)
            for a in n.names
        } | {
            (n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
        }  # fmt: skip
        assert not imported & {"asyncpg", "psycopg", "psycopg2"}, (rel, imported)
        assert "export_ledger" not in path.read_text()
        for other, other_tree in trees.items():
            if other == path:
                continue
            for n in ast.walk(other_tree):
                names: list[str] = []
                if isinstance(n, ast.ImportFrom):
                    names = [n.module or "", *(a.name for a in n.names)]
                elif isinstance(n, ast.Import):
                    names = [a.name for a in n.names]
                elif isinstance(n, ast.Name | ast.Attribute):
                    names = [_last_name(n)]
                assert module not in {x.split(".")[-1] for x in names}, (other.name, module)


# --- the real store over a fake pool that refuses what Postgres refuses ------------------------


def _bootstrap_columns() -> dict[str, bool]:
    """The ledger's columns and whether each is NOT NULL, read from the bootstrap statement the
    store really runs, so the fake refuses exactly what the table would."""
    from services.api.export import ledger_bootstrap_sql

    body = ledger_bootstrap_sql().split("(", 1)[1].split(");", 1)[0]
    out: dict[str, bool] = {}
    for line in body.splitlines():
        m = re.match(r"\s+(\w+)\s+(TEXT|INTEGER|BOOLEAN|TIMESTAMPTZ)\b(.*)", line)
        if m:
            out[m.group(1)] = "NOT NULL" in m.group(3) or "PRIMARY KEY" in m.group(3)
    return out


class _NotNullViolation(Exception):
    pass


class FakePool:
    """`asyncpg.Pool`'s `acquire()`, a table that refuses a NULL in a NOT NULL column, and a switch
    that makes the database unreachable."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.down = False
        self._not_null = _bootstrap_columns()

    def acquire(self) -> FakePool:
        return self

    async def __aenter__(self) -> FakePool:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def execute(self, sql: str, *args: Any) -> None:
        if self.down:
            raise ConnectionError("the database is unreachable")
        m = re.search(r"INSERT INTO export_ledger \(([^)]*)\)", sql)
        assert m, sql
        columns = [c.strip() for c in m.group(1).split(",")]
        assert len(columns) == len(args), (columns, args)
        row = dict(zip(columns, args, strict=True))
        for column, required in self._not_null.items():
            if required and row.get(column) is None:
                raise _NotNullViolation(f'null value in column "{column}" violates not-null')
        self.rows.append({c: row.get(c) for c in self._not_null} | row)

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        """The ledger read, with the one condition Postgres would apply: where the SQL carries the
        no-case dataset clause (`export.NO_CASE_DATASET_ROWS_SQL`), a row of no case about a
        dataset is kept only for a reader who names every dataset (`$1`) or reads that dataset
        (`$2`). A read whose SQL lacks the clause gets every row, as Postgres would give it."""
        assert sql.startswith("SELECT * FROM export_ledger")
        rows = list(reversed(self.rows))
        if "subject_kind IS DISTINCT FROM 'dataset'" not in sql:
            return rows
        names_every, reads = args
        return [
            r for r in rows
            if r["subject_kind"] != "dataset" or r["investigation_id"] is not None
            or names_every or r["subject_id"] in reads
        ]  # fmt: skip


async def test_the_fake_refuses_a_no_case_row_when_the_case_is_required() -> None:
    """The fake is only worth its green if it can be red: built over the table as it was before
    SE8b (the case NOT NULL), it refuses the row a release writes, as Postgres did."""
    from services.api.export import ledger_bootstrap_sql

    pool = FakePool()
    pool._not_null = {**_bootstrap_columns(), "investigation_id": True}
    assert "investigation_id TEXT," in ledger_bootstrap_sql()
    with pytest.raises(_NotNullViolation):
        await pool.execute(
            "INSERT INTO export_ledger (id, investigation_id, principal_id, artefact_kind, "
            "exported_at, item_count, withheld, manifest_policy) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
            "x", None, "p", "dataset_release", NOW, 1, False, "omit",
        )  # fmt: skip


def _store(pool: FakePool) -> Any:
    from services.api.export import ExportLedgerStore

    return ExportLedgerStore(pool)  # type: ignore[arg-type]


# --- the routes, through the client ---------------------------------------------------------------

#: A synthetic secret, made for this run and put in every name the routes are given: it must never
#: be in a ledger row, nor in a refused answer.
SECRET = f"synthetic-{uuid.uuid4().hex}"
ANALYST = Principal(
    id="analyst-1", clearance="OFFICIAL", org_unit="unit-1", datasets=[DATASET],
    roles=["analyst", "data_engineer", "rule_author", "reports_viewer"],
)  # fmt: skip
COMPLIANCE = Principal(id="compliance-1", clearance="OFFICIAL", org_unit="unit-9",
                       roles=["osprey-admin"])  # fmt: skip
NOBODY = Principal(id="analyst-2", clearance="OFFICIAL", org_unit="unit-1", roles=["analyst"])
NOW = datetime(2026, 11, 21, 9, 0, tzinfo=UTC)


class _Audit:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> None:
        self.rows.append(kwargs)


class _NoGraph:
    async def get_node(self, *args: Any, **kwargs: Any) -> None:
        return None


class _WorkingSet:
    def __init__(self, withheld: bool) -> None:
        self.withheld = withheld

    async def withheld_for(self, investigation_id: str, principal: Principal) -> bool:
        return self.withheld


class _Rules:
    async def get_listed(self, rule_id: str, case_id: str, principal: Principal) -> Any:
        return SimpleNamespace(id=RULE, version=3, dataset_id=DATASET, name=f"Rule {SECRET}")

    async def rule_files(self, rule_id: str, version: int) -> None:
        return None


def _handling() -> Any:
    from schemas.domain import Handling

    return Handling(classification="OFFICIAL", handling_code="P", originator="unit-1",
                    owning_unit="unit-1")  # fmt: skip


class _Packs:
    async def get(self, case_id: str, pack_id: str) -> Any:
        from schemas.packs import ReportPack

        return ReportPack(id=PACK, investigation_id=CASE, title=f"Pack {SECRET}", created_by="ed",
                          created_at=NOW, updated_at=NOW)  # fmt: skip

    async def readable_version(self, pack_id: str, principal: Principal, scheme: Any) -> Any:
        from services.api.packs import PackVersion, StoredPackItem

        item = StoredPackItem(
            id="i1", kind="note", marking="OFFICIAL", added_by="ed", added_at=NOW,
            note=f"note {SECRET}",
            handlings=[_handling()],
        )  # fmt: skip
        return PackVersion(pack_id=PACK, version=2, published_at=NOW, published_by="ed",
                           items=[item]), [item], False  # fmt: skip


class _NoAlerts:
    async def cited_by_ids(self, ids: Any) -> dict[str, Any]:
        return {}

    async def settle_pending(self, graph: Any, *, now: Any = None) -> None:
        return None


class _Names:
    async def display_names(self, ids: Any) -> dict[str, str]:
        return {}


def _scheme() -> Any:
    from ontology.handling import load_uk_le_scheme

    return load_uk_le_scheme()


def _the_figures(lowered: bool = False) -> Any:
    """`_case_report`'s answer: the figures, and whether they were lowered by what the reader may
    not see (the figures' own computation says: `reports.case_report_and_withheld`)."""

    async def figures(*args: Any, **kwargs: Any) -> Any:
        from schemas.domain import ReportFigures

        return ReportFigures(period_weeks=12, as_of=date(2026, 11, 21), generated_at=NOW,
                             alerts_total=3), lowered  # fmt: skip

    return figures


async def _released(**kwargs: Any) -> Any:
    from services.api.studio_release import ExportResult

    return ExportResult(files={"release.yaml": f"token: {SECRET}\n".encode()}, left_out=1)


def _rule_file(*args: Any, **kwargs: Any) -> Response:
    return Response(
        content=f"<rule>{SECRET}</rule>".encode(),
        media_type="application/xml",
        headers={"Content-Disposition": 'attachment; filename="rule.bpmn"'},
    )


def _walk(dependant: Any) -> Iterator[Any]:
    for sub in dependant.dependencies:
        yield sub
        yield from _walk(sub)


@dataclasses.dataclass
class Case:
    """How to call a route and what it needs: the request, and the stores the route reads by the
    name of their dependency (any other is an object that fails loudly if it is asked)."""

    method: str
    path: str
    stores: dict[str, Any]
    params: dict[str, Any] = dataclasses.field(default_factory=dict)
    body: Any = None
    patches: dict[str, Any] = dataclasses.field(default_factory=dict)
    #: A word that is in the artefact's answer, and so must not be in a refused one.
    artefact_word: str = ""


def _cases() -> dict[str, Case]:
    base = {"get_handling_scheme": _scheme()}
    figures = {"_case_report": _the_figures()}
    config = SimpleNamespace(export_manifest_policy="disclose")
    return {
        "submit_export_route": Case(
            "POST",
            f"/v1/investigations/{CASE}/export",
            {
                **base,
                "get_graph": _NoGraph(),
                "get_judgements_store": object(),
                "get_config": config,
            },
            body={
                "artefact_kind": "subgraph",
                "resolution_threshold": 0.5,
                "items": [
                    {
                        "id": "e1",
                        "kind": "edge",
                        "label": f"edge {SECRET}",
                        "handling": _handling().model_dump(mode="json"),
                    }
                ],
            },
            artefact_word="mark",
        ),  # fmt: skip
        "export_pack_route": Case(
            "POST",
            f"/v1/investigations/{CASE}/packs/{PACK}/export",
            {
                **base,
                "get_pack_store": _Packs(),
                "get_graph": _NoGraph(),
                "get_alerts_store": _NoAlerts(),
                "get_analytics": object(),
                "get_principal_names": _Names(),
                "get_config": config,
            },
            body={},
            artefact_word="items",
        ),  # fmt: skip
        "read_report_feed": Case(
            "GET",
            f"/v1/investigations/{CASE}/reports/feed",
            {},
            params={"format": "csv"},
            patches=figures,
            artefact_word="section",
        ),  # fmt: skip
        "read_case_report": Case(
            "GET",
            f"/v1/investigations/{CASE}/reports",
            {},
            patches=figures,
            artefact_word="alerts_total",
        ),  # fmt: skip
        "export_dataset_release": Case(
            "GET",
            f"/v1/datasets/{DATASET}/release",
            {**base},
            params={"name": f"release {SECRET}", "version": f"v1 {SECRET}"},
            patches={"export_release": _released},
            artefact_word="files",
        ),  # fmt: skip
        "export_rule_standard_file": Case(
            "GET",
            f"/v1/investigations/{CASE}/rules/{RULE}/export.bpmn",
            {"get_typology_rules": _Rules()},
            patches={"export_rule_file": _rule_file},
            artefact_word="<rule>",
        ),  # fmt: skip
    }


@dataclasses.dataclass
class Run:
    pool: FakePool
    audit: _Audit
    response: Any

    @property
    def rows(self) -> list[dict[str, Any]]:
        return self.pool.rows


def _call(
    name: str,
    monkeypatch: pytest.MonkeyPatch,
    *,
    withheld: bool = False,
    down: bool = False,
    who: Principal = ANALYST,
    params: dict[str, Any] | None = None,
    lowered: bool = False,
) -> Run:
    from fastapi.routing import APIRoute
    from services.api import app as app_module
    from services.api.investigations import Investigation

    case = _cases()[name]
    pool = FakePool()
    pool.down = down
    audit = _Audit()
    stores = {
        "get_export_ledger": _store(pool), "get_audit": audit,
        "get_working_set": _WorkingSet(withheld), **case.stores,
    }  # fmt: skip
    app = app_module.app
    (route,) = [r for r in app.routes if isinstance(r, APIRoute) and r.endpoint.__name__ == name]
    investigation = Investigation(id=CASE, name="Case", created_at=NOW, created_by="alice",
                                  owning_unit="unit-1", domains=[])  # fmt: skip
    try:
        app.dependency_overrides[app_module.get_principal] = lambda: who
        for sub in _walk(route.dependant):
            call = sub.call
            if hasattr(call, "required_level"):
                app.dependency_overrides[call] = lambda: investigation
            elif (getattr(call, "__name__", "").startswith("get_")
                  and call is not app_module.get_principal):  # fmt: skip
                app.dependency_overrides[call] = (lambda s: lambda: s)(
                    stores.get(call.__name__, object())
                )  # fmt: skip
        for attr, value in case.patches.items():
            monkeypatch.setattr(
                app_module, attr, _the_figures(lowered) if attr == "_case_report" else value
            )
        client = TestClient(app, raise_server_exceptions=False)
        response = client.request(
            case.method, case.path, params=params or case.params, json=case.body,
            headers={"Authorization": "Bearer x"},
        )  # fmt: skip
    finally:
        app.dependency_overrides.clear()
    return Run(pool, audit, response)


def test_every_reviewed_export_has_a_route_case() -> None:
    assert set(_cases()) == set(EXPORT_ROUTES)


@pytest.mark.parametrize("route", sorted(EXPORT_ROUTES))
def test_each_export_route_writes_its_row(route: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """The row of the owner's ruling, at each route: who, what kind, the subject, the case or none,
    when, and a count; written once; and nothing of the artefact's content in it (the secret is in
    every route's own input: a name, a version, an item's label, a pack's title, a rule's name)."""
    expect = EXPORT_ROUTES[route]
    run = _call(route, monkeypatch)
    assert run.response.status_code == 200, run.response.text[:300]
    (row,) = run.rows
    assert row["principal_id"] == ANALYST.id
    assert row["artefact_kind"] == expect.kind
    assert (row["subject_kind"], row["subject_id"]) == (expect.subject_kind, expect.subject_id)
    assert row["investigation_id"] == expect.case
    assert isinstance(row["exported_at"], datetime) and row["exported_at"].tzinfo is not None
    assert isinstance(row["item_count"], int) and row["item_count"] >= 1
    assert isinstance(row["withheld"], bool)
    assert SECRET not in repr(row), "an artefact's content or a name reached the ledger row"
    assert run.audit.rows, "the audit row is kept beside the ledger row"


def test_the_dataset_release_row_has_no_case_and_counts_what_was_exported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _call("export_dataset_release", monkeypatch)
    (row,) = run.rows
    assert row["investigation_id"] is None
    assert row["item_count"] == 1, "the files in the answer, never a stored count"
    assert row["withheld"] is True, "left_out was 1: the release left a pipeline out"
    assert row["handling_level"] is None, "a bundle with no pipeline has no marking to record"


@pytest.mark.parametrize("route", sorted(EXPORT_ROUTES))
def test_a_ledger_that_cannot_be_written_fails_the_export_closed(
    route: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail closed (as the audit writer does): 503, and none of the artefact in the answer."""
    run = _call(route, monkeypatch, down=True)
    assert run.response.status_code == 503, run.response.text[:300]
    assert _cases()[route].artefact_word not in run.response.text
    assert SECRET not in run.response.text
    assert run.rows == []


@pytest.mark.parametrize("route", ["read_report_feed", "read_case_report"])
@pytest.mark.parametrize("lowered", [True, False])
@pytest.mark.parametrize("working_set_holds_more", [True, False])
def test_the_figures_row_says_what_the_figures_computation_says(
    route: str, lowered: bool, working_set_holds_more: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The row's flag is whether the reader's figures were lowered by what they may not see, as the
    figures' own computation answers (`_case_report`'s second value), and nothing else. The case's
    working-set sentence is made to say the opposite in every case here: a route that asked it (the
    first version did, `withheld_for`, a question about the case's stored set, of which no figure
    is counted) is red in two of the four combinations, and so is the old constant `False` (red
    where the figures were lowered). The computation itself, against fakes that drop what a reader
    may not read, is `test_report_figures_withheld.py`."""
    run = _call(route, monkeypatch, withheld=working_set_holds_more, lowered=lowered)
    assert run.response.status_code == 200
    (row,) = run.rows
    assert row["withheld"] is lowered


def test_the_feed_in_json_writes_one_row_too(monkeypatch: pytest.MonkeyPatch) -> None:
    run = _call("read_report_feed", monkeypatch, params={"format": "json"})
    assert run.response.status_code == 200
    assert run.response.json()["alerts_total"] == 3
    assert len(run.rows) == 1


# --- the store: the read rule for a row with no case, and what it refuses --------------------


async def test_a_no_case_row_reaches_only_a_reader_of_the_ledger() -> None:
    """Rule 4 and the owner's rule 3 and 7: the one read of the ledger is the role's, and a no-case
    row is read as every row is, by the role. It carries ids and no name. A reader of the ledger
    who may name every dataset (the administrator: `GET /v1/admin/datasets`) learns that a person
    exported a release of dataset `ds-1`; a person without the role learns nothing, not even that
    the ledger holds a row. Who else may learn of a dataset's release is
    `test_a_dataset_release_row_reaches_only_a_reader_who_may_know_the_dataset`."""
    from services.api.export import ComplianceRoleRequiredError, ExportLedgerEntry

    pool = FakePool()
    store = _store(pool)
    await store.record(ExportLedgerEntry(
        id="x1", investigation_id=None, principal_id=ANALYST.id, artefact_kind="dataset_release",
        handling_level=None, exported_at=NOW, item_count=2, withheld=False, manifest_policy="omit",
        subject_kind="dataset", subject_id=DATASET,
    ))  # fmt: skip
    (entry,) = await store.list_all(COMPLIANCE.model_copy(update={"datasets": []}))
    assert (entry.investigation_id, entry.subject_kind, entry.subject_id) == (
        None,
        "dataset",
        DATASET,
    )
    assert set(entry.model_dump()) == {
        "id", "investigation_id", "principal_id", "artefact_kind", "handling_level", "exported_at",
        "item_count", "withheld", "manifest_policy", "justification_given",
        "originator_reference_given", "subject_kind", "subject_id",
    }  # fmt: skip
    with pytest.raises(ComplianceRoleRequiredError):
        await store.list_all(NOBODY)
    with pytest.raises(ComplianceRoleRequiredError):
        await store.list_all(ANALYST)


COMPLIANCE_ONLY = Principal(id="compliance-2", clearance="OFFICIAL", org_unit="unit-9",
                            roles=["compliance"], datasets=[])  # fmt: skip


def _release(row_id: str, dataset: str) -> Any:
    from services.api.export import ExportLedgerEntry

    return ExportLedgerEntry(
        id=row_id, investigation_id=None, principal_id=ANALYST.id,
        artefact_kind="dataset_release", handling_level="OFFICIAL", exported_at=NOW, item_count=2,
        withheld=False, manifest_policy="omit", subject_kind="dataset", subject_id=dataset,
    )  # fmt: skip


async def _ledger_of_three_kinds(pool: FakePool) -> Any:
    """A release of `ds-1`, a rule file and a case's report, the three a reader may be shown."""
    from services.api.export import ExportLedgerEntry

    store = _store(pool)
    await store.record(_release("rel-1", DATASET))
    await store.record(ExportLedgerEntry(
        id="rule-1", investigation_id=None, principal_id=ANALYST.id, artefact_kind="rule_file",
        handling_level=None, exported_at=NOW, item_count=1, withheld=False, manifest_policy="omit",
        subject_kind="rule", subject_id="rule-a",
    ))  # fmt: skip
    await store.record(ExportLedgerEntry(
        id="case-1", investigation_id="case-1", principal_id=ANALYST.id, artefact_kind="report",
        handling_level="OFFICIAL", exported_at=NOW, item_count=2, withheld=False,
        manifest_policy="omit", subject_kind="report", subject_id="r-1",
    ))  # fmt: skip
    return store


async def _seen(store: Any, reader: Principal) -> set[str]:
    return {e.id for e in await store.list_all(reader)}


async def test_a_dataset_release_row_reaches_only_a_reader_who_may_know_the_dataset() -> None:
    """Rules 3 and 7, the finding of the round before: the ledger read must not reveal a dataset
    the reader has no right to. The row of a release has no case, so no case's reach places it;
    it is kept by the reader's own: the administrator, who names every dataset already, and a
    principal that carries the dataset in `principal.datasets`. The compliance role by itself, and
    a reader of other datasets only, are given no release row, and nothing says one was left out. A
    rule file's row and a case's row are read by the role alone, as before. **This is the store's
    rule, asked with principals the test shapes: `GET /v1/exports` never gives it one that carries
    a reach** (outside a case `datasets=[]`), so only the administrator is admitted there; the
    route's own case is `test_at_the_ledger_route_only_the_administrator_is_given_a_release_row`."""
    store = await _ledger_of_three_kinds(FakePool())
    admin = COMPLIANCE.model_copy(update={"datasets": []})
    assert await _seen(store, admin) == {"rel-1", "rule-1", "case-1"}
    assert await _seen(store, COMPLIANCE_ONLY) == {"rule-1", "case-1"}
    other = COMPLIANCE_ONLY.model_copy(update={"datasets": ["ds-other"]})
    assert await _seen(store, other) == {"rule-1", "case-1"}
    reader = COMPLIANCE_ONLY.model_copy(update={"datasets": [DATASET]})
    assert await _seen(store, reader) == {"rel-1", "rule-1", "case-1"}


class _Resolver:
    """A stand-in for the token resolver alone: `get_principal` is the real one, so the principal
    the ledger route is given is the one the app builds, not one a test shaped."""

    def __init__(self, who: Principal) -> None:
        self.who = who

    async def resolve_principal(self, token: str) -> Principal:
        return self.who


def _get_exports(who: Principal, store: Any) -> set[str]:
    """`GET /v1/exports` as `who`, through the client, with the real `get_principal` (so the
    request's principal is `outside_any_case(identity)`, as in a running Conduit) and the real
    ledger store over the fake pool. Returns the ids of the rows the answer holds."""
    from services.api import app as app_module

    app = app_module.app
    saved = getattr(app.state, "principal_resolver", None)
    try:
        app.state.principal_resolver = _Resolver(who)
        app.dependency_overrides[app_module.get_export_ledger] = lambda: store
        response = TestClient(app, raise_server_exceptions=False).get(
            "/v1/exports", headers={"Authorization": "Bearer x"}
        )
    finally:
        app.dependency_overrides.clear()
        app.state.principal_resolver = saved
    assert response.status_code == 200, response.text
    return {entry["id"] for entry in response.json()["entries"]}


async def test_at_the_ledger_route_only_the_administrator_is_given_a_release_row() -> None:
    """Round 5, case 9, through the route as it is (`GET /v1/exports`). The route takes the plain
    principal, which outside a case is `outside_any_case(identity)`: `datasets=[]`, whatever reach
    the token holds. So the only reader the route admits to a dataset's release row is the one who
    names every dataset already (`ADMINISTER_SYSTEM`). A compliance reader whose own identity
    carries the dataset is given the rule file's row and the case's row, no release row and no
    sign that one was left out: the same answer as a compliance reader with another dataset or
    none. Nothing here widens who reads a release row. (The store's own reach branch,
    `test_a_dataset_release_row_reaches_only_a_reader_who_may_know_the_dataset`, answers a
    principal that carries a reach; no request builds one for this route.)"""
    store = await _ledger_of_three_kinds(FakePool())
    admin = COMPLIANCE.model_copy(update={"datasets": [DATASET]})
    assert _get_exports(admin, store) == {"rel-1", "rule-1", "case-1"}
    for reach in ([DATASET], ["ds-other"], []):
        reader = COMPLIANCE_ONLY.model_copy(update={"datasets": reach})
        assert _get_exports(reader, store) == {"rule-1", "case-1"}, reach
    unlimited = COMPLIANCE_ONLY.model_copy(update={"datasets": None})
    assert _get_exports(unlimited, store) == {"rule-1", "case-1"}


async def test_the_ledger_route_test_fails_if_the_route_were_given_the_identitys_reach(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rule 15, the planted fault at the shape the route really sees: `outside_any_case` replaced by
    a pass-through, so the route's principal keeps the reach on the token. The compliance reader of
    `ds-1` is then given the release row, and the route test above would be red. It is the same
    store, the same rows; only the route's principal differs."""
    from services.api import app as app_module

    store = await _ledger_of_three_kinds(FakePool())
    reader = COMPLIANCE_ONLY.model_copy(update={"datasets": [DATASET]})
    assert "rel-1" not in _get_exports(reader, store)
    monkeypatch.setattr(app_module, "outside_any_case", lambda principal: principal)
    assert "rel-1" in _get_exports(reader, store), "the planted fault must show the grant"


async def test_the_release_row_is_left_out_in_the_query_not_after_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rule 15, at the shape the store really sends: the condition is in the `WHERE`, with the
    reader's reach as its parameters (rule 3: not applied after retrieval). Planted: the read as it
    was before this round (no condition) shows the compliance role a release of `ds-1`: red here.
    The real query is Postgres's, so the same case is run live (owed:
    `test_export.py::test_a_release_row_is_left_out_of_the_read_of_a_reader_who_may_not_know_it`)."""
    from services.api import export

    store = await _ledger_of_three_kinds(FakePool())
    assert "rel-1" not in await _seen(store, COMPLIANCE_ONLY)
    for fragment in ("WHERE", "subject_kind IS DISTINCT FROM 'dataset'", "$1::boolean",
                     "subject_id = ANY($2::text[])"):  # fmt: skip
        assert fragment in export.NO_CASE_DATASET_ROWS_SQL
    monkeypatch.setattr(
        export, "NO_CASE_DATASET_ROWS_SQL", "SELECT * FROM export_ledger ORDER BY exported_at DESC"
    )
    assert "rel-1" in await _seen(store, COMPLIANCE_ONLY), "the fake must show the old read red"


async def test_the_store_refuses_a_row_that_says_nothing_of_what_it_concerns() -> None:
    """A row with no case and no subject says nothing of what left: refused before the database."""
    from services.api.export import ExportLedgerEntry

    pool = FakePool()
    entry = ExportLedgerEntry(
        id="x2", investigation_id=None, principal_id=ANALYST.id, artefact_kind="dataset_release",
        handling_level=None, exported_at=NOW, item_count=1, withheld=False, manifest_policy="omit",
    )  # fmt: skip
    with pytest.raises(ValueError, match="subject"):
        await _store(pool).record(entry)
    assert pool.rows == []


async def test_a_database_failure_is_an_audit_write_error_that_holds_no_content() -> None:
    from services.api.audit import AuditWriteError
    from services.api.export import ExportLedgerEntry

    pool = FakePool()
    pool.down = True
    entry = ExportLedgerEntry(
        id="x3", investigation_id=CASE, principal_id=ANALYST.id, artefact_kind="subgraph",
        handling_level="OFFICIAL", exported_at=NOW, item_count=1, withheld=False,
        manifest_policy="omit", subject_kind="case", subject_id=CASE,
    )  # fmt: skip
    with pytest.raises(AuditWriteError) as raised:
        await _store(pool).record(entry)
    assert "subgraph" in str(raised.value) and "unreachable" not in str(raised.value)


def test_the_table_accepts_a_row_with_no_case_and_the_check_asks_for_a_subject() -> None:
    """The table and its migration, read as text (the migration against a live Postgres is
    `test_export.py`'s, owed live): the case is nullable, the subject columns exist, and a row with
    neither a case nor a subject is refused by a check; the migration is idempotent by its words."""
    from services.api.export import ledger_bootstrap_sql, ledger_migration_sql

    columns = _bootstrap_columns()
    assert columns["investigation_id"] is False
    assert columns["handling_level"] is False
    assert {"subject_kind", "subject_id"} <= set(columns)
    create = " ".join(ledger_bootstrap_sql().split())
    assert (
        "CHECK ( investigation_id IS NOT NULL OR "
        "(subject_kind IS NOT NULL AND subject_id IS NOT NULL) )" in create
    )
    migrate = ledger_migration_sql()
    assert "ALTER COLUMN investigation_id DROP NOT NULL" in migrate
    assert "ALTER COLUMN handling_level DROP NOT NULL" in migrate
    assert migrate.count("ADD COLUMN IF NOT EXISTS subject_kind") == 1
    assert migrate.count("ADD COLUMN IF NOT EXISTS subject_id") == 1
    assert "DELETE" not in migrate.upper()


# --- the release's marking ----------------------------------------------------------------------


async def test_a_release_reports_the_highest_marking_of_the_pipelines_it_holds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`export_release` says the marking of what it exported: the highest of the viewable
    pipelines' source handling (a bundle's only marked parts), not of those it left out."""
    from services.api import studio_release

    def draft(classification: str) -> Any:
        return SimpleNamespace(
            dataset_id=DATASET, status=studio_release.StudioRecipeStatus.PUBLISHED,
            handling={"classification": classification, "handling_code": "P",
                      "originator": "unit-1", "owning_unit": "unit-1"},
            source_location=None, pipeline=None,
        )  # fmt: skip

    class _Models:
        async def live(self, dataset_id: str) -> Any:
            return object()

    class _Recipes:
        async def list_all(self, principal: Principal) -> list[Any]:
            return [draft("OFFICIAL"), draft("OFFICIAL-SENSITIVE"), draft("SECRET")]

    class _Sources:
        async def list_for(self, dataset_id: str) -> list[Any]:
            return []

    async def no_lists(*args: Any, **kwargs: Any) -> list[Any]:
        return []

    monkeypatch.setattr(studio_release, "dataset_reference_lists", no_lists)
    monkeypatch.setattr(studio_release, "build_bundle", lambda **kw: {"a.yaml": b"x"})
    reader = ANALYST.model_copy(update={"clearance": "OFFICIAL-SENSITIVE"})
    result = await studio_release.export_release(
        dataset_id=DATASET, principal=reader, metadata=SimpleNamespace(name="n", version="1"),  # type: ignore[arg-type]
        models=_Models(), recipes=_Recipes(), rows_kept=None, staging_storage=None,  # type: ignore[arg-type]
        list_store=None, sources=_Sources(), scheme=_scheme(), secrets=[],  # type: ignore[arg-type]
    )  # fmt: skip
    assert result.left_out == 1
    assert result.marking == "OFFICIAL-SENSITIVE"
