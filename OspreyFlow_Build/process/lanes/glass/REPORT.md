# glass lane · report · L2.3 part 2, variant B of the case screen's lightening, after review (7 November 2026)

1. **Variant B in the product: met.**
   - The column opens with the Inspector only (`layout/SidePanelStack.tsx`, `DEFAULT_FOLDED`).
   - The rail keeps Cases and Explore; Ownership, History, Questions and Dashboards are under its ⋯ More.
   - The view switch keeps Graph and Map; Matrix and Reports are under More views.
   - Monitoring's open count is on the banner's section.
   - The GOV.UK banner's leading "·" is gone. `canvas/**` is untouched.
2. **Count: met.** `App.chrome.test.tsx` counts 24 controls before the canvas on the real `App` (25 with the deployed skip link); part 1's figures were one short. It goes red with Ownership back on the rail. The test reads document order, not a real Tab walk, which needs the stack; its docstring says what that can miss.
3. **Column parts: met.** `keyboard/case-screen-parts.spec.ts` counts the real panels: the Inspector has at most 7 parts for a node (6 for a link), Metrics 3, the Query builder 3. So today's column shows up to 13 parts and B up to 7 (the prototype's stand-in said 15 and 8). ADR-145 Amendment 2 §5 is corrected.
4. **Banner count: met.** With an open, a claimed and a closed alert, `App.chrome.test.tsx` checks the banner says "Monitoring 2 open". It goes red when `App` doesn't pass the count.
5. **Keyboard: met.** `shell.spec.ts` covers each destination under More (Escape returns to ⋯), More views and the folded panels, each red with its handler removed. ⋯ More and More views mark the view open with `aria-current` (red with it removed). Full suite: see 9.
6. **Axe: met** in dark, light and GOV.UK, now covering:
   - Monitoring's badge, including inside the GOV.UK notification banner;
   - ⋯ More and More views drawn open;
   - the column's fresh-page default.
   The badge scan found a real defect: the Monitoring button's name omitted its visible text (WCAG 2.5.3). It is fixed: "Monitoring 3 open".
7. **Vitest:** 2626 pass, 1 fail: the Matrix first-frame budget (`MatrixView.budget.test.tsx`) failed in the full run, as on earlier runs. The orchestrator is measuring main's own status on a quiet machine, and I left it alone.
8. **Docs: met.** ADR-145 Amendment 2 and `spec/02` give the measured figures. The DEMO_GUIDE (§8a, the Reports and Dashboards steps) is updated, plus a friction row.
9. **Commits:** on `lane/glass`, rebased on main. **Full keyboard suite: 563/563** on 5185 under `CI=1`, in one run after the last change.
10. **Requests:** the three `SHELL_ACTIONS` ids (diff sent). `DropdownPanel` is left as it is: a `className` prop alone would not let the rail's icon trigger reuse it.
11. **Hand check** (use a fresh browser profile or clear the site's storage, since the column's default applies only when nothing is stored). From `OspreyFlow_Core`: `.venv/bin/ospreyflow start --build`, then `.venv/bin/ospreyflow open`. As the analyst, open a case:
    - The Inspector is open; Metrics and the Query builder are folded.
    - The rail shows Cases, Explore and ⋯.
    - ⋯ → History works.
    - More views → Matrix works.
    - The banner reads "Monitoring" with its count.
    - Repeat with `?brand=govuk`: the banner has no leading "·".
12. **Still running:** nothing. No dev stack or lease used.
