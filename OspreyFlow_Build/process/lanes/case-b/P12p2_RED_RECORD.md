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

## Piece 6: the cloud-platform profile presets Laurium (ADR-135 Amendment 5 decision 2, the owner's)

The orchestrator withdrew its ruling (b) on case-b's stop (an accepted owner decision), and closed the rule 11 gap
("the profile's pack" names no artefact) as a **profile default**: left unset, `laurium` on `cloud-platform`,
`deep_read` everywhere else; naming `deep_read` opts out. For Amendment 9. Platform's two fixtures name `deep_read`
(in `P12p2_platform.diff`) so its tests keep their meaning; P7b's poc fixture leaves it unset, so it renders Laurium.

- Written first: `test_left_unset_it_is_the_profiles_preset`, `test_a_cluster_translation_keeps_what_cloud_platform_chose`
  — **2 failed** against the deep_read default; green after (17 of 17), and
  `test_left_unset_cloud_platform_renders_laurium_its_preset` (the render) green.
- Found running it: `test_any_other_value_is_refused[None]` turned red (DID NOT RAISE). Correct under the new rule:
  null written out is the field left unset, so the preset. Taken out of the refused values, with that said.
- With the diff applied: the schemas, harness, CLI, cp-policy-check, engine and Laurium adapter suites, 2,160 passed;
  the one failure is `test_deployment_schema.py` reading the owner's own local `osprey.yaml`, as before.

## Piece 5: *Admin › Models* shows the extraction engine, read-only (the orchestrator's ruling (B))

Set-up only: Admin shows the engine the render chose, with "chosen at set-up: change it in osprey.yaml, then re-render
(ospreyflow start --build or the next upgrade)", and offers no change; no write route.

- **The API** (`ModelsAdminView.extraction_engine`, the schema; `Installed`'s and `view`'s two lines in
  `P12p2_platform.diff`): `tests/services/api/test_admin_models_extraction_engine.py`, written first, **5 failed**
  (`Installed` had no such field), then 7 passed; with the model admin routes and engine kinds, 135 passed.
  The access case (rule 4: an analyst refused the view) and the no-write-route case passed before and after: they are
  the existing route's rights and the absence of a route, regression guards.
- **The Glass** (`P12p2_glass_models.diff`, for platform-b: `Models.tsx`, its test, the harness and the axe list):
  `Models.test.tsx`'s new block, written first, **2 failed**, then 13 passed; `tsc` and ESLint clean. No focusable
  element added, so no keyboard case (rule 13 covers actions). **axe in all three themes** on the test server,
  offline: the Models harness's states with `cloud=1&engine=laurium` added, **40 passed**
  (`gates/fa445e5.a11y-models-harness.txt`).

## Piece 7: Laurium reads a real model's answer (leased)

Stack b, taken by case-b at 18:01:21Z on the test server, up, `remote`, down, released; beside the orchestrator's
gateway pair (LiteLLM at CI's digest with its own Postgres, keys real; Ollama with `qwen2.5:7b-instruct`, ADR-020 pin
845dbda0ea48, the product's own extraction model, and the 0.5B conformance model), torn down by the orchestrator after.
`test_laurium_reads_a_real_model_live.py` in Laurium's 3.13 environment through `laurium_live_adapter`, three runs each
its own:

| Run | qwen2.5:7b-instruct | qwen2.5:0.5b-instruct (the control) |
| --- | --- | --- |
| 2e3ec43 (`gates/2e3ec43.p12p2-live-run1-event-loop.txt`) | 2 passed, 1 failed: **"Event loop is closed" in 0.07 s**, before any model call | 3 failed, `unparseable` |
| b21d6db (`gates/b21d6db.p12p2-live-run2.txt`) | **3 passed** (about 2–12 s a call) | 3 failed, `unparseable` |

The first run's failure was the test's, not the model's: LangChain's OpenAI client caches its HTTP client across
instances, and pytest gave each test a fresh event loop, so the second met the first's closed loop. The Conduit and
Laurium's service each run one loop; the module now shares one (`loop_scope="module"`). Nothing was left on the gateway
but the orchestrator's probe key. **What is not proven:** the client's own engine (not reachable from the test server;
the orchestrator's call, 20 November). Part 1's strict xfail on the 0.5B model stays, and the control above is it.

## The lane-reviewer's round (13 findings must-fix and minor), as fixed

- **Item 3, the preset written into the stored config:** now read, never written (`OspreyConfig.extraction_engine`, a
  property; the validator records only a cloud-platform translation). Written first:
  `test_the_preset_is_read_not_written_so_a_dump_round_trips`, `test_a_shared_models_instance_is_not_changed_by_a_profile`,
  `test_the_real_cluster_translation_keeps_the_preset` (through the real `_as_cluster`): red (10 failed with the rest
  before the property), then 18 passed. **Plant** (the preset written back into `models`): 2 failed, the round trip and
  the shared instance.
- **Item 4, the key in an address:** the live factory looks for Laurium's key by its hash in `/key/list`;
  `test_live_factory_guard.py` 2 passed.
- **Item 2, every caller of `extract` sent to Laurium** (ruled: the review queue's document extraction alone, a rule 11
  gap for Amendment 9): `LauriumExtracts` sends `extract` to Laurium only inside `laurium_reads()`, set by
  `services.api.review.run_extraction` alone. `test_laurium_reads_findings_alone.py`, written first (red at
  collection), through the real `run_extraction` and store and through a direct call: 3 passed. **Plants:** the marker
  left out of `run_extraction` (`nullcontext()`), 1 failed; every caller sent to Laurium, 2 failed.
- **Items 1, 5 and 14** (`services/api/laurium_start.py`, which `app.py` now calls): the key at start never stops the
  Conduit (tried once, then in the background, each wait twice the last up to ten minutes, as `ModelAdmin.start`;
  logged in words, never the key) and Laurium's calls alone are refused in words until it is held; the composition
  inside the routes made by `routed_model`; Laurium's client closed at shutdown. `tests/services/api/test_laurium_start.py`,
  written first (red at collection), 5 passed. **Plants:** the routes inside Laurium's composition (the reversed
  wrapping), 3 failed; a key failure raised, 2 failed; Laurium's calls sent before its key is held, 1 failed; its
  client left open, 1 failed.
- **Item 9, the sweep's paging and failures untested:** `test_every_page_is_read_before_anything_is_deleted` (150 stale
  keys, two pages of 100) and `test_a_refused_list_or_delete_is_said_and_raised` (list, delete): regression guards,
  green on the code; **plants**: deleting while reading, 2 failed (the 150 keys and the refused delete); a refused
  delete passed over, 1 failed.
