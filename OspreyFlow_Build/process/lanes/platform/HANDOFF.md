# Platform lane · P3 handoff (paused by the orchestrator, 8 November 2026, about 20:56 UTC)
**Step and part.** P3 (maps administration, ADR-147), part 1 of 2: the items carried from P2's review.
Part 2, the maps work, not started (no code, no ADR-147 text). **Last commit:** 41c7ff3 (rebased on main
0e72db5). Nothing running; no stack or lease held. Reds and measurements: `P3_RED_RECORD.md`.

**Done (committed, each new test shown red):** 1 stale engine keys revoked at each reconcile
(`GatewayAdmin.revoke_stale_engine_keys`: every page of `/key/list`, delete by hash, `osprey_engine` tag only);
2 each engine key's `models` its own; 4 first `start()` guarded; minors: no key from an empty master, `local`
refused as a hosted name (schemas commit e56300a), *Test the connection* tagged `osprey:<engine>/test`,
`model_keys` closes its admin; 6 `patterns/api.ts` shows `model_limit_reached` (not ours: ratify at merge).
3 decided, not yet run live: the spend tables keep the engine key's hash (usage reads `LiteLLM_DailyTagSpend`);
`test_model_gateway_live.py`'s pg_dump case calls with the key, waits 75 s, fails if the hash is anywhere but
the four spend tables. Run it live (pinned gateway published on 127.0.0.1:54400 on a lane network).

**Next.** Item 5: append "As built in P3" to ADR-135 Amendment 3 (items 1–4, the hash decision, and why usage
counts are not an unfiltered count under rule 7: gateway call counts, no case/entity/content, behind
`manage_models`); log the hash choice under "Decisions taken". Then part 2, as planned:
- maps file `/var/lib/osprey/data/maps/maps.yaml` (replaces osprey.yaml's `map:` whole) and a separate `600`
  key file beside it on `osprey-data` (backup copies only `analytics.duckdb` from it; add maps.yaml to the set);
- `services/api/map_admin.py`, `/v1/admin/maps/*` behind `manage_geospatial`; tile proxy reads the key store;
  `MapProvider.credential_param` settles the WMTS KVP key slot (endpoint conflict already closed in
  `tile_proxy.py`; `07_BUILD_PLAN.md` phase 5 still says "Not fixed": orchestrator's file);
- prefetch areas as named boxes, a tile cap refused in words, an in-process schedule;
- Build in the Conduit: Java 21 (jlink from cached `eclipse-temurin:21-jdk`) in `services/api/Dockerfile`
  (request), jar placed by `ospreyflow map build --planetiler-jar`; set-up console's 501s call the Conduit's
  `/v1/admin/geospatial/*`; `ospreyflow map list|build|verify|prefetch` via `docker compose exec api`.

**Open question (orchestrator):** `/v1/admin/geospatial/*` check `manage_geospatial` and the `osprey-admin`
role; dropping the role check would loosen access, so not done. **Must not redo:** the two measurements, the
carried items' code and reds.
