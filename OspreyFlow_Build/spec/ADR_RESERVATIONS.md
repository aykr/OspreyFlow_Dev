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
| ADR-143 Amendment 7 | Merging a drawn dataset as built (L3.9), with the owner's ruling of 10 November: drawn types mapped to the domain model's types in the Ingest Studio's Map step | case | 2026-11-10 | written |
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
| ADR-146 Amendment 4 | L2.10 as built: team routing (a routed alert read by the team's members and the home case's Authors, in the queue's query, trends and packs), one queue, filters, the lead's hand-off and Suppress until…, Raise an alert…, What raises alerts, watched patterns on a schedule | rules | 2026-11-09 | written |
| ADR-147 Amendment 1 | The analyst's map: the basemap switch, place search over the case's gazetteer, the three themes' contrast (P4) | platform | 2026-11-09 | written |
| ADR-147 Amendment 2 | The owner's rulings of 9 November: a Java runtime under the Classpath exception in the Conduit image, gazetteer places copied into a case's dataset at load, the gazetteer's unit a build setting (P5) | platform | 2026-11-09 | written |
| ADR-114 Amendment 37 | Backups in a folder the administrator names at setup, for every install, never inside the checkout (P5b) | platform | 2026-11-09 | written |
| ADR-114 Amendment 38 | Backups folder, as built (P5b): the decisions beyond Amendment 37, and a deployment name equal to a profile name refused so two deployments' sets never share a subfolder | platform-b | 2026-11-09 | written |
| ADR-140 Amendment 16 | A subscribed list read at the sample, at Test and at the run, correcting Amendment 13 point 10 (L1.8) | studio-b | 2026-11-09 | written |
| ADR-145 Amendment 8 | Disable and the items an administrator may not see: the ownership route's withheld flag and the refusal (the owner's ruling, L3.8) | orchestrator | 2026-11-09 | written |
| ADR-133 Amendment 10 | Declared amounts summed as Decimal(38,9) on both analytics adapters (event_frequency and account_activity): rounding, no-amount past 10^29 or inf/nan, no silent overflow (L2.10) | rules | 2026-11-09 | written |
| ADR-133 Amendment 9 | The owner's ruling of 9 November: L1.6's reference lists are the screening-list store of record; the Lists tab read-only, then retired | studio-b | 2026-11-09 | written |
| ADR-140 Amendment 15 | The owner's ruling of 9 November: an operator's allow-list in osprey.yaml admits named private hosts or networks to the SQL and API connectors | studio-b | 2026-11-09 | written |
| ADR-143 Amendment 6 | The grading change as built (L3.7): the verb over the scripts module, the dry run enforced (ruling C13), the Conduit stopped, the scheme file, what the change leaves alone | case-b | 2026-11-09 | written |
| ADR-145 Amendment 7 | The Studio's tips and who-can refusals as decided (built with L2.12's patches, L1.8): the roles that hold a right named, never people (the owner's ruling, 9 November); 'domain model' held by a gate | studio-b | 2026-11-09 | written |
| ADR-140 Amendment 17 | The recipes repository written in-process by dulwich, the git binary removed from the Conduit image (the owner's ruling of 9 November, "Replace with dulwich"), and the publish's refusals: an id one plain file name, no link followed, a compare-and-swap on HEAD, one lock over write, index and commit (L1.7a) | studio-b | 2026-11-10 | written |
| ADR-145 Amendment 9 | Disable's full transfer list as built (L2.5b): a view's or board's recipient held to the case's ceiling until a view's count is per reader (rule 3, decided on the strict reading); Admin › System's count said when it cannot be read, and the dry-run report's place | admin | 2026-11-10 | written |
| ADR-147 Amendment 3 | Gazetteer-only identifiers (osm_id, os_place_id, gss_code, gnis_feature_id, tiger_geoid, nad_address_id) withheld from every node for every request reader, whatever dataset it sits in, and a Location matched on its name alone when it carries one; uprn kept on a case's own Location (Amendment 1 point 3a); decided on the strict reading (CARRIES row 23) | platform-b | 2026-11-10 | written |
| ADR-148 Amendment 1 | The cloud-platform profile as built (P7); the context table's six Dockerfiles corrected to eight | platform | 2026-11-10 | written |
| ADR-141 Amendment 1 | Phase 10 as built (L1.7): open question 1 (the grant per pipeline, by Owned externally), open question 2 (a quota refusal not counted toward a pause), the run API, Operations' runs and quotas, and what is left | studio | 2026-11-10 | reserved |
| ADR-146 Amendment 5 | The rule's standards as built (L2.11a): the BPMN 2.0 and DMN files' shapes, namespace, caps and rights; the files stored beside each rule version by rules' L2.11 save, so Export returns what was stored (decision 3 as accepted, R2) | rules-b | 2026-11-10 | written |
| ADR-147 Amendment 4 | The case's gazetteer panel as built (P6): add and remove a gazetteer in the Glass by keyboard, the four empty cases in words, the buttons not drawn without run_pipelines; Amendment 2's "Left" closed | platform-b | 2026-11-10 | written |
| ADR-140 Amendment 18 | L1.7a's carries: a refused publish puts the file back as HEAD holds it; the aside sweep removes only an empty or .git-only aside; Amendment 17 point 6's sweep at first use corrected (under the in-process lock, before the flock exists) | studio-b | 2026-11-10 | written |
| ADR-142 Amendment 5 | A lane's pre-merge live check is a selection by change (`stack_lease.sh live`, route rights always, the full set for an unmapped path), with the full live set nightly on main (T1 part 3, the owner's word on faster runs) | admin | 2026-11-10 | written |
| ADR-148 Amendment 2 | The deployment's marking ceiling as built (L1.10, decision 10): the setting, loads and imports above it refused before a write, in words naming the limit; System shows it | studio-b | 2026-11-10 | written |
| ADR-135 Amendment 4 | The model route on the cloud-platform profile: the client's own approved gateway, or Bedrock (P11) | platform | 2026-11-10 | written |
| ADR-135 Amendment 5 | Laurium as a second extraction engine behind ModelPort.extract, chosen at setup (P12) | platform | 2026-11-10 | written |
| ADR-148 Amendment 3 | The ceiling's carries as built (L1.10b): each demo pack's highest marking declared and proved (public judged by what it stages), a refused staged run's step tables removed, and Test judging the ceiling | studio-b | 2026-11-10 | written |
| ADR-148 Amendment 4 | The ceiling on promotions and drawn merges as built (L3.H2): refused per item, on the record and before the load's transaction, in words naming the limit | case | 2026-11-10 | written |
| ADR-142 Amendment 6 | The fix-and-check order: both reviews at 'built', in parallel; one rebase, then one round of gates; heavy runs on the test server; a self-check list of recurring findings | orchestrator | 2026-11-10 | written |
| ADR-114 Amendment 39 | Refresh refuses, in words and before writing anything, a deployment rendered before ADR-135 Amendment 2 (or holding any unset required secret), naming the one-time `ospreyflow apply` route; it never mints or changes a held secret; which deployment a named update reaches; files moved into place whole (the v0.4.12 to v0.5.0 upgrade; retitled from the withdrawn minting approach) | platform-b | 2026-11-10 | written |
| ADR-142 Amendment 7 | A second merge session (the merger) prepares merges for lanes the orchestrator hands it; the orchestrator alone lands them on main, fast-forward only, and alone pushes (the owner's word, 10 November) | orchestrator | 2026-11-10 | written |
| ADR-110 Amendment 19 | A scheduled load's notice (a failed or refused run) reaches its owner in *Needs you*, owner-filtered in the query, since L2.10 removed the owner's own inbox that Amendment 3 decision 10 named | rules | 2026-11-10 | written |
| ADR-140 Amendment 19 | A Join's guard on markings: a table with no bound marking is unmarked and never joins a marked one (fail closed, as built in L1.7), unless its source declares a default marking, which its rows then carry before the join; the declaration audited | studio | 2026-11-10 | written |
| ADR-135 Amendment 6 | Laurium runs as its own Python 3.13 service, built only when chosen, behind a thin ModelPort.extract adapter in the Conduit, every call through the gateway; its licence record and the spaCy model's one source beyond PyPI (the owner's ruling of 11 November on P12's licence check) | platform | 2026-11-11 | written |
| ADR-142 Amendment 8 | The client chain sooner: P7 merged in two parts (P7a, its kind acceptance, after); P10, P9, P11, P12, L1.9 side by side once P7 merges, by template file; P9 cut (P9b after the install); P8 deferred; merges without the owner except access, credential and data-model steps (the owner's word, 11 November) | orchestrator | 2026-11-11 | written |
| ADR-148 Amendment 5 | The cloud-platform profile's proof-of-concept shape (`shape: poc`): one ArcadeDB and one ClickHouse with its Keeper inside the server, no PodDisruptionBudgets, a scratch volume for Ingest, a manual-install runbook and a decommission runbook (P7b) | platform | 2026-11-11 | written |
| ADR-148 Amendment 6 | Sign-in claims from Entra ID as built (P10 part 1): clearance, unit and handling codes mapped by settings from a named claim or a group table, one construction path, the tenant and issuer pinned, a principal keyed by `oid` within its tenant | admin | 2026-11-11 | written |
| ADR-140 Amendment 20 | L1.9 part 1 as built: the S3 and Athena connectors (read-only, by the namespace's IAM role; the named query's relations checked, failing closed). The host allowed only while the source is enabled is part 2's (ADR-148 decision 7) | studio-b | 2026-11-11 | written |

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
| ADR-146 Amendment 6 | The rule editor as built (L2.11): a declared dataset fixed at creation, draft, Test over 30 days and Make live with the dataset's second-person policy (ADR-145 A3), the per-version stored rule files, when a screening list refreshes, and the migration of whole-deployment rules; the template form just for its author, and who a rule runs as | rules | 2026-11-10 | written |
| ADR-135 Amendment 7 | The model route's two engine kinds as built (P11 part 1): the client's gateway and Bedrock by the namespace's IAM role in Admin › Models, Amendment 4's rules held to the cloud-platform profile, London-only model ids, no key in an address | platform-b | 2026-11-11 | written |
| ADR-110 Amendment 20 | A fault acting as a schedule's owner: the ledger keeps refused with the notice kind failed; the error's text stays in the log alone, and Am 19 point 5's "ledger" does not hold for this branch (rules-hyg) | rules | 2026-11-11 | written |
| ADR-114 Amendment 40 | The upgrade path's carries as built: one atomic writer for deployment.env, the refresh's lock, stage and pending record, every verb's lockout words; a value in the shell does not count as held (Am 39 decision 2 stands) | platform-b | 2026-11-11 | written |
| ADR-148 Amendment 7 | Backups on the cloud-platform profile as built (P9, cut): the encrypted scheduled backup of ArcadeDB and ClickHouse to S3 by the namespace's role, and one timed restore | case | 2026-11-11 | written |
| ADR-135 Amendment 8 | The model route wired into the cloud-platform profile as built (P11 part 2): the gateway rendered by default, its own service account and IAM role (Bedrock invocation in eu-west-2 only) while a Bedrock engine is enabled, the model host allowed only while an engine is enabled | platform-b | 2026-11-11 | written |
| ADR-135 Amendment 9 | Laurium wired into the cloud-platform profile as built (P12 part 2): its own service and egress to the gateway alone, the extraction-engine setting on cloud-platform only, the pack's preset Laurium (the owner's ADR-135 Amendment 5 decision 2; the earlier deep_read wording withdrawn 11 Nov) | case-b | 2026-11-11 | written |
| ADR-148 Amendment 8 | Entra ID's claims wired into the cloud-platform profile as built (P10 part 2): the claim settings in principal resolution, Keycloak not rendered, every reader of a role through principal_auth | admin | 2026-11-11 | written |
| ADR-140 Amendment 21 | L1.9 part 2 as built: the S3 and Athena connectors on the cloud-platform profile, with their hosts declared at install and rendered into the reading pod's own egress rows on 443, the IAM role's read-only statements scoped to the declared buckets, prefixes and workgroups, and Admin refusing a connection whose host was not rendered | studio-b | 2026-11-11 | written |
| ADR-146 Amendment 7 | One owner named on two screening lists: one alert citing both, each list's citation shown only to a reader cleared for it (the owner's ruling of 12 November 2026), a list's marking, a true positive confirming only what its closer reads (the owner's ruling), and live files removing the lists they load | rules | 2026-11-12 | written |
| ADR-145 Amendment 10 | The guides from Home: the user, developer and administration guides linked under the Glass, Ingest Studio and Admin cards a person's rights open, served by the Conduit to a principal holding that place's right | rules-b | 2026-11-12 | written |
| ADR-132 Amendment 7 | The GOV.UK phase banner's text settable in osprey.yaml (appearance.banner_text), shown in the Glass and on the sign-in page; unset, nothing changes | platform-b | 2026-11-12 | written |
| ADR-114 Amendment 41 | A shared-key prompt in the product's proxy on all three names, checked against a bcrypt hash the owner sets on the server, with noindex; unset, nothing changes | platform-b | 2026-11-12 | written |
| ADR-114 Amendment 42 | The shared-key pass covers the deployment's three names: osprey_pass written with Domain= the base name (as the theme cookie, ADR-072), so one prompt lets a visitor through to the sign-in name too (the owner, 13 Nov) | platform-b | 2026-11-13 | written |
| ADR-145 Amendment 11 | Home's "What you can do, and what you answer for" renamed "Your access and tasks", full width below the two columns, its headings beneath the title, and its wording plainer (the owner, 13 Nov) | platform | 2026-11-13 | written |
| ADR-132 Amendment 8 | The GOV.UK look inside a case's workspace made compact: a slim GOV.UK header, the banner on one slim line, and the place's context bar (ADR-145's "You are in …") on the same row as Case · Boards and the case, so the canvas gets the height (the owner, 13 Nov); Home and the sign-in page unchanged | platform | 2026-11-13 | reserved |
| ADR-145 Amendment 12 | The Glass's rail: Cases, Explore, Ask & Chat (Questions renamed) and Dashboards on the rail itself; ⋯ More renamed Explore Details, holding History, Ownership and Connection strength; and the rail's Help opens its panel over any view and toggles it (the owner, 13 Nov; amends Amendment 2's variant B) | platform-b | 2026-11-13 | reserved |
| ADR-050 Amendment 3 | A browser refresh keeps the person signed in and where they were: a silent prompt=none sign-in at load against the identity provider's own session before the Sign in screen is shown, and the place returned to is the one refreshed (Home stays Home, a case stays that case) (the owner, 13 Nov) | admin | 2026-11-13 | written |
| ADR-114 Amendment 43 | A deployment's own Postgres allows the connections its services need at rest: max_connections rendered from the product's own number (or the Conduit's pools bounded where idle is normal), proven by two Conduits against the rendered Postgres (the owner, 13 Nov, from CARRIES) | admin | 2026-11-13 | reserved |
| ADR-135 Amendment 10 | Corrects Amendment 8 decision 3 to the code: an engine's host is the gateway's alone (reach.engines [litellm]), and an engine disabled in Admin › Models keeps its host open until removed from osprey.yaml and rendered again | platform-b | 2026-11-13 | written |
| ADR-145 Amendment 13 | The Glass's mode toggle reads "Graph · Drawing board" (was "Case · Boards"), with a one-line note in each mode: "Graph: the case's data. Saved views are under Cases." / "Drawing board: your sketch; it does not change the case's data." (the owner, 13 Nov) | platform-b | 2026-11-13 | written |
| ADR-144 Amendment 3 | A "Views ▾" menu beside the graph's toolbar lists the case's saved views and opens one in a click; the Cases drawer keeps its list (the owner, 13 Nov) | platform-b | 2026-11-13 | written |
| ADR-114 Amendment 44 | Two Smalls on one server, by name: --name for a Small with server:, the doctor's 443 asked of listen_address and its graph-store check of graph_port, one model server shared by name (models.ollama_from), and an edge that routes by host name with TLS passed through (amends ADR-138 Am 1 item 11 and decision 2's "share no port" for the model server only) (the owner, 13 Nov: Part 3) | platform | 2026-11-13 | reserved |
| ADR-114 Amendment 45 | The Conduit's store pool sizes from settings (osprey.yaml), today's figures the default, the deployment's Postgres minimum derived from them (the owner, 13 Nov, R1 finding 15b) | admin | 2026-11-13 | reserved |
| ADR-135 Amendment 11 | Disabling a model engine in Admin › Models closes its egress too: the render reads Admin's enabled set, not only osprey.yaml's (the owner, 13 Nov; closes Amendment 10's gap) | platform-b | 2026-11-13 | reserved |
