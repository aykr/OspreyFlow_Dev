# glass lane · report · L2.3 part 2, variant B of the case screen's lightening (7 November 2026)

1. **Variant B in the product: met.**
   - The column opens with the Inspector only (`layout/SidePanelStack.tsx`, `DEFAULT_FOLDED`); the column's host is the lane's own, so `canvas/**` is untouched.
   - The rail keeps Cases and Explore; Ownership, History, Questions and Dashboards go under its ⋯ More (`shell/LeftRail.tsx`).
   - The view switch keeps Graph and Map; Matrix and Reports go under More views (`shell/TopBar.tsx`).
   - Monitoring's open count moves to the banner's section. The GOV.UK banner's leading "·" is gone.
2. **Count: met, with a correction.** `App.chrome.test.tsx` counts the real `App`: 24 controls before the canvas, 25 with the deployed skip link. Part 1's harness drew the mark without its Home button, so all its counts were one short; today is 29 (30). The test is red with Ownership back on the rail. The column test (Inspector open, the rest folded) is red with the default removed.
3. **Keyboard: met.** New cases in `shell.spec.ts`: each destination under More with Escape back to ⋯; More views; the column's folded panels opening with one keypress. Each is red with its handler removed. Moved cases are updated, not deleted: the rail entries, the views, and `App.test` / `App.matrix.test`, now through the banner's Monitoring and More views. Full suite 562/562 on 5185 under `CI=1`.
4. **Axe: met** in dark, light and GOV.UK: 48 harness scans and 12 real screens. **Vitest:** 2627 pass, 1 fail, the load-only Matrix budget, which passes alone.
5. **Docs: met.** ADR-145 Amendment 2 is written with the corrected count. `spec/02` covers the rail, the view switch, the column's default and §2.0a's count. DEMO_GUIDE §8a and step 4 are updated. The friction row is in.
6. **Request:** the three `SHELL_ACTIONS` ids as a diff (sent): `rail-more-by-keyboard`, `more-views-by-keyboard`, `open-a-folded-panel-by-keyboard`.
7. **Hand check.** From `OspreyFlow_Core`: `.venv/bin/ospreyflow start --build`, then `.venv/bin/ospreyflow open`. As the analyst, open a case:
   - The column shows the Inspector, with Metrics and Query builder folded.
   - The rail shows Cases, Explore and ⋯.
   - ⋯ → History works.
   - More views → Matrix works.
   - The banner's Monitoring carries the count.
   - Repeat with `?brand=govuk`: the banner has no leading "·".
8. **Still running:** nothing. No dev stack or lease used.
