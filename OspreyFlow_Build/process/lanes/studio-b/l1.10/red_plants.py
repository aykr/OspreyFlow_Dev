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
LOADS = "../OspreyFlow_Build/tests/services/api/test_deployment_ceiling.py"
UPLOADS = "../OspreyFlow_Build/tests/services/api/test_deployment_ceiling_uploads.py"

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
    originals = {path: path.read_bytes() for path in {ENGINE, CEILING, PIPELINE, APP, SITE}}
    missed: list[tuple[str, str]] = []
    for n, (slug, what, edits, files, must_fail, reason) in enumerate(PLANTS, start=1):
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
    (HERE / "green.txt").write_text(f"# head {head}; no plant\n{run([LOADS, UPLOADS])}\n")
    print("missed:", missed or "none")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
