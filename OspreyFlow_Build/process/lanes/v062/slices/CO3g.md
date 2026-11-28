# Slice CO3g · CO3 · conformance-model on CI runs a small pinned model, so CI checks the pipeline; the deployment model's recall stays release evidence

- **Build id:** CO3 (GitHub's reds; slice id CO3g).
- **Kind:** the owner's ruling of 27 November 2026, about 11:15 UTC (RULINGS.md, item 2, option (a)). It is an exception to the line freeze, given on 28 November about 12:10 (item 7). **The CI change is a diff for the owner to apply** (`OspreyFlow_Build/process/lanes/v062/CO3G_CI_MODEL.diff`); the line never writes `.github/`.
- **After:** nothing.

## Why

GitHub's `conformance-model` job failed on `5614900`, `300e3fe`, `95db737` and `023d2f9`:
- `test_phase6_exit_criterion_end_to_end` and `test_golden_set_recall_has_not_regressed` end on "The model did not answer within the time this deployment allows (900 seconds)".
- The runner's CPU cannot run the ADR-020-pinned model in time.

The tests are not wrong.

## What

1. **A small model for CI's job alone.** It is pinned by its manifest, as the job's `pull_and_verify` pins today's models (`ci.yml`'s `conformance-model` job, about lines 948 to 980). It is small enough to answer on GitHub's 4-CPU runner well inside the deadline.
   - Name the model, its licence (from its own card) and its size.
   - Measure its answer time on a runner of GitHub's shape (4 CPUs, no GPU) on the Mac, and give the figure.
   - **Licence: it must be on the register's allowed list** (`make licence-check`'s model-weights leg). A new model's licence entry is a question for the owner only if it is not already allowed.
2. **The tests choose the model by setting, never by the runner's name.** Under CI's setting:
   - the pipeline tests (extraction, the end-to-end exit criterion) run against the small model;
   - `test_golden_set_recall_has_not_regressed` is skipped with its reason in words, never weakened to the small model's figure: "recall is measured on the deployment model as release evidence (the owner, 27 November)".
   A test proves that the recall test is never skipped outside CI's setting. Show it red first (rule 15).
3. **The release evidence.** One command, documented in `RL2`'s brief notes (a new section in `process/lanes/v062/slices/RL2.md`), runs the golden set on the deployment model on the server's GPU and records the figure. You write the command and its record's shape. **You do not run it:** the server is the owner's.
4. **The diff:** `CO3G_CI_MODEL.diff`, the job's model pull and its setting. `git apply --check` must pass on main; give its output.
5. **Not in scope:** the deployment's models, ADR-020's pins for every other deployment, and the `conformance-model-vision` job.

**Questions:** answer (a) on the owner's standing word unless one is his own kind, which stops the slice: a licence not already allowed, the server, or a decision record.

Binding: process/CLAUDE.md rules 12 and 15; British English.

## Acceptance test

`OspreyFlow_Build/tests/conformance/model_port/test_ci_model_setting.py` (new, red on main): it covers the setting choosing the model, and the recall test skipped only under CI's setting.

## Checks

- The model port's unit tests (no live model: ports 9).
- The licence register's tests.
- Ruff.

**Before your final report, run by hand the cheap checks the conductor will run again before the merge.**
