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

## Piece 3: Laurium's traffic, read from Helm's output in Calico's order

`tests/harness/test_laurium_network_policy.py`, on the test server offline at 98587eb with `P12p2_platform.diff`
applied from the working tree (Helm runs in Docker; `gates/98587eb.p12p2-server-*.txt`):

- **The finding, measured on the rendered chart** (`--runxfail`): today Laurium's pod **reaches an outside host,
  the Conduit, ClickHouse and the gateway on another port**, and **every pod reaches Laurium** (the workspace,
  ArcadeDB and the gateway among them); no egress policy of its own is rendered. `allow-egress` (`all()`, order
  100) decides before anything narrower.
- **Ruled (the orchestrator, relaying platform's P7b design):** no policy of Laurium's own; its rows in P7b's
  `egress.paths` (`P12p2_egress_paths.md`). Until they land the three Helm-read cases are `xfail(strict=True)`,
  each failing for the reason above (read with `--runxfail`, not assumed: round 3's lesson); the controls
  (the Conduit reaching a store, the managed stores and the gateway) pass, so the evaluator is not denying blindly.
- **The evaluator**, on hand-written manifests in P7b's announced shape and in today's: 3 passed offline on the
  Mac, among them a selector it cannot read refused rather than guessed.
- With it on the server: the render's 13 and the setting's 15, passed.

## Piece 4: the Conduit's routing and Laurium's key at start

Written before `adapters/extract_laurium/composed.py`, `keys.laurium_at_start` and `harness.laurium.laurium_env`
(rule 1): `tests/adapters/extract_laurium/test_laurium_at_start.py` (red at collection: the module did not exist),
the render's `test_the_conduit_is_told_the_choice_and_lauriums_address` (2 failed: `KeyError
'OSPREY_EXTRACTION_ENGINE'`). Green after: 8 and 15. Plants at the real call sites, each put back (offline, the Mac):

| Plant | Red |
| --- | --- |
| `extract` sent to the inner adapter (`LauriumExtracts.extract`) | 1 failed |
| an unknown engine read as Deep read (`extraction_from_env`) | 1 failed |
| every key but the current deleted, the `osprey_service` tag not read (`laurium_at_start`) | 1 failed |
| no stale key deleted | 2 failed |
| **part 1's carried hazard:** the live factory's guard removed (a gateway already holding Laurium's key written to and its key deleted) — `test_live_factory_guard.py` | 1 failed |

**Not shown red, and why:** `services/api/app.py`'s two lines (the model wrapped by `extraction_from_env`, and
`laurium_at_start` after the model admin starts) run only in the Conduit's lifespan, which needs the stores; no
offline test reaches them. The test that fails if either is dropped is piece 7's leased live case through the
Conduit, carried to it.
