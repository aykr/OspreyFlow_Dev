# rules-b · L2.12 · patches for other lanes' files (the orchestrator's ruling of 8 November)

Each was built and tested in this worktree, saved with `git diff`, then reverted; each applies to the
branch's head alone and all three together (`git apply --check`). Pass each to its owner's next step,
or apply it at the merge if the owner has finished with those files.

| Patch | Owner | What | Its test, red first |
| --- | --- | --- | --- |
| `canvas-badge.patch` | case (`canvas/GlassCanvas.tsx`) + `App.tsx` | ADR-146 decision 9: the canvas's alert badge, `reports/alertBadges.tsx`'s overlay mounted beside the judgements' badge, App reading the reader's own queue | `reports/alertBadges.test.ts` (on the branch); App and canvas suites green with it applied (512) |
| `admin-tips.patch` | admin (`admin/AdminPlace.tsx`, `admin/sections/Roles.tsx`, `AdminPlace.test.tsx`) | ADR-145 Amendment 4 decision 12: each right's tip from `help/roles.ts`, read with its box (`aria-describedby`); *Roles, teams and Authors* opened from Admin | `AdminPlace.test.tsx`'s new case; admin suite green with it applied (88) |
| `see-the-trend.patch` | rules (`alerts/AlertQueue.tsx`, `alerts/RulesPlace.tsx`) + `App.tsx`, `App.test.tsx` | ADR-145 Amendment 4 decision 9: *See the trend* on an alert opens the Alert monitoring board filtered to its rule group and period | `App.test.tsx`'s `See the trend opens the Alert monitoring board …`, red with the button removed |

Not yet built anywhere: the Studio's door to the help page (studio's review, accept-type and merge
screens, which L3.4 and L1.x build) and the boards' Alerts panel mount (L3.3). Both take
`help/RolesHelpPage` and `reports/AlertsPanel` as they stand.
