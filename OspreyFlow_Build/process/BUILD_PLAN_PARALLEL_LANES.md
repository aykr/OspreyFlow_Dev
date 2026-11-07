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

## Lane 1 · Studio (`lane/studio`) · Opus · medium

Continues the redesign's build plan (`spec/ingest_studio_redesign/` and `BUILD_PLAN_INGEST_STUDIO.md`).
Phase 5 is **not** in this lane (ADR-143 C1).

| Step | Work | Size | Exit (the build plan's, plus) |
| --- | --- | --- | --- |
| L1.1 | Phase 4's remainder: `make ci` green (the causes found at step 0) | S | Phase 4's exit tests green; `make ci` green |
| L1.2 | Phase 6: the canvas as editor, the Map editor, guided mode | L | Phase 6's exit; GOV.UK axe green |
| L1.3 | Phase 7a: the staging catalogue's engine (Knowledge Adapters, golden files, staged Parquet, `source_refs`) | L | Golden files per step; provenance survives a Join |
| L1.4 | Phase 7b: the drawers for each step | M | Phase 7's exit |
| L1.5 | Phase 8: expert steps | L | Phase 8's exit |
| L1.6 | Phase 9: connectors | M | Phase 9's exit |
| L1.7 | Phase 10: Operations content and external orchestration, inside Admin's *Running › Operations* (ADR-145 decision 9) | L | Phase 10's exit |

## Lane 2 · Glass and places (`lane/glass`) · Opus · medium (Sonnet for L2.6–L2.7)

| Step | Work | Size | Exit |
| --- | --- | --- | --- |
| L2.1 | The alerts gap map (ADR-145 N5): every alert's generation, triage, routing and case scope against ADR-109, 130, 133, 134; no code | M | A written map in `spec/` with its open questions as multiple choice for the owner |
| L2.2 | Three places: the switcher, the context banner and cross-links, Home's cards, the rail losing Ingest Studio, Admin and Proposed types; the GOV.UK header (ADR-145 decisions 1–3) | L | Each role sees only its places, and the hidden places' routes refuse it; `keyboard/shell.spec.ts` and axe (dark, light, GOV.UK) green; DEMO_GUIDE chapters touched say so |
| L2.3 | The case screen's first lightening (decision 4), from a prototype round the owner rules on first | M | The owner's ruling recorded; `keyboard/panel-frames.spec.ts` green |
| L2.4 | Admin regrouped into sections (decision 5); Datasets' highest marking and promotion policy columns (decision 8; fields from L3.1) | M | Every section shows only with its right; `keyboard/admin.spec.ts` green |
| L2.5 | People and roles: the row (R3), Author visibility and *Name an Author* (R1), custom roles (R2), *Disable…* with transfers (A4) | L | Decision 7's refusals at the route; disable refused with an item untransferred |
| L2.6 | Operations' promotions and ageing (O3), and the Audit section (O2) | M | The overdue alert fires once at N days; audit access test by unit |
| L2.7 | The data engineer's *Needs you* and the Model tab's count (A2) | S | Keyboard and tooltip cases |

## Lane 3 · Case contract and drawing (`lane/case`) · Opus · medium

The riskiest lane: every step starts with its access and existence-leak tests (rules 3 and 4), and the
`lane-reviewer` reads each step before it goes to the orchestrator.

| Step | Work | Size | Exit |
| --- | --- | --- | --- |
| L3.1 | Phase 5 as amended (ADR-140 Amendment, ADR-143 decision 1): target model per dataset, reference lists, ADR-126 derived, one dataset per case, composites, **each case's analyst layer and its read set**; `scripts.migrate_cases_to_one_dataset` (dry run first) also creates the layers | L | Phase 5's exit; ADR-143's "unchanged under case B" conformance case green; every seeded case reads one dataset plus its layer |
| L3.1b | Phase 5's target-model half: `TargetModel`, reference lists, ADR-126 derived, the domain-model node; a `packages/schemas` commit first; Lane 1's files agreed (the owner's ruling "New L3.1b", 7 November, case Q4) | L | Phase 5's exit in full |
| L3.2 | Case views replace branches (ADR-144), `scripts.migrate_branches_to_views` (dry run first) | L | ADR-144's tests; the selection bar's view actions by keyboard |
| L3.3 | Drawing boards (ADR-143 decisions 4–7): declare, link by handle, Alt-drag, right-click and keyboard; marking, grading, source; matching; pictures | L | `keyboard/boards.spec.ts`; one field analyst's check of moving versus linking (open question 4) |
| L3.4 | Promotion (decisions 8 and 10): the sheet, one load, the dataset's policy and highest marking, review; the Studio's *Analyst promotions* list in `ingest/runs/` by agreement with Lane 1 | L | ADR-143's promotion and policy tests; the owner's ruling on online revert (open question 2) |
| L3.5 | Analyst-defined link types (decision 9) and the Model tab's proposals block | M | A proposed type's links cannot be promoted; accepted, they can |
| L3.6 | The alert when a load meets a drawn item (decision 12) | M | One alert per match per case; *Open the board* |
| L3.7 | The grading scheme setting and its change command (decision 11) | S | The dry run writes nothing; grades keep their original |
| L3.8 | The ownership route Lane 2's *Disable…* reads (views, boards, promotions, proposed types per person) | S | Access test; Lane 2's L2.5 consumes it |

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

## File ownership

A lane changes only what it owns. Anything else is a request to the orchestrator, who either makes a
small shared commit and merges it first or moves the work to the owning lane.

**Ratified changes (the owner's ruling, 7 November 2026, "Ratify if needed").** A change outside a lane's
map that the brief's work needs is ratified by the orchestrator at review when the lane-reviewer finds
no conflict with another lane's work, and is recorded in the merge's friction row. Shared files
(`packages/schemas/**`, `keyboard/actionRegistry.ts`, `tokens.css`, the Makefile, `ci.yml`) stay
shared. A registry id is committed by the orchestrator immediately before the merge whose cases
prove it, not earlier, because `assertAllCovered` refuses an id with no proving case.

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

## What the owner checks by hand

After each merge, the orchestrator gives the full commands to start the product and where to click. At
least once per lane, the same walk is done under the GOV.UK brand.
