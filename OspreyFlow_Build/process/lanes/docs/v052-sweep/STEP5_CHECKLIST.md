# Step 5, Tue 17 Nov: the wording sweep, its checklist

The docs lane, prepared 14 November 2026 at the orchestrator's word, against main 760ff5b. The route's step 5 row:
"Feature freeze (the moment the last open feature merges) and the wording sweep at once". It is docs', after 3f, 3f′,
3g, 3h and U, and before step 6's install test on Wed 18. It brings the sweep forward from Tue 24.

**Sources:**
- the route (`process/lanes/route.tsv`);
- part one of the sweep (`README.md` beside this file: D1 to D8 and the websites);
- the guide survey of 14 November, against main 016b29a;
- the orchestrator's rulings since;
- the sites' own notes (`marketing_site/sites/README.md`, `process/lanes/docs/sites-v051-facts.md`);
- `CARRIES.md`.

**How each item is marked:**
- **done** names the version row that did it;
- **to do** names the line on main as of 760ff5b;
- **check** means not yet confirmed either way, to be read against the code on the day.

**Rules for the day, as before:**
- The guides say only what is built, so a merged feature's words go in after it merges.
- Each claim is held to the code both ways, and each new assertion is shown red first at its real call site, with a
  fresh `PYTHONPYCACHEPREFIX` each run.
- One version row per guide per branch.
- The PDFs and the CHANGELOG are the orchestrator's.
- spec/10 is mirrored with `--write`.
- British English.

## 1. What the freeze's last features bring (after each merges)

| Step | What | Guide words to write | Status |
| --- | --- | --- | --- |
| 3f, 3f′ | An expansion past the cap promoted to a batch job, ADR-151: the choice on the cap refusal, its progress and result (rules-b, case-b) | User guide §5.2's expand-at-the-cap words (the over-cap dialog), and whatever right or limit it names in the administration guide | to do when merged |
| 3g | The administrator fallback on Entra, audit 4c, ADR-148 Amendment 15 (platform-b) | Administration guide §9's "No administrator can give a missing clearance or unit instead" becomes the fallback as built (part one's D6, 4c); §6a.7 to match | to do when merged |
| 3h | A merged pair arrives as one cluster when nodes enter the working set, rule 6 (case) | User guide: where it says how resolved records are drawn (§5.2, and §5.5's *Show on graph*): check the words against the fix | check when merged |
| U | An upgrade or a fresh install builds the search index, ADR-150 decision 4 (platform) | Administration guide §6a.1's *Moving to a new release* steps and §13's restore: where the index is built on install and upgrade | to do when merged |

## 2. The version headers (the orchestrator's ruling: at the cut)

- [ ] Every guide's header from "For OspreyFlow v0.5.0" to v0.5.2:
  - the administration guide (2.09, line 17);
  - the user guide (1.60, line 18);
  - the developer guide (1.35, line 17);
  - the architecture guide (1.3, line 19).
- [ ] "from v0.5.2" used consistently up to the cut, then read again. Administration guide line 1123 holds one ("Superset
  and the report sync (from v0.5.2: …"). The survey also found reporting, Entra's runs and the search rebuild
  unmarked, so mark them all or none.
- [ ] Version-bound phrases, each checked against v0.5.2. In the administration guide:
  - "After updating to v0.5.0" (line 2369 and one more);
  - "every install before this version" (360);
  - "which this release does not ask for" (1720);
  - "After upgrading to this release, hosted engines receive nothing" (2715);
  - "Sets taken before this release" (2983);
  - "A bundle made before this version" (3067).

  In the developer guide, line 823's example tag `v0.4.1`.

## 3. Navigation wording outside the user guide (ADR-145 Amendments 12 and 15)

The user guide's navigation was rewritten as 1.54, held by `tests/test_user_guide_navigation.py`. The other guides
and the sites were not.

| Where | Says | Becomes | Status |
| --- | --- | --- | --- |
| AG line 2904 (§12) | "the rail's **Dashboards** draws an **Alert monitoring** board" | Reports, on the view switch | to do |
| AG line 2513 (§9.6) | "In the Glass's rail, **Connection strength**" | under **More views** | to do |
| AG line 1197 (§6a.1) | "Questions and Ask stay on Deep read" | Ask & Chat | to do |
| AG lines 895, 2721 (§5a.4, §10) | "Ask the case" | Ask & Chat (and *Whole case*, as user guide §6 names it) | to do |
| AG line 3137 (§15) | "Admin → Schedules and runs" | Operations, with its screenshot (item 6) | to do |
| ospreyflow.org, Home and Features, and the *questions* figure's caption | "Questions" | "Ask & Chat", with the screenshots | to do, with item 6 (`sites-v051-facts.md`) |
| A test | Nothing holds the other guides' navigation words | Extend `test_user_guide_navigation.py`'s reading of `railLayout.ts` to the administration guide's mentions, red first | to do |

## 4. Search wording (left as it was until now, the orchestrator's ruling)

| Where | What | Status |
| --- | --- | --- |
| DG §1, ArchG §2 | The third narrow port, `IndexFeedSource`, is named in neither guide | to do; check spec 00 and 04 too (the survey found them silent) |
| ArchG line 62 (§2) | "OpenSearch or PostgreSQL full-text" | check against `postgres-fulltext` on main (`packages/schemas/deployment.py`); the survey found graph search marked limited |
| ArchG §8, §6, §10 | Rows for the index feed and search; the access filter in `search_access.py`, said in rule 3's words; embeddings in search (there are none) | check |
| DG §1, §3.9, §7.5, §9.3, §9.5, §9.1 | OpenSearch's role, the pending index, the search document's `withhold_sources`, the rebuild and drift scripts, a restore's rebuild, the search and suggest shapes | check each |
| UG §5.5 | The suggestions' no-index line, and the box's filters and their limits, against the box's code (the survey: "Suggestions are limited just now…", a 50-character limit). Neither is in the guide | check, then add with assertions |
| AG §6a.5, §6a.11 | `opensearch_signing` (on main: `harness/cloud_platform/settings.py`, `runbooks.py`) is named in no guide; §6a.11's question on an IAM-only OpenSearch policy without fine-grained access control, and two subnets in two zones (part one's D8) | to do |
| ospreyflow.org | The overview's Vault chip "OpenSearch or PostgreSQL", and every search claim | check with section 6's re-check |

## 5. Rulings and flags

- [ ] **R7:** "Mark for suppression" is named in user guide §5.2 (line 328) because it is on screen. Its ruling (27
  September) is tentative. Flag it to the orchestrator for the owner. The guide keeps the name until ruled.
- [ ] Part one's D-items:
  - D1, owner resolution: done (AG 1.98).
  - D2 and D3, data safety and the decommission: done (AG 1.96, 2.01, 2.03, 2.05).
  - D4, reporting: done (AG 1.97). §9's dashboard refusal is gone (2.01).
  - D8, OpenSearch on the poc: done in part (AG 2.00), the rest in section 4.
  - D5, the manifest's tables: check whether the command exists yet.
  - D6: 4b done (AG 2.02), 4c with 3g, 4d not ruled.
  - D7, acceptance: not until step 6 runs (Wed 18), after this sweep.

## 6. The sites

- [ ] At the cut, re-check every release-marked claim against v0.5.2 and set `CHECKED_AGAINST` to `v0.5.2`. `build.py`
  refuses to build until then.
  - "On main, coming next" moves into the release, or out: scheduled runs, reporting and the data-safety fixes.
  - The second extraction engine's "no screen uses it yet": check.
  - The gateway's "a stand-in gateway alone": check against step 6.
  - Record it all in a new facts file.
- [ ] The search wording (section 4) and "Questions" (section 3) with the screenshots.
- Not in the sweep: the screenshots (item 6), after the cut, from the rebuilt demonstration, on the orchestrator's
  word.

## 7. Built since the guides said "coming"

- [ ] DG §7.8 line 790 and ArchG §5 line 149: "**Coming:** merging a drawn dataset into another". `drawn_merge.py` and
  its routes are on main, so check the screens and write it as built.
- [ ] DG §8 line 800's "(coming)" in the alerts journey: check.
- [ ] DG §7.5's writers list: the survey found `drawn_merge`, `case_gazetteers` and grading missing. Check.

## 8. v0.5.1's own gaps (check whether still open)

- [ ] UG §2: a refresh signs in again silently and returns you where you were (ADR-050 Amendment 3).
- [ ] UG §4: the GOV.UK look's slim header and one-line banner inside a case (ADR-132 Amendment 8). "slim header"
  and "one-line banner" are in no guide on main.
- [ ] ArchG line 102, "One set of images, three modes", against the shared-platform profile.
- [ ] AG §14's table: a cloud-platform row. Also check the opening audience line.

## 9. Tests to close (the survey's gaps)

- [ ] `test_section_9_quotes_each_entra_people_refusal` holds code to guide only, so a refusal the code dropped stays
  in the guide. Hold it both ways, red first.

## 10. Screenshots marked, for item 6 (not the sweep)

- [ ] The user guide's five `<!-- needs a new capture -->` marks (lines 288, 311, 386, 443, 848). Each shows the rail
  and banner before ADR-145 Amendment 15.
- [ ] AG §15's Operations screenshot (section 3).
- [ ] The sites' images.
