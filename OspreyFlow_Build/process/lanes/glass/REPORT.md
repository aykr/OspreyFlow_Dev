# glass lane · report · L2.4 part 1, Admin regrouped into sections (7 November 2026)

1. **Sections: met.** Admin is a side list from `admin/sections.json`: People, Data, Running, Policies, Audit, Demo packs. Each section shows only to a holder of its right. Roles, Grading scheme, Approval rights, Uploads and Audit are "(coming)" placeholders that call nothing. Under GOV.UK the list is a GOV.UK side navigation. Each screen is its own file in `admin/sections/` (Schedules stays put: other lanes import it).
2. **Routes refuse: met (rule 3).** `test_admin_sections.py` (25 tests):
   - derives each section's routes from its screen and that screen's imports;
   - holds each route to the section's right, by declared checks and over HTTP;
   - holds the component `SCREENS` draws to the file the JSON names;
   - finds every `/v1/admin` route some section's.

   It went red with the real egress route's check removed, then naming another right, and with `SCREENS` drawing the wrong file.
3. **Keyboard: met.** `keyboard/admin.spec.ts` (19) adds moving between sections and opening a coming one, each red with the side list's handler removed. **Ids for the registry** (please land them): `move-between-admin-sections-by-keyboard` and `open-a-coming-admin-section-by-keyboard` in `ADMIN_ACTIONS`.
4. **Axe: met.** Dark, light and GOV.UK: the harness now applies `?brand=`, and every section is listed with a placeholder open. Full scan: 384 pass.
5. **Other checks:**
   - Vitest: 2640 pass, 1 fail (the Matrix budget, not ours).
   - Keyboard, full suite: 562 pass, 1 skipped (the L2.3 screenshot case, which needs `OSPREY_L23_SHOTS`).
   - Python: place, section, route-rights and stand-alone tests all pass.
   - lanes-check and the citation checks are green.
6. **Docs: met.** ADR-145 Amendment 3, `spec/02`'s Admin area, the DEMO_GUIDE and a friction row.
7. **Questions to the owner** (settled by the orchestrator): Q1 the placeholders' rights, (a); Q2 Proposed types under Data, (a); Q3 Approval rights as a placeholder, (a).
8. **Lane-reviewer findings and what was done:**
   - (1) `SCREENS` was held to nothing: fixed, with a new test shown red.
   - (2) The place test's exemptions were skipped for every section: now each skip is named per section, with its reason.
   - (3) DEMO_GUIDE is outside the map: **please ratify.**
   - (4) This report: written.
   - (5) Administer_system alone now lands on Datasets, not System: recorded in Amendment 3; the place test's `ENTRY` was updated.
   - (6) The scanner's blind spots: stated in its docstring.
   - (7–9) A wrong count, overstated red claims and a stale citation: corrected.
   - (11) Sub-headings: now h4.
   - (12) Wording: "link-styled buttons".
   - (10) Duplicated `utc` and handling-scheme reads: left; the move kept them as they were.
9. **For the owner:** a holder of `operate_schedules` alone sees Operations, but the schedule preview (`schedule_pipelines`) refuses them. This predates the lane, is recorded in Amendment 3, and nothing was changed.
10. **Still running:** nothing. No dev stack and no lease.
