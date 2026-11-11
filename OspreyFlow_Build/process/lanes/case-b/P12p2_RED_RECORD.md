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
