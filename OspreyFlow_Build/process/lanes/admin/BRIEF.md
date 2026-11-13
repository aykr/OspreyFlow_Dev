# Admin lane · brief refresh + pg · a refresh keeps you signed in; Small's Postgres connections (M)

Written by the orchestrator, 13 November 2026, at the owner's word ("implement all the deferred topics"), for a
**fresh admin session on `sol`**, from **main** (`git fetch`, branch `lane/admin-refresh` from `main`). Opus, medium.
Two steps, in order; each is merged on its own.

## Step 1 · A refresh keeps the person signed in and where they were (ADR-050 Amendment 3, reserved for you)

**What the owner saw on the demo (13 Nov, govuk.ospreyflow.app):** refreshing the page shows the Glass's own Sign in
screen; after signing in, the tab goes into the case it last had open, skipping Home. Both are as built: tokens are held
in memory only (`apps/workspace/src/auth/userManager.ts`, `InMemoryStorage`, ADR-050), and `App.tsx`'s bootstrap
(around lines 296–350) shows the screen unless `handoff.autoSignIn`; `initialInvestigationId()` reads the case from
the URL or session storage. CARRIES has the row.

**Build:**
1. At load, with no token in memory, the Glass first tries a **silent** sign-in against the identity provider's own
   session (`prompt=none`, the same as ADR-050 Amendment 1's renewal, `signinSilent`), and shows the Sign in screen
   only when that fails (`login_required` or any error). Tokens stay in memory only: nothing about ADR-050's storage
   choice changes. Keycloak and Entra (P10, ADR-148 Am 8) both.
2. **The place returned to is the place refreshed:** Home stays Home; a case stays that case; Admin, Studio and
   Rules and Monitoring stay themselves. Keep it in this tab's session storage the way `placeMemory.ts` keeps the
   Glass's view, and never across tabs.
3. The shared-key gate (ADR-114 Am 41/42) is in front on osprey-small: the silent round trip goes through
   `id.<host>` in a hidden frame. Check it still passes the gate with the pass cookie (Am 42 makes the pass cover
   `id.`), and say so in the amendment.

**Tests, red first (rules 12, 13, 15):**
- a refresh with a live identity-provider session lands signed in without the screen;
- a refresh with no session shows the screen with its sentence;
- a refresh on Home lands on Home; in a case, in that case; in Admin, in Admin;
- a silent failure never loops;
- the fake identity provider refuses `prompt=none` when there is no session, as Keycloak does (rule 15's "what does
  the real one refuse");
- one live case against a real Keycloak on a lane stack;
- keyboard: none new, unless the screen changes.

## Step 2 · A deployment's Postgres allows what its services hold at rest (ADR-114 Amendment 43, reserved for you)

From platform-b's stateless finding (process/lanes/platform-b/stateless/REPORT.md, CARRIES row): a deployed Small's
Postgres is rendered with no `max_connections` (default 100), and one Conduit holds 50 at rest, beside Keycloak, the
gateway's database, Superset and workers. A second Conduit replica, or a worker using the same stores, meets
`TooManyConnectionsError`. Choose with evidence: render `max_connections` from the product's own number, or bound
the Conduit's pools (`min_size=0` where idle is normal), or both. Measure the profiles (lite, small, cloud-platform's
in-cluster Postgres if any) as rendered. Red: two Conduits against the rendered Postgres, refused before, up after.
A deployed Small picks it up on `ospreyflow apply` and its next restart. Say so in the amendment.

## Rules

- Test stacks only, through `stack_lease.sh acquire admin "<purpose>" && <run>`. **osprey-small is never touched**:
  the demo lane deploys, on the orchestrator's word.
- Self-review with lane-reviewer, then the gates, then ready-to-merge for each step.
- No push. No real data.
