# Admin's other sections' headings (ADR-145 Amendment 16, the orchestrator's follow-up of 14 November 2026)

Branch `lane/admin-section-headings`, from main. This is the same pass as People's, applied to Roles, Dashboard
identities, Datasets, Operations (with its figures), System and Demo packs:
- each section heads its parts with `h2`s beneath its `h1`;
- Datasets' details nest `h3`s beneath the dataset's `h2`;
- every `h2` is drawn at `--fs-13` and every `h3` at `--fs-12`, below the `h1` in each look.

Under GOV.UK, a person's row links also carry `govuk-link`, so a focused one takes GOV.UK's focus state. Models and
Maps are the platform lane's, done in its own step.

Browser runs used `OSPREY_PORTS_SLOT=1`. No stack, no server run, nothing on osprey-small, no real data.

| File | What it is |
| --- | --- |
| `look-spec-before.red.log` | `keyboard/admin-sections-look.spec.ts` on main's sections: all 19 cases red. Each section skips a level in all three looks, and the GOV.UK row link has no `govuk-link` |
| `plants.py`, `plants.log` | 5 plants, each planted alone and counted red only when every failure stops at the assertion it names: Datasets' Authors an `h5` again; Roles' form title an `h3` again; the sections' `h2`s at the browser's size (12 cases, the dark and light looks); the row links without `govuk-link`; a local focus rule over GOV.UK's with the class kept. All 5 red |
| `lint.log`, `vitest-full.log`, `keyboard.log`, `axe.log` | The gates at the head each names: tsc and eslint clean; vitest 3464; the sections' look spec, People's and `admin.spec.ts`, 71 passed; axe on every admin-harness state in dark, light and GOV.UK, 104 passed (two new states, Dashboard identities and Demo packs, under `serve=packs`) |

Shared files changed in the branch:
- `keyboard/admin-harness.tsx`: a `serve=packs` block, just before the render;
- `a11y/every-harness.spec.ts`: two states at the end of the Admin list.

The platform lane's branch adds its own blocks above `serve=people` and after `open=connections`. Whichever of us
merges second rebases.
