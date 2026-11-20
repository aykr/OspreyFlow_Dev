# Slice SE2 · SE2 · The source governance edit judges the editor's clearance, the deployment's ceiling and the source's current marking (C187)

- **Build id:** SE2
- **Dial setting:** balanced
- **Rounds limit:** 4
- **After:** nothing (SE1 is merged)
- **Status of this brief:** written by the conductor on 19 November 2026 under the owner's standing approval (ruling 8 of
  19 November: start everything that is ready). The scope is the owner's of 18 November: C187 is SE2, "the editor's
  clearance, the ceiling, never below the source's current marking". The details below are from a scout of 19 November
  (it corrected four points in the first backlog text, noted where they matter).

## What

The route that edits a source's governance judges nothing about markings. The default-marking route does.

- **The governance edit** (the handler `edit_dataset_source_governance`, OspreyFlow_Core/services/api/app.py, about lines
  12642-12681): gated by edit_pipelines with add_ingest_files (about lines 12633-12641) and by the source-author dependency;
  its only refusal is the keyless-refresh check (about lines 12656-12657); it writes `body.handling` as given
  (`edit_governance` in OspreyFlow_Core/services/api/sources.py, about lines 194-206; the input type is
  `SourceGovernanceInput` in OspreyFlow_Core/packages/schemas/sources.py, about line 655). An editor can set a marking above
  their own clearance, above the deployment's ceiling, or lower than the source's current marking.
- **The default-marking route** (PUT, `set_dataset_source_default_marking`, app.py about lines 12695-12751) calls
  `default_marking_problems` (OspreyFlow_Core/services/api/sources.py, about lines 99-152) with
  `DeploymentCeiling.from_env(handling_scheme)` and answers 422 `default_marking_refused` with a `problems` list: above
  the editor's clearance ("a source's rows are never marked higher than the person declaring it may read"), above the
  deployment's highest marking (naming the ceiling), and below the source's own marking ("a default never lowers a
  marking"). Its wording is in spec/06_DECISIONS.md (ADR-140 Amendment 19, decisions 4 and 5, about lines 31899-31903).
  The governance route's spec line is spec/03_CONDUIT_MIDDLEWARE.md about line 688 and gives only its gate.

**The change.** The governance edit judges the marking it is asked to set by the same three checks, before anything is
written, and answers as the default-marking route does: 422 with the problems in words (a sentence each, naming the
ceiling for the second, never the data). Share the check, do not copy it (`default_marking_problems` is the one place);
if the shared function needs a name or a signature change to serve both routes, change it in one place and keep the
default-marking route's behaviour byte-for-byte for every case it refuses or accepts today. The error code is the
default-marking route's family; the builder names it and the spec edit says so. The spec is silent on this route
(spec/03 about line 688 gives only the gate): the wording and the status code are a spec edit in the same slice (rule 11).
Only the marking carried by the handling in the request is judged; a governance edit that changes no marking is not newly
refused (control, rule 15).

Binding: process/CLAUDE.md rules 3, 4, 11, 12, 15; spec/06_DECISIONS.md ADR-140 Amendment 19; ADR-148 decision 10 (the
ceiling).

## Acceptance test

New file OspreyFlow_Build/tests/services/api/test_governance_edit_marking.py (pure). The fixture shape to copy is
test_dataset_sources.py's `world`, `_as`, `_register` and the parametrised three-problem default-marking test (about lines
119-160 and 627); the ceiling is set with the environment variable the default-marking tests use. Through the governance
route, with a fake principal and a recording fake store:

- a marking above the editor's clearance: refused 422 with the clearance sentence, **and the store is unchanged**;
- a marking above the deployment's ceiling: refused 422 naming the ceiling, store unchanged;
- a marking below the source's current marking: refused 422 ("never lowers"), store unchanged;
- each of the three red today because the route answers 200 and writes it.
- controls (rule 15): a marking at or above the current one, within the clearance and the ceiling, is accepted; an edit that
  changes no marking is accepted; with no ceiling set, only the other two checks apply; the default-marking route's refusals
  and acceptances are unchanged.

Plant the violation in the shape the code meets at its real call site: the request body the route receives
(`SourceGovernanceInput`), through the app, not a call to the helper alone.

## Checks

Pure only (ports 9): the acceptance file and the existing tests of the touched modules under OspreyFlow_Build/tests/:
services/api/test_dataset_sources.py, ingest/test_staged_pipeline_run.py (it calls `edit_governance` on the in-memory
store), services/api/test_audit_kinds.py, services/api/test_deployment_ceiling.py (the route-rights test, test_route_rights.py,
needs Postgres and is not a pure check: it is left out). The
line adds every mapped pure test that scans a folder the slice changes. The live store test that touches
`edit_governance` (test_studio_recipes_store.py) needs the dev stack and is not run here: it is owed.

## First step, from the conductor (19 November 2026)

Your branch was cut from main before the owner's commit c7fda31, which allows the 25 paths ADR-152 names. Until your branch
has it, the citations scan (test_the_repository_itself_is_clean) is red for files you did not touch, and no change of yours
can fix that. Before anything else, merge main into your branch (git merge main in your worktree), then run the checks. Do
not change any citation, allowlist or spec file other than the spec text this slice is about.

## Out of scope

The Glass (no change to what the governance editor shows: if it needs to show the new refusal, stop and say); the
TypeScript types; the default-marking route's behaviour; SE3 (the model draft's creator). Do not touch the Makefile or
the CI workflow.
