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

`a11y-siblings-T3.patch` (the same undecided-contrast check at the sibling axe scans: `apps/workspace/a11y/{a11y,canvas-focus}.spec.ts`, `apps/harness/a11y/{a11y,install-page}.spec.ts`) was ratified by the orchestrator to go in directly. It is in the branch, and the patch file is gone.

## guides (12 November 2026)

| Patch | Owner | What | Its test, red first |
| --- | --- | --- | --- |
| `registry-guides.patch` | shared (`keyboard/actionRegistry.ts`) | `START_ACTIONS` gains `read-a-place-s-guide-from-home-by-keyboard` and `read-why-a-guide-was-refused-on-home-by-keyboard`. It goes in with the merge itself, as `start.spec.ts` proves both | each id's case in `start.spec.ts` (the browser gate's record in `gates/`) |
| `docs-guides.patch` | docs (`docs/user-guide.md` §3 Home, `docs/administration-guide.md` §9.1) | A line each: the guide under each card, opened in a new tab, only with a card the person's roles open, checked again by the Conduit; the version the deployment was built with. The PDFs and `manifest.json` are re-rendered by docs as usual | none of the lane's: a docs change. The byte-for-byte test reads whatever `docs/pdf/` holds, so a re-render keeps it green |
| `every-harness-guides.patch` | shared (`a11y/every-harness.spec.ts`) | The start harness's `guide=refused` state: Home with the administration guide refused, its words under its link, scanned in dark, light and GOV.UK | `start.spec.ts` *the harness's refused state … shows the refusal under its link* (red with a refusal's words dropped); 18 passed with it applied (`gates/02f3752.browser.txt`) |
| `spec03-guides.patch` | spec (`spec/03_CONDUIT_MIDDLEWARE.md`, beside `/v1/me/rights`) | `GET /v1/guides/{guide}`'s row: who, the place check, 403 `place_required`, 404 `no_such_guide`, 503 `guide_not_carried`. **Needed at merge:** `route-coverage-check` is red without it | `make route-coverage-check`: red at the branch head, green with the patch applied (420 routes, no drift) |
| `spec02-guides.patch` | spec (`spec/02_GLASS_FRONTEND.md`, Home) | The guides under the Glass's, the Studio's and Admin's cards: a link whose activation is handled, shown from a blob or saved under its name, failures in words (rule 11) | none: spec prose |

## v052D (13 November 2026)

Each applies at the branch head (`git apply --check`). The bar and registry patches were applied for the slot-9
browser run (21/21 keyboard green) and then restored.

| Patch | Owner | What | Its test, red first |
| --- | --- | --- | --- |
| `audit-v052D.patch` | admin (`services/api/audit_section.py`) | `will_read_question` classified with the reads. **The branch needs it at merge.** | `test_audit_kinds.py`: red at the branch head, green with the patch |
| `spec03-v052D.patch` | orchestrator (`spec/03_CONDUIT_MIDDLEWARE.md`) | The questions route's row rewritten for `read_from`, the `read` summary, `nothing_to_read`, `read_from_unavailable` and no `no_documents`; the will-read route's row; the Editor table's `questions/will-read` (POST). **The branch needs it at merge.** | `route-coverage-check`: red without (names `POST …/questions/will-read`), green with |
| `registry-v052D.patch` | shared (`keyboard/actionRegistry.ts`) | `QUESTIONS_ACTIONS` gains `choose-what-to-read-from-by-keyboard`. Goes with the merge (the spec registers it). | `questions.spec.ts`'s new case, red with the radios' handler a no-op (`keyboard-plant.txt`) |
| `bar-v052D.patch` | case (`canvas/SelectionBar.tsx`, `SelectionBar.test.tsx`, `canvas/GlassCanvas.tsx`, `keyboard/selection.spec.ts`) | ADR-144 Am 4: *Ask the model about these…* whenever anything is selected (no `documentCount`); the view named "Questions on n items". Case-b folds it into Part C's shared action list if that lands first. | `SelectionBar.test.tsx`'s *whatever is selected*; `selection.spec.ts`'s Ask case (green applied) |
| `user-guide-v052D.patch` | docs (`docs/user-guide.md` §6) | Read from, About, Will read, the engine, no-documents answers, Ask for any selection; "needs at least one document" removed | — (prose) |
