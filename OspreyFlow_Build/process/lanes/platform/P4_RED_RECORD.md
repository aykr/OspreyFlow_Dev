# Platform P4 · each new test shown red by a plant at its real call site (rule 15)

Each plant was applied to the code under test, the test run, and the file restored (a scratch script
that replaces one exact string, runs pytest or Playwright, and writes the original back). Offline runs
pin the closed store ports (59991–59994), no lease, no `OSPREY_LANE`.

## Place search (`services/api/map_places.py`, `POST /v1/investigations/{id}/map/places`)

`tests/services/api/test_map_places_route.py`, 9 November 2026:

| Plant | Where | Red |
| --- | --- | --- |
| the gazetteer filter dropped (any `Location` with a `geometry_ref` kept) | `search_places`' `candidates` | `test_only_the_gazetteers_places_with_a_point_are_offered` (the yard offered) |
| the place's `osm_id` joined to its name | `search_places`' `MapPlace(...)` | the same, and `test_a_gazetteers_own_identifier_never_reaches_the_glass` |
| `more` taken from the store alone | `search_places`' return | `test_more_is_said_when_more_places_matched_than_are_shown` |
| the deployment's online geocoder asked when nothing is found | `map_place_search_route`, after the search | `test_no_hosted_geocoder_is_called_even_when_the_deployment_names_one` |

Each restored: 6 passed.

## No key in any map answer the Glass reads

`tests/services/api/test_glass_map_reads_carry_no_key.py`, 9 November 2026 (an Admin key and an
installer's `env:` key planted; every `GET /v1/map/*` route walked for every provider):

| Plant | Where | Red |
| --- | --- | --- |
| a proxied provider's own `source` given to the Glass | `mapconfig_loader.public_view` | both cases (`answers`, `refuses`): the hosted address and `{credential}` in `/v1/map/providers` |
| a refused tile's words naming the upstream URL | `get_map_tile_route`'s 502 | `[refuses]`: the Admin key and the address in the answer |

Each restored: 3 passed.

## The gazetteer's dataset and points (the orchestrator's settlement, option A)

`tests/services/api/test_geospatial_admin_routes.py::test_the_build_loads_the_places_into_the_regions_gazetteer_dataset_with_their_points`:

| Plant | Where | Red |
| --- | --- | --- |
| the loader handed no analytics store (`analytics=None`) | `build_basemap_route`'s `_load_places` | the case |
| the dataset's registration dropped | the same | the case (no `gazetteer-osm-rutland` in the store) |

Each restored: 13 passed. The stamping itself, live: see "The leased live run" below.

## The basemap switch and the place search, by keyboard (rule 13)

`apps/workspace/keyboard/map-view.spec.ts` (`MAP_VIEW_ACTIONS`), 9 November 2026, port 5185 free
(another worktree's vite had held it earlier; waited, never reused). Each plant in the product code;
each made its case red and, with it, the registry's coverage case:

| Plant | Where | Red |
| --- | --- | --- |
| choosing a basemap does nothing | `BasemapSwitch`'s `onChange` | `the basemap is switched by keyboard…` |
| the map keeps the caller's provider whatever is chosen | `MapView`'s `active` | the same |
| going to a place moves nothing | `MapView`'s `PlaceSearch onGo` | `a place is found in the case's gazetteer and shown by keyboard` |
| Enter in the search submits nothing | `PlaceSearch`'s `onSubmit` | the same |

Each restored: 7 passed. Added after the lane's review: the third keyboard case (`a name the gazetteer
does not hold is said in words…`), red with the empty answer's words removed from `PlaceSearch`; a
`-g Atlantis` filter matched no test at first ("No tests found", not a pass), so it was run by its title.

## The map's contrast in the dark, light and GOV.UK themes

`apps/workspace/map-verify/contrast.spec.ts`, 9 November 2026. Fifteen pairs a theme, each read from
its call site (`buildBundledDarkStyle`, `overlayColours`, the controls' computed CSS).

**Red on the real code first.** The first run, before any fix: the dark theme's `marker on water` at
**2.7:1**, under WCAG 1.4.11's 3:1 (brass on the ramp's second step); light and GOV.UK passed. Fixed in
`style.ts`'s `landAndWater`: water the ramp's first step and land the panel surface wherever a marker
on the second step would fall under 3:1 (the dark theme), so markers are 4.39:1 on water and 5.78:1
on land, and land and water stay apart (`style.test.ts`'s 0.08 OKLab lightness, 0.088).

| Plant | Where | Red |
| --- | --- | --- |
| a marker drawn in the hover surface | `overlayColours` | all three themes |
| water always the ramp's second step | `landAndWater` | the dark theme (2.7:1, as found) |
| the controls' note in `--text-tertiary` | `mapControls.css` | **not red**: it still meets 4.5:1, so it proves nothing (kept here, not counted) |
| the controls' note in `--border-strong` | `mapControls.css` | the dark and GOV.UK themes |

Each restored: the 3 floor checks passed (the plants were run against the floor checks alone; the
reference images are this section's last paragraph).

**The reference images: the comparison could not fail in the dark theme.** With the picture rewritten
for P4, the old dark reference (the four channel dots of 8 November) still passed against the new
page: at Playwright's default per-pixel threshold of 0.2 (YIQ), a dark scene's changes fall under it.
With `threshold: 0.05` the same comparison failed (324,927 pixels, 36%), then the three references
were made (`map-contrast-{dark,light,govuk}-darwin.png`) and passed twice more unchanged.

## The lane's review round (9 November 2026)

The lane-reviewer's findings, each fixed and shown red (offline, closed ports):

| Finding | Plant | Red |
| --- | --- | --- |
| the store matches a `Location` on its identifiers, so a `uprn` fragment found a place (rule 7) | the name match dropped in `is_gazetteer_place` | `test_a_match_on_a_gazetteers_identifier_alone_offers_nothing` |
| "the gazetteer's places" were picked by identifier, so a case's own address with a postcode was one | the `gazetteer-*` dataset check dropped | `test_only_the_gazetteers_places_with_a_point_are_offered` (the case's address offered) |
| a query of spaces reached the store as an empty scan (a 500 against ArcadeDB) | the stripping validator returns the value unchanged | `test_a_spaces_only_query_is_refused_not_a_scan` |
| no test went through the real case-level check (rule 4) | the route takes a bare `investigation_id` in place of `InvestigationViewerDep` | `test_the_case_level_is_checked_before_the_store_is_asked` (no level, another case) |
| an `osprey.yaml` provider with `credential: env:` and no `proxy` line was handed to the Glass whole | the needs-a-key refusal in `MapProvider` disabled | `test_a_provider_the_browser_fetches_takes_no_key` (the two `{credential}` shapes) |
| a key typed into a browser-fetched address | the key-named-parameter refusal disabled | the same test (the two typed shapes) |
| an unreachable database at a command-line build was a traceback | the `except` narrowed to nothing | `test_an_unreachable_database_is_said_in_words` (a refused connection and an unresolvable name; an authentication refusal is caught but not planted, since importing the driver marks a test file live) |
| an empty answer with `more` was said as "no such place" (rule 2) | `PlaceSearch` ignores `more` | `MapControls.test.tsx` |

**A plant that proved nothing, first (rule 15's second paragraph):** the first two shapes of
`test_a_provider_the_browser_fetches_takes_no_key` used `?key={credential}`, which the key-named rule
also refuses, so disabling the needs-a-key rule left them refused by the other: 15 passed under the plant.
Their parameter was renamed `tile`, and each case now matches its own rule's words; then each plant
made exactly its own two cases red.

**The axe state `searched=1`:** checked drawn before it was relied on: a scratch Playwright case (not
kept) opened the harness with `searched=1`, with and without `brand=govuk`, waited for the network to
settle as `every-harness.spec.ts` does, and found both "Go to …" buttons each time.

## The leased live run

**Platform lease on stack b, 02:23:11–02:31:30 UTC 9 November 2026, at `e1470f1`** (on main `90b3149`),
ports pinned from the lease's own export line, `OSPREY_LANE=platform`; `make -k ci` was running offline
on this machine at the same time (load average 24–29).

- `test_route_rights.py`, `tests/ingest/test_gazetteer_place_search_live.py`,
  `test_map_admin_build_end_to_end.py`, `test_build_local_basemap_end_to_end.py`,
  `test_osm_gazetteer_recipe_end_to_end.py`, `test_tile_cache.py`, `test_prefetch.py`,
  `tests/geocoder/test_match_live.py`, `test_statelessness.py`: **23 passed, 1 failed, 1 error**, the two
  both `test_statelessness.py`'s, whose Conduit subprocess did not answer within the test's 15 seconds
  ("never came up"). Not this branch's: the same Conduit started cleanly by hand under the same lease,
  and with the wait raised to 90 seconds for one diagnostic run (the file restored) both passed (2
  passed, 27 s). The machine's load, not the change.
- **The stamp, red live:** `load_gazetteer` writing through the plain graph (`stamping` dropped):
  `test_a_case_that_added_the_gazetteer_finds_its_place…`, `test_a_rebuild_writes_no_second_copy…`,
  `test_map_admin_build_end_to_end[finished]` and `test_build_local_basemap…` red (4 failed).
- **The case's limit, red live at its own assertion:** the search asking the store with an unlimited
  principal (`principal.model_copy(update={"datasets": None})` in `search_places`): red at `assert
  nothing.places == []`, the case that did not add the gazetteer then finding Cranford. (A first plant,
  stamping into the case's own dataset, went red only at the case that did add it, since the search keeps
  `gazetteer-*` datasets alone, so it did not show this side; kept here, not counted.) Restored: passed.
- Teardown: each live test's ArcadeDB database is a throwaway one, dropped pass or fail
  (`arcadedb_adapter`); the analytics store is in memory; the stack was brought down before release.

## The independent review's round, and the lane's review of it (9 November 2026)

Offline plants (closed ports, no lease):

| Item | Plant | Red |
| --- | --- | --- |
| 2: a gazetteer's identifiers withheld from every request reader | `_gazetteer_identifiers_withheld` dropped from `withhold_sources` | `tests/ontology/test_gazetteer_identifiers_withheld.py::test_a_request_reader_is_sent_a_gazetteer_place_without_its_identifiers` |
| 3: the store asked by name alone, `more` included | `search_places` back on `suggest_nodes` (contains, ignoring case, `Location`), the shape it had | `test_an_identifier_fragment_finds_no_place_and_says_no_more`, at its assertion (`more` true): the stand-in's `suggest_nodes` matches identifiers as `suggestion_scope` does, so the case fails at the assertion and not on a missing method |
| 6: registration after the load commits | `map_admin._build_here` registers before the commit; the script registers before the load | `tests/test_gazetteer_build_registration_order.py`: `…cli_build…[finished]`; the script's two cases |
| 8: a user part or a key-like path segment in a browser-fetched address | each refusal disabled | `test_a_provider_the_browser_fetches_takes_no_key[…user part]`, `[…key-like path segment]` (two) |
| 8: the path rule reads whole segments | the segment rule replaced by the letter rule (`_KEY_NAMED`) | `test_a_word_holding_key_is_not_refused` (`monkey.pmtiles`, `keystone`, `authority-maps`, `turnkey`) |

**Live plants**, platform lease on stack a (below):

| Item | Plant | Red |
| --- | --- | --- |
| 2 | the projection dropped | `tests/ingest/test_gazetteer_ids_withheld_live.py`, at `/search`'s answer carrying `osm_id` and `uprn` |
| 3 | `suggest_nodes` (contains, ignoring case) in place of `suggest_locations` | `test_an_identifier_fragment_finds_no_place_and_no_more`, at its assertion (`more` true) |
| 5 | the store asked with the reader's clearance raised to SECRET | `test_a_case_that_added_the_gazetteer_finds_its_place…`, the SECRET depot offered (its point OFFICIAL, so only the graph store's access step keeps it out) |

**Two plants that proved nothing first (rule 15), kept, not counted:**
- the first live plant of item 3 called `SuggestOptions`, which `map_places` does not import: every case
  errored on the name, not at an assertion. Redone with the import.
- redone, it passed: with one place holding the fragment, the name check alone rejected it and the scan
  never filled, so `more` stayed false. The case now plants 205 places whose identifiers, not names,
  hold the fragment (more than one scan of 200 reads); then it went red at `more`.

**Axe states drawn (item 9 and the review's 11):** a scratch Playwright case (not kept) opened the
harness at `searched=1`, `searched=more` and `searched=fail`, each with and without `brand=govuk`, waited
for the network to settle as `every-harness.spec.ts` does, and found each state's words already in the
status (6 passed); axe on the four states in dark, light and GOV.UK, 16 passed. Port 5184 was held by
another worktree's vite throughout, so both ran from a temporary copy of `a11y/playwright.config.ts` on
port 5187, removed afterwards.

## The leased live run, round 2

**Platform lease on stack a, 03:31:21–03:38:05 UTC 9 November 2026**, at `aad6e9b` and again at
`b38c6de` (the second only adds the identifier-fragment case's 205 places), on main `75f277d`. **Nothing
else ran on this machine of this lane's during the lease** (no `make ci`, no Playwright); load average 4–5.

`test_route_rights.py` (with L3.5's routes, on main), `tests/ingest/{test_gazetteer_place_search_live,
test_gazetteer_ids_withheld_live,test_map_admin_build_end_to_end,test_build_local_basemap_end_to_end,
test_osm_gazetteer_recipe_end_to_end}.py`, `test_tile_cache.py`, `test_prefetch.py`,
`test_statelessness.py`, `tests/geocoder/test_match_live.py`, `test_sources_withheld_routes.py`,
`tests/adapters/graph_arcadedb/test_sources_withheld_live.py` and every file under
`tests/services/api/working_set/` (the per-reader projection changed): **336 passed** at each commit.
`test_statelessness.py` passed with its own 15 s wait unchanged; its round-1 failures were the load.
The three live plants above were run within the same lease. Teardown: the throwaway databases dropped;
`test_gazetteer_ids_withheld_live.py` removed its nodes and link by id, deleted its two cases (each
delete checked) and its dataset rows (asserted gone).
