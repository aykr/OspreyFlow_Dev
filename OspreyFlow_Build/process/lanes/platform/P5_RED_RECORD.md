# Platform lane · P5 · red record (rule 15)

Each fix removed at its own call site, the test run red, the fix restored and the test green. Offline
runs on the closed ports (59991–59994), no lane set.

| Fix | Plant (at the call site) | Test | Red |
| --- | --- | --- | --- |
| Ruling 8: the build's unit, checked before anything runs | `app.build_basemap_route`: `gazetteer_unit = "unit-1"`, the check skipped | `test_geospatial_admin_routes.py::test_the_build_s_unit_is_a_setting_and_an_unknown_one_is_refused_in_words_before_anything` | `assert 200 == 422` |
