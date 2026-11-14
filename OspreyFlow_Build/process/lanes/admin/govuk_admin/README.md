# Admin in the GOV.UK look (ADR-145 Amendment 16)

The owner's ruling of 14 November 2026, through the orchestrator. Branch `lane/admin-govuk-admin`, from main.

| File | What it is |
| --- | --- |
| `look-spec-on-main.red.log` | `keyboard/admin-look.spec.ts` on main 3c59060 before any change: 4 failed (structure in all three looks, GOV.UK's scale); the dark and light size guards pass, as main must |
| `red-on-main-code.log` | After rebasing: main's `AdminPlace.tsx`, `sections/People.tsx` and `admin.css` under the branch's tests. 5 unit tests and 5 browser cases red, among them the keyboard coming case |
| `plant-govuk-size-in-every-look.log` | The dark and light guards red: the GOV.UK 16px rule unscoped from `[data-brand="govuk"]` |
| `keyboard-after-rebase.log` | `admin-look.spec.ts` and `admin.spec.ts` with `registry-govuk.diff` applied: 52 passed |
| `axe-after-rebase.log` | `every-harness.spec.ts -g admin-harness`, dark, light and GOV.UK with `checkUndecidedContrast`: 96 passed |
| `before-people*.png`, `after-people*.png` | GOV.UK at 1280px, People with People rights only and with every Admin right (`keyboard/admin-look-capture.spec.ts`) |
| `registry-govuk.diff` | The orchestrator's `actionRegistry.ts`: `open-a-coming-admin-section-by-keyboard` replaced by `read-a-coming-admin-section-by-keyboard` |

Browser runs on `OSPREY_PORTS_SLOT=1`, as approved. No stack, nothing on osprey-small, no real data.

**A flake found and fixed.** In the first combined run after the rebase, GOV.UK's person row read 173px against a
bound of 160px. Alone, the spec passed three times out of three; the capture showed 153px. The measure ran before
GDS Transport had loaded under the parallel run, so `open()` now waits for `document.fonts.ready`.
