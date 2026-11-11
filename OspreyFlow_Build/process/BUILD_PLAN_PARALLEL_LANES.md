# Build plan: three outcomes in parallel lanes

6 November 2026 · for the owner and the orchestrator · companion to ADR-142 to ADR-145 and
`SESSIONS_RUNBOOK.md`.

Three outcomes, built at once (ADR-142):

1. **A more usable Ingest Studio:** the rest of the redesign, ADR-140 and ADR-141.
2. **A clear Glass:** three places, a context banner, a lighter case screen, alerts mapped, Admin
   regrouped and roles an administrator can define (ADR-145).
3. **Drawing for field analysts on a bulletproof case and dataset contract:** the analyst layer,
   case views, drawing boards, promotion (ADR-143, ADR-144).

**Restarted on 8 November 2026 with six lanes (ADR-142 Amendment 3).** Glass is retired and split into
`admin` and `rules`; a `platform` lane takes maps and model administration (Lane 5); the docs lane's scope
widens and it starts when the new screens run deployed in both themes (Lane 4). Lanes run on chosen
accounts (rules, case, studio and platform on `sol`) and live runs take one of two test stacks, a or b
(`SESSIONS_RUNBOOK.md` §4).

Every step obeys `process/CLAUDE.md` rules 1–15 (rule 14 as ADR-142 rewords it): tests first and shown
red; access tests on every read path; keyboard cases for every action; spec gaps fixed in `spec/`;
synthetic fixtures; British English; no `Co-Authored-By` lines. **Every screen is built and
axe-scanned in the dark, light and GOV.UK themes** (ADR-132), each ADR naming its GOV.UK forms.

Sizes: **S** = half a session, **M** = one session, **L** = a long session that may need a second.
Effort follows the owner's practice: Opus at medium for judgement, Sonnet for mechanical work.

## Step 0 · Set up the lanes (orchestrator, alone; M; Opus · medium)

Done before any lane starts, with the phase 4 session finished and stopped (rule 14 as it stands
today).

**Do.**
1. Owner confirms the items marked "the owner confirms at step 0" in ADR-142 (P7), ADR-143 (C14–C17) and
   ADR-145 (the small items). Any answer that changes a record changes it before it is committed.
2. Reserve ADR-142 to ADR-145 and their amendments in `spec/ADR_RESERVATIONS.md`, filling each
   `<reserved>` amendment number from the ADR's last amendment in `06_DECISIONS.md` at that moment.
3. Append ADR-142 to ADR-145, then each amendment under its ADR, to `spec/06_DECISIONS.md`. Copy the
   prototype's source into `spec/glass_redesign/navigation_prototype.dc.html`.
4. Replace `process/CLAUDE.md` rule 14 with ADR-142's appendix. In `process/FDE_HANDOVER.md` §1, change
   "the owner pushes and you never do" to "the orchestrator pushes under ADR-142 decision 6; lanes never
   push".
5. Build, each with its test shown red first, under `OspreyFlow_Build/`: `OspreyFlow_Build/scripts/stack_lease.sh`
   (`tests/test_stack_lease.py`, starting from this package's draft); `OspreyFlow_Build/scripts/lanes_heartbeat.sh`
   (`tests/test_lanes_heartbeat.py`, from this package's draft, ADR-142 decision 9);
   `OspreyFlow_Build/scripts/lanes_launch.sh` (`tests/test_lanes_launch.py`, from this package's draft, decision 10);
   `tools/friction_assemble.py` (`tests/test_friction_assemble.py`); the reservation check
   (`tests/test_adr_reservations.py`). Ask the owner to wire them into `make ci` (protected files).
6. Save the runbook's Prompt L and Prompt R as `process/lanes/PROMPT_L.md` and `PROMPT_R.md`.
   Create `process/lanes/{studio,glass,case,docs}/` (each with `BRIEF.md` and `REPORT.md`),
   `process/lanes/PUSH_LOG.md`, `process/friction/`, and `.claude/agents/lane-reviewer.md` (a copy of
   `pid-reviewer.md` without the Prison Intelligence specifics).
7. Add a friction fragment for step 0; assemble it; `make ci`; commit; push (ADR-142 decision 6).
8. Write each lane's first brief, commit and push; then `lanes_launch.sh setup` and `open` for studio,
   glass and case (ADR-142 decision 10), and tell the owner which tabs opened.

**Exit.** `git diff --stat` for step 0 touches only `spec/`, `process/`, `OspreyFlow_Build/scripts/`
(`stack_lease.sh`, `lanes_heartbeat.sh`, `lanes_launch.sh`), `OspreyFlow_Build/tools/`
(`friction_assemble.py`, `adr_reservations_check.py`, and `decision_log_publication_check.py`'s
process set gaining ADR-142), their tests and `.claude/agents/`; the five gates were each shown red; `lanes_heartbeat.sh show` prints a row
for each lane;
`git worktree list` shows five checkouts (the docs lane's is made at step 0 and opened after the
first merge); `PUSH_LOG.md` holds the first push.

**As run, 6 November 2026.** `make ci` was found red at `b548d9f`, before step 0, for causes from 3 to
6 November (ruff, mypy, a spec citation of `process/`, eleven build-calendar annotations, an unwired
live test). The owner ruled "Spec by me, code by L1.1": the orchestrator fixed the spec text in step
0; L1.1 fixes the rest; step 0 is committed on `main` and pushed with L1.1's merge, the first `make ci`
to pass (`PUSH_LOG.md` records it). The owner gave a standing yes to the downloads `make ci` needs.

## The orchestrator's own step

| Step | Work | Size | Exit |
| --- | --- | --- | --- |
| O-hyg | Test hygiene, from 7–8 November's findings: live files that create deployment-wide rules (`test_load_checks`, `test_rule_sentence_routes`, `test_rule_maker_checker_routes`, `test_rule_schedule`, `test_rule_sentences`, `test_sentence_rules`) clean up after themselves; `tests/services/api/test_ws_ticket.py:26` reads `VALKEY_PORT` instead of a hard-coded 6379; tests that read their own records select by their own ids; and `make ci` runs, or names, the fast tier, which GitHub's `test` job runs and `make ci` does not | S | A second run of each file over a database the first left changes nothing; no test connects to a port it was not given |
| O-acc | ADR-142 Amendment 1: `accounts.conf`; `--account` on `open`, `resume`, `headless` and the orchestrator's start; `pause`, `pause --now`, `switch`; the `paused` heartbeat state; `HANDOFF.md`; the merge gate's `wip(` refusal; Prompt R's handoff line; the monitor's *Account* column; `fallback` lines | M | ADR-142 Amendment 1's six tests green and shown red first; the runbook's commands updated; the owner can pause the case lane and resume it on another account by hand |

## Lane 1 · Studio (`lane/studio`) · Opus · medium

Continues the redesign's build plan (`spec/ingest_studio_redesign/` and `BUILD_PLAN_INGEST_STUDIO.md`).
Phase 5 is **not** in this lane (ADR-143 C1).

| Step | Work | Size | Exit (the build plan's, plus) |
| --- | --- | --- | --- |
| L1.1 | Phase 4's remainder: `make ci` green (the causes found at step 0) | S | Phase 4's exit tests green; `make ci` green |
| L1.2 | Phase 6: the canvas as editor, the Map editor, guided mode | L | Phase 6's exit; GOV.UK axe green |
| L1.2d | Found by L1.2c on main: `upsert_edges`' merge writes `g.E().has("id",…)` untyped, so a merge rewrites every link type holding that id. Type the merge's write, as L1.2c typed the restore; a conformance case with two types sharing an id, red first; and `read_link_state` refuses an id two types hold, as `revert_elements` does, rather than taking the first type (L1.2c's final check) | S | Only the merged type changes; an ambiguous id is refused |
| L1.3 | Phase 7a: the staging catalogue's engine (Knowledge Adapters, golden files, staged Parquet, `source_refs`); it carries reference lists of kind `screening` (ADR-140 Amendment 9 decision 3), the engine only, no screen | L | Golden files per step; provenance survives a Join; a screening list round-trips through the catalogue |
| L1.4 | Phase 7b: the drawers for each step | M | Phase 7's exit |
| L1.5 | Phase 8: expert steps | L | Phase 8's exit |
| L1.6 | Phase 9: connectors; and the screening-list connector in Sources, mapping templates (OFAC SDN, OFSI, UN, EU, OpenSanctions where licensed, blank) with synthetic golden files, deployment-wide import and per-dataset subscription, schedule and *Refresh now* (ADR-140 Amendment 9) | L | Phase 9's exit; each template maps its golden file; a rule offers only subscribed lists (with Lane 2) |
| L1.7 | Phase 10: Operations content and external orchestration, inside Admin's *Running › Operations* (ADR-145 decision 9); and Studio › Releases, the YAML bundle, `packages/schemas/release.schema.json` (a `packages/schemas` commit first), `ospreyflow release export` and `import --dry-run` (ADR-140 Amendment 9 decision 4) | L | Phase 10's exit; ADR-140 Amendment 9's release tests |
| L1.8 | The Studio's tips and *who can* refusals (ADR-145 Amendment 4 decision 12), from `help/roles.ts`; *Domain model* wording everywhere; `tools/ui_words_check.py` | S | No "target model" on screen; every disabled action says why and who can |
| L1.7a | studio-b: the git CLI in `studio_publish.py` replaced by dulwich under its Apache-2.0 licence (the owner's ruling, 9 November), then the Studio's tips patches after L2.7 | S | publish writes a commit real git reads, no `git` binary called, each red first; the tips' keyboard and axe |
| L1.9 | **S3 and Athena connectors** in *Studio › Sources*: read-only; S3 (CSV and Parquet under a prefix) and Athena (a named query or a table, results paged); authenticated by the namespace's IAM role, never a stored key; the host added to the egress allow list only when the source is enabled (ADR-148 decision 7); mapping as other sources; ADR-140 amendment (to reserve) | L | Golden files on synthetic data in an S3 stand-in (SeaweedFS in CI); Athena against a recorded fixture, its live test marked for the client's platform; another dataset's source refused (as L1.6's); the byte cap; keyboard and axe |
| L1.10 | **The deployment's marking ceiling** (ADR-148 decision 10): `deployment.highest_marking`; a load, an import or a drawn item above it refused before anything is written, in words naming the limit, never the content; System shows the ceiling | S | Refusal at each entry point, red first; nothing written on refusal (plant a row above the ceiling); a load at the ceiling passes |

L1.9 and L1.10 are studio-b's (ADR-148, 9 November 2026): L1.10 when studio-b is next free, L1.9 after P7 merges (it needs the profile's egress list). L1.10 touches the case lane's drawing code (`services/api/boards.py`, which already holds a case's ceiling): studio-b owns the setting and the load path, and carries the drawn-item check to case-b (CARRIES).

## Lane 2 · Glass and places, split into Admin (`lane/admin`) and Rules (`lane/rules`) · Opus · medium (Sonnet for L2.6–L2.7)

From 8 November 2026 (ADR-142 Amendment 3) the glass lane is retired. L2.1 to L2.8b are its own, merged.
**`lane/admin`** takes L2.4 part 2, L2.5, L2.6 and L2.7; **`lane/rules`** takes L2.8c and L2.9 to L2.12.
L2.10's team routing still waits for admin's L2.5 (merge order 11), and L2.7's Home section is built by
agreement with rules, which owns Home (merge order 18).

| Step | Work | Size | Exit |
| --- | --- | --- | --- |
| L2.1 | The alerts gap map (ADR-145 N5): every alert's generation, triage, routing and case scope against ADR-109, 130, 133, 134; no code | M | A written map in `spec/` with its open questions as multiple choice for the owner |
| L2.2 | Three places: the switcher, the context banner and cross-links, Home's cards, the rail losing Ingest Studio, Admin and Proposed types; the GOV.UK header (ADR-145 decisions 1–3) | L | Each role sees only its places, and the hidden places' routes refuse it; `keyboard/shell.spec.ts` and axe (dark, light, GOV.UK) green; DEMO_GUIDE chapters touched say so |
| L2.3 | The case screen's first lightening (decision 4), from a prototype round the owner rules on first | M | The owner's ruling recorded; `keyboard/panel-frames.spec.ts` green |
| L2.4 | Admin regrouped into sections (decision 5); part 2, Datasets' highest marking and promotion policy columns (decision 8; fields from L3.1), and from ADR-145 Amendment 4: the kind (with *Drawn*), the **Authors** and *Change owner…*, **every linked case with its layer's counts, size and state**, a removed case's *Merge* and *Delete* with dry runs; System gains *Dataset owners may be*. Part 2 waits for L3.1 **and** ADR-145 Amendment 4 | M→L | Every section shows only with its right; `keyboard/admin.spec.ts` green; ADR-145 Amendment 4's Datasets and System tests; no layer contents on any route |
| L2.5 | People and roles: the row (R3), Author visibility and *Name an Author* (R1), custom roles (R2), *Disable…* with transfers (A4); and ADR-112 Amendment 5: `author_rules`, `merge_datasets`, the *Rule author* role and the Super user preset; teams (name, mailbox, a level in a case, ownership); the lead, hand-over and cover; service accounts refused; the guard rails | L | Decision 7's refusals at the route; disable refused with an item untransferred; ADR-112 Amendment 5's tests |
| L2.6 | Operations' promotions and ageing (O3), and the Audit section (O2); *promotions overdue* goes to the dataset's Authors holding `review_promotions` (ADR-145 Amendment 4 decision 11, R7) | M | The overdue alert fires once at N days; audit access test by unit |
| L2.7 | The data engineer's *Needs you* and the Model tab's count (A2); Home's *What you can do, and what you answer for*, from the same source as the tips (ADR-145 Amendment 4 decision 12) | M | Keyboard and tooltip cases; the section lists nothing the reader can't see |
| L2.8 | ADR-146 decision 10: G2, G3 and G9 fixed, each with its test shown red first (the first of the alerts work) | S | The three tests; a friction row each |
| L2.8b | Found in L2.8's audit (rule 3): a `rule_fired` entry's words are withheld by the alert's links and transactions as well as its nodes; `edge_ids` and `event_ids` written into the entry at raise time (`rule_evaluation.py`, that write only); entries written earlier keep their entry but withhold their words when they name an alert (fail closed; the orchestrator's call, 7 November); and, from L2.8's review: held rows' "it matched: {words}" withheld the same way; pack items rechecked by links and transactions too (`packs.py`, that check only); a one-off `scripts.remark_alert_nodes` (dry run first) for Alert nodes written before `7fac778` below their links' marking; G3's route-level live test through a second case; and from L2.8's review: a triage conflict after the graph commit that leaves a match superseded with nothing repointed; the other `supersede_edge` callers (`link_changes.py`, `entity_pictures.py`) that hide alerts citing the old revision; the plants re-made in the real paths' shapes; the `get_edges` fake made to drop a link with a hidden end, as the port does; one transaction scope for the queue and the inbox; the canvas's `edges_among`; the id paths' timing recorded | M | New-shape and old-shape entries' words withheld, each red first; held rows and pack items each red with nodes alone; the script's dry run writes nothing |
| L2.8c | From L2.8b's review: the journal's id-path timing recorded; the rename taken under the id-ordered lock; the lock pool given a timeout and its own advisory-key space; and the other supersedes that clone or replace links alerts can cite (`supersede_node`'s clones in confirm_node and retract_node, `supersede.py`, `pipeline_run`, `same_as_writer`'s NOT_SAME_AS) go through the repoint journal, each red first with an alert citing the old link | S | An alert citing a link each caller replaces stays listed for its readers, each red without the journal |
| L2.9 | Four places: Rules and Monitoring in the switcher and the GOV.UK header; the place's shell and tabs; Monitoring and its count leave the Glass (reworking L2.2 and L2.3); the workspace router and `/alerts/<id>`; Home opens the alert; *Open the evidence* as a private view with the way back (R5) | L | ADR-145 Amendment 4's switcher test; ADR-146's address, refusal and way-back tests |
| L2.10 | One queue (the inbox removed, *what fired it* on every watch alert); the queue's filters; the inventory *What raises alerts*; watches kept there and made from the Glass (*Watch for this*, *Save as a watch*); saved patterns on a schedule (G16); team routing (the new rule-3 read, tests first); the lead's hand-off and taken-back marking; *Raise an alert…* to the case or the dataset (R4). *Suppress until…* included (R8 a, ADR-146 Amendment 1). Also from L2.8b: an alert repointed by a settle on a read path (after a failure between the graph commit and the repoint) keeps any working-set copy of its node at the old marking until redrawn, because the settle holds no working-set store; purge it, test first. Also from L3.1's final review: in a branch of a composite case every monitor alert raises `BranchLayerError`, so each scheduled slot fails and the KYC sweep stops whole; test first. Also, found in L2.8: outside a load (`raise_committed`, the sweep), an alert whose referent or cited link cannot be read raises neither node nor row, and the error propagates; say what a person sees, and raise the row without the node as a load does, test first. Worst today: the daily KYC sweep (`kyc_sweep.py`, no per-rule or per-case catch) stops whole at one such finding, the day's claim already taken, seen only in a server log, and fails at the same point every day if the cause persists; give it a per-rule and per-case catch and a failure a person sees. Also: a scheduled slot's failure does not count the alerts it raised before the error, and a screening re-screen's failure drops the rule's raised count | L | ADR-146's queue, watch, team and analyst-alert tests |
| L2.11 | The rule editor: a declared dataset, the *When / If / Then* form, BPMN 2.0 and DMN storage, *Show as BPMN*, *Export*, import refusal, draft, test and live with a second person, *Changes*; `scripts.migrate_rules_to_datasets` (dry run first) | L | ADR-146's editor, round-trip and migration tests |
| L2.12 | Reporting folded: the case's *Figures* tab (replacing the Reports view) with its Alerts and drawing panels; the Alerts panel for boards; the *Alert monitoring* board (D2); the second dashboards door removed; the Reports Viewer's journey; the canvas's alert badge; the *Roles, teams and Authors* help page and Admin's tips | M | ADR-145 Amendment 4's reporting and Reports Viewer tests |

## Lane 3 · Case contract and drawing (`lane/case`) · Opus · medium

The riskiest lane: every step starts with its access and existence-leak tests (rules 3 and 4), and the
`lane-reviewer` reads each step before it goes to the orchestrator.

| Step | Work | Size | Exit |
| --- | --- | --- | --- |
| L3.1 | Phase 5 as amended (ADR-140 Amendment, ADR-143 decision 1): target model per dataset, reference lists, ADR-126 derived, one dataset per case, composites, **each case's analyst layer and its read set**; `scripts.migrate_cases_to_one_dataset` (dry run first) also creates the layers. Before merge: branch layers dropped; a branch reads its original case's layer read-only until L3.2 (ADR-144 Amendment 1 decision 2) | L | Phase 5's exit; ADR-143's "unchanged under case B" conformance case green; every seeded case reads one dataset plus its layer; a branch holds no layer of its own (red with the old copy restored) |
| L3.1b | Phase 5's target-model half: `TargetModel`, reference lists, ADR-126 derived, the domain-model node; a `packages/schemas` commit first; Lane 1's files agreed (the owner's ruling "New L3.1b", 7 November, case Q4); and *domain model* wording; the *Make live* owner step (people, team or both; maker proposed; service account refused; the System setting); the home case made at first *Make live*; `scripts.make_home_cases` (dry run first); the `drawn` dataset kind. Waits for ADR-140 Amendment 9 and ADR-145 Amendment 4. Lane 1's files agreed on 8 November: case builds target_models.py, the model routes with impact and *Make live*, and `StudioRecipeStore.flag_for_model` (studio ratified it at `d5118ac` on conditions: a real-Postgres store test flagging only this dataset's published recipes, keeping a recipe's first reason and leaving drafts and superseded ones alone; red with the dataset condition and with the status condition removed; the route fake refusing what the store refuses; ids deduplicated); studio builds `model_version` pinned on pipelines (a schemas commit first), the Test run naming the draft version, and the screens (the Model tab, the domain-model node removed, *Make live*'s owner step, the *Drawn* badge), in that order around its Part B | L | Phase 5's exit in full; ADR-145 Amendment 4's home-case and *Make live* tests |
| L3.2 | Case views replace branches (ADR-144), `scripts.migrate_branches_to_views` (dry run first); widened by ADR-144 Amendment 1: branches gone from every route, screen, keyboard spec and spec; `tools/no_branches_check.py` in `make ci`; a branch's unnamed writes (proposals, extractions, `ALERTED_ON`) touching an original-layer node must not reach the original case through the source (from L3.1's final review, test first); branch-only items to the original case's layer, and anything in a legacy branch's or alert-jump case's own layer (cases made before L3.1, which the migration could not tell apart) moved into the original case's layer, tagged `from_branch` | L | ADR-144's tests; ADR-144 Amendment 1's tests; the selection bar's view actions by keyboard |
| L3.3 | Drawing boards (ADR-143 decisions 4–7): declare, link by handle, Alt-drag, right-click and keyboard; marking, grading, source; matching; pictures; and from ADR-143 Amendment 2: a board with no case makes a drawn dataset and its home case (decision 5); drawing an item sets its watch (decision 8, with Lane 2's queue); the layer's marking ceiling; the restore test | L | `keyboard/boards.spec.ts`; one field analyst's check of moving versus linking (open question 4); ADR-143 Amendment 2's tests for decisions 3, 4, 5 and 8 |
| L3.4 | Promotion (decisions 8 and 10): the sheet, one load, the dataset's policy and highest marking, review; the Studio's *Analyst promotions* list in `ingest/runs/` by agreement with Lane 1; and a removed case's layer merged by the dataset's Authors as a promotion, with the read grant for that merge only, and its delete (ADR-143 Amendment 2 decision 1) | L | ADR-143's promotion and policy tests; the owner's ruling on online revert (open question 2); decision 1's tests |
| L3.5 | Analyst-defined link types (decision 9) and the Model tab's proposals block | M | A proposed type's links cannot be promoted; accepted, they can |
| L3.6 | Replaced by ADR-143 Amendment 2 decision 8: no separate alert kind. What is left is the `drawn_watch` kind's queue cases and *Open the board*, built with L2.10 | S | One alert per match per case, withheld from a reader who may not see the item |
| L3.7 | The grading scheme setting and its change command (decision 11) | S | The dry run writes nothing; grades keep their original |
| L3.8 | The ownership route Lane 2's *Disable…* reads (views, boards, promotions, proposed types per person) | S | Access test; Lane 2's L2.5 consumes it |
| L3.9 | Merging a drawn dataset (ADR-143 Amendment 2 decisions 6 and 7): the Studio's *Merge into a dataset…* screen (in `ingest/**` by agreement with Lane 1) with map, match, dry run and merge; the drawing becomes a case view with annotations; L5 and L6 answered (a) (ADR-143 Amendment 3) | L | Decisions 6 and 7's tests |

## Lane 5 · Platform: maps and model administration (`lane/platform`) · Opus · medium

New on 8 November 2026 (ADR-142 Amendment 3). Neither had an owner: engines, each job's model and keys are
set only in `osprey.yaml` and the CLI, and System shows them read-only; maps have no Admin section, the
set-up console's basemap Build and Verify answer 501, prefetch runs only by hand, and the analyst's map
has no basemap switch or place search. **The owner's rulings of 8 November:** model choice and keys are
managed in the Glass's Admin place, keys write-only and never shown back, the CLI kept for headless and
recovery use; map provider keys follow the same rule.

| Step | Work | Size | Exit |
| --- | --- | --- | --- |
| P1 | Model administration in Admin (ADR-135 Amendment 2, written by the lane): *Admin › Models*: engines added, edited and removed (label, roles, an https base, the privacy contract and its reference); each job's model chosen from the closed, pinned lists; a key entered, rotated or removed write-only, never returned by any route, logged or sent back to the Glass; *Test the connection*; every change audited, behind a new right (`manage_models`). The Conduit writes the key only where the gateway reads it and restarts the gateway; System's engine table becomes the summary; `ospreyflow models` kept. Also the set-up console's egress warning, which reads the legacy `hosted_fallback` and not `providers` (red first). **Ask the owner first, as multiple choice:** where a key written from the Glass is stored. | L | Access tests (no right → refused; the key in no response, log or audit entry, planted at the real call site); the key round trip against the real gateway configuration; keyboard and axe in the three themes; the egress-warning test |
| P2 | Model usage and limits: calls and tokens per engine and job over a period, from the gateway's own records; the budgets and rate limits `spec/00` and `spec/04` promise, set in *Admin › Models* | M | Figures equal a planted gateway record; access test; keyboard and axe |
| P3 | Maps administration (ADR-147, written by the lane): *Admin › Maps*: each provider (tiers 1–4) with its state, added and edited, its key under ADR-135 Amendment 2's rule; the local basemap's state, with Build and Verify really run (the set-up console's 501s replaced, the `/v1/admin/geospatial/*` routes called) and the glyph fonts; prefetch areas set and run on a schedule; attribution; `ospreyflow map` verbs (list, build, verify, prefetch) for headless use; the WMTS `endpoint` conflict (`07_BUILD_PLAN.md`, phase 5's known gaps) settled | L | Access tests (`MANAGE_GEOSPATIAL`); demo and CI map data still tier 1 only (`test_demo_osprey_config_is_tier_1_only.py`); build and verify on a small synthetic region; keyboard and axe in the three themes |
| P4 | The analyst's map: a basemap switch among the providers the deployment holds; place search over the loaded gazetteer; the light and GOV.UK themes' contrast check beside the dark one | M | `keyboard/map-view.spec.ts` cases for both, each shown red; contrast in the three themes |
| P5 | The owner's map rulings (9 November): a Classpath-exception Java runtime in the Conduit image; gazetteer places copied into a case's dataset at load, identifiers withheld (3b); the gazetteer's unit a build setting | M | licence-check red for plain GPL Java; a live copy's identifiers absent, red without the fix; a working case still loads |
| P5b | Backups in a folder the administrator names at setup, for every install, never inside the checkout (ADR-114 Amendment 37), by the sister lane platform-b (the owner, 9 November) | S | ADR-114 Amendment 37's table of tests, each red first |
| P7 | **The `cloud-platform` profile** (ADR-148 decisions 1–5, 7, 8, 12, 14): the harness renders `deploy/generated/cloud-platform/` (Helm values into an existing namespace, and the namespace's Terraform for RDS, ElastiCache, OpenSearch, S3, ECR and IRSA in the environments repository's shape); the chart's optional `Ingress` (class, host, TLS, ModSecurity and allow-list annotations); numeric UID `10001` in all our Dockerfiles and `runAsNonRoot`, no privilege escalation, capabilities dropped on every rendered pod; the managed stores in place of ours, their connection details read from the platform's secrets; ArcadeDB ×3, ClickHouse ×2, Keeper ×3 as StatefulSets on `gp2-expand` with PodDisruptionBudgets (one of each for development); the Calico deny-egress and allow policies rendered from the settings ADR-135 Am 2 and ADR-147 already gate; `ospreyflow images push --registry`; the Conduit built without Java on this profile (build argument) and *Admin › Maps*' Build saying so; `make cp-policy-check` | L | `make cp-policy-check` green on the render and red on each planted fault (root pod, named UID, RWX claim, hostPath, port < 1024, foreign registry, no deny-egress); ArcadeDB, ClickHouse and Keeper each shown to start as UID 10001 (or a thin image of ours, in the licence register); the acceptance scenarios green on a kind/k3d cluster with the deny policy and no RWX class; `local-lite`, `small` and `cluster` renders unchanged except the UIDs. **Live on the platform (later):** the same scenarios in `ospreyflow-dev` |
| P8 | **Nothing on a shared disk** (ADR-148 decision 6): uploads, staging Parquet, map tiles and model files in S3; the model and map settings and the key file per the owner's ruling on ADR-148 question 2; the recipes repository per question 1. **Report first, then ask:** which components read and write the recipes repository and the settings files, and how; the owner rules before the move is built | M | No `ReadWriteMany` claim in the `cloud-platform` render (the policy check); a settings change in one Conduit replica seen by another; a key still in no response, log or audit entry (the P1 access tests, run on this profile); a recipe published and run across two replicas; restore of each moved item |
| P9 | **Running it on the platform** (ADR-148 decisions 5, 13): the backup CronJob to S3 (ArcadeDB `BACKUP DATABASE`, ClickHouse `BACKUP … TO S3`), encrypted; a restore rehearsed and timed; ArcadeDB's graceful stop; Prometheus alerts for volume use, memory and a copy down; the volume-expansion procedure written; the recovery runbook's `cloud-platform` section with measured times | M | Backup and restore round trip on kind/k3d with an S3 stand-in, red first on a broken restore; a drained node keeps the graph answering (one copy down at a time). **Live (later):** the restore rehearsed in `ospreyflow-dev` |
| P10 | **Sign-in claims from Entra ID** (ADR-148 decision 9): the claims `principal_auth` builds from (clearance, organisational unit, handling codes) mapped by settings, from a named claim or an Entra group table; one construction path kept; Keycloak not rendered on this profile | M | Access tests with tokens shaped as Entra's (extension attributes; groups; both missing → refused, never defaulted to cleared); the existing `principal_auth` cases unchanged; an unmapped group grants nothing |
| P11 | *(Replaces the held Bedrock step: the owner, 10 November 2026)* **The model route on the `cloud-platform` profile** (ADR-135 Amendment 4): the LiteLLM gateway rendered by default on the profile; an engine type for the client's own OpenAI-compatible AI gateway (base URL; a token or the namespace's IAM role) and Bedrock by IAM role, no stored key, London only; the route's host the only model host in the allow list, and only while an engine using it is enabled | M | P1/P2's access and key tests on both engine kinds, against recorded fixtures; no key stored for the IAM-role kinds; the allow list gains the host only when an engine is enabled (red first); `cp-policy-check` green |
| P12 | *(New: the owner, 10 November 2026)* **Laurium as a second extraction engine** (ADR-135 Amendment 5): **licence check first**, of Laurium and every dependency it brings, against the register; **stop and ask the owner** if any fails. Then `packages/adapters/extract_laurium/` implementing `ModelPort.extract` only, as the optional extra `ospreyflow[laurium]`, built into the images that serve `ModelPort.extract` only when selected; the *extraction engine* setting (Deep read or Laurium) in the set-up console and *Admin › Models*, audited behind `manage_models`; the `cloud-platform` pack presets Laurium; Laurium's chat model configured with the gateway's endpoint only, any other host refused at start; the domain model mapped to Laurium's schema and its output to `ExtractionResult`, findings *inferred* and traced | M | The licence record in the register (or the owner's ruling); `ModelPort.extract`'s conformance suite green on both adapters; a Laurium configuration naming another host refused (planted); findings from Laurium arrive *inferred* with their document, accepted and rejected in the reader as Deep read's (keyboard and axe in three themes); an image built without the extra contains no `langchain` (checked in CI); access test: no `manage_models`, no change |
| P6 | *(by platform-b after P5b, 10 November, so the demo does not wait on ADR-148's chain)* The case's gazetteer panel beside place search: add and remove a gazetteer (ruling 6) in the Glass, by keyboard | S | a keyboard case and registry id, red first; axe in three themes |

**Added 9 November 2026 (ADR-148, the owner's client decision: hosting on the UK public sector client's Cloud Platform).** P7–P11 come after P5 and before P6 (P6 moves after P9). Everything is built and proven without the client's namespaces, on a local kind or k3d cluster set up to the platform's rules (the deny-egress policy, no ReadWriteMany storage class); the *live on the platform* lines wait for the client's access and are recorded later, so a step merges on its local exit. P11 is held until the client asks for AI. The Dockerfiles' `USER` line (numeric UID 10001) touches files other lanes own: P7 makes it first, as a shared commit, as schema commits are.

## Lane 4 · Documentation and collateral (`lane/docs`) · Sonnet (P7 confirmed at step 0: interactive, opened after the first feature merge)

Follows merges, never runs ahead of them for the guides:

- **The user guide** (`OspreyFlow_Core/docs/user-guide.md`): the three places; boards; views; promotion.
- **The developer guide**: the analyst layer, the promotion load, the new routes, the lease and the
  lanes.
- **The administration guide** §9: the sections, roles, disable and transfer, approval rights' fourth
  row, the grading scheme, uploads.
- **The website** (`OspreyFlow_Build/marketing_site`) and **the deck** (`OspreyFlow_presentations`,
  Product Overview, next draft after `Draft1l`): drawing boards as the headline feature, from the
  design reference, marked "coming" until L3.3 and L3.4 are merged; screenshots retaken after each
  merge, in the default and GOV.UK themes.
- **D2 (rescoped by the owner, 8 November 2026; ADR-142 Amendment 3 decision 5).** It starts when
  rules' L2.9 and L2.10, admin's L2.5 and platform's P1 and P3 are merged and a deployment started from
  the checkout shows them in both the default and GOV.UK themes; then a pass after each later merge that
  changes a screen. Scope:
  - **The README** (`OspreyFlow_Core/README.md`), carrying the overview deck's lasting content (the
    problem, the four people, See/Where/Do, the guarantees and safeguards, the use cases, reporting, the
    two architecture levels, the honest limits and the licence traps), describing the product as built.
    What it claims is published, so the owner approves the draft.
  - **The user, developer and administration guides, and a standalone architecture guide** printed
    beside them (`tools/docs_pdf.py`): four places; no branches; three alert sources and one queue; the
    whole rules and alerting module (sentence rules, screening lists, schedules, checks on load, the
    second approver, hotlists, held rows, the Rules place and its editor, teams and routing, the
    monitoring board); home cases, Authors and teams; releases; the Reports Viewer's journey; Maps and
    Models administration; the roles' words from `help/roles.ts`; and the spec copy's drift fixed
    (`spec/10_ADMINISTRATION_GUIDE.md` lacks §9.5 and §9.6).
  - **The welcome pages, the website and the GOV.UK theme's wording**, brought into line with one
    another and with the guides (the owner, 8 November: they diverge in places).
  - The website marks unbuilt features *coming*. This is **D2a**.
- **D2b, the decks** (the owner, 8 November 2026): once the rule editor (L2.11) and drawing boards (L3.3) are
  merged and captured in the default and GOV.UK themes, every deck in `OspreyFlow_presentations/` updated for
  the rules engine (the Rules place and its editor), drawing boards and the one alert queue: the Product
  Overview (Draft1m, after Draft1l), the Administration and Architecture deck (Draft4), the three Prison
  Intelligence demo decks (rev5, built by `prison_intelligence_demo/decks/build_decks.py`) with the HMP demo
  script and the PID demo setup guide, the AML Opportunity deck (Draft3), the Pitch Deck (after Draft3b) and
  the AE Enablement deck (Draft2); screenshots from the deck-capture harnesses. What a deck claims is
  published, so the owner approves each draft.
  Exit: `make ci`'s spec and link gates; `make docs-pdf`; no "three places" and no "branch" outside the
  pipeline DAG.
- **D2c, the Cloud Platform deployment guide** (ADR-148, 9 November 2026; after P7–P10): the namespace and resource pull requests, the secrets each component reads, images to ECR, the egress list, Entra's claims, backups and restore, the volume-expansion and upgrade runbooks for ArcadeDB and ClickHouse; the architecture page shared with the client kept in step; and (the owner, 10 November 2026) choosing the extraction engine, the client's gateway as an engine, and Laurium's licence entry, correcting the architecture page if P12 places Laurium other than in the Conduit and workers. Size M.
  Exit: every command in the guide run on kind/k3d; link and provenance gates green.

## Two tracks (10 November 2026)

**Track A, demo-ready:** L2.7, L1.5, P5, D2a, L2.10, L1.7a, P5b, L2.5b, L3.9, P6 (platform-b), L3.6, L1.7, L2.11,
then D2b with captures from a deployment built from `main` on the owner's test server (a separate named deployment,
never `osprey-small`). **Track B, the client's install (ADR-148):** P7, L1.10, P8, P9, P10, L1.9, P11, P12, D2c.
Track B's live exits wait for the client's access. Neither track waits on the other; P6 moved to platform-b for that.

**Track B, from 11 November (ADR-142 Amendment 8, the owner's word):** one complete install on the client's
environment in one go, Laurium included; the client's environment is due on 20 November. P7 merges on its render,
`cp-policy-check` and the ordinary gates; its kind acceptance is P7a. Once P7 merges, side by side:

| Lane | Step | Notes |
| --- | --- | --- |
| admin | P10 | Entra ID claims (`packages/principal_auth/`, the profile's claim settings); an access step, two rounds; after T1 part 5 |
| platform | P9, then P7a, then P7b | P9 cut to backup and one timed restore (P9b later); P7b the `shape: poc` profile (ADR-148 Am 5) |
| platform-b | P11 | The model route, after its carries |
| case-b | P12 | Laurium as its own Python 3.13 service (BRIEF_P12, p12/LICENCE_CHECK.md) |
| studio-b | L1.9 | S3 and Athena connectors |
| docs | D2c | From P7's merge, filled as each step lands; records where Laurium runs |

Merge order: P10 and P9 first, then P11, P12 and L1.9; P7b last. One template file per step; `values.yaml`, the
profile's settings model and `render.py`'s profile entry are platform's, the others sending diffs. **P8 deferred**
until after the install (P7's interim stands), and **P9b** (alerts, drain test, volume expansion) after it too.
Paused until the chain merges: T3b's follow-ups, D2b's captures, rules' `lists`.

## File ownership

A lane changes only what it owns. Anything else is a request to the orchestrator, who either makes a
small shared commit and merges it first or moves the work to the owning lane.

**Review, from 7 November 2026 evening (the orchestrator's judgement; the owner asked for speed and chose
"Just the four changes").**
1. *A lane reviews itself first.* Before reporting ready-to-merge, a lane runs the `lane-reviewer`
   agent on its own branch against its brief and rules 1-15, fixes what it finds, and says so in its
   report.
2. *Depth by risk.* A step that touches access (rules 3 and 4), the data model, the analyst layer,
   provenance or a store gets the orchestrator's full review. A UI-only or docs step gets one
   review, then merges.
3. *Two rounds, then carry forward.* After two review rounds, anything left that isn't a blocker
   (a rule 3 or 4 defect, a failing gate, data written where it must not be) goes into a follow-up
   item in the lane's next step's brief, and the step merges.
4. *Briefs name the hard parts.* A brief that touches access names the cross-case and composite
   cases, the real call site to plant at (rule 15), and what the real dependency refuses.

**Merge order, as practised from 7 November 2026 (the orchestrator's judgement).** `make ci` is run on the
merge result **before** the merge is kept: the orchestrator merges with `--no-commit`, or on a scratch
branch, runs `make ci`, and keeps the merge only if it is no redder than `main`. Found when L1.2's merge
(`25b1084`) turned two green gates red because `make ci` was run after the merge rather than before.
**One push at the end (the owner's instruction, 8 November 2026, about 06:20 UTC).** GitHub's CI is slow, so the orchestrator no longer pushes after each merge. Every merge is still kept only when `make ci` and `make test` are green locally on the merge result. Merges collect on local `main` and go to `origin` in one push at the very end (or when the owner asks), logged in `PUSH_LOG.md` as before.

**And the fast tier too (from 8 November 2026).** `make ci` does not run `make test`, the fast tier GitHub's `test` job runs, so L2.8's and L1.2c's merges, each green on `make ci`, left eight fast-tier tests red on `main` unseen for hours. A merge that changes code also runs `make test` on the merge result (closed ports, no lane; about 14 minutes) before it is kept, and a failure there that is not the machine's own (the local `osprey.yaml`, a root `graphify-out`, pinned ports) blocks it as a `make ci` failure does.

**A lane's own gate run stands for an identical tree (the owner's ruling, 8 November 2026, to speed
merges).** A lane reports ready-to-merge at a commit rebased onto current `main`, with `make -k ci` and
`make test` run offline at that commit and their outputs saved as `process/lanes/<lane>/gates/<sha>.ci.txt`
and `<sha>.test.txt` (failures listed, each explained). If `main` is still an ancestor of that commit, the
`--no-ff` merge's tree is the tested tree (the orchestrator checks `git rev-parse <sha>^{tree}` against
the merge result's), and the merge is kept on the lane's run; only what the orchestrator adds at the merge
(registry ids, reservation rows, allowlist lines) is checked by its own targeted gates. If `main` has moved
only by the orchestrator's records (`OspreyFlow_Build/process/**` and `spec/ADR_RESERVATIONS.md`, which no
code test reads), the orchestrator runs the document gates on the merge (`citation-check`,
`provenance-annotation-check`, `decision-log-publication-check`, `lanes-check`) instead of the full set.
If `main` has moved otherwise, the lane rebases and runs again, or the orchestrator gates the merge as
before. Several ready lanes are
gated in one run, split only if red. Gates run in a merge worktree, so `main` stays free. The seven trivy
image scans, refused locally by Docker Hub's pull limit, are left to GitHub's CI.

**A fresh session for each step (the owner's ruling, 8 November 2026).** When a lane's step is merged
and the lane is idle (its worktree clean, nothing unmerged, no lease held, no child process), the
orchestrator ends that session's process itself and opens a fresh one on the lane's account for the next
brief (`lanes_launch.sh open <lane>`). A fresh session carries the brief and the reports, not a long
history, so it costs fewer tokens.

**Speed-ups (the owner's ruling, 8 November 2026, evening).** (1) Lanes never stop on a question: they
build the recommended option and log it under "Decisions taken" in REPORT.md; only a question that would
loosen access, admit real data or contradict an accepted ADR stops the piece it touches. (2) A step's
`packages/schemas` change rides with the step (merge order 2 applies only when another lane needs the change
first). (3) Two review rounds, the lane's own and the orchestrator's independent one, only for a step that
touches access control, credentials or the data model; any other step gets the lane's own review and the
orchestrator's check of its diff. (4) Ready-to-merge once, at the end of a step.

**Ratified changes (the owner's ruling, 7 November 2026, "Ratify if needed").** A change outside a lane's
map that the brief's work needs is ratified by the orchestrator at review when the lane-reviewer finds
no conflict with another lane's work, and is recorded in the merge's friction row. Shared files
(`packages/schemas/**`, `keyboard/actionRegistry.ts`, `tokens.css`, the Makefile, `ci.yml`) stay
shared. A registry id is committed by the orchestrator immediately before the merge whose cases
prove it, not earlier, because `assertAllCovered` refuses an id with no proving case.

**Operational judgements are the orchestrator's (the owner, 7 November 2026: "can you make some of these
operational judgements on your own … if I get them wrong we would need to revert them during the active
testing").** The orchestrator decides operational matters itself and records each one, with its reason,
in `process/lanes/MORNING.md` and the merge's friction row: tooling and gates, test and CI hygiene,
ports and stacks, ignore entries, merge order, review handling, ratifying out-of-map files, and which
lane fixes what. The owner still rules on what a person sees or can do, who may access what, the data
model and any product decision an ADR records, published claims, real data, anything outside the
private repository, and the protected `Makefile` and `ci.yml`.

**While the owner is away (the owner, 7 November 2026, ~17:30).** The orchestrator may merge Lane 3's L3.1 once its
final review passes and `make ci` is no redder, leaving the plain-language summary in `MORNING.md`, and may
apply the CI-wiring diffs to the protected `.github/workflows/ci.yml` and `OspreyFlow_Build/Makefile` itself,
each checked with `git apply --check` and `make ci`, pushing once `make ci` is fully green (ADR-142
decision 6).

**Owner questions go through the orchestrator (the owner, 7 November).** A lane sends a question for the
owner to the orchestrator's session by cross-session message, as multiple choice, instead of asking in
its own window. The orchestrator batches the questions for the owner and sends the answers back, and
the lane records each one in `REPORT.md`.

| Lane | Owns |
| --- | --- |
| Studio | `apps/workspace/src/ingest/**` (except `ingest/runs/promotions*` during L3.4); `services/ingest/**`; the Studio's routes in `services/api`; `packages/knowledge_adapters/**`; `recipes/**`; `connectors/**` |
| Admin | `apps/workspace/src/admin/**` except the Models and Maps sections; the Admin, people, roles, teams and audit routes in `services/api`; operations' promotions and ageing |
| Rules | `apps/workspace/src/{shell,layout,home,statusbar,theme,brand}/**` (the places and the GOV.UK header); `apps/workspace/src/alerts/**` and the Rules and Monitoring place; the alerts, rules, watches and monitoring modules and routes in `services/api` |
| Platform | `apps/workspace/src/admin/sections/{Models,Maps}*`; `apps/workspace/src/{map,site,models}/**`; `services/api/{model_routing,tile_proxy,tile_cache,prefetch,tier4_registration,mapconfig_loader}.py` and the map, geospatial and model routes; `services/geocoder/**`; `packages/adapters/model_litellm/**`; the set-up console's Models and Geospatial screens and their routes (`apps/harness/src/screens/{Models,Geospatial}Screen.tsx`, `harness/{geospatial,install_page}.py`); `cli/ospreyflow/models.py` and the map verbs; `scripts/{build_local_basemap,fetch_basemap_glyphs,geo_local_provider,verify_map}.py`; for ADR-148 (P7–P11): the harness's `cloud-platform` profile files (`harness/` profile and render code, `deploy/generated/cloud-platform/`), `deploy/helm/ospreyflow/templates/ingress.yaml`, the policy check behind `make cp-policy-check` and its tests (paths named by P7), `ospreyflow images push`, and for P10 `packages/principal_auth/`; from P12, `packages/adapters/extract_laurium/` (the optional extra `ospreyflow[laurium]` and the lock file's Laurium entries go in a shared commit P12 makes first) |
| Case | `services/api/dataset_scope.py`; `services/api/working_set/**`; the case, view, board and promotion routes; the graph adapter's access step; `apps/workspace/src/{canvas,investigation}/**` and new `boards/`, `views/`; `scripts/migrate_*` |
| case-b (ADR-142 Amendment 4) | L3.5's link types (`services/api/link_types.py`, `link_type_store.py`, the Model tab's proposals block, `apps/workspace/src/linktypes/**`); L3.7's grading scheme setting and command; L3.8's ownership route |
| studio-b | `connectors/**`, the Studio's Sources step and its routes (L1.6), then L1.8's tips and wording across the Studio by agreement with studio |
| rules-b | L2.12's reporting: the case's *Figures* tab, the *Alert monitoring* board, the Reports Viewer and the dashboards door, by agreement with rules for the shell |
| platform-b (9 November 2026) | P5b's backups folder (ADR-114 Amendment 37): `harness/{backup,restore}.py`, `cli/ospreyflow/{answers,doctor}.py` and the backup and restore dispatch in `cli/ospreyflow/main.py`, and their tests; the admin guide's §13 by carry to docs |
| Docs | `OspreyFlow_Core/docs/**`, `OspreyFlow_Core/README.md`, `apps/workspace/src/welcome/**`, `OspreyFlow_Build/marketing_site/**`, `OspreyFlow_presentations/**` |
| Orchestrator | `spec/06_DECISIONS.md` (appends, reservations), `spec/ADR_RESERVATIONS.md`, `process/**`, `OspreyFlow_Build/tools/friction_assemble.py`, `OspreyFlow_Build/tools/adr_reservations_check.py`, `OspreyFlow_Build/scripts/{stack_lease,lanes_heartbeat,lanes_launch}.sh` |
| Shared, by small orchestrator-merged commits only | `packages/schemas/**` (and the generated types); `keyboard/actionRegistry.ts`; `apps/workspace/src/design/tokens.css`; `OspreyFlow_Core/Makefile` and `.github/workflows/ci.yml` (the owner's); every `Dockerfile`'s `USER` line (P7's numeric UID, a shared commit made first) |

## The fix-and-check order (ADR-142 Amendment 6, 10 November 2026)

Every step from 10 November evening: **built** (the lane messages "built at <hash>") → **both reviews at once** (the
lane's reviewer and the orchestrator's independent one) → **fixes together** → **rebase onto main** → **gates once**
(`make test` and `make -k ci` on the test server; browser tests in a granted slot; `stack_lease.sh live`) →
**ready-to-merge** → the orchestrator's trial merge and merge. The self-check list a lane runs before "built" is in
`process/lanes/PROMPT_L.md`. Heavy runs never on the owner's Mac.

## Merge order

1. Step 0.
2. Any `packages/schemas` change, alone and first, so every lane rebases onto the new types.
3. L3.1 before L2.4's Datasets columns and before any Lane 1 step that reads a case's dataset.
4. L2.2 (three places) before L2.3–L2.7 and before Lane 3's board screens settle their top bar.
5. L3.4's promotions list in `ingest/runs/` is merged only after Lane 1 has rebased past it, by
   agreement, with Lane 1 told first.
6. L3.2–L3.5 and L3.8 before L2.5's transfer list is finished.
7. O-acc before any lane is next opened or resumed.
8. L3.1 (with branch layers dropped) before L2.4 part 2 and L3.1b.
9. ADR-145 Amendment 4 and ADR-140 Amendment 9 on `main` before L2.4 part 2, L2.5, L2.7, L2.9, L3.1b and L3.3.
10. L2.8 before L2.9; L2.9 before L2.10–L2.12; L2.10 before L2.11.
11. L2.5 before L2.10's team routing and before L3.1b's team owners.
12. L3.3 and L3.4 before L3.9 (L5 and L6 answered: ADR-143 Amendment 3).
13. D2 as Lane 4 now says (ADR-142 Amendment 3 decision 5): after L2.9, L2.10, L2.5, P1 and P3, once a
    deployment shows them in both themes; then again after each later merge that changes a screen.
14. No brief for L2.5, L2.7, L2.9–L2.12, L3.1b–L3.4, L3.6, L3.9 or the new L1.3, L1.6, L1.7 before the
    owner's records of 7 November are on `main` (`process/inbox/specs_2026-11-07`, applied at the commit
    that appends them).

15. P1 before P3: P3's map keys follow P1's rule, right and audit.
16. A new Admin section (Models, Maps) needs its entry in Admin's section list: a small orchestrator
    commit immediately before the merge that builds it, as with a registry id.
17. L2.8c before L2.9 (the rules lane's first step, on the journal L2.8b left).
18. L2.7's Home section is built by agreement with rules, which owns Home; rules is told first.
19. ADR-148 (the owner's client decision, 9 November 2026): P7 → P8 (after the owner's two rulings on ADR-148's questions 1 and 2) → P9 → P10 → D2c. L1.10 any time; L1.9 after P7 (it needs the profile's egress list). P11 and P12 after P7 merges (they need the profile), each in a fresh session; P12 does not wait for P11 (proven on `local-lite` through the gateway's stand-in model) and starts with its licence check, stopping for the owner if anything fails the register (the owner, 10 November 2026). P6 by platform-b after P5b (10 November: moved off the client chain so the demo track does not wait on it).
20. P7's numeric-UID change to every `Dockerfile`'s `USER` line is a shared commit, made first and alone, as schema commits are; every lane rebases past it.
21. `make cp-policy-check`'s Makefile target and `ci.yml` job are the owner's files: P7 writes them as `process/lanes/platform/P7_ci_makefile.diff` for the owner to apply, as L1.1's diff was.

## What the owner checks by hand

After each merge, the orchestrator gives the full commands to start the product and where to click. At
least once per lane, the same walk is done under the GOV.UK brand.

**10 November evening: tonight's order and where runs happen (the owner).** Demo-ready: L2.11, then L1.7, then D2b;
then the product repo published from `main` (make ci, make test and the image scans green on the test server). The
owner's laptop deployment is rebuilt only after the whole build, both tracks, is finished. Heavy runs leave the
owner's Mac: `make -k ci` and `make test` run on the test server (`stack_lease.sh offline`); browser tests run there
too (Chromium installed, 10 November) one lane at a time until T2's per-lane ports land, and in the Mac's two slots
otherwise. Lanes never open desktop apps on the Mac. Started tonight for tomorrow: admin T1 part 4, platform-b T2,
rules-b T3, case L3.H2, studio-b L1.10b; platform P7's acceptance on kind (down by 20:30).
