# Alerting and monitoring as a core feature

**Status:** planned 1 November 2026, at the owner's request; nothing built yet. It runs after the
GOV.UK deck work in flight (capture, decks, merge) and before the repository move
(`REPO_MOVE_PLAN.md`), unless the owner reorders them.

**The owner's requests (1 November 2026):**
- "Event monitoring and alerting needs to be highlighted as key features, this means that the reporting
  screens should allow for this as well." The owner chose all three: alerts in report packs, a
  monitoring dashboard, and alert trends.
- "Add the use cases to illustrate alerting and monitoring to the prison Intelligence demo as well as
  the AML demo case."
- "I would also like alerting and monitoring features to be highlighted as core feature hence all the
  decks and guides will need updated."

**Already done:** ADR-115 Amendment 4 puts "event monitoring and alerting" in the product's one-line
description, as a fifth capability on the welcome page and as a part of About.

## Where the demos stand

- **Prison Intelligence:** one alerting moment, in chapter 9: a hotlist on the coordinator's number
  fires when the batch-2 seized-phone file loads. The alert names the hotlist entry, the node it
  matched, and the file and row.
- **Operation Ledger (AML):** the structuring ring raises a typology alert as it loads, and the
  onboarding file is screened before commit. Both are part of the loading story; nothing shows
  ongoing monitoring of later data.

## The owner's choices (1 November 2026)

- **Use cases:**
  - all of P1–P4, "built into the story line as well": they become part of the prison demo's
    narrative, not an appendix;
  - all of A1–A4.
- **Order:**
  1. Finish the current deck work.
  2. The reporting ADR, then the demo use cases on top of it, then guides and decks (this plan).
  3. One more change before the repository move: the website pages say that OspreyFlow now has a
     fully featured, GDS-compliant UK public sector option that any UK department can use.
  4. Then the repository move (`REPO_MOVE_PLAN.md`).

## What is built today (read 1 November 2026; file references in the session's findings)

- **One `alerts` table for every kind** (`services/api/alerts.py`), told apart by `rule_id`:
  - typology alerts (`typology:<rule>`; KYC rules are typology alerts too);
  - hotlist alerts (`hotlist:<id>`, owned by the recipient);
  - monitor alerts (`monitor:<id>`);
  - scheduler run notices.
  An alert has no handling field of its own; triage gives it a status, a disposition, a reason and
  who decided.
- **Only typology alerts reach the case queue and the reporting figures** (`typology IS NOT NULL`).
  Hotlist and monitor alerts are in the owner's own list and in no figure. P4 and A4 therefore need
  hotlist and monitor alerts counted too, which the reporting ADR must decide.
- **The reporting feed already carries alerts by typology by week** (the `raised` section), alerts
  open by age, and outcomes, per case. So part of the monitoring dashboard's feed exists; no
  monitoring dashboard does.
- **Report packs** hold four item kinds (trend, assessment, entity, note), and each item is withheld
  unless the reader may view every handling it rests on.
- **Trends** count analytics events only. Alerts are in Postgres, not the event store, so an alert
  trend needs a new source.
- **Matters to settle in the reporting ADR, not to fix here:**
  - pack items and queue alerts are checked for visibility after the rows are read, in the Conduit,
    which rule 3 forbids for retrieval (ADR-111 and ADR-113 describe them as all-or-nothing checks);
  - ADR-113 decision 4 still says "how many" where Amendment 5 made it yes or no;
  - the owner's alerts route's docstring says "the case's datasets", but the store scopes it to the
    owner.

## Built by ADR-134 (build-order step 4, 1 November 2026)

- **Alerts in report packs:** a fifth item kind, `alert`, resting on every node, link and transaction
  it cites; withheld as a yes or no; checked item by item on export; says open, and inferred.
- **The monitoring dashboard:** four feed sections (`raised_by_rule`, `closed`, `time_to_close`,
  `hotlist_matches`) over every kind, through the same sync and mart; the board is described in the
  administration guide (no board ships as a file).
- **Alert trends:** `source: alerts` in the trend builder, read through `AnalyticsPort.alert_trend`
  over alert facts the alert store keeps in the analytics store.
- **The rule-3 review of the pack and queue readers — what was found:**
  - *Packs:* the reader's items were read whole into the Conduit and filtered there. No count left
    the Conduit (a yes or no only) and no order changed (no positions), but every hidden item was
    read. Moved into the pack store's query; the Conduit check stays as a second line.
  - *The case queue* (`alert_queue.queue`, which the Reports figures and neighbourhood risk count):
    read each alert's nodes in turn and stopped at the first hidden one, so the number of graph
    reads grew with the alerts the reader may not see — a timing leak, shown as 8 reads against 2
    (`test_case_queue_reads.py`). Now one batched read through the one queue.
  - *The one queue* (`monitoring_queue`): already scoped in the query and one batched read; no leak
    found. What remains in every reader: an alert's referents are checked against the graph after
    the SQL, as ADR-039 requires, so the size of that one batch grows with the alerts in the
    reader's SQL scope, hidden ones included; opening one alert by its id still reads its nodes in
    turn (the reader must already hold the id, and is told "not found" either way).

## Built by step 8b (1 November 2026): the Ledger's monitoring week and the UK Sanctions List

- **A1–A4** (ADR-108 Amendment 5; `packages/demo_fixtures/ledger_monitoring.py`): the bank's next
  weekly export raises a pass-through (rapid movement) and a circle (circular flow) through the case's
  rules on load, and a hotlist alert on a mule's account; a synthetic UK Sanctions List update raises a
  screening alert on Sofia Ruiz; the pass-through, closed as *Referred*, reaches the pack and the
  figures. Golden and negative tests: `tests/scenarios/test_ledger_monitoring_storyline.py`.
- **The UK Sanctions List (FCDO) connector** (ADR-133 Amendment 6), OGL v3.0; the OFSI connector
  marked as reading a closed list.
- **Two fixes:** a hotlist can watch an account number; a money-flow rule judges only accounts its
  author may see (rule 3).

## Built by ADR-133 stage (c) (build-order step 6, 1 November 2026)

- **Connectors** (`packages/knowledge_adapters/screening_lists.py`): OFAC SDN, OFSI consolidated, UN
  and EU consolidated, OpenSanctions (and, from step 8b, the FCDO's UK Sanctions List), each a Knowledge Adapter with synthetic golden files
  (`tests/knowledge_adapters/golden/screening_lists/`), refusing a file not in its format in words.
  Licences in spec 00 §7 (OFSI's list closed on 28 January 2026; the UN list has no open licence found).
- **Lists as managed sources** (`services/api/screening.py`, `screening_refresh.py`): subscriptions,
  versions, a diff per update, every refresh recorded; rule 9 by the repository's synthetic manifest or
  the device's exceptions file; routes for the Lists screen, subscribing and *Refresh now*; the operator
  command `scripts/refresh_screening_list.py`. The schedule is stage (d)'s: `scheduler.py` runs recipes
  only.
- **Re-screening** against the added and changed entries only, as each `kyc_screening` rule's deployer
  within its case's datasets; matches written `inferred`, alerts high severity in the one queue.
- **The AML templates** (`services/api/aml_rules.py`; `AnalyticsPort.account_activity`, DuckDB and
  ClickHouse, conformance first): high-risk jurisdiction, large cash, dormant account reactivated,
  sudden rise in velocity.
- **The Glass** (`src/alerts/ListsPanel.tsx`, the Rules tab), user guide 1.15 §7.9–7.10, administration
  guide 1.18 §9.5, Product Overview Draft1g.
- Not run here: the ClickHouse half of the conformance cases, and re-screening and the AML templates
  against ArcadeDB and Valkey (no stack was started).

## Built by ADR-133 stage (b) (build-order step 5, 1 November 2026)

- **The sentence** (`packages/schemas/sentences.py`, `services/api/rule_sentences.py`): closed
  choices from the ontology, refused by blank when undeclared; compiled to a drawn pattern saved as the
  author's plus `SentenceRuleParams` (typology `sentence`); a drawn pattern reads back as the sentence.
- **On the load path** (`services/api/sentence_rules.py`, on `RuleGate`): severity and team on the
  alert; *just me* alerts its author alone with no `Alert` node; *hold* holds a hit's rows; a
  deployment-wide sentence watches every case, judged in the loading case's datasets.
- **Frequency and amount** (`AnalyticsPort.event_frequency`, DuckDB and ClickHouse, conformance first).
- **Preview** (`POST …/rules/preview`): as the caller, `limit_exceeded` past the working-set limit,
  writes nothing.
- **The Glass** (`src/alerts/SentenceBuilder.tsx`), user guide 1.14 §7.6–7.8, Product Overview Draft1f.
- Not run here: the ClickHouse half of the conformance cases, and the load path against ArcadeDB and
  Valkey (no stack was started); see the step's report for its interpretations.

## The decisions (accepted 1 November 2026)

- **ADR-133 (monitoring rules):** sentences built from POLE, templates, preview, managed lists with
  re-screening, one Monitoring place in the Glass, the Studio's "Checks on load" step, and
  maker–checker. Accepted as written, in four stages, with these rulings:
  - each stage is done only when the user guide and the Product Overview deck show it working;
  - the hotlist audience is a deployment setting;
  - stage (a) is built first.
- **ADR-134 (alerts in reporting):** the `alert` pack item, the monitoring dashboard, and alert
  trends. Accepted as written; built after ADR-133 stage (a).
- **Build order:**
  1. ADR-133 (a);
  2. ADR-134;
  3. ADR-133 (b), (c) and (d).
  The demo use cases P1–P4 and A1–A4 land with the stage that makes each one possible.

## Stage 1 — map what is built

For each candidate use case, mark it as one of: **built today**, **needs the reporting ADR**, or **a
product gap**. The demo claims only what the product does. The facts on alerts, packs, trends and
dashboards are being gathered now.

## Stage 2 — choose the use cases (owner approval 1)

Candidates (the owner chooses):

| | Use case | Depends on |
| --- | --- | --- |
| P1 | A new PIN-phone call log arrives, and a typology rule flags a prisoner calling a number already seized from a handset | rules on load (check) |
| P2 | A hotlisted associate books a visit: the visits batch raises the alert before the visit | hotlists (built) |
| P3 | A weekly alerts trend for Wing F, and the chapter 9 alert as a pack item, in chapter 11's pack | reporting ADR |
| P4 | The monitoring dashboard: alerts raised and closed per week, and the open queue | reporting ADR |
| A1 | Next week's transactions file: rapid-movement and circular-flow rules fire | rules on load (built) |
| A2 | A new cash deposit into a hotlisted mule account raises an alert | hotlists (built) |
| A3 | A sanctions or PEP list update makes an existing customer match on re-screening | **unknown: re-screening on a list change may be a product gap** |
| A4 | An alert is closed with a reason, then appears in the case's pack and on the dashboard | reporting ADR |

## Stage 3 — decisions (owner approval 2)

1. **A proposed ADR for alerts in reporting:** a fifth pack item kind, `alert`; a monitoring dashboard
   fed through the reporting mart; and alerts as a trend series. Every count is over what the reader
   may see (rules 3, 4 and 7), and an alert's inferred match stays inferred (rule 5).
2. **ADR-127 (Prison Intelligence) and ADR-108 (Operation Ledger) amendments.** For each chosen use
   case: the data it needs, the exact alert it raises, the test that fails if it stops firing, and the
   test that fails if it fires when it should not (a hotlist added after the load, a reader without
   the dataset).

## Stage 4 — build (one worker against the tree at a time; rule 14)

1. **The reporting features**, tests written first, each with its access-control test.
2. **The demo data:**
   - new synthetic batch files generated from the existing plans (`pid_plan`, `ledger`), placed in
     `incoming/` as the demo loads them;
   - golden tests: "this batch raises exactly these alerts, in this order".
   - Rule 9 holds: synthetic and in the repository only.

## Stage 5 — make it a core feature everywhere

**Product and guides:**
- **README:** the feature list leads with monitoring and alerting beside mapping.
- **User guide:** a full chapter on monitoring and alerting:
  - hotlists and watches, with review dates;
  - typology alerts and the queue;
  - each alert's explanation;
  - closing with a reason;
  - alerts in packs, trends and the dashboard.
- **Developer guide:** writing and testing a typology rule in the Ingest Studio, and how a load
  raises alerts before commit.
- **Administration guide:** who sees alerts, the monitoring dashboard's feed, and retention.
- Each guide gets a new version and its PDF; the documentation site follows.
- `DEMO_GUIDE.md` and the Prison Intelligence setup guide get the new chapters.

**Demos:**
- the prison demo script: new or extended chapters, and the 20-minute version's run of show;
- the Operation Ledger walkthrough;
- capture steps for each new screen, captured in both brands.

**Decks** (new revisions saved beside the originals; originals kept):
- **Prison Intelligence (v1, v2, v3):** built by `build_decks.py`; new monitoring slides and the
  captured screens.
- **Pitch** (latest: Draft2), **Product Overview** (latest: Draft1c), **AML Opportunity** (Draft1)
  and **Administration Architecture** (Draft2): hand-made files, edited directly. Each gets:
  - monitoring and alerting as a core capability, with a slide of its own;
  - the one-line description from ADR-115 Amendment 4.

The marketing site's copy is the owner's call: it already names the theme but not monitoring.

## Stage 6 — rehearse (owner approval 3)

Run every demo on a freshly reset deployment, in both brands, from start to finish, before it is
presented. Check that the guides' steps match what is on screen.

## Order and size

The reporting features are a build phase of their own; stage 4 is most of the work. Without the
reporting ADR, only P1, P2, A1 and A2 can be shown. Recommended order:

1. Finish the current deck work.
2. The reporting ADR (stage 3.1).
3. The use-case choice and the demo amendments.
4. The build.
5. Guides, decks and rehearsal.
