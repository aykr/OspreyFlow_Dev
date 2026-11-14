# Admin's other sections' headings (ADR-145 Amendment 16, the orchestrator's follow-up of 14 November 2026)

Branch `lane/admin-section-headings`, from main. This is the same pass as People's, applied to Roles, Dashboard
identities, Datasets, Operations (with its figures), System and Demo packs:
- each section heads its parts with `h2`s beneath its `h1`;
- Datasets' details nest `h3`s beneath the dataset's `h2`, and Operations' figures nest `h3`s beneath *Runs and
  what they cost*;
- every `h2` is drawn at `--fs-13` and every `h3` at `--fs-12`, below the `h1` in each look.

Under GOV.UK, a person's row links also carry `govuk-link`, so a focused one takes GOV.UK's focus state. Models and
Maps are the platform lane's, done in its own step.

Browser runs used `OSPREY_PORTS_SLOT=1`. No stack, no server run, nothing on osprey-small, no real data.

| File | What it is |
| --- | --- |
| `look-spec-before.red.log` | `keyboard/admin-sections-look.spec.ts` on main's sections: all 19 cases red. Each section skips a level in all three looks, and the GOV.UK row link has no `govuk-link` |
| `plants.py`, `plants.log` | 9 plants (the ninth, the h2 size plant in GOV.UK, from the second review), each planted alone and counted red only when every failure stops at the assertion it names. All 9 red: (1) Datasets' Authors an `h5` again; (2) Roles' form title an `h3` again; (3) the sections' `h2`s at the browser's size (12 cases, dark and light); (4) the row links without `govuk-link`; (5) a local focus rule over GOV.UK's, the class kept; (6) GOV.UK's link focus shadow replaced by the workspace's inset ring; (7) the `h3` rule removed (Datasets and Operations, 6 cases); (8) a second `h1` |
| `lint.log`, `vitest-full.log`, `keyboard.log`, `axe.log` | The gates, each naming the head it ran at (all rerun after the last rebase onto main; the plants at the head before it, with nothing of this step changed since): tsc and eslint clean; vitest 3466; the sections' look spec, People's, `admin.spec.ts` and `operations-figures.spec.ts`, 80 passed; axe in dark, light and GOV.UK on every admin-harness state (two new: Dashboard identities and Demo packs under `serve=packs`) and on the figures' own harness, 116 passed |

Shared files changed in the branch:
- `keyboard/admin-harness.tsx`: a `serve=packs` block, just before the render;
- `a11y/every-harness.spec.ts`: two states at the end of the Admin list.

The platform lane's branch adds its own blocks above `serve=people` and after `open=connections`. Whichever of us
merges second rebases.

**The lane review** (14 November) found the following.
- Must fix:
  - the `h3` rule would have restyled Models' and Maps' `h3`s. Platform's step, merged first, made those `h2`s, so
    only Datasets and Operations draw `h3`s now;
  - the focus test's "black bar" line also matched the workspace's own GOV.UK ring. The shadow is now compared
    entire, and plant 6 shows it red.
- Should fix, all done:
  - each `h2` and `h3` is held at its token's size;
  - Operations' figures nest as Datasets' details do;
  - the harness serves every part of the figures, and the spec waits on *Budget alerts*, drawn only once they are
    read;
  - the figures' own harness is run;
  - the one-`h1` check is planted;
  - the Amendment's wording on System and on the side navigation's focus is corrected;
  - the stale `actionRegistry.ts` exclusion is out of `plants.py`.

Kept, and said here:
- Amendment 16 is extended in place, as the step was given under it, and its reservation row still reads
  "reserved". The orchestrator rules whether this wants an amendment of its own.
- Datasets' `h3`s are 16px under 19px prose in GOV.UK. That is larger than main's `h5`, and below the `h2` they
  belong to.
- `govuk_admin/plants.py` runs at its own head: its `h2.value` plant names a rule this step generalised.
