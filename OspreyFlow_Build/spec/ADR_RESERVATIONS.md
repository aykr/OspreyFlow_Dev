# ADR and amendment reservations

ADR-142 decision 5 (P5). Lanes work in parallel, but `06_DECISIONS.md` hands out ADR and amendment
numbers in order and stays one file. So the orchestrator reserves each number here, in a one-line
commit to `main`, **before** a lane writes the record; the lane then writes the heading exactly as
reserved. `tools/adr_reservations_check.py` (`tests/test_adr_reservations.py`) reports any heading
above the baseline with no row here, any amendment heading not in the form `### ADR-n, Amendment m`,
and any number reserved twice.

## Reservations

Status is `reserved` (the number is held; the lane has not written it) or `written` (the heading is in
`06_DECISIONS.md`).

| Number | Title | Lane | Date | Status |
| --- | --- | --- | --- | --- |
| ADR-142 | Parallel lanes: one agent per worktree, one leased dev stack, an orchestrator that merges | orchestrator | 2026-11-06 | written |
| ADR-143 | The case and dataset contract: a case's analyst layer, drawing boards, and promotion into a dataset as a load | orchestrator | 2026-11-06 | written |
| ADR-144 | Case views replace branches | orchestrator | 2026-11-06 | written |
| ADR-145 | Three places, the Admin area regrouped, and roles an administrator can define | orchestrator | 2026-11-06 | written |
| ADR-140 Amendment 7 | Phase 5 held, and rebuilt under ADR-143 | orchestrator | 2026-11-06 | written |
| ADR-099 Amendment 13 | A case's analyst layer | orchestrator | 2026-11-06 | written |
| ADR-090 Amendment 4 | Proposed types are decided on the Studio's Model tab | orchestrator | 2026-11-06 | written |
| ADR-105 Amendment 3 | Pictures on drawn items | orchestrator | 2026-11-06 | written |
| ADR-133 Amendment 8 | A fourth decision for a second person | orchestrator | 2026-11-06 | written |
| ADR-084 Amendment 5 | Superseded in part by ADR-144 | orchestrator | 2026-11-06 | written |
| ADR-132 Amendment 6 | The place switch in the GOV.UK header | orchestrator | 2026-11-06 | written |
| ADR-110 Amendment 14 | The Admin area becomes a place of its own, in sections | orchestrator | 2026-11-06 | written |
| ADR-112 Amendment 4 | Roles an administrator defines, and five new rights | orchestrator | 2026-11-06 | written |
| ADR-143 Amendment 1 | Where today's analyst writes go: hand-marking and manual links into the layer, accepted proposals and extractions into the source (the owner's ruling "Split", 7 November) | case | 2026-11-07 | written |
| ADR-099 Amendment 14 | A case reading a composite adds no data: a composite is read-only for now (the owner's ruling, 7 November) | case | 2026-11-07 | written |
| ADR-136 Amendment 1 | A case's analyst layer takes the strictest egress of the case's sources (the owner's ruling, 7 November) | case | 2026-11-07 | written |
| ADR-025 Amendment 1 | A split held only in a case's analyst layer: the source SAME_AS goes ahead and the conflict is recorded for review in that case only (the owner's ruling, 7 November) | case | 2026-11-07 | written |
| ADR-099 Amendment 15 | In a case reading a composite, only its analyst layer is written; every other write is refused in words (the owner's ruling, 7 November) | case | 2026-11-07 | written |
| ADR-140 Amendment 8 | Phase 6 as built: the drawer beside the pipeline, Preview, guided and expert mode, the Map editor's strip and keyboard bind (the owner's rulings of 7 November: Q1 a, Q2 a, Q3 a) | studio | 2026-11-07 | written |
| ADR-145 Amendment 1 | Three places as built: each place follows the full checks its routes make; no route moves place; only the Studio's run history narrows (to run_pipelines); schedule preview exempt from place assignment; the GOV.UK header's local extension (the owner's corrected ruling, 7 November) | glass | 2026-11-07 | written |
| ADR-090 Amendment 5 | Proposed types stay in Admin until the Studio's Model tab shows them (L3.5) (the owner's ruling, 7 November) | glass | 2026-11-07 | written |
| ADR-115 Amendment 6 | Places a person cannot open are hidden, not dimmed (ADR-145 N6; the owner's ruling, 7 November) | glass | 2026-11-07 | written |
| ADR-110 Amendment 15 | A full snapshot's withdrawal takes back only the dropped rows' own events, never a node or a link, so what it changes never depends on what the loader cannot read (the owner's ruling "Only the rows' events", 7 November) | studio | 2026-11-07 | written |
| ADR-145 Amendment 2 | The case screen lightened: the column opens with the Inspector only; the rail keeps Cases and Explore, the rest under ⋯ More; the view switch keeps Graph and Map, the rest under More views (the owner's choice of variant B, 7 November) | glass | 2026-11-07 | written |
| ADR-145 Amendment 3 | Admin's sections as built: each section's right (Roles manage_people; Grading scheme, Approval rights and Uploads administer_system; Audit read_audit, which opens no place until Audit is built); Proposed types under Data; five coming placeholders that call nothing; the GOV.UK side navigation (the orchestrator's settlement under the owner's delegation, 7 November) | glass | 2026-11-07 | written |
| ADR-146 | The alerts journey: three sources, one queue, and Rules and Monitoring as a place of its own (the owner's records of 7 November) | orchestrator | 2026-11-07 | written |
| ADR-143 Amendment 2 | The analyst layer's lifecycle; drawn datasets and merging them; drawn items watched (the owner's records of 7 November) | orchestrator | 2026-11-07 | written |
| ADR-144 Amendment 1 | No branches anywhere: not in the code, the screens, the guides or the specs, and no branch has a layer (the owner's records of 7 November) | orchestrator | 2026-11-07 | written |
| ADR-145 Amendment 4 | Four places; a home case per dataset and its Authors; reporting folded into the places; roles made clear (the owner's records of 7 November) | orchestrator | 2026-11-07 | written |
| ADR-140 Amendment 9 | "Domain model" on screen; a drawn dataset as a third way to start a case; screening lists; releases as YAML; the owner step in Make live (the owner's records of 7 November) | orchestrator | 2026-11-07 | written |
| ADR-112 Amendment 5 | The Rule author role, two more rights, and teams (the owner's records of 7 November) | orchestrator | 2026-11-07 | written |
| ADR-142 Amendment 1 | Each session on a chosen Claude account; a lane can be paused and resumed on another (the owner's records of 7 November) | orchestrator | 2026-11-07 | written |
| ADR-142 Amendment 2 | A merge's make ci takes no lease: it touches no stack, and the port guard refuses the leased stack to anyone not holding the lease | orchestrator | 2026-11-07 | written |
| ADR-124 Amendment 17 | A jump to an alert whose evidence is not whole for the reader is refused exactly as a missing alert, before anything is created (rule 3; ADR-146's address test; L2.8's Q1, the orchestrator's settlement, 7 November) | glass | 2026-11-07 | written |
| ADR-109 Amendment 9 | Confirming a link's new revision repoints every open alert citing the old one in the same close, and the queue checks the new revision for every reader (L2.8's Q2, the orchestrator's settlement, 7 November) | glass | 2026-11-07 | written |
| ADR-109 Amendment 10 | A link superseded while alerts cite it is recorded before the graph's commit and settled from the graph's stored states; the settle runs before every read of alerts; a repointed alert's node is re-marked to its new evidence (L2.8b, the orchestrator's settlement, 8 November) | glass | 2026-11-08 | written |
| ADR-112 Amendment 6 | A right to edit a dataset's domain model, edit_target_model (D8), held by the data engineer, behind the dataset's own gate (ADR-140 decision 4; L3.1b, the orchestrator's settlement, 8 November) | case | 2026-11-08 | written |
| ADR-126 Amendment 3 | An existing dataset's first domain model is seeded as a live v1 whose packs are the union of the packs its cases chose, by scripts.seed_target_models (dry run first); until then a dataset has no model and the model routes say so (L3.1b, the orchestrator's settlement, 8 November) | case | 2026-11-08 | written |
| ADR-143 Amendment 3 | A fresh drawing's items live in its drawn dataset (L5 a); a drawn dataset is merged by an Author of the target holding merge_datasets, with a second person when the target's policy asks (L6 a) (the owner's rulings, 7 November) | orchestrator | 2026-11-07 | written |
| ADR-146 Amendment 1 | The team lead's queue tools are all four, Suppress until… included (R8 a) (the owner's ruling, 7 November) | orchestrator | 2026-11-07 | written |
| ADR-099 Amendment 16 | A load confined to one dataset matches only within its reach: the same person loaded into two datasets is two nodes, joined by resolution's scored SAME_AS (QB a) (the owner's ruling, 7 November) | orchestrator | 2026-11-07 | written |
| ADR-110 Amendment 16 | A row that comes back after a full snapshot withdrew it, and merges into its own withdrawn key's link, counts that merge as the row's own, so its load reverts (L1.2c, the owner's ruling A, 7 November) | studio | 2026-11-07 | written |
| ADR-110 Amendment 17 | A Studio load is stamped with its case's dataset and confined to it, by the scheduler and Run now alike, so two cases on two datasets never merge a link; Amendment 15's point 7 and its known limit restated as proven, and what is not driven (L1.2a Part A2) | studio | 2026-11-08 | written |
| ADR-110 Amendment 18 | A link write names its type: a merge and a supersede change only their own type's link, and a link state read refuses an id two types hold, so a returning row's load stays unrevertable there (L1.2d, the orchestrator's settlement, 8 November) | studio | 2026-11-08 | written |
| ADR-140 Amendment 10 | Phase 6's exit met: the reports pipeline built from scratch in guided mode by keys, an expert-mode edit, and a live walk under the lease (L1.2b, 8 November) | studio | 2026-11-08 | written |
| ADR-142 Amendment 3 | Six lanes: glass split into admin and rules, a platform lane for maps and model administration, docs after the new screens run deployed; lanes on chosen accounts (studio, case, rules and platform on sol); two throwaway stacks, each leased (the owner's records of 8 November) | orchestrator | 2026-11-08 | reserved |
| ADR-135 Amendment 2 | Model engines, each job's model and their keys are managed in the Glass's Admin place (keys write-only, never shown back, each change audited behind its own right); the CLI stays for headless and recovery use (the owner's ruling, 8 November) | platform | 2026-11-08 | written |
| ADR-147 | Maps administration: providers and their keys in Admin under the model keys' rule, the local basemap built and verified in the Conduit, prefetch areas on a schedule — ACCEPTED (design) | platform | 2026-11-08 | written |
| ADR-148 | Deploying into a namespace on a shared Kubernetes platform: the cloud-platform profile, first for the UK public sector client's Cloud Platform | platform | 2026-11-09 | written |
| ADR-143 Amendment 7 | Merging a drawn dataset as built (L3.9), with the owner's ruling of 10 November: drawn types mapped to the domain model's types in the Ingest Studio's Map step | case | 2026-11-10 | reserved |
| ADR-109 Amendment 11 | Every write that clones or replaces a link an alert can cite goes through the repoint journal, and the purge is published to connected canvases | rules | 2026-11-08 | written |
| ADR-112 Amendment 7 | A right to manage model engines, each job's model and their keys, manage_models, held by the administrator and grantable alone | platform | 2026-11-08 | written |
| ADR-140 Amendment 11 | Phase 7a as built: the staging catalogue's engine, its YAML keys, and staged rows' source references in each element's provenance | studio | 2026-11-08 | written |
| ADR-109 Amendment 12 | A corrected node an alert names is renamed in its referents through the repoint journal; L2.8c's carries | rules | 2026-11-08 | written |
| ADR-145 Amendment 5 | Custom roles, the Super user preset, teams and leads, and Disable as built (L2.5) | admin | 2026-11-08 | written |
| ADR-144 Amendment 2 | Case views as built: the refusal's name, no origin link on an alert's case (B14's link withdrawn), who applies a view's window and threshold, and an opened view is a read-only lens | case | 2026-11-08 | written |
| ADR-140 Amendment 12 | Phase 7b as built: staging steps as pipeline nodes, a drawer per step with its live sample, the run route feeding a pipeline's sources, per-step counts and staging metering, and a dataset's reference list rows from its version's file | studio | 2026-11-08 | written |
| ADR-135 Amendment 3 | Model usage and limits: calls and tokens per engine and job from the gateway's own records, limits per engine applied by the gateway on the engine's own key, a budget in tokens, no person in usage | platform | 2026-11-08 | written |
| ADR-146 Amendment 2 | Rules and Monitoring as built in L2.9: the place's gate and the five routes it shares (three reads, two writes); an alert's address; the jump replaced; the Rule author's queue read, as the owner ruled | rules | 2026-11-08 | written |
| ADR-145 Amendment 6 | Audit and Operations' ageing as built (L2.6) | admin | 2026-11-08 | written |
| ADR-142 Amendment 4 | Sister lanes: case-b, studio-b and rules-b take the steps that do not wait on their parent's current one, on the sol account; a third test stack (the owner's ruling, 8 November) | orchestrator | 2026-11-08 | reserved |
| ADR-140 Amendment 13 | Phase 9 as built: connectors (SQL, API, JSON) and the screening-list connector, its templates, deployment-wide import, subscription by list id, schedule and Refresh now (L1.6) | studio-b | 2026-11-08 | written |
| ADR-143 Amendment 4 | Analyst-defined link types as built (L3.5) | case-b | 2026-11-08 | written |
| ADR-140 Amendment 14 | Phase 8 as built: the SQL transform's sandbox and its _ref rule, the fuzzy match's inferred SAME_AS and inferred matched values, YAML editing in expert mode, the expert steps' disclosure, and open question 7 answered (L1.5) | studio | 2026-11-08 | written |
| ADR-112 Amendment 8 | write_sql_transforms (D12): the expert steps' right, held by no built-in role and granted singly by an administrator (L1.5) | studio | 2026-11-08 | written |
| ADR-146 Amendment 3 | load_screening_lists acts in Rules and Monitoring and in Studio › Sources' list connector, reconciling decision 2 with ADR-140 Amendment 9 decision 3; no one's rights change (L1.6) | studio-b | 2026-11-09 | written |
| ADR-143 Amendment 5 | Promotion and a removed case's layer as built (L3.4) | case | 2026-11-09 | written |
| ADR-146 Amendment 4 | L2.10 as built: team routing (a routed alert read by the team's members and the home case's Authors, in the queue's query, trends and packs), one queue, filters, the lead's hand-off and Suppress until…, Raise an alert…, What raises alerts, watched patterns on a schedule | rules | 2026-11-09 | reserved |
| ADR-147 Amendment 1 | The analyst's map: the basemap switch, place search over the case's gazetteer, the three themes' contrast (P4) | platform | 2026-11-09 | written |
| ADR-147 Amendment 2 | The owner's rulings of 9 November: a Java runtime under the Classpath exception in the Conduit image, gazetteer places copied into a case's dataset at load, the gazetteer's unit a build setting (P5) | platform | 2026-11-09 | written |
| ADR-114 Amendment 37 | Backups in a folder the administrator names at setup, for every install, never inside the checkout (P5b) | platform | 2026-11-09 | written |
| ADR-114 Amendment 38 | Backups folder, as built (P5b): the decisions beyond Amendment 37, and a deployment name equal to a profile name refused so two deployments' sets never share a subfolder | platform-b | 2026-11-09 | reserved |
| ADR-140 Amendment 16 | A subscribed list read at the sample, at Test and at the run, correcting Amendment 13 point 10 (L1.8) | studio-b | 2026-11-09 | written |
| ADR-145 Amendment 8 | Disable and the items an administrator may not see: the ownership route's withheld flag and the refusal (the owner's ruling, L3.8) | orchestrator | 2026-11-09 | written |
| ADR-133 Amendment 10 | Declared amounts summed as Decimal(38,9) on both analytics adapters (event_frequency and account_activity): rounding, no-amount past 10^29 or inf/nan, no silent overflow (L2.10) | rules | 2026-11-09 | reserved |
| ADR-133 Amendment 9 | The owner's ruling of 9 November: L1.6's reference lists are the screening-list store of record; the Lists tab read-only, then retired | studio-b | 2026-11-09 | written |
| ADR-140 Amendment 15 | The owner's ruling of 9 November: an operator's allow-list in osprey.yaml admits named private hosts or networks to the SQL and API connectors | studio-b | 2026-11-09 | written |
| ADR-143 Amendment 6 | The grading change as built (L3.7): the verb over the scripts module, the dry run enforced (ruling C13), the Conduit stopped, the scheme file, what the change leaves alone | case-b | 2026-11-09 | written |
| ADR-145 Amendment 7 | The Studio's tips and who-can refusals as decided (built with L2.12's patches, L1.8): the roles that hold a right named, never people (the owner's ruling, 9 November); 'domain model' held by a gate | studio-b | 2026-11-09 | written |
| ADR-140 Amendment 17 | The recipes repository written in-process by dulwich, the git binary removed from the Conduit image (the owner's ruling of 9 November, "Replace with dulwich"), and the publish's refusals: an id one plain file name, no link followed, a compare-and-swap on HEAD, one lock over write, index and commit (L1.7a) | studio-b | 2026-11-10 | reserved |
| ADR-145 Amendment 9 | Disable's full transfer list as built (L2.5b): a view's or board's recipient held to the case's ceiling until a view's count is per reader (rule 3, decided on the strict reading); Admin › System's count said when it cannot be read, and the dry-run report's place | admin | 2026-11-10 | reserved |

## Baseline

The decision log as it stood at `b548d9f` (6 November 2026), before reservations existed, generated by
`python -m tools.adr_reservations_check --baseline` (the owner's ruling "Baseline table", step 0).
Nothing at or below these numbers needs a row. This section is never edited after step 0.

Last ADR at the baseline: ADR-141
Amendment headings in another form at the baseline: 15

| ADR | Last amendment at the baseline |
| --- | --- |
| ADR-006 | 1 |
| ADR-034 | 2 |
| ADR-045 | 1 |
| ADR-048 | 1 |
| ADR-049 | 2 |
| ADR-050 | 2 |
| ADR-051 | 5 |
| ADR-052 | 12 |
| ADR-053 | 1 |
| ADR-054 | 6 |
| ADR-055 | 9 |
| ADR-056 | 24 |
| ADR-058 | 11 |
| ADR-060 | 2 |
| ADR-064 | 1 |
| ADR-080 | 3 |
| ADR-081 | 3 |
| ADR-084 | 4 |
| ADR-086 | 1 |
| ADR-089 | 1 |
| ADR-090 | 3 |
| ADR-091 | 1 |
| ADR-092 | 3 |
| ADR-094 | 1 |
| ADR-095 | 2 |
| ADR-097 | 2 |
| ADR-098 | 6 |
| ADR-099 | 12 |
| ADR-100 | 9 |
| ADR-101 | 2 |
| ADR-102 | 4 |
| ADR-105 | 2 |
| ADR-106 | 1 |
| ADR-108 | 6 |
| ADR-109 | 8 |
| ADR-110 | 13 |
| ADR-111 | 8 |
| ADR-112 | 3 |
| ADR-113 | 5 |
| ADR-114 | 36 |
| ADR-115 | 5 |
| ADR-116 | 1 |
| ADR-120 | 19 |
| ADR-121 | 1 |
| ADR-122 | 2 |
| ADR-123 | 1 |
| ADR-124 | 16 |
| ADR-126 | 2 |
| ADR-127 | 47 |
| ADR-128 | 6 |
| ADR-129 | 3 |
| ADR-130 | 2 |
| ADR-132 | 5 |
| ADR-133 | 7 |
| ADR-134 | 2 |
| ADR-135 | 1 |
| ADR-138 | 1 |
| ADR-139 | 3 |
| ADR-140 | 6 |
