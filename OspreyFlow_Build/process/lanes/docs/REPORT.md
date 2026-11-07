# docs lane · report · first brief (the website), 7 November 2026

1. **Pages.** New `drawing-boards.html` (ADR-143: boards, analyst layer, grading, matching, own link types, promotion, alert) and `three-places.html` (ADR-145: places, banner, Admin sections, custom roles, GOV.UK header). `index.html`: two "(coming)" nav links and a `#coming` section, via the template's own encoding. `monitoring.html`, `public-sector.html`: nav and footer links. `README.md`: the two pages and how to move a section from Coming to built.
2. **Marked coming, and why.** Every section of both pages and the home section carries a "Coming" mark: ADR-143 to ADR-145 are accepted design, "Not built". No screenshots; nothing of it is built. Nothing was described as newly built: the alerts gap map is a design document and no screen has merged, so I claimed nothing from it.
3. **Exit criteria.**
   - Pages render: all five served with `python3 -m http.server`, HTTP 200. Met.
   - Every new claim marked coming: by reading. No test enforces it. Met, unproved by a test.
   - British English: read through, no American spellings found. Met.
   - No broken local links: a scratch link and fragment check found none in new or edited pages (the home page's `{{ repoUrl }}` placeholders and bundle image ids already existed; the README records them). Met.
   - Wording rule: `tests/test_website_wording.py`, 31 passed (it covers the new pages automatically).
   - Friction fragment: `process/friction/2026-11-07-docs-website-coming-pages.md`.
4. **Not done.** Dark, light and GOV.UK axe scans: these are static pages, not product screens, and no scan harness covers them; the pages use the site's own light/dark tokens. The browser look was by HTTP check only, not by eye.
5. **Pages needing new captures** once L2.2 and the boards (L3.3, L3.4) merge: `three-places.html` (switcher, banner, Admin sections; default and GOV.UK themes), `drawing-boards.html` (blank board, link drawing, promotion sheet, Analyst promotions list), and the home page's `#coming` section.
6. **Commits.** db64770 (site pages); a second commit holds this report.
7. **Requests to the orchestrator.** (a) A test in `tests/` that every local link and fragment in `marketing_site/deploy/*.html` resolves and that `drawing-boards.html` and `three-places.html` have no section without a "Coming" mark (rules 12, 15; I do not own `tests/`). (b) The design source `OspreyFlow Site.dc.html` needs the same nav links and `#coming` section before its next export. (c) The guides are untouched, as briefed. Nothing was published or pushed.
8. **Questions for the owner.** When a feature merges, should its page section change to "Built" at once, or wait for your capture of the screens? (a) Change at once, with text only (recommended); (b) wait for captures; (c) wait for you to publish.
9. **Running.** Nothing of mine is running; the local web server was stopped. No dev stack lease was taken.
