"""A subscribed deployment-wide list read by a Lookup at every place a staged pipeline runs (ADR-140
Amendment 13 point 10; the studio lane's review of L1.5, carried into studio-b's L1.8).

`staging_catalogue.run_staging` judges its steps again, and refuses a Lookup of a deployment-wide list
the dataset does not subscribe to. Every caller must therefore hand it the dataset's subscriptions.
Three did not: the drawer's sample (`studio_staging.preview_staging`), Test
(`studio_verify` through `staged_run.dry_run_staged_recipe`) and the run (`pipeline_run` through
`staged_run.prepare_staged_load`). So a subscribed Lookup passed save and publish, then was refused at
each of them. It failed closed, so nothing leaked, but no subscribed Lookup could run.
`test_subscribed_lists_seam.py` stopped at `lists_for_run` and could not see it.

What a mistake would do, and the case that catches it:
- the drawer's sample refusing a subscribed list — `test_the_drawer_s_sample_reads_a_subscribed_list`;
- Test refusing it — `test_test_reads_a_subscribed_list`;
- the run refusing it — `test_the_run_reads_a_subscribed_list`;
- a fourth caller of the three that forgets the subscriptions —
  `test_every_caller_hands_the_staging_engine_the_subscriptions`;
- the subscribed list's rows, a read newly opened at the sample and at Test, reaching a principal who may
  not read the dataset (rule 4): one whose case reads no dataset of it, and one whose case reads another
  dataset that subscribes to the same list —
  `test_a_subscribed_list_is_withheld_from_a_case_not_reading_the_dataset_at_the_sample` and `..._at_test`;
- the subscriptions widening what a Lookup reads, at each of the three: a list another dataset subscribes
  to and this one does not — `test_another_dataset_s_subscription_is_refused_at_the_sample`,
  `..._at_test` and `..._at_the_run`;
- the check itself blind to a caller that names `subscribed=` empty, imports the engine under another
  name, or hands it on through `partial`, `run_in_executor` or a bare reference —
  `test_the_caller_check_finds_a_call_that_forgets_them` (rule 15).

The fixture is the Studio's own staged pipeline (`test_studio_staging_routes.py`, phase 7's visits
and contacts, synthetic: rule 9). Its establishments Lookup reads a deployment-wide list named
`establishments` that the dataset subscribes to, and the dataset's own model names no list. Shown red
at each call site before the fix (`process/lanes/studio-b/l1.8/red-carry-subscribed.txt`).
"""

from __future__ import annotations

import ast
import shutil
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from services.api.app import app, get_target_models
from services.api.list_connector import InMemoryListStore, ParquetListRows, deployment_reference

from schemas.ingest import PipelineGraph, StudioRecipeDraft, StudioRecipeStatus
from schemas.list_connector import BlankListMapping, DeploymentListInput
from schemas.staging import AddedColumn
from tests.ingest.test_staged_pipeline_run import HANDLING, LOADER
from tests.ingest.test_staged_run import FIXTURES, ONTOLOGY, RECIPE, SCHEME
from tests.services.api.test_studio_staging_routes import (  # noqa: F401  (fixtures)
    RECIPE_URL,
    STORAGE,
    _draft,
    _Models,
    _pipeline,
    _preview,
    _update,
    client,
    git_repo,
    graph_client,
    staged,
    store,
)

# ruff: noqa: F811  (the imported fixtures are every test's own same-named parameters)

CORE = Path(__file__).resolve().parents[4] / "OspreyFlow_Core"

#: The deployment-wide list's rows, in the screening shape: keyed on `ref`, named in `primary_name`.
ROWS = [
    {"ref": code, "primary_name": name, "aliases": None, "date_of_birth": None, "nationality": None,
     "identifiers": None, "programme": None, "listing": None, "entity_type": "Organisation"}
    for code, name in (("FMR", "HMP Fenwick Moor"), ("HBK", "HMP Halbeck"), ("ODE", "HMP Oakdene"))
]  # fmt: skip


async def _deployment_list(lists: InMemoryListStore, *, subscriber: str) -> str:
    """The deployment-wide list, subscribed to by `subscriber` ("pid", the staged pipeline's own
    dataset, or another one, the shape of the real mistake: a subscription that is not this dataset's)."""
    made = await lists.add(
        DeploymentListInput(name="establishments", template="blank", location="establishments.csv",
                            mapping=BlankListMapping(ref="ref", primary_name="primary_name")),
        "admin-1",
    )  # fmt: skip
    ParquetListRows(STORAGE).write(deployment_reference(made, 1), ROWS)
    assert await lists.apply_version(made.id, previous=0, version=1, digest="d", entries=len(ROWS),
                                     at=made.created_at)  # fmt: skip
    await lists.subscribe(subscriber, made.id, "author-1")
    assert await lists.subscribed(subscriber) == [made.id]
    return made.id


def _reading_the_deployment_list(pipeline: PipelineGraph) -> PipelineGraph:
    """The Lookup adds the deployment list's `primary_name`, as the establishment, where the dataset's
    own list had `name`."""
    graph = pipeline.model_copy(deep=True)
    lookup = next(n for n in graph.nodes if n.id == "with_establishment")
    lookup.config["add"] = [{"column": "primary_name", "as": "establishment"}]
    return graph


async def published(
    tmp_path: Path, change: Callable[[PipelineGraph], PipelineGraph]
) -> tuple[StudioRecipeDraft, Path]:
    """The exit's staged recipe, published to a throwaway repository, its pipeline `change`d (as
    `test_staged_pipeline_run.py`'s own `_published`)."""
    from services.api.studio_publish import write_and_commit_recipe

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    bookings = tmp_path / "visit_bookings.csv"
    shutil.copy(FIXTURES / "visit_bookings.csv", bookings)
    pipeline = change(_pipeline(tmp_path))
    assert RECIPE.staging
    staging = [
        s.model_copy(update={"add": [AddedColumn(column="primary_name", as_="establishment")]})
        if s.id == "with_establishment" else s
        for s in RECIPE.staging
    ]  # fmt: skip
    recipe = RECIPE.model_copy(update={"id": "recipe-1", "pipeline": pipeline, "staging": staging})
    git_path = await write_and_commit_recipe(recipe, repo_root=repo)
    draft = StudioRecipeDraft(
        recipe_id="recipe-1", version=1, status=StudioRecipeStatus.PUBLISHED, label="Visits",
        connector_profile="generic-csv", source_location=str(bookings), handling=HANDLING,
        legal_basis="Synthetic demonstration data", owning_unit="unit-1", created_by="author-1",
        created_at=datetime(2026, 11, 8, tzinfo=UTC), ready_for_profile=True,
        row_template=RECIPE.row_template, pipeline=pipeline, git_path=git_path,
        dataset_id="pid", pack_versions={},
    )  # fmt: skip
    return draft, repo


@pytest.fixture
async def subscribed(staged: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    lists = InMemoryListStore()
    monkeypatch.setattr(app.state, "list_store", lists, raising=False)
    staged.list_id = await _deployment_list(lists, subscriber="pid")  # type: ignore[attr-defined]
    # The dataset's own model names no list: the only `establishments` it reads is the subscribed one.
    app.dependency_overrides[get_target_models] = lambda: _Models([])
    _update(staged, pipeline=_reading_the_deployment_list(_draft(staged).pipeline))
    staged.lists = lists  # type: ignore[attr-defined]
    return staged


def test_the_drawer_s_sample_reads_a_subscribed_list(subscribed: TestClient) -> None:
    response = _preview(subscribed, "with_establishment")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["problems"] == [], body["problems"]
    names = {row["establishment"] for row in body["rows"]}
    assert {"HMP Fenwick Moor", "HMP Halbeck"} <= names, names


def test_test_reads_a_subscribed_list(subscribed: TestClient) -> None:
    response = subscribed.post(f"{RECIPE_URL}/verify")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rows_read"] == 10
    # The subscribed list's rows were joined in, not merely not refused.
    cited = {s["document_id"] for n in body["nodes"] for s in n["provenance"]["sources"]}
    assert "reference_list:establishments@v1" in cited, cited
    titles = " ".join(str(n["properties"].get("title", "")) for n in body["nodes"])
    assert "HMP Fenwick Moor" in titles and "HMP Halbeck" in titles, titles


async def test_the_run_reads_a_subscribed_list(
    subscribed: TestClient, tmp_path: Path
) -> None:
    from services.api.pipeline_run import run_published_pipeline
    from tests.ingest.recipe_test_support import ValidatingGraph

    draft, repo = await published(tmp_path, _reading_the_deployment_list)
    graph = ValidatingGraph(ONTOLOGY)
    report = await run_published_pipeline(
        draft, LOADER, graph=graph, ontology=ONTOLOGY, scheme=SCHEME,  # type: ignore[arg-type]
        load_id="run-s", investigation_scope="case-1", repo_root=repo,
        recogniser_for=lambda *_: None,  # type: ignore[arg-type,return-value]
        target_models=_Models([]), staging_storage=STORAGE,  # type: ignore[arg-type]
        list_store=subscribed.lists,  # type: ignore[attr-defined]
    )  # fmt: skip
    [branch] = report.branches
    lookup = next(s for s in branch.report.staging_steps if s.step == "with_establishment")
    assert lookup.rows_in == 6 and lookup.unmatched == 1  # XXX, kept with no establishment
    assert graph.committed_nodes


#: Rule 4: the cases whose principal may not read `pid`. The second's own dataset subscribes to the
#: same deployment-wide list, so a check that asked "is this list subscribed by a dataset the principal
#: reads?" instead of "does the principal read the dataset this pipeline is?" would let it through.
OUTSIDERS = {
    "a case reading none of it": ["ledger"],
    "a case whose own dataset subscribes the list": ["other-dataset"],
}


@pytest.mark.parametrize("who", sorted(OUTSIDERS))
async def test_a_subscribed_list_is_withheld_from_a_case_not_reading_the_dataset_at_the_sample(
    subscribed: TestClient, who: str
) -> None:
    from services.api.app import get_principal
    from services.api.studio_staging import DATASET_WITHHELD, LISTS_WITHHELD
    from tests.services.api.test_studio_staging_routes import SOURCE_AUTHOR

    await subscribed.lists.subscribe("other-dataset", subscribed.list_id, "author-2")  # type: ignore[attr-defined]
    app.dependency_overrides[get_principal] = lambda: SOURCE_AUTHOR.model_copy(
        update={"datasets": OUTSIDERS[who]}
    )
    response = _preview(subscribed, "with_establishment")
    body = response.json()
    assert body["values_masked"] is True and body["rows"] == [] and body["counts"] == [], who
    # Withheld by either of the sample's two guards: the dataset's (every step) or the lists' (a
    # Lookup's); each backs the other, so the case asks that nothing is given, not which words.
    assert {DATASET_WITHHELD, LISTS_WITHHELD} & set(body["problems"]), body["problems"]
    assert "HMP" not in response.text, who


@pytest.mark.parametrize("who", sorted(OUTSIDERS))
async def test_a_subscribed_list_is_withheld_from_a_case_not_reading_the_dataset_at_test(
    subscribed: TestClient, who: str
) -> None:
    from services.api.app import get_principal
    from services.api.studio_staging import DATASET_WITHHELD
    from tests.services.api.test_studio_staging_routes import SOURCE_AUTHOR

    await subscribed.lists.subscribe("other-dataset", subscribed.list_id, "author-2")  # type: ignore[attr-defined]
    app.dependency_overrides[get_principal] = lambda: SOURCE_AUTHOR.model_copy(
        update={"datasets": OUTSIDERS[who]}
    )
    response = subscribed.post(f"{RECIPE_URL}/verify")
    assert response.status_code == 422, response.text
    assert response.json() == {"error": "recipe_rule", "problems": [DATASET_WITHHELD]}
    assert "HMP" not in response.text, who


REFUSED = (
    "step 'with_establishment' looks up 'establishments', which names no list this dataset "
    "holds or subscribes to"
)


@pytest.fixture
async def subscribed_elsewhere(staged: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """The list exists and is subscribed, but by another dataset, never by `pid`."""
    lists = InMemoryListStore()
    monkeypatch.setattr(app.state, "list_store", lists, raising=False)
    await _deployment_list(lists, subscriber="other-dataset")
    assert await lists.subscribed("pid") == []
    app.dependency_overrides[get_target_models] = lambda: _Models([])
    _update(staged, pipeline=_reading_the_deployment_list(_draft(staged).pipeline))
    staged.lists = lists  # type: ignore[attr-defined]
    return staged


def test_another_dataset_s_subscription_is_refused_at_the_sample(
    subscribed_elsewhere: TestClient,
) -> None:
    body = _preview(subscribed_elsewhere, "with_establishment").json()
    assert body["problems"] == [REFUSED]
    assert not body.get("rows")


def test_another_dataset_s_subscription_is_refused_at_test(subscribed_elsewhere: TestClient) -> None:
    response = subscribed_elsewhere.post(f"{RECIPE_URL}/verify")
    assert response.status_code == 422, response.text
    assert response.json() == {"error": "recipe_rule", "problems": [REFUSED]}


async def test_another_dataset_s_subscription_is_refused_at_the_run(
    subscribed_elsewhere: TestClient, tmp_path: Path
) -> None:
    from services.api.pipeline_run import run_published_pipeline
    from services.ingest.recipe_rules import RecipeRuleError
    from tests.ingest.recipe_test_support import ValidatingGraph

    draft, repo = await published(tmp_path, _reading_the_deployment_list)
    graph = ValidatingGraph(ONTOLOGY)
    with pytest.raises(RecipeRuleError) as refused:
        await run_published_pipeline(
            draft, LOADER, graph=graph, ontology=ONTOLOGY, scheme=SCHEME,  # type: ignore[arg-type]
            load_id="run-x", investigation_scope="case-1", repo_root=repo,
            recogniser_for=lambda *_: None,  # type: ignore[arg-type,return-value]
            target_models=_Models([]), staging_storage=STORAGE,  # type: ignore[arg-type]
            list_store=subscribed_elsewhere.lists,  # type: ignore[attr-defined]
        )  # fmt: skip
    assert refused.value.problems == [REFUSED]
    assert not graph.committed_nodes


#: Each entry into the staging engine that judges a Lookup, and so needs the dataset's subscriptions.
#: `run_staged_recipe` takes the same `subscribed=()` default as the others (the lane review of L1.8).
ENGINE = {
    "run_staging", "dry_run_staged_recipe", "prepare_staged_load", "lists_for_run", "run_staged_recipe",
}  # fmt: skip

#: The places a caller may live: the Conduit and ingest service, the command, the scripts and packages.
SCANNED_ROOTS = ("services", "cli", "scripts", "packages")

#: The engine's own modules, where the defaults live and where each entry hands its own
#: `subscribed` on to the next; their calls are the engine's, not a caller's.
ENGINE_MODULES = {"staging_catalogue.py", "staged_run.py", "reference_list_import.py"}

#: Function-handing helpers, and the position of the function they are handed.
HANDERS = {"to_thread": 0, "partial": 0, "run_in_executor": 1}


def _name(node: ast.AST) -> str | None:
    return node.id if isinstance(node, ast.Name) else getattr(node, "attr", None)


def _empty(value: ast.AST) -> bool:
    """`()`, `[]`, `set()`, `frozenset()`, `tuple()`, `list()` and `None`: a `subscribed=` that names the
    keyword and hands the engine nothing, the default under another spelling."""
    if isinstance(value, ast.Constant):
        return value.value is None or value.value in ((), "", b"")
    if isinstance(value, (ast.Tuple, ast.List, ast.Set)):
        return not value.elts
    if isinstance(value, ast.Dict):
        return not value.keys
    if isinstance(value, ast.Call) and _name(value.func) in {"tuple", "list", "set", "frozenset"}:
        return not value.args and not value.keywords
    return False


def _hands_subscriptions(call: ast.Call) -> bool:
    return any(k.arg == "subscribed" and not _empty(k.value) for k in call.keywords)


def _calls_without_subscriptions(path: Path, root: Path = CORE) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    # An engine entry imported under another name is still that entry.
    alias = {n: n for n in ENGINE}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name in ENGINE and a.asname:
                    alias[a.asname] = a.name
    where = path.relative_to(root)
    missing: list[str] = []
    accounted: set[int] = set()  # the ids of the references a checked call already covers
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _name(node.func)
        if name in alias:
            accounted.add(id(node.func))
            if not _hands_subscriptions(node):
                missing.append(f"{where}:{node.lineno} {alias[name]}")
        # `to_thread(f, ...)`, `partial(f, ...)`, `loop.run_in_executor(None, f, ...)`: f is handed on,
        # and the keywords given beside it are the ones it is called with (run_in_executor takes none,
        # so it can only hand the engine nothing).
        if name in HANDERS and len(node.args) > HANDERS[name]:
            handed = node.args[HANDERS[name]]
            if _name(handed) in alias:
                accounted.add(id(handed))
                if not _hands_subscriptions(node):
                    missing.append(f"{where}:{node.lineno} {alias[_name(handed)]} ({name})")
    # Any other reference to an entry (stored, returned, passed to something not listed) is a call
    # this check cannot follow, so it is named rather than let through.
    for node in ast.walk(tree):
        if isinstance(node, (ast.Name, ast.Attribute)) and isinstance(node.ctx, ast.Load):
            if _name(node) in alias and id(node) not in accounted:
                missing.append(f"{where}:{node.lineno} {alias[_name(node)]} (handed on unchecked)")
    return missing


def _callers() -> list[Path]:
    return [
        p
        for top in SCANNED_ROOTS
        if (CORE / top).is_dir()
        for p in sorted((CORE / top).rglob("*.py"))
        if p.name not in ENGINE_MODULES and ".venv" not in p.parts and "node_modules" not in p.parts
    ]


def test_every_caller_hands_the_staging_engine_the_subscriptions() -> None:
    """Every call in the Conduit, the ingest service, the command, the scripts and the packages names
    a `subscribed=` that is not empty. The engine's own modules are the ones not asked."""
    scanned = _callers()
    # Non-vacuous: the three modules the reviewer named are among those read (a wrong root read none).
    assert {"studio_staging.py", "studio_verify.py", "pipeline_run.py"} <= {p.name for p in scanned}
    missing = [m for path in scanned for m in _calls_without_subscriptions(path)]
    assert missing == [], missing


#: Rule 15: each plant the shape a real caller takes, and each one red against the check alone.
PLANTS = {
    "forgotten": "def a(s):\n    return run_staging(s, sources={}, lists={}, dataset_id='d')\n",
    "awaited": "async def b(s):\n    return await dry_run_staged_recipe(s, sources={}, lists={})\n",
    "to_thread": (
        "import asyncio\n"
        "async def c(s):\n    return await asyncio.to_thread(lists_for_run, s, [], dataset_id='d')\n"
    ),
    "empty tuple": "def d(s):\n    return run_staging(s, sources={}, lists={}, subscribed=())\n",
    "empty list": "async def e(s):\n    return await prepare_staged_load(s, lists={}, subscribed=[])\n",
    "None": "def f(s):\n    return run_staging(s, sources={}, lists={}, subscribed=None)\n",
    "tuple()": "def g(s):\n    return run_staging(s, sources={}, lists={}, subscribed=tuple())\n",
    "aliased": (
        "from services.ingest.staging_catalogue import run_staging as stage\n"
        "def h(s):\n    return stage(s, sources={}, lists={})\n"
    ),
    "partial": (
        "import functools\n"
        "def i(s):\n    return functools.partial(run_staging, s, sources={}, lists={})()\n"
    ),
    "run_in_executor": (
        "async def j(loop, s):\n    return await loop.run_in_executor(None, run_staged_recipe, s)\n"
    ),
    "bare reference": "def k():\n    step = prepare_staged_load\n    return step\n",
    "attribute": (
        "from services.ingest import staged_run\n"
        "async def m(s):\n    return await staged_run.run_staged_recipe(s, sources={})\n"
    ),
}


@pytest.mark.parametrize("shape", sorted(PLANTS))
def test_the_caller_check_finds_a_call_that_forgets_them(tmp_path: Path, shape: str) -> None:
    planted = tmp_path / "plant.py"
    planted.write_text(PLANTS[shape], encoding="utf-8")
    assert len(_calls_without_subscriptions(planted, tmp_path)) == 1, shape


def test_the_caller_check_passes_the_real_callers_shape(tmp_path: Path) -> None:
    """The green half: a call handing real subscriptions, directly and through `to_thread`, is not
    named, so the plants above are red for what they plant and not for being calls at all."""
    planted = tmp_path / "plant.py"
    planted.write_text(
        "import asyncio\n"
        "async def a(s, refs):\n"
        "    run_staging(s, sources={}, lists={}, subscribed=subscribed_in(refs))\n"
        "    return await asyncio.to_thread(lists_for_run, s, refs, subscribed=subscribed_in(refs))\n",
        encoding="utf-8",
    )
    assert _calls_without_subscriptions(planted, tmp_path) == []



STAND_IN = "services.ingest.reference_list_import"


def _stand_in_uses(path: Path) -> list[int]:
    """The lines referring to the stand-in's `import_list`, resolved by module: `list_connector` has
    an `import_list` of its own (a deployment-wide list's import), which is not the stand-in."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()  # what the stand-in's function is called here
    modules: set[str] = set()  # what the stand-in's module is called here
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == STAND_IN:
            for a in node.names:
                if a.name == "import_list":
                    names.add(a.asname or a.name)
                    lines.append(node.lineno)
        elif isinstance(node, ast.ImportFrom) and node.module == STAND_IN.rsplit(".", 1)[0]:
            modules |= {a.asname or a.name for a in node.names if a.name == "reference_list_import"}
        elif isinstance(node, ast.Import):
            modules |= {a.asname or a.name for a in node.names if a.name == STAND_IN}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id in names:
            lines.append(node.lineno)
        elif isinstance(node, ast.Attribute) and node.attr == "import_list":
            if ast.unparse(node.value) in modules:
                lines.append(node.lineno)
    return sorted(lines)


def test_nothing_but_tests_seeds_a_list() -> None:
    """L1.4's stand-in import is retired (CARRIES, studio-b): `import_list` stays only as the
    tests' seed of a synthetic list, so no module a deployment runs refers to it."""
    named = {
        f"{p.relative_to(CORE)}:{line}"
        for top in SCANNED_ROOTS
        if (CORE / top).is_dir()
        for p in sorted((CORE / top).rglob("*.py"))
        if p.name != "reference_list_import.py" and ".venv" not in p.parts
        for line in _stand_in_uses(p)
    }
    assert named == set(), named


SEED_PLANTS = {
    "imported": (
        "from services.ingest.reference_list_import import import_list\n"
        "def seed(p, s):\n    return import_list('pid', 'establishments', p, storage=s)\n"
    ),
    "aliased": (
        "from services.ingest.reference_list_import import import_list as seed_it\n"
        "def seed(p, s):\n    return seed_it('pid', 'establishments', p, storage=s)\n"
    ),
    "by module": (
        "from services.ingest import reference_list_import as rli\n"
        "def seed(p, s):\n    return rli.import_list('pid', 'establishments', p, storage=s)\n"
    ),
}


@pytest.mark.parametrize("shape", sorted(SEED_PLANTS))
def test_the_seed_check_finds_a_caller(tmp_path: Path, shape: str) -> None:
    """Rule 15, at a real caller's shapes: a module importing and calling the stand-in is named."""
    planted = tmp_path / "plant.py"
    planted.write_text(SEED_PLANTS[shape], encoding="utf-8")
    assert _stand_in_uses(planted), shape


def test_the_seed_check_lets_the_list_connector_s_own_import_through(tmp_path: Path) -> None:
    """The green half: the Conduit's `list_connector.import_list` (a deployment-wide list's import,
    as `app.py` calls it) is another function and is not named."""
    planted = tmp_path / "plant.py"
    planted.write_text(
        "from services.api.list_connector import import_list\n"
        "async def refresh(i, l, r):\n    return await import_list(i, store=l, rows_kept=r)\n",
        encoding="utf-8",
    )
    assert _stand_in_uses(planted) == []
