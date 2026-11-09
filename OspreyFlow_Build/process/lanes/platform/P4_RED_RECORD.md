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
