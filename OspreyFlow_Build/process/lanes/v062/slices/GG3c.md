# Slice GG3c · GG3 · The case's timeline as a GOV.UK page, read-only: the case's events counted by day (or by hour, week or month) and by weekday and hour, each as a plain SVG chart followed by a table of the same figures (a draft)

**Status: a draft, not ruled.** Written in an away drafting session (D246), 26 to 27 November 2026, on the branch
`drafts/2026-11-27`, read from `origin/main` at `7f4f9554a`. No row in `slices.tsv`; no builder starts from this paper.
**Size M.**

**Where it comes from.** The plan's row "GG3c: the case's timeline, read-only: the events and the histogram as a table
and a plain SVG chart (the GR3a chart rule), with playback later" (`slices/drafts_2026-11-26/CHAIN_PLAN.md:75`), which
depends on "GG3b's case path; the timeline module waits for decision 6's module rules", and whose exception column
offers "the table and chart before GG2". `FUNCTIONS.yaml` row `timeline-playback` (`OspreyFlow_Core/apps/pages/FUNCTIONS.yaml:229-235`:
"Timeline and playback", scenarios A4, A5, A11, B16, B17, B18, slice "R5", no route). The owner's chart rule of
24 November: "**charts are plain SVG with classes, no library, no inline style, each with a table of the same
figures**" (`slices/GR3a.md:6`). ADR-152 decision 6 puts "timeline" among the drawing modules
(`spec/06_DECISIONS.md:41037-41038`, :41060); **a read-only chart drawn on the server is not a module** and needs none.

## What exists today (read on `origin/main` at `7f4f9554a`; re-read, lines move)

- **The routes.**
  - `POST /v1/analytics/histogram` (`histogram_route`, `services/api/app.py:9974-9998`): `require_right(INVESTIGATE)`;
    the case in the body (`filter.investigation_scope`) is gated at **Viewer** by `_case_event_filter`
    (:9953-9967), which also discards any `inherited` the caller sent: "It counts the case's own events alone"
    (ADR-144 Amendment 1). A case the reader cannot see raises `InvestigationNotFoundError`, **404
    `investigation_not_found`** (handler :3343-3349). Viewer is the lowest level, so no level is "too low" here; only a missing
    `INVESTIGATE` right is **403** (`require_right`). Audited
    `analytics_histogram` with the total.
  - `GET /v1/investigations/{id}/events/holders` (`case_event_holders_route`, :19528-19561): when the case holds no
    events the reader may count, the other cases the reader can open that read one of its datasets and do hold them
    (ADR-099 Amendment 9, `spec/06_DECISIONS.md:10600`). "A case the reader holds no level on is never listed, so never
    named."
  - **No route lists a case's events.** `list_events` is reached only inside the Conduit (`app.py:19550`,
    `services/api/link_events.py:64`, `document_reader.py:257` and others); the only events a Glass route lists are one
    link's (`GET .../links/{edge_id}/events`, `app.py:7756`, GG3d1's).
- **The shapes** (`packages/schemas/analytics.py`): `HistogramRequest` (:261-273: `filter`, `bucketing`,
  `interval_seconds` required for `fixed_interval`, `field` for `categorical`, a 422 otherwise); `HistogramBucket`
  (:276-286: `start`/`end`, or `weekday`/`hour`, or `label`, and `count`); `Histogram` (:289-292: `bucketing`,
  `buckets`, `total`); `EventFilter` (:185-243); `CaseEvents` (:637-646).
- **What the adapter sends.** Only **buckets that hold an event**, in order: `GROUP BY bucket ORDER BY bucket`
  (`packages/adapters/analytics_duckdb/adapter.py:421-438`; the weekday-hour grid the same, :440-456). A fixed
  interval is counted from the Unix epoch (`floor(epoch(occurred_at) / ?)`, :422), so **a seven-day bucket starts on a
  Thursday** and a thirty-day bucket on no calendar boundary. The ClickHouse adapter's `histogram` is at
  `packages/adapters/analytics_clickhouse/adapter.py:326` (not re-read here: the builder reads it).
- **The React timeline.** `apps/workspace/src/timeline/Timeline.tsx` (846 lines, echarts on a canvas): a daily density
  strip (`DAILY_INTERVAL_SECONDS`, :81), asked again by the hour when every event is on one day (ADR-097 step 3,
  :83, :261-277), the cyclical weekday × hour view (`weekday_hour`, :262), the brush, playback (`usePlayback`, :214),
  the cross-case overlay (B16, :219-244), and the "events elsewhere" sentence (:150-169), which is
  `eventsElsewhereSentence` in `apps/workspace/src/analytics/eventsElsewhere.ts:7-16` (pure; **not in glass-shared**).
  The shared fetchers are `packages/glass-shared/src/analytics/api.ts:43-64`.
- **The chart pattern on the GOV.UK tree.** GR3a's `chartOf` (`apps/pages/server/views/alertMonitoringWords.ts:384-397`)
  and `tree-govuk/alert-monitoring.njk:33-39`: `rect` elements with a class and their geometry as attributes, the
  chart `role="img"` with a title and a description saying a table follows. **It draws horizontal bars, one per row**;
  no time axis exists in the pages yet.
- **The address.** GR1a merged at `/cases` and `/cases?case=<id>` (`tree-govuk/routes.yaml`; `server/pageList.ts:25`);
  GR1a question 1 was ruled (a), the query form (`RULINGS.md`, 26 November 12:15). GG3b is at `/cases/document`
  (`away/GG3b`). A path belongs to one page and an id to one `FUNCTIONS.yaml` row (`server/pages.ts:106-146`).
- **Scenarios.** A4, A5 and A11 (`spec/08_ACCEPTANCE_SCENARIOS.md:385-386`, :392) start from the canvas's filtered
  selection and a brush. **None reads a whole case's timeline by its address**, so a scenario is written first
  (decision 12).

## Acceptance (red before, green after)

A new `spec/08` scenario **TL** (a case's timeline, GOV.UK tree), written first, and
`apps/pages/test/govuk/timeline.test.ts`, red (no page), green after; `test_govuk_timeline_scenario.py`'s census of
`Histogram`, `HistogramBucket` and `CaseEvents` green.

## Questions for the owner (the proposal first)

1. **Scope.** (a) **The whole case's events, read-only: the density by time (question 4's bucket) and the weekday ×
   hour grid (A4), each as a plain SVG chart followed by a table of the same figures.** No brush, no playback, no
   overlay, no node restriction (a page has no selection), no "select what is lit". (b) With a window form (from and
   to dates) narrowing both: the React strip never filters itself by its window (`Timeline.tsx:246-253`), so a window
   only matters to a page that shows something else beside it. Later, with GG2e.
2. **When it starts.** (a) **After GG3b merges** (the plan's row, `CHAIN_PLAN.md:75`, "GG3b's case path", and the
   lane order GG3b → GG3c; both add to `pageList.ts` and `routes.yaml`), **before GG2b and PL8b**, as the plan's
   exception column offers ("the table and chart before GG2"): it draws nothing with Sigma and needs no selection. This
   is an early start against the plan's "GG3 needs GG2 and PL8"; the index flags it. (b) After GG2b and PL8b, as the
   row's "needs" say.
3. **The address.** (a) **`/cases/timeline?case=…&view=time|week`, the page of the `timeline-playback` row**, with
   GR1a's case page linking to it. (b) A part of GR1a's case page: two charts and a 168-cell table make that page long,
   and the row is a function of its own.
4. **The bucket for the density, and a long span.** The adapter sends one bucket per interval that holds an event, with
   no cap of its own. A case over five years by day can send about 1,800 rows. (a) **Asked by the day first; if every
   event is on one day, asked again by the hour (as ADR-097 step 3); if the answer has more than 400 buckets, asked
   again by 7 days, then by 30, then by 365, until it has 400 or fewer.** The bucket is said above the chart ("Counted
   in 7-day periods, from Thursday 1 January 2026"), every event is still counted (the total does not change), and
   nothing is cut (rule 2): a coarser bucket covers the same events. Each row says its own start and end, as the route
   sends them, since epoch-aligned periods start on no calendar day. At most four reads a render, each audited by the
   route. (b) Always by day, all rows shown. (c) A page-side cut to the latest 400 days. **Not proposed** (rule 2).
5. **Days with no events.** The route sends none. (a) **The table lists the periods that hold events and says so**
   ("Periods with no events are not listed"); the chart draws on a time axis, so a gap is a gap. (b) The page fills the
   missing periods with zero rows: a figure the route did not send, so not proposed.
6. **The weekday × hour grid's figures.** A4's expectation is a share ("Saturday and Sunday together are ~34%").
   (a) **A table of seven rows (Monday first, as the route's weekday 0) and 24 hour columns, with each day's total and
   its share of the case's total, all from the route's own counts** (the reader's own, so no rule-3 question); the chart
   is a 7 × 24 grid of `rect` cells, each with a class from a fixed five-step scale of the largest cell, and its count
   in its title. Times are said in UTC, as the route counts them. (b) The grid as a chart only, with the table of the
   density alone. **Not proposed** (the owner's chart rule: each chart has its table).
7. **A case with no events of its own.** `eventsElsewhereSentence` returns one joined string (`eventsElsewhere.ts:7-16`),
   so it cannot carry a link per case. (a) **`eventsElsewhere.ts` moves to `packages/glass-shared` unchanged (I11, as
   GG2c), re-imported by the workspace, and gains beside it a pure `eventsElsewhereParts(found)` returning the fixed
   words and the list of `{investigation_id, name}` in the route's order; `eventsElsewhereSentence` is rewritten over
   it, its own tests unchanged and green.** The page draws the words with each named case a link to
   `/cases?case=…`. Otherwise "This case has no dated events." (b) The sentence moved as it is, with no links.
8. **The panel frame.** (a) **Not mounted here**: the page is laid out in the GOV.UK width. When PL8b merges, the
   timeline region is its `timeline` slot (PL8b question 4), a step in PL8b's or a later slice. (b) Wait for PL8b.
9. **What waits for a module.** (a) **The brush, playback (B18), the cross-case overlay (B16) and the dimming of the
   graph are a later slice of the timeline module** (decision 6), after GG2e gives a page a working set to dim. The
   function row stays "planned" until then, with this page as its first route. (b) Your words.

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | A case with events on 40 days (synthetic) | one `POST /v1/analytics/histogram` with `bucketing: fixed_interval`, `interval_seconds: 86400`, the case in `filter.investigation_scope` and nothing else in the filter; 40 rows and 40 bars; the total said | `inherited` or `node_ids` sent in the filter |
| 2 | Every event on one day | a second read by the hour; 24 or fewer rows; "Counted by the hour" | the daily answer drawn as one bar |
| 3 | A span the day count puts over 400 buckets | the re-ask by 7 days (and on, as needed); the bucket said; the total equal to the first answer's | the first 400 days drawn (a page-side cut) |
| 4 | Each bar against its row | every bar's height and every cell's class follow from the table's count | a bar drawn from another row's count |
| 5 | The weekday × hour grid | one read with `bucketing: weekday_hour`; seven rows Monday first; each day's share sums to 100 within rounding | Sunday put first (weekday 0 read as Sunday) |
| 6 | No `style` attribute, no script, no `innerHTML` | none in the output | a bar sized by `style="height: …"` |
| 7 | A case with no events, two other readable cases holding them | the sentence names both, each a link to `/cases?case=…` | one holder dropped (the page listing only the first of `held_by`), or the names drawn without links |
| 8 | A case with no events and no holders | "This case has no dated events." | an empty chart and table |
| 9 | No level on the case (404), no `INVESTIGATE` (403), a missing case | GR1a's 404 page for each | the 403 said in words |
| 10 | A body missing a field `Histogram` requires | "could not be read" | each required field removed in turn |
| 11 | The fixture | refuses as the route does: 422 for `fixed_interval` without `interval_seconds`, 404 by the case's Viewer gate, 403 without `INVESTIGATE`, and sends only non-empty buckets | a fixture that sends zero buckets the adapter never sends |
| 12 | The Conduit gives no answer, or 401 | the 502 page; 401 says to sign in again | an empty timeline |
| 13 | No internal id on the page | the case id only in a link's query; no bucket or event id | an id printed |
| 14 | Keyboard and scripts off | the page whole (the page adds links only; one tab-order case in `test/govuk/keyboard/timeline.spec.ts`, rule 13; I4) | a link out of the tab order |

## Waits on

GG3b merged (its case path, and the shared `pageList.ts` and `routes.yaml` lines; the lane runs GG3b → GG3c). Not GG2b or
PL8b if question 2 (a) is taken (an early start against the plan's row, flagged in the index). Nothing in it waits on
WS4b.

## Files touched

`spec/08` (scenario TL); `spec/02` (the GOV.UK timeline under the chart rule, a sentence); `apps/pages/FUNCTIONS.yaml`
(`timeline-playback`: its route and scenario); `apps/pages/server/timeline.ts`, `server/views/timelineWords.ts`,
`server/pageList.ts`; `tree-govuk/timeline.njk`, `tree-govuk/routes.yaml`; `server/cases.ts` and `tree-govuk/cases.njk`
(the link); `packages/glass-shared/src/analytics/eventsElsewhere.ts` (moved) and its test, re-imported by
`apps/workspace/src/timeline/Timeline.tsx` and `reports/TrendsTab.tsx`; `test/govuk/timeline.test.ts`,
`timelineConduit.ts`, `timelineServer.ts`, `keyboard/timeline.spec.ts`, `scripts-off/timeline.spec.ts`;
`OspreyFlow_Build/tests/glass_trees/test_govuk_timeline_scenario.py`; `tests/harness/test_pages_setting.py` (the route
list); `test_tree_parity.py`'s pins.

## Checks (frozen when cut)

GG3b's list (`slices/GG3b.md`), with the timeline scenario test in place of the document one, and the React workspace's
suite for the moved sentence.

## Out of scope

The brush, playback, the overlay and the graph's dimming (the module, later); a list of the case's events (no route: an
amendment, decision 11); the panel frame (PL8b); any Conduit change; `apps/workspace` beyond the one re-import.
