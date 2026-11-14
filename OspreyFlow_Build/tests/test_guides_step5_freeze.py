"""What the v0.5.2 freeze's last features changed that the guides now say (the docs lane's step 5 sweep, parts 1 and
5), each held to the code that decides it, never to its comments (rule 12):

- step U, ADR-150 Amendment 2: the search index rebuilt from the graph wherever OpenSearch is searched, on install
  (`harness/apply.py`), on update (`harness/update.py`) and in the cloud-platform `INSTALL.md` (`runbooks.py`'s
  `_SEARCH_REBUILD`); the install's app registrations counted (`entra_registrations`); and, by step S9,
  `start --build` (`scripts/refresh.py`), last;
- step 3f′, the batch job's limits;
- step 3h, ADR-124 Amendment 19: clusters worked out per reader as nodes enter, never shared;
- R7, the mark for suppression as built.
(Steps 3f and 3f′'s own words are user guide 1.60's, `test_user_guide_batch_expansion.py`; step 3g's, administration
guide 2.06.)
"""

from __future__ import annotations

import ast
import re
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


def function(path: str, name: str) -> str:
    source = read(path)
    node = next(n for n in ast.walk(ast.parse(source)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    return fold(ast.get_source_segment(source, node) or "")


# ---------------------------------------------------------------- step U: the index rebuilt


def test_the_install_rebuilds_the_index_after_the_demo_accounts_and_before_the_packs() -> None:
    apply = read("harness/apply.py")
    accounts, rebuild, seed = (apply.index(s) for s in ("# 4c. The demo analyst's password", "# 4d. The search index", "# 5. Seed"))
    assert accounts < rebuild < seed
    block = fold(apply[rebuild:seed])
    assert 'if search_rebuild.renders_opensearch(compose_file): _run(search_rebuild.rebuild_argv(_compose(compose_file)), stage="search index")' in block
    # `_run` raises on failure, so the install stops there (no try around it in the block).
    assert "try:" not in block and "except" not in block
    assert '"opensearch" in services' in fold(read("harness/search_rebuild.py"))
    text = guide("administration")
    assert ("4. makes the demo accounts (unless `--no-demo-accounts`); 5. where the deployment searches with OpenSearch "
            "(`components.search: opensearch`, the default), rebuilds the search index from the graph, so search "
            "answers from the index at once; a rebuild that fails fails the install, saying so; 6. loads the chosen "
            "demo packs.") in text  # fmt: skip


def test_an_update_rebuilds_the_index_inside_what_rolls_back() -> None:
    source = read("harness/update.py")
    call = source.index('_ok(host, search_rebuild.rebuild_argv(compose), "rebuild the search index")')
    opened = source.rfind("\n    try:\n", 0, call)
    closed = source.index("\n    except UpdateFailed as failed:", call)
    assert opened != -1 and "return _roll_back(" in source[closed : closed + 400], "a failed rebuild rolls the update back"
    assert 'if search_rebuild.renders_opensearch(directory / "compose.yaml"):' in source[opened:call]
    assert ("where the deployment searches with OpenSearch, rebuilds the search index from the graph (an index made "
            "before v0.5.2 is not one v0.5.2 writes to). If anything fails after the backup it **rolls back**") in guide("administration")  # fmt: skip


def test_start_build_rebuilds_last_and_the_guide_says_so() -> None:
    body = function("scripts/refresh.py", "_refresh")
    rebuilt = function("scripts/refresh.py", "_search_index_rebuilt")
    assert body.rstrip().endswith('_search_index_rebuilt(directory / "compose.yaml", compose, run)'), "the last step"
    assert body.index("code = register(") < body.index("_search_index_rebuilt("), "after the sign-in accounts"
    assert "if not search_rebuild.renders_opensearch(compose_file): return" in rebuilt
    assert "run(search_rebuild.rebuild_argv(compose))" in rebuilt
    assert "so search answers only exact identifiers" in rebuilt
    text = guide("administration")
    assert "`start --build` does not rebuild" not in text
    assert ("Where the deployment searches with OpenSearch, `start --build` rebuilds the search index from the graph as "
            "its last step, as `install` and `update` do. If the rebuild fails it says so: the stack is up, search is "
            "limited to exact identifiers, and running `start --build` again rebuilds it") in text  # fmt: skip


def test_the_platform_s_install_rebuilds_the_index_by_a_job_after_its_rollouts() -> None:
    runbooks = read("harness/cloud_platform/runbooks.py")
    assert 'if "searchIndex" in values:\n        rollouts += "\\n" + _SEARCH_REBUILD.rstrip("\\n")' in runbooks
    job = runbooks[runbooks.index('_SEARCH_REBUILD = """') :]
    job = job[: job.index('"""', 25)]
    assert 'kubectl -n "$NS" create job --from=cronjob/ospreyflow-search-rebuild "$J"' in job
    assert "for i in $(seq 60); do" in job and "  sleep 5\n" in job, "five minutes to start: 60 tries, five seconds apart"
    assert '"job/$J" --timeout=30m || ok=0; }' in job
    assert "grep -qx 1 || ok=0; }" in job, "a Job that fails fails the step"
    assert 'kubectl -n "$NS" delete job "$J" --ignore-not-found --wait=false;' in job
    text = guide("administration")
    assert ("the search index rebuilt from the graph by a Job once the Conduit and the workers are rolled out (on a "
            "fresh install and on every upgrade; the step fails, naming the Job and deleting it, if the Job fails, or "
            "has not started in five minutes or finished in 30)") in text  # fmt: skip
    assert "the search index is rebuilt from the graph as on a fresh install" in text


def test_question_11_counts_the_registrations_as_the_install_does() -> None:
    runbooks = fold(read("harness/cloud_platform/runbooks.py"))
    assert "return 2 + int(config.reporting.superset) + int(config.reporting.sync)" in runbooks
    assert runbooks.count("{_COUNT[entra_registrations(config)]} app registrations") == 2, "INSTALL.md counts them"
    assert ("They are two registrations, `client_id` and `api_client_id`, not one, and with reporting on, Superset's "
            "and the report sync's too: the rendered `INSTALL.md` counts them.") in guide("administration")  # fmt: skip


# ---------------------------------------------------------------- step 3f′: the batch job's limits


def test_user_guide_gives_the_batch_job_s_limits_as_the_panel_and_service_do() -> None:
    panel = fold(read("apps/workspace/src/workingset/BatchExpansion.tsx"))
    assert '"You cannot run a batch job in this case: it needs the Editor level, since its result is saved as a view of the case. No job was started."' in panel
    assert '"Your account does not hold the right to expand a case, so it cannot run a batch job. No job was started."' in panel
    assert 'words: job.words || "The batch job is under way."' in panel
    service = read("services/api/batch_expansion.py")
    assert re.search(r"^TIME_LIMIT_SECONDS = 600$", service, re.MULTILINE)
    assert "outcome = await asyncio.wait_for(work, time_limit or TIME_LIMIT_SECONDS)" in service
    text = guide("user")
    assert "A batch job needs the Editor level on the case, since its result is saved as a view of it, and the right to expand" in text
    assert 'While it runs the panel says "The batch job is under way."; one that would take longer than ten minutes is stopped and saves nothing.' in text


# ---------------------------------------------------------------- step 3h: clusters on entry, per reader


def test_user_guide_says_records_arrive_as_one_for_this_reader_alone() -> None:
    service = fold(read("services/api/working_set/service.py"))
    # The add path: clusters for the nodes and resolution links it brought, on its own answer.
    assert "ids = await self._reader_clusters(investigation_id, principal, touching=touched)" in service
    assert "clusters = DeltaReproject( seq=delta.seq, reason=REASON_ENTRY, affected_cluster_ids=ids )" in service
    assert "return ExpansionOutcome(delta=delta, clusters=clusters)" in service
    # The snapshot: every cluster, in full.
    assert "visible_nodes = _with_clusters( visible_nodes, await self._reader_clusters(investigation_id, principal) )" in service
    # Nothing shared: every read strips a stored id.
    assert service.count("_without_cluster(") >= 2
    text = guide("user")
    assert ("Records drawn into the graph, by a search, an expansion or a list, arrive already shown as one where they "
            "match at the case's strictness") in text  # fmt: skip
    assert "What is shown as one is worked out for you alone, from the records you may see: a record hidden from you joins nothing." in text
    assert ("your graph shows it in full when the case is loaded again; an expansion brings it only for the records it "
            "adds.") in text  # fmt: skip


# ---------------------------------------------------------------- R7: the mark for suppression as built


def mark_label() -> str:
    canvas = fold(read("apps/workspace/src/canvas/GlassCanvas.tsx"))
    m = re.search(r'label: suppressionMarks\[nodeId\] \? "Remove suppression mark" : "([^"]+)",', canvas)
    assert m, "the menu's mark item"
    return m.group(1)


def test_user_guide_says_what_a_suppression_mark_does_as_built() -> None:
    canvas = fold(read("apps/workspace/src/canvas/GlassCanvas.tsx"))
    label = mark_label()
    assert label == "Mark for suppression (hides nothing yet)"
    # The reason is the canvas's own, not asked for; the marks start empty and are never read back.
    assert 'const reason = marked ? "" : "Marked from the canvas";' in canvas
    assert "const [suppressionMarks, setSuppressionMarks] = useState< Record<string, string> >({});" in canvas
    assert "/suppression-marks" not in canvas, "the canvas reads the marks back now"
    panel = read("apps/workspace/src/explore/ExplorePanel.tsx")
    assert "· marked for suppression by ${m.marked_by} · ${when(m.marked_at)} · “${m.reason}”" in panel
    # A mark is its own table's row, never a graph write: the store's one graph call reads.
    store = read("services/api/suppression.py")
    assert "CREATE TABLE IF NOT EXISTS suppression_marks (" in store
    assert set(re.findall(r"graph\.(\w+)\(", store)) == {"get_node"}
    # Step two is unbuilt: only the routes hold the marks' store; Explore reads marks to list them; nothing else.
    users = sorted(
        p.relative_to(CORE).as_posix() for root in ("services", "packages") for p in (CORE / root).rglob("*.py")
        if "test" not in p.name and p.name != "suppression.py" and "SuppressionMarkStore" in p.read_text(encoding="utf-8")
    )  # fmt: skip
    assert users == ["services/api/app.py"], users
    text = guide("user")
    assert f"Set picture… and {label};" in text
    assert (f"**{label}** proposes a record for suppression, in the open: the node is marked, and the Explore panel "
            'lists it, with who marked it, when, and "Marked from the canvas".') in text  # fmt: skip
    assert "A mark hides nothing and changes no record" in text
    assert (f"In the session that made the mark, the menu offers **Remove suppression mark** in its place; after a "
            f"reload, or for anyone else, it offers **{label}** again, and choosing it marks the node afresh.") in text  # fmt: skip
    assert "A suppression that takes effect, once its evidence is loaded through the Ingest Studio, is not built yet." in text
