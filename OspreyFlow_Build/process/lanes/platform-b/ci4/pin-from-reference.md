# A digest-pinned reference locked from itself (the orchestrator's hardening after run 43413711132), 13 November 2026

Branch `lane/platform-b-pin`, from main 8176f38.

- `harness/render.py` `_render_versions_lock`: when a reference has the form `name@sha256:…`, the
  digest is taken from the reference and the row records `source: reference`; the resolver is never
  called for it. A reference by tag goes through the resolver as before, and is refused by name
  (`UnpinnedImagesError`) when it can't be resolved.
- Spec: `05_DEPLOYMENT.md` (the paragraph on `daemon_then_registry_digest_resolver`), the one place
  the lookup is described. No ADR names it: ADR-114 and ADR-111 don't mention the resolver or the
  lock's `source` values, so no reservation is needed. Nothing in Core reads the `source` of a lock
  row, so no reader needed changing.

## Red then green (`tests/harness/test_render.py`; the resolver stubbed as run 43413711132 met it:
## every ghcr.io lookup fails, every other one answers)

| Case | main 8176f38 | branch |
| --- | --- | --- |
| `test_a_reference_pinned_by_digest_is_locked_from_the_reference_never_the_registry` (litellm, speaches on ghcr.io, and ollama) | red: `UnpinnedImagesError` naming litellm@sha256 and speaches@sha256, CI's own refusal | green |
| `test_an_unpinned_reference_the_registry_cannot_resolve_is_still_refused` (pull mode: `ghcr.io/ospreyflow/<service>:<sha>`) | refused (the `raises` holds); the exact-set check is red only because the refusal also names the two pinned references | green: refused, and exactly the four unpinned ones named |

The refusal is proven both before and after the change. Three label cases and two refusal cases
expected every third-party row to carry the resolver's label, or to appear in the refusal; they now
leave out the pinned rows, and the compose/lock cross-check expects `reference` exactly where the
compose file's reference names that digest.

## The suites

- `tests/harness/` on the branch: 1546 passed, 1 failed, 2 errors. The failure is
  `test_deployment_schema.py::test_the_committed_osprey_yaml_still_validates`, because the committed
  `OspreyFlow_Core/osprey.yaml` names `osm-local-great-britain`. The two errors are
  `test_restore_drawn_layer.py`, which needs a stack on the closed ports. All three are the same on
  main 8176f38 (1 failed, 59 passed, 2 errors), so none is this change's.
- Every other test that imports the renderer, the bundle, `harness.images` or `cloud_platform`:
  807 passed, 1 failed. The failure is `test_monitoring_settings.py`, which needs Postgres on the
  closed port 59992.
- All runs with the ports pinned closed and no stack.
