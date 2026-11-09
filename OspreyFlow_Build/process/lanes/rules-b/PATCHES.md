# rules-b · L2.12 · patches for other lanes' files (the orchestrator's ruling of 8 November)

Each was built and tested in this worktree, saved with `git diff`, then reverted. Each applies to the
branch's head alone (`git apply --check`); together, apply them in this order with `git apply --3way`
(the badge's and the trend's `App.tsx` hunks are neighbours): `see-the-trend`, `canvas-badge`,
`admin-tips`, `registry-L2.12`. All four applied: 850 unit cases (App, alerts, admin, canvas, reports,
home, help) and 87 keyboard cases (rules-place, admin, alert-figures, reports, shell) passed, after review
round 1. Pass each to its owner's next step,
or apply it at the merge if the owner has finished with those files.

| Patch | Owner | What | Its test, red first |
| --- | --- | --- | --- |
| `canvas-badge.patch` | case (`canvas/GlassCanvas.tsx`) + `App.tsx` | ADR-146 decision 9: the canvas's alert badge, `reports/alertBadges.tsx`'s overlay mounted beside the judgements' badge, App reading the reader's own queue | `reports/alertBadges.test.ts` (on the branch); App and canvas suites green with it applied (512) |
| `admin-tips.patch` | admin (`admin/AdminPlace.tsx`, `admin/sections/Roles.tsx`, `AdminPlace.test.tsx`, `keyboard/admin.spec.ts`) | ADR-145 Amendment 4 decision 12: each right's tip from `help/roles.ts`, beside its box and read with it (`aria-describedby`); the box's name from `roles.ts`'s `rightName` (Admin's `rightWords` becomes it); *Roles, teams and Authors* opened from Admin | `AdminPlace.test.tsx`'s new case; `admin.spec.ts`'s tip-and-help case, red with `aria-describedby` removed; axe on Admin's harness (56) after 2.5.3 failed with the tip inside the label |
| `see-the-trend.patch` | rules (`alerts/AlertQueue.tsx`, `alerts/RulesPlace.tsx`, `keyboard/rules-place-harness.tsx`, `rules-place.spec.ts`) + `App.tsx`, `App.test.tsx` | ADR-145 Amendment 4 decision 9: *See the trend* on an alert opens the Alert monitoring board filtered to its rule group and period | `App.test.tsx`'s `See the trend opens the Alert monitoring board …` and `rules-place.spec.ts`'s keyboard case, each red with the button's handler removed; axe on R&M's harness (16) |
| `registry-L2.12.patch` | shared (`keyboard/actionRegistry.ts`) | `ALERT_FIGURES_ACTIONS` (8 ids); `REPORTS_ACTIONS` loses the Dashboards tab's id; `ADMIN_ACTIONS` +2 and `RULES_PLACE_ACTIONS` +1 for the patches above (commit those ids with their patch) | each id's case, red with its handler removed (RED_RECORD §8, §9) |

Not yet built anywhere: the Studio's door to the help page (studio's review, accept-type and merge
screens, which L3.4 and L1.x build) and the boards' Alerts panel mount (L3.3). Both take
`help/RolesHelpPage` and `reports/AlertsPanel` as they stand.
