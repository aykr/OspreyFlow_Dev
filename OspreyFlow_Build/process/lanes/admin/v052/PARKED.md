# v052-identities (ADR-148 Amendment 10) · parked 13 November 2026 at the orchestrator's word (v052-heartbeat first)

`lane/admin-v052`, from main `84c1b27`. Built and committed, each red first (records here):
- the route gate (`Principal.routes`, 403 `route_not_admitted` in `get_principal`; `test_route_gate.py`'s `KINDS`,
  which platform-b's Superset row joins) and the resolver's dashboard branch (`Dashboard.Read`, the pinned tenant,
  one GUID client neither the Glass's nor this API's, registered; built in `principal_from_claims`) — `a7ec066`;
- the store (`entra_dashboards` beside `entra_people`), Admin › Dashboards on Entra (by application id, no secret,
  `no_such_dashboard`), Keycloak refusing an application id, the store wired as the resolver's dashboard source,
  the Glass's form (the application id on Entra; the role to grant said) — this commit. The live store tests
  (`test_entra_people_live.py`, two new) are written, not yet run (they need the test server's PostgreSQL).

**Agreed with platform-b and platform** (messages, 13 Nov): REPORT_SYNC_SCOPE (`api://…/.default`), a GUID
client id when it is set; the role `Dashboard.Read`; one route gate; the exact claims read (sent to platform for
its R1 stand-in).

**Left, in order, when it resumes:**
1. The run API (`get_service_identity`) refusing a registered dashboard identity's token, and one carrying
   `Dashboard.Read` (a dashboard never submits runs); its test, red first.
2. `services/report_sync`: `REPORT_SYNC_SCOPE` sent as `scope` when set, and the client id then a GUID (the
   `osprey-dashboard-` rule kept when it is not); tests in `test_report_sync.py`, red first.
3. ADR-148 Amendment 10 written; CARRIES row 202 given one line (dashboards check their role; the run API is the
   remaining door — the orchestrator's ruling (b)).
4. Plants; the live store tests and the gates on the test server; lane review; report; ready-to-merge (no merge
   before v0.5.1's candidate).
