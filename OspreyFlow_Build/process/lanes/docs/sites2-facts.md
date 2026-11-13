# sites2: every claim in the two animations, checked against main and the guides

The docs lane, 13 November 2026, for `BRIEF_sites2.md` item 3 ("facts"). Checked against main at efdb75a, the same as
`lane/docs-sites2`'s base, and against release v0.5.0 (4b8de6c, CHANGELOG 2026-11-10). The orchestrator accepted the
changes as listed in the lane's first report, the same day. Paths are relative to `OspreyFlow_Core/` unless they start with
`spec/`. **UG**, **AG**, **DG** and **ArchG** are the user, administration, developer and architecture guides in
`OspreyFlow_Core/docs/`. The animations' source is `marketing_site/sites/overview.py` and `govanim.py`.

Names, figures, times and case names in every drawing are invented, and each section says so. The Features, Get started
and UK public sector pages keep the text corrected on 12 November (`BRIEF.md` item 3): where the 13 November design's text
differed from it, ours was kept.

## The overview: eleven chapters

| Chapter | Claim in the design | Verdict | Now reads | Source |
| --- | --- | --- | --- | --- |
| Analyst 1, Network | Expand from one person, communities, a path between two people, ranked by betweenness | Confirmed | Unchanged | UG §5.2, §5.7, §5.8 |
| Analyst 2, Drawing board | Grading "B · 2 · P" | Changed | "Grading, 5x5x5: B · 2 · 1". B·2·P is valid only under 3x5x2; the default is 5x5x5 | packages/schemas/domain.py:293-316; UG §5.14; AG app. A `grading.scheme` |
| | Drawn by, source, marking, kept in the case's analyst layer | Confirmed | "Source note" for "Source" | domain.py:391, 402-410; UG §5.14 |
| | "Promotion is a load of its own, reviewed by a second person" | Changed | "…reviewed by a second person where the dataset asks". The default policy is `author_promotes` | packages/schemas/admin.py:217, 240; services/api/promotions.py:424, 661; AG §9.10 |
| | Panel "Boards · yours until you share it" | Changed | "Drawing board · Board 3 · Operation Ledger (synthetic)". The guides use no such words | UG §5.14 |
| Analyst 3, Alerts | One queue for every alert you may see; severity, why, who may see it, age | Confirmed | Who-may-see values as the screens give them ("The case team", "Shared with team"), age as "2 hours old" | UG §7.1, §7.2 |
| | "A high-severity close waits for a second person" | Changed | "Propose the close: a second person approves a high-severity one". Sub line: "…approves closing a high-severity one that others may see". An alert only its owner can see is closed alone | services/api/alert_queue.py:445-450; UG §7.3, §7.12 |
| | True match; Claimed | Confirmed | Unchanged | UG §7.3; domain.py:1110-1115; UG §7.1 "Claim" |
| Analyst 4, Dashboards | "Dashboards for leadership" | Changed | "…for the people who read the figures". The role is Reports Viewer; "leadership" is not a product term | UG §9; AG §9.2 |
| | "Monitoring board"; tiles including "Waiting for a second person" | Changed | "Alert monitoring"; tiles "Alerts raised this week", "Closed with an outcome", "Hotlist matches", as the board has them | UG §9 ("alerts raised each week and by rule, closed by outcome, … hotlist matches") |
| Developer 1, Data model | "Published as model v14"; "…and their markings, published as a version" | Changed | Chips "Model v14 · live" and "v15 · draft"; sub "…kept as numbered versions, one live and one draft". The product says "made live". Markings belong to the handling scheme, not the model. Making a model live has no screen yet, only its route (DG §3.3 "Coming"), so no button is drawn | packages/schemas/dataset_model.py:172-186; DG §3.3 |
| | "Each type carries its own colour and shape" | Changed | "Each type is drawn with a colour and a shape". Nine channels and six shapes can repeat across types | packages/ontology/default.yaml:121-156 |
| Developer 2, Ingest Studio | "Pipeline"; 1 Model, 2 Sources, 3 Pipelines, 4 Runs; Verify shows what a file would create and reject before it loads | Confirmed | "Pipeline" everywhere, the screens' word (the owner, 13 November) | DG §3, §3.8; ingest/dag/PipelineStudio.tsx |
| | "Nothing reaches a case without a pipeline someone published" | Changed | "Loaded data reaches a dataset only through a pipeline someone published", as the corrected Features page says | DG §3 |
| | "A load can be taken back" | Confirmed, with a caveat | Unchanged. Today it is a host command shown in 4 Runs; a revert button is "Coming" | DG §6.4 |
| Developer 3, Rule editor | A sentence of blanks from your own types and links, no formula; preview on the last 90 days, which raises and writes nothing; Make live | Confirmed | Sub line adds "tested on the last 30" | UG §7.6, §7.8 |
| | "When a Person calls a number on a hotlist" | Changed | "When a Phone is on one of my hotlists", a blank the editor offers | UG §7.6 ("And is … on one of my hotlists") |
| | "A rule for the whole deployment needs a second person" | Changed | "Make live waits for a second Author where the dataset asks". No new rule covers the whole deployment | UG §7.6; AG §9.4, §9.6; services/api/rule_editor.py:71-78 |
| Administrator 1, Architecture | Glass, Conduit and Vault; four typed ports | Confirmed | Ports written as the spec writes them: GraphPort, AnalyticsPort, ComputePort, ModelPort | spec/00_ARCHITECTURE.md §2; ArchG §2 |
| | Conduit: "Model routing" | Changed | "Extraction" in its place; LiteLLM is the Vault's model serving behind ModelPort. "Python · FastAPI" | spec/00_ARCHITECTURE.md:16-28; ArchG §8 |
| | Vault: ArcadeDB, ClickHouse, OpenSearch, PostgreSQL, Object store, LiteLLM | Changed | ArcadeDB, "DuckDB or ClickHouse", "OpenSearch or PostgreSQL", Valkey, "Object storage", LiteLLM, as the corrected Features page says | ArchG §2; packages/adapters/* |
| Administrator 2, Access | "No one can give more than they hold" | Changed | "Nobody can give more than they hold, clearance included" | AG §9.2 |
| | "Sign-in through your organisation: Entra ID or any OpenID Connect provider" | Changed | "On a server of your own: sign-in through Entra ID, ADFS or OpenID Connect". Not on Lite | AG §5a.1, §7 |
| | "Disabling a person first asks who receives what they answer for" | Changed | "…who takes each thing they answer for" | AG §9.9 |
| | Roles Analyst, Data Engineer, Rule author, Reports Viewer; clearances OFFICIAL, OFFICIAL-SENSITIVE; nothing hidden is counted | Confirmed | Unchanged | AG §9.2; packages/ontology/handling/uk-le.yaml:4; CLAUDE.md rule 3 |
| Administrator 3, Datasets | Sub line: "Merges are reviewed by a second person, and the model and each pipeline are versioned" | Changed | The owner's sub line, accepted 13 November: "Every load is recorded with the pipeline version that made it, and can be reverted. The dataset's model is versioned: one live, one draft, and every earlier version can be restored." | BRIEF_sites2.md item 5; dataset_model.py:172-186 (`DatasetModelView`, `RevertModelInput`); domain.py:275, 496 (`load_id`, `recipe_version`) |
| | Chips "Domain model v14", "Pipeline v3" | Changed | Each load tagged "pipeline v3", one struck through as "Reverted"; a model card "Model v14 · live / v15 · draft"; no version on the dataset | BRIEF_sites2.md item 5 |
| | "Promotion · Second person approved" | Changed | "Load 14 · promotion · 6 drawn items, as a load · Reviewed where the dataset asks" | as Analyst 2 |
| | "Highest marking: OFFICIAL-SENSITIVE"; "Egress: none" | Confirmed | "Highest marking it may hold: OFFICIAL-SENSITIVE", the screen's words. A per-dataset field, not a caveat | admin.py:210, 227; AG §9.10 |
| | "Backups are verified before an update" | Changed | "An update backs everything up first, and rolls back if it fails". The update checks image signatures, not the backup; checksums are checked on restore | AG §14; harness/update.py |
| | A scheduled run | Confirmed | Unchanged | DG §6.3 |
| Administrator 4, Audit | Filters "All actions, Exports, Approvals, What may leave" | Changed | The real ones: "Cases, people, datasets and loads", "Loads and promotions", "People and roles", "Datasets" | AG §9.11 |
| | "Exported a report pack, approved and recorded"; "Closed an alert … a second person approved" | Changed | Entries of the audit's own kinds: a run (load 15), a promotion (load 14), an egress change, a refused read, a disable with transfer. Pack exports have no approval step | AG §9.11; services/api/packs.py:282-313 |
| | "Read with the administrator's own access. Nothing is deleted." | Changed | "Where your own read of a record would not show its words, the entry says so. The log is append-only." | AG §9.11; spec/03_CONDUIT_MIDDLEWARE.md:1624 |

## The GOV.UK animation: four steps (ospreyflow.org's UK public sector page only)

| Step | Claim | Verdict | Now reads | Source |
| --- | --- | --- | --- | --- |
| 1, One setting | `osprey.yaml` `appearance: brand: govuk`; a setting, not a fork | Confirmed | Unchanged | AG app. A; spec/06_DECISIONS.md ADR-132 |
| | The install command without `--mode` | Changed | `ospreyflow install --mode lite …`: the install refuses without a mode (the 12 November finding, and `test_sites.py`'s install check) | cli/ospreyflow/main.py |
| 2, Your service | The install asks for the service's name, the organisation and the phase; the Beta banner "This is a new service."; the four places in the header; "Built with OspreyFlow, open source." in the footer | Confirmed | Unchanged | AG §1a; apps/workspace/src/brand/govuk/PhaseBanner.test.tsx:27; GovukFooter.tsx:40; UG §3 |
| | Case names "Operation Ledger (synthetic)", "HMP demonstration case (synthetic)" | Changed | "Operation Ledger (synthetic demo)", "HMP fixture (synthetic demo)", as the starters name them | UG §4 (starter table) |
| 3, Same product | An "Inferred" company with a "Confirm" button | Changed | "A possible match": "Inferred", "This / Same as / Came from", and **Confirm as the same**. There is no Confirm button on an inferred entity; the screens confirm a match, a candidate or an alert | apps/workspace/src/canvas/linkMenu.ts:61; UG §1, §5.11 |
| | Colours and shapes the same under either look | Confirmed | Unchanged | apps/workspace/src/design/tokens.css:172-176 |
| 4, Accessible | The Matrix as tables; columns "From, Link, To, Times seen" | Changed | "From, Type, To, Marking": the Links table has a type, two ends, a marking and a provenance | UG §5.11 |
| | Tab, arrow keys | Confirmed | "Each table is one Tab stop; arrow keys move between cells…" | UG §5.11 |
| | "Accessibility scans run on every screen, in each look" | Changed | "Automated accessibility scans run on the screens we test", as the corrected UK public sector page says | 12 November correction |
| The line under it | "The crown and the GOV.UK logotype are drawn only on a gov.uk domain" | Changed | "This is the website's own drawing of the GOV.UK theme, not a screen from the product…". Off gov.uk the product draws no crown but does draw the GOV.UK word mark, in GDS Transport. The site's own rule (no crown, no logotype, Arial) is the owner's; the line no longer says it is the product's | apps/workspace/src/brand/govuk/GovukHeader.tsx:18-45; tokens.css:189; ADR-132 Amendment 8 (the crown rule is on main only, a09546e) |

## In the release, or only on main

Everything the animations claim is in release v0.5.0 except two things. The crown rule off gov.uk (a09546e, 13 November) is
on main only, and the drawing does not claim it. The guides' statement that no new rule covers the whole deployment
describes v0.5.0's code too, but v0.5.0's own guide still described such rules. The pages name the release from the
CHANGELOG at build time. `build.py` refuses to build once the CHANGELOG names a release other than `CHECKED_AGAINST`
(v0.5.0), until every claim marked as in a release or only on main has been checked against the new one.
