# Admin in the GOV.UK look (ADR-145 Amendment 16)

The owner's ruling of 14 November 2026, through the orchestrator. Branch `lane/admin-govuk-admin`, from main.
Browser runs on `OSPREY_PORTS_SLOT=1`, as approved. No stack, nothing on osprey-small, no real data.

| File | What it is |
| --- | --- |
| `look-spec-on-main.red.log` | `keyboard/admin-look.spec.ts`'s first form on main 3c59060, before any change: 4 failed (structure in all three looks, GOV.UK's scale). Each stopped at its first assertion, so `plants.py` covers the rest |
| `red-on-main-code.log` | After the first rebase: main's `AdminPlace.tsx`, `sections/People.tsx` and `admin.css` under the branch's tests. 5 unit tests and 5 browser cases red, the keyboard coming case among them |
| `case-name-red.log` | The orchestrator's follow-up, a case's name in the body face: red without the marker, then red on the face itself (IBM Plex Mono) with the marker in place, then 52 passed |
| `plants.py`, `plants.log` | Each look-spec check and the coming keyboard case, planted alone in the shape main drew or a regression would take, the tree restored from git after each. A plant counts as red only when every failing test points at the assertion it names, so a harness break or another check failing first counts as missed: 12 plants, all red for their reason. The GOV.UK `h2sNotSmaller` and `headerHeight` bounds are not red in GOV.UK: no plausible plant draws a 36px `h2`, and the header plant is red in dark and light. A first plant, main's long header back, stayed green and was the wrong plant: with headers kept to one line it is harmless. The height check got its own plant instead |
| `measures.log` | What the look spec measures, printed (`ADMIN_LOOK_PRINT=1`) on the branch and on main's three files, each naming its commit: the figures Amendment 16 cites |
| `keyboard-after-rebase.log` | `admin-look.spec.ts` and `admin.spec.ts` with `registry-govuk.diff` applied: 52 passed |
| `axe-after-rebase.log` | `every-harness.spec.ts -g admin-harness`, dark, light and GOV.UK with `checkUndecidedContrast`: 96 passed |
| `vitest-full.log` | The whole workspace suite at the head it names: 3455 passed, `PeopleEntraAdministrator.test.tsx` (4c) among them |
| `before-*.png`, `after-*.png` | People at 1280px: GOV.UK with People rights alone and with every Admin right; every Admin right in dark and light (`keyboard/admin-look-capture.spec.ts`, after the faces load, the place let grow to its whole height inside the harness) |
| `registry-govuk.diff` | The orchestrator's `actionRegistry.ts`: `open-a-coming-admin-section-by-keyboard` replaced by `read-a-coming-admin-section-by-keyboard` |

**A flake found and fixed.** In the first combined run after the rebase, GOV.UK's person row read 173px against a
bound of 160px. Alone the spec passed three times out of three, and the capture showed 153px. The measurement ran
before GDS Transport had loaded under the parallel run, so `open()` now waits for `document.fonts.ready`.

**The lane review** (lane-reviewer, 14 November) found the following, all fixed in the branch:
- checks that could not fail for their reason:
  - coming links counted only as `<a>`;
  - a primary counted by the lane's own class;
- no plant beyond each test's first assertion;
- the open forms spanning eight columns;
- heading levels that skipped from the `h1` to `h3` and `h4`;
- the old `h3` rules and the unreachable placeholder;
- values outside the tokens;
- Amendment 16's claims about the username, the registry diff and figures that no record held;
- captures cut at the viewport, and none in dark or light.

The `h2`s then drew larger than the `h1` in dark and light (seen in the dark capture), so they are sized, and that
is held too. Kept and recorded in Amendment 16:
- *Save* as the default button: GOV.UK keeps one primary per page, and this page has a row per person;
- the shared help page's `h2`.

**The second review** (same reviewer, at 9c108a1) found:
- the gate records naming no head;
- captures still cut, by the harness's fixed height rather than the viewport;
- `plants.py` counting any failure as red;
- the GOV.UK `headerHeight` plant too small to go red there, and no plant of the row links' size alone;
- a stale fallback to a coming section;
- stale figures in the look spec;
- a test still counting the lane's own class;
- Amendment 16 claiming `h2`s on every screen.

All are fixed except the last, which is narrowed: the other sections' headings are named as not yet changed.

Still open:
- the row links in GOV.UK take the workspace's focus ring, not `govuk-link`'s;
- the dark and light row bound has 1px of headroom (141px against 142px), measured on this Mac with the
  repository's own fonts. `make -k ci` was not run, as the orchestrator ruled, so CI's own reading of it is not
  on record.
