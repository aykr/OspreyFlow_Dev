# 08 — Acceptance Scenarios

Two analyst journeys, taken from the supplied documents, that between them exercise every
capability in the pack. They are the functional definition of done: if a scenario needs
scenario-specific code to pass, the platform has failed the test rather than passed it.

Both run on synthetic fixtures generated from a seeded generator in `tests/scenarios/fixtures/`.
No real data enters the repository.

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
entry found true of the single-session walkthrough as written and not a claim that hotlists and
monitors fire across different analysts — the operational case B13's own CoLP framing is actually
modelled on. Both instances share the same shape: an acceptance row whose literal wording is
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

**A fixture gap this correction surfaces, disclosed rather than filled in silently:** `Person`
resolution needs a genuinely close-but-not-exact pair — this scenario's own two cohorts
(`_seed_cohort`/`_seed_handle_cohort`, `tests/scenarios/test_phase8_exit_criterion_end_to_end.py`)
currently write each cohort's own four `Person` nodes with a shared, identical `family_name` and
sequential `given_names` ("Member0", "Member1", ...) — structurally simple, no near-duplicate
signal for Splink to score. **Scenario B's own fixture does not yet contain a `Person` pair B9/B10
can be genuinely exercised against**; `tests/scenarios/fixtures/fixture_corp.py` already builds
this shape for a different demo case and is not reused here without a real decision to do so.
Real, unscoped work — owning phase Phase 8 — not built under this correction.

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
