# glass lane · report · L2.2 three places (7 November 2026)

1. **Each role sees only its places, and the hidden places' routes refuse it: met, with three crossings held open by your ruling.** `tests/services/api/test_place_routes.py` (11 pass, 3 strict xfail) assigns every route to the places whose screens call it. It checks `shell/places.json` against the routes' rights, then calls every route of each hidden place as each role and Super user, expecting 403 `right_required`. It went red with `invite_person_route`'s and `list_studio_recipe_drafts`'s `require_right` removed. The switcher side is covered by `shell/places.test.tsx` and `rights/visibility.test.ts`.
2. **`keyboard/shell.spec.ts`: met.** It covers the switcher under both brands, the banner's cross-link (keeps the case) and Home's cards; each went red with its handler removed. The full keyboard suite passes, 534 of 534.
3. **Axe in dark, light and GOV.UK: met.** `a11y/every-harness.spec.ts` covers `places-harness`, `start`, `shell`, `top-bar` and `admin`, with the banner in each place (34 pass); `a11y.spec.ts` passes 12 of 12.
4. **`spec/02` rewritten: met.** §2.0 is updated and a new §2.0a is added; the rail, Home, Admin and launcher passages are corrected. The citation and product-tree gates are green.
5. **DEMO_GUIDE: met, text only.** §3.7a now reaches the Studio from the switcher; §8a says what moved. Friction fragment: `process/friction/2026-11-07-glass-three-places.md`.
6. **Left.** "Feeds n cases" in the Studio banner is not drawn: no route counts a dataset's cases as the reader may see them, and an unfiltered count would break rule 7. *Boards* waits for Lane 3. The GOV.UK banner is a full notification banner, so it is taller than one line.
7. **Commits (branch `lane/glass`, not pushed):** 8594a6b, 2975a72, 9b85f57, 01a766c, 174154d, ddff049, and the commit holding this report.
8. **Requests to the orchestrator.**
   - (a) An ADR-112 amendment and the `packages/schemas/rights.py` change: the Analyst loses `add_ingest_files`, the Admin loses `schedule_pipelines`.
   - (b) Lane 1: `/v1/ingest/schedule-preview` must also accept `operate_schedules` before (a) lands, or Admin › Operations breaks. `GET …/ingest/recipes/{id}/runs` needs a pipeline right, not `read_data_feeds`.
   - (c) When (a) and (b) land, the strict xfails turn red; delete them from `AWAITING_*`.
   - (d) Add three registry ids to `SHELL_ACTIONS`: `switch-place-by-keyboard`, `banner-cross-link-by-keyboard`, `home-place-cards-by-keyboard`.
   - (e) Reserve an ADR-132 amendment for the local GOV.UK header slot (6.6.0's header has no navigation).
   - (f) Note in ADR-115 that decision 7's greyed-out panels are superseded.
   - (g) Add `App.tsx`, `rights/**` and `a11y/every-harness.spec.ts` (one line edited) to the ownership map.
9. **Questions for the owner.** None open. Your rulings: rights decide, narrowed; Proposed types goes into Admin for now; glass edits `App.tsx` and `rights/visibility.ts`.
10. **Hand check.** From `OspreyFlow_Core`, run `.venv/bin/ospreyflow start --build`, then `.venv/bin/ospreyflow open`. Sign in as each person below, then repeat the walk with `?brand=govuk` on the URL:
    - **Analyst** (`osprey-demo-analyst`): Home shows the Glass card. Until (a) lands it also shows the Studio card, so this check confirms the hold. Open a case: the bar shows *Places*, and the banner reads "You are in the Glass · Case … · reads …". The rail has no Studio and no Admin.
    - **Data engineer** (`osprey-demo-engineer`): Home shows three cards. In the Glass, press *Open … in the Ingest Studio ↗*. The Studio has no rail; press *← Back to case … in the Glass* and the same case and view return.
    - **Administrator** (`osprey-demo-admin`): open *Admin* from the switcher. The banner reads "You are in Admin". The *Proposed types* tab opens the proposals. Under GOV.UK, the places sit in the blue header.
11. **Still running.** Nothing of mine. The Playwright and Vite processes still running are the studio lane's (`studio-a7`). No dev stack and no lease were used: every test ran without the stack.
