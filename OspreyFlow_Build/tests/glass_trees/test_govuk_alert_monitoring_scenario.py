"""Scenario AM: the alert monitoring figures as a GOV.UK page, a table and a plain SVG chart of the same figures (slice GR3a, build
GR3; ADR-152 decisions 8, 10 and 12 and invariants I1, I2, I7 and I15; the owner's rulings of 24 November 2026).

**There is no React-first proof for this page** (decision 12 asks for one only "where one exists"): the React board
(`apps/workspace/src/reports/AlertMonitoringBoard.tsx`) draws its bars as divs with inline styles and has no scenario in `spec/08`.
The scenario is written first, from the board's figures and the report route, and the page test
(`apps/pages/test/govuk/alert-monitoring.test.ts`, vitest, the real service started for the GOV.UK tree) is the proof.

This file holds the document, the page test, the function row, the route list and the chart rule in step, and pins the two answers of
the report route that the owner's ruling rests on (item 2 of the slice's brief):

* a scenario with no page test, or a page test with no scenario           -> `test_every_scenario_has_a_page_test_and_back`
* a row whose cited words are not in the file it cites                     -> `test_every_row_cites_words_that_are_in_the_source`
* `spec/02` silent on the chart rule or the ruling                         -> `test_spec_02_says_the_chart_rule`
* the figures row left without its scenarios, or the dashboards row given
  a slice, a route or a scenario                                            -> `test_the_figures_row_has_its_scenarios`
* the route list without the page's path                                   -> `test_the_route_list_holds_the_page`
* the Conduit answering a person with no level on the case other than it
  answers a case that is not there                                         -> `test_a_non_viewer_is_answered_as_a_missing_case_by_the_report_route`
* the Conduit answering a person without `read_reports` as anything but
  its own refusal (403 `right_required`), which the page then flattens     -> `test_a_reader_without_read_reports_is_refused_by_the_report_route`

**What the owner's ruling "a non-viewer at the report route gets 404, the same as a missing report" meant, read from the code
(`services/api/app.py`, `read_case_report`, and `investigations.py`, `InvestigationStore.get_authorized`):** the route's viewer
dependency (`InvestigationViewerDep`, level Viewer, the lowest) answers a person who holds no level on the case, in the unit or not,
shared with or not, with the `InvestigationNotFoundError` a case that is not there gets: 404 `{"error": "investigation_not_found"}`,
byte for byte. So the Conduit already does what the ruling says, and this file pins it (rule 4). A person who lacks the *right*
`read_reports` is a different refusal, made first and for every right-gated route (ADR-112): 403 `right_required`. That is pinned as it
is and is not changed here (a Conduit change is the owner's); **the page answers both as one page** (the vitest cases AM6).

THE FOLDERS THIS TEST WALKS (the conductor's scan-map row): none. It reads named files only, by path, and plants every fault in an
in-memory copy of what it read; it never writes into the repository. The two Conduit cases run the real app in process, with stores
answering from memory (no database, no port), as `tests/services/api/test_reports_viewer_journey.py` does. The files, from the
repository's root: `OspreyFlow_Build/spec/{08_ACCEPTANCE_SCENARIOS,02_GLASS_FRONTEND}.md`,
`OspreyFlow_Build/tests/services/api/test_reports_viewer_journey.py` (its harness is imported), and under `OspreyFlow_Core`:
`apps/pages/FUNCTIONS.yaml`, `apps/pages/tree-govuk/routes.yaml`, `apps/pages/test/govuk/alert-monitoring.test.ts`,
`apps/pages/test/govuk/keyboard/alert-monitoring.spec.ts`, `apps/pages/server/{alertMonitoring,pageList}.ts`,
`apps/pages/server/views/alertMonitoringWords.ts`, `apps/pages/tree-govuk/alert-monitoring.njk`,
`apps/workspace/src/reports/AlertMonitoringBoard.tsx`, `services/api/{app,investigations,reports}.py`.

Every planted fault is the real inputs with one thing changed (rule 15), run through the same `problems` the real inputs go through,
which finds nothing in them; the Conduit plant is the real store answering the non-viewer as a refused level (403), the shape the
route would emit if its viewer dependency were wrong.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from schemas.domain import Principal

BUILD = Path(__file__).resolve().parents[2]
ROOT = BUILD.parent
CORE = ROOT / "OspreyFlow_Core"
PAGES = CORE / "apps" / "pages"
SPEC = BUILD / "spec"

SPEC_08 = SPEC / "08_ACCEPTANCE_SCENARIOS.md"
SPEC_02 = SPEC / "02_GLASS_FRONTEND.md"
FUNCTIONS = PAGES / "FUNCTIONS.yaml"
ROUTES = PAGES / "tree-govuk" / "routes.yaml"
PAGE_TEST = PAGES / "test" / "govuk" / "alert-monitoring.test.ts"
KEYBOARD_TESTS = {
    "keyboard/alert-monitoring.spec.ts": PAGES / "test" / "govuk" / "keyboard" / "alert-monitoring.spec.ts",
}

SECTION = "## Scenario AM"
ID = re.compile(r"^AM\d+$")
TITLE = re.compile(r"""\b(?:it|test)\(\s*(?:"|'|`)(AM\d+): """)
PAGE_TEST_NAME = "alert-monitoring.test.ts"
PATH = "/reports"

#: What each behaviour of the page is, by id: a behaviour with no scenario is one nobody will build or test.
BRIEF: dict[str, tuple[str, ...]] = {
    "the figures as tables: a caption, column headers, a row header, the period and the count, as the route sends them": ("AM1",),
    "the same figures as a plain SVG bar chart, classes only, a text alternative, the table after it": ("AM2",),
    "only what the route sends for this reader: no total of the page's own, held rows only when sent": ("AM3",),
    "a report past its bound is said in words with the way out, never a figure": ("AM4",),
    "no alerts in the period is said in words, with no empty chart": ("AM5",),
    "a case that is missing, a non-viewer and a reader without read_reports are one answer": ("AM6",),
    "a Conduit that fails says so and draws no figure": ("AM7",),
    "scripts off, no inline style, GET only, no action beyond links, and the tab order": ("AM8",),
    "the route list, the one Conduit read, and no Superset board": ("AM9",),
    "the Conduit's own two refusals, pinned": ("AM10",),
    "each check is red against the real page with one thing changed": ("AM11",),
}

# ---------------------------------------------------------------------------------------------------- reading the scenario


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _find_file(name: str) -> Path | None:
    for base in (BUILD, CORE, ROOT):
        candidate = base / name
        if candidate.is_file():
            return candidate
    return None


def section_of(spec_08: str) -> str:
    start = spec_08.find(SECTION)
    if start == -1:
        return ""
    end = spec_08.find("\n## ", start + 1)
    return spec_08[start : end if end != -1 else len(spec_08)]


def rows_of(section: str) -> dict[str, list[str]]:
    """`{id: [behaviour, read-from, page test, tree]}` for each table row of the section."""
    rows: dict[str, list[str]] = {}
    for line in section.splitlines():
        if not line.startswith("| AM"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split(" | ")]
        if len(cells) == 5:
            rows[cells[0]] = cells[1:]
    return rows


def cited(cell: str) -> list[tuple[str, list[str]]]:
    """Each `path` of a read-from cell with the quoted words that go with it (the parts are split at `;`)."""
    out: list[tuple[str, list[str]]] = []
    for part in cell.split(";"):
        paths = re.findall(r"`([^`]+)`", part)
        words = re.findall(r'"([^"]+)"', part)
        if paths and words:
            out.append((paths[0], words))
    return out


def page_test_ids(text: str) -> set[str]:
    return set(TITLE.findall(text))


def inputs() -> dict[str, Any]:
    """Everything `problems` reads, as text or parsed data: a plant changes one entry."""
    return {
        "spec_08": read(SPEC_08),
        "spec_02": read(SPEC_02),
        "functions": yaml.safe_load(read(FUNCTIONS))["functions"],
        "routes": yaml.safe_load(read(ROUTES))["routes"],
        "page_test": read(PAGE_TEST),
    }


# ---------------------------------------------------------------------------------------------------- the checks


def scenario_problems(data: dict[str, Any]) -> list[str]:
    found: list[str] = []
    section = section_of(data["spec_08"])
    if not section:
        return [f"spec/08 has no section headed {SECTION!r}"]
    rows = rows_of(section)
    if not rows:
        return ["the scenario AM section has no table row"]
    for row_id, cells in rows.items():
        if not ID.match(row_id):
            found.append(f"{row_id} is not an id of the form AM<number>")
        behaviour, read_from, page_test, tree = cells
        if not behaviour:
            found.append(f"{row_id} says no behaviour")
        if tree != "GOV.UK":
            found.append(f"{row_id} runs on {tree!r}: the alert monitoring page is the GOV.UK tree's")
        if not read_from:
            found.append(f"{row_id} says nothing of what it was read from")
        if PAGE_TEST_NAME not in page_test and "spec.ts" not in page_test and ".py" not in page_test:
            found.append(f"{row_id} names no page test")
    for behaviour, ids in BRIEF.items():
        for row_id in ids:
            if row_id not in rows:
                found.append(f"the behaviour {behaviour!r} has no scenario {row_id}")
    named_in_tests = page_test_ids(data["page_test"])
    page_rows = {row_id for row_id, cells in rows.items() if PAGE_TEST_NAME in cells[2]}
    for row_id in sorted(page_rows - named_in_tests):
        found.append(f"{row_id} names {PAGE_TEST_NAME} but no case of it is titled {row_id}")
    for row_id in sorted(named_in_tests - set(rows)):
        found.append(f"{PAGE_TEST_NAME} has a case titled {row_id}, which is no scenario")
    for text in ("counted for the reader", "scripts off", "404", "no new Conduit route"):
        if text not in section:
            found.append(f"the scenario's own text does not say {text!r}")
    return found


def citation_problems(data: dict[str, Any]) -> list[str]:
    found: list[str] = []
    for row_id, cells in rows_of(section_of(data["spec_08"])).items():
        for path, words in cited(cells[1]):
            source = _find_file(path)
            if source is None:
                found.append(f"{row_id} cites {path}, which is not a file")
                continue
            text = read(source)
            found += [f"{row_id}: {path} does not hold {word!r}" for word in words if word not in text]
    return found


def spec_02_problems(data: dict[str, Any]) -> list[str]:
    match = re.search(r"^### 2\.0f .*$", data["spec_02"], flags=re.M)
    if not match:
        return ["spec/02 has no section 2.0f on the GOV.UK tree's charts"]
    rest = data["spec_02"][match.end() :]
    end = re.search(r"^#{2,3} ", rest, flags=re.M)
    body = rest[: end.start() if end else len(rest)]
    found: list[str] = []
    for text in (
        "plain SVG",
        "classes",
        "no library",
        "no inline style",
        "table of the same figures",
        "24 November 2026",
        "text alternative",
        "`rect`",
    ):
        if text not in body:
            found.append(f"spec/02 section 2.0f does not say {text!r}")
    return found


def function_problems(data: dict[str, Any]) -> list[str]:
    found: list[str] = []
    rows = {row["id"]: row for row in data["functions"]}
    figures = rows.get("reports-figures")
    if figures is None:
        return ["the row reports-figures is missing"]
    ids = {item.strip() for item in figures["scenario"].split(",") if item.strip()}
    if not ids or not all(ID.match(item) for item in ids):
        found.append(f"the figures row's scenario is {figures['scenario']!r}, not AM ids")
    elif ids != set(rows_of(section_of(data["spec_08"]))):
        found.append("the figures row's scenario ids are not the section's rows")
    if figures["slice"] != "GR3":
        found.append(f"the figures row's slice is {figures['slice']!r}, not GR3")
    if figures["route"] != PATH:
        found.append(f"the figures row's route is {figures['route']!r}, not {PATH} (every page's row names its route: help.test.ts HP9)")
    dashboards = rows.get("reports-dashboards", {})
    if dashboards.get("slice") != "none named" or dashboards.get("route") or dashboards.get("scenario"):
        found.append("the dashboards row must be later: slice 'none named', no route, no scenario")
    return found


def route_problems(data: dict[str, Any]) -> list[str]:
    found: list[str] = []
    if PATH not in data["routes"]:
        found.append(f"the route list {data['routes']!r} does not hold {PATH}")
    if data["routes"] != sorted(set(data["routes"]), key=data["routes"].index):
        found.append("the route list names a path twice")
    return found


# ---------------------------------------------------------------------------------------------------- the real inputs


def test_the_real_inputs_have_no_problem() -> None:
    data = inputs()
    for check in (scenario_problems, citation_problems, spec_02_problems, function_problems, route_problems):
        assert check(data) == [], check.__name__


def test_every_scenario_has_a_page_test_and_back() -> None:
    assert scenario_problems(inputs()) == []
    assert PAGE_TEST.is_file()
    section = section_of(read(SPEC_08))
    for name, path in KEYBOARD_TESTS.items():
        assert path.is_file(), f"AM8 names {name}, which is not a file"
        assert name in section, f"no row of the scenario names {name}"


def test_every_row_cites_words_that_are_in_the_source() -> None:
    assert citation_problems(inputs()) == []


def test_spec_02_says_the_chart_rule() -> None:
    assert spec_02_problems(inputs()) == []


def test_the_figures_row_has_its_scenarios() -> None:
    assert function_problems(inputs()) == []


def test_the_route_list_holds_the_page() -> None:
    assert route_problems(inputs()) == []


# ---------------------------------------------------------------------------------------------------- the Conduit's own two answers (AM10)
#
# The harness is `test_reports_viewer_journey.py`'s: the real app, a principal handed to the routes, every store but the case store
# answering empty. The case store here is the *real* `InvestigationStore`, over a pool that answers from memory what its one query
# would return: no row for a case that is not there, and a row with no grant and no unit-wide level for a case the person may not open.

CASE_WITH_NO_LEVEL = "case-nobody-shared"
MISSING_CASE = "case-that-is-not-there"
READS = Principal(id="reader-1", clearance="SECRET", org_unit="unit-1", roles=["reports_viewer"])
NO_RIGHT = Principal(id="analyst-0", clearance="SECRET", org_unit="unit-1", roles=["viewer"])


class _Connection:
    async def fetchrow(self, sql: str, *args: Any) -> dict[str, Any] | None:
        if args[0] != CASE_WITH_NO_LEVEL:
            return None
        from datetime import UTC, datetime

        return {
            "id": CASE_WITH_NO_LEVEL,
            "name": "A case in the unit that nobody has shared",
            "created_at": datetime(2026, 1, 1, tzinfo=UTC),
            "created_by": "someone-else",
            "owning_unit": "unit-1",
            "domains": None,
            "grant_level": None,
            "unit_level": None,
        }


class _Pool:
    @asynccontextmanager
    async def acquire(self) -> Any:
        yield _Connection()


@pytest.fixture
def report_route(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[Principal], TestClient]]:
    from services.api.app import app, get_investigations
    from services.api.investigations import InvestigationStore

    from tests.services.api.test_reports_viewer_journey import _journey_client

    def make(who: Principal) -> TestClient:
        client = _journey_client(monkeypatch, who)
        app.dependency_overrides[get_investigations] = lambda: InvestigationStore(_Pool())  # type: ignore[arg-type]
        return client

    yield make
    app.dependency_overrides.clear()


def answer(client: TestClient, case: str) -> tuple[int, Any]:
    response = client.get(f"/v1/investigations/{case}/reports", headers={"Authorization": "Bearer x"})
    return response.status_code, response.json()


def test_a_non_viewer_is_answered_as_a_missing_case_by_the_report_route(
    report_route: Callable[[Principal], TestClient],
) -> None:
    """The owner's ruling (24 November 2026): a non-viewer gets 404, the same as a missing report. The route already does it:
    a person holding `read_reports` but no level on the case is answered with the body a case that is not there is."""
    client = report_route(READS)
    missing = answer(client, MISSING_CASE)
    not_shared = answer(client, CASE_WITH_NO_LEVEL)
    assert missing == (404, {"error": "investigation_not_found"})
    assert not_shared == missing, "a case the person may not open is answered other than a case that is not there"


def test_a_reader_without_read_reports_is_refused_by_the_report_route(
    report_route: Callable[[Principal], TestClient],
) -> None:
    """Pinned as it is: the right is asked before the case, for every right-gated route (ADR-112), and it names the right. The
    page, not the Conduit, makes this and the 404 one page for the person (AM6); changing the Conduit is the owner's."""
    client = report_route(NO_RIGHT)
    for case in (MISSING_CASE, CASE_WITH_NO_LEVEL):
        status, body = answer(client, case)
        assert status == 403
        assert body["detail"] == {"error": "right_required", "right": "read_reports"}


def test_the_non_viewer_check_fails_for_a_viewer_dependency_that_refuses_with_403(
    report_route: Callable[[Principal], TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15: the real store made to answer a case with no level as a level too low (403, the shape the route would emit)
    is not the answer a missing case gets, and the comparison the test above makes sees it."""
    from services.api.investigations import (
        InsufficientAccessError,
        InvestigationNotFoundError,
        InvestigationStore,
    )

    real = InvestigationStore.get_authorized

    async def refusing(self: Any, investigation_id: str, principal: Principal, *, need: Any) -> Any:
        try:
            return await real(self, investigation_id, principal, need=need)
        except InvestigationNotFoundError:
            if investigation_id == CASE_WITH_NO_LEVEL:
                raise InsufficientAccessError("viewer access is needed on this case") from None
            raise

    monkeypatch.setattr(InvestigationStore, "get_authorized", refusing)
    client = report_route(READS)
    assert answer(client, CASE_WITH_NO_LEVEL) != answer(client, MISSING_CASE)


# ---------------------------------------------------------------------------------------------------- ADR-152 I15, the Python half (AM3)
#
# `test_the_alert_monitoring_page_shows_only_the_readers_own_counts` is a pair: this half, and the vitest case of the same name in
# `alert-monitoring.test.ts` (the page, over a fixture Conduit that counts as the reader and refuses what the route refuses). This
# half asks the *route*: two readers of different clearance, one world of alerts, and each is answered the figures of what that
# reader may see, the hidden ones in no total and in no week or rule. **What stands in for what:** the queue's all-or-nothing check
# (`alert_queue.monitoring_queue_and_left_out`, which reads the graph) is replaced by a function of the reader it is handed, so this
# half proves the route gives the check the *reader* and adds up only what comes back (the fault I15 names: one fetch, one identity,
# shown to everyone); that the check itself leaves a hidden alert out of every figure is the live test
# `tests/services/api/test_reports.py::test_a_hidden_alert_changes_no_figure`, which needs the stores and is not run here.

_NODE_RANK = {"n-official": 0, "n-secret": 1}
_CLEARANCE_RANK = {"OFFICIAL": 0, "SECRET": 1}
SECRET_ONLY_TYPOLOGY = "circular_flow"
OFFICIAL_READER = Principal(id="reader-1", clearance="OFFICIAL", org_unit="unit-1", roles=["reports_viewer"])
SECRET_READER = Principal(id="reader-1", clearance="SECRET", org_unit="unit-1", roles=["reports_viewer"])


def _world() -> list[Any]:
    from datetime import UTC, datetime, timedelta

    from schemas.domain import Alert, AlertMode, QueuedAlert

    when = datetime.now(UTC) - timedelta(days=1)
    made = []
    for number, (typology, node) in enumerate(
        [("structuring", "n-official")] * 3 + [("rapid_movement", "n-official")] * 2 + [(SECRET_ONLY_TYPOLOGY, "n-secret")] * 5
    ):
        alert = Alert(id=f"a-{number}", rule_id=f"typology:{typology}", owner_id="raiser", mode=AlertMode.FULL,
                      created_at=when, typology=typology, referent_node_ids=[node])  # fmt: skip
        made.append(QueuedAlert(alert=alert, summary="", kind="typology"))
    return made


async def _as_the_reader(store: Any, graph: Any, analytics: Any, investigation_id: str, reader: Principal, **kwargs: Any) -> Any:
    rank = _CLEARANCE_RANK[reader.clearance]
    world = _world()
    shown = [q for q in world if all(_NODE_RANK[n] <= rank for n in q.alert.referent_node_ids)]
    return shown, len(shown) != len(world)


async def _as_one_identity(store: Any, graph: Any, analytics: Any, investigation_id: str, reader: Principal, **kwargs: Any) -> Any:
    """The fault: one read, as an identity that sees everything, for every reader."""
    return _world(), False


def _counted(figures: dict[str, Any]) -> dict[str, Any]:
    monitoring = figures["monitoring"]
    return {
        "total": figures["alerts_total"],
        "by_rule": sorted({(c["typology"], c["count"]) for c in monitoring["raised_by_rule"] if c["label"] == "typology"}),
    }


def hidden_counts_leak(seen_by_official: dict[str, Any]) -> list[str]:
    """Every way the official reader's figures show what only the secret reader may see: the same check reads the real answer and each plant."""
    found: list[str] = []
    counted = _counted(seen_by_official)
    if counted["total"] != 5:
        found.append(f"the official reader's total is {counted['total']}, not the 5 they may see")
    if any(typology == SECRET_ONLY_TYPOLOGY for typology, _ in counted["by_rule"]):
        found.append("a rule that only the secret reader may see is in the official reader's figures")
    return found


def _figures_as(client: TestClient, who: Principal) -> dict[str, Any]:
    from services.api.app import app, get_principal

    app.dependency_overrides[get_principal] = lambda: who
    response = client.get("/v1/investigations/case-1/reports", headers={"Authorization": "Bearer x"})
    assert response.status_code == 200, response.text
    return dict(response.json())


def test_the_alert_monitoring_page_shows_only_the_readers_own_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    """The route's half of I15: counted as the reader asking, each time, and never a total the page could then show to everyone."""
    from services.api import reports
    from services.api.app import app

    from tests.services.api.test_reports_viewer_journey import _journey_client

    try:
        client = _journey_client(monkeypatch, OFFICIAL_READER)
        monkeypatch.setattr(reports, "monitoring_queue_and_left_out", _as_the_reader)
        official = _figures_as(client, OFFICIAL_READER)
        secret = _figures_as(client, SECRET_READER)
        official_again = _figures_as(client, OFFICIAL_READER)
        assert hidden_counts_leak(official) == []
        assert _counted(secret)["total"] == 10, "the secret reader's own figures are the whole world's"
        assert any(t == SECRET_ONLY_TYPOLOGY for t, _ in _counted(secret)["by_rule"])
        assert _counted(official_again) == _counted(official), "a second read as the first reader is answered from the other reader's"
        assert "hidden" not in str(official).lower()
    finally:
        app.dependency_overrides.clear()


def test_the_leak_check_fails_for_one_identity_read_for_every_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rule 15: the same route with the queue read as one identity that sees everything, which is the fault I15 names, is flagged."""
    from services.api import reports
    from services.api.app import app

    from tests.services.api.test_reports_viewer_journey import _journey_client

    try:
        client = _journey_client(monkeypatch, OFFICIAL_READER)
        monkeypatch.setattr(reports, "monitoring_queue_and_left_out", _as_one_identity)
        leaks = hidden_counts_leak(_figures_as(client, OFFICIAL_READER))
        assert any("not the 5" in message for message in leaks) and any("only the secret reader" in message for message in leaks), leaks
    finally:
        app.dependency_overrides.clear()


def test_the_vitest_half_of_the_pair_is_there() -> None:
    assert "test_the_alert_monitoring_page_shows_only_the_readers_own_counts" in read(PAGE_TEST), (
        "I15's page half is not named in alert-monitoring.test.ts"
    )


# ---------------------------------------------------------------------------------------------------- planted faults (rule 15)


def _without_row(row_id: str) -> Callable[[dict[str, Any]], None]:
    def plant(data: dict[str, Any]) -> None:
        data["spec_08"] = "\n".join(line for line in data["spec_08"].splitlines() if not line.startswith(f"| {row_id} |"))

    return plant


def _replace(key: str, old: str, new: str) -> Callable[[dict[str, Any]], None]:
    def plant(data: dict[str, Any]) -> None:
        assert old in data[key], f"the plant's anchor {old!r} is not in {key}"
        data[key] = data[key].replace(old, new, 1)

    return plant


def _in_section(old: str, new: str) -> Callable[[dict[str, Any]], None]:
    """A change inside scenario AM's own section, never an earlier place that happens to hold the same words."""

    def plant(data: dict[str, Any]) -> None:
        section = section_of(data["spec_08"])
        assert old in section, f"the plant's anchor {old!r} is not in the scenario AM section"
        data["spec_08"] = data["spec_08"].replace(section, section.replace(old, new), 1)

    return plant


def _in_chart_rule(old: str, new: str) -> Callable[[dict[str, Any]], None]:
    """A change inside spec/02's section 2.0f, never an earlier place that happens to hold the same words."""

    def plant(data: dict[str, Any]) -> None:
        start = data["spec_02"].index("### 2.0f ")
        end = data["spec_02"].index("\n### ", start + 1)
        section = data["spec_02"][start:end]
        assert old in section, f"the plant's anchor {old!r} is not in section 2.0f"
        data["spec_02"] = data["spec_02"][:start] + section.replace(old, new) + data["spec_02"][end:]

    return plant


def _row(row_id: str, **changes: Any) -> Callable[[dict[str, Any]], None]:
    def plant(data: dict[str, Any]) -> None:
        next(r for r in data["functions"] if r.get("id") == row_id).update(changes)

    return plant


PLANTS: list[tuple[str, Callable[[dict[str, Any]], None], Callable[[dict[str, Any]], list[str]], str]] = [
    ("a scenario row removed", _without_row("AM4"), scenario_problems, "no scenario AM4"),
    ("a page test case with no scenario row", _without_row("AM9"), scenario_problems, "titled AM9"),
    ("a row run on the other tree", _in_section("| GOV.UK |", "| Default |"), scenario_problems, "GOV.UK tree's"),
    ("the 404 sentence left out", _in_section("404", "four hundred and four"), scenario_problems, "'404'"),
    ("words a source does not hold", _in_section("Raised each week", "Raised every week"), citation_problems, "does not hold"),
    ("the chart rule left out of spec/02", _in_chart_rule("no inline style", "any style"), spec_02_problems, "no inline style"),
    ("the ruling left out of spec/02", _in_chart_rule("table of the same figures", "table"), spec_02_problems, "same figures"),
    ("the figures row with no scenario", _row("reports-figures", scenario=""), function_problems, "not AM ids"),
    ("the figures row on the wrong slice", _row("reports-figures", slice="R7"), function_problems, "not GR3"),
    ("the figures row without its route", _row("reports-figures", route=""), function_problems, "not /reports"),
    ("the dashboards row given a slice", _row("reports-dashboards", slice="GR3"), function_problems, "must be later"),
    ("the dashboards row given a route", _row("reports-dashboards", route=PATH), function_problems, "must be later"),
    ("the page's path left out of the route list", lambda d: d["routes"].remove(PATH), route_problems, "does not hold"),
    ("the page's path listed twice", lambda d: d["routes"].append(PATH), route_problems, "twice"),
]


@pytest.mark.parametrize(("label", "plant", "check", "expected"), PLANTS, ids=[p[0] for p in PLANTS])
def test_the_check_fails_for_each_planted_fault(
    label: str,
    plant: Callable[[dict[str, Any]], None],
    check: Callable[[dict[str, Any]], list[str]],
    expected: str,
) -> None:
    data = inputs()
    assert check(data) == [], f"{check.__name__} is not clean on the real inputs, so a plant proves nothing"
    plant(data)
    problems = check(data)
    assert any(expected in message for message in problems), f"{label}: {problems!r} does not say {expected!r}"
