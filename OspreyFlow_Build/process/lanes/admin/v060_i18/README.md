# v0.6.0 #18: the run API's own app role (ADR-148 Amendment 20; CARRIES row 202)

**The gap.** On Entra ID the run API admitted any app-only token of the pinned tenant, except the deployment's own
clients and, since Amendment 10, a dashboard identity. Any other application in the client's tenant could
trigger a pipeline.

**The fix** (`OspreyFlow_Core/services/api/service_identity.py`, `principal_auth.RUN_APP_ROLE`). An app-only token
is a service identity's only while its `roles` holds `OspreyFlow.Run`, an app role this API defines. Without it,
the token is refused (403) in words: "the orchestrator's application does not hold this API's OspreyFlow.Run app
role: in Entra ID, assign it to the application (the API's registration, App roles), then sign in again". The
dashboards' role and the deployment's own clients are refused as before. Keycloak is unchanged.

**For the orchestrator** (diffs: neither change can land on this branch):
- `registration_and_guide.diff`, platform's harness and the guide together, because §6a.2's tables are written from
  the manifest:
  - the poc manifest's API registration lists `OspreyFlow.Run` beside `Dashboard.Read`;
  - the runbook's *What it needs* says how the client's Entra administrator defines and grants it;
  - the administration guide's §6a.7 says it with the refusal's words, §6a.2's tables follow (2.22 on this main, version set at
    merge), and spec/10 follows the guide.
  The orchestrator's application is the client's own, not a registration of the deployment's, so INSTALL's count is
  unchanged. Applied, the harness and guide tests pass (112). There is no Terraform: the client's administrator
  makes the registrations by hand.
- `r1_proof.diff`, platform's R1. Two orchestrator applications are added in the Entra stand-in, one granted
  `OspreyFlow.Run` and one granted none, with their secrets made per run (a state folder from before keeps its own).
  - The stand-in's test gains a case: an application granted no app role gets a token without `roles`, as Entra
    issues it.
  - `run_api_role_checks` runs on the live Conduit on kind, asking `GET /v1/runs/<none>` with each token: the granted
    orchestrator is admitted (past its door, a 404), the other is refused in the words, and the report sync's
    dashboard identity and the Glass's client are refused.
  - Applied, the stand-in tests pass (44). The live checks need R1 on kind, under a lease the orchestrator queues.

**Records:**
- `red_before_code.log`: the test file against the base 7dd860e's code, 8 red.
- `plants.py` and `plants.log`: 3 plants, each red only where it must be.
- `tests.log`: `tests/services/api`, `tests/cli` and the poc harness test on the branch and on the base.

**Kept, and said here.**
- Proving that the client's real tenant assigns the role stays one check, at install.
- install_verify checks no `app_roles` (the stand-in enforces its own registrations), so that check is the run
  API's refusal itself, or R1's.
