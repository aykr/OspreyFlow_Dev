# 08 — Acceptance Scenarios

Two analyst journeys, taken from the supplied documents, that between them exercise every
capability in the pack. They are the functional definition of done: if a scenario needs
scenario-specific code to pass, the platform has failed the test rather than passed it.

Both run on synthetic fixtures generated from a seeded generator in `tests/scenarios/fixtures/`.
No real data enters the repository.

## Which test proves these, and at which tier — DECIDED by owner ruling R5, 27 September 2026

There are two, and they are not interchangeable.

| Tier | Test | What it is |
| --- | --- | --- |
| **The closing-pass proof** | `tests/scenarios/test_phase8_exit_over_the_wire.py` | The rendered `local-lite` deployment, **through the analyst's own door**: OIDC authorization code with PKCE against the deployment's real Keycloak as the `--demo-analyst` subject, every call through the workspace's nginx proxy, the delta stream through the ticket exchange. No store port, no in-process app. Opt-in (`OSPREY_TEST_OVER_THE_WIRE=1`), its own CI job (`over-the-wire-exit-test`), `make exit-over-the-wire`. **This is the test `07_BUILD_PLAN.md`'s milestone line cites.** |
| **The fast developer tier** | `tests/scenarios/test_phase8_exit_criterion_end_to_end.py` | The more complete walkthrough — every row below, including the ingest-dependent ones — driven in process (`TestClient`) against `make dev-up`'s published stores. Fast, and what a developer runs while changing a route. |

**Why R5 was needed.** The in-process test reaches ArcadeDB, Postgres and Valkey directly on
published ports. A rendered deployment publishes only the workspace and Keycloak — correct for a
deployment (`05_DEPLOYMENT.md` §7), and fatal for that test. Until R5 it was therefore the case
that the single test the milestone rested on **had never been run against the thing the milestone
is about**, which `07_BUILD_PLAN.md` records as round 13's finding.

**The over-the-wire test does not cover every row, and its own module docstring has the row-by-row
table.** The reason is one fact: a rendered deployment gives an analyst **no route by which to
supply a source file** — `POST /v1/ingest/recipes` takes a `source_location` the Conduit's own
container must be able to read, nothing is mounted there, and the only upload route in the Conduit
is the site image. So B1–B3 and every row that depends on data arriving that way (B6, B7, B8, B13,
B14, B15–B18) cannot be performed by an analyst against a rendered deployment at all. That is a
product gap, not a shortfall of the test. **B1–B3 were closed on 27 September 2026 — see below;
the remaining rows in that list are not.**

**Owner ruling R8, 27 September 2026 — those remaining rows are milestone-blocking, and this
section used to leave their weight unstated.** Round 13c put the question to the owner because
this section could be read two ways: it nominates the over-the-wire test as the one
`07_BUILD_PLAN.md`'s milestone line cites (and it is green), while also saying that test does not
cover every row. R8 settles it:

> Clause 3 of V1 END TO END is **NOT REACHED — Reading B**. The milestone requires **every row of
> both acceptance scenarios to be performable through the analyst's own door on a rendered
> `local-lite` deployment.** Seeding the deployment with the remaining Scenario A and B fixture
> data is **milestone-blocking** work.

**So "which test proves these" has a bar, not just a tier.** A row proven only at the developer
tier (`test_phase8_exit_criterion_end_to_end.py`, in process against published stores) does **not**
count towards clause 3, however green it is.

**Built, 27 September 2026 (round 13cb) — six rows now clear that bar.** A third seed dataset,
`scenarios` (`scripts/seed_scenarios.py`, `--seed hmp,fixture-corp,scenarios`), puts Scenario B's
person layer, the shared messaging handle, the seized handset with its two SIMs and the device's
sightings into a rendered deployment.

| Row | Status after 13cb | Proven by |
| --- | --- | --- |
| B7 | **over the wire** | `test_b7_a_shared_messaging_handle_is_common_to_the_second_cohort` |
| B8 | **over the wire** | `test_b8_the_handle_is_linked_to_the_shared_endpoint_asserted_at_one` |
| B15 | **over the wire** | `test_b15_both_sims_link_to_one_device_in_one_traversal` |
| B17 | **over the wire** | `test_b17_the_devices_location_events_are_reachable_and_windowed` |
| B16, B18 | **data half only** | `test_b16_…`, `test_b18_…`; rendering and playback stay the Glass tier |
| A1, A6, B6 | still not | Need content the graph does not hold — below |
| B13, B14 | still not | An alert needs an ingest to fire it |
| A7 (item-category), A15 (consult-originator block) | still not | Recorded gaps, not seeding |

Each of the six was **shown red first** against a deployment seeded `hmp,fixture-corp` only, then
green against **the same deployment** after seeding `scenarios` — one variable, not two
deployments.

**Why A6 and B6 did not move, precisely rather than "not seeded".** Both are document-view rows,
and a document's *spans* come from the extraction-candidates store — `GET /v1/investigations/{id}/
dossier/documents/{id}` reads `ExtractionCandidates`, not the graph. The `scenarios` seeder writes
to the graph. Those rows need a seeding path into that second store, which is different work and
is not pretended to be done here. A1 needs a placed site grid; B13/B14 need an ingest to fire an
alert, and `09_INGEST_STUDIO.md`'s own rule is that a row worded "ingest …" is performed through
the Studio rather than seeded around it.

**Built, 27 September 2026 (round 13bc) — the "no door" half is closed.** The ingest root is
rendered, mounted read-only, listed by Connect, and walked end to end over the wire by
`tests/scenarios/test_phase8_exit_over_the_wire.py`.

**Built, 27 September 2026 (round 13bf) — B1–B3 are now over the wire.** They are walked through
the analyst's own door, Connect → Profile → Map → Verify → Publish → Run, and asserted by test id
(`test_b1_…`, `test_b2_…`, `test_b3_…`). Four separate things had to be true and none of them was:

1. **Connector availability is derived from `connectors/*.yaml`, not declared.** It had been
   hard-coded in four unconnected places, so `cdr-generic-csv` was declared in the catalogue and
   refused by the Studio — the reason recorded here until now.
2. **A connector profile's own settings reach the published recipe.** `studio_publish` built its
   `RecipeConnector` from the profile's *id* alone, so `date_order: dmy` never arrived and B3's
   `12/01/2026` would have been read with no declared order. Every test passed throughout,
   because they asserted on a hand-built connector the Studio never produces.
3. **The Conduit's image carries `git`.** It never had, so Publish — "publishing writes the
   recipe to version control" (`09_INGEST_STUDIO.md` §6) — returned a bare 500 in every rendered
   deployment this project has built. The one test of publishing runs on the host and supplies
   its own initialised repository, so it agreed with the code while the deployed article could
   not publish at all.
4. **The recipe repository has a persistent root.** It defaulted to `/app` inside the container:
   the image's own code directory, rebuilt on every deploy.

**What B3 asserts, and why those values.** Row 9 of the fixture is `2026-03-30 11:00:00` with no
offset against a recipe declaring `tz=Europe/London`; 30 March 2026 is inside British Summer
Time, so the correct conversion is `10:00Z` — a normaliser that read naive local time as UTC
would record `11:00Z` and pass any fixture that avoided a DST boundary. Row 6 is `12/01/2026`,
which read as `mdy` would land in December and move the stored interval's upper bound. Row 10 is
unparseable and appears in the run report's rejections, named, rather than guessed at.

**Ruled 27 September 2026 — owner ruling R6, restated the same day in fuller terms.** Ingest for
a rendered deployment works **through the existing Ingest Studio**, not around it: the ingest
folder is a configurable storage root in `osprey.yaml` (`components.storage.ingest`) alongside
data, staging and backups, set on the Components screen and shown in the summary rail; the
renderer bind-mounts it read-only into the Conduit for every profile; and the Studio's Connect
stage lists that folder's files so an analyst picks one and maps it on the existing Map canvas to
the POLE model. A browser upload route is explicitly post-milestone, as are Map's two already
recorded gaps. `07_BUILD_PLAN.md` carries the ruling verbatim and the five pieces that have to
land together. Until they do, the rows above stay proven at the in-process tier only, and this
section's table stays as it reads.

---

## Scenario A — Fixed-site geospatial and temporal analysis

Derived from the HMP Hollywood intelligence development summary. Exercises site geospatial,
temporal, comparative case analysis, link analysis and assessment production.

**Fixture.** A synthetic secure site: 262 incident records over a two-month window, each with a
yard identifier, timestamp and item type; 229 associated reports of which 68 carry structured
detail; a population of ~400 person entities with wing and cell locations; a subset with
recorded group affiliations and family relationships; an aerial image of the site with control
points.

### The journey

| Step | Analyst action | Platform capability | Assertion |
| --- | --- | --- | --- |
| A1 | Upload the site image, place four control points, draw a 10×10 grid | Site geospatial | Grid cells become `Location` entities; incidents geocode into cells |
| A2 | View incident density across the grid | Geo-binning, heat layer | The four hotspot cells are the top four by count, and together account for ~52% of incidents |
| A3 | Select the hotspot cells | Cross-filter | Canvas, timeline and histograms all restrict to those cells; status bar shows the dimmed count |
| A4 | Switch the timeline to cyclical weekday × hour | Temporal, cyclical view | Two intra-day peaks are visible; Saturday and Sunday together are ~34% of the filtered total |
| A5 | Brush to the two intra-day peak windows | Temporal brush | The combined selection is ~66% of incidents in the hotspot cells |
| A6 | Open the reports for the filtered selection | Document view, provenance | 68 structured reports are returned; each links to its source with a locator |
| A7 | Filter reports to one residential sub-unit and one item category | Histogram cross-filter | The person entities named in the surviving reports are added to the working set as a named history step |
| A8 | Rank the resulting people by appearance count and group affiliation | Metrics panel | The principal subject ranks first; the affiliated subset is identifiable by an `Organisation` edge |
| A9 | Expand the principal subject's relationships | Radial menu, Search Around | Family, co-location, group and document-mention edges expand with a cardinality preview first |
| A10 | Notice the family link to a second subject on another wing | Link analysis | Both subjects share an `Organisation`; the second has prior events outside the current window |
| A11 | Drop the timeline filter to the full available history for these two | Temporal | Prior-period events appear; the pattern is visibly continuous rather than new |
| A12 | Run the Clique Metric on the working set | ComputePort | The relay group passing items between cells scores high on clique and low on degree centrality |
| A13 | Record four judgements against the yardstick, each with evidence | Assessment objects | A judgement cannot be saved without at least one supporting reference |
| A14 | Record seven intelligence gaps and three assumptions | Assessment objects | Gaps link to the entities they concern; assumptions link to the judgements they support |
| A15 | Export the chart and the assessment | Export, handling gate | Items marked consult-originator block the export by name; export proceeds only with a recorded justification and carries a withheld-item manifest; the export produces a real artefact of the requested shape (chart/subgraph/report), carrying the mark |

### What A13–A15 prove

Steps A1 to A12 are things a competent link analysis tool does. A13 to A15 are the reason this
platform exists: the analytical picture and the intelligence product are the same artefact, and
the product cannot be exported without the handling policy being applied to every element in it.
If a later change makes A15 pass without evaluating handling on each element, the platform has
regressed in the way that matters most.

**A15's own assertion was strengthened rather than left to read as proving more than it did.**
Before this addition, A15 tested the gate — blocks by name, requires justification, carries a
manifest — and stopped there, silent on whether anything a recipient could actually open ever
came out the other side. `07_BUILD_PLAN.md`'s own Phase 8 exit criterion, and through it the alpha
gate (`06_DECISIONS.md` ADR-042), were both satisfiable by an export feature that exported
nothing: the gate could pass every check and still hand nobody a file. **This is the second
instance of the same pattern this document's own standing rule 12 names — a gate proving less
than its name implies — found at the acceptance-scenario level, not only in a test file.** The
first was Scenario B's own "B12/B13/B14/B20 pass end to end," which `07_BUILD_PLAN.md`'s Phase 7
entry originally found true only of the single-session walkthrough as written, not a claim that
hotlists and monitors fire across different analysts — the operational case B13's own CoLP framing
is actually modelled on. **That finding no longer holds — superseded by Stage 1 (principal
resolution, `06_DECISIONS.md` ADR-043), proven by `test_a_hotlist_owned_by_one_analyst_fires_
from_a_different_analysts_own_ingest` (`07_BUILD_PLAN.md` has the full record) — cited here as the
historical example the pattern was first found from, not as a still-open gap.** Both instances
share the same shape: an acceptance row whose literal wording is
narrower than what a reader assumes it proves, discovered only by checking the row against the
system's real behaviour rather than against its own passing test. A15's own assertion now says
what it means: the artefact must exist, in the requested shape, carrying the mark — not only that
the gate around producing one behaved correctly.

### Implementation note — A2's mechanism (found during Phase 5 Checkpoint 2's live verification)

`AnalyticsPort.geo_bins`'s precision ceiling (12, enforced by `GeoBinRequest`'s own validator)
cannot resolve individual grid cells at this fixture's scale: ten yards a few dozen metres apart
on one fixed site collapsed into two bins even at maximum precision — nowhere near "four hotspot
cells". A2's literal figure is instead produced by a *categorical* `cross_filter` dimension on
`target_id` (the yard `Location` each incident is `PRESENT_AT`), which resolves per-cell exactly
and reproduced the figure against live seeded data (51.1% measured vs. ~52% here). The Glass's
Map view ships both: the `geo_bins` heat layer (`02_GLASS_FRONTEND.md` §3.5 names it directly,
and it stays correct at a coarser scale this fixture doesn't exercise) and a ranked "hotspot
cells" panel on `target_id` as the mechanism A2/A3 actually rely on at this fixture's scale.

### Known gap — A7's "item category" filter

A7 asks to filter reports "to one residential sub-unit and one item category". The sub-unit half
is a `node_ids` restriction (already supported — a sub-unit is a `Location`). The item-category
half is not: `EventFilter` (`packages/schemas/analytics.py`) carries `investigation_scope`,
`window`, `node_ids` and `edge_types` only — no generic field/value predicate an event property
such as `item_type` could be filtered on. `cross_filter`'s categorical dimensions *aggregate and
display* a field's distinct values; they do not let a caller *restrict by* one. Building that
(a `value_filters` field on `EventFilter`, or an equivalent) is real, unscoped work, not something
Checkpoint 2 quietly worked around.

### Additional assertion — retraction propagates

After A15, retract one node that supports a judgement. The judgement is flagged for review
within the same session, and the export produced in A15 is marked as resting on retracted
evidence. This closed loop is what makes the assessment objects worth storing rather than
writing in a word processor.

**This sentence is not what the analyst sees, and the discrepancy was found by running the
scenario over the wire on 27 September 2026 — recorded here, not fixed here.** The flag *is*
written (`flag_judgements_citing_superseded_node`, proven by `tests/services/api/
test_assessments.py`, which calls it directly and re-reads the store). But retraction supersedes
the node with a **new id**, the judgement's `supporting` still names the old one, and ADR-046's
hide-in-full rule (`judgement_visible_to`, composed into `list_visible_judgements`, the function
the Judgements tab's own route calls) removes every judgement with an unverifiable supporting
citation. Measured through the deployed Conduit: before the retraction the judgement lists with
`flagged_for_review: false`; after it, the list is empty. Two rules each correct alone compose
into a third behaviour this document does not describe, and no test could see it because the only
one that checked the flag bypassed the route.

**Ruled 27 September 2026 — owner ruling R7, and recorded as TENTATIVE at the owner's own
instruction, to be revisited after their usability walkthrough.** `06_DECISIONS.md` ADR-046's
addendum carries it in full. Two parts:

- **Retraction becomes two steps.** In the Glass an analyst *marks* a node for suppression —
  immediate, reversible, shown as a marker on the node and in the inspector. The suppression only
  *takes effect* when its evidence arrives through the Ingest Studio: a retraction record ingested
  and mapped to the node like any other source, so no suppression is ever an unevidenced click.
  This depends on ruling R6 (ingest for a rendered deployment works through the Studio) and cannot
  land before it.
- **A judgement citing a marked or suppressed node stays visible to its author, flagged for
  review, with the citation resolved to the successor for display.** ADR-046's hide-in-full rule
  applies to citations the principal is not *permitted* to verify, not to citations the system
  itself superseded.

**The visibility half is now built (round 13bd, 27 September 2026), so this document's own
sentence is true again**: a judgement whose supporting node is retracted stays visible to its
author, flagged for review, with the citation resolved to the successor for display — and the
citation itself is never rewritten, because the judgement asserted something about the evidence
as it stood. `tests/scenarios/test_phase8_exit_over_the_wire.py` asserts exactly that through a
real deployment, and `tests/services/api/test_assessments.py` in-process.

**The export half is built too, and it was not merely unimplemented — it was unimplementable.**
"The export produced in A15 is marked as resting on retracted evidence" had no implementation
anywhere, and could not have had one: `evaluate_export_selection` treated a superseded item the
same way it treated an access-denied one, so naming a retracted item blocked the export outright
and left no artefact to mark. Narrowed the same way, and `ExportMark.rests_on_retracted_evidence`
now carries it.

**Still not built: the two-step retraction R7 also describes** — marking a node is built
(`02_GLASS_FRONTEND.md` §9.5) but the suppression still takes effect through the existing
`/v1/nodes/{id}/retract` route rather than through an ingested retraction record.
`06_DECISIONS.md` ADR-046's addendum records the two decisions that blocks on.

### The fixture's statistical shape is built and proved in Phase 2

The A1/A2 site-grid mechanism (upload an image, place control points, draw a 10×10 grid) is
Phase 5's — it needs the Glass's map screen. But the *finding itself* — four yards at ~52% of
incidents, two intra-day peaks, Saturday and Sunday at ~34% — is a property of the event data,
not of the grid UI, and `07_BUILD_PLAN.md` Phase 2 builds and proves it early
(`tests/scenarios/fixtures/hmp.py`, `tests/scenarios/test_hmp_fixture_shape.py`) against a real
`AnalyticsPort` adapter. Otherwise Scenario A would only discover in Phase 5, discovered by eye
in a UI, whether the fixture ever actually carried the finding it is supposed to demonstrate.

---

## Scenario B — Communications, identity pivot and cross-case alerting

Derived from the City of London Police demonstration journey. Exercises identifier
normalisation, deduplication, entity resolution, pattern analysis, hotlist alerting and
cross-case linking.

**Fixture.** Two device extractions and two CDR files in different carrier formats, with
deliberate variation: the same number rendered four ways, CLI-suppression prefixes, duplicated
rows with differing sequence numbers, and mixed timestamp formats including one file in local
time. Two cohorts of person entities with no overt association. One messaging-handle dataset.
One later seizure record with two SIMs and a handset identifier.

### The journey

| Step | Analyst action | Platform capability | Assertion |
| --- | --- | --- | --- |
| B1 | Ingest both CDR files and both device extractions | Connectors, Knowledge Adapters | All four renderings of the shared number resolve to one `Endpoint`; `value_raw` is retained on each |
| B2 | Check the ingest report | Deduplication | Duplicate rows collapse to single events; every source row reference is retained on the survivor |
| B3 | Check timestamps | Datetime normaliser | The local-time file is converted with its original offset recorded; a file with no recoverable offset is rejected with a named error, not guessed |
| B4 | Seed a working set from the first cohort | Search, seed | Four person entities, no edges between them |
| B5 | Expand each to their endpoints, then one hop out | Search Around | One shared `Endpoint` is common to all four |
| B6 | Inspect the shared endpoint's messages | Document view | Message content renders with the entity spans highlighted in place |
| B7 | Repeat for the second cohort | Search Around | A shared messaging handle is common to that cohort |
| B8 | Examine the handle | Entity resolution | A `SAME_AS` edge, asserted at score 1.0 (ADR-024's own pattern for identifier systems with no lexical overlap — a handle and an `e164` number share none), links the handle to the shared endpoint |
| B9 | Move the resolution threshold from Strict to Balanced, on a genuinely close-but-not-exact `Person` pair the fixture provides (not the handle/endpoint pair — B8 is now a deterministic assertion, never threshold-sensitive; see the note after this table) | Resolution projection | The merge applies; the change summary reports entities merged and nodes affected |
| B10 | Open `explain` on the merged `Person` cluster | Resolution explainability | Per-comparison match weights are shown, not just the total score |
| B11 | Attribute the handle to a person | Manual link | A `SAME_AS` with score 1.0, provenance `asserted`, attributed to the analyst |
| B12 | Add the endpoint to a hotlist | Hotlist | The hotlist records owner and review date |
| B13 | Ingest the later seizure record | Hotlist alert | An alert fires naming the matched identifier, the triggering document and the rule |
| B14 | Open the alert into a pre-populated investigation | Alert workflow | The new working set contains the alert's entities and a link to the originating investigation |
| B15 | Pivot on the handset identifier | Endpoint model | Both SIMs link to one device; the SIM-swap pattern is one traversal, not a special case |
| B16 | Overlay the second investigation's timeline on the first | Cross-case overlay | Both event sets render on distinct tracks against a shared axis |
| B17 | Brush to the seizure date | Temporal brush | Location events for the device in that window restrict the map |
| B18 | Plot the device's sightings | Snail trail | An ordered track renders and animates under playback |
| B19 | Expand to common contacts across the two principal endpoints | Pattern query | The intersection set is returned, with the estimated count shown before running |
| B20 | Save the pattern as a monitor | Saved-pattern monitor | Subsequent matching ingest raises an alert with the same shape as B13 |
| B21 | Run the pathfinder between the two principal endpoints, one from each investigation | Pathfinder | `POST /v1/paths` returns k-shortest paths through the Glass end to end; the shortest path traces the same cross-case link B16 found by timeline alone, and the on-path node state matches §3.1's own convention |

### What B1–B3 prove

The unglamorous part. If identifier normalisation is wrong, the shared endpoint in B5 does not
exist, every subsequent step fails, and — worse — it fails by returning a clean, confident,
wrong answer. These three steps are the highest-value assertions in either scenario and should
be the first tests written in Phase 2.

### B8's own disposition — the chain split, 23 September 2026, correcting the scenario rather than working around it

**B8, B9 and B10 were one chain until this correction; they no longer are.** `Endpoint` carries no
`resolution` block in `packages/ontology/default.yaml` — checked directly, not assumed — and the
closed comparison-function registry (`packages/ontology/resolution_functions.py`:
`jaro_winkler`/`levenshtein`/`soundex`/`exact`) compares values of the same kind, the same reason
`06_DECISIONS.md` ADR-024 already gives for why an MSISDN and the IMSI it is dialled through
cannot be Splink-matched: "no lexical resemblance a comparison function could ever detect." A
handle and an `e164` number are the identical shape of problem. **This is the scenario catching up
with an already-accepted ADR, not the ADR being worked around**: ADR-024 decided this exact class
of identifier — two systems naming the same real-world thing with no shared lexical space — gets a
deterministic, asserted `SAME_AS` at score 1.0, written at ingest, never a Splink comparison. B8 is
corrected to say that (above).

**B9 and B10 move to `Person` resolution, unchanged in their own assertion text, because on
`Person` those assertions are literally true.** A deterministic score of 1.0 is already included
at every threshold, so "the merge applies" when moving Strict to Balanced would be vacuous against
B8's own corrected pair — there is nothing for the threshold to newly admit. `explain`'s own
"per-comparison match weights" likewise requires a real multi-comparison Splink score, which an
asserted 1.0 does not have. Both assertions are real and provable, on a real `Person` pair, which is
what B9/B10 now target.

**The fixture gap above — closed, 23 September 2026.** `Person` resolution needed a genuinely
close-but-not-exact pair; neither of this scenario's own two cohorts provides one
(`_seed_cohort`/`_seed_handle_cohort` write each cohort's own four `Person` nodes with a shared,
identical `family_name` and sequential `given_names`, no near-duplicate signal at all). **Closed by
reusing `tests/scenarios/fixtures/fixture_corp.py`'s own generator
(`generate_resolution_persons()`), not a second, hand-rolled pair** —
`test_phase8_exit_criterion_end_to_end.py`'s own `_seed_and_resolve_b9_b10_person_pair` extracts
that generator's own `close_given_name` pair's property values ("Volkov"/"Mikael" vs.
"Volkov"/"Mikhail", same DOB), writes them under fresh ids (avoiding a node-id collision with
Fixture Corp's own literal fixed ids in the same shared, persistent `ospreyflow` database), and
resolves them for real. **The measured, live score: 0.9812853391529271** — inside
(Balanced 0.95, Strict 0.99) by a real margin either side, asserted directly in that helper
(`THRESHOLD_BALANCED <= score < THRESHOLD_STRICT`) before the edge is even written, so a pair that
happened to land outside the band fails loudly rather than silently making B9/B10 vacuous again.
B9 now proves the threshold move for real (Strict: `merged == 0`; Balanced: `merged == 1`,
`affected == 2`); B10's `explain` shows a real `comparison_vector` and `manually_asserted: false`.

**Every other citation of B8 checked, none resting on it being Splink-scored.** `06_DECISIONS.md`
ADR-023 names B8 as its own precedent for using the `SAME_AS` edge *type* for a duplicate-identity
question — quoted alongside B11's own manual (asserted) link in the same sentence, never
distinguishing scored from asserted, so its reasoning holds unchanged; ADR-023 needs no correction.
Every remaining citation (`06_DECISIONS.md` ADR-025 and its own references, `07_BUILD_PLAN.md`'s
Phase 7/8 entries) groups B8 with B9/B13/B20 as needing the corpus-wide resolution trigger
(ADR-025) to run against a live deployment — **this grouping is now stale for B8 specifically**:
under the corrected, ADR-024-pattern write, B8's own edge is produced by the ingest recipe engine
at load time (ADR-024's own "natural home"), not by a later batch resolution job, so B8 no longer
depends on ADR-025's trigger at all. B9/B10, now pointed at genuine `Person` resolution, still do.
Not swept across every citation site here — recorded as a known, real consequence for whoever next
touches those references.

---

## Cross-cutting assertions

Run against both scenarios, on both the `local-lite` and `cluster` profiles.

| Assertion | Why |
| --- | --- |
| Every action appears in the audit stream with principal, query and result cardinality | Audit is architecture (`00_ARCHITECTURE.md` §5) |
| A restricted principal running the same scenario sees fewer entities, is told how many are withheld, and is never told which | Filter at the port, disclose the count, never the content |
| Every model-derived node is `inferred` until confirmed; no automatic promotion occurs | `01_DOMAIN_MODEL.md` §2.1 |
| No filter removes a node from the canvas; all filtering dims | `02_GLASS_FRONTEND.md` §2 |
| The status bar count of dimmed and withheld items is correct at every step | An analyst must never mistake a partial picture for a complete one |
| The performance budget holds throughout | `02_GLASS_FRONTEND.md` §5 |
| Results are identical on both profiles, allowing only floating-point tolerance on iterative metrics | Transportability |
| Disconnecting the network mid-scenario on `local-lite` changes nothing | Air-gap capability is a claim that must be tested |

**The two rows above are not part of V1 END TO END — recorded here by the checker, pending the
owner's own confirmation, 23 September 2026.** The owner defined `07_BUILD_PLAN.md`'s own milestone
as a `local-lite`-only, clean-laptop install-and-demo; neither row is exercised by that milestone
as a consequence of that definition — this document does not claim the owner separately stated a
view on these two rows in these terms. Both remain real, standing claims for this document to prove
once their own owning work exists. Profile-parity testing's home is Phase 8a (the `cluster`
profile); network-partition resilience has no owning phase yet — both entries, with the full
reasoning, are in `07_BUILD_PLAN.md`'s "Out of scope for v1" list, not deleted from here.
