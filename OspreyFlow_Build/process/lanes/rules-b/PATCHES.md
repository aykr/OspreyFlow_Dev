# rules-b · L2.12 · patches for other lanes' files (the orchestrator's ruling of 8 November)

Each was built and tested in this worktree, saved with `git diff`, then reverted. **They apply after this
branch lands, not to `main` alone:** each is made against the branch's own files (`help/roles.ts`,
`reports/alertBadges.tsx`, the board, the registry's L2.12 ids), so each applies to the branch's head on
its own (`git apply --check`), and to `main` once L2.12 is merged; the orchestrator passes the three to
their owners then (the orchestrator's review, 9 November). Together, apply them in this order with `git apply --3way`
(the badge's and the trend's `App.tsx` hunks are neighbours): `see-the-trend`, `canvas-badge`,
`admin-tips`, `registry-L2.12`. All four applied together, after the orchestrator's review's fix round
(Admin's tip now `rightSays`): 866 unit cases (App, alerts, admin, canvas, reports, home, help) and 87
keyboard cases (rules-place, admin, alert-figures, reports, shell) passed. Reversing them in turn fails
at `App.tsx`'s neighbouring hunks; restore those files from the branch instead. `registry-L2.12.patch` goes in with the merge itself (the branch's keyboard coverage needs it).

| Patch | Owner | What | Its test, red first |
| --- | --- | --- | --- |
| `canvas-badge.patch` | case (`canvas/GlassCanvas.tsx`) + `App.tsx` | ADR-146 decision 9: the canvas's alert badge, `reports/alertBadges.tsx`'s overlay mounted beside the judgements' badge, App reading the reader's own queue | `reports/alertBadges.test.ts` (on the branch); App and canvas suites green with it applied (512) |
| `admin-tips.patch` | admin (`admin/AdminPlace.tsx`, `admin/sections/Roles.tsx`, `AdminPlace.test.tsx`, `keyboard/admin.spec.ts`) | ADR-145 Amendment 4 decision 12: each right's tip from `help/roles.ts`, beside its box and read with it (`aria-describedby`); the box's name from `roles.ts`'s `rightName` (Admin's `rightWords` becomes it); *Roles, teams and Authors* opened from Admin | `AdminPlace.test.tsx`'s new case; `admin.spec.ts`'s tip-and-help case, red with `aria-describedby` removed; axe on Admin's harness (56) after 2.5.3 failed with the tip inside the label |
| `see-the-trend.patch` | rules (`alerts/AlertQueue.tsx`, `alerts/RulesPlace.tsx`, `keyboard/rules-place-harness.tsx`, `rules-place.spec.ts`) + `App.tsx`, `App.test.tsx` | ADR-145 Amendment 4 decision 9: *See the trend* on an alert opens the Alert monitoring board filtered to its rule group and period | `App.test.tsx`'s `See the trend opens the Alert monitoring board …` and `rules-place.spec.ts`'s keyboard case, each red with the button's handler removed; axe on R&M's harness (16) |
| `registry-L2.12.patch` | shared (`keyboard/actionRegistry.ts`) | `ALERT_FIGURES_ACTIONS` (8 ids) and `REPORTS_ACTIONS` without the Dashboards tab's id: the branch's own ids. `admin-tips.patch` carries `ADMIN_ACTIONS`' two and `see-the-trend.patch` `RULES_PLACE_ACTIONS`' one, so each patch is whole (the gates at b29e8b1 found the coverage cases red with the ids ahead of their patches) | each id's case, red with its handler removed (RED_RECORD §8–§10) |

Not yet built anywhere: the Studio's door to the help page (studio's review, accept-type and merge
screens, which L3.4 and L1.x build) and the boards' Alerts panel mount (L3.3). Both take
`help/RolesHelpPage` and `reports/AlertsPanel` as they stand.

## L2.11a (10 November 2026)

| Patch | Owner | What | Its test, red first |
| --- | --- | --- | --- |
| `registry-L2.11a.patch` | shared (`keyboard/actionRegistry.ts`) | `RULE_STANDARDS_ACTIONS` (3 ids): *Show as BPMN* opened, then closed by Escape and by *Close*, with focus back on the button each time. It goes in with the merge itself, since `keyboard/rule-standards.spec.ts` imports it | each id's case in `rule-standards.spec.ts`, red with its handler removed (l2.11a/RED_RECORD §4) |
| `audit-L2.11a.patch` | admin (`services/api/audit_section.py`) | `export_rule_file` classified in `READS_AND_OTHER`. **The branch needs it at merge:** `test_audit_kinds.py` is red without it (it finds every action the Conduit writes) and green with it (6) | `test_audit_kinds.py`, red at the branch head, green with the patch applied |
| `every-harness-L2.11a.patch` | shared (`a11y/every-harness.spec.ts`) | `EXTRA_STATES` for `rule-standards-harness.html`: the drawing open, and a stored file it does not draw | the axe scan of those two states in dark, light and GOV.UK |
| `spec03-L2.11a.patch` | orchestrator (`spec/03_CONDUIT_MIDDLEWARE.md` §3.8a) | The two routes' rows: Export (`export.{kind}`, Viewer) and Import (`import`, Author), with their refusals. **The branch needs it at merge:** `make ci`'s `route-coverage-check` is red without it (it names both routes) and green with it | `route-coverage-check` at e72588c (red), then with the patch (green) |

All four apply at the branch head (`git apply --check`); the audit patch was regenerated after the rebase onto L2.10's main. `audit`, `every-harness` and `spec03` were applied unstaged for the gates.

## T3 (10 November 2026)

| Patch | Owner | What | Its test, red first |
| --- | --- | --- | --- |
| `a11y-siblings-T3.patch` | shared (`apps/workspace/a11y/{a11y,canvas-focus}.spec.ts`, `apps/harness/a11y/{a11y,install-page}.spec.ts`) | The same undecided-contrast check as every-harness, through `a11y/undecidedContrast.ts`, at each sibling axe scan (the self-check's "every sibling run path"), with the showcase's one finding listed in `a11y.spec.ts` (the warning toast's glyph, design system) | P4 in `t3/RED_RECORD.md`: a 1:1 plant in the harness app, red in 34 of 34; the workspace's scans went red on the toast glyph before it was listed |
