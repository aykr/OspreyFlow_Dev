# L2.9 plan · four places, Rules and Monitoring, `/alerts/<id>`, the way back

Working from: ADR-145 decisions 1–3 and Amendments 1 and 4 (decision 1); ADR-146 decisions 2 and 6 and
Amendment 1; ADR-112 Amendment 5; ADR-124 Amendment 17; ADR-132 Amendments 5 and 6; ADR-144 decision 4 and
Amendment 2 (case lane, L3.2b, not yet on main); spec 02's shell sections.

## Tests first (each shown red by a plant at the real call site)

1. `tests/services/api/test_place_routes.py` (the switcher test, ADR-145 Amendment 4):
   - a fourth place, `rules`, in `PLACE_ORDER`; R&M's routes placed in it (`PLACE_RULES`);
   - every route of the place carries the place gate (`require_rules_place`: `triage_alerts` or
     `author_rules`), red with the gate removed from one real route (hiding alone must not pass);
   - each role is offered exactly ADR-146 decision 2's places; every route of a hidden R&M refuses
     the Data Engineer, the Administrator and the Reports Viewer, over HTTP;
   - the two reads Home also makes (the queue list, the held rows list) named with their reason.
2. `tests/services/api/test_alert_address.py` (ADR-146 decision 6, rule 3): `GET /v1/alerts/{id}`
   answers an unreadable alert (another case; evidence hidden; a case the reader is not a member of)
   with the same status and body as a missing one; red with the case check skipped and with the
   evidence check skipped.
3. The jump's case-of-its-own gone: `POST …/alerts/{id}/jump` answers 404/405.
4. Workspace: `shell/router.test.ts` (the address parsed and pushed; Back returns); `places.test.tsx`
   held to `placesByRole.json`; `RulesPlace.test.tsx` (tabs Alerts, What raises alerts, Held rows,
   Changes); Home's row opens `/alerts/<id>`; the count on the switcher's *Rules and Monitoring*;
   *Open the evidence* then *← Back to the alert* returns to the same alert, still open.
5. Keyboard (rule 13): `keyboard/shell.spec.ts` (the fourth place, its count, Home opens the alert)
   and `keyboard/rules-place.spec.ts` (each tab, open an alert, *Open the evidence*, the way back);
   registry ids sent as a diff. Axe in dark, light and GOV.UK for the place and its tabs.

## Files

- Conduit: `services/api/rules_place.py` (new, the gate); `services/api/app.py` (the gate on R&M's
  routes, `GET /v1/alerts/{alert_id}`, the jump removed); `services/api/watch_routes.py`.
- Schemas (own commit at the head): `AlertAtAddress` in `packages/schemas`, and generated TS.
- Workspace: `shell/places.json`, `places.ts`, `PlaceSwitcher.tsx`, `ContextBanner.tsx`,
  `placesByRole.json`, `shell/router.ts` (new, a small history-API router, no dependency);
  `alerts/RulesPlace.tsx` (replacing `AlertsPlace.tsx`), `alerts/AlertAddress.tsx`; `home/*`;
  `App.tsx` (ratify: shared with case); Connection strength stays in the Glass under ⋯ More.
- Item 4 (*Open the evidence*) is built on L3.2b's lens once it is on main.
