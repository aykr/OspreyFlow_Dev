# docs lane · report · D2a, the README, the guides, the welcome page and the website as built (10 November 2026)

**Gated head d820afb, on main 984194c** (rebased once, after L2.7, L1.5 and P5 merged, and not again). Every gate below ran at that head; the commits after it are this report and the gate records only. Round 1 was reported at c6941e0; this report replaces it, after the orchestrator's independent review and its re-review.

1. **Exit.**
   - *Guides build to PDF:* met. Four guides printed at user 1.41, administration 1.63, developer 1.31 and architecture 1.1 (`docs/pdf/`, `test_docs_pdf.py` green).
   - *Docs gates:* `make citation-check product-tree-link-check provenance-annotation-check demo-guide-check no-branches-check` green; `test_doc_site.py`, `test_admin_guide.py`, `test_website_wording.py` and `test_guide_role_words.py` green. `make -k ci` here is green but for the 11 Docker targets (Docker off): `gates/d820afb.ci.txt`. `make test` on the server through `stack_lease.sh offline docs`: pytest 10,065 passed, 2 failed (the server's GPU preflight, the closed Valkey port), and vitest 2,892 passed, 1 failed (MatrixView's budget under load). All three fail on main too and are explained in `gates/d820afb.test.txt`.
   - *Claims traceable:* each was checked against read-only fact sheets taken from the code (Glass, Admin, Studio; then L3.4; then L2.7, L1.5 and P5), the lane reviewer, and the orchestrator's independent review and re-review.
   - *Friction row:* `friction/2026-11-09-docs-guides-as-built.md`.
   - *Welcome:* `WelcomeAbout.test.tsx` has three cases, shown red by four plants and green restored (`gates/bfb8257.welcome-plants.txt`). The sign-in axe passed 12/12 in dark, light and GOV.UK, and keyboard 6/6 (`gates/d820afb.axe-sign-in.txt`, `d820afb.keyboard-sign-in.txt`).
2. **Done.**
   - *README:* a draft for the owner at `process/lanes/docs/README_DRAFT.md`, kept outside `OspreyFlow_Core` because `tools/publish_user_repo.py` exports every committed file there. `OspreyFlow_Core/README.md` is main's until the owner approves.
   - *User guide:* Home, with *What you can do, and what you answer for* and *Needs you*; the four places; no branches; home cases, Authors and teams; levels and roles in `help/roles.ts`'s words; views; drawing boards; *Promote…* and its review; the board's Alerts panel and the canvas badge; link types; *Find a place*; Figures; Dashboards; the Reports Viewer's journey.
   - *Administration guide:* Admin's sections, with Proposed types gone, Grading scheme built and Connections' four kinds; roles and every right in `roles.ts`'s words, with the tips and the refusal that names roles; custom roles; Super user; teams; Disable; datasets and Authors; a removed case's layer, where the screen offers dry runs and the route exists; Operations, with promotions waiting and overdue; Audit; Models; Maps, with `map build --unit` and a dataset's gazetteers; the backups folder, *coming*.
   - *Developer guide:* the Studio's four steps, with Analyst promotions and Removed cases' layers in 4 Runs; *Make live*'s owner step; connectors; staging; the expert steps (§3.4b); the analyst layer; promotion and its review and revert; and every new route, L3.4's and the gazetteers' among them.
   - *Architecture guide.*
   - *Spec 10:* its §9 and §10 mirror the guide's.
   - *Website:* drawing boards and four places, marked Built or Coming; nav labels; the home page; Rules and Monitoring on monitoring; the four places in the GOV.UK header.
   - *Test:* `test_guide_role_words.py` holds every copy's role, level, place and right tables, and `PLACE_SAYS`, to `roles.ts` and `placesByRole.json`. Each copy's role table must list all five built-in roles, plus the Super user where it lists places; a name `roles.ts` does not know fails. Seven plants were red and green restored (`gates/bfb8257.role-words-plants.txt`). The renamed, dropped and Super user cases are pinned in the file.
3. **Waits for L2.10 and L2.11:** user guide §7 and administration guide §9.4–9.6 (one queue, what raises alerts, watches, team routing, *Raise an alert*, the rule editor; screening lists' place), with a note on each; `monitoring.html` beyond its place name; the welcome page's monitoring words.
4. **Marked coming, not built on main:**
   - Figures' *Drawing* panel: the Glass has it, but no Conduit code fills `ReportFigures.drawing` (`domain.py:1381`).
   - Admin › Datasets' merge and delete on screen: `Datasets.tsx:422`; its delete route exists.
   - Merging a drawn dataset into another.
   - An alert when new data meets a drawn item, and drawn items on the analysis canvas.
   - Releases as YAML, and the Studio's *Make live* screen.
   - Admin's Approval rights and Uploads.
   - Team case levels and routing.
   - The Disable panel reading the ownership route (L2.5b).
   - A dataset's gazetteers on screen (P6).
   - The backups folder at setup (P5b).
5. **Captures needed** once a deployment runs (default and GOV.UK):
   - user: 03-start (Home, *What you can do*, *Needs you*), 05-canvas (Save as a view), 07 and 08 (Figures, Dashboards), 09, 13, 21;
   - developer: 01, 02 (with an expert step), 04 (four steps), 10, 11;
   - admin: 01 (Disable…, Super user), 03, 04 (Operations), 05 (System);
   - new: boards, the promotion sheet, Analyst promotions, a view's lens, *Find a place*, Admin Roles with tips, Datasets, Grading scheme, Models, Maps, Audit, Rules and Monitoring;
   - the website's two pages.
6. **Reviews.**
   - *Lane review:* one round, 6 must-fix and 5 minor, all fixed.
   - *Independent review of c6941e0:* L3.4 as built; the role-words test; the welcome plants recorded; the README kept a draft. Minors: the scanned commit named; Disable's button; the alert route's place gate; Small publishing 443 alone; *Start here*; §7.1; spec 10's blank lines. All fixed.
   - *Re-review of 1f53dbd:* the draft out of `OspreyFlow_Core`; gates at one head; the role tables held whole; the welcome drift case calling its check; developer guide 4 Runs, §9.1's L3.4 routes and Admin's delete route. All fixed.
   - *Passed to case through CARRIES:* *Promote…* shown before the route's Author and `promote_to_dataset` check; *Analyst promotions*' refusal words.
7. **Decisions taken** (yours to overrule):
   - (a) The README's "See/Where/Do" is read as *what you see, where you work, what you may do*.
   - (b) `three-places.html` keeps its file name, retitled *Four places*.
   - (c) Document control stays *For OspreyFlow v0.4.12 · Issued*.
   - (d) The welcome page names places from `PLACE_WORDS`, but says what each is for in the guides' words, held to them by the test.
   - (e) Spec 10 mirrors §9 and §10 only.
   - (f) The guides' version history says the 10 November changes in their own rows (1.40–1.41, 1.61–1.63, 1.29–1.31, 1.1), rather than rewriting the unissued 9 November rows.
8. **Requests:**
   - Ratify `tools/docs_pdf.py`, `tools/doc_site.py` (GUIDES and *Start here*), spec 10's commits and `tests/test_guide_role_words.py`.
   - The owner of `help/roles.ts`: its Ingest Studio and Rules and Monitoring sentences still claim releases and one queue (a carry for rules).
   - Case: a home case's removal (a carry).
   - Publish only after `publish_pages.sh` copies the two pages (in MORNING.md).
9. **Questions:** none. **Running:** nothing; no stack held.
