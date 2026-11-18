# Slice SE1 · SE1 · A drawn item or board picture above the deployment's ceiling is refused before anything is kept (C039, C071)

- **Build id:** SE1
- **Dial setting:** balanced
- **Rounds limit:** 2
- **After:** nothing
- **Status of this brief:** APPROVED by the owner, 18 November 2026, with the ruling below. C187 and C186 are their own
  slices, SE2 and SE3 (`BACKLOG.md`), after this one.

## What

ADR-148 decision 10 (`OspreyFlow_Build/spec/06_DECISIONS.md`): an item marked above `deployment.highest_marking` is
refused "before anything is written, in words that say the deployment's limit", never the item's content. Rule 3 and 4
of `process/CLAUDE.md` bind it: access control at the write, and an access-control test for every path.

What exists (scouted 18 Nov, the key points re-read by the conductor):

- The graph write is already backstopped: `dataset_scope.py` (lines 554, 563, 609, 622, 729) calls
  `refuse_writes_above_the_ceiling` (`services/ingest/ceiling.py:218`), so a drawn item above the ceiling does not reach
  the store, but it is refused there with the generic reason `write`. The boards layer itself checks only the scheme,
  the case's ceiling and the drawer's clearance (`services/api/boards.py:201-216`; the case ceiling falls back to the
  scheme's highest, `:165-188`), and `get_boards` (`app.py:4863-4884`) passes no deployment ceiling.
- **The real defect (C071):** `Boards.upload_picture` calls `media.put(...)` (`boards.py:~1088`) before the graph
  refuses the Document, so an above-ceiling picture's bytes are kept and orphaned. The routes `upload_drawn_picture`
  (`app.py:5174-5221`) and `choose_picture` (`:5224-5249`) never call `refuse_above_the_deployment_ceiling`
  (`app.py:3352`, used only at `:7785` documents and `:7886` entity pictures).
- Write sites that need the early refusal: declare (`boards.py:498`, check `:516`), link (`:544`, `:580`), edit
  (`:666`, `:695`), decide (`:914`, check `:936`), upload_picture (`:1048`, `:1078`), choose_picture (`:1117`, `:1147`).

**Ruling (the owner, 18 November 2026: "refused before any bytes are kept, with the refusal documents already get"):** the refusal is the
documents route's: status 422, code `above_the_deployments_highest_marking`, words naming the deployment's limit and
never the item's content (spec 03 line 513). Spec 03 line 185's 409 `above_the_ceiling` is the case's ceiling and is not
used here.

## Acceptance test

New file `OspreyFlow_Build/tests/services/api/test_deployment_ceiling_drawn_items.py` (pure). For each of the six write
sites above, with the deployment ceiling set below the item's marking: the response is the 422 above, the body does not
carry the item's marking text or content, and **nothing was kept**: the recording fake's media store and graph are
untouched (assert `put` was never called and `nodes == []`), written the way `test_deployment_ceiling_uploads.py:35-61`
does. Plus the controls (rule 15): an item at the ceiling is accepted; with no ceiling set, nothing changes.
Red today because the picture routes return a different status and the media store's `put` is called before the
refusal; each case must fail on that assertion, not on a missing fixture.

## Checks

Pure only: the acceptance file, `test_boards.py`, `test_deployment_ceiling_uploads.py`,
`test_deployment_ceiling_backstop.py`. No `packages/` change is expected, so no TypeScript to regenerate; if one is
needed, stop and say.

## Out of scope

- **C187** (the source governance edit judges no clearance and does not stop a marking being lowered) and **C186** (the
  model draft takes any writer): both need the owner's ruling first, see the conductor's questions. They are added as
  rows of build SE1 after the rulings.
- The 409/422 choice for anything but drawn items and board pictures; the Glass; the store backstop (keep it).
