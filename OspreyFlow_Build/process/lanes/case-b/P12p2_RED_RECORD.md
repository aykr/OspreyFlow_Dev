# case-b · P12 part 2 · the red record (rule 15)

## Piece 1: the extraction-engine setting (`models.extraction_engine`)

`tests/schemas/test_extraction_engine_setting.py`, written before `packages/schemas/deployment.py`'s field and
validator (rule 1), run on the Mac offline with the closed ports, 11 November 2026:

- **Red before the setting existed: 15 failed of 15** — the default absent on every profile, Laurium neither taken
  on cloud-platform nor refused in its own words elsewhere, the cluster translation not carried.
- **Found writing it (rule 15's second clause):** the first version's "any other value refused" matched on the
  field's name, and **passed before the field existed**, because `extra="forbid"` refused the unknown field itself.
  It now matches the literal's own refusal (`Input should be 'deep_read' or 'laurium'`), and was red with the rest.
- **Green after: 15 passed**; with it, `test_cloud_platform_render.py`, `test_model_engine_kinds.py`,
  `test_model_engines.py` and `tests/schemas/` 404 passed, 4 xfailed. `tools.schemas_check` clean after
  `generate_ts.py` (`ModelsConfig.ts`, `OspreyConfig.ts`).

## Piece 2: Laurium in the cloud-platform render

`tests/harness/test_laurium_render.py`, written before `harness/laurium.py` and the render's hook (rule 1), on the
Mac offline with the closed ports, 11 November 2026:

- **Red before: 6 failed, 7 passed.** The 7 were the regression guards (nothing of Laurium unless chosen; another
  profile unchanged), true before Laurium existed; each is shown red by its own plant below.
- **Found writing it:** the test first asserted the Secret held `LITELLM_MASTER_KEY`; the render's Secret names it
  `OSPREY_LITELLM_MASTER_SECRET` (the gateway's container maps it). Corrected; the assertion is the pairing that
  makes the no-`envFrom` case mean something.
- **Green after: 13 passed**, with `P12p2_platform.diff` applied (render's hook, Laurium's port, the gateway
  rendered while Laurium is chosen, its image and resources in the profile). The harness, CLI and cp-policy-check
  suites beside it: 1,674 passed, one failure in `test_deployment_schema.py` reading the owner's own local
  `osprey.yaml` (`osm-local-great-britain`), not this change.
- **Plants, at the real call site (`harness/laurium.py`), each put back:**

| Plant | Red |
| --- | --- |
| `env_file: [deployment.env]` in Laurium's stanza (its pod reads the deployment's Secret, the master key with it) | 2 failed: "Laurium's pod reads the deployment's Secret" |
| Laurium rendered whatever the setting (the `chosen` check removed) | 4 failed: "values.yaml names Laurium, which was not chosen" |
