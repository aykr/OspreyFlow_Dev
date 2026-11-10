"""L1.10b's red-then-green record (rules 12 and 15), as L1.10's: each plant is one exact edit to the
code under test; the script applies it, runs the named test files, restores the file byte for byte
and writes `red-<n>-<slug>.txt`, headed by the commit, the plant and the command. A plant may name
the reason each named test must fail with, found on that test's own FAILED line.

Run from OspreyFlow_Core with the closed offline ports pinned (no stack):
    .venv/bin/python ../OspreyFlow_Build/process/lanes/studio-b/l1.10b/red_plants.py
"""

from __future__ import annotations

# ruff: noqa: E501  (each plant is an exact line of the code under test)
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE.parents[4] / "OspreyFlow_Core"
PIPELINE = CORE / "services/api/pipeline_run.py"
STAGED = CORE / "services/ingest/staged_run.py"
VERIFY = CORE / "services/api/studio_verify.py"
ENGINE = CORE / "services/ingest/engine.py"
SEEDS = CORE / "scripts/seed_internal.py"
PID_PLAN = CORE / "packages/demo_fixtures/pid_plan.py"
LEDGER = CORE / "packages/demo_fixtures/ledger.py"
HMP = CORE / "packages/demo_fixtures/hmp_network.py"
HMP_EVENTS = CORE / "packages/demo_fixtures/hmp.py"
CORP = CORE / "packages/demo_fixtures/fixture_corp.py"
ENRON = CORE / "scripts/seed_enron.py"
TABLES = "../OspreyFlow_Build/tests/services/api/test_deployment_ceiling_staged.py"
PACKS = "../OspreyFlow_Build/tests/test_seed_internal_ceiling.py"
VERIFYING = "../OspreyFlow_Build/tests/services/api/test_deployment_ceiling_verify.py"

DRY_RUN_CHECK = (
    "    refuse_rows_above_the_ceiling(\n"
    "        recipe, sample, ceiling if ceiling is not None else DeploymentCeiling.from_env()\n"
    "    )\n"
)
WHOLE_FILE_CHECK = "        refuse_rows_above_the_ceiling(recipe, all_rows, DeploymentCeiling.from_env())\n"
REMOVAL = "        await asyncio.to_thread(remove_step_tables, prepared, storage)\n        raise\n"

#: (slug, what, [(file, old, new)], test files, the tests that must go red, the reason or None)
PLANTS = [
    ("branch-keeps-tables", "the pipeline's staged branch leaves its step tables on the refusal",
     [(PIPELINE, REMOVAL + "    finish_staged_report(branch, prepared)",
       "        raise\n    finish_staged_report(branch, prepared)")],
     [TABLES], ["test_a_staged_run_refused_at_the_ceiling_leaves_no_step_table"],
     "a refused run left its step tables behind"),
    ("engine-keeps-tables", "the staged engine's own load leaves its step tables on the refusal",
     [(STAGED, REMOVAL + "    finish_staged_report(report, prepared)",
       "        raise\n    finish_staged_report(report, prepared)")],
     [TABLES], ["test_the_staged_engine_s_own_load_leaves_no_step_table_on_the_refusal"],
     "a refused staged load left its step tables"),
    ("removed-on-success", "a run the ceiling passes loses its step tables too",
     [(PIPELINE, "    finish_staged_report(branch, prepared)\n",
       "    finish_staged_report(branch, prepared)\n    remove_step_tables(prepared, storage)  # PLANT\n")],
     [TABLES], ["test_a_staged_run_within_the_ceiling_keeps_its_step_tables"],
     "AssertionError: assert [] == ['titled.parq"),
    ("removal-too-wide", "the removal clears every load's tables, not the refused run's own",
     [(STAGED, "    for path in prepared.paths.values():\n        fs.delete_file(path)\n",
       "    fs._fs.delete_dir_contents(f\"{storage.bucket}/loads\")  # PLANT\n")],
     [TABLES], ["test_the_removal_touches_no_other_run_s_tables"],
     "AssertionError: assert [] == ['titled.parq"),
    ("pack-undeclared", "a pack's declaration dropped (the Ledger's)",
     [(SEEDS, '        case_name="Operation Ledger (synthetic demo)",\n        highest_marking="OFFICIAL",\n',
       '        case_name="Operation Ledger (synthetic demo)",\n')],
     [PACKS], ["test_every_pack_declares_its_highest_marking"], "assert {'ledger'} == set()"),
    ("pid-secret", "the Prison Intelligence plan marks its rows SECRET",
     [(PID_PLAN, '    classification: str = "OFFICIAL"\n', '    classification: str = "SECRET"\n')],
     [PACKS], ["test_prison_intelligences_declaration_holds_for_every_write"],
     "AboveTheDeploymentCeiling"),
    ("scale-secret", "the scale cohort, from the same plan, marked SECRET",
     [(PID_PLAN, '    classification: str = "OFFICIAL"\n', '    classification: str = "SECRET"\n')],
     [PACKS], ["test_the_scale_cohorts_declaration_holds_for_every_write"],
     "a write above the declaration"),
    ("ledger-secret", "the Ledger's own direct nodes marked SECRET (its links left as they are)",
     [(LEDGER, '            handling=_HANDLING, created_by=principal.id, created_at=now,\n            load_id=f"{load_id_prefix}-direct",',
       '            handling=_HANDLING.model_copy(update={"classification": "SECRET"}), created_by=principal.id, created_at=now,\n            load_id=f"{load_id_prefix}-direct",')],
     [PACKS], ["test_ledgers_declaration_holds_for_every_write"], "a write above the declaration"),
    ("hmp-no-secret", "HMP's SECRET conflict lowered, so its declaration overstates",
     [(HMP, 'date(2025, 11, 2), classification="SECRET")', 'date(2025, 11, 2), classification="OFFICIAL")')],
     [PACKS], ["test_hmps_declaration_is_the_highest_it_writes"],
     "a declaration higher than anything the pack writes"),
    ("corp-no-secret", "Fixture Corp's SECRET shortcut lowered, so its declaration overstates",
     [(CORP, '            classification="SECRET",\n', '            classification="OFFICIAL",\n')],
     [PACKS], ["test_fixture_corps_declaration_is_the_highest_it_writes"],
     "a declaration higher than anything the pack writes"),
    ("public-staged-unjudged", "a staged public dataset judged as an undeclared pack, its rows unread",
     [(SEEDS, "        _refuse_staged_rows_above_the_ceiling(name, data_root / spec.data_folder, ceiling)\n        return\n",
       "        pass  # PLANT\n")],
     [PACKS], ["test_a_staged_public_dataset_within_the_ceiling_is_seeded",
               "test_a_staged_public_dataset_above_the_ceiling_is_refused_before_its_seed_starts"], None),
    ("public-rows-unjudged", "a staged public dataset's rows never judged",
     [(SEEDS, "        refuse_rows_above_the_ceiling(recipe, rows, ceiling)\n", "        pass  # PLANT\n")],
     [PACKS], ["test_a_staged_public_dataset_above_the_ceiling_is_refused_before_its_seed_starts"],
     "DID NOT RAISE"),
    ("enron-secret", "Enron's seed marks its writes SECRET",
     [(ENRON, '    classification="OFFICIAL",\n    handling_code="P",\n    originator="enron-demo",',
       '    classification="SECRET",\n    handling_code="P",\n    originator="enron-demo",')],
     [PACKS], ["test_enrons_declaration_holds_for_every_write"], "a write above the declaration"),
    ("dry-run-unjudged", "Test's dry run judges no row against the ceiling",
     [(ENGINE, DRY_RUN_CHECK, "")],
     [VERIFYING], ["test_a_staged_pipeline_s_test_refuses_a_row_above_the_ceiling"], 'AssertionError: {"rows_read":'),
    ("sample-only", "Verify judges only its sample, not the whole file",
     [(VERIFY, WHOLE_FILE_CHECK, "")],
     [VERIFYING], ["test_test_judges_every_row_of_the_file_not_only_its_sample"], 'AssertionError: {"rows_read":'),
    ("test-unjudged", "Test judges nothing against the ceiling, in Verify or its dry run",
     [(ENGINE, DRY_RUN_CHECK, ""), (VERIFY, WHOLE_FILE_CHECK, "")],
     [VERIFYING], ["test_test_refuses_a_file_with_a_row_above_the_ceiling_in_the_load_s_words",
                   "test_test_judges_every_row_of_the_file_not_only_its_sample",
                   "test_a_staged_pipeline_s_test_refuses_a_row_above_the_ceiling"], 'AssertionError: {"rows_read":'),
    # SECRET is the scheme's top, so nothing the scheme defines is above HMP's declaration: these two
    # plant a marking outside the scheme (which the ceiling counts as above it) where the first proof
    # never looked, to show it now reads the network's own writes and the incident events.
    ("hmp-network-unread", "HMP's network nodes and homes marked outside the scheme",
     [(HMP, 'def _handling(classification: str = "OFFICIAL") -> Handling:',
       'def _handling(classification: str = "TOP SECRET") -> Handling:')],
     [PACKS], ["test_hmps_declaration_is_the_highest_it_writes"], "a write above the declaration"),
    ("hmp-events-unread", "HMP's incident events marked outside the scheme",
     [(HMP_EVENTS, '    handling = Handling(\n        classification="OFFICIAL",',
       '    handling = Handling(\n        classification="TOP SECRET",')],
     [PACKS], ["test_hmps_declaration_is_the_highest_it_writes"], "a write above the declaration"),
    ("ceiling-before-guards", "Test without steps judges the ceiling before its withheld guards",
     [(VERIFY, "    else:\n        # The staged path's two guards",
       "    else:\n        refuse_rows_above_the_ceiling(recipe, all_rows, DeploymentCeiling.from_env())  # PLANT\n"
       "        # The staged path's two guards")],
     [VERIFYING], ["test_the_withheld_guards_come_before_the_ceiling_without_steps"], None),
    ("staged-ceiling-before-guard", "a staged Test judges the ceiling before its clearance guard",
     [(VERIFY, "        tested_rows = [r for rows in read.raw.values() for r in rows[:DEFAULT_SAMPLE_SIZE]]\n",
       "        tested_rows = [r for rows in read.raw.values() for r in rows[:DEFAULT_SAMPLE_SIZE]]\n"
       "        refuse_rows_above_the_ceiling(recipe, tested_rows, DeploymentCeiling.from_env())  # PLANT\n")],
     [VERIFYING], ["test_the_withheld_guards_come_before_the_ceiling_on_a_staged_pipeline"], None),
    ("whole-file-told-to-all", "the rest of the file judged for an author not cleared for it",
     [(VERIFY, "lambda: sample_markings(draft, scheme, all_rows).readable_by(principal, scheme)",
       "lambda: True  # PLANT")],
     [VERIFYING], ["test_a_row_past_the_sample_is_not_told_to_an_author_not_cleared_for_it"],
     "above_the_deployments_highest_marking"),
    ("removal-error-escapes", "a table the store will not remove turns the refusal into its error",
     [(STAGED, "        try:\n            fs.delete_file(path)\n        except OSError as error:\n"
       "            _log.warning(\"a refused load's step table %s was not removed: %s\", path, error)\n",
       "        fs.delete_file(path)  # PLANT\n")],
     [TABLES], ["test_a_table_the_store_will_not_remove_leaves_the_refusal_as_it_was"],
     "OSError: the store would not remove it"),
    ("write-refusal-removes", "the backstop's later refusal removes the step tables too",
     [(STAGED, "    if refused.kind in ROW_REFUSALS:\n", "    if True:  # PLANT\n")],
     [TABLES], ["test_only_the_row_check_s_refusals_remove_the_step_tables"], None),
    ("pack-unproved", "a pack added, declared, with no proof",
     [(SEEDS, '    "hmp": Dataset(\n',
       '    "extra": Dataset(script="scripts.seed_extra", case_name="x", highest_marking="OFFICIAL"),\n'
       '    "hmp": Dataset(\n')],
     [PACKS], ["test_every_pack_declares_its_highest_marking"],
     "a pack whose declaration no test below proves"),
]


def run(files: list[str]) -> str:
    try:
        done = subprocess.run(
            [".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-p", "no:cacheprovider",
             "-q", "-rA", *files],
            cwd=CORE, capture_output=True, text=True, timeout=600,
            env={**os.environ, "COLUMNS": "400"},
        )  # fmt: skip
    except subprocess.TimeoutExpired:
        return "FAILED (the run hung past 600 s and was stopped)\n0 passed, hung"
    keep = ("PASSED", "FAILED", "ERROR ")
    lines = [line for line in done.stdout.splitlines() if line.startswith(keep)]
    return "\n".join(lines + [done.stdout.strip().splitlines()[-1]])


def main() -> int:
    head = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=CORE, capture_output=True, text=True
    ).stdout.strip()
    only = set(sys.argv[1:])
    plants = [(n, p) for n, p in enumerate(PLANTS, start=1) if not only or p[0] in only]
    originals = {path: path.read_bytes() for _, p in plants for path, _, _ in p[2]}
    missed: list[tuple[str, str]] = []
    for n, (slug, what, edits, files, must_fail, reason) in plants:
        texts = {path: data.decode() for path, data in originals.items()}
        for path, old, new in edits:
            assert texts[path].count(old) == 1, (slug, path.name, old)
            texts[path] = texts[path].replace(old, new)
        try:
            for path, text in texts.items():
                if text != originals[path].decode():
                    path.write_text(text)
            out = run(files)
        finally:
            for path, data in originals.items():
                path.write_bytes(data)
        failed = [line for line in out.splitlines() if line.startswith("FAILED")]
        absent = []
        for test in must_fail:
            mine = [line for line in failed if f"::{test} " in line or line.endswith(f"::{test}")]
            if not mine:
                absent.append(test)
            elif reason and not any(reason in line for line in mine):
                absent.append(f"{test}: the reason {reason!r}")
        missed += [(slug, a) for a in absent]
        (HERE / f"red-{n}-{slug}.txt").write_text(
            f"# head {head}; plant: {what}\n# command: pytest -q -rA {' '.join(files)}\n"
            f"# must fail: {', '.join(must_fail)}"
            f"{'; for the reason ' + repr(reason) if reason else ''}"
            f"; all failed: {'yes' if not absent else absent}\n{out}\n"
        )
    for path, data in originals.items():
        assert path.read_bytes() == data, path
    if not only:
        suites = [TABLES, PACKS] + ([VERIFYING] if (CORE / VERIFYING).exists() else [])
        (HERE / "green.txt").write_text(f"# head {head}; no plant\n{run(suites)}\n")
    print("missed:", missed or "none")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
