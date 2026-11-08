# Build plan: three outcomes in parallel lanes

6 November 2026 · for the owner and the orchestrator · companion to ADR-142 to ADR-145 and
`SESSIONS_RUNBOOK.md`.

Three outcomes, built at once (ADR-142):

1. **A more usable Ingest Studio:** the rest of the redesign, ADR-140 and ADR-141.
2. **A clear Glass:** three places, a context banner, a lighter case screen, alerts mapped, Admin
   regrouped and roles an administrator can define (ADR-145).
3. **Drawing for field analysts on a bulletproof case and dataset contract:** the analyst layer,
   case views, drawing boards, promotion (ADR-143, ADR-144).

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
| O-acc | ADR-142 Amendment 1: `accounts.conf`; `--account` on `open`, `resume`, `headless` and the orchestrator's start; `pause`, `pause --now`, `switch`; the `paused` heartbeat state; `HANDOFF.md`; the merge gate's `wip(` refusal; Prompt R's handoff line; the monitor's *Account* column; `fallback` lines | M | ADR-142 Amendment 1's six tests green and shown red first; the runbook's commands updated; the owner can pause the case lane and resume it on another account by hand |

## Lane 1 · Studio (`lane/studio`) · Opus · medium

Continues the redesign's build plan (`spec/ingest_studio_redesign/` and `BUILD_PLAN_INGEST_STUDIO.md`).
Phase 5 is **not** in this lane (ADR-143 C1).

| Step | Work | Size | Exit (the build plan's, plus) |
| --- | --- | --- | --- |
| L1.1 | Phase 4's remainder: `make ci` green (the causes found at step 0) | S | Phase 4's exit tests green; `make ci` green |
| L1.2 | Phase 6: the canvas as editor, the Map editor, guided mode | L | Phase 6's exit; GOV.UK axe green |
| L1.2d | Found by L1.2c on main: `upsert_edges`' merge writes `g.E().has("id",…)` untyped, so a merge rewrites every link type holding that id. Type the merge's write, as L1.2c typed the restore; a conformance case with two types sharing an id, red first | S | Only the merged type changes |
| L1.3 | Phase 7a: the staging catalogue's engine (Knowledge Adapters, golden files, staged Parquet, `source_refs`); it carries reference lists of kind `screening` (ADR-140 Amendment 9 decision 3), the engine only, no screen | L | Golden files per step; provenance survives a Join; a screening list round-trips through the catalogue |
| L1.4 | Phase 7b: the drawers for each step | M | Phase 7's exit |
| L1.5 | Phase 8: expert steps | L | Phase 8's exit |
| L1.6 | Phase 9: connectors; and the screening-list connector in Sources, mapping templates (OFAC SDN, OFSI, UN, EU, OpenSanctions where licensed, blank) with synthetic golden files, deployment-wide import and per-dataset subscription, schedule and *Refresh now* (ADR-140 Amendment 9) | L | Phase 9's exit; each template maps its golden file; a rule offers only subscribed lists (with Lane 2) |
| L1.7 | Phase 10: Operations content and external orchestration, inside Admin's *Running › Operations* (ADR-145 decision 9); and Studio › Releases, the YAML bundle, `packages/schemas/release.schema.json` (a `packages/schemas` commit first), `ospreyflow release export` and `import --dry-run` (ADR-140 Amendment 9 decision 4) | L | Phase 10's exit; ADR-140 Amendment 9's release tests |
| L1.8 | The Studio's tips and *who can* refusals (ADR-145 Amendment 4 decision 12), from `help/roles.ts`; *Domain model* wording everywhere; `tools/ui_words_check.py` | S | No "target model" on screen; every disabled action says why and who can |

## Lane 2 · Glass and places (`lane/glass`) · Opus · medium (Sonnet for L2.6–L2.7)

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
| L2.8c | From L2.8b's review: the other supersedes that clone or replace links alerts can cite (`supersede_node`'s clones in confirm_node and retract_node, `supersede.py`, `pipeline_run`, `same_as_writer`'s NOT_SAME_AS) go through the repoint journal, each red first with an alert citing the old link | S | An alert citing a link each caller replaces stays listed for its readers, each red without the journal |
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
- **D2 (after L2.9 merges):** the user, developer and admin guides, the website and the deck: four
  places; no branches; three alert sources and one queue; Rules and Monitoring and the rule author; home
  cases, Authors and teams; screening lists; releases; the Reports Viewer's journey; the roles' words from
  `help/roles.ts`; GOV.UK screenshots too. The website marks unbuilt features *coming*. Exit: `make ci`'s
  spec and link gates; no "three places" and no "branch" outside the pipeline DAG. Until then the website
  and deck edits that say "three places" are held (ADR-145 Amendment 4).

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
| Glass | `apps/workspace/src/{shell,layout,home,welcome,admin,statusbar,theme,brand}/**`; `apps/workspace/src/alerts/**` read-only during L2.1; the Admin and audit routes in `services/api`; the GOV.UK header |
| Case | `services/api/dataset_scope.py`; `services/api/working_set/**`; the case, view, board and promotion routes; the graph adapter's access step; `apps/workspace/src/{canvas,investigation}/**` and new `boards/`, `views/`; `scripts/migrate_*` |
| Docs | `OspreyFlow_Core/docs/**`, `OspreyFlow_Build/marketing_site/**`, `OspreyFlow_presentations/**` |
| Orchestrator | `spec/06_DECISIONS.md` (appends, reservations), `spec/ADR_RESERVATIONS.md`, `process/**`, `OspreyFlow_Build/tools/friction_assemble.py`, `OspreyFlow_Build/tools/adr_reservations_check.py`, `OspreyFlow_Build/scripts/{stack_lease,lanes_heartbeat,lanes_launch}.sh` |
| Shared, by small orchestrator-merged commits only | `packages/schemas/**` (and the generated types); `keyboard/actionRegistry.ts`; `apps/workspace/src/design/tokens.css`; `OspreyFlow_Core/Makefile` and `.github/workflows/ci.yml` (the owner's) |

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
13. D2 after L2.9, then again after each later merge that changes a screen.
14. No brief for L2.5, L2.7, L2.9–L2.12, L3.1b–L3.4, L3.6, L3.9 or the new L1.3, L1.6, L1.7 before the
    owner's records of 7 November are on `main` (`process/inbox/specs_2026-11-07`, applied at the commit
    that appends them).

## What the owner checks by hand

After each merge, the orchestrator gives the full commands to start the product and where to click. At
least once per lane, the same walk is done under the GOV.UK brand.
