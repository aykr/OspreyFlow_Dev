# admin · refresh (Step 1 of BRIEF.md) · report (13 November 2026): a refresh keeps the person signed in and where they were

`lane/admin-refresh` over main `fa5d988`, gated at `6c691e8` (tree `635aef59`). ADR-050 Amendment 3 (written). Reviewed by
my lane-reviewer at `8657a4b` (13 findings) and twice by the orchestrator (`8657a4b`, `4f31898`); every must closed, each
with its red. Step 2 (Postgres connections, ADR-114 Am 43) is on its own branch, `lane/admin-pg`, not part of this merge.

| Exit criterion (brief) | Met | Proving test (records in `gates/`) |
| --- | --- | --- |
| Live IdP session → signed in, no screen | yes | `keyboard/refresh-sign-in.spec.ts` (real App, real `oidc-client-ts` frame); `App.test.tsx`; red on e1f15e4 |
| No session → the screen with its sentence | yes | spec: no session, and each of `login_required`/`interaction_required`/`consent_required`; red with a fake that grants |
| Home stays Home; a case that case; Admin Admin | yes | spec (Admin; kept Admin without rights → Home); `App.test.tsx` (Home with a case open; the case's workspace; a refused case → Home; a case switch over a full-page sign-in); `refreshPlace.test.ts` |
| A silent failure never loops | yes | `signInAtLoad.test.ts` (red without the memo); spec asks once |
| The fake refuses `prompt=none` with no session, as Keycloak does | yes | spec's fake (iss, state, PKCE, redirect_uri, code once; each refusal red-planted) |
| One live case against a real Keycloak | yes, on a throwaway Keycloak 26.0 (no lane stack carries one) | `test_refresh_silent_sign_in_keycloak.py`, the library's captured request; green + plant |
| The shared-key gate passes the round | at the HTTP level only | `test_refresh_silent_round_through_the_key.py` through Caddy 2.11.4, red with `Domain=` dropped; browser frame behaviour unmeasured (Am 3 says so) |
| Keyboard | none new | the Sign in screen is unchanged |

**Gates at `6c691e8`:** spec 30/30 (ten cases × 3), unpiped. `make test`: pytest 13,031 passed, 8 failed — the server's GPU
case (known), six `test_lanes_groups.py` cases and `test_doc_citations_check.py`, all from main's own platform-b files
(new steps not in `groups.tsv`; `ci4/committed-osprey-yaml.md` citing `OspreyFlow_Build/scripts/lanes_launch.sh`), none touched here;
test-js 3,257 passed, MatrixView's first-frame budget failed (known). `make -k ci`: exit 2 on `citation-check` alone (the
same citation). Records: `gates/6c691e8.{test,ci}.txt`.

**Decisions taken** (Prompt L): 10 s timeout for the round at load (the bundle is warm; the person faces a blank page);
`from`/`view`/`investigation` stripped after a silent sign-in, as the redirect's return to the root did (the case stays,
from session storage); only views the landing check corrects are restored; the live Keycloak case on a throwaway container
under `offline`, since no lane stack carries Keycloak; the waits after the round 15 s (the frame loads the dev server's
whole bundle; Home past 5 s in 1 of 20 server runs); the Caddy and Keycloak cases import platform-b's fixtures (a shared
fixture is a CARRIES row for after this merge).

**Commits:** `git log --oneline fa5d988..6c691e8` (13). **Requests:** none open (RDS and the shared fixture are CARRIES rows).
**Questions for the owner:** none. **Still running:** nothing. The orchestrator's socket in PROMPT_L.md (`8906`) is stale;
`6964` answered.
