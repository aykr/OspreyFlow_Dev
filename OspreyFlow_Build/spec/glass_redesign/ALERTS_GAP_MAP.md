# The alerts gap map

Written 6 November 2026 for ADR-145 N5: "map what exists against ADR-109, ADR-130 and ADR-134 before
designing anything". The map changes nothing that runs. Its findings become their own ADR once the
owner has answered the questions at the end (ADR-145 open question 1). That ADR's number is to be
reserved first, and it is not written here.

**How to read it.**
- **The code is the evidence.** Where an ADR and the code disagree, the cell follows the code and
  says so.
- **Paths are logical names**, as the repository's gates read them:
  - `services/…`, `packages/…` and `apps/…` are in `OspreyFlow_Core`;
  - `tests/…` is in `OspreyFlow_Build`.
  - A number after a path is a line in that file at `83ff99e`.
- **Each cell is marked with one status:**
  - **Built**: in the code, and a named test holds it.
  - **Partly**: in the code, but short of what the ADR says, or with no test.
  - **Recorded**: in an ADR, not in the code.
  - **Contradicted**: the code does something other than what an ADR or its own docstring says.
  - **Not built**: a new kind that no code serves yet.

## 1. What an alert is today

One Postgres table, `alerts` (`services/api/alerts.py` 76–108), holds every alert. Each row is
`Alert` (`packages/schemas/domain.py` 683).

**Kinds.** There are three queue kinds: `AlertKind = typology | hotlist | monitor`
(`packages/schemas/domain.py` 881).
- **The kind is never stored.** It is worked out in SQL (`_KIND_SQL`, `services/api/alerts.py`
  196–200):
  - a row with a `typology` is the `typology` kind;
  - otherwise the `rule_id` prefix decides (`hotlist:` or `monitor:`);
  - anything else is no kind at all and never reaches the queue. The scheduled-run notice is the one
    such row.
- **Typologies.** Inside the `typology` kind are twelve typologies (`TypologyName`,
  `packages/schemas/domain.py` 835–848).

**Statuses and closing.**
- **Statuses:** `open | claimed | closing | closed` (`packages/schemas/domain.py` 861).
- **Closing reasons:** true match, false positive, duplicate, no further action, referred (866–876).
  Only "true match" confirms anything (rule 5).
- **Severity:** `low | medium | high`.
- **Audience:** `case | team | owner`.

**There is no registry of kinds.** What a new kind touches by hand depends on which sort of kind it
is. (Earlier counts said twelve, then fifteen, from one mixed list that held places reading severity
or audience rather than kind, and missed the Glass's queue.)

*A new queue kind* (beside `typology`, `hotlist` and `monitor`) touches fifteen places:
1. `AlertKind` (`packages/schemas/domain.py` 881);
2. `AlertFactKind` (`packages/schemas/analytics.py` 556);
3. `DEFAULT_SEVERITY` (`services/api/alerts.py` 171–175);
4. `_KIND_SQL` (`services/api/alerts.py` 196–200);
5. `_SEVERITY_SQL` (`services/api/alerts.py` 201–210);
6. `_SHARED_SQL` and `_AUDIENCE_SQL` (`services/api/alerts.py` 217–224);
7. `queue_scope` (`services/api/alerts.py` 227–245);
8. `_row_to_fact` (`services/api/alerts.py` 293);
9. `summary_of` (`services/api/alert_queue.py` 68);
10. `_RULE_GROUP` (`services/api/reports.py` 134);
11. `GROUP_NAMES` (`services/api/trends.py` 110);
12. the Glass's `type Kind` (`apps/workspace/src/alerts/AlertQueue.tsx` 49);
13. its kind label (`apps/workspace/src/alerts/AlertQueue.tsx` 65);
14. its kind filter's options (`apps/workspace/src/alerts/AlertQueue.tsx` 140–142);
15. `KindFilter` (`apps/workspace/src/alerts/api.ts` 32).

*A new typology* inside the `typology` kind touches three:
1. `TypologyName` (`packages/schemas/domain.py` 835–848);
2. `TYPOLOGY_SEVERITY` (`services/api/alerts.py` 176–179), only for a default other than medium;
3. `TYPOLOGY_LABELS` (`apps/workspace/src/alerts/names.ts` 30–44).

Not counted: `needs_second_person` (`services/api/alert_queue.py` 314–319) reads severity and
audience, not kind; `ALERT_TREND_COLUMNS` (`packages/adapters/analytics_duckdb/alert_facts.py` 30–35)
is the trend's columns, not a kind map.

**Two lists, not one.**
- **The queue.** The Monitoring place's *Queue* tab reads `GET …/alert-queue`
  (`services/api/app.py` 9279), which serves all three kinds.
- **The inbox.** The *Watches* tab's alert inbox (`apps/workspace/src/watches/AlertInbox.tsx`)
  reads `GET …/alerts` (`services/api/app.py` 6271). That route returns every alert the reader
  *owns*, with no case filter. The dataset reach does apply: `list_authorized` adds
  `reach_clause(principal, 2)` (`services/api/alerts.py` 439–448), which keeps alerts whose
  `dataset_id` is one of the open case's datasets or is null, and applies no filter at all when
  `principal.datasets` is `None` (`services/api/dataset_scope.py` 73–83). So the inbox shows the reader's alerts from *every case
  whose datasets the open case reaches*, not only the open case's alerts.
- **Where ADR-130's explanation is.** ADR-130's "what fired it" (`fired_on`, the hotlist's identifier
  and review date) is only in the inbox's view (`services/api/watch_routes.py` 161–204). It is not in
  the queue's `AlertExplanation` (`packages/schemas/domain.py` 1339–1361).

## 2. The table: every kind that exists today

The *Tests* column names the test that would fail if the cell were violated (rule 12).

| # | Kind (where it lives) | Generated | Triaged | Routed | Case scope | Tests |
| --- | --- | --- | --- | --- | --- | --- |
| K1 | **Flow typologies**: `structuring`, `rapid_movement`, `circular_flow` (`typology`) | **Built.** When a load runs, before or after commit, as the rule declares. `RuleGate.pre_commit` / `post_commit` (`services/api/rule_evaluation.py` 811–999). The row is built by `alert_row` (551–569). Each finding alerts once (Valkey signature, 715–723). A failing pre-commit rule holds the rows (fail closed). | **Built.** Case queue. Medium by default, no severity written (`services/api/alerts.py` 172). Claim and release. *Give to* a case Editor or Author. Closed with the closed list plus words. Never needs a second person (not high). | **Partly.** The case's members. People only (ADR-133 Amendment 7) holds only where a directory answers: a deployment with no directory keeps every Editor and Author grant, a seed's or service account's included, in the *Give to* list (`services/api/app.py` 9349–9363). Nothing is sent outside the Glass. | **Built.** `investigation_id` is the loading case. Evaluated as the deployer within the rule's dataset (`services/api/rule_evaluation.py` 678–688). Events are read through `AnalyticsPort.list_events` with the access step in the WHERE. **Contradicted** for the queue list: see G2. | `tests/ingest/test_typology_rules.py` 329, 491, 531, 550 |
| K2 | **AML templates**: `high_risk_jurisdiction`, `large_cash`, `dormant_reactivated`, `velocity_rise` (`typology`) | **Built.** As K1, through `judge_aml` (`services/api/aml_rules.py` 163). The last two run after commit only (`packages/schemas/domain.py` 1059–1067). | **Built**, as K1. Medium (`services/api/alerts.py` 172). | **Partly**, as K1 (`services/api/app.py` 9349–9363) | **Built**, as K1. An account's history is read through `AnalyticsPort.account_activity` as the deployer (`services/api/aml_rules.py` 163). | `tests/services/api/test_aml_rules.py` 197, 269 |
| K3 | **KYC screening**: `kyc_screening`, with beneficial owners (`typology`) | **Built**, with three triggers. (1) When a load runs, before or after commit (`services/api/kyc_rules.py` 223–273), writing the listed party and an `inferred` `SAME_AS`. (2) When a list is refreshed: by hand, on the list's schedule, or by command. This re-screens every customer of every active screening rule, as each rule's deployer (`services/api/screening_refresh.py` 280–397). (3) Never manually per alert. | **Built.** High (`services/api/alerts.py` 177), so closing a case alert needs a second person (`services/api/alert_queue.py` 314–319): proposed, then approved by another member, never the proposer. A true match also confirms the `SAME_AS` (ADR-109 Amendment 7). | **Partly**, as K1 (`services/api/app.py` 9349–9363) | **Built.** On re-screening, the deployer is cut to the rule's dataset, else to the case's (`services/api/screening_refresh.py` 322–328). Its words name the customer, the listed party, the list and the score (`services/api/kyc_rules.py` 257–261). | `tests/ingest/test_kyc_rules.py` 235, 405; `tests/services/api/test_screening_refresh.py` 290; `tests/scenarios/test_ledger_monitoring_storyline.py` 514 |
| K4 | **Shared contact details**: `shared_attributes` (`typology`) | **Built.** When a load runs (`services/api/kyc_rules.py` 391–449) | **Built.** Low (`services/api/alerts.py` 178) | **Partly**, as K1 (`services/api/app.py` 9349–9363) | **Built.** Its words name the endpoint's value and the other customers (`services/api/kyc_rules.py` 428–442). | `tests/ingest/test_kyc_rules.py` 192 |
| K5 | **Unverified customer**: `document_verification` (`typology`) | **Built.** When a load runs (`services/api/kyc_rules.py` 452–482). Also **on a schedule**: the daily sweep of lapsed documents (`services/api/kyc_sweep.py` 50–132), with one replica claiming each day. | **Built.** Medium (`services/api/alerts.py` 172) | **Partly**, as K1 (`services/api/app.py` 9349–9363) | **Built.** Read as each rule's deployer (`services/api/kyc_sweep.py` 50–132). Documents loaded before a case had a rule are not swept (ADR-109 Amendment 4, disclosed). | `tests/ingest/test_kyc_rules.py` 338 |
| K6 | **Drawn pattern**: `pattern` (`typology`) | **Built.** After a load commits only. The saved pattern is matched as the deployer (`services/api/pattern_rules.py` 30–72). One alert per distinct match. Past `max_matches` it is refused in words. | **Built.** Medium (`services/api/alerts.py` 172) | **Partly**, as K1 (`services/api/app.py` 9349–9363) | **Built.** Its words name up to five matched nodes (`services/api/pattern_rules.py` 30–72). | `tests/ingest/test_pattern_rules.py` 94, 110 |
| K7 | **Sentence rule**, "this case" or "whole deployment": `sentence` (`typology`) | **Built.** Before commit, after commit, or **on a schedule** (`services/api/rule_schedule.py` 140–238, run as the author resolved afresh). A hit set to "hold" holds rows and raises **no** alert (`services/api/rule_evaluation.py` 867–877). | **Built.** The severity is the sentence's own. A whole-deployment rule is `pending` until a second person approves (`services/api/typology_rules.py` 239–248, 430–473). | **Contradicted.** The builder's *Alert goes to: my team* (`apps/workspace/src/alerts/SentenceBuilder.tsx` 586–593) writes `alerts.team`. (`services/api/sentence_rules.py` 84). But a typology row's audience is always `case` (`services/api/alerts.py` 223), and `_queued` drops the team (`services/api/alert_queue.py` 96). The alert goes to the whole case either way (G6). | **Built.** A deployment-wide rule is judged within the loading case's datasets (`services/api/rule_evaluation.py` 684–687). | `tests/services/api/test_sentence_rules.py` 145, 197; `tests/services/api/test_rule_schedule.py` 194; `tests/services/api/test_rule_maker_checker_routes.py` 139, 204 |
| K8 | **Sentence rule, "just me"** (`monitor` kind, `rule_id` `monitor:sentence:<id>`) | **Built.** As K7, but after commit only. No `Alert` node is written (`services/api/rule_evaluation.py` 493–494). | **Built.** No team is written (`services/api/sentence_rules.py` 85–87), so the audience is `owner` (`services/api/alerts.py` 217–224) and the owner closes it alone (`services/api/alert_queue.py` 314–319). Claimed, never given (`services/api/alert_queue.py` 466–470). | **Built.** Its author alone (`services/api/sentence_rules.py` 85–87) | **Built**, within its case's datasets (`services/api/sentence_rules.py` 83) | `tests/services/api/test_sentence_rules.py` 162 |
| K9 | **Hotlist** (`hotlist`) | **Built.** When a load reaches the change stream, and after a manual resolution link (`services/api/evaluation.py` 144–236; `services/api/recipe_run.py` 400–470). Matched as the unscoped service principal (the exemption ADR-038 records). A `notify` policy writes a stub with no evidence. | **Built.** High by default (`services/api/alerts.py` 173), so a hotlist shared with a team needs a second person to close. It is claimed, never given (`services/api/alert_queue.py` 466–470). Its review date passing raises nothing (not asked for). | **Built.** The owner, plus the owner's organisational unit while its audience is `team` *now* (`services/api/alerts.py` 217–221; ADR-133 ruling 3). | **Partly.** It is not tied to a case: it shows in every case whose datasets reach it (`queue_scope`, `services/api/alerts.py` 242–243). `investigation_id` is only a hint. ADR-130's file and row explanation is in the inbox only (G1). | `tests/services/api/test_monitoring_queue.py` 201–280; `tests/services/api/test_alert_view_explains.py` 153, 259; `tests/services/api/test_evaluation.py` 217, 320 |
| K10 | **Monitor**, a saved-pattern watch (`monitor`) | **Contradicted.** It runs on the change stream only, as K9, matched as the owner within the monitor's dataset (`services/api/evaluation.py` 239–315). It is never pre-commit and never scheduled. Spec 02 says a saved-pattern monitor is "run on a schedule against new data", and that this is the CoLP deck's "automatic daily searches" requirement (`spec/02_GLASS_FRONTEND.md` 918–920). No schedule runs one: `services/api/rule_schedule.py` schedules sentence rules only (140–238). See G16 and Q3. | **Built.** Medium (`services/api/alerts.py` 174). Claimed, never given (`services/api/alert_queue.py` 466–470). | **Contradicted** against its own docstring. The team is always written (`services/api/evaluation.py` 308) and every monitor row with a team is shared (`services/api/alerts.py` 218), which matches ADR-133 Amendment 1 item 2. But `needs_second_person`'s docstring calls them owner-only (`services/api/alert_queue.py` 316–318), and there is no "only me" setting for a monitor. | **Partly**, as K9 | `tests/services/api/test_evaluation.py` 631, 703; `tests/services/api/test_monitors.py` 61 |
| K11 | **Scheduled-run notice** (no kind, `rule_id` `schedule:<recipe>`) | **Built.** When a scheduled or watched pipeline run is refused or fails (`services/api/scheduler.py` 142–159, 496–502). | **None.** It has no typology and no `hotlist:` or `monitor:` prefix, so `_KIND_SQL` gives it no kind (`services/api/alerts.py` 196–200), and it is never queued, triaged, trended or counted. | **Built.** The schedule's owner's inbox only (`services/api/scheduler.py` 142–159; `services/api/alerts.py` 439–448) | **Partly.** No `dataset_id` (`services/api/scheduler.py` 142–159), so `reach_clause` keeps it in reach of every case its owner opens (`services/api/dataset_scope.py` 81). | `tests/services/api/test_schedule_notice.py` 30 |

**Next to the alerts, but not alerts.**
- **Held rows** (`services/api/held_rows.py`) are a quarantine with no alert row, read by marking in
  SQL. A sentence hit set to "hold" is seen only as held rows (`tests/ingest/test_typology_rules.py`
  405, 429).
- **Neighbourhood risk** (`services/api/risk.py` 43–112) reads only the typology alerts the reader
  may see whole (`tests/ingest/test_risk.py` 94, 117).
- **Beneficial ownership** (`services/api/ownership.py`) is a view that raises nothing. Its alerts
  come from K3 with *screen owners*.

## 3. The two new kinds (not built)

| # | Kind (ADR) | Generated | Triaged | Routed | Case scope | Test to write first |
| --- | --- | --- | --- | --- | --- | --- |
| N1 | **A load meets a drawn item** (ADR-143 decision 12, C16; Lane 3, L3.6) | **Not built.** After any load into a source dataset, items it loaded that resemble a drawn item, in a case reading that dataset, raise one alert in that case. The nearest code is K6 (`pattern`), which matches a saved pattern, not a board item, and points at no board. | **Not built.** The ADR names no severity, assignment or close rule. Open question Q2. | **Not built.** To "the case". With no team, today's code would make it the case's members (as K1). | **Not built.** A board is in the case's analyst layer, read by `Principal.datasets` like any dataset (ADR-143 decision 3). The match must be judged as someone. Today's rules run as a named deployer, and a board has no deployer. Its words may name the loaded item only as the reader sees it (rule 7). | One alert per match per case; none in a case not reading the dataset; none for a reader who cannot see the drawn item; *Open the board* reaches the board. |
| N2 | **Promotions overdue** (ADR-145 decision 9, O3; Lane 2, L2.6) | **Not built.** A promotion waiting for review past *N days* (default 3) raises one alert. Nothing schedules it: the KYC sweep (`services/api/kyc_sweep.py`) is the only daily pass, and it would be the model. | **Not built.** It is not a case alert: no case queue is its home. | **Not built.** "The reviewers and administrators" (ADR-145 decision 9), which is a set of people with a right, not a case or a unit. No code routes an alert by right today. | **Not built.** It must name the load, not its contents (ADR-145's named test; rule 7). It is read under the reader's own principal. | It fires once at N days and not again; it names the load, not the items; a reviewer of another dataset is not told. |

**The ADR-133 Amendment 8 maker–checker row.** Promoting into a review-policy dataset is the fourth
decision that needs a second person. It is **recorded** and not built: the code has three rule
decisions plus the high-severity close.

## 4. The journeys

### An analyst, from an alert to its case and back

1. **Where they start.** They sign in and land on Home.
   - *Needs your attention* lists open and own-claimed queue alerts, titled "<typology> alert in
     <case>" (`apps/workspace/src/home/homeData.ts` 101–127).
   - A hotlist or monitor alert has no typology, so it reads **"Alert alert in Kestrel"**
     (`apps/workspace/src/alerts/names.ts` 46–48).
   - Choosing a row **opens the case, not the alert** (`apps/workspace/src/home/HomePage.tsx`
     214–235).
2. **Finding the alert.** The rail's *Monitoring* entry (`apps/workspace/src/App.tsx` 1410) carries
   a count of open and claimed alerts. Alerts proposed for closing are not counted
   (`apps/workspace/src/home/homeData.ts` 90–91).
   - It opens on *Queue*.
   - Filters: status, kind and severity. There is no filter for mine, team, age or sort.
3. **Opening it.** It shows "What fired this alert": the summary in words, and the transactions
   table or the parties it concerns.
   - For a hotlist alert, the identifier, the file and the row are **not shown here**. They are in
     the *Watches* tab's inbox, a second list of the same alerts (G1).
4. **To the case.**
   - **Show on the canvas** puts the alert's node, entities and links into the open case's working
     set and switches to the graph (`apps/workspace/src/App.tsx` 1519–1523). This is the same case,
     not another.
   - **The inbox's other route.** Its *Jump into investigation* makes a **new branched case**
     instead (`services/api/app.py` 6309). ADR-144 decision 4 turns that into a private view; this
     is Lane 3's work.
5. **Back.** There is **no way back**.
   - No deep link exists: there is no router, and the view is local state.
   - The opened alert is lost when the place unmounts (`apps/workspace/src/alerts/AlertQueue.tsx`
     112).
   - The analyst presses *Monitoring* again and finds the alert again by hand (G7).
6. **Closing it.** They choose a reason, write words, then *Close the alert*.
   - For high severity it is *Propose the close*, and a second member decides.

### A team lead triaging

1. **One case at a time.** The queue is per case. There is no cross-case or team queue.
   - Hotlist and monitor alerts of the team appear in every case reaching their dataset, so a lead
     moving between cases sees them repeatedly (`services/api/alerts.py` 242–243).
2. **Reading the workload.** No filter or column shows the workload by assignee, by team or by
   age. The age is printed on each row only.
   - The age figures are in Reports > Figures ("open by age").
   - ADR-134's monitoring dashboard is served by the Conduit
     (`tests/services/api/test_monitoring_dashboard.py`), but **no Glass screen reads it**. Its
     generated `MonitoringFigures` type is unused.
3. **Assigning.** *Give to* lists the case's Editors and Authors who are people.
   - It is offered only for case alerts. Team and owner alerts are "claimed by someone who can see
     it" (`apps/workspace/src/alerts/AlertQueue.tsx` 355–362).
   - A lead cannot hand a team hotlist alert to a colleague.
4. **Approving.** High-severity closes wait as `closing`.
   - The queue's *Show: active* includes them.
   - The rail badge and Home do not.
5. **Tuning.** Rules, held rows and audit sit in the same place: the people who triage tune
   (ADR-109 Amendment 2 (d)).
   - Rule changes of whole-deployment rules wait for an administrator who is an Author.
   - Suppressing a known entity for a rule, with an expiry (ADR-133 decision 7), is **recorded only**.

## 5. The gaps

The rule-3 gaps (G2 and G3) are defects, not design questions. They need their test written and seen
red by the lane that owns `services/api/alert_queue.py` and `services/api/watch_routes.py`. That is
not this lane (see the report).

| # | Gap | Status | Evidence |
| --- | --- | --- | --- |
| G1 | **Two lists of the same alerts.** The queue holds all three kinds. The Watches inbox holds the owner's alerts with no case filter, kept only to the open case's dataset reach, so it shows alerts from every case reaching the same datasets: typology alerts they deployed, plus schedule notices, which name no dataset and so are always in reach (`services/api/alerts.py` 439–448; `services/api/dataset_scope.py` 73–83). ADR-130's explanation lives only in the inbox. ADR-133 decision 5 ("one alert queue for every kind") and decision 7 ("ADR-130's shape, extended to every kind") are partly built. | Partly | `services/api/app.py` 6271, 9279; `services/api/watch_routes.py` 161–204; `packages/schemas/domain.py` 1339–1361 |
| G2 | **Rule 3: the queue list checks nodes only.** The list drops an alert whose *nodes* the reader cannot see, but not one whose cited *links or transactions* they cannot see, so the list can show an alert whose explanation answers 404. That says a hidden element exists. The module's own docstring and spec 03 §3.8a say links and transactions are checked. `close_for_elements` admits the gap. | Contradicted | `services/api/alert_queue.py` 116–127 (vs 11–15); `services/api/alerts.py` 628–630 |
| G3 | **Rule 3, untested: the inbox returns an alert's words whatever the evidence.** `alert_to_view` withholds the referents when the evidence is not available, but returns `words` as stored. A typology alert's words name customers, list entries and identifiers. It sits in its deployer's inbox, which has no case filter, only the dataset reach (`services/api/alerts.py` 439–448), so it is read from any case reaching its dataset, as a principal whose access may differ from the one the case it was raised in gave. No test covers a worded alert with hidden evidence: the redaction test uses a hotlist alert with no words. | Partly (untested) | `services/api/watch_routes.py` 205–232; `tests/scenarios/test_phase7_stage6c_watch_routes.py` |
| G4 | **No registry of kinds.** ADR-143 decision 12 asks for "its own rule kind". A new queue kind touches fifteen places, and a new typology three (§1), and a missed one goes silently uncounted, because `_KIND_SQL` gives NULL and the row is never queued. | Partly | `services/api/alerts.py` 196–224 |
| G5 | **Hotlist and monitor alerts have no case.** They follow the dataset reach, not the case, so the journey "from an alert to its case" has no case to go to for them. | Partly (as designed, ADR-099 Amendment 3) | `services/api/alerts.py` 242–243 |
| G6 | **"Alert goes to: my team" does nothing to who sees it.** A sentence rule's team is written but never read for a typology alert. | Contradicted (ADR-133 decision 1, "the team the alert goes to") | `services/api/alerts.py` 223; `services/api/alert_queue.py` 96 |
| G7 | **No way back** from the canvas or the case to the alert. Home opens the case, not the alert. There is no link to an alert. | Not built (no ADR asks) | `apps/workspace/src/alerts/AlertQueue.tsx` 112; `apps/workspace/src/home/HomePage.tsx` 214–235 |
| G8 | **A team lead has no team view**: no filters for assignee, team or age; no cross-case queue; team and owner alerts cannot be given; and the monitoring dashboard has no Glass screen. | Partly (ADR-134 decision 2: Conduit built, Glass not) | `apps/workspace/src/alerts/AlertQueue.tsx` 128–153; `tests/services/api/test_monitoring_dashboard.py` |
| G9 | **`closing` is said wrongly or left out.** A pack's status sentence has no `closing` branch ("Closed without an outcome"). Trends count it as open. The rail badge and Home leave it out. | Contradicted | `apps/workspace/src/reports/packText.ts` 120–130; `services/api/alerts.py` 287–290; `apps/workspace/src/home/homeData.ts` 90–91 |
| G10 | **Hotlist and monitor alerts are titled "Alert alert in …"** on Home. | Contradicted (rule 7's spirit: say what it is) | `apps/workspace/src/home/homeData.ts` 120; `apps/workspace/src/alerts/names.ts` 46–48 |
| G11 | **Suppression with an expiry** (ADR-133 decision 7) is not built. `services/api/suppression.py` is node suppression, unrelated. | Recorded | ADR-133 decision 7 |
| G12 | **Taken back by a revert**: closed with no outcome, said only in reports ("Closed, no outcome"). Nothing in the queue explains it. ADR-134 Amendment 2 leaves how to say it to the owner. | Partly | `services/api/alerts.py` 617–683; `apps/workspace/src/reports/ReportsView.tsx` 16–23 |
| G13 | **Coverage gaps (rules 13 and 15).** Held rows and Audit are not axe-scanned in any theme: the harness switches only rules, watches and lists. The alerts and watch-panel harnesses have no GOV.UK scan. These actions have no keyboard case: *Withdraw the close*, *Read a saved pattern as a sentence*, Home's attention rows. | Partly | `apps/workspace/keyboard/monitoring-harness.tsx` 281; `apps/workspace/a11y/every-harness.spec.ts` |
| G14 | **Stale docstrings.** These say what was true before ADR-133 or ADR-134: monitors are owner-only; `record_match` is the only constructor; `investigation_id` is "not an access-control scope" (it scopes typology alerts in `queue_scope`); Reports count typology only; no hotlist store exists. | Contradicted (comments only) | `services/api/alert_queue.py` 7–8, 316–318; `packages/schemas/domain.py` 687–691; `services/api/alerts.py` 23–30 |
| G15 | **N1 and N2 are not built** (§3). N2 needs routing by *right* (reviewers and administrators), which no alert has. N1 needs a judge with no deployer. | Not built | ADR-143 decision 12; ADR-145 decision 9 |
| G16 | **A saved-pattern monitor never runs on a schedule.** Spec 02 makes the schedule the CoLP deck's "automatic daily searches" requirement. A monitor is judged only when a load reaches the change stream; nothing runs it daily. The only scheduled rules are sentence rules (K7). Spec 02 is not rewritten here: whether the code or the requirement moves is the owner's choice (Q3). | Contradicted | `spec/02_GLASS_FRONTEND.md` 918–920; `services/api/evaluation.py` 239–315; `services/api/rule_schedule.py` 1–18 |

## 6. Questions for the owner (round 1, multiple choice)

The recommendation is first in each question.

**Q1. One list or two?** Today the Watches inbox and the Monitoring queue both show alerts (G1).
- **A (recommended).** One queue. The inbox's alerts move into it, and ADR-130's "what fired it" is
  shown there for every kind. The schedule notices move to Home's *Needs your attention*. *Jump into
  investigation* becomes *Open as a view* (ADR-144 decision 4).
- **B.** Keep both, and rename the inbox *My watches' matches*.
- **C.** Keep both as they are.

**Q2. Where do the two new kinds live?**
- **A (recommended).**
  - *A load meets a drawn item* is a typology alert in the case's queue: medium severity, its action
    *Open the board*, judged as the board's creator. It is withheld whole from a reader who cannot
    see the drawn item.
  - *Promotions overdue* is not a case alert. It shows in the top bar's *Needs you* (ADR-145
    decision 11) and on Admin › Operations, to each person holding `review_promotions` for the
    dataset and to administrators.
- **B.** Both in the case's queue: the overdue alert in the case the promotion came from. This
  **amends ADR-145 decision 9**, which raises the overdue alert "to the reviewers and
  administrators", not to a case's members.
- **C.** A fourth queue kind, *board*, for the drawn-item alert. The overdue alert as in A.

*ADR-143 decision 12 asks for "its own rule kind".* A and B meet it at the rule level: the drawn-item
alert gets its own typology and rule kind (beside `pattern` and `sentence`), inside the existing
`typology` queue kind, so it touches §1's three typology places and none of the fifteen queue-kind
ones. C meets it at the queue level too, and touches the fifteen as well (G4).

**Q3. A saved-pattern monitor and "automatic daily searches".** (G16) Spec 02 says a monitor runs on
a schedule and calls that the CoLP requirement; the code runs it only when a load arrives.
- **A (recommended).** Build the schedule: a monitor gains "on a schedule (daily or weekly)" beside
  "as data loads", run as its owner resolved afresh, one replica per slot, as `rule_schedule.py`
  already does for sentence rules. Spec 02 then stays as written.
- **B.** Amend the requirement by ADR: a monitor runs as data loads, and "automatic daily searches"
  is met by a sentence rule set to run daily (K7). Spec 02's sentence is corrected by that ADR.
- **C.** Both: the ADR records B now, and A is built later.

**Q4. From an alert to the case and back.** (G7)
- **A (recommended).** Opening an alert's evidence opens it as a private view of its case (ADR-144
  decision 4). The context banner (ADR-145 decision 2) then reads "From alert: Structuring ·
  ← Back to the alert", which returns to the alert, still open, in Monitoring. Home's rows open the
  alert itself.
- **B.** Only Home's rows open the alert. *Show on the canvas* stays as it is, with no way back.
- **C.** As today.

## 7. Questions for the owner (round 2, once round 1 is answered)

**Q5. What should "Alert goes to: my team" mean on a case rule?** (G6)
- **A (recommended).** The case's members still all see it. The team becomes a label and a queue
  filter, and the queue gains filters for *mine*, *team*, *unassigned* and *older than N days* for a
  team lead (G8).
- **B.** Only members of the author's unit see it. That is a new rule-3 read, with its tests first.
- **C.** Remove the choice from the builder. The case's members see it, as today.

The rest of round 2 is still to be written as multiple choice: whether a lead may give a team hotlist
alert to a named person; whether a taken-back alert is said apart in the queue (G12); and suppression
with an expiry (G11).
