"""The Prison Intelligence seed, its rehearsal reset and its two mid-demo commands
(`scripts/seed_pid.py`, ADR-127 Amendment 23, as corrected by Amendments 25 to 27 and 30 to 32).

Pure: every store, the graph and the run are replaced by fakes, and files are written to a temporary
folder. What the stores do with the seed's calls is proved live
(`tests/ingest/test_pid_seed_live.py`, slow, outside `make ci`: three cases, Amendment 32). What a
mistake would do, and the case that catches it:

**The order and the files**
- the seed keeping a list of its own, so it drifts from the replay every golden test derives its
  markings from (`test_the_seed_loads_in_the_one_constant_the_replay_uses`,
  `test_the_seed_names_no_source_file_or_recipe_of_its_own`);
- `manifest.json` or the pictures landing in the folder the Studio lists, or batch 2 in the listing
  before chapter 9 (`test_the_listed_folder_holds_the_seeds_files_and_nothing_else`);
- a second seed changing a byte (`test_a_second_write_is_byte_for_byte_the_first`);
- a half-written file offered in the picker (`test_a_file_is_placed_whole_or_not_at_all`).

**Who loads** (Amendment 31)
- a loader that is not the demo data engineer (OFFICIAL, the engineer's rights, no `EDIT_GRAPH`), or
  one still cleared to SECRET (`test_the_loader_is_the_demo_data_engineer_and_not_secret_cleared`);
- the edit right given to the loads, or not given to the pictures
  (`test_the_edit_right_is_granted_to_the_pictures_step_and_to_nothing_else`);
- a write made before the loader is scoped to the case, so nodes land outside the dataset
  (`test_nothing_is_written_before_the_worker_is_scoped_to_the_case`).

**The recipes** (Amendment 30)
- a recipe re-serialised instead of copied, committed before its checks, committed before the row it
  would meet is compared, or entered with a source outside the dataset's folder
  (`test_each_recipe_but_the_reports_is_checked_compared_copied_then_entered`);
- a committed file that differs from the row it is published against
  (`test_a_row_that_differs_is_refused_by_name_before_anything_is_committed`);
- R9 entered as published, or its starting pipeline wrong
  (`test_the_reports_recipe_is_entered_as_the_draft_and_never_as_published`,
  `test_the_starting_pipeline_is_the_domain_model_and_one_source_at_the_reports_file`);
- the repository the recipes are committed to not being the one the runs read, found only after the
  files and the case were written
  (`test_a_repository_that_the_runs_do_not_read_stops_the_seed_before_any_write`).

**The runs**
- a file run again when its load stands, or not run again when its load was reverted
  (`test_a_file_with_an_unreverted_load_is_not_run_again`,
  `test_a_reverted_load_is_run_again`, `test_the_question_asked_of_the_ledger_is_the_cases_own`);
- R17 run before R9, which would make 589 empty report Documents
  (`test_r17_is_refused_without_an_unreverted_r9_in_the_case`,
  `test_r17_is_allowed_once_r9_stands_and_never_asked_about_for_another_recipe`);
- the measurements of R5 absent, or invented when it was not run
  (`test_r5s_time_and_peak_memory_are_said_when_it_ran_and_not_invented_when_it_did_not`);
- a reseed that hides a short, held or missing standing load
  (`test_a_standing_loads_rows_are_reported_and_a_short_one_fails_the_checks`);
- the seed's loads enqueueing post-ingest resolution that would write `SAME_AS` onto the reports
  recipe's people (`test_the_seeds_runs_enqueue_no_post_ingest_resolution`).

**The pictures**
- a picture attached to a subject that has any history (Amendment 27), a subject not found passing
  for done, or a refusal swallowed (`test_a_subject_with_a_picture_history_is_not_touched`,
  `test_a_subject_not_found_is_counted_and_fails_the_seed`,
  `test_a_refusal_is_reported_by_subject_and_fails_the_seed`);
- a subject found by an identifier other than the plan's
  (`test_every_picture_subject_is_found_by_the_property_the_replay_names`);
- a picture subject the seed cannot mark faithfully
  (`test_no_picture_subject_carries_an_action_or_sanitisation_code`).

**The demo numbers** (Amendment 32; Brief 2 section 8, Brief 1 section 5.8, each check against a
fake that holds the plan as the store would, passing, then failing for the mistake it names)
- J1, J2, Ch2, Ch3, Ch5, Ch6, Ch11's gaps and the S2 handling row
  (`test_each_demo_number_holds_over_the_plan_as_stored`,
  `test_each_demo_number_fails_for_its_own_mistake`);
- a check that cannot read the store passing (`test_a_check_that_cannot_run_is_a_failed_check`);
- the moment a case is at read wrongly
  (`test_the_moment_a_case_is_at_is_read_from_its_standing_loads`);
- a failed check not failing the seed
  (`test_a_failed_demo_number_fails_the_seed_line_and_the_exit`).

**The reset** (Amendment 32)
- the choice: every unreverted R9 and R17 load, only batch 2's R6 loads, newest first
  (`test_the_reset_chooses_every_r9_and_r17_load_and_only_batch_twos_r6_loads_newest_first`);
- a refusal that does not stop it, or does not say to reseed with the full command
  (`test_a_revert_refused_stops_names_it_and_says_to_reseed`);
- ids and link types printed without `--show-ids`
  (`test_a_refusal_prints_counts_and_link_types_only_with_show_ids`);
- the end state (`test_a_reset_reverts_newest_first_then_restores_the_draft_and_the_files`);
- a new R9 version written when nothing was reverted and R9 is already at its starting draft
  (`test_a_reset_that_reverted_nothing_leaves_a_starting_draft_alone`,
  `test_a_draft_is_at_its_start_only_if_it_is_a_draft_with_no_mapping_and_the_starting_pipeline`);
- a file the seed did not write left in the listed folder, or removed without being named
  (`test_the_reset_removes_batch_two_and_every_other_file_naming_each`);
- what the reset cannot undo, unsaid (`test_the_reset_says_what_it_cannot_undo`).

**The mid-demo commands**
- `--release-batch-2` opening a store, or leaving the file in two places wrongly
  (`test_release_batch_2_copies_it_into_the_listed_folder_and_opens_no_store`);
- the fallback publishing at a version other than the draft's, leaving the row's Connect fields as
  the engineer edited them, skipping the unrunnable-pipeline gate, committing without the pipeline,
  or writing no audit entry (`test_the_fallback_publishes_the_file_as_a_route_would`,
  `test_the_fallback_refuses_a_pipeline_the_runner_cannot_run_before_anything_is_written`,
  `test_the_fallback_refuses_when_the_row_does_not_agree_with_the_file_after_its_writes`);
- importing the module connecting to anything (`test_importing_the_seed_opens_nothing`).

**The wiring** (`_seed_into` over fakes: the order of the steps, who holds which right, what is
printed, what the exit is)
- a step run out of order, a picture attached without the edit right, a check not printed, or a
  failed number or a reseed's failed standing load exiting 0
  (`test_the_seed_runs_end_to_end_over_fakes_and_prints_its_checks`,
  `test_a_failed_demo_number_makes_the_seed_exit_non_zero`,
  `test_a_reseed_reports_each_standing_load_and_runs_nothing_again`).

**Refusals and ambiguity** (Amendment 30)
- a refusal that ends as a traceback, or exits 0
  (`test_every_refusal_is_printed_by_name_with_a_non_zero_exit`);
- two cases of one name, one of them silently chosen (`test_two_cases_of_one_name_are_refused`)."""

from __future__ import annotations

import ast
import dataclasses
import re
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from scripts import seed_pid
from services.api.recipe_run import RecipeRunDeps
from services.api.resolution_trigger import submit_post_ingest_resolution_jobs
from services.api.studio_publish import build_recipe, pack_versions_for, serialise_recipe
from services.api.studio_recipes import (
    SeededRecipeContentDiffers,
    carry_source_declarations,
    check_seeded_recipe,
)
from services.ingest.load_revert import Refusal as RevertRefusal
from services.ingest.load_revert import RevertIncomplete, RevertRefused, RevertResult

from demo_fixtures import pid_files, pid_plan, pid_writes
from demo_fixtures.datasets import PID
from ontology.handling import load_uk_le_scheme
from ontology.packs import load_deployment_ontology
from schemas.domain import (
    AuditStub,
    Edge,
    ExpandRequest,
    Node,
    PatternQuery,
    Principal,
    Provenance,
    ProvenanceState,
    SourceRef,
    Subgraph,
)
from schemas.ingest import (
    LoadRecord,
    LoadReport,
    PipelineNode,
    PipelineNodeKind,
    Recipe,
    StudioRecipeDraft,
    StudioRecipeStatus,
)
from schemas.rights import DATA_ENGINEER, Right, rights_for

FIXTURES = Path(seed_pid.__file__).resolve().parents[1] / "packages" / "demo_fixtures"
ONTOLOGY = load_deployment_ontology()
SCHEME = load_uk_le_scheme()
NOW = datetime(2026, 10, 26, 9, tzinfo=UTC)
PLAN = pid_plan.build_plan("demo")
CASE = "case-pid"


SWITCH = "OSPREY_POST_INGEST_RESOLUTION"


@pytest.fixture(autouse=True)
def _the_demo_deployment_has_resolution_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """The deployment the pack requires (Amendments 33 and 34). The cases about the switch being on
    set it themselves."""
    monkeypatch.setenv(SWITCH, "off")


@cache
def _persona() -> Principal:
    """The loader as the seed scopes it to the case: the demo data engineer, OFFICIAL."""
    return seed_pid.engineer("verify").model_copy(update={"datasets": [PID.id]})


def _record(load_id: str, recipe: str, source: str, version: int = 1) -> LoadRecord:
    return LoadRecord(
        load_id=load_id, recipe_id=recipe, recipe_version=version, source=source, started_at=NOW,
        created_by=seed_pid.ENGINEER_USERNAME, investigation_id=CASE,
    )  # fmt: skip


def _root(tmp_path: Path) -> Path:
    return tmp_path / "ingest"


def _source(root: Path, file: str) -> str:
    return str(root / "uploaded" / "prison-intelligence" / file)


# --- the order, and no list of its own -----------------------------------------------------------


def test_the_seed_loads_in_the_one_constant_the_replay_uses() -> None:
    from tests.ingest import pid_golden_support

    assert seed_pid.SEED_ORDER is pid_files.SEED_ORDER
    assert pid_golden_support.pid_files.SEED_ORDER is seed_pid.SEED_ORDER
    assert [s.file for s in seed_pid.stages_to_run()] == [
        s.file for s in pid_files.seed_stages("seed")
    ]
    assert [s.moment for s in seed_pid.stages_to_run()] == ["seed"] * 15
    assert [s.recipe for s in seed_pid.stages_to_run()][:2] == [
        "pid_establishment_plan_recipe.yaml",
        "pid_nomis_prisoners_recipe.yaml",
    ]


def _names_a_file_or_recipe(tree: ast.AST) -> list[str]:
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and re.search(r"pid_[a-z0-9_]+\.(csv|yaml)|pid_[a-z_]+_recipe", node.value)
    ]


def test_the_seed_names_no_source_file_or_recipe_of_its_own() -> None:
    """A copy of the order, or of a file name, is a second definition that drifts. Every file and
    recipe the seed uses comes from `pid_files`."""
    tree = ast.parse(Path(seed_pid.__file__).read_text(encoding="utf-8"))
    assert _names_a_file_or_recipe(tree) == []


def test_the_check_for_a_name_of_its_own_finds_one() -> None:
    """The scan above fails for a planted literal (rule 15)."""
    tree = ast.parse('FILE = "pid_pin_calls.csv"\nORDER = ["pid_pin_calls_recipe.yaml"]\n')
    assert _names_a_file_or_recipe(tree) == ["pid_pin_calls.csv", "pid_pin_calls_recipe.yaml"]


# --- the files ------------------------------------------------------------------------------------


def _fake_writer(plan: Any, out_dir: Path, *, text: str = "a,b\n1,2\n") -> pid_files.WriteReport:
    """What `pid_files.write_files` leaves: the CSV files, `incoming/` for batch 2, `pictures/` and
    `manifest.json`, small."""
    names = [s.file for s in pid_files.SEED_ORDER]
    names = [f"incoming/{n}" if n == pid_files.BATCH_2 else n for n in dict.fromkeys(names)]
    records = []
    for name in names:
        path = out_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{text}{name}\n", encoding="utf-8")
        records.append(pid_files.FileRecord(name, 1, path.stat().st_size, "x"))
    (out_dir / "pictures").mkdir()
    (out_dir / "pictures" / "a.png").write_bytes(b"png")
    (out_dir / pid_files.MANIFEST).write_text("{}", encoding="utf-8")
    return pid_files.WriteReport("demo", 1, tuple(records), (), {}, "{}")


def _listed(root: Path) -> Path:
    return root / "uploaded" / "prison-intelligence"


def test_the_listed_folder_holds_the_seeds_files_and_nothing_else(tmp_path: Path) -> None:
    root = _root(tmp_path)
    written = seed_pid.write_listed_files(PLAN, root, write=_fake_writer)
    listed = _listed(root)
    direct = sorted(p.name for p in listed.iterdir() if p.is_file())
    expected = sorted({s.file for s in pid_files.SEED_ORDER} - {pid_files.BATCH_2})
    assert direct == expected, "every seed file, no manifest, no batch 2, no part file"
    assert not (listed / pid_files.MANIFEST).exists()
    assert not (listed / "pictures").exists()
    assert (listed / "incoming" / pid_files.BATCH_2).is_file(), "batch 2 waits under incoming/"
    assert sorted(written) == sorted([*expected, f"incoming/{pid_files.BATCH_2}"])
    assert not list(root.rglob("*.part")) and not list(root.rglob(".*"))


def test_a_second_write_is_byte_for_byte_the_first(tmp_path: Path) -> None:
    root = _root(tmp_path)
    seed_pid.write_listed_files(PLAN, root, write=_fake_writer)
    first = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    seed_pid.write_listed_files(PLAN, root, write=_fake_writer)
    second = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert first == second and first


def test_a_file_is_placed_whole_or_not_at_all(tmp_path: Path) -> None:
    """The bytes go to a hidden part file and are renamed into place, as an upload's are, so the
    picker never offers half a file."""
    source = tmp_path / "src.csv"
    source.write_bytes(b"whole")
    destination = tmp_path / "dest" / "x.csv"
    seen: list[list[str]] = []
    real = seed_pid._replace

    def spy(part: Path, final: Path) -> None:
        seen.append(sorted(p.name for p in final.parent.iterdir()))
        real(part, final)

    seed_pid._place(source, destination, replace=spy)
    assert destination.read_bytes() == b"whole"
    assert len(seen) == 1 and seen[0] and seen[0][0].startswith(".") and "x.csv" not in seen[0]
    assert sorted(p.name for p in destination.parent.iterdir()) == ["x.csv"]


def test_the_seed_writes_into_the_dataset_folder_under_the_ingest_roots_uploaded(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    assert seed_pid.listed_folder(root) == root / "uploaded" / "prison-intelligence"
    assert seed_pid.incoming_folder(root) == root / "uploaded" / "prison-intelligence" / "incoming"
    assert seed_pid.source_of(root, "pid_pin_calls.csv") == _source(root, "pid_pin_calls.csv")
    assert seed_pid.FOLDER == PID.id


# --- who loads (Amendment 31) ---------------------------------------------------------------------


def test_the_loader_is_the_demo_data_engineer_and_not_secret_cleared() -> None:
    from harness.realm import DEMO_ENGINEER_SUBJECT

    loader = seed_pid.engineer("verify")
    assert seed_pid.ENGINEER_USERNAME == DEMO_ENGINEER_SUBJECT == "osprey-demo-engineer"
    assert loader.id == DEMO_ENGINEER_SUBJECT, "with no --run-as, the username"
    assert loader.org_unit == "verify"
    signed_in = seed_pid.engineer("verify", "kc-sub-1234")
    assert signed_in.id == "kc-sub-1234" and signed_in.roles == loader.roles, (
        "the id he signs in as"
    )
    assert loader.clearance == "OFFICIAL", "Amendment 31 withdrew the SECRET-cleared worker"
    held = rights_for(loader.roles)
    assert DATA_ENGINEER <= held, "the data engineer's rights"
    assert Right.EDIT_GRAPH not in held, "the role holds no EDIT_GRAPH (Amendment 31)"
    assert loader.datasets is None, "unscoped until the seed scopes it to the case"
    assert not hasattr(seed_pid, "worker"), "the SECRET-cleared worker is gone"
    assert "pid-seed-worker" not in Path(seed_pid.__file__).read_text(encoding="utf-8")


def test_the_edit_right_is_granted_to_the_pictures_step_and_to_nothing_else() -> None:
    loader = seed_pid.engineer("verify")
    picturer = seed_pid.with_edit_graph(loader)
    assert Right.EDIT_GRAPH in rights_for(picturer.roles)
    assert DATA_ENGINEER <= rights_for(picturer.roles)
    assert (picturer.id, picturer.clearance, picturer.org_unit) == (
        loader.id, loader.clearance, loader.org_unit,
    )  # fmt: skip
    assert Right.EDIT_GRAPH not in rights_for(loader.roles), "the grant is a copy, not a mutation"


async def test_nothing_is_written_before_the_worker_is_scoped_to_the_case() -> None:
    log: list[tuple[str, Any]] = []

    async def scope(principal: Any) -> Any:
        log.append(("scope", principal.datasets))
        return principal.model_copy(update={"datasets": ["prison-intelligence"]})

    async def step(name: str, principal: Any) -> None:
        log.append((name, principal.datasets))
        log.append((name + "-edit", Right.EDIT_GRAPH in rights_for(principal.roles)))

    await seed_pid.seed_all(
        seed_pid.engineer("verify"),
        scope=scope,
        enter_recipes=lambda p: step("recipes", p),
        run=lambda p: step("runs", p),  # type: ignore[arg-type, return-value]
        pictures=lambda p: step("pictures", p),
        checks=lambda p: step("checks", p),
    )
    order = [name for name, _ in log if not name.endswith("-edit")]
    assert order == ["scope", "recipes", "runs", "pictures", "checks"]
    assert log[0][1] is None
    assert all(d == ["prison-intelligence"] for n, d in log[1:] if not n.endswith("-edit"))
    edit = {n.removesuffix("-edit"): v for n, v in log if n.endswith("-edit")}
    assert edit == {"recipes": False, "runs": False, "pictures": True, "checks": False}


async def test_a_scope_that_returns_an_unscoped_worker_stops_the_seed_before_a_write() -> None:
    log: list[str] = []

    async def scope(principal: Any) -> Any:
        return principal  # datasets still None

    async def step(principal: Any) -> None:
        log.append("wrote")

    with pytest.raises(RuntimeError, match="scoped"):
        await seed_pid.seed_all(
            seed_pid.engineer("verify"),
            scope=scope,
            enter_recipes=step,
            run=step,
            pictures=step,
            checks=step,
        )
    assert log == []


# --- the recipes ----------------------------------------------------------------------------------


@dataclass
class _Calls:
    log: list[tuple[str, Any]] = field(default_factory=list)


async def _enter(root: Path, calls: _Calls, **overrides: Any) -> dict[str, Any]:
    async def commit(recipe_id: str, data: bytes, *, version: int, repo_root: Path) -> str:
        calls.log.append(("commit", (recipe_id, data, version, repo_root)))
        return f"recipes/{recipe_id}.yaml"

    async def compare(recipe: Recipe, **kw: Any) -> None:
        calls.log.append(("compare", (recipe.id, kw)))

    async def enter(recipe: Recipe, **kw: Any) -> Any:
        calls.log.append(("enter", (recipe.id, kw)))
        return SimpleNamespace(recipe_id=recipe.id, version=recipe.version, **kw)

    async def enter_draft(recipe: Recipe, **kw: Any) -> Any:
        calls.log.append(("draft", (recipe.id, kw)))
        return SimpleNamespace(recipe_id=recipe.id, version=recipe.version, status="draft")

    def check(recipe: Recipe, ontology: Any, scheme: Any) -> None:
        calls.log.append(("check", recipe.id))
        check_seeded_recipe(recipe, ontology, scheme)

    args: dict[str, Any] = {
        "repo_root": root / "repo", "ontology": ONTOLOGY, "scheme": SCHEME, "commit": commit,
        "compare": compare, "enter": enter, "enter_draft": enter_draft, "check": check, "now": NOW,
        "worker_unit": "verify", "published_by": seed_pid.ENGINEER_USERNAME,
    }  # fmt: skip
    args.update(overrides)
    return await seed_pid.enter_recipes(root, **args)


async def test_each_recipe_but_the_reports_is_checked_compared_copied_then_entered(
    tmp_path: Path,
) -> None:
    root, calls = _root(tmp_path), _Calls()
    rows = await _enter(root, calls)
    entered = [c for c in calls.log if c[0] == "enter"]
    on_disk = sorted(p.name for p in FIXTURES.glob("pid_*_recipe.yaml"))
    assert len(on_disk) == 17 and len(entered) == 16
    assert len(rows) == 17, "the reports recipe is in the answer too, as the draft"
    for _, (recipe_id, kw) in entered:
        recipe_file = next(
            s.recipe for s in pid_files.SEED_ORDER if seed_pid.recipe_id_of(s.recipe) == recipe_id
        )
        committed = [d for n, d in calls.log if n == "commit" and d[0] == recipe_id]
        assert len(committed) == 1
        assert committed[0][1] == (FIXTURES / recipe_file).read_bytes(), "byte for byte"
        assert committed[0][3] == root / "repo"
        # the order: its checks, the comparison with the row it would meet, its commit, its row
        names = [n for n, d in calls.log if (d if isinstance(d, str) else d[0]) == recipe_id]
        assert names == ["check", "compare", "commit", "enter"], (recipe_id, names)
        first_stage = next(s for s in pid_files.SEED_ORDER if s.recipe == recipe_file)
        assert kw["source_location"] == _source(root, first_stage.file)
        assert kw["git_path"] == f"recipes/{recipe_id}.yaml"
        assert kw["dataset_id"] == "prison-intelligence" and kw["owning_unit"] == "verify"
        assert kw["published_by"] == seed_pid.ENGINEER_USERNAME and kw["now"] == NOW
        assert kw["ontology"] is ONTOLOGY and kw["scheme"] is SCHEME
        (compared,) = [d for n, d in calls.log if n == "compare" and d[0] == recipe_id]
        # the comparison is made about the very row `enter` writes
        assert compared[1] == {
            "source_location": kw["source_location"], "git_path": kw["git_path"],
            "dataset_id": kw["dataset_id"], "owning_unit": kw["owning_unit"],
        }  # fmt: skip


async def test_a_row_that_differs_is_refused_by_name_before_anything_is_committed(
    tmp_path: Path,
) -> None:
    """The row in the registry differs from what the seed would enter: the refusal comes from the
    comparison (the store's own, as `enter_published_for_seed` makes it), so nothing is committed to
    the recipe repository and no row is entered, for that recipe or any after it."""
    root, calls = _root(tmp_path), _Calls()

    async def refusing(recipe: Recipe, **kw: Any) -> None:
        if recipe.id == "pid-pin-calls":
            raise SeededRecipeContentDiffers(
                f"recipe {recipe.id!r} v{recipe.version} is already in the registry and differs "
                "in content"
            )

    with pytest.raises(SeededRecipeContentDiffers, match="pid-pin-calls"):
        await _enter(root, calls, compare=refusing)
    touched = [d[0] for n, d in calls.log if n in ("commit", "enter")]
    assert "pid-pin-calls" not in touched, "a committed file must never differ from its row"
    order = [d[0] for n, d in calls.log if n == "commit"]
    assert order and order == [r for r in order if r != "pid-pin-calls"], "nothing after it either"
    assert len([1 for n, _ in calls.log if n == "commit"]) < 16


async def test_a_recipe_the_checks_refuse_is_not_committed_or_entered(tmp_path: Path) -> None:
    root, calls = _root(tmp_path), _Calls()

    def refusing(recipe: Recipe, ontology: Any, scheme: Any) -> None:
        if recipe.id == "pid-pin-calls":
            raise ValueError("refused by the rules")
        check_seeded_recipe(recipe, ontology, scheme)

    with pytest.raises(ValueError, match="refused by the rules"):
        await _enter(root, calls, check=refusing)
    touched = [d[0] for n, d in calls.log if n in ("commit", "enter", "compare")]
    assert "pid-pin-calls" not in touched


async def test_the_reports_recipe_is_entered_as_the_draft_and_never_as_published(
    tmp_path: Path,
) -> None:
    root, calls = _root(tmp_path), _Calls()
    await _enter(root, calls)
    for name in ("enter", "commit", "compare"):
        assert [d[0] for n, d in calls.log if n == name].count("pid-intel-reports") == 0, name
    ((_, (recipe_id, kw)),) = [c for c in calls.log if c[0] == "draft"]
    assert recipe_id == "pid-intel-reports"
    assert kw["source_location"] == _source(root, pid_files.REPORTS)
    assert kw["dataset_id"] == "prison-intelligence" and kw["owning_unit"] == "verify"
    assert kw["created_by"] == seed_pid.ENGINEER_USERNAME
    assert kw["pipeline"] == seed_pid.starting_pipeline(_source(root, pid_files.REPORTS))


def test_the_starting_pipeline_is_the_domain_model_and_one_source_at_the_reports_file() -> None:
    location = "/ingest/uploaded/prison-intelligence/" + pid_files.REPORTS
    pipeline = seed_pid.starting_pipeline(location)
    kinds = [n.kind for n in pipeline.nodes]
    assert kinds == [PipelineNodeKind.DOMAIN_MODEL, PipelineNodeKind.SOURCE]
    domain, source = pipeline.nodes
    assert domain.config == {"pack": "niem"}
    assert source.config == {"connector_profile": "generic-csv", "source_location": location}
    assert [(e.source, e.target) for e in pipeline.edges] == [(domain.id, source.id)]


def test_the_recipe_id_comes_from_the_committed_file() -> None:
    assert seed_pid.recipe_id_of("pid_intel_reports_recipe.yaml") == "pid-intel-reports"
    assert seed_pid.recipe_id_of("pid_report_incidents_recipe.yaml") == "pid-report-incidents"
    assert seed_pid.recipe_id_of("pid_seized_comms_recipe.yaml") == "pid-seized-comms"


def test_the_recipe_repository_is_named_by_the_environment_and_not_the_checkout() -> None:
    """Unset, `studio_publish` falls back to the product folder itself, and a seed that committed
    the recipes there would `git init` inside the checkout: the seed refuses instead."""
    with pytest.raises(seed_pid.SeedRefusal, match="OSPREY_RECIPE_REPO_ROOT"):
        seed_pid.recipe_repo_root({})
    with pytest.raises(seed_pid.SeedRefusal, match="OSPREY_RECIPE_REPO_ROOT"):
        seed_pid.recipe_repo_root({"OSPREY_RECIPE_REPO_ROOT": ""})
    assert seed_pid.recipe_repo_root({"OSPREY_RECIPE_REPO_ROOT": "/data/recipes"}) == Path(
        "/data/recipes"
    )


def test_a_repository_that_is_not_the_one_the_run_reads_is_refused(tmp_path: Path) -> None:
    """The engine reads the published file from `RunResources.recipe_repo_root`; committing the
    copy anywhere else would leave every run unable to find it."""
    seed_pid.agree_on_repository(tmp_path, tmp_path)
    with pytest.raises(seed_pid.SeedRefusal, match="not the repository"):
        seed_pid.agree_on_repository(tmp_path / "a", tmp_path / "b")


def _seed_args(*extra: str) -> Any:
    return seed_pid.parse_args(["--case-name", "X", "--grant", "a=author", *extra])


async def test_a_repository_that_the_runs_do_not_read_stops_the_seed_before_any_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Amendment 30: checked before the case is made and before a file is written, not after."""
    wrote: list[str] = []

    class Resources:
        recipe_repo_root = tmp_path / "the-repository-the-runs-read"

        async def close(self) -> None:
            wrote.append("closed")

    async def build(config: Any) -> Any:
        return Resources()

    async def never_scope(*a: Any, **k: Any) -> str:
        wrote.append("case")
        return "c"

    def never_write(*a: Any, **k: Any) -> Any:
        wrote.append("files")
        return {}

    monkeypatch.setenv("OSPREY_RECIPE_REPO_ROOT", str(tmp_path / "another"))
    monkeypatch.setattr(seed_pid, "ApiConfig", SimpleNamespace(
        from_env=lambda: SimpleNamespace(postgres=SimpleNamespace(dsn="postgresql://unused")),
    ))  # fmt: skip

    async def no_case_yet(*a: Any, **k: Any) -> None:
        return None

    async def connect(dsn: str) -> Any:
        async def close() -> None: ...

        return SimpleNamespace(close=close)

    monkeypatch.setattr(seed_pid, "build_run_resources", build)
    monkeypatch.setattr(seed_pid, "_find_case", no_case_yet)
    monkeypatch.setattr(seed_pid, "StudioRecipeStore", SimpleNamespace(connect=connect))
    monkeypatch.setattr(seed_pid, "scope_for", never_scope)
    monkeypatch.setattr(seed_pid, "write_listed_files", never_write)
    with pytest.raises(seed_pid.SeedRefusal, match="not the repository"):
        await seed_pid._seed(_seed_args(), _root(tmp_path))
    assert "case" not in wrote and "files" not in wrote, wrote


# --- the runs -------------------------------------------------------------------------------------


def _resolved(root: Path) -> list[Any]:
    return [seed_pid.resolve(stage, root) for stage in seed_pid.stages_to_run()]


class _Runner:
    """A run that records each file and answers a report that read what the file holds."""

    def __init__(self) -> None:
        self.ran: list[str] = []

    async def __call__(self, resolved: Any) -> LoadReport:
        self.ran.append(resolved.stage.file)
        return LoadReport(
            load_id=f"load-{len(self.ran)}", recipe_id=resolved.recipe_id,
            recipe_version=resolved.version, rows_read=10, nodes_created=4, edges_created=3,
        )  # fmt: skip


async def test_every_file_of_the_seed_is_run_in_order_when_nothing_is_loaded(
    tmp_path: Path,
) -> None:
    runner = _Runner()
    results = await seed_pid.run_stages(_resolved(_root(tmp_path)), [], run=runner)
    assert runner.ran == [s.file for s in pid_files.seed_stages("seed")]
    assert [r.skipped for r in results] == [False] * 15
    assert all(r.report is not None and r.seconds >= 0 for r in results)


async def test_a_file_with_an_unreverted_load_is_not_run_again(tmp_path: Path) -> None:
    root = _root(tmp_path)
    resolved = _resolved(root)
    loaded = [_record("L1", r.recipe_id, r.source, r.version) for r in resolved[:15]]
    runner = _Runner()
    results = await seed_pid.run_stages(resolved, loaded, run=runner)
    assert runner.ran == [], "a second seed re-reads nothing"
    assert [r.skipped for r in results] == [True] * 15 and all(r.report is None for r in results)


async def test_a_reverted_load_is_run_again(tmp_path: Path) -> None:
    """The ledger query leaves a reverted record out, so a reverted file is simply not among the
    records the seed is given: it runs. (`test_recipe_runs_unreverted.py` and its live twin prove
    the query's side; here, that absence means run.)"""
    root = _root(tmp_path)
    resolved = _resolved(root)
    loaded = [_record("L1", r.recipe_id, r.source, r.version) for r in resolved[1:]]
    runner = _Runner()
    await seed_pid.run_stages(resolved, loaded, run=runner)
    assert runner.ran == [resolved[0].stage.file]


@pytest.mark.parametrize(
    "change",
    [
        {"recipe_version": 2},
        {"source": "/elsewhere/pid_pin_calls.csv"},
        {"recipe_id": "another-recipe"},
    ],
)
async def test_a_load_of_another_version_source_or_recipe_does_not_stop_the_file(
    tmp_path: Path, change: dict[str, Any]
) -> None:
    root = _root(tmp_path)
    resolved = _resolved(root)
    target = resolved[11]  # R5, the call file
    assert target.stage.file == pid_files.CALLS
    record = _record("L1", target.recipe_id, target.source, target.version).model_copy(
        update=change
    )
    runner = _Runner()
    await seed_pid.run_stages([target], [record], run=runner)
    assert runner.ran == [pid_files.CALLS]


def test_there_is_no_second_copy_of_the_question_a_file_is_asked() -> None:
    """`already_loaded` was a function nothing called: `run_stages` decides by the ledger's own
    records. A second definition of "is it loaded" is a way for the two to disagree."""
    assert not hasattr(seed_pid, "already_loaded")


class _Ledger:
    def __init__(self, records: list[LoadRecord]) -> None:
        self.records = records
        self.asked: list[tuple[str, list[str]]] = []

    async def unreverted_loads(self, case: str, recipe_ids: Sequence[str]) -> list[LoadRecord]:
        self.asked.append((case, list(recipe_ids)))
        return [r for r in self.records if r.recipe_id in recipe_ids]


async def test_the_question_asked_of_the_ledger_is_the_cases_own(tmp_path: Path) -> None:
    ledger = _Ledger([])
    got = await seed_pid.loaded_so_far(ledger, CASE, _resolved(_root(tmp_path)))  # type: ignore[arg-type]
    assert got == []
    ((case, recipe_ids),) = ledger.asked
    assert case == CASE
    assert sorted(recipe_ids) == sorted(
        {seed_pid.recipe_id_of(s.recipe) for s in pid_files.seed_stages("seed")}
    )


async def test_r17_is_refused_without_an_unreverted_r9_in_the_case(tmp_path: Path) -> None:
    root = _root(tmp_path)
    r17 = seed_pid.resolve(pid_files.SEED_ORDER[16], root)
    assert r17.recipe_id == "pid-report-incidents"
    runner = _Runner()
    with pytest.raises(seed_pid.GuardRefused, match="pid-intel-reports"):
        await seed_pid.run_stages([r17], [], run=runner)
    assert runner.ran == [], "refused before a single row is read"
    # R9 absent but other recipes loaded: still refused
    other = _record("L1", "pid-seized-comms", "x")
    with pytest.raises(seed_pid.GuardRefused):
        await seed_pid.run_stages([r17], [other], run=runner)
    assert runner.ran == []


async def test_r17_is_allowed_once_r9_stands_and_never_asked_about_for_another_recipe(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    r9 = seed_pid.resolve(pid_files.SEED_ORDER[15], root)
    r17 = seed_pid.resolve(pid_files.SEED_ORDER[16], root)
    runner = _Runner()
    await seed_pid.run_stages([r17], [_record("L9", "pid-intel-reports", r9.source)], run=runner)
    assert runner.ran == [pid_files.REPORT_INCIDENTS]
    # R9 run in the same call makes R17 allowed after it, and R17 before it is refused
    runner = _Runner()
    await seed_pid.run_stages([r9, r17], [], run=runner)
    assert runner.ran == [pid_files.REPORTS, pid_files.REPORT_INCIDENTS]
    with pytest.raises(seed_pid.GuardRefused):
        await seed_pid.run_stages([r17, r9], [], run=_Runner())
    # an ordinary recipe is never held to the guard
    first = seed_pid.resolve(pid_files.SEED_ORDER[0], root)
    runner = _Runner()
    await seed_pid.run_stages([first], [], run=runner)
    assert runner.ran == [first.stage.file]


def test_the_guard_is_a_function_every_path_that_runs_a_stage_calls() -> None:
    """`run_stages` is the only place a stage is run, so the guard cannot be bypassed by a path that
    forgets it: the module calls the run itself nowhere else."""
    text = Path(seed_pid.__file__).read_text(encoding="utf-8")
    assert text.count("run_recipe_as(") == 1
    assert "check_r17_guard(" in text


async def test_r5s_time_and_peak_memory_are_said_when_it_ran_and_not_invented_when_it_did_not(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    resolved = _resolved(root)
    ticks = iter(range(0, 1000, 7))
    results = await seed_pid.run_stages(
        resolved, [], run=_Runner(), clock=lambda: float(next(ticks))
    )
    lines = seed_pid.measurement_lines(results, peak_before_mb=120.0, peak_after_mb=210.0)
    text = "\n".join(lines)
    assert "pid-pin-calls" in text and "7.0 s" in text
    assert "120" in text and "210" in text
    assert "process-wide" in text, "a peak of the whole process says so"
    skipped = await seed_pid.run_stages(
        resolved, [_record("L", r.recipe_id, r.source, r.version) for r in resolved], run=_Runner()
    )
    said = "\n".join(seed_pid.measurement_lines(skipped, peak_before_mb=1.0, peak_after_mb=2.0))
    assert "not run" in said and "s," not in said and "MB" not in said


def test_the_peak_memory_is_read_in_megabytes_on_either_platform() -> None:
    assert seed_pid.peak_megabytes(1_048_576 * 5, platform="darwin") == 5.0
    assert seed_pid.peak_megabytes(5 * 1024, platform="linux") == 5.0


# --- standing loads (Amendment 30: a reseed cannot hide a failed first seed) ----------------------


def _run_row(
    load_id: str,
    recipe: str,
    *,
    read: int,
    rejected: int = 0,
    held: int = 0,
    outcome: str = "succeeded",
    case: str = CASE,
) -> Any:
    return SimpleNamespace(
        load_id=load_id, recipe_id=recipe, investigation_id=case, outcome=outcome,
        rows_read=read, rows_rejected=rejected, rows_held=held, started_at=NOW,
    )  # fmt: skip


def test_the_run_that_made_a_standing_load_is_found_by_its_load_id_in_the_cases_own_runs() -> None:
    record = _record("L1", "r", "/x.csv")
    right = _run_row("L1", "r", read=5, held=2)
    runs = [
        _run_row("L1", "r", read=9, case="another-case"),
        _run_row("L1", "r", read=9, outcome="failed"),
        _run_row("L0", "r", read=9),
        right,
    ]
    found = seed_pid.pick_standing_run(runs, record)
    assert found == seed_pid.StandingRun(rows_read=5, rejected=0, held=2)
    assert seed_pid.pick_standing_run([], record) is None
    assert seed_pid.pick_standing_run([_run_row("L0", "r", read=1)], record) is None


async def test_a_standing_loads_rows_are_reported_and_a_short_one_fails_the_checks(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    resolved = _resolved(root)
    loaded = [_record(f"L{i}", r.recipe_id, r.source, r.version) for i, r in enumerate(resolved)]
    rows = {r.stage.file: 10 for r in resolved}

    async def standing_of(record: LoadRecord) -> Any:
        if record.load_id == "L3":
            return seed_pid.StandingRun(rows_read=7, rejected=1, held=2)  # short and held
        if record.load_id == "L4":
            return None  # no run row can be found for the load
        return seed_pid.StandingRun(rows_read=10, rejected=0, held=0)

    results = await seed_pid.run_stages(resolved, loaded, run=_Runner(), standing_of=standing_of)
    assert all(r.skipped for r in results)
    summary = "\n".join(seed_pid.summary_lines(results))
    assert "already loaded, not read again" in summary
    third = next(line for line in summary.splitlines() if resolved[3].stage.file in line)
    assert "7 rows read" in third and "1 rejected" in third and "2 held" in third
    fourth = next(line for line in summary.splitlines() if resolved[4].stage.file in line)
    assert "no run" in fourth
    lines, ok = seed_pid.check_lines(results, rows)
    assert ok is False
    failed = [line for line in lines if "FAILED" in line]
    assert len(failed) == 2 and any(resolved[3].stage.file in line for line in failed)
    assert any(resolved[4].stage.file in line for line in failed)

    # the same standing loads, whole: the checks hold, as the first seed's would
    async def whole(record: LoadRecord) -> Any:
        return seed_pid.StandingRun(rows_read=10, rejected=0, held=0)

    again = await seed_pid.run_stages(resolved, loaded, run=_Runner(), standing_of=whole)
    assert seed_pid.check_lines(again, rows)[1] is True


# --- no post-ingest resolution (Amendment 30, "Resolution's links") -------------------------------


class _Queue:
    def __init__(self) -> None:
        self.submitted: list[tuple[str, dict[str, Any]]] = []

    async def submit(self, job_type: str, payload: dict[str, Any]) -> str:
        self.submitted.append((job_type, payload))
        return f"job-{len(self.submitted)}"


def _deps_with(jobs: Any) -> RecipeRunDeps:
    return RecipeRunDeps(
        **{f.name: None for f in dataclasses.fields(RecipeRunDeps)} | {"jobs": jobs}
    )


async def test_the_seeds_runs_enqueue_no_post_ingest_resolution() -> None:
    """The finding, then the fix. A run of the reports recipe makes `Person` nodes (an outside
    subject is found or made on `nino`), and after a load that created something the run enqueues a
    `resolve_entity_type` job for each type its template declares and the ontology gives a
    `resolution` block (`Person`). The worker's resolution scores every pair its blocking rules
    bring together and writes a `SAME_AS` link for each, onto whatever nodes it reads, the reports
    recipe's included: links outside the load, resting on its nodes, which would make every
    rehearsal reset refuse."""
    reports = seed_pid._recipe(seed_pid.reports_recipe_file())
    report = LoadReport(load_id="l", recipe_id=reports.id, recipe_version=1, nodes_created=3)
    real = _Queue()
    await submit_post_ingest_resolution_jobs(
        report,
        reports.row_template,
        ontology=ONTOLOGY,
        jobs=real,  # type: ignore[arg-type]
    )
    assert real.submitted == [("resolve_entity_type", {"entity_type": "Person"})], (
        "the Studio's own route enqueues it: the shape the fix has to stop"
    )
    # the seed's deps hold a queue that takes the job and enqueues nothing
    original = _Queue()
    deps = seed_pid.without_post_ingest_resolution(_deps_with(original))
    await submit_post_ingest_resolution_jobs(
        report,
        reports.row_template,
        ontology=ONTOLOGY,
        jobs=deps.jobs,  # type: ignore[arg-type]
    )
    assert original.submitted == []
    assert deps.jobs is not original
    assert all(  # nothing else of the deps was touched
        getattr(deps, f.name) is None for f in dataclasses.fields(deps) if f.name != "jobs"
    )


def test_the_seed_runs_every_stage_with_the_deps_that_enqueue_nothing() -> None:
    text = Path(seed_pid.__file__).read_text(encoding="utf-8")
    assert "without_post_ingest_resolution(resources.run_deps())" in text
    assert text.count("run_deps()") == 1


# --- the pictures ---------------------------------------------------------------------------------


class _Pictures:
    """Finds a subject by its identifying property, and attaches unless it has a history."""

    def __init__(
        self,
        missing: set[str] = frozenset(),
        history: set[str] = frozenset(),  # type: ignore[assignment]
        refused: set[str] = frozenset(),
    ) -> None:  # type: ignore[assignment]
        self.missing, self.history, self.refused = missing, history, refused
        self.found: list[tuple[str, str, str]] = []
        self.attached: list[tuple[str, str, bytes, str]] = []

    async def find(self, entity_type: str, field_name: str, value: str) -> Any:
        self.found.append((entity_type, field_name, value))
        if value in self.missing:
            return None
        return SimpleNamespace(id=f"stored-{entity_type}-{value}", value=value)

    async def attach(self, node_id: str, *, name: str, data: bytes, legal_basis: str) -> bool:
        if any(node_id.endswith(v) for v in self.refused):
            raise ValueError("a subject the seed cannot mark faithfully")
        if any(node_id.endswith(v) for v in self.history):
            return False
        self.attached.append((node_id, name, data, legal_basis))
        return True


def _plan_of(count: int) -> pid_plan.Plan:
    """The real plan holding only its first `count` picture subjects, so each case draws few."""
    return dataclasses.replace(PLAN, picture_subjects=PLAN.picture_subjects[:count])


async def test_every_picture_attached_is_the_plans_picture_for_the_subject_found_by_reference() -> (
    None
):
    fake = _Pictures()
    plan = _plan_of(40)
    summary = await seed_pid.seed_pictures(plan, find=fake.find, attach=fake.attach)
    assert summary.attached == 40 and summary.skipped == 0 and summary.missing == []
    assert len(fake.attached) == 40
    expected = list(zip(plan.picture_subjects, pid_writes.picture_writes(plan), strict=True))
    for (node_id, name, data, basis), (key, (_, file_name, png)) in zip(
        fake.attached, expected, strict=True
    ):
        entity_type, _field_name, value = seed_pid.identity_of(PLAN, key)
        assert node_id == f"stored-{entity_type}-{value}", "found by reference, never by plan id"
        assert name == file_name and data == png
        assert basis == "Synthetic demonstration data"


async def test_a_subject_with_a_picture_history_is_not_touched() -> None:
    first = PLAN.picture_subjects[0]
    _, _, value = seed_pid.identity_of(PLAN, first)
    fake = _Pictures(history={value})
    summary = await seed_pid.seed_pictures(_plan_of(5), find=fake.find, attach=fake.attach)
    assert summary.skipped == 1 and summary.attached == 4
    assert all(not a[0].endswith(value) for a in fake.attached)


async def test_a_subject_not_found_is_counted_and_fails_the_seed() -> None:
    first = PLAN.picture_subjects[0]
    _, _, value = seed_pid.identity_of(PLAN, first)
    fake = _Pictures(missing={value})
    summary = await seed_pid.seed_pictures(_plan_of(5), find=fake.find, attach=fake.attach)
    assert summary.missing == [first] and summary.attached == 4
    assert not summary.ok


async def test_a_refusal_is_reported_by_subject_and_fails_the_seed() -> None:
    first = PLAN.picture_subjects[0]
    _, _, value = seed_pid.identity_of(PLAN, first)
    fake = _Pictures(refused={value})
    summary = await seed_pid.seed_pictures(_plan_of(5), find=fake.find, attach=fake.attach)
    assert [key for key, _ in summary.refused] == [first]
    assert "cannot mark faithfully" in summary.refused[0][1]
    assert summary.attached == 4 and not summary.ok


async def test_a_second_pass_over_subjects_that_all_have_a_picture_attaches_nothing() -> None:
    plan = _plan_of(60)
    values = {seed_pid.identity_of(plan, k)[2] for k in plan.picture_subjects}
    fake = _Pictures(history=values)
    summary = await seed_pid.seed_pictures(plan, find=fake.find, attach=fake.attach)
    assert summary.attached == 0 and summary.skipped == 60
    assert summary.ok and fake.attached == []
    said = "\n".join(seed_pid.picture_lines(summary, 60))
    assert re.search(r"\b0 attached\b", said), "the line the live test reads, exactly"


def test_every_picture_subject_is_found_by_the_property_the_replay_names() -> None:
    from tests.ingest.pid_golden_support import _identity

    for key in PLAN.picture_subjects:
        assert seed_pid.identity_of(PLAN, key) == _identity(PLAN.entity(key)), key


def test_no_picture_subject_carries_an_action_or_sanitisation_code() -> None:
    """The seed marks a picture with the worker's unit, which cannot carry either, and the route
    keeps neither (Amendment 27). Every PID element's handling code is `P`, so no reader's view
    differs between the plan's marking of a picture and the seed's."""
    for key in PLAN.picture_subjects:
        handling = PLAN.entity(key).handling
        assert handling.action_code is None and handling.sanitisation_code is None, key
    assert {e.handling.handling_code for e in PLAN.entities} == {"P"}
    assert {lk.handling.handling_code for lk in PLAN.links} == {"P"}


def test_every_picture_subject_is_one_the_seed_moment_loads() -> None:
    assert {pid_plan.entity_moment(PLAN, k) for k in PLAN.picture_subjects} == {"seed"}


# --- the demo numbers (Amendment 32) --------------------------------------------------------------


def _id(key: str) -> str:
    return pid_plan.node_id(key)


def _stub_edge(
    link_type: str,
    source: str,
    target: str,
    *,
    edge_id: str,
    props: Any = None,
    occurrences: int = 1,
    classification: str = "OFFICIAL",
) -> Edge:
    return Edge(
        id=edge_id, type=link_type, source=source, target=target, properties=props or {},
        occurrences=occurrences,
        provenance=Provenance(
            state=ProvenanceState.ASSERTED,
            sources=[SourceRef(document_id="fake", locator=edge_id, excerpt_hash="")],
            first_seen=NOW,
        ),
        handling=pid_writes._handling(pid_plan.PlanHandling(classification=classification)),
        audit=AuditStub(created_at=NOW, created_by="fake"),
        datasets=[PID.id],
    )  # fmt: skip


@cache
def _base_store(moment: pid_plan.Moment) -> tuple[dict[str, Node], list[Edge], tuple[str, ...]]:
    """The plan's nodes, links and selected reports at a moment, built once: `pid_writes.writes` is
    about 15,000 elements, and every case below reads its own copy of this."""
    from tests.scenarios.test_pid_plan import View

    plan = PLAN
    written_nodes, written_edges = pid_writes.writes(plan, moment, dataset=PID.id, created_at=NOW)
    nodes: dict[str, Node] = {}
    for write in written_nodes:
        nodes[write.id] = Node(
            id=write.id, type=write.type, properties=dict(write.properties),
            provenance=write.provenance, handling=write.handling,
            audit=AuditStub(created_at=NOW, created_by=write.created_by),
            datasets=list(write.datasets),
        )  # fmt: skip
    for key in plan.report_texts:
        # R9 writes the report's reference into `message_id`, which the plan's entity does not hold
        if _id(key) in nodes:
            nodes[_id(key)].properties["message_id"] = seed_pid.identity_of(plan, key)[2]
    edges: list[Edge] = [
        Edge(
            id=w.id,
            type=w.type,
            source=w.source,
            target=w.target,
            properties=dict(w.properties),
            interval=w.interval,
            occurrences=w.occurrences,
            provenance=w.provenance,
            handling=w.handling,
            audit=AuditStub(created_at=NOW, created_by=w.created_by),
            datasets=list(w.datasets),
        )  # fmt: skip
        for w in written_edges
    ]
    for link in pid_plan.links_at(plan, moment, secret_cleared=True):
        if link.link_type != "DEPICTS":
            continue
        picture = plan.entity(link.source)
        nodes[_id(link.source)] = Node(
            id=_id(link.source), type="Document", properties=dict(picture.properties),
            provenance=Provenance(
                state=ProvenanceState.ASSERTED,
                sources=[SourceRef(document_id="fake", locator=link.source, excerpt_hash="")],
                first_seen=NOW,
            ),
            handling=pid_writes._handling(picture.handling),
            audit=AuditStub(created_at=NOW, created_by="fake"), datasets=[PID.id],
        )  # fmt: skip
        edges.append(
            _stub_edge(
                "DEPICTS", _id(link.source), _id(link.target), edge_id=pid_plan.link_id(link)
            )
        )
    reports = tuple(sorted(View(plan).selected)) if moment in ("chapter4", "chapter9") else ()
    return nodes, edges, reports


class PlanGraph:
    """The store, as the plan says it holds the case at a moment: `pid_writes.writes` read back as
    `Node`s and `Edge`s, with the picture links the route writes and the one reading rule the
    adapter applies (an element above the reader's clearance is not there). The same five reads the
    checks make of the real graph: `find_node`, `search_nodes`, `expand`, `match`, `match_count`.
    A planted fault is made by `drop_edges`, `add_edge`, `set_property`, `drop_node` and
    `drop_report`.
    """

    def __init__(self, plan: pid_plan.Plan, moment: pid_plan.Moment) -> None:
        nodes, edges, reports = _base_store(moment)
        # shallow copies: a plant replaces an element, never edits one shared with another test
        self.nodes: dict[str, Node] = dict(nodes)
        self.edges: list[Edge] = list(edges)
        self.reports: list[str] = list(reports)

    # -- the faults a test plants

    def drop_edges(
        self,
        link_type: str,
        source: str | None = None,
        target: str | None = None,
        *,
        count: int | None = None,
    ) -> int:
        kept, dropped = [], 0
        for edge in self.edges:
            hit = (
                edge.type == link_type
                and (source is None or edge.source == _id(source))
                and (target is None or edge.target == _id(target))
                and (count is None or dropped < count)
            )
            if hit:
                dropped += 1
            else:
                kept.append(edge)
        self.edges = kept
        assert dropped, f"nothing to drop: {link_type} {source} {target}"
        return dropped

    def add_edge(self, link_type: str, source: str, target: str, *, occurrences: int = 1) -> None:
        assert _id(source) in self.nodes and _id(target) in self.nodes, (
            "a plant joins two stored nodes"
        )
        self.edges.append(
            _stub_edge(link_type, _id(source), _id(target), edge_id=f"planted-{len(self.edges)}",
                       occurrences=occurrences)
        )  # fmt: skip

    def set_property(self, key: str, name: str, value: Any) -> None:
        node = self.nodes[_id(key)]
        self.nodes[_id(key)] = node.model_copy(
            update={"properties": {**node.properties, name: value}}
        )

    def drop_node(self, key: str) -> None:
        del self.nodes[_id(key)]

    def drop_report(self) -> None:
        self.reports.pop()

    def add_node(self, key: str, node_type: str, properties: dict[str, Any]) -> None:
        template = next(iter(self.nodes.values()))
        self.nodes[_id(key)] = template.model_copy(
            update={"id": _id(key), "type": node_type, "properties": properties}
        )

    # -- the writes the seed makes (inferred links)

    async def begin_transaction(self) -> str:
        return "tx"

    async def commit_transaction(self, tx: str) -> None: ...

    async def rollback_transaction(self, tx: str) -> None: ...

    async def upsert_edges(self, writes: Sequence[Any], tx: str) -> list[str]:
        for w in writes:
            self.edges.append(
                Edge(
                    id=w.id,
                    type=w.type,
                    source=w.source,
                    target=w.target,
                    properties=dict(w.properties),
                    interval=w.interval,
                    occurrences=w.occurrences,
                    provenance=w.provenance,
                    handling=w.handling,
                    audit=AuditStub(created_at=NOW, created_by=w.created_by),
                    datasets=[PID.id],
                )  # fmt: skip
            )
        return [w.id for w in writes]

    # -- the reads

    def _may(self, principal: Principal, classification: str) -> bool:
        ranks = SCHEME.classification
        return ranks.index(classification) <= ranks.index(principal.clearance)

    def _nodes_seen(self, principal: Principal) -> dict[str, Node]:
        return {
            i: n for i, n in self.nodes.items() if self._may(principal, n.handling.classification)
        }

    async def find_node(
        self, entity_type: str, identifier_field: str, value: str, principal: Principal
    ) -> Node | None:
        for node in self._nodes_seen(principal).values():
            if node.type == entity_type and str(node.properties.get(identifier_field)) == value:
                return node
        return None

    async def search_nodes(
        self, query: str, principal: Principal, *, limit: int = 20
    ) -> list[Node]:
        found = []
        for node in self._nodes_seen(principal).values():
            declared = ONTOLOGY.entity_type(node.type)
            names = declared.identifiers if declared is not None else []
            if any(str(node.properties.get(name)) == query for name in names):
                found.append(node)
        return found[:limit]

    async def expand(self, req: ExpandRequest, principal: Principal) -> Subgraph:
        assert req.depth == 1, "the checks expand one step"
        seen = self._nodes_seen(principal)
        ids = set(req.node_ids)
        out: list[Edge] = []
        for edge in self.edges:
            if not self._may(principal, edge.handling.classification):
                continue
            if edge.source not in seen or edge.target not in seen:
                continue
            if req.edge_types is not None and edge.type not in req.edge_types:
                continue
            outward = edge.source in ids and req.direction in ("out", "both")
            inward = edge.target in ids and req.direction in ("in", "both")
            if outward or inward:
                out.append(edge)
        reached = ids | {end for e in out for end in (e.source, e.target)}
        return Subgraph(nodes=[seen[i] for i in sorted(reached) if i in seen], edges=out)

    async def match(self, pattern: PatternQuery, principal: Principal) -> Subgraph:
        zone = next(n for n in pattern.nodes if n.var == "zone")
        if zone.node_id not in self.nodes:
            return Subgraph(nodes=[], edges=[])
        docs = [self.nodes[_id(k)] for k in self.reports if _id(k) in self.nodes]
        return Subgraph(nodes=docs, edges=[])

    async def match_count(
        self, pattern: PatternQuery, principal: Principal, *, ceiling: int
    ) -> int:
        return len((await self.match(pattern, principal)).nodes)


MOMENTS: tuple[pid_plan.Moment, ...] = ("seed", "chapter4", "chapter9")
#: Which checks have something to read at each moment: the reports load at chapter 4.
NEEDS_REPORTS = {"Ch5", "Handling S2"}
ALL_CHECKS = ("J1", "J2", "Ch2", "Ch3", "Ch5", "Ch6", "Ch11 gaps", "Handling S2")


async def _run(graph: PlanGraph, moment: pid_plan.Moment) -> dict[str, Any]:
    results = await seed_pid.run_demo_checks(graph, _persona(), PLAN, moment)
    return {r.name: r for r in results}


@pytest.mark.parametrize("moment", MOMENTS)
async def test_each_demo_number_holds_over_the_plan_as_stored(moment: pid_plan.Moment) -> None:
    by_name = await _run(PlanGraph(PLAN, moment), moment)
    assert tuple(by_name) == ALL_CHECKS, "every check of Brief 2 section 8, in the brief's order"
    for name, result in by_name.items():
        assert result.ok, f"{name}: {result.detail}"
        needs_reports = name in NEEDS_REPORTS
        assert result.skipped == (needs_reports and moment == "seed"), name
        assert result.detail, "every check says what it measured"
    j1 = by_name["J1"].detail
    expected = (
        pid_plan.PRINCIPAL_LINK_COUNT_ACT1 if moment == "seed" else pid_plan.PRINCIPAL_LINK_COUNT
    )
    assert str(expected) in j1, "the figure comes from the plan's own constant"
    assert str(pid_plan.TOTAL_THROW_OVERS) in by_name["Ch2"].detail
    if moment != "seed":
        assert str(pid_plan.REPORTS_SELECTED) in by_name["Ch5"].detail
        assert str(pid_plan.REPORTS_USED) in by_name["Ch5"].detail


def _drop_one_visit(g: PlanGraph) -> None:
    g.drop_edges("VISITED", "outside_1", "principal")


def _drop_the_picture(g: PlanGraph) -> None:
    g.drop_edges("DEPICTS", None, "principal")


def _a_second_endpoint_for_the_coordinators_number(g: PlanGraph) -> None:
    held = dict(g.nodes[_id("number:coordinator")].properties)
    g.add_node("planted:second-endpoint", "Endpoint", held)


def _one_pin_stops_calling(g: PlanGraph) -> None:
    g.drop_edges("COMMUNICATED_WITH", "pin:relay_2", "number:coordinator")


def _a_pin_nobody_uses(g: PlanGraph) -> None:
    g.drop_edges("USES", None, "pin:relay_1")


def _a_throw_over_goes_missing_from_its_yard(g: PlanGraph) -> None:
    g.drop_edges("OCCURRED_AT", "incident:to:0001", None)


def _a_hotspot_yard_stops_adjoining_wing_f(g: PlanGraph) -> None:
    g.drop_edges("PART_OF", "yard:03", "zone:wing-f")


def _a_throw_over_moves_out_of_the_peak(g: PlanGraph) -> None:
    peak = {h for h, c in pid_plan.HOUR_COUNTS.items() if c > pid_plan.TOTAL_THROW_OVERS / 24}
    for key in sorted(k for k in (e.key for e in PLAN.entities) if k.startswith("incident:to:")):
        stored = g.nodes[_id(key)].properties["occurred_at"]
        when = datetime.fromisoformat(str(stored))
        if when.hour in peak:
            g.set_property(key, "occurred_at", when.replace(hour=3).isoformat())
            return
    raise AssertionError("no throw-over in a peak hour")


def _a_sunday_becomes_a_monday(g: PlanGraph) -> None:
    for key in sorted(k for k in (e.key for e in PLAN.entities) if k.startswith("incident:to:")):
        when = datetime.fromisoformat(str(g.nodes[_id(key)].properties["occurred_at"]))
        if when.weekday() == 6:
            g.set_property(key, "occurred_at", (when.replace(day=when.day + 1)).isoformat())
            return
    raise AssertionError("no Sunday throw-over")


def _a_report_leaves_the_pattern(g: PlanGraph) -> None:
    g.drop_report()


def _the_pattern_zone_is_not_there(g: PlanGraph) -> None:
    g.drop_node("zone:wing-f")


def _no_report_carries_s2(g: PlanGraph) -> None:
    for key in g.reports:
        node = g.nodes[_id(key)]
        g.nodes[_id(key)] = node.model_copy(
            update={"handling": node.handling.model_copy(update={"sanitisation_code": None})}
        )


def _the_payer_stops_funding_one(g: PlanGraph) -> None:
    g.drop_edges("TRANSACTED", "account:payer", "cash:relay_2")


def _the_payer_pays_a_fourth(g: PlanGraph) -> None:
    fourth = next(e.key for e in PLAN.entities if e.key.startswith("cash:prisoner:"))
    g.add_edge("TRANSACTED", "account:payer", fourth, occurrences=2)


def _the_coordinator_stops_visiting(g: PlanGraph) -> None:
    g.drop_edges("VISITED", "coordinator", "principal")


def _the_unidentified_number_gets_an_owner(g: PlanGraph) -> None:
    g.add_edge("USES", "relay_1", "number:unidentified")


def _a_person_is_linked_to_a_throw_over(g: PlanGraph) -> None:
    g.add_edge("PRESENT_AT", "relay_1", "incident:to:0002")


def _the_third_member_is_named_in_a_text_report(g: PlanGraph) -> None:
    text = "planted:text-report"
    g.add_node(text, "Document", {"media_kind": "text", "message_id": "IR 9999"})
    g.add_edge("MENTIONED_IN", "third_member", text)


def _the_found_account_has_a_holder(g: PlanGraph) -> None:
    g.add_node(
        "planted:found-account", "Endpoint",
        {"value_normalised": "SYN-00988", "e164": "SYN-00988", "endpoint_kind": "account"},
    )  # fmt: skip


#: (the check, the moments it is planted at, the mistake, the other checks that read the same
#: thing and so fail with it): each plant must turn its own check red, and none outside that set.
PLANTS: list[tuple[str, tuple[str, ...], Callable[[PlanGraph], None], tuple[str, ...]]] = [
    ("J1", MOMENTS, _drop_one_visit, ()),
    ("J1", MOMENTS, _drop_the_picture, ()),
    ("J2", MOMENTS, _a_second_endpoint_for_the_coordinators_number, ()),
    ("J2", MOMENTS, _one_pin_stops_calling, ()),
    ("J2", MOMENTS, _a_pin_nobody_uses, ()),
    ("Ch2", MOMENTS, _a_throw_over_goes_missing_from_its_yard, ("Ch3",)),
    ("Ch2", MOMENTS, _a_hotspot_yard_stops_adjoining_wing_f, ()),
    ("Ch3", MOMENTS, _a_throw_over_moves_out_of_the_peak, ()),
    ("Ch3", MOMENTS, _a_sunday_becomes_a_monday, ()),
    ("Ch5", ("chapter4", "chapter9"), _a_report_leaves_the_pattern, ()),
    ("Ch5", ("chapter4", "chapter9"), _the_pattern_zone_is_not_there, ("Ch2", "Handling S2")),
    ("Handling S2", ("chapter4", "chapter9"), _no_report_carries_s2, ()),
    ("Ch6", MOMENTS, _the_payer_stops_funding_one, ()),
    ("Ch6", MOMENTS, _the_payer_pays_a_fourth, ()),
    ("Ch6", MOMENTS, _the_coordinator_stops_visiting, ("J1",)),
    ("Ch11 gaps", MOMENTS, _the_unidentified_number_gets_an_owner, ()),
    ("Ch11 gaps", MOMENTS, _a_person_is_linked_to_a_throw_over, ()),
    ("Ch11 gaps", MOMENTS, _the_third_member_is_named_in_a_text_report, ()),
    ("Ch11 gaps", MOMENTS, _the_found_account_has_a_holder, ()),
]


@pytest.mark.parametrize(
    ("check", "moment", "plant", "also"),
    [(c, m, p, also) for c, ms, p, also in PLANTS for m in ms],
    ids=lambda v: v.__name__ if callable(v) else str(v),
)
async def test_each_demo_number_fails_for_its_own_mistake(
    check: str, moment: pid_plan.Moment, plant: Callable[[PlanGraph], None], also: tuple[str, ...]
) -> None:
    """Rule 15: the planted fault is made to the store the check reads, in the shape the store gives
    (`Node`s and `Edge`s from `pid_writes.writes`), and it must turn exactly its own check red and
    leave the others alone, so a check that passes whatever is stored (or fails whatever is stored)
    is found."""
    graph = PlanGraph(PLAN, moment)
    plant(graph)
    by_name = await _run(graph, moment)
    assert not by_name[check].ok, f"{check} passed over a planted fault: {by_name[check].detail}"
    failed = {n for n, r in by_name.items() if not r.ok}
    assert failed == {check, *also}, {n: r.detail for n, r in by_name.items() if not r.ok}


async def test_a_check_that_cannot_run_is_a_failed_check() -> None:
    """A store that raises, or a subject the store does not hold, is a failure, never a pass."""

    class Broken(PlanGraph):
        async def expand(self, req: ExpandRequest, principal: Principal) -> Subgraph:
            raise RuntimeError("the store is down")

    results = await seed_pid.run_demo_checks(Broken(PLAN, "seed"), _persona(), PLAN, "seed")
    failed = {r.name: r for r in results if not r.ok}
    assert {"J1", "J2", "Ch2", "Ch3", "Ch6", "Ch11 gaps"} <= set(failed)
    assert "the store is down" in failed["J1"].detail
    empty = PlanGraph(PLAN, "seed")
    empty.nodes.clear()
    nothing = await seed_pid.run_demo_checks(empty, _persona(), PLAN, "seed")
    assert all(not r.ok for r in nothing if not r.skipped), "nothing stored, nothing passes"


async def test_the_checks_read_as_the_persona_and_see_no_more_than_the_persona_may() -> None:
    """The checks are the persona's own reads (Amendment 32): a reader cleared to OFFICIAL, scoped
    to the case. The fake reads under the scheme as the adapter does, so a check that asked as
    anyone else would see what it must not."""
    seen: list[Principal] = []

    class Spy(PlanGraph):
        async def expand(self, req: ExpandRequest, principal: Principal) -> Subgraph:
            seen.append(principal)
            return await super().expand(req, principal)

    await seed_pid.run_demo_checks(Spy(PLAN, "seed"), _persona(), PLAN, "seed")
    assert seen and all(p is _persona() for p in seen)
    assert _persona().clearance == "OFFICIAL" and _persona().datasets == [PID.id]


def test_the_expected_figures_are_read_from_the_plan_and_none_is_typed_in_the_seed() -> None:
    """Amendment 32: "read the expected values from demo_fixtures.pid_plan". A number the brief
    quotes, typed into the seed, is a second copy that drifts."""
    tree = ast.parse(Path(seed_pid.__file__).read_text(encoding="utf-8"))
    typed = sorted(
        {
            n.value
            for n in ast.walk(tree)
            if isinstance(n, ast.Constant)
            and isinstance(n.value, int)
            and not isinstance(n.value, bool)
            and n.value in {45, 49, 136, 262, 173, 229, 68, 90, 50, 23, 28, 13}
        }
    )
    assert typed == [], typed


def test_the_moment_a_case_is_at_is_read_from_its_standing_loads() -> None:
    comms = seed_pid.comms_recipe_id()
    reports, incidents = seed_pid.reports_recipe_id(), seed_pid.incidents_recipe_id()
    root = Path("/ingest")
    batch2 = _record("B", comms, _source(root, pid_files.BATCH_2))
    batch1 = _record("A", comms, _source(root, pid_files.BATCH_1))
    r9, r17 = (
        _record("C", reports, _source(root, pid_files.REPORTS)),
        _record("D", incidents, _source(root, pid_files.REPORT_INCIDENTS)),
    )
    assert seed_pid.moment_of([]) == "seed"
    assert seed_pid.moment_of([batch1]) == "seed"
    assert seed_pid.moment_of([r9]) == "seed", "the reports alone are not chapter 4 yet"
    assert seed_pid.moment_of([r9, r17]) == "chapter4"
    assert seed_pid.moment_of([r9, r17, batch1]) == "chapter4"
    assert seed_pid.moment_of([r9, r17, batch2]) == "chapter9"
    assert seed_pid.moment_of([batch2]) == "seed", "batch 2 with no reports is not chapter 9"


def test_a_failed_demo_number_fails_the_seed_line_and_the_exit() -> None:
    ok = seed_pid.CheckResult("J1", True, "45 links", False)
    bad = seed_pid.CheckResult("Ch2", False, "135 of 262", False)
    skipped = seed_pid.CheckResult("Ch5", True, "needs the reports", True)
    lines, good = seed_pid.demo_check_lines([ok, skipped])
    assert good is True
    assert any("check ok" in line and "J1" in line for line in lines)
    assert any("not run" in line and "Ch5" in line for line in lines)
    lines, good = seed_pid.demo_check_lines([ok, bad, skipped])
    assert good is False
    assert any("check FAILED" in line and "Ch2" in line and "135 of 262" in line for line in lines)
    assert seed_pid.exit_code(files_ok=True, pictures_ok=True, demo_ok=False) == 1
    assert seed_pid.exit_code(files_ok=False, pictures_ok=True, demo_ok=True) == 1
    assert seed_pid.exit_code(files_ok=True, pictures_ok=False, demo_ok=True) == 1
    assert seed_pid.exit_code(files_ok=True, pictures_ok=True, demo_ok=True) == 0


# --- the reset (Amendment 32) ---------------------------------------------------------------------


def _loads() -> list[LoadRecord]:
    root = Path("/ingest")
    batch2_listed = _source(root, pid_files.BATCH_2)
    batch2_incoming = str(
        root / "uploaded" / "prison-intelligence" / "incoming" / pid_files.BATCH_2
    )
    return [
        _record("01A", "pid-pin-calls", _source(root, pid_files.CALLS)),
        _record("01B", "pid-seized-comms", _source(root, pid_files.BATCH_1)),
        _record("01C", "pid-intel-reports", _source(root, pid_files.REPORTS)),
        _record("01D", "pid-report-incidents", _source(root, pid_files.REPORT_INCIDENTS)),
        _record("01E", "pid-seized-comms", batch2_incoming),
        _record("01F", "pid-intel-reports", _source(root, pid_files.REPORTS)).model_copy(
            update={"load_id": "01F:source"}
        ),
        _record("01G", "pid-seized-comms", batch2_listed),
        _record("01H", "pid-seized-comms", "/elsewhere/uploaded/other/" + pid_files.BATCH_2),
    ]


def test_the_reset_chooses_every_r9_and_r17_load_and_only_batch_twos_r6_loads_newest_first() -> (
    None
):
    chosen = seed_pid.choose_reset(_loads())
    assert [r.load_id for r in chosen] == ["01G", "01F:source", "01E", "01D", "01C"]
    kept_out = {"01A", "01B", "01H"}
    assert kept_out.isdisjoint(r.load_id for r in chosen)


def test_the_reset_choice_fails_for_a_record_chosen_by_the_wrong_rule() -> None:
    """Planted, in the real shape (a `LoadRecord`): batch 1's R6 load and another dataset's batch-2
    file are chosen by a rule that looks at the recipe alone, and the oldest-first order is the one
    that reverts a node before the link resting on it."""
    wrong = [r for r in _loads() if r.recipe_id in ("pid-seized-comms", "pid-intel-reports")]
    assert {"01B", "01H"} <= {r.load_id for r in wrong}
    right = {r.load_id for r in seed_pid.choose_reset(_loads())}
    assert not {"01B", "01H"} & right
    assert [r.load_id for r in seed_pid.choose_reset(_loads())] != sorted(
        r.load_id for r in seed_pid.choose_reset(_loads())
    )


@dataclass
class _ResetWorld:
    records: list[LoadRecord]
    resting: set[str] = field(default_factory=set)
    refuse_at: str | None = None
    refusal_reason: str = "rests_on_by_live_links"
    starting_draft: bool = False
    log: list[str] = field(default_factory=list)

    async def unreverted_loads(self, case: str, recipe_ids: Sequence[str]) -> list[LoadRecord]:
        self.log.append(f"query:{case}")
        return [r for r in self.records if r.recipe_id in recipe_ids]

    async def load_record(self, load_id: str) -> LoadRecord | None:
        found = next((r for r in self.records if r.load_id == load_id), None)
        return found.model_copy(update={"created_node_ids": [f"n-{load_id}"]}) if found else None

    async def live_edges_touching(self, node_ids: Sequence[str]) -> set[str]:
        self.log.append("links-asked")
        return set(self.resting)

    async def get_edges(self, ids: Sequence[str], principal: Any) -> list[Any]:
        return [SimpleNamespace(id=i, type="SAME_AS") for i in sorted(ids) if i != "hidden-link"]

    async def revert(self, load_id: str, *, reverted_by: str, deps: Any, now: datetime) -> Any:
        self.log.append(f"revert:{load_id}")
        if load_id == self.refuse_at:
            raise RevertRefused([RevertRefusal(load_id, self.refusal_reason, 2)])  # type: ignore[arg-type]
        return RevertResult()


def _reset_args(
    tmp_path: Path, world: _ResetWorld, said: list[str], **extra: Any
) -> dict[str, Any]:
    root = _root(tmp_path)
    log = world.log

    async def restore_draft() -> None:
        log.append("restore-draft")

    async def draft_is_starting() -> bool:
        log.append("draft-asked")
        return world.starting_draft

    def rewrite_reports() -> None:
        log.append("rewrite-reports")
        seed_pid.listed_folder(root).mkdir(parents=True, exist_ok=True)
        (seed_pid.listed_folder(root) / pid_files.REPORTS).write_text("fresh", encoding="utf-8")

    return {
        "case_id": CASE, "root": root, "ledger": world, "graph": world, "worker": _persona(),
        "revert": world.revert, "deps": object(), "now": NOW, "restore_draft": restore_draft,
        "draft_is_starting": draft_is_starting, "rewrite_reports": rewrite_reports,
        "say": said.append,
    } | extra  # fmt: skip


def _seed_folder(root: Path, *, extra: Sequence[str] = (), batch_two: bool = True) -> None:
    listed = seed_pid.listed_folder(root)
    (listed / "incoming").mkdir(parents=True, exist_ok=True)
    for stage in pid_files.SEED_ORDER:
        if stage.file != pid_files.BATCH_2:
            (listed / stage.file).write_text("x", encoding="utf-8")
    (listed / "incoming" / pid_files.BATCH_2).write_text("b2", encoding="utf-8")
    if batch_two:
        (listed / pid_files.BATCH_2).write_text("b2", encoding="utf-8")
    for name in extra:
        (listed / name).write_text("a corrected upload", encoding="utf-8")


async def test_a_reset_reverts_newest_first_then_restores_the_draft_and_the_files(
    tmp_path: Path,
) -> None:
    world, said = _ResetWorld(_loads()), []
    _seed_folder(_root(tmp_path))
    code = await seed_pid.reset_live(**_reset_args(tmp_path, world, said))
    assert code == 0
    assert world.log == [
        f"query:{CASE}", "revert:01G", "revert:01F:source", "revert:01E", "revert:01D",
        "revert:01C", "restore-draft", "rewrite-reports",
    ]  # fmt: skip
    assert "links-asked" not in world.log, "Amendment 32 withdrew the precheck of every refusal"
    assert not (seed_pid.listed_folder(_root(tmp_path)) / pid_files.BATCH_2).exists()
    assert (seed_pid.listed_folder(_root(tmp_path)) / "incoming" / pid_files.BATCH_2).exists()


async def test_a_revert_refused_stops_names_it_and_gives_the_restore_procedure(
    tmp_path: Path,
) -> None:
    world, said = _ResetWorld(_loads(), refuse_at="01E", resting={"same-as-1", "hidden-link"}), []
    _seed_folder(_root(tmp_path), extra=["a_correction.csv"])
    code = await seed_pid.reset_live(**_reset_args(tmp_path, world, said))
    assert code == 1
    assert [e for e in world.log if e.startswith("revert")] == [
        "revert:01G", "revert:01F:source", "revert:01E",
    ]  # fmt: skip
    assert "restore-draft" not in world.log and "rewrite-reports" not in world.log
    assert "draft-asked" not in world.log
    text = "\n".join(said)
    assert "01E" in text and "1 live link(s) you can read" in text, "named, readable links only"
    assert "2 live link(s)" not in text and "hidden-link" not in text and "more" not in text, (
        "no count of the links the engineer cannot read (Amendment 34)"
    )
    assert "reverted: 01G, 01F:source" in text
    assert seed_pid.BACKUP_COMMAND in text and seed_pid.RESTORE_COMMAND in text, (
        "the whole restore procedure, the commands to the character"
    )
    assert "reseed the case" not in text.lower(), "it no longer tells the operator to reseed"
    assert (seed_pid.listed_folder(_root(tmp_path)) / "a_correction.csv").exists(), (
        "files untouched"
    )
    assert (seed_pid.listed_folder(_root(tmp_path)) / pid_files.BATCH_2).exists()


def test_the_restore_procedure_restores_the_demo_in_order_and_ends_with_the_reset() -> None:
    """Amendment 34: a backup holds the stores and not the ingest folder (a host bind mount), so the
    procedure is: take the backup after seeding; to restore, empty the volumes, bring the stack back
    up, restore the set, and then run the reset, which removes a released batch 2 and rewrites the
    reports file."""
    steps = list(seed_pid.restore_steps())
    text = "\n".join(steps)
    where = {
        name: next(i for i, line in enumerate(steps) if needle in line)
        for name, needle in {
            "backup": seed_pid.BACKUP_COMMAND,
            "empty": "empty the deployment's volumes",
            "restore": seed_pid.RESTORE_COMMAND,
            "reset": "--reset-live",
        }.items()
    }
    assert where["backup"] < where["empty"] < where["restore"] < where["reset"]
    assert where["reset"] == max(
        i for i, line in enumerate(steps) if line.strip()[:2] in {"1.", "2.", "3.", "4."}
    ), "the reset is the last numbered step"
    reset_line = steps[where["reset"]]
    assert (
        "python -m scripts.seed_internal prison-intelligence --reset-live --stop-api" in reset_line
    )
    assert "ingest folder" in text and "batch 2" in text and "reports file" in text, (
        "it says why: the backup does not hold the ingest folder"
    )
    assert "ospreyflow restore" in steps[where["restore"]] and "--yes" in steps[where["restore"]]
    assert "reseed" not in text.lower()


async def test_a_refusal_prints_a_count_of_readable_links_and_types_and_ids_only_with_show_ids(
    tmp_path: Path,
) -> None:
    quiet, shown = [], []
    for said, show in ((quiet, False), (shown, True)):
        world = _ResetWorld(_loads(), refuse_at="01E", resting={"same-as-1", "hidden-link"})
        _seed_folder(_root(tmp_path))
        code = await seed_pid.reset_live(**_reset_args(tmp_path, world, said, show_ids=show))
        assert code == 1
        assert "links-asked" in world.log, "the readable count needs the read, shown or not"
    text = "\n".join(quiet)
    assert "1 live link(s) you can read" in text
    assert "same-as-1" not in text and "SAME_AS" not in text and "hidden-link" not in text
    assert "--show-ids" in text, "it says how to see them"
    text = "\n".join(shown)
    assert "same-as-1" in text and "SAME_AS" in text, "the readable link, by type and id"
    assert "hidden-link" not in text and "not shown" not in text and "more" not in text


async def test_a_long_list_of_readable_links_says_its_total(tmp_path: Path) -> None:
    said: list[str] = []
    many = {f"link-{i:03d}" for i in range(seed_pid.LISTED + 7)}
    world = _ResetWorld(_loads(), refuse_at="01E", resting=many)
    _seed_folder(_root(tmp_path))
    await seed_pid.reset_live(**_reset_args(tmp_path, world, said, show_ids=True))
    text = "\n".join(said)
    assert f"{len(many)} live link(s) you can read" in text
    assert f"showing {seed_pid.LISTED} of {len(many)}" in text
    assert text.count("SAME_AS link-") == seed_pid.LISTED


async def test_only_a_refusal_about_links_has_links_to_show(tmp_path: Path) -> None:
    said: list[str] = []
    world = _ResetWorld(_loads(), refuse_at="01E", refusal_reason="merged_nodes", resting={"x"})
    _seed_folder(_root(tmp_path))
    code = await seed_pid.reset_live(**_reset_args(tmp_path, world, said, show_ids=True))
    assert code == 1 and "links-asked" not in world.log
    assert "x" not in "\n".join(said).split()


async def test_a_revert_that_stopped_part_way_says_so_and_restores_nothing(tmp_path: Path) -> None:
    world, said = _ResetWorld(_loads()), []

    async def incomplete(load_id: str, *, reverted_by: str, deps: Any, now: datetime) -> Any:
        world.log.append(f"revert:{load_id}")
        raise RevertIncomplete(done=[], failed_load_id=load_id, failed_step="events",
                               cause=RuntimeError("the analytics store is down"))  # fmt: skip

    args = _reset_args(tmp_path, world, said) | {"revert": incomplete}
    _seed_folder(_root(tmp_path))
    assert await seed_pid.reset_live(**args) == 2
    assert "restore-draft" not in world.log
    assert "analytics store is down" in "\n".join(said)


async def test_the_reset_removes_batch_two_and_every_other_file_naming_each(
    tmp_path: Path,
) -> None:
    world, said = _ResetWorld(_loads()), []
    _seed_folder(_root(tmp_path), extra=["corrected_upload.csv", "notes.txt"])
    await seed_pid.reset_live(**_reset_args(tmp_path, world, said))
    listed = seed_pid.listed_folder(_root(tmp_path))
    left = sorted(p.name for p in listed.iterdir() if p.is_file())
    assert left == sorted({s.file for s in pid_files.SEED_ORDER} - {pid_files.BATCH_2})
    text = "\n".join(said)
    for name in ("corrected_upload.csv", "notes.txt", pid_files.BATCH_2):
        assert f"removed {name}" in text, name
    assert (listed / pid_files.REPORTS).read_text(encoding="utf-8") == "fresh"


async def test_the_reset_says_what_it_cannot_undo(tmp_path: Path) -> None:
    world, said = _ResetWorld(_loads()), []
    _seed_folder(_root(tmp_path))
    await seed_pid.reset_live(**_reset_args(tmp_path, world, said))
    text = "\n".join(said).lower()
    for phrase in (
        "reverted runs stay in the ledger",
        "last run",
        "alerts and the cases they opened",
        "review-queue findings",
        "contents of working sets",
        "hotlists and saved patterns",
        "climbing version number",
        "recipe repository",
    ):
        assert phrase in text, phrase


async def test_a_reset_that_reverted_nothing_leaves_a_starting_draft_alone(tmp_path: Path) -> None:
    """Amendment 30: no new R9 version for a reset that had nothing to do. The files are still
    rewritten, since they cost nothing and may have been edited."""
    world, said = _ResetWorld([], starting_draft=True), []
    _seed_folder(_root(tmp_path))
    assert await seed_pid.reset_live(**_reset_args(tmp_path, world, said)) == 0
    assert "restore-draft" not in world.log and "rewrite-reports" in world.log
    text = "\n".join(said).lower()
    assert "no load to revert" in text and "already at its starting draft" in text
    # not at its starting draft (the fallback published it): restored, though nothing was reverted
    world, said = _ResetWorld([], starting_draft=False), []
    _seed_folder(_root(tmp_path))
    assert await seed_pid.reset_live(**_reset_args(tmp_path, world, said)) == 0
    assert world.log[-2:] == ["restore-draft", "rewrite-reports"]
    # something was reverted: the draft is restored even if it looks like its start
    world, said = _ResetWorld(_loads(), starting_draft=True), []
    _seed_folder(_root(tmp_path))
    assert await seed_pid.reset_live(**_reset_args(tmp_path, world, said)) == 0
    assert "restore-draft" in world.log and "draft-asked" not in world.log


def _starting_row(root: Path, **changes: Any) -> Any:
    source = _source(root, pid_files.REPORTS)
    row = SimpleNamespace(
        status=StudioRecipeStatus.DRAFT, row_template=None, unmapped_fields=[], deduplicate=None,
        pipeline=seed_pid.starting_pipeline(source), source_location=source, owning_unit="verify",
        dataset_id="prison-intelligence",
    )  # fmt: skip
    for name, value in changes.items():
        setattr(row, name, value)
    return row


def test_a_draft_is_at_its_start_only_if_it_is_a_draft_with_no_mapping_and_the_starting_pipeline(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    source = _source(root, pid_files.REPORTS)
    assert seed_pid.is_starting_draft(_starting_row(root), source, "verify")
    mapped = seed_pid._recipe(seed_pid.reports_recipe_file()).row_template
    other_pipeline = seed_pid.starting_pipeline(source).model_copy(update={"edges": []})
    for change in (
        {"status": StudioRecipeStatus.PUBLISHED},
        {"status": StudioRecipeStatus.FLAGGED},
        {"row_template": mapped},
        {"unmapped_fields": [object()]},
        {"deduplicate": object()},
        {"pipeline": other_pipeline},
        {"pipeline": None},
        {"source_location": "/elsewhere/x.csv"},
        {"owning_unit": "another-unit"},
        {"dataset_id": "another-dataset"},
    ):
        assert not seed_pid.is_starting_draft(_starting_row(root, **change), source, "verify"), (
            change
        )


# --- the mid-demo commands ------------------------------------------------------------------------


def test_release_batch_2_copies_it_into_the_listed_folder_and_opens_no_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("a store was opened")

    monkeypatch.setattr(seed_pid, "build_run_resources", refuse)
    root = _root(tmp_path)
    _seed_folder(root, batch_two=False)
    assert seed_pid.main(["--release-batch-2", "--ingest-root", str(root)]) == 0
    listed = seed_pid.listed_folder(root)
    assert (listed / pid_files.BATCH_2).read_bytes() == b"b2"
    assert (listed / "incoming" / pid_files.BATCH_2).exists(), "the original stays"
    assert pid_files.BATCH_2 in capsys.readouterr().out
    # again: the same bytes, said to be there already, nothing changed
    assert seed_pid.main(["--release-batch-2", "--ingest-root", str(root)]) == 0
    assert "already" in capsys.readouterr().out


def test_release_batch_2_before_the_seed_says_to_seed_first(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert seed_pid.main(["--release-batch-2", "--ingest-root", str(_root(tmp_path))]) == 1
    assert "seed" in capsys.readouterr().err.lower()


def test_the_fallback_changes_the_version_line_and_nothing_else() -> None:
    text = (FIXTURES / "pid_intel_reports_recipe.yaml").read_text(encoding="utf-8")
    changed = seed_pid.with_version(text, 4)
    assert changed != text
    before, after = text.splitlines(), changed.splitlines()
    assert len(before) == len(after)
    differing = [(a, b) for a, b in zip(before, after, strict=True) if a != b]
    assert differing == [("version: 1", "version: 4")]
    assert seed_pid.with_version(text, 1) == text
    with pytest.raises(ValueError, match="version"):
        seed_pid.with_version("id: x\n", 2)


def _draft_row(version: int = 3, **changes: Any) -> StudioRecipeDraft:
    """R9's draft as the reset leaves it, with what Connect holds edited by an engineer since (the
    legal basis, the marking, the connector), so a fallback that leaves them is found."""
    recipe = seed_pid._recipe(seed_pid.reports_recipe_file())
    source = "/ingest/uploaded/prison-intelligence/" + pid_files.REPORTS
    base: dict[str, Any] = {
        "recipe_id": recipe.id, "version": version, "status": StudioRecipeStatus.DRAFT,
        "label": recipe.label, "connector_profile": "generic-csv", "source_location": source,
        "handling": {"classification": "OFFICIAL", "handling_code": "P", "originator": "elsewhere",
                     "owning_unit": "elsewhere", "units": ["elsewhere"]},
        "legal_basis": "An engineer's own words", "owning_unit": "verify", "created_by": "x",
        "created_at": NOW, "ready_for_profile": False, "dataset_id": "prison-intelligence",
        "pipeline": seed_pid.starting_pipeline(source),
    }  # fmt: skip
    return StudioRecipeDraft(**(base | changes))


class _FakeRecipeStore:
    """The `StudioRecipeStore` methods the fallback uses, over one real `StudioRecipeDraft`: the
    writes keep the real store's rules (`carry_source_declarations`; an edit clears `verified_at`;
    `publish` needs a verified draft), so a fallback that skips a step is refused here as it would
    be there."""

    def __init__(
        self, row: StudioRecipeDraft, log: list[tuple[str, Any]], *, ignore: set[str] = frozenset()
    ) -> None:  # type: ignore[assignment]
        self.row, self.log, self.ignore = row, log, ignore

    async def get(self, recipe_id: str) -> StudioRecipeDraft:
        return self.row

    async def update_draft(self, recipe_id: str, principal: Any, **kw: Any) -> StudioRecipeDraft:
        self.log.append(("update_draft", sorted(k for k, v in kw.items() if v is not None)))
        update: dict[str, Any] = {"verified_at": None}
        if kw.get("handling") is not None:
            update["handling"] = carry_source_declarations(self.row.handling, kw["handling"])
        for name in ("connector_profile", "source_location", "legal_basis"):
            if kw.get(name) is not None and name not in self.ignore:
                update[name] = kw[name]
        if kw.get("deduplicate") is not None:
            update["deduplicate"] = kw["deduplicate"]
        self.row = self.row.model_copy(update=update)
        return self.row

    async def update_row_template(self, recipe_id: str, principal: Any, **kw: Any) -> Any:
        self.log.append(("update_row_template", kw["row_template"] is not None))
        self.row = self.row.model_copy(update={
            "row_template": kw["row_template"], "unmapped_fields": kw["unmapped_fields"],
            "verified_at": None,
        })  # fmt: skip
        return self.row

    async def mark_verified(self, recipe_id: str, version: int, *, now: datetime) -> None:
        self.log.append(("verified", version))
        self.row = self.row.model_copy(update={"verified_at": now})

    async def publish(self, recipe_id: str, principal: Any, **kw: Any) -> StudioRecipeDraft:
        assert self.row.verified_at is not None, "publish needs a verified draft"
        self.log.append(("publish", kw))
        self.row = self.row.model_copy(update={
            "status": StudioRecipeStatus.PUBLISHED, "git_path": kw["git_path"],
            "pack_versions": kw["pack_versions"], "ontology_version": kw["ontology_version"],
        })  # fmt: skip
        return self.row


class _Audit:
    def __init__(self, log: list[tuple[str, Any]]) -> None:
        self.log = log

    async def record(self, **kw: Any) -> None:
        self.log.append(("audit", kw))


def _fallback_kwargs(log: list[tuple[str, Any]], tmp_path: Path) -> dict[str, Any]:
    async def commit(recipe_id: str, data: bytes, *, version: int, repo_root: Path) -> str:
        log.append(("commit", (recipe_id, version, data)))
        return f"recipes/{recipe_id}.yaml"

    return {
        "ontology": ONTOLOGY, "scheme": SCHEME, "repo_root": tmp_path, "commit": commit,
        "audit": _Audit(log), "now": NOW,
    }  # fmt: skip


async def test_the_fallback_publishes_the_file_as_a_route_would(tmp_path: Path) -> None:
    log: list[tuple[str, Any]] = []
    store = _FakeRecipeStore(_draft_row(3), log)
    out = await seed_pid.publish_reports_fallback(
        store,
        _persona(),
        **_fallback_kwargs(log, tmp_path),  # type: ignore[arg-type]
    )
    file_recipe = seed_pid._recipe(seed_pid.reports_recipe_file())
    assert out.version == 3 and out.status is StudioRecipeStatus.PUBLISHED
    names = [n for n, _ in log]
    assert names == [
        "update_draft",
        "update_row_template",
        "verified",
        "commit",
        "publish",
        "audit",
    ], "the route's order: the writes, the commit, the flip of the row, then the audit entry"
    # the row's content is the committed file's, Connect's fields included
    assert out.legal_basis == file_recipe.defaults.legal_basis
    assert out.connector_profile == file_recipe.connector.profile
    assert out.handling == {
        **file_recipe.defaults.handling,
        "units": list(file_recipe.defaults.units),
        "handling_columns": dict(file_recipe.defaults.handling_columns),
    }
    assert out.row_template == file_recipe.row_template
    assert out.unmapped_fields == file_recipe.unmapped_fields
    assert out.deduplicate == file_recipe.deduplicate
    # the commit is `build_recipe`'s, with its pipeline, at the draft's version
    ((_, (committed_id, committed_version, data)),) = [e for e in log if e[0] == "commit"]
    assert committed_id == "pid-intel-reports" and committed_version == 3
    committed = yaml.safe_load(data)
    assert committed["version"] == 3
    assert [n["kind"] for n in committed["pipeline"]["nodes"]] == ["domain_model", "source"]
    pins = pack_versions_for(out.pipeline, out.row_template, ONTOLOGY)  # type: ignore[arg-type]
    expected = build_recipe(
        out.model_copy(update={"status": StudioRecipeStatus.DRAFT}),
        ontology_version=ONTOLOGY.version, pack_versions=pins,
        schedule_cron=None, schedule_watch=None,
    )  # fmt: skip
    assert data.decode() == serialise_recipe(expected)
    publish = dict(log)["publish"]
    assert publish["git_path"] == "recipes/pid-intel-reports.yaml"
    assert publish["schedule_cron"] is None and publish["schedule_watch"] is None
    assert publish["ontology_version"] == ONTOLOGY.version and publish["pack_versions"] == pins
    audit = dict(log)["audit"]
    assert audit["action"] == "publish_studio_recipe" and audit["principal"] is _persona()
    query = audit["resolved_query"]
    assert query["recipe_id"] == "pid-intel-reports"
    assert query["git_path"] == "recipes/pid-intel-reports.yaml"
    assert audit["result_cardinality"] == 1


async def test_the_fallback_refuses_a_pipeline_the_runner_cannot_run_before_anything_is_written(
    tmp_path: Path,
) -> None:
    source = "/ingest/uploaded/prison-intelligence/" + pid_files.REPORTS
    bad = seed_pid.starting_pipeline(source).model_copy(update={"nodes": [
        *seed_pid.starting_pipeline(source).nodes,
        PipelineNode(id="x", kind=PipelineNodeKind.EXTRACT, label="Names",
                     config={"library": "not-a-library"}),
    ]})  # fmt: skip
    log: list[tuple[str, Any]] = []
    store = _FakeRecipeStore(_draft_row(3, pipeline=bad), log)
    with pytest.raises(seed_pid.SeedRefusal, match="not-a-library"):
        await seed_pid.publish_reports_fallback(
            store,
            _persona(),
            **_fallback_kwargs(log, tmp_path),  # type: ignore[arg-type]
        )
    assert log == [], "no write, no commit, no flip, no audit entry"


async def test_the_fallback_refuses_when_the_row_does_not_agree_with_the_file_after_its_writes(
    tmp_path: Path,
) -> None:
    """The store keeps what the engineer set (a legal basis it will not overwrite): the committed
    file and the row would then differ, so nothing is committed."""
    log: list[tuple[str, Any]] = []
    store = _FakeRecipeStore(_draft_row(3), log, ignore={"legal_basis"})
    with pytest.raises(seed_pid.SeedRefusal, match="legal_basis"):
        await seed_pid.publish_reports_fallback(
            store,
            _persona(),
            **_fallback_kwargs(log, tmp_path),  # type: ignore[arg-type]
        )
    assert "commit" not in [n for n, _ in log] and "publish" not in [n for n, _ in log]
    assert "audit" not in [n for n, _ in log]


async def test_the_fallback_refuses_a_recipe_that_is_not_a_draft(tmp_path: Path) -> None:
    log: list[tuple[str, Any]] = []
    store = _FakeRecipeStore(_draft_row(2, status=StudioRecipeStatus.PUBLISHED), log)
    with pytest.raises(seed_pid.SeedRefusal, match="published"):
        await seed_pid.publish_reports_fallback(
            store,
            _persona(),
            **_fallback_kwargs(log, tmp_path),  # type: ignore[arg-type]
        )
    assert log == []


def test_the_fallback_says_what_it_skips() -> None:
    said = seed_pid.FALLBACK_SKIPS.lower()
    for phrase in ("role", "editor", "verify"):
        assert phrase in said, phrase


# --- refusals, by name ----------------------------------------------------------------------------


def _every_refusal() -> list[Exception]:
    from services.api.datasets import DatasetRefusedError
    from services.api.document_content import UploadRefusedError
    from services.api.studio_map import HandlingLoosenedError
    from services.api.studio_publish import GitCommitError, RecipeNotRunnableError
    from services.api.studio_recipes import (
        SeededRecipeAnotherPublished,
        SeededRecipeNoLegalBasis,
        SeededRecipePinsDiffer,
        SourceDeclarationsInvalidError,
        StudioRecipeNotADraftError,
        StudioRecipeNotFoundError,
        StudioRecipeNotVerifiedError,
    )
    from services.extract.writer import NodeNotFoundError
    from services.ingest.engine import StaleRecipeError
    from services.ingest.recipe_rules import RecipeRuleError

    return [
        seed_pid.SeedRefusal("a refusal"), seed_pid.GuardRefused("a guard"),
        SeededRecipeContentDiffers("differs"), SeededRecipePinsDiffer("pins"),
        SeededRecipeNoLegalBasis("basis"), SeededRecipeAnotherPublished("another"),
        StaleRecipeError("stale"), RecipeRuleError(["a rule"]),
        HandlingLoosenedError("UNKNOWN", "OFFICIAL"),
        SourceDeclarationsInvalidError("units"), UploadRefusedError("upload"),
        NodeNotFoundError("node"), StudioRecipeNotFoundError("row"),
        StudioRecipeNotADraftError("draft"), StudioRecipeNotVerifiedError("verified"),
        RecipeNotRunnableError("r", StudioRecipeStatus.DRAFT), GitCommitError("git"),
        DatasetRefusedError("dataset"),
    ]  # fmt: skip


@pytest.mark.parametrize("mode", ["seed", "reset", "fallback"])
def test_every_refusal_is_printed_by_name_with_a_non_zero_exit(
    mode: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    flags = {"seed": [], "reset": ["--reset-live"], "fallback": ["--publish-reports-fallback"]}[
        mode
    ]
    for refusal in _every_refusal():

        async def raising(*a: Any, **k: Any) -> int:
            raise refusal

        monkeypatch.setattr(
            seed_pid, {"seed": "_seed", "reset": "_reset", "fallback": "_fallback"}[mode], raising
        )
        code = seed_pid.main(["--case-name", "X", "--grant", "a=author", *flags])
        captured = capsys.readouterr()
        assert code == 1, type(refusal).__name__
        assert type(refusal).__name__ in captured.err, (type(refusal).__name__, captured.err)
        assert "Traceback" not in captured.err


def test_a_bug_is_not_a_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the refusals the seed can meet are caught and named; an `AttributeError` is a defect and
    reaches the operator as one."""

    async def broken(*a: Any, **k: Any) -> int:
        raise AttributeError("a defect")

    monkeypatch.setattr(seed_pid, "_seed", broken)
    with pytest.raises(AttributeError):
        seed_pid.main(["--case-name", "X", "--grant", "a=author"])


def test_two_cases_of_one_name_are_refused() -> None:
    assert seed_pid.one_case([], "Prison") is None
    assert seed_pid.one_case(["c1"], "Prison") == "c1"
    with pytest.raises(seed_pid.SeedRefusal, match="2 cases") as refused:
        seed_pid.one_case(["c1", "c2"], "Prison")
    assert "Prison" in str(refused.value) and "c1" in str(refused.value)


# --- the seed end to end over fakes (the wiring `_seed_into` does) -------------------------------


class _Registry:
    """The registry's methods the seed calls, each answering what it was given."""

    def __init__(self, log: list[tuple[str, Any]]) -> None:
        self.log = log

    async def check_seeded_row(self, recipe: Recipe, **kw: Any) -> None:
        self.log.append(("compare", recipe.id))

    async def enter_published_for_seed(self, recipe: Recipe, **kw: Any) -> Any:
        self.log.append(("enter", recipe.id))
        return SimpleNamespace(recipe_id=recipe.id, version=recipe.version)

    async def enter_draft_for_seed(self, recipe: Recipe, **kw: Any) -> Any:
        self.log.append(("draft", recipe.id))
        return SimpleNamespace(recipe_id=recipe.id, version=recipe.version)

    async def get(self, recipe_id: str) -> Any:
        return SimpleNamespace(
            status=StudioRecipeStatus.DRAFT, version=1, row_template=None, recipe_id=recipe_id
        )


class _RunLedger:
    def __init__(self, standing: list[LoadRecord] | None = None) -> None:
        self.standing = standing or []

    async def unreverted_loads(self, case: str, recipe_ids: Sequence[str]) -> list[LoadRecord]:
        return [r for r in self.standing if r.recipe_id in recipe_ids]

    async def for_recipe(self, recipe_id: str, *, limit: int = 50) -> list[Any]:
        return [
            _run_row(r.load_id, r.recipe_id, read=10, case=CASE)
            for r in self.standing
            if r.recipe_id == recipe_id
        ]


def _wire_the_seed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, graph: PlanGraph, ledger: _RunLedger
) -> tuple[Any, Any, list[tuple[str, Any]]]:
    """The seed's own wiring (`_seed_into`) with the stores replaced: every file has ten rows and
    every run reads ten; the graph is the plan as stored. Returns the arguments `_seed_into` takes
    and the log of what was written."""
    log: list[tuple[str, Any]] = []
    files = {stage.file: 10 for stage in pid_files.SEED_ORDER}

    async def scope_for(args: Any, **kw: Any) -> str:
        return CASE

    async def scope_to_case(principal: Principal, case: str, store: Any) -> Principal:
        return principal.model_copy(update={"datasets": [PID.id]})

    async def run_recipe_as(
        deps: Any, *, recipe: Any, source_location: str, **kw: Any
    ) -> LoadReport:
        log.append(("run", Path(source_location).name))
        return LoadReport(
            load_id=f"load-{len(log)}", recipe_id=recipe.recipe_id, recipe_version=recipe.version,
            rows_read=10, nodes_created=1,
        )  # fmt: skip

    async def commit(recipe_id: str, data: bytes, *, version: int, repo_root: Path) -> str:
        log.append(("commit", recipe_id))
        return f"recipes/{recipe_id}.yaml"

    class Pictures:
        def __init__(self, *args: Any, **kw: Any) -> None: ...

        async def attach_for_seed(
            self, case: str, node_id: str, principal: Principal, **kw: Any
        ) -> bool:
            log.append(("picture", Right.EDIT_GRAPH in rights_for(principal.roles)))
            return True

    # ADR-128: the brief step's own stores (Postgres) are replaced; its logic is `test_seed_pid_brief.py`.
    brief_outcome: list[seed_pid.BriefSummary] = [
        seed_pid.BriefSummary(written=True, requirements=4, ok=True)
    ]

    async def require_author_of(case_id: str, persona: Principal) -> None:
        log.append(("author", persona.id))

    async def seed_brief_into(case_id: str, author: Principal, audit: Any) -> seed_pid.BriefSummary:
        log.append(("brief", author.id))
        return brief_outcome[0]

    monkeypatch.setattr(seed_pid, "_require_author_of", require_author_of)
    monkeypatch.setattr(seed_pid, "_seed_brief_into", seed_brief_into)
    monkeypatch.setattr(seed_pid, "scope_for", scope_for)
    monkeypatch.setattr(seed_pid, "scope_to_case", scope_to_case)
    monkeypatch.setattr(seed_pid, "write_listed_files", lambda plan, root: files)
    monkeypatch.setattr(seed_pid, "run_recipe_as", run_recipe_as)
    monkeypatch.setattr(seed_pid, "commit_recipe_file", commit)
    monkeypatch.setattr(seed_pid, "WorkingSetService", lambda *a, **k: None)
    monkeypatch.setattr(seed_pid, "ValkeyWorkingSetStore", lambda *a, **k: None)
    monkeypatch.setattr(seed_pid, "EntityPictureService", Pictures)
    queue = _Queue()
    resources = SimpleNamespace(
        ontology=ONTOLOGY, handling_scheme=SCHEME, datasets_store=None, recipe_runs=ledger,
        graph=graph, valkey=None, media=None, audit=None, run_deps=lambda: _deps_with(queue),
        brief_outcome=brief_outcome,
    )  # fmt: skip
    return resources, _Registry(log), log


async def test_the_seed_runs_end_to_end_over_fakes_and_prints_its_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    resources, registry, log = _wire_the_seed(
        monkeypatch, tmp_path, PlanGraph(PLAN, "seed"), _RunLedger()
    )
    code = await seed_pid._seed_into(
        _seed_args(), _root(tmp_path), resources, registry, tmp_path / "repo", seed_pid.engineer()
    )
    out = capsys.readouterr().out
    assert code == 0, out
    assert [e for n, e in log if n == "run"] == [s.file for s in pid_files.seed_stages("seed")]
    assert [n for n, _ in log if n == "commit"] == ["commit"] * 16, "every recipe but the reports'"
    pictured = [edit for n, edit in log if n == "picture"]
    assert len(pictured) == len(PLAN.picture_subjects) and all(pictured), (
        "every picture is attached with the edit right"
    )
    assert "pictures:" in out and "check ok: J1" in out and "check not run: Ch5" in out
    assert "Take a backup now" in out and seed_pid.BACKUP_COMMAND in out, "advice, with the command"
    assert seed_pid.RESTORE_COMMAND in out
    assert "check FAILED" not in out and "at the seed moment" in out
    assert f"as {seed_pid.ENGINEER_USERNAME}" in out


async def test_the_seed_confirms_the_author_before_any_write_then_writes_the_brief_and_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """ADR-128 decision 3 and Amendment 4: the brief is written as the case's author, the account
    the seed grants author. The author is confirmed first
    (before a recipe is committed or a file run) and the brief is written once the loads are in."""
    resources, registry, log = _wire_the_seed(
        monkeypatch, tmp_path, PlanGraph(PLAN, "seed"), _RunLedger()
    )
    code = await seed_pid._seed_into(
        _seed_args(), _root(tmp_path), resources, registry, tmp_path / "repo", seed_pid.engineer()
    )
    out = capsys.readouterr().out
    names = [n for n, _ in log]
    assert code == 0, out
    assert names.count("author") == 1 and names.count("brief") == 1
    assert names.index("author") < names.index("commit") < names.index("run") < names.index("brief")
    # Amendment 4: as the account the seed's grants make Author (`a`), not the engineer who runs
    # it, whom the pack makes an Editor (ADR-113 decision 8).
    assert dict(log)["brief"] == "a" == dict(log)["author"]
    assert "case brief: the priority requirement and 4 information requirements written" in out
    assert "check ok: the case holds a brief" in out


async def test_a_brief_that_is_not_there_makes_the_seed_exit_non_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    resources, registry, _ = _wire_the_seed(
        monkeypatch, tmp_path, PlanGraph(PLAN, "seed"), _RunLedger()
    )
    resources.brief_outcome[0] = seed_pid.BriefSummary(written=True, requirements=0, ok=False)
    code = await seed_pid._seed_into(
        _seed_args(), _root(tmp_path), resources, registry, tmp_path / "repo", seed_pid.engineer()
    )
    out = capsys.readouterr().out
    assert code == 1 and "check FAILED: the case holds a brief" in out
    assert "check ok: J2" in out, "the others are still said"


async def test_a_persona_who_is_not_the_author_stops_the_seed_before_a_recipe_or_a_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    resources, registry, log = _wire_the_seed(
        monkeypatch, tmp_path, PlanGraph(PLAN, "seed"), _RunLedger()
    )

    async def not_the_author(case_id: str, persona: Principal) -> None:
        raise seed_pid.SeedRefusal(f"{persona.id} is not the Author of case {case_id}")

    monkeypatch.setattr(seed_pid, "_require_author_of", not_the_author)
    with pytest.raises(seed_pid.SeedRefusal):
        await seed_pid._seed_into(
            _seed_args(),
            _root(tmp_path),
            resources,
            registry,
            tmp_path / "repo",
            seed_pid.engineer(),
        )
    assert [n for n, _ in log if n in {"commit", "run", "compare", "enter", "draft", "brief"}] == []


async def test_a_failed_demo_number_makes_the_seed_exit_non_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    graph = PlanGraph(PLAN, "seed")
    graph.drop_edges("VISITED", "outside_1", "principal")
    resources, registry, _ = _wire_the_seed(monkeypatch, tmp_path, graph, _RunLedger())
    code = await seed_pid._seed_into(
        _seed_args(), _root(tmp_path), resources, registry, tmp_path / "repo", seed_pid.engineer()
    )
    out = capsys.readouterr().out
    assert code == 1 and "check FAILED: J1" in out
    assert "check ok: J2" in out, "the others are still said"


async def test_a_reseed_reports_each_standing_load_and_runs_nothing_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _root(tmp_path)
    standing = [
        _record(f"L{i}", r.recipe_id, r.source, r.version) for i, r in enumerate(_resolved(root))
    ]
    resources, registry, log = _wire_the_seed(
        monkeypatch, tmp_path, PlanGraph(PLAN, "seed"), _RunLedger(standing)
    )
    code = await seed_pid._seed_into(
        _seed_args(), root, resources, registry, tmp_path / "repo", seed_pid.engineer()
    )
    out = capsys.readouterr().out
    assert code == 0, out
    assert not [n for n, _ in log if n == "run"], "a second seed reads nothing"
    assert (
        out.count("already loaded, not read again; its run: 10 rows read, 0 rejected, 0 held") == 15
    )
    assert "check ok: " in out and "check FAILED" not in out


# --- the inferred links the loads leave out (the plan's "graph port" shapes) --------------------


def _graph_port_links() -> list[pid_plan.PlanLink]:
    return [lk for lk, _ in seed_pid.inferred_links(PLAN, created_at=NOW)]


async def _seed_the_inferred(graph: PlanGraph) -> seed_pid.InferredSummary:
    async def find(entity_type: str, identifier: str, value: str) -> Any:
        return await graph.find_node(entity_type, identifier, value, _persona())

    async def present(source: str, link_type: str, target: str) -> bool:
        star = await graph.expand(
            ExpandRequest(node_ids=[source], depth=1, edge_types=[link_type], direction="out"),
            _persona(),
        )
        return any(e.source == source and e.target == target for e in star.edges)

    async def write(edges: Sequence[Any]) -> None:
        await graph.upsert_edges(edges, await graph.begin_transaction())

    return await seed_pid.seed_inferred_links(
        PLAN, find=find, present=present, write=write, now=NOW
    )


def test_the_graph_port_links_are_the_plans_inferred_ones() -> None:
    links = _graph_port_links()
    assert links and {lk.link_type for lk in links} == {"PASSES_ITEMS_TO"}
    assert all(lk.provenance == "inferred" for lk in links)
    assert len(links) == pid_plan.PRINCIPAL_LINKS_BY_TYPE["PASSES_ITEMS_TO"] or len(links) >= 3


async def test_the_seed_writes_the_plans_graph_port_links_inferred_and_a_second_seed_none() -> None:
    graph = PlanGraph(PLAN, "seed")
    planned = _graph_port_links()
    graph.drop_edges("PASSES_ITEMS_TO")
    first = await _seed_the_inferred(graph)
    assert first.written == len(planned) and first.present == 0 and first.ok
    stored = [e for e in graph.edges if e.type == "PASSES_ITEMS_TO"]
    assert len(stored) == len(planned)
    for edge in stored:
        assert edge.provenance.state is ProvenanceState.INFERRED
        assert edge.provenance.extracted_by and edge.provenance.extraction_confidence is not None
        assert edge.audit.created_by == seed_pid.ENGINEER_USERNAME
        assert edge.handling.classification == "OFFICIAL"
    second = await _seed_the_inferred(graph)
    assert (second.written, second.present) == (0, len(planned))
    assert len([e for e in graph.edges if e.type == "PASSES_ITEMS_TO"]) == len(planned)
    said = "\n".join(seed_pid.inferred_lines(first))
    assert f"{len(planned)} inferred link(s) written, 0 already present" in said


async def test_an_inferred_link_whose_end_is_not_stored_is_named_and_fails() -> None:
    graph = PlanGraph(PLAN, "seed")
    link = _graph_port_links()[0]
    graph.drop_edges("PASSES_ITEMS_TO")
    graph.drop_node(link.target)
    summary = await _seed_the_inferred(graph)
    assert not summary.ok and any(link.target in m for m in summary.missing)
    assert "check FAILED" in "\n".join(seed_pid.inferred_lines(summary))


async def test_a_seed_over_loaded_stages_still_writes_the_missing_inferred_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _root(tmp_path)
    standing = [
        _record(f"L{i}", r.recipe_id, r.source, r.version) for i, r in enumerate(_resolved(root))
    ]
    graph = PlanGraph(PLAN, "seed")
    graph.drop_edges("PASSES_ITEMS_TO")
    resources, registry, log = _wire_the_seed(monkeypatch, tmp_path, graph, _RunLedger(standing))
    code = await seed_pid._seed_into(
        _seed_args(), root, resources, registry, tmp_path / "repo", seed_pid.engineer()
    )
    out = capsys.readouterr().out
    assert not [n for n, _ in log if n == "run"], "every stage was loaded already"
    assert code == 0, out
    assert f"{len(_graph_port_links())} inferred link(s) written, 0 already present" in out
    assert "check ok: J1" in out, "J1 counts them"


async def test_without_the_inferred_links_the_principals_count_is_short_and_the_seed_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The plant that found it: the step does nothing, and J1 (45 in the plan) counts 42."""
    graph = PlanGraph(PLAN, "seed")
    graph.drop_edges("PASSES_ITEMS_TO")
    resources, registry, _ = _wire_the_seed(monkeypatch, tmp_path, graph, _RunLedger())

    async def nothing(plan: Any, **kw: Any) -> seed_pid.InferredSummary:
        return seed_pid.InferredSummary()

    monkeypatch.setattr(seed_pid, "seed_inferred_links", nothing)
    code = await seed_pid._seed_into(
        _seed_args(), _root(tmp_path), resources, registry, tmp_path / "repo", seed_pid.engineer()
    )
    out = capsys.readouterr().out
    assert code == 1 and "check FAILED: J1" in out and "PASSES_ITEMS_TO" in out


async def test_a_second_seed_over_a_case_that_has_them_writes_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    resources, registry, _ = _wire_the_seed(
        monkeypatch, tmp_path, PlanGraph(PLAN, "seed"), _RunLedger()
    )
    code = await seed_pid._seed_into(
        _seed_args(), _root(tmp_path), resources, registry, tmp_path / "repo", seed_pid.engineer()
    )
    out = capsys.readouterr().out
    assert (
        code == 0
        and f"0 inferred link(s) written, {len(_graph_port_links())} already present" in out
    )


def test_the_reset_chooses_no_load_that_holds_an_inferred_link() -> None:
    """Inferred links are in no load record (the seed writes them itself), and the reset reverts
    loads of the reports, their incident links and batch 2 only: it never touches them."""
    kinds = {r.recipe_id for r in seed_pid.choose_reset(_loads())}
    assert kinds <= {
        seed_pid.reports_recipe_id(),
        seed_pid.incidents_recipe_id(),
        seed_pid.comms_recipe_id(),
    }


# --- the resolution switch, checked (Amendment 34) ----------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, True), ("", True), ("on", True), ("ON", True), ("off", False), (" Off ", False)],
)
def test_the_switch_is_read_as_the_conduit_reads_it(value: str | None, expected: bool) -> None:
    environ = {} if value is None else {SWITCH: value}
    assert seed_pid.resolution_is_on(environ) is expected


def test_a_switch_the_conduit_would_refuse_is_refused() -> None:
    with pytest.raises(seed_pid.SeedRefusal, match=SWITCH):
        seed_pid.resolution_is_on({SWITCH: "maybe"})


def test_the_warning_names_the_osprey_yaml_line_and_the_re_render() -> None:
    text = "\n".join(seed_pid.resolution_warning())
    assert "components.post_ingest_resolution: false" in text
    assert "ospreyflow install" in text and "restart" in text.lower()
    assert "SAME_AS" in text


def test_release_and_reset_refuse_while_resolution_is_on_and_go_on_when_it_is_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _root(tmp_path)
    _seed_folder(root, batch_two=False)
    monkeypatch.setenv(SWITCH, "on")
    assert seed_pid.main(["--release-batch-2", "--ingest-root", str(root)]) == 1
    err = capsys.readouterr().err
    assert "components.post_ingest_resolution: false" in err and "SeedRefusal" in err
    assert not (seed_pid.listed_folder(root) / pid_files.BATCH_2).exists(), "nothing released"
    monkeypatch.setenv(SWITCH, "off")
    assert seed_pid.main(["--release-batch-2", "--ingest-root", str(root)]) == 0


async def test_the_reset_refuses_while_resolution_is_on_before_it_opens_anything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(SWITCH, "on")
    args = seed_pid.parse_args(["--reset-live", "--case-name", "X"])
    with pytest.raises(seed_pid.SeedRefusal, match="components.post_ingest_resolution"):
        await seed_pid._reset(args, _root(tmp_path))  # would fail on a missing config otherwise


async def test_the_seed_and_check_warn_while_resolution_is_on_and_say_nothing_when_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for value, warned in (("on", True), ("off", False)):
        monkeypatch.setenv(SWITCH, value)
        resources, registry, _ = _wire_the_seed(
            monkeypatch, tmp_path, PlanGraph(PLAN, "seed"), _RunLedger()
        )
        code = await seed_pid._seed_into(
            _seed_args(), _root(tmp_path), resources, registry, tmp_path / "repo",
            seed_pid.engineer(),
        )  # fmt: skip
        assert code == 0, "a warning, not a failure"
        assert ("components.post_ingest_resolution: false" in capsys.readouterr().out) is warned
    code = await seed_pid.check_case(
        graph=PlanGraph(PLAN, "seed"), ledger=_RunLedger(), principal=_persona(), plan=PLAN,
        case_id=CASE, say=print, resolution_on=True,
    )  # fmt: skip
    assert code == 0 and "components.post_ingest_resolution: false" in capsys.readouterr().out


# --- loads in the engineer's own id (Amendment 34) -----------------------------------------


def test_run_as_is_an_argument_and_the_username_is_the_default_and_says_so() -> None:
    assert seed_pid.parse_args(["--case-name", "X", "--grant", "a=author"]).run_as is None
    args = seed_pid.parse_args(["--case-name", "X", "--grant", "a=author", "--run-as", "kc-1"])
    assert args.run_as == "kc-1"
    assert "kc-1" in seed_pid.run_as_line("kc-1")
    local = seed_pid.run_as_line(seed_pid.ENGINEER_USERNAME, given=False)
    assert "username" in local and seed_pid.ENGINEER_USERNAME in local


async def test_every_write_of_the_seed_carries_the_id_it_was_told_to_run_as(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The run's principal, the recipe rows' published_by and created_by, the picture principal and
    the inferred links' creator: one id, the engineer's, never the username when told another."""
    graph = PlanGraph(PLAN, "seed")
    graph.drop_edges("PASSES_ITEMS_TO")
    resources, registry, log = _wire_the_seed(monkeypatch, tmp_path, graph, _RunLedger())
    seen: dict[str, set[str]] = {"runs": set(), "pictures": set(), "published_by": set()}
    real_enter = registry.enter_published_for_seed

    async def enter(recipe: Recipe, **kw: Any) -> Any:
        seen["published_by"].add(kw["published_by"])
        return await real_enter(recipe, **kw)

    async def draft(recipe: Recipe, **kw: Any) -> Any:
        seen["published_by"].add(kw["created_by"])
        return SimpleNamespace(recipe_id=recipe.id, version=1)

    registry.enter_published_for_seed = enter  # type: ignore[method-assign]
    registry.enter_draft_for_seed = draft  # type: ignore[method-assign]

    async def run_recipe_as(
        deps: Any, *, principal: Principal, recipe: Any, **kw: Any
    ) -> LoadReport:
        seen["runs"].add(principal.id)
        return LoadReport(load_id="l", recipe_id=recipe.recipe_id, recipe_version=1, rows_read=10)

    class Pictures:
        def __init__(self, *a: Any, **k: Any) -> None: ...

        async def attach_for_seed(
            self, case: str, node: str, principal: Principal, **kw: Any
        ) -> bool:
            seen["pictures"].add(principal.id)
            return True

    monkeypatch.setattr(seed_pid, "run_recipe_as", run_recipe_as)
    monkeypatch.setattr(seed_pid, "EntityPictureService", Pictures)
    code = await seed_pid._seed_into(
        _seed_args(), _root(tmp_path), resources, registry, tmp_path / "repo",
        seed_pid.engineer("verify", "kc-sub-1234"),
    )  # fmt: skip
    out = capsys.readouterr().out
    assert code == 0, out
    assert seen == {
        "runs": {"kc-sub-1234"},
        "pictures": {"kc-sub-1234"},
        "published_by": {"kc-sub-1234"},
    }
    assert [e.audit.created_by for e in graph.edges if e.type == "PASSES_ITEMS_TO"] == [
        "kc-sub-1234"
    ] * len([1 for e in graph.edges if e.type == "PASSES_ITEMS_TO"])
    assert "kc-sub-1234" in out


async def test_the_reset_reverts_and_restores_the_draft_as_the_id_it_runs_as(
    tmp_path: Path,
) -> None:
    reverted_by: list[str] = []
    world, said = _ResetWorld(_loads()), []

    async def revert(load_id: str, *, reverted_by: str, deps: Any, now: datetime) -> Any:
        seen.append(reverted_by)
        return RevertResult()

    seen = reverted_by
    _seed_folder(_root(tmp_path))
    args = _reset_args(tmp_path, world, said) | {
        "revert": revert,
        "worker": seed_pid.engineer("verify", "kc-sub-1234"),
    }
    assert await seed_pid.reset_live(**args) == 0
    assert set(reverted_by) == {"kc-sub-1234"} and len(reverted_by) == 5


# --- an interrupted stage (Amendment 34) ---------------------------------------------------


def test_a_latest_run_that_failed_over_a_standing_load_is_interrupted_not_missing() -> None:
    record = _record("L1", "r", "/x.csv")
    failed = _run_row("L2", "r", read=0, outcome="failed")
    failed.failure = "ArcadeDBError: Remote transaction session not found or expired"
    found = seed_pid.pick_standing_run([failed], record)
    assert isinstance(found, seed_pid.Interrupted)
    assert found.load_id == "L1" and "session not found" in found.failure
    # a failed run in another case, or an older failure under a newer success, is not one
    other = _run_row("L2", "r", read=0, outcome="failed", case="another-case")
    assert seed_pid.pick_standing_run([other], record) is None
    newer = _run_row("L1", "r", read=10)
    assert seed_pid.pick_standing_run([newer, failed], record) == seed_pid.StandingRun(10, 0, 0)


async def test_an_interrupted_stage_is_reported_with_the_revert_command_and_fails_the_checks(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    resolved = _resolved(root)
    loaded = [_record(f"L{i}", r.recipe_id, r.source, r.version) for i, r in enumerate(resolved)]

    async def standing_of(record: LoadRecord) -> Any:
        if record.load_id == "L11":
            return seed_pid.Interrupted(record.load_id, "ArcadeDBError: session expired")
        return seed_pid.StandingRun(rows_read=10, rejected=0, held=0)

    results = await seed_pid.run_stages(resolved, loaded, run=_Runner(), standing_of=standing_of)
    summary = "\n".join(seed_pid.summary_lines(results, run_as="kc-sub-1234"))
    line = next(x for x in summary.splitlines() if resolved[11].stage.file in x)
    assert "INTERRUPTED" in line and "session expired" in line
    assert "python -m scripts.revert_load L11 --reverted-by kc-sub-1234" in line
    lines, ok = seed_pid.check_lines(results, {r.stage.file: 10 for r in resolved})
    assert not ok and sum("FAILED" in x for x in lines) == 1
    # after that revert the ledger no longer lists the load, and a reseed loads the stage again
    after = [r for r in loaded if r.load_id != "L11"]
    runner = _Runner()
    again = await seed_pid.run_stages(resolved, after, run=runner, standing_of=standing_of)
    assert runner.ran == [resolved[11].stage.file]
    assert [r.skipped for r in again].count(False) == 1


# --- the fallback checks before it writes, and says what it attested (Amendment 34) ---------------


async def test_the_fallback_refuses_a_draft_that_is_not_the_seeds_before_any_write(
    tmp_path: Path,
) -> None:
    log: list[tuple[str, Any]] = []
    store = _FakeRecipeStore(_draft_row(3, dataset_id="another-dataset"), log)
    with pytest.raises(seed_pid.SeedRefusal, match="another-dataset"):
        await seed_pid.publish_reports_fallback(
            store,
            _persona(),
            **_fallback_kwargs(log, tmp_path),  # type: ignore[arg-type]
        )
    assert log == [], "nothing was written, committed, verified or audited"
    log = []
    store = _FakeRecipeStore(_draft_row(3, label="An engineer's own label"), log)
    with pytest.raises(seed_pid.SeedRefusal, match="label"):
        await seed_pid.publish_reports_fallback(
            store,
            _persona(),
            **_fallback_kwargs(log, tmp_path),  # type: ignore[arg-type]
        )
    assert log == []


async def test_the_fallbacks_audit_entry_records_the_verify_it_did_not_run(tmp_path: Path) -> None:
    log: list[tuple[str, Any]] = []
    store = _FakeRecipeStore(_draft_row(3), log)
    await seed_pid.publish_reports_fallback(
        store,
        _persona(),
        **_fallback_kwargs(log, tmp_path),  # type: ignore[arg-type]
    )
    query = dict(log)["audit"]["resolved_query"]
    assert query["recipe_id"] == "pid-intel-reports" and query["git_path"]
    assert query["verified_by"] == "operator's attestation"
    assert "no Verify" in query["verified_note"]


# --- the refusals the engine can give, and the lists that say their totals ------------------------


@pytest.mark.parametrize("name", ["RowKeyDefinitionChanged", "RowKeyRunInProgress"])
def test_the_engines_row_key_refusals_are_named_refusals(
    name: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from services.ingest import engine

    refusal = getattr(engine, name)
    assert refusal in seed_pid.REFUSALS

    async def raising(*a: Any, **k: Any) -> int:
        raise refusal("the keys were made under another definition")

    monkeypatch.setattr(seed_pid, "_seed", raising)
    assert seed_pid.main(["--case-name", "X", "--grant", "a=author"]) == 1
    assert name in capsys.readouterr().err


async def test_every_shortened_list_gives_its_total() -> None:
    fake = _Pictures(missing={seed_pid.identity_of(PLAN, k)[2] for k in PLAN.picture_subjects[:9]})
    summary = await seed_pid.seed_pictures(_plan_of(12), find=fake.find, attach=fake.attach)
    text = "\n".join(seed_pid.picture_lines(summary, 12))
    assert "9 subject(s) no reference found" in text and "first 5 of 9" in text
    refused = seed_pid.PictureSummary(
        refused=[(f"k{i}", "UploadRefusedError: no") for i in range(8)]
    )
    text = "\n".join(seed_pid.picture_lines(refused, 8))
    assert "first 5 of 8" in text and text.count("refused k") == 5
    missing = seed_pid.InferredSummary(missing=[f"PASSES_ITEMS_TO a{i} -> b" for i in range(7)])
    text = "\n".join(seed_pid.inferred_lines(missing))
    assert "first 5 of 7" in text


def test_the_stale_wording_is_corrected() -> None:
    doc = seed_pid.reset_live.__doc__ or ""
    assert "reseed" not in doc.lower() and "restore" in doc.lower()
    from services.ingest import load_revert

    links = load_revert.links_resting_on.__doc__ or ""
    assert (
        "before it reverts anything" not in links
        and "so the Prison Intelligence reset" not in links
    )
    guide = (Path(seed_pid.__file__).resolve().parents[1] / "DEMO_GUIDE.md").read_text(
        encoding="utf-8"
    )
    row = next(x for x in guide.splitlines() if x.startswith("| **Prison Intelligence Dataset"))
    assert "each source with its own marking" not in row
    assert "OFFICIAL" in row and "post_ingest_resolution" in row, "now OFFICIAL, and the switch"


# --- `--check`: the demo numbers for the moment the stored loads reach (Amendment 33) -----------


def test_check_is_a_mode_that_needs_a_case() -> None:
    assert seed_pid.parse_args(["--check", "--case-name", "X"]).mode == "check"
    with pytest.raises(SystemExit):
        seed_pid.parse_args(["--check"])
    with pytest.raises(SystemExit):
        seed_pid.parse_args(["--check", "--reset-live", "--case-name", "X"])


def test_check_reads_the_graph_and_postgres_and_never_opens_the_analytics_store() -> None:
    """The checks are the persona's reads of the graph, and the ledger's records of what is loaded.
    `build_run_resources` opens DuckDB, which has one writer: a `--check` that opened it could not
    run with the Conduit up. So it opens the graph, the dataset store and the run ledger and nothing
    else."""
    import inspect

    function = ast.parse(inspect.getsource(seed_pid._check).lstrip()).body[0]
    assert isinstance(function, ast.AsyncFunctionDef)
    function.body = function.body[1:]  # the docstring says what it avoids; the code must not use it
    body = ast.unparse(function)
    assert "build_run_resources" not in body and "analytics" not in body.lower()
    for opened in (
        "ArcadeDBClient",
        "GraphArcadeDBAdapter",
        "RecipeRunStore",
        "PostgresDatasetStore",
    ):
        assert opened in body, opened


@pytest.mark.parametrize("moment", ["seed", "chapter4", "chapter9"])
async def test_check_runs_every_number_for_the_moment_the_stored_loads_reach(
    moment: pid_plan.Moment, capsys: pytest.CaptureFixture[str]
) -> None:
    root = Path("/ingest")
    loads: list[LoadRecord] = []
    if moment != "seed":
        loads += [
            _record("C", seed_pid.reports_recipe_id(), _source(root, pid_files.REPORTS)),
            _record("D", seed_pid.incidents_recipe_id(), _source(root, pid_files.REPORT_INCIDENTS)),
        ]
    if moment == "chapter9":
        loads.append(_record("E", seed_pid.comms_recipe_id(), _source(root, pid_files.BATCH_2)))
    code = await seed_pid.check_case(
        graph=PlanGraph(PLAN, moment), ledger=_RunLedger(loads), principal=_persona(),
        plan=PLAN, case_id=CASE, say=print,
    )  # fmt: skip
    out = capsys.readouterr().out
    assert code == 0, out
    assert f"at the {moment} moment" in out
    for name in ALL_CHECKS:
        assert name in out
    assert ("check ok: Ch5" in out) == (moment != "seed")
    assert "check not run: Ch5" in out or moment != "seed"


async def test_check_exits_non_zero_when_a_number_fails(capsys: pytest.CaptureFixture[str]) -> None:
    graph = PlanGraph(PLAN, "seed")
    graph.drop_edges("VISITED", "outside_1", "principal")
    code = await seed_pid.check_case(
        graph=graph, ledger=_RunLedger(), principal=_persona(), plan=PLAN, case_id=CASE, say=print
    )
    assert code == 1 and "check FAILED: J1" in capsys.readouterr().out


async def test_check_over_a_case_the_reports_loaded_into_fails_when_the_reports_are_not_there(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The ledger says chapter 4 is loaded, the graph holds the seed's data only: the report numbers
    are judged, and fail, rather than skipped."""
    root = Path("/ingest")
    loads = [
        _record("C", seed_pid.reports_recipe_id(), _source(root, pid_files.REPORTS)),
        _record("D", seed_pid.incidents_recipe_id(), _source(root, pid_files.REPORT_INCIDENTS)),
    ]
    code = await seed_pid.check_case(
        graph=PlanGraph(PLAN, "seed"), ledger=_RunLedger(loads), principal=_persona(),
        plan=PLAN, case_id=CASE, say=print,
    )  # fmt: skip
    out = capsys.readouterr().out
    assert code == 1 and "check FAILED: Ch5" in out


# --- the module -----------------------------------------------------------------------------------


def test_importing_the_seed_opens_nothing() -> None:
    import importlib

    for name in [n for n in sys.modules if n == "scripts.seed_pid"]:
        del sys.modules[name]
    module = importlib.import_module("scripts.seed_pid")
    assert callable(module.main)


def test_the_seed_shares_the_reverts_construction_and_does_not_copy_it() -> None:
    text = Path(seed_pid.__file__).read_text(encoding="utf-8")
    assert "build_revert_deps(" in text
    for copied in ("WorkingSetReverter(", "RevertDeps(", "invalidate_every_cache("):
        assert copied not in text, copied


def test_the_seed_shares_the_lifespans_construction_of_the_run() -> None:
    text = Path(seed_pid.__file__).read_text(encoding="utf-8")
    assert "build_run_resources(" in text and ".run_deps()" in text
    assert "RecipeRunDeps(" not in text


def test_each_mode_is_one_of_four_and_a_seed_names_its_case() -> None:
    with pytest.raises(SystemExit):
        seed_pid.parse_args(["--reset-live", "--release-batch-2"])
    with pytest.raises(SystemExit):
        seed_pid.parse_args([])
    args = seed_pid.parse_args(["--case-name", "X", "--grant", "a=author"])
    assert args.mode == "seed" and args.case_name == "X" and args.show_ids is False
    assert seed_pid.parse_args(["--case-name", "X", "--reset-live"]).mode == "reset"
    assert seed_pid.parse_args(["--release-batch-2"]).mode == "release"
    assert (
        seed_pid.parse_args(["--publish-reports-fallback", "--case-name", "X"]).mode == "fallback"
    )
    assert seed_pid.parse_args(["--case-name", "X", "--reset-live", "--show-ids"]).show_ids is True


def test_the_summary_lines_hold_a_count_for_every_recipe_and_the_checks() -> None:
    root = Path("/ingest")
    resolved = [seed_pid.resolve(s, root) for s in seed_pid.stages_to_run()]
    results = [
        seed_pid.StageResult(r, skipped=(i == 0), report=None if i == 0 else LoadReport(
            load_id="l", recipe_id=r.recipe_id, recipe_version=1, rows_read=7, nodes_created=2,
            edges_created=1), seconds=0.5)
        for i, r in enumerate(resolved)
    ]  # fmt: skip
    lines = seed_pid.summary_lines(results)
    text = "\n".join(lines)
    for r in resolved:
        assert r.recipe_id in text
    assert "already loaded" in text and "7 rows read" in text
    assert len(lines) == 15, "a line for each stage of the seed"


# --- the counts the checks wait for ---------------------------------------------------------------


def test_the_plan_constants_the_checks_read_are_the_plans_own() -> None:
    """The names the seed reads exist, so a rename in the plan is found here and not at a demo."""
    for name in (
        "PRINCIPAL_LINK_COUNT",
        "PRINCIPAL_LINK_COUNT_ACT1",
        "TOTAL_THROW_OVERS",
        "YARD_COUNTS",
        "HOTSPOT_YARDS",
        "HOUR_COUNTS",
        "WEEKDAY_COUNTS",
        "REPORTS_SELECTED",
        "REPORTS_USED",
        "REPORT_PATTERN",
    ):
        assert hasattr(pid_plan, name), name
    assert sum(pid_plan.YARD_COUNTS.values()) == pid_plan.TOTAL_THROW_OVERS
    assert Counter(pid_plan.HOTSPOT_YARDS) and set(pid_plan.HOTSPOT_YARDS) <= set(
        pid_plan.YARD_COUNTS
    )


# --- the after-chapter-4 check reads with the ontology applied --------------------------------


async def test_the_check_command_reads_through_a_graph_with_the_deployments_ontology_applied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Found running `--check` on the owner's deployment after chapter 4: J2 and Ch11 could not be
    run ("no ontology schema has been applied"), and Ch5 and S2 read 0 reports, because `_check`
    built its own adapter and never applied the ontology (the seed's comes from
    `build_run_resources`, which does). The checks' other tests run over `PlanGraph`, which needs
    no ontology, so nothing caught it (rule 15)."""
    ontology = object()
    applied: list[object] = []
    handed: list[Any] = []

    class Adapter:
        def __init__(self, client: Any, scheme: Any) -> None:
            pass

        async def apply_schema(self, schema: object) -> None:
            applied.append(schema)

    class Store:
        async def close(self) -> None:
            pass

    class Client:
        def __init__(self, config: Any) -> None:
            pass

        async def aclose(self) -> None:
            pass

    async def find_case(*_: Any) -> str:
        return CASE

    async def connect(_: str) -> Store:
        return Store()

    async def scope(principal: Any, *_: Any) -> Any:
        return principal

    async def check_case(*, graph: Any, **_: Any) -> int:
        handed.append(graph)
        return 0

    monkeypatch.setattr(
        seed_pid.ApiConfig,
        "from_env",
        classmethod(lambda cls: SimpleNamespace(postgres=SimpleNamespace(dsn="x"))),
    )
    monkeypatch.setattr(seed_pid, "_find_case", find_case)
    monkeypatch.setattr(seed_pid, "ArcadeDBClient", Client)
    monkeypatch.setattr(seed_pid.ArcadeDBConfig, "from_env", classmethod(lambda cls, **_: None))
    monkeypatch.setattr(seed_pid.PostgresDatasetStore, "connect", staticmethod(connect))
    monkeypatch.setattr(seed_pid.RecipeRunStore, "connect", staticmethod(connect))
    monkeypatch.setattr(seed_pid, "GraphArcadeDBAdapter", Adapter)
    monkeypatch.setattr(seed_pid, "load_deployment_ontology", lambda: ontology)
    monkeypatch.setattr(seed_pid, "scope_to_case", scope)
    monkeypatch.setattr(seed_pid, "check_case", check_case)

    assert await seed_pid._check(seed_pid.parse_args(["--case-name", "X", "--check"])) == 0
    assert len(handed) == 1 and applied == [ontology], "the checks' graph has the ontology applied"
