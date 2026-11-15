# v0.6.0 #18: the run API's own app role (ADR-148 Amendment 20; CARRIES row 202)

**The gap.** On Entra ID the run API admitted any app-only token of the pinned tenant, except the deployment's own
clients and, since Amendment 10, a dashboard identity. Any other application in the client's tenant could
trigger a pipeline.

**The fix** (`OspreyFlow_Core/services/api/service_identity.py`, `principal_auth.RUN_APP_ROLE`). An app-only token
is a service identity's only while its `roles` holds `OspreyFlow.Run`, an app role this API defines. Without it,
the token is refused (403) in words: "the orchestrator's application does not hold this API's OspreyFlow.Run app
role: in Entra ID, add it to the orchestrator's own registration (API permissions, this API, Application
permissions) and grant admin consent, then ask for a new token". The checks keep their order: the deployment's own
clients first, then the dashboards' role (a dashboard identity is told it is a dashboard's), then this one. A
client registered in Admin › Dashboards whose token holds no role at all is still told it is a dashboard's: the
refusal carries its client (`ServiceIdentityRefused.client`), and `get_service_identity` reads the registrations
before answering (`app.py`). Keycloak is unchanged.

**For the orchestrator** (diffs, since neither change can land on this branch):
- `registration_and_guide.diff`: platform's harness and the guide together, because §6a.2's tables are written from
  the manifest.
  - The poc manifest's API registration lists `OspreyFlow.Run` beside `Dashboard.Read`.
  - The runbook's *What it needs* says how the client's Entra administrator defines and grants the role. Its
    paragraph comes after the report sync's and is said whatever reporting renders. The orchestrator's
    registration is the client's own, not one of the deployment's counted registrations, so INSTALL's count is
    unchanged.
  - The administration guide's §6a.7 quotes the refusal. Its "Roles are not read from an Entra token" now says a
    person's roles, and names the two app roles read from an application's token. §6a.2's tables follow (2.22 on
    this main, version set at merge), and spec/10 follows the guide.
  - A new test file in the diff, `test_admin_guide_run_app_role`, ties the guide's quote to `RUN_ROLE_NOT_HELD`,
    ties the guide's and the manifest's role to `RUN_APP_ROLE`, and refuses the first draft's words. The poc
    harness test gains a case: the install says how the role is granted, with reporting on and off.
  - Applied at adabc4b, the guide, guide-copy and poc harness tests pass (255). The diff also carries the CLI
    scope's install and guide text (`../v060_cli_scope/`). There is no Terraform: the client's
    administrator makes the registrations by hand.
- `r1_proof.diff`: platform's R1.
  - Two orchestrator applications are added in the Entra stand-in, one granted `OspreyFlow.Run` and one granted
    none. Their secrets are made per run, and a state folder from before keeps its own.
  - The stand-in's test gains a case: an application granted no app role gets a token without `roles`, as Entra
    issues it.
  - `run_api_role_checks` fetches each application's token from the stand-in itself: `kubectl exec` in
    `deployment/entra-standin` posts client credentials to its own token endpoint, in the run's access-token
    version. It then asks the live Conduit `GET /v1/runs/r1-no-such-run` with each token. The granted orchestrator
    gets past the door (the Conduit's own 404, in its words: "no run this service identity triggered has that id",
    so an ingress's 404 is no pass), the unassigned one is refused in the words, and the report sync's dashboard
    identity is refused as a dashboard's.
  - A token the stand-in will not issue is a FAIL line in R1's record, not a bare exit. A stand-in started from a
    state folder before the two applications were added refuses them (700016), and the FAIL line says so: the
    in-pod script writes Entra's error and AADSTS words, and the record keeps them. Re-apply it (`entra`, or
    `platform`) before the checks.
  - The checks run last, after the domain's, and only on a release from v0.6.0 (Admin › System's version). An
    earlier release (step 6's copy A, v0.5.1) gets a SKIP line in the record. A version that cannot be read runs
    the checks, so nothing is skipped quietly.
  - `tests/test_r1_kind_domain_guard.py` drives the real `checks()` through all of this. It skips before v0.6.0,
    and runs with the stand-in's tokens on v0.6.0, on a later version and on an unreadable one. It fails when the
    run API lets the unassigned application or the dashboard identity in, refuses the granted orchestrator, or
    answers a 404 in other words; and records a token the stand-in will not issue. It holds R1's words to the
    Conduit's own constants and 404.
  - `STANDIN_TOKEN` itself runs offline too, against the real stand-in (`tests/test_r1_entra_standin.py`); only
    the `kubectl exec` hop into the pod is live alone. R1's record keeps one line a check: the refusal's first
    line, not the "command terminated" kubectl adds.
  - Applied at adabc4b, R1's driver tests pass (37 in the two changed files, 102 across R1's seven test files).
  - **The live run is pending.** It needs R1 on kind, under a lease the orchestrator queues.

**Records** (the branch's base is main 97dc544):
- `red_before_code.log`: the test file at adabc4b, run against 97dc544's code. 11 red, each at its named
  assertion: the role's name, the six shapes refused in words, the v1.0 token, and a client that is no dashboard
  with no role (let in on the base), also when the registrations answer nothing (let in) or too slowly (a 503 on the
  base, where the run role's words are now kept). The dashboard cases
  pass on the base, as they should: it already refuses a dashboard.
- `plants.py` and `plants.log`: 23 plants, each red only where it must be (the head is named in the log).
  - The Conduit's six: the role not required, compared without its case, a roles string taken for a list, the
    run role asked before the dashboards', a registered dashboard holding no role sent to grant itself it, and a
    run-role refusal turned into a 503 when the registrations cannot be read.
  - R1's eleven, with `r1_proof.diff` applied: no gate by release, skipped on every release, an unreadable version
    taken for an old one, the unassigned application let in, any answer or any 404 taken for the granted
    orchestrator, the dashboard identity let in, an unissued token exiting unrecorded, the record keeping `sh()`'s
    command instead of the refusal, the record taking every line kubectl adds, and the in-pod fetch letting a
    refusal out as a traceback.
  - The guide diff's six, with `registration_and_guide.diff` applied: the first draft's words, the manifest without
    the role, the runbook's paragraph said only with reporting on, the guide's `run` row and the install without
    `OSPREY_TOKEN_SCOPE`, and the install's scope forced to `api://<id>` whatever the ID URI.
- `tests.log`: `tests/services/api`, `tests/cli` and the poc harness test at adabc4b and at 97dc544 (with the
  branch's test files).
- A flake for platform: on 15 November one plant run at d24317e read six of `tests/test_r1_entra_standin.py`'s
  sign-in cases (`test_the_person_signed_in_is_the_one_the_hint_names[…]`, `test_an_unknown_hint_is_refused_on_entras_own_page`,
  `test_a_v1_api_registration_gets_v1_access_tokens_as_entra_issues_them`) as failed under a plant that does not
  reach their code. They passed in four reruns of their own and in every plant run since. Unreproduced; for
  platform to know of.

**Kept, and said here.**
- Whether a real Entra tenant puts a granted role in an app-only token's `roles` is not measured: no tenant of the
  client's has been asked. Install checks nothing of it (install_verify reads no `app_roles`). The first measure is
  the run API's own refusal, in words, on an ungranted orchestrator's first run. ADR-148 Amendment 20 says so.
- The CLI's `conduit_client.service_token` asks for a client-credentials token with no `scope`, which Entra
  refuses (AADSTS1002012). The orchestrator ruled it into v0.6.0 beside #18; it is fixed on this branch
  (`v060_cli_scope/`).
- CARRIES row 202 is closed by this step's merge (the orchestrator strikes it through).
