# placesByRole.json at L3.4's merge: a regeneration note for the orchestrator

`OspreyFlow_Core/apps/workspace/src/shell/placesByRole.json` (rules') is left as on main on this branch.
After merging L3.4, regenerate it from the routes:

```
cd OspreyFlow_Core && OSPREY_WRITE_PLACES_BY_ROLE=1 .venv/bin/python -m pytest -q \
  ../OspreyFlow_Build/tests/services/api/test_place_routes.py -k record_of_places
```

Expected changes, and the only ones (after the independent review's round 2):
- `right:review_promotions` gains `answered_hidden` `["decide_promotion", "list_dataset_promotions",
  "promotion_details"]`; its `places` stays `[]`. These three Studio routes answer a person holding
  `review_promotions` alone because that is the right they check; *Details* and a decision still ask one of the
  dataset's Authors.
- `analyst` and `right:investigate` each gain `answered_hidden` `["cancel_layer_merge",
  "delete_removed_case_layer", "dry_run_delete_removed_case_layer", "merge_removed_case_layer",
  "open_layer_merge"]`: the removed-case writes name `investigate` (ADR-112: a Reports Viewer refused every
  write), which these hold; each still asks the dataset's own gate and Author level on its home case, so
  only one of the dataset's Authors acts. No place is newly offered to anyone. Until it is
regenerated, `test_place_routes.py`'s `test_the_record_of_places_by_role_is_the_routes` and
`test_every_route_of_a_hidden_place_refuses_the_role[...]` fail on the branch; L3.4's gates were run
with it regenerated (not committed).
