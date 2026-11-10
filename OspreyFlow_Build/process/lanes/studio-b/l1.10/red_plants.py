"""L1.10's red-then-green record (rules 12 and 15): each plant is one exact edit to the code under
test, in whichever file holds it; the script applies it, runs the named test files, restores the
file byte for byte and writes `red-<n>-<slug>.txt`, headed by the commit, the plant and the
command. A plant may name the reason each named test must fail with.

Run from OspreyFlow_Core with the closed offline ports pinned (no stack):
    .venv/bin/python ../OspreyFlow_Build/process/lanes/studio-b/l1.10/red_plants.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE.parents[4] / "OspreyFlow_Core"
ENGINE = CORE / "services/ingest/engine.py"
CEILING = CORE / "services/ingest/ceiling.py"
PIPELINE = CORE / "services/api/pipeline_run.py"
APP = CORE / "services/api/app.py"
SITE = CORE / "harness/site.py"
SCOPE = CORE / "services/api/dataset_scope.py"
SEEDS = CORE / "scripts/seed_internal.py"
PAYSIM = CORE / "packages/demo_fixtures/paysim.py"
CYBER = CORE / "scripts/seed_cyber_intrusion.py"
LOADS = "../OspreyFlow_Build/tests/services/api/test_deployment_ceiling.py"
UPLOADS = "../OspreyFlow_Build/tests/services/api/test_deployment_ceiling_uploads.py"
BACKSTOP = "../OspreyFlow_Build/tests/services/api/test_deployment_ceiling_backstop.py"
PACKS = "../OspreyFlow_Build/tests/test_seed_internal_ceiling.py"
BACKSTOP_LINE = "        refuse_writes_above_the_ceiling(stamped)  # ADR-148 decision 10, the backstop\n"
CORRECTION_LINE = (
    "        refuse_writes_above_the_ceiling([replacement])  # ADR-148 decision 10, the backstop\n"
)

CHECK_COMMENT = (
    "    # ADR-148 decision 10: the deployment's marking ceiling, judged over every row before raw\n"
)
DOC_NAME = "        filename = validate_upload_name(name, UPLOAD_CONTENT_EXTENSIONS)\n"
PIC_NAME = "        filename = validate_upload_name(name, PICTURE_EXTENSIONS)\n"
REFUSAL = "            status_code=_UPLOAD_REFUSAL_STATUS[refusal.code], detail=refusal.message\n"
UPLOAD_CHECK = (
    "        ) from refusal\n"
    "    # ADR-148 decision 10: refused before the body is read or anything is stored.\n"
    "    refuse_above_the_deployment_ceiling(request, classification)\n"
)


def _upload(name_line: str) -> tuple[str, str]:
    """The upload check after this route's own name check, removed."""
    old = name_line + "    except UploadRefused as refusal:\n        raise HTTPException(\n" + REFUSAL
    return old + UPLOAD_CHECK, old + "        ) from refusal\n"


#: (slug, what, [(file, old, new)], test files, the tests that must go red, the reason or None)
PLANTS = [
    ("engine-check-removed", "run_recipe judges no row against the ceiling",
     [(ENGINE, "        refuse_rows_above_the_ceiling,\n", "        lambda *_: None,  # PLANT\n")],
     [LOADS], ["test_a_load_with_a_row_above_the_ceiling_is_refused_and_writes_nothing"],
     "DID NOT RAISE"),
    ("engine-check-after-staging", "the raw rows staged before the ceiling is judged",
     [(ENGINE, CHECK_COMMENT,
       "    _stage_raw_rows(materialized_rows, storage=storage or ObjectStorageConfig.from_env(), "
       "load_id=load_id, source=source)  # PLANT\n" + CHECK_COMMENT)],
     [LOADS], ["test_a_load_with_a_row_above_the_ceiling_is_refused_and_writes_nothing"],
     "staged before the refusal"),
    ("off-by-one", "a marking at the ceiling counted as above it: `>` -> `>=`",
     [(CEILING, "        return self.scheme.classification.index(classification) > self.scheme",
       "        return self.scheme.classification.index(classification) >= self.scheme")],
     [LOADS, UPLOADS],
     ["test_a_load_at_the_ceiling_passes", "test_a_document_at_the_ceiling_is_stored",
      "test_a_picture_at_the_ceiling_is_stored", "test_the_conduit_reads_the_ceiling"], None),
    ("default-the-lowest", "nothing set read as the scheme's lowest, not its highest",
     [(CEILING, "            return cls(marking=scheme.classification[-1], scheme=scheme)\n",
       "            return cls(marking=scheme.classification[0], scheme=scheme)  # PLANT\n")],
     [LOADS], ["test_nothing_set_is_the_scheme_s_highest",
               "test_with_no_ceiling_set_a_secret_row_loads_as_before"], None),
    ("unknown-ceiling-guessed", "an unknown OSPREY_HIGHEST_MARKING read as no ceiling",
     [(CEILING, "        if raw not in scheme.classification:\n",
       "        if raw not in scheme.classification:\n            raw = ''  # PLANT\n"
       "        if raw and raw not in scheme.classification:\n")],
     # Each fails in its own words (the reader: no CeilingUnknown; the start: the stores opened),
     # so no one reason is named; the record keeps both lines.
     [LOADS], ["test_an_unknown_ceiling_stops_the_conduit_rather_than_guessing",
               "test_the_conduits_start_stops_on_an_unknown_ceiling_before_opening_anything"],
     None),
    ("start-read-removed", "the Conduit's start reads no ceiling",
     [(APP, "    deployment_ceiling = DeploymentCeiling.from_env()\n",
       "    deployment_ceiling = None  # PLANT\n")],
     [LOADS], ["test_the_conduits_start_stops_on_an_unknown_ceiling_before_opening_anything"],
     "the start went on to open the stores"),
    ("fixed-check-removed", "a staged pipeline writes its step tables with its fixed markings unjudged",
     [(PIPELINE, "    refuse_fixed_markings_above_the_ceiling(recipe, DeploymentCeiling.from_env())\n",
       "")],
     [LOADS], ["test_a_staged_pipeline_judges_its_fixed_markings_before_its_step_tables"],
     "does not judge its fixed markings"),
    ("render-unchecked", "an unknown deployment.highest_marking rendered as written",
     [(SITE, "    chosen = config.deployment.highest_marking\n    if chosen is None:\n"
             "        return known[-1]\n    if chosen not in known:\n",
       "    chosen = config.deployment.highest_marking\n    if chosen is None:\n"
       "        return known[-1]\n    if False:  # PLANT\n")],
     [LOADS], ["test_a_ceiling_the_scheme_does_not_know_is_refused_at_render"], "DID NOT RAISE"),
    ("document-check-removed", "a document's marking not judged against the ceiling",
     [(APP, *_upload(DOC_NAME))], [UPLOADS],
     ["test_a_document_above_the_ceiling_is_refused_before_anything_is_stored"], None),
    ("picture-check-removed", "an entity's picture's marking not judged against the ceiling",
     [(APP, *_upload(PIC_NAME))], [UPLOADS],
     ["test_a_picture_above_the_ceiling_is_refused_before_anything_is_stored"], None),
    ("backstop-removed", "the stamping graph's writes not judged against the ceiling",
     [(SCOPE, None, None)], [BACKSTOP],
     ["test_a_node_above_the_ceiling_never_reaches_the_store",
      "test_a_link_above_the_ceiling_never_reaches_the_store",
      "test_a_bulk_load_above_the_ceiling_never_reaches_the_store"], "DID NOT RAISE"),
    ("pack-refusal-removed", "a demo pack's declared highest not judged before its seed",
     [(SEEDS, "        _refuse_a_pack_above_the_ceiling(dataset, spec, directory)\n",
       "        pass  # PLANT\n")], [PACKS],
     ["test_a_pack_above_the_ceiling_is_refused_before_its_seed_starts",
      "test_a_pack_that_declares_nothing_is_judged_as_the_scheme_s_highest"], "DID NOT RAISE"),
    ("undeclared-pack-passes", "a pack that declares nothing read as the scheme's lowest",
     [(SEEDS, "    held = spec.highest_marking or scheme.classification[-1]\n",
       "    held = spec.highest_marking or scheme.classification[0]  # PLANT\n")], [PACKS],
     ["test_a_pack_above_the_ceiling_is_refused_before_its_seed_starts"], "DID NOT RAISE"),
    ("whole-marking-widened", "the row judged by its whole marking, widened when any part fails "
     "(the engine's `_resolve_markings`), not by its classification",
     [(CEILING, "        found, cannot_read = _row_classifications(recipe, row, ceiling.scheme)\n",
       "        from .engine import _resolve_markings  # PLANT\n\n"
       "        found = {m.classification for m in _resolve_markings(recipe, row, ceiling.scheme)}\n"
       "        cannot_read = False\n")],
     [LOADS], ["test_a_row_whose_classification_reads_is_judged_by_it_alone",
               "test_a_row_whose_classification_cannot_be_read_is_refused_in_words_that_say_so"],
     None),
    ("bound-cell-ignored", "a column's classification never counted, only the element's default",
     [(CEILING, "            found.add(cell)\n", "            pass  # PLANT\n")], [LOADS],
     ["test_a_row_whose_units_conflict_is_still_judged",
      "test_a_load_with_a_row_above_the_ceiling_is_refused_and_writes_nothing"], "DID NOT RAISE"),
    ("unreadable-passes", "a row whose classification cannot be read never refused",
     [(CEILING, "    if unreadable:\n        raise AboveTheDeploymentCeiling(ceiling.marking, "
                "\"unreadable\")\n", "")], [LOADS],
     ["test_a_row_whose_classification_cannot_be_read_is_refused_in_words_that_say_so"],
     "DID NOT RAISE"),
    ("element-literal-ignored", "an element's own fixed classification not judged, the defaults' alone",
     [(CEILING,
       "        fixed.append(str(literal.get(\"classification\") or defaults.get(\"classification\") "
       "or \"\"))\n",
       "        fixed.append(str(defaults.get(\"classification\") or \"\"))  # PLANT\n")], [LOADS],
     ["test_an_element_whose_own_fixed_marking_is_above_the_ceiling_is_refused"], "DID NOT RAISE"),
    ("detail-removed", "the 422 without the detail the Glass shows a person",
     [(APP, "            \"detail\": exc.problems[0],\n", "")], [UPLOADS],
     ["test_a_document_above_the_ceiling_is_refused_before_anything_is_stored",
      "test_a_picture_above_the_ceiling_is_refused_before_anything_is_stored"], "KeyError"),
    ("upload-said-as-a-load", "an upload refused in a load's words",
     [(APP, "        raise AboveTheDeploymentCeiling(ceiling.marking, \"import\")\n",
       "        raise AboveTheDeploymentCeiling(ceiling.marking)  # PLANT\n")], [UPLOADS],
     ["test_a_document_above_the_ceiling_is_refused_before_anything_is_stored"], "This load would write rows"),
    ("correction-backstop-removed", "a correction's new element not judged against the ceiling",
     [(SCOPE, (CORRECTION_LINE, 2), None)], [BACKSTOP],
     ["test_a_correction_above_the_ceiling_never_reaches_the_store"], "DID NOT RAISE"),
    ("paysim-stray-marking", "one PaySim link written at the seed's marking, not the one given",
     [(PAYSIM, "                provenance=_provenance(row.index),\n                handling=handling,\n"
                "                created_by=created_by,\n",
       "                provenance=_provenance(row.index),\n"
       "                handling=handling.model_copy(update={\"classification\": \"SECRET\"}),\n"
       "                created_by=created_by,\n")], [PACKS],
     ["test_paysims_declaration_holds_for_every_write"],
     "a write at another marking"),
    ("cyber-stray-marking", "a cyber-intrusion node written above its declaration",
     [(CYBER, "        handling=node.handling,",
       "        handling=node.handling.model_copy(update={\"classification\": \"SECRET\"}),")],
     [PACKS], ["test_cyber_intrusions_declaration_holds_for_every_write"], None),
    ("bound-floor-unjudged", "a bound element's default floor judged nowhere: skipped in the fixed "
     "check, and an empty cell adds nothing",
     [(CEILING, "        # A bound element's literal holds no classification, so its floor is the "
                "defaults'.\n",
       "        if \"classification\" in handling_bindings(element.handling):  # PLANT\n"
       "            continue\n"),
      (CEILING, "        found.add(default)\n        column = handling_bindings(element.handling)"
                ".get(\"classification\")\n",
       "        column = handling_bindings(element.handling).get(\"classification\")\n"
       "        if column is None:  # PLANT\n            found.add(default)\n")],
     [LOADS], ["test_an_empty_cell_takes_the_element_s_default_and_is_judged_by_it",
               "test_a_bound_element_s_default_above_the_ceiling_is_refused_before_any_staging"],
     "DID NOT RAISE"),
    ("condition-key-dropped", "a condition's column left out of the key rows are judged once by",
     [(CEILING, "        if element.when is not None:\n            columns.add(element.when.field)\n",
       "")], [LOADS],
     ["test_a_condition_s_column_keeps_rows_apart_when_judged_once_per_combination"],
     "DID NOT RAISE"),
    ("missing-keyed-as-empty", "a missing column keyed as an empty one",
     [(CEILING, "        key = tuple((c in row, row.get(c)) for c in ordered)\n",
       "        key = tuple((True, row.get(c)) for c in ordered)  # PLANT\n")], [LOADS],
     ["test_a_missing_column_is_not_read_as_an_empty_one"], "DID NOT RAISE"),
    ("undeclared-said-to-hold", "an undeclared pack told it holds data up to the scheme's highest",
     [(SEEDS, "            if spec.highest_marking is not None\n", "            if True  # PLANT\n")],
     [PACKS], ["test_a_pack_that_declares_nothing_is_judged_as_the_scheme_s_highest"],
     "declares no highest marking"),
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
    originals = {
        path: path.read_bytes()
        for path in {ENGINE, CEILING, PIPELINE, APP, SITE, SCOPE, SEEDS, PAYSIM, CYBER}
    }
    missed: list[tuple[str, str]] = []
    for n, (slug, what, edits, files, must_fail, reason) in enumerate(PLANTS, start=1):
        texts = {path: data.decode() for path, data in originals.items()}
        for path, old, new in edits:
            if old is None:  # every backstop line in the file, removed
                assert texts[path].count(BACKSTOP_LINE) == 3, (slug, path.name)
                texts[path] = texts[path].replace(BACKSTOP_LINE, "")
                continue
            if isinstance(old, tuple):  # (a line, how many times it is there): each removed
                line, count = old
                assert texts[path].count(line) == count, (slug, path.name, line)
                texts[path] = texts[path].replace(line, "")
                continue
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
    (HERE / "green.txt").write_text(
        f"# head {head}; no plant\n{run([LOADS, UPLOADS, BACKSTOP, PACKS])}\n"
    )
    print("missed:", missed or "none")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
