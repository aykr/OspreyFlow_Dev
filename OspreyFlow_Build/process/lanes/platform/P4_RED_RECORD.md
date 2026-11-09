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

Each restored: 13 passed. The stamping itself, live: see the leased run below.

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

Each restored: 7 passed.

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

Each restored: 3 passed.

**The reference images: the comparison could not fail in the dark theme.** With the picture rewritten
for P4, the old dark reference (the four channel dots of 8 November) still passed against the new
page: at Playwright's default per-pixel threshold of 0.2 (YIQ), a dark scene's changes fall under it.
With `threshold: 0.05` the same comparison failed (324,927 pixels, 36%), then the three references
were made (`map-contrast-{dark,light,govuk}-darwin.png`) and passed twice more unchanged.
