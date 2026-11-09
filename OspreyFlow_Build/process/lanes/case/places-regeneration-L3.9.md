# placesByRole.json at L3.9's merge: a regeneration note for the orchestrator

`OspreyFlow_Core/apps/workspace/src/shell/placesByRole.json` (rules') is left as on main on this branch. After
merging L3.9, regenerate it from the routes:

```
cd OspreyFlow_Core && OSPREY_WRITE_PLACES_BY_ROLE=1 .venv/bin/python -m pytest -q \
  ../OspreyFlow_Build/tests/services/api/test_place_routes.py -k record_of_places
```

Expected change, and the only one: `right:merge_datasets` gains `answered_hidden` `["drawn_merge_dry_run",
"drawn_merge_sheet", "drawn_merge_targets", "merge_drawn_dataset"]`; its `places` stays `[]`. The four Studio routes
(classed `ingest` in `test_place_routes.py`, this branch) answer a holder of `merge_datasets` alone because that is
the right they name; each still asks the dataset's gate and an Author level on the target's home case. Until it is
regenerated, `test_the_record_of_places_by_role_is_the_routes` fails on the branch; L3.9's gates are run with it
regenerated (not committed).
