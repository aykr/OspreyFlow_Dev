# Build order from 1 November 2026 (autonomous run)

**The owner's instruction (1 November 2026, 09:41):** run the build autonomously, in this order; if the
token quota runs out, resume automatically once it resets (12:00); **pause only before the repository
move.** This file is the run's state: each step's status is updated and committed as it changes, so a
resumed session starts here.

**To resume:**
1. Read this file. Steps run in the order the table lists them, not by number.
2. Read `git log --oneline -15`.
3. Confirm no other agent is running (`ListAgents`; CLAUDE.md rule 14).
4. Continue at the first step not marked **done**.

## Guardrails for the whole run

- **No pushes and no GitHub changes.**
  - Never `git push`; no GitHub repository, release, Pages or package changes.
  - The website is prepared locally and published only within the repository move.
- **Git:** commit on a branch per step, and merge into local `main` once that step's gates are green.
- **One agent at a time** against the tree and the stacks (rule 14). Tests first, shown red (rules 12
  and 15).
- **Pin ports on every pytest** (`ARCADEDB_HTTP_PORT=2491 POSTGRES_PORT=55433
  POSTGRES_PASSWORD=throwaway VALKEY_PORT=6379 CLICKHOUSE_HTTP_PORT=18123`).
- **Deployments:**
  - May be switched, rebuilt with `ospreyflow start --build`, and the GOV.UK demo case reset, for
    captures.
  - Never `ospreyflow install` over a running deployment.
  - Leave the everyday deployment running at the end.
- **Data:**
  - Synthetic data only.
  - The real Enron case on the everyday deployment is never touched. Since the owner's ruling of
    1 November (step 2c) it may be sent to Gemini; it is sent nowhere else.
- **Every worker runs the whole non-live suite before handing back**, and shows that each failure it
  leaves also fails on `main` (added 1 November, after the step 4–6 stand-in regressions).
- **When the spec is silent:**
  - write the question under "Open questions" below;
  - take the conservative reading;
  - carry on, or move to the next independent step.
  - Do not stop the run for it.
- **Never print a secret.**

## Steps

| # | Step | Status | Notes |
| --- | --- | --- | --- |
| 0 | Today's finished work: GOV.UK alignment, identity, plain sign-in card (ADR-132 Am. 4); intelligence-mapping theme (ADR-115 Am. 4); capture fixes; decks rebuilt; plans written; ADR-133, ADR-134, ADR-135 accepted | done | `main` at `ec7b611` and before |
| 1 | **ADR-135, server side:** engines and keys in `osprey.yaml`; gateway table; install; `ospreyflow models` verb; routing; `GET /v1/models/engines` | done | Merged 1 November. 193 model tests and 991 CLI and harness tests pass; the one failure is the owner's own uncommitted map setting |
| 2 | **ADR-135, the rest:** (merged 1 November: 120 workspace and 28 install-page unit tests, two keyboard steps, guides 1.13 and 1.9 with their PDFs; also: the guided install's Models screen drops `providers` and `defaults` when it saves; a key typed into the install page needs a secret-carrying endpoint, a decision of its own) engine picker in Ask the case and Ask to search (+ keyboard step); Admin → System; guided install Models screen; administration guide §8, §10 and Appendix A; user guide; new versions and PDFs; correct ADR-135 decision 3 if the verb restarts more than the gateway | done | The live Gemini check waits for the owner's key (see "Waiting on the owner"); it does not block |
| 2e | **Applying a changed `osprey.yaml`, and secrets kept private** (found doing 2c, 1 November): (1) no supported way exists to apply a changed `osprey.yaml` to an installed deployment — `start --build` reads the rendered copy; `install --yes` refuses a different `osprey.yaml` and `--force` would overwrite it; `ospreyflow models key` refuses a provider newly enabled in `osprey.yaml` and tells the admin to run `install` again, which must not be done over a running deployment. Build a verb (for example `ospreyflow apply`) that re-renders from `osprey.yaml`, keeps every secret, takes a newly enabled provider's key from the terminal, and restarts what changed; fix the verb's message; document it in the administration guide. (2) `apply` writes `deployment.env` world-readable (`-rw-r--r--`); create it `600` and keep it so on every rewrite, with a test shown red first (both local deployments' files were set to `600` by hand on 1 November). (3) Then key entry on the guided install page (the owner's ruling): a write-only key field per provider, never logged or echoed. ADR-137 before code | done | Comes first. Then step 2c: Gemini is already in the everyday `osprey.yaml` (backup in the session scratchpad), waiting on this verb Merged 1 November (131 tests re-run). **Follow-up:** `apply` restarts the one-shot `ingest` job container and waits on it, so it reports failure (exit 2, usage) though every service is healthy — exclude one-shot jobs from the restart and the wait, with a test. |
| 2c | **Gemini on the everyday deployment** (the owner's ruling of 1 November): install the key with `ospreyflow models key gemini` from `~/.ospreyflow/gemini.key`; enable `gemini` (`gemini-2.5-flash`, label "Gemini") in the everyday `osprey.yaml` with `sendable_handling_codes: [P]`; **the owner rules the Enron case sendable to Gemini** ("the dataset I am using is a publicly available dataset"), recorded as an amendment to ADR-035 §C3 and in the local exceptions entry. Then `ospreyflow start` to apply, and a live check: one Ask the case question on the synthetic PID case on Gemini, and one on the local model | done | After step 2 merges (one agent at a time). Remind the owner: on a free-tier key Google may use prompts to improve its products; a paid key does not Done 1 November: key installed by `ospreyflow apply`; Google retired `gemini-2.5-flash` for new users, so the engine is `gemini-3-flash-preview`; a request through the gateway answered; the Conduit holds no key. The Ask the case check in the Glass runs with the C8 captures. |
| 2d | **Per-dataset egress** (the owner's ruling, ADR to write): a second gate beside the handling codes — each dataset is marked sendable to hosted engines or not, and material leaves only when both its handling code and its dataset allow it. **Plus, the owner's ruling of 1 November: each provider key is marked by the admin as covered by a privacy contract or not** ("for every key specified allow the admin to mark if this key has privacy contract underpinning the key or not"): shown in Admin → System, in the analysts' engine choice and in `ospreyflow models`; and a dataset may be marked sendable to contracted engines only. Schema, the route, the Admin screen, tests that a non-sendable dataset's material is never sent | done | New ADR-136, written and recorded as accepted from the owner's ruling before code Built and merged 1 November (82 Python, 63 front-end tests; admin guide 1.15, user guide 1.10). Everyday deployment rebuilt; its Prison Intelligence and Enron datasets set to `any` through Admin → Datasets (audited); it holds no scale-cohort dataset. |
| 2b | **GDS baseline audit** (the owner's request of 1 November, from Gemini's brief): accessibility (axe on every page and harness, plus manual keyboard and screen-reader checks of the graph, map and timeline against WCAG 2.2 AA); security (bandit, `npm audit`, secrets and configuration, the `withhold_sources` and `sources_in_full` use in writers); open standards and OpenAPI; then `process/gds/gds_compliance_report.md` and `gds_remediation_plan.md` (prioritised backlog). Critical items fixed in this step; the rest folded into steps 3–7. Its outcomes go into the Prison Intelligence decks at once (a baseline-results slide; the mapping slides' statuses), and the decks are rebuilt | done | Evidence against each of the 14 Service Standard points, with an honest status; never a claim of "compliant" (only an assessment panel can say that). The new tools are dev-only and go through the licence gate Done 1 November: `process/gds/gds_compliance_report.md` and `gds_remediation_plan.md`; seven fixes, each shown red first (button names, the CVE mitigation's test, 320px reflow, a contrast fix, the sign-in page's language, a folded timeline kept out of the Tab order, a hit target); the every-harness axe scan (90 pages and variants); the prison decks gain a results slide and corrected mapping (the Matrix view was claimed but is not built). |
| 2g | **The Matrix view** (`02_GLASS_FRONTEND.md` §6; GDS remediation A1, P1): the accessible table alternative to the canvas that the spec requires and the decks had claimed as built. Then A2 (the canvas announces the focused node's name) rides with step 3 | done | First Glass change after the audit. Keyboard and axe cases first (rules 12, 13) Done 1 November: a fourth view, Matrix — entity and link tables as ARIA grids, sortable, paged 100 rows with the caption saying so, selection shared with the canvas both ways; 43 unit, 9 keyboard, 9 axe cases; user guide 1.11. |
| 3 | **ADR-133 stage (a):** one alert queue for every kind (typology, hotlist, monitor); severity, team, assignment; hotlist audience setting (`monitoring.hotlist_audience`, `hotlist_audience_editable`); the existing typologies as templates | done | Done means the user guide section and the Product Overview deck slides exist (ADR-133 ruling 2) Done 1 November: one queue (typology, hotlist and monitor alerts, visibility decided in SQL), severity, team, assignment, the hotlist audience setting, typologies as templates, and A2 (the canvas announces the focused node); user guide 1.12, admin guide 1.16, and Product Overview Draft1d (two slides). Interpretations recorded as ADR-133 Amendment 1. The live-store tests ran against a throwaway Postgres; the ArcadeDB suites (reports, typology rules, alerts) are not run here. |
| 4 | **ADR-134:** `alert` pack item; monitoring dashboard feed sections and board; alert trends (conformance first); the rule-3 review of the pack and queue readers; the ADR-113 decision 4 text and the alerts route docstring fixed | done | Guide and Product Overview deck as in step 3 Done 1 November: the `alert` pack item, four monitoring feed sections (board described in admin guide §12), alert trends (DuckDB conformance first; ClickHouse written, not run here), a queue timing leak fixed, pack items filtered in SQL; user guide 1.13, admin guide 1.17, Product Overview Draft1e. Interpretations: ADR-134 Amendment 1. Live-store suites need Postgres, ArcadeDB and ClickHouse: run in CI. |
| 5 | **ADR-133 stage (b):** sentence builder; frequency and amount conditions; preview (backtest) | done | Guide and deck Done 1 November: rules as sentences over the ontology, round-tripping with the drawn pattern; frequency, amount and first-time conditions (`event_frequency`, DuckDB conformance; ClickHouse not run here); a 90-day preview that writes nothing; user guide 1.14; Product Overview Draft1f. Interpretations: ADR-133 Amendment 2. Also fixed: the revert test's stand-in store, broken on main by step 4. |
| 6 | **ADR-133 stage (c):** list subscriptions (OFAC, OFSI, UN, EU, OpenSanctions adapters with synthetic golden files; licence register entries); re-screening on update; new AML templates | done | Guide and deck. Real lists never in the repository (rule 9) Done 1 November: five list connectors (OFAC, OFSI, UN, EU, OpenSanctions) proven on synthetic golden files; versions, diffs and delta re-screening into the one queue, written inferred; a Lists tab; four AML templates (`account_activity`, DuckDB conformance); user guide 1.15, admin guide 1.18, Product Overview Draft1g. Interpretations and two licence findings: ADR-133 Amendment 3. Also fixed: the run-resources stand-in, broken on main by step 4. |
| 7 | **ADR-133 stage (d):** scheduled trigger; Studio "Checks on load" step with Verify preview; maker–checker | done | Guide and deck. Done 1 November: rule and list schedules, Checks on load with Verify's would-be alerts, maker–checker for deployment rules and high-severity closes; user guide 1.16, developer guide 1.8, admin guide 1.19; Product Overview Draft1h. Merged at `1666e1a` with `fix-sweep-regressions`; 98 screening and stage (d) tests pass on a fresh Postgres (a fixture-order fix, `8612bce`). Interpretations: ADR-133 Amendment 4 |
| 7b | **The owner's answers of 1 November** (see "Owner's answers" below): build what they ask — Watches rail entry removed; admin screening counts limited to the admin's unit; the closing reasons list; Ask to search carries the case's handling; the brand button's spoken name; OpenAPI published and versioned; the UK Sanctions List (FCDO) connector; UN and OpenSanctions marked "licence not confirmed"; the test-harness port guard | done | Done 1 November, merged at `0bf72a7`: Watches reached from Monitoring alone (the alert inbox moved into its Watches tab); admin screening counts per the admin's unit, chosen in SQL; five closing reasons; Ask to search carries the case's handling and datasets; "Osprey, go to Home"; `/v1/openapi.json` behind sign-in, versioned with the release; UN and OpenSanctions "licence not confirmed" and synthetic-only, enforced; the port guard (`CI=true` the only switch). User guide 1.17, admin guide 1.20, developer guide 1.9. Interpretations: ADR-133 Amendment 5, ADR-135 Amendment 1. Not done: answer 3's "unit admins see their own unit" (check whether a unit-admin role exists; a follow-up). After step 7. Each with a test shown red first. The FCDO connector may ride with step 8 |
| 8 | **Demo use cases** (`ALERTING_MONITORING_PLAN.md`): amendments to ADR-127 (Prison Intelligence) and ADR-108 (Ledger); generated batches and golden tests; P1–P4 woven into the prison storyline; A1–A4 in Operation Ledger | done | Each case built once its stage has landed: P2, A1 and A2 after step 3; P1 after step 5; A3 after step 6; P3, P4 and A4 after step 4. **8a done 1 November** (merged at `b75683f`): P1–P4 in chapters 9 to 11 (ADR-127 Amendment 41), visit bookings and new-contacts batches (recipes R18, R19), golden and negative tests, the seed's release and reset; `DEMO_GUIDE.md`. **8b built 1 November on branch `demo-ledger-alerting`, not merged** (awaiting the coordinator): the UK Sanctions List (FCDO) connector and OFSI marked closed (ADR-133 Amendment 6); A1–A4 in Operation Ledger's monitoring week (ADR-108 Amendment 5), with two product fixes it needed (a hotlist on an account number; a money-flow rule judging only accounts its author may see); `DEMO_GUIDE.md` §8b; user guide 1.18, administration guide 1.21 (§12's `closed` row fixed). Open question 14 |
| 9 | **Demos shown:** prison demo script (v4) and the Ledger walkthrough; `DEMO_GUIDE.md` and the setup guide; capture steps; captures in both brands; prison decks rebuilt | in progress | **Part 1 built 1 November on branch `demo-scripts-v4`, not merged:** script v4 proposed and the Ledger week's presenter script (local, git-excluded); the setup guide; `DEMO_GUIDE.md` §8b corrected and §8c added; capture steps for both brands (`live/pid-capture.spec.ts` updated, `live/ledger-capture.spec.ts` new, helpers in `live/capture-kit.ts`) and `CAPTURE_RUNBOOK_v4.md`. Not run against any deployment. Open question 15. Part 2 (the captures and the decks) to do. **Part 1 done** (merged at `5e71ff6`): script v4 (proposed), the Ledger presenter's script, the setup guide, capture steps and runbook. **Part 2 running (2 November):** everyday deployment rebuilt and its prison case and Ledger pack reseeded; GOV.UK deployment listed, moved to `main` and reinstalled; captures in both brands; prison decks rebuilt |
| 9c | **Starter packs (ADR-138, the owner's request of 2 November):** `ospreyflow install --starter <theme>-<domain>` (themes `ospreyflow`, `govuk`; domains `crime`, `aml`, `fraud`, `cyber`, `blank`) on the command line and the guided page; several deployments side by side (`--name`, `ospreyflow deployments`, `ospreyflow switch`); a public dataset of the administrator's choosing (`ospreyflow demo add public`), with the IEEE VAST Challenge datasets as the first catalogue entries (licences confirmed); a synthetic STIX 2.1 `cyber-intrusion` demo pack; the administration guide's new "Choosing a starter" section | to do | After step 9. The owner's existing deployments keep working; moving them into `~/.ospreyflow/deployments/` needs the owner's go-ahead |
| 9b | **GDS re-audit** on the finished product, with the monitoring features: the report and backlog updated; an accessibility statement drafted; `process/gds/gds_pitch_deck_content.md` (Gemini's seven slides: title, the mission, Service Standard alignment, accessibility, security by design, deployment, the road to assessment) | to do | **The owner (1 November): the GDS testing outcomes are recorded in the Prison Intelligence demo decks** (v1, v2 and v3, via `build_decks.py`): a results slide per pass (2b baseline, 9b re-audit) and each Service Standard point's status and evidence brought up to date on the existing mapping slides. Feeds step 10 (a GDS section in the Product Overview deck; the prison decks' mapping slides refreshed; a GDS section in the guides) and step 12 (the website claims only what this re-audit evidences) |
| 10 | **Decks and guides as a core feature:** Pitch (Draft2 → Draft3), Product Overview, AML Opportunity, Administration Architecture: monitoring and alerting slides and the one-line description; guides' monitoring chapters checked end to end; README feature list | to do | New revisions beside the originals; originals kept |
| 11 | **Rehearsal:** every demo on a freshly reset deployment, both brands, start to finish; the guides' steps checked against the screens | to do | The rehearsal residue (repeated hotlists and gaps) is an open question below |
| 12 | **Website:** pages saying OspreyFlow has a fully featured UK public sector option, designed to meet the GDS Service Standard (the owner, 1 November: never "GDS-compliant"; the independent checks listed as planned), for every UK department; the alerting and monitoring theme | to do | Prepared and committed locally; **published only within step 13** |
| 12b | **`make ci` locally, once** (the owner, 1 November), ports pinned; fix what it finds | to do | Before the pause at step 13 |
| 13 | **PAUSE: the repository move** (`REPO_MOVE_PLAN.md`) | **waits for the owner** | Do not start any part of it, including the packaging-rule change, without the owner |

## Waiting on the owner (does not block the run)

- **The Gemini key** for the everyday deployment's demos.
  - Saved by the owner on 1 November to `~/.ospreyflow/gemini.key` (mode 600, outside the
    repository). Checked the same day: Google's API accepted it (HTTP 200). Use `gemini-3-flash-preview` (Google refuses `gemini-2.5-flash` for new users).
  - Once step 1 has merged, install it with
    `OSPREY_MODEL_KEY_GEMINI="$(cat ~/.ospreyflow/gemini.key)" ospreyflow models key gemini`. Never
    print the file or the key.
  - Then enable Gemini in the everyday `osprey.yaml` (`models.providers`) for the synthetic demo
    cases' handling codes only. Never the Enron case's (rule 9).
  - Retry the C8-a and C8-b captures on Gemini.
  - If the file is missing, leave the C8 captures on the local model and carry on.
- **Rehearsal residue on the GOV.UK demo deployment.** The case reset leaves the coordinator's number
  hotlisted three times, the intelligence gap four times, alerts, and 3,000 nodes in the scale-cohort
  case. Either clean it by hand in the app or reinstall that deployment: the owner's choice.
- **ADR-133 ruling 3** reads "configurable" as a deployment setting; the owner to confirm.

## Owner's answers, 1 November (interactive review)

| Question | Answer |
| --- | --- |
| 1, hotlist audience ("configurable") | As built: `monitoring.hotlist_audience` (default `only_me`), with `hotlist_audience_editable`; dataset access still applies. ADR-133 ruling 3 confirmed |
| 2, Ask to search's engine choice | Ask to search carries the case's handling, so the engine choice applies |
| 3, Admin → Datasets across units | Keep it for system administrators; unit admins see their own unit |
| 4, the brand button's spoken name | "Osprey, go to Home" (WCAG 2.5.3) |
| 4, OpenAPI | Publish it at the deployment's address, versioned with the release |
| 4, CI | Run `make ci` locally (ports pinned) **once, after step 12** (the owner, 1 November: deferred to the end); still no push. Each step still runs the whole non-live suite |
| 4, independent checks | Website and decks say "designed to meet the GDS Service Standard", and list the accessibility audit, penetration test and DPIA as planned |
| 5, the Matrix view | Keep as built |
| 6, stage (a) | Keep; remove the Watches rail entry; closing reasons are True match, False positive, Duplicate, No further action, Referred |
| 7, alert trends | No backfill |
| 8, the port guard | Add it: tests refuse 2480, 5432, 8080 and 8081, shown red first |
| 9, deployment rules with no approver | Closed by stage (d) |
| 10, lists | Build a UK Sanctions List (FCDO) connector in step 8; mark UN and OpenSanctions "licence not confirmed" (Lists tab and admin guide), synthetic only |
| 11, admin screening counts | Limit them to the admin's own unit (rule 7) |
| Step 7, Data Engineers' L3 | Keep L3 for the seven typology rules |
| GOV.UK rehearsal residue | Reinstall that deployment before step 11, listing what is removed first. **2 November (step 9 part 2):** reinstall it now on current `main`, seeding the prison case and the Ledger pack, for the GOV.UK captures (the owner, after the list of what goes) |
| Everyday deployment for the v4 captures | **2 November:** `ospreyflow start --build` on current `main`, then reseed only the prison case and the Ledger pack; the Enron case and the others untouched |

## Open questions found during the run

15. **Step 9 part 1, the demo scripts against the Glass as built** (found writing script v4 and the capture
    steps at `4cdab46`, read from the code, not walked), for the owner:
    - **The demo analyst cannot deploy a rule for the case team.** A case rule (a template, or a sentence
      for "this case") needs the case's Author level, and the seeds make `osprey-demo-analyst` an Editor
      (`osprey-demo-admin` the Author). Script v4 deploys P1's rule from the admin's profile, and
      `DEMO_GUIDE.md` §8b now has the Author deploy the Ledger's two templates. Alternatively, grant the
      demo analyst Author on the synthetic cases.
    - **The admin may be the second person** for S1's close (open question 13): it holds the Analyst role
      and is the case's Author, and `approve_close` refuses only the proposer. Not tried; the capture
      runbook's optional step 10c finds out. Script v4 keeps the slide meanwhile.
    - **Checks on load is unreachable on a seeded pipeline without a new version.** The seed publishes R18
      and R19 (and every PID recipe but R9) with no canvas, so they open on Publish, where neither Checks on
      load nor Verify is offered; **Reopen for editing** makes a new version. Script v4 shows both screens on
      the reports pipeline. Give the seeded pipelines a canvas, or rehearse the reopen?
    - **The pack's alert picker offers active alerts only** (the queue's default: open, claimed, closing), so
      a closed alert cannot be added from the Glass. §8b's A4 now adds R1 while open and refreshes the item
      after the close, as ADR-134 decision 1 provides.
    - **A hotlist entry cannot be removed in the Glass,** so every rehearsal that adds the coordinator's
      number again adds a second active entry. The scripts say to keep the first.

14. **Step 8b, Operation Ledger's monitoring week (ADR-108 Amendment 5) and the UK Sanctions List
    (ADR-133 Amendment 6)**, for the owner:
    - **The FCDO's XML schema carries its own notice**, not the OGL: use "for … developing, testing, or
      implementing compatible systems", not "as part of a paid service without prior consent".
      OspreyFlow does not ship it; the connector was written from its element names. Confirm with the
      FCDO whether a paid deployment's use is "part of a paid service".
    - **The XML only.** The CSV's column order is documented nowhere found; a CSV connector waits for it.
    - **A typology template has no preview** (preview is built for sentence rules only), so the
      circle's tuning from 30 days to 7 is explained on screen, not shown against evidence.
    - **The Ledger has no seeded Studio recipe**, so the week is loaded through a pipeline the engineer
      builds in the Studio (as the onboarding chapter is), and the reset cannot revert it by recipe: it
      names `scripts.revert_load`. A seeded recipe and a reverting reset, as the prison demo has, would
      be a step of its own.
    - **The transactions recipe keeps no row keys**, so loading the week twice writes its events twice
      (each finding is still alerted once). Add row keys to `ledger_transactions_recipe.yaml`?
    - **Two product changes made to let A2 and A1's negative case work**, open to review: a hotlist on
      an account number (stored compact and upper case; no IBAN checksum, since the Ledger's numbers are
      invented), and a money-flow rule judging only movements between accounts its author may see
      (before, a rule deployed in another of the case's datasets judged every movement of the case).
    - Unchanged from question 13: no second analyst account for a demo approval (A4 closes a
      medium-severity alert, so needs none), and the Glass shows no monitoring figure (A4's figures are
      the board's).

13. **Step 8a, the prison demo's monitoring use cases P1 to P4** (ADR-127 Amendment 41, merged at `b75683f`), for the owner:
    - **A second analyst account for the demo.** Approving the rule alert's high-severity close (stage
      (d)) needs a second person with the analyst role; the demo has one analyst account. Add a demo
      persona (an intelligence manager, a realm change), or show the approval from a slide?
    - **Where P4 is shown.** The Glass shows no monitoring figure (the Reports view counts typology
      alerts only); the monitoring sections reach the Superset board, which never counts an "only me"
      hotlist. Show P4 on the board (dashboards on, the hotlist shared with a team the board's account
      belongs to), or add the figures to the Glass?
    - **A seized handset is named "Device" and an id tail** in alert words and the queue: a `Device`
      declares no name property. Should `imei` name a device?
    - **"For Wing F"** (P3): alert trends cannot filter by place; built as the case's alerts. A place
      filter would be a decision of its own.
    - **Administration guide §12's `closed` row** lists true and false positives only; since ADR-133
      Amendment 5 a label is any of the five reasons. For the guides' next version.
    - **Rehearsals:** S1 must not be closed as *True match* (it supersedes the load's `Alert` node and
      the reset then refuses), and a rehearsal's rule must be retired and written again (a rule raises a
      finding once). Both are in the setup guide and the reset's words.

12. **The port guard and `make dev-up` (step 7b).** The guard refuses every local test run that
    reaches 2480, but `make dev-up` also publishes its ArcadeDB on 2480, so the live ArcadeDB suites
    can no longer run against the dev stack locally (CI is allowed by `CI=true`). Proposed: move
    `make dev-up`'s ArcadeDB to 2491, which the pinned ports already use. Also: `make test` itself
    is unpinned, so a bare `make test` is refused with words saying how to pin.

11. **Admin screening counts (found fixing the sweep regressions):** the admin screening routes return
    re-screened and alert counts across the whole deployment, in tension with rule 7. **Answered
    above:** limit them to the admin's own unit.

10. **Sanctions lists (ADR-133 Amendment 3), before a customer relies on them:**
    - The OFSI Consolidated List closed on 28 January 2026; a UK Sanctions List (FCDO) connector is
      needed.
    - The UN list has no open licence found; confirm its terms with the UN.
    - OpenSanctions needs a commercial data licence for business screening.

8. **An unpinned test reached the owner's ArcadeDB (step 5).** One worker test run reached the
   everyday deployment's ArcadeDB on port 2480 because its shell had not pinned the ports. It was
   refused (403, wrong credentials), so nothing was read or written. Every later worker brief carries
   the pinned ports. For the owner: the test harness could refuse to run against port 2480 by default.
9. **Rules as sentences** (ADR-133 Amendment 2) are open to review, notably whole-deployment rules
   going live with no second approver until stage (d).

7. **Alerts in reporting** (ADR-134 Amendment 1, for the owner):
   - Older alerts never count in alert trends (fail closed); should a backfill be built?
   - The feed names rules by typology.
   - A re-marked node reaches a trend only when the alert next changes.

6. **Monitoring, stage (a)** (ADR-133 Amendment 1, for the owner):
   - Team means the organisational unit.
   - Monitor alerts go to the team.
   - The severity defaults.
   - Only case alerts can be given to someone.
   - The closed list of closing reasons is to be named.
   - Should the separate Watches rail entry go, now that Monitoring has a Watches tab?

5. **The Matrix view (step 2g), for the owner:** it is built as entity and link tables, not an
   adjacency matrix (the spec only names it "Matrix"). Expand opens the Graph, where the preview and
   the limit live. A resolution cluster shows as its members, not one row. Pages are 100 rows. Keep
   these, or change any?

4. **From the GDS audit (step 2b), for the owner:**
   - **The top bar's brand button:** what should its spoken name be? It reads "Osprey" but is named
     "OspreyFlow, go to Home" (WCAG 2.5.3; ADR-132 Amendment 4 ruling 5).
   - **The OpenAPI document:** publish it at the deployment's address, and version it with the
     release? It is served only inside the API container, versioned `0.1.0`; the spec is silent.
   - **Main has not been through CI since 29 October.** CI runs on push, and this run never pushes.
   - **Yours to commission:** an independent accessibility audit, a penetration test and a DPIA.

3. **Admin → Datasets lists every unit's datasets** (built in step 2d), so a system administrator can
   set egress anywhere. It shows names and settings only, but it widens dataset-name visibility across
   units, which ADR-099 is careful about. For the owner: keep it, or limit it to the admin's own unit?
   Also built, for the owner's review: Ask the case sends the whole case's datasets (stricter than
   the elements actually sent); an engine shows "not available" when no handling code is sendable.

2. **Ask to search's engine choice changes nothing** (found building step 2). It sends no handling
   code, so it always runs locally (ADR-135's note), yet decision 5 gives it an engine choice. Built as
   written, and the answer line says truthfully that the local model answered. For the owner: keep
   the choice, drop it, or let Ask to search carry the case's handling so the choice applies?

1. **Gemini on the everyday deployment would also send the real Enron case (found 1 November).**
   - The Enron seed stamps its data with handling code `P` (`scripts/seed_enron.py:63`), the same
     code as the synthetic demo data.
   - Egress is decided by handling code alone, so `sendable_handling_codes: [P]` on the everyday
     deployment would make the real email sendable to Google (rule 9).
   - **Superseded by the owner's ruling below (step 2c).**
   - **Answered by the owner, 1 November:** egress is to be decided per dataset as well as by handling
     code (step 2d); meanwhile the Enron case may be sent to Gemini, since the dataset is public
     (step 2c).
