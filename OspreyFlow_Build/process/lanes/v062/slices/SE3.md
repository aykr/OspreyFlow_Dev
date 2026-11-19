# Slice SE3 · SE3 · Only a model draft's creator can save into, replace or discard it (C186)

- **Build id:** SE3
- **Dial setting:** balanced
- **Rounds limit:** 4
- **After:** nothing (SE1 is merged)
- **Status of this brief:** written by the conductor on 19 November 2026 under the owner's standing approval (ruling 8 of
  19 November: start everything that is ready). The scope is the owner's of 18 November: C186 is SE3, merged before the
  Studio's Model step (IS2) starts. The wording below follows the backlog row in BACKLOG.md and a scout of 19 November.

## What

Today a second writer can rewrite someone else's model draft. The store is OspreyFlow_Core/services/api/target_models.py
(the scout of 19 November found it there, not under services/ingest):

- The protocol is `open_draft(dataset_id, principal)` and `save_draft(dataset_id, given, principal)` (about lines 173-176).
  The principal is passed and never compared with the draft's owner.
- In-memory `save_draft` (about lines 245-255) copies the update onto the draft and keeps the first author's created_by,
  so a second writer's content replaces the first's and is audited as the first's. The Postgres `save_draft` (about
  lines 418-434) reads the draft under lock and updates by dataset and version only.
- The PUT draft route (OspreyFlow_Core/services/api/app.py, about lines 11753-11770) answers 200 to the second writer.
  The discard route and `discard_draft` (target_models.py about lines 257-261 and 460-469) have no owner check either.
- A second writer's open is already refused with 409 (`_refuse_a_second_draft`, about lines 85-89).
- The import path (OspreyFlow_Core/services/api/studio_release.py, `held_draft_problem` about lines 228-270) is the model to
  copy: another person's draft is refused whatever is confirmed, in words that name who holds it; the importer's own draft
  is replaced only on a confirmation of that exact version. Its docstring (about lines 514-517) already names this gap.

**The change.** Every write to a draft (save, replace, discard) checks that the draft's created_by is the principal, in
both the in-memory and the Postgres store, and refuses otherwise **before anything is changed**. The refusal is the neighbours':
status 409, error model_refused (`TargetModelRefused`, app.py about lines 3703-3707), in words copied from
`held_draft_problem`, naming who holds the draft, never its content. A replace of one's own draft is confirmed against the
version (a store argument, as `replace_own_draft` does at about lines 228-237 in studio_release.py), so a stale save is
refused too. The version confirmation is a store argument: it must not change `TargetModelDraftInput` in
OspreyFlow_Core/packages/schemas/dataset_model.py (that regenerates the TypeScript types). The import path
(`apply_import`, about lines 523-533) passes the version it planned. If the PUT route cannot get the version without a
schema change or a Glass change, make the creator check mandatory, make the version check apply where a version is passed,
and **stop and say** which route needs the Glass.

Binding: process/CLAUDE.md rules 3, 4, 11, 12, 15. The spec text for the draft routes is edited in the same slice if it is
silent on this (rule 11); the builder finds the place in spec/03_CONDUIT_MIDDLEWARE.md and spec/09_INGEST_STUDIO.md.

## Acceptance test

New file OspreyFlow_Build/tests/services/api/test_target_model_draft_owner.py (pure: the in-memory store and the app with
fake principals; the fixture shape is test_dataset_model_routes.py's PEOPLE and resolver, and test_studio_release_routes.py's
helper that plants a draft held by someone else). Cases, each red today for the reason it names:

- a second principal's PUT of the draft is refused 409 model_refused and **the draft is unchanged** (content, version,
  created_by): today it returns 200 and rewrites it;
- a second principal's discard is refused the same way and the draft is still there;
- the creator's own save works, and with a stale version it is refused and changes nothing;
- the creator check also holds at the store (call the store directly, not only through the route), in-memory;
- the refusal's body names who holds the draft and carries none of the draft's content;
- controls (rule 15): the creator saves and discards; a second writer's open is still refused 409 as before; the import path's
  behaviour for another person's draft is unchanged.

Plant the second writer in the shape the code meets at its call sites: a different `principal.id` arriving through the
route's own token resolver. The Postgres store's cases are added to its live test file (test_target_models_store.py) but
that file needs the dev stack and is not run in this slice: it is owed.

## Checks

Pure only (ports 9): the acceptance file and the existing tests of the touched modules under
OspreyFlow_Build/tests/services/api/: test_target_models.py, test_dataset_model_routes.py, test_studio_release_routes.py. The route-rights test (test_route_rights.py) needs Postgres and is not a pure check: it is
left out. The line adds every mapped pure test that scans a folder the slice changes.

## Out of scope

The Glass; the TypeScript types; a change to `TargetModelDraftInput`; the Studio's Model step (IS2), which waits for this
slice; the live Postgres run. Do not touch the Makefile or the CI workflow.

## Round 2 note from the conductor (19 November 2026)

The PUT route's missing version check is **accepted as owed** and recorded in the backlog (the row "the draft's PUT route
confirms no version until the Glass sends one"): do not change the route's body or the Glass. Fix the verifier's findings and
nothing else: name the cases after the two tests the accepted ADR-152 decision 11, X5, names (a second person cannot save
into, replace or delete another person's draft; a stale version is refused in words), by renaming the cases you wrote or
adding them; and add a pure case that plants a stale discard, in the route test and in the in-memory store, shown red by
deleting the version argument from the discard.
