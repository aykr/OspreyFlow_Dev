"""What the v0.5.2 freeze's last features changed that the guides now say (the docs lane's step 5 sweep, part 1), each
held to the code that does it (rule 12):

- step U, ADR-150 Amendment 2: the search index rebuilt from the graph wherever OpenSearch is searched, on install
  (`harness/apply.py`), on update (`harness/update.py`) and in the cloud-platform `INSTALL.md` (`runbooks.py`'s
  `_SEARCH_REBUILD`), and the install's app registrations counted (`entra_registrations`);
- step 3h, ADR-124 Amendment 19: clusters worked out per reader as nodes enter, never shared;
- the install test's date, as the route gives step 6.
(Steps 3f and 3f′, the batch job, were written by their own lane, user guide 1.60, `test_user_guide_batch_expansion.py`;
step 3g, the administrator fallback, administration guide 2.06.)
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

BUILD = Path(__file__).resolve().parents[1]
CORE = BUILD.parent / "OspreyFlow_Core"


def fold(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def guide(name: str) -> str:
    text = (CORE / "docs" / f"{name}-guide.md").read_text(encoding="utf-8")
    return fold(re.sub(r"<!-- document-control:begin -->.*?<!-- document-control:end -->", " ", text, flags=re.DOTALL))


def read(path: str) -> str:
    return (CORE / path).read_text(encoding="utf-8")


# ---------------------------------------------------------------- step U: the index rebuilt


def test_the_install_rebuilds_the_index_after_its_start_and_before_the_demo_packs() -> None:
    apply = read("harness/apply.py")
    start, rebuild, seed = (apply.index(s) for s in ("# 4. Up, then", "# 4d. The search index", "# 5. Seed"))
    assert start < rebuild < seed
    block = fold(apply[rebuild:seed])
    assert 'if search_rebuild.renders_opensearch(compose_file): _run(search_rebuild.rebuild_argv(_compose(compose_file)), stage="search index")' in block
    text = guide("administration")
    assert ("4. where the deployment searches with OpenSearch (`components.search: opensearch`, the default), rebuilds "
            "the search index from the graph, so search answers from the index at once; a rebuild that fails fails "
            "the install, saying so; 5. makes the demo accounts") in text  # fmt: skip


def test_an_update_rebuilds_the_index_or_rolls_back() -> None:
    update = fold(read("harness/update.py"))
    assert ('if search_rebuild.renders_opensearch(directory / "compose.yaml"): _ok(host, '
            'search_rebuild.rebuild_argv(compose), "rebuild the search index")') in update  # fmt: skip
    assert ("where the deployment searches with OpenSearch, rebuilds the search index from the graph (an index made "
            "before v0.5.2 is not one v0.5.2 writes to). If anything fails after the backup it **rolls back**") in guide("administration")  # fmt: skip


def test_the_platform_s_install_rebuilds_the_index_by_a_job_after_its_rollouts() -> None:
    runbooks = read("harness/cloud_platform/runbooks.py")
    assert 'if "searchIndex" in values:\n        rollouts += "\\n" + _SEARCH_REBUILD.rstrip("\\n")' in runbooks
    job = runbooks[runbooks.index('_SEARCH_REBUILD = """') :]
    job = job[: job.index('"""', 25)]
    assert "five minutes to start,\n# 30 to finish, deleted and named if it does not." in job
    assert 'kubectl -n "$NS" create job --from=cronjob/ospreyflow-search-rebuild "$J"' in job
    assert "--timeout=30m" in job
    text = guide("administration")
    assert ("the search index rebuilt from the graph by a Job once the Conduit and the workers are rolled out (on a "
            "fresh install and on every upgrade; the step fails, naming the Job, if it has not started in five "
            "minutes or finished in 30)") in text  # fmt: skip
    assert "the search index is rebuilt from the graph as on a fresh install" in text


def test_question_11_counts_the_registrations_as_the_install_does() -> None:
    runbooks = fold(read("harness/cloud_platform/runbooks.py"))
    assert "return 2 + int(config.reporting.superset) + int(config.reporting.sync)" in runbooks
    assert ("They are two registrations, `client_id` and `api_client_id`, not one, and with reporting on, Superset's "
            "and the report sync's too: the rendered `INSTALL.md` counts them.") in guide("administration")  # fmt: skip


def test_the_install_test_s_date_is_the_route_s_step_6() -> None:
    route = (BUILD / "process" / "lanes" / "route.tsv").read_text(encoding="utf-8")
    row = next(line.split("\t") for line in route.splitlines() if line.startswith("6\t"))
    day = date.fromisoformat(row[3])
    words = f"{day.day} {day.strftime('%B')} {day.year}"
    assert f"v0.5.2's install test, planned for {words} on a kind cluster (route step 6)" in guide("administration")


# ---------------------------------------------------------------- step 3h: clusters on entry, per reader


def test_user_guide_says_records_arrive_as_one_for_this_reader_alone() -> None:
    service = fold(read("services/api/working_set/service.py"))
    assert 'REASON_ENTRY = "resolution_on_entry"' in service
    assert "async def _reader_clusters(" in service and "def _without_cluster(node: Node) -> Node:" in service
    assert "so the only cluster id a reader is ever sent is one computed for them (`_reader_clusters`)" in service
    text = guide("user")
    assert ("Records drawn into the graph, by a search, an expansion or a list, arrive already shown as one where they "
            "match at the case's strictness") in text  # fmt: skip
    assert "What is shown as one is worked out for you alone, from the records you may see: a record hidden from you joins nothing." in text
    assert "your graph follows the next time you expand it or the case is loaded again, not at once." in text


# ---------------------------------------------------------------- R7: a mark for suppression, built as the first step


def test_user_guide_says_a_suppression_mark_hides_nothing_and_the_suppression_is_not_built() -> None:
    canvas = fold(read("apps/workspace/src/canvas/GlassCanvas.tsx"))
    assert 'label: suppressionMarks[nodeId] ? "Remove suppression mark" : "Mark for suppression",' in canvas
    panel = read("apps/workspace/src/explore/ExplorePanel.tsx")
    assert "· marked for suppression by ${m.marked_by} · ${when(m.marked_at)} · “${m.reason}”" in panel
    store = fold(read("services/api/suppression.py"))
    assert "reason TEXT NOT NULL" in store and "marks live here, in their own table" in store
    # The second step is unbuilt: nothing in ingest supersedes or suppresses a record.
    ingest = [p for p in (CORE / "services" / "ingest").rglob("*.py") if re.search(r"suppress", p.read_text(encoding="utf-8"), re.IGNORECASE)]
    assert ingest == [], "a suppression from ingest exists now: the guide must say what it does"
    text = guide("user")
    assert ("The node is marked, with your reason, and the Explore panel lists it, with who marked it and when; "
            "**Remove suppression mark** takes the mark off.") in text  # fmt: skip
    assert "A mark hides nothing and changes no record" in text
    assert "A suppression that takes effect, once its evidence is loaded through the Ingest Studio, is not built yet." in text
