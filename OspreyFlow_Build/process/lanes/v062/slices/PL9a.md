# Slice PL9a · PL9 · A real sign-in for the page service, Keycloak first: the round trip, the session on the server, the page service's own client in the realm (ADR-152 decision 5)

- **Build id:** PL9 (new build, the owner's word of 20 November 2026: "a real sign-in for the page service: the round trip, the session on the server, the
  page service's own client in the realm, sign-out and renewal"). Cut in two so each fits four rounds: **PL9a** (this: Keycloak; the round trip; local sign-out;
  the realm client and its secrets) and **PL9b** (renewal, sign-out on the identity provider's side, and the Entra registration, which needs CO2).
- **Dial setting:** balanced
- **Rounds limit:** 4
- **After:** nothing (PL3 is on main). Runs beside PL4 and PL10. Touches no workspace file.
- **Status of this brief:** written by the conductor on 20 November 2026 under the owner's standing approval, from a read-only scout of the same day.
  The open choices are **settled by the conductor** below; the owner is told afterwards. **Every page build needs this one and PL10 (the /v1 forwarder).**

## What

`OspreyFlow_Core/apps/pages` has the session shell from PL3 (a signed cookie, a Valkey store with idle and absolute lifetimes, a synchroniser CSRF token,
`POST /session/sign-out`) and a one-shot identity seam (`server/identity.ts`: `signIn({query})`) whose only implementation, `unconfiguredProvider`, always throws, so
sign-in answers `503`. This slice builds the real code flow for the Keycloak realm. Read `identity.ts`, `app.ts` (about lines 85-130), `sessionPolicy.ts`, `sessionStore.ts`,
`expressStore.ts`, `config.ts`, `start.ts` and `test/support/` first; read the Glass's own flow in `apps/workspace/src/auth` (`userManager.ts`, `oidcConfig.ts`) for the realm's
claims and the audience, and `harness/realm.py`, `harness/keycloak_admin.py`, `harness/register_sign_in.py`, `harness/oidc.py`, `scripts/apply`'s secret minting
(`harness/apply.py`) and `OspreyFlow_Build/tests/harness/fake_idp.py`, `test_oidc.py`, `test_realm.py`, `test_register_sign_in.py`.

Choices, **settled by the conductor**:
1. **Paths:** `GET /session/sign-in` (exists) becomes the start: it redirects to the identity provider; `GET /session/callback` is new; `POST /session/sign-out` stays
   local in this slice (destroys the pages session and clears the cookie; the provider-side logout is PL9b). The redirect URI is `OSPREY_PAGES_PUBLIC_ORIGIN` plus
   `/session/callback`, exact-matched by the provider.
2. **The flow:** authorisation code with **PKCE S256**, **state** and **nonce**, as a **confidential** client (the client secret sent at the token endpoint). Library:
   `openid-client` (ADR-152 decision 2 names it; a hand-written flow is not allowed). It must pass `make licence-check` (tools `licence_check.py` and `.mjs`) and be entered in
   `OspreyFlow_Build/spec/00_ARCHITECTURE.md` section 7 **before** it is installed; if its licence does not pass, **stop and say**. Scope `openid`. The ID token is verified
   (signature through the realm's JWKS, `iss`, `aud` = the client id, `nonce`, `exp`). The access token is kept as the bearer (the Conduit verifies its audience `osprey-conduit`;
   no Conduit change is needed for Keycloak: the scout read `principal_auth` and it checks `aud` and `iss`, never `azp`).
3. **Before a session exists (login CSRF):** the start stores `{state, nonce, verifier, returnTo}` server-side in Valkey under a new key prefix (e.g. `pages-login:`), single
   use, TTL 10 minutes, and sets a short-lived signed `HttpOnly; Secure; SameSite=Lax` cookie holding only the random id of that record. The callback must present the
   cookie, the record must exist, `state` must match, and the record is deleted when read (a second use of the same callback is refused). `returnTo` is a path inside the
   application only (a leading single `/`, no `//`, no scheme, no backslash); anything else is dropped.
4. **The callback (a GET: CSRF does not apply, `state` does the work):** on success it regenerates the session id (as PL3's sign-in does), saves the session record
   (`SessionRecord`, with the refresh token kept in it for PL9b; never logged), clears the login cookie and redirects to `returnTo` or `/`. A new error class beside
   `IdentityProviderUnavailable`: `IdentityProviderRefused` (an `invalid_grant`, a state or nonce mismatch, a wrong audience, a missing code, the provider's `error=`
   on the callback): answered `403` with words that change nothing about the person's access ("Sign-in was refused. Nothing about your access has changed.") and **never** the
   provider's text. `IdentityProviderUnavailable` stays `503`.
5. **Settings** (`config.ts`; the service refuses to start in words and never prints a secret): `OSPREY_PAGES_OIDC_ISSUER` (an `https` URL, or `http` only for a loopback test
   address), `OSPREY_PAGES_CLIENT_ID` (default `osprey-pages`), `OSPREY_PAGES_CLIENT_SECRET` (a `Secret` like the session secret: at least 32 characters, redacted everywhere).
   **Unset all three:** sign-in stays unconfigured (503), as PL3 behaves and its tests expect. **Set some but not all:** refuse to start, in words naming what is missing.
   The secret rules are the owner's: no value committed anywhere (examples, compose files, fixtures), tests generate their own at run time, never printed.
6. **The realm's client** (`harness/realm.py`): a confidential client `osprey-pages` (`publicClient` false, standard flow only, S256 required, refresh tokens on, redirect URI
   `<origin>/session/callback`, post-logout redirect `<origin>/`), with the same mappers as the Glass's client and the **audience mapper for `osprey-conduit`** (the docstring
   says every client whose tokens the Conduit accepts needs it). It is registered on existing realms by `harness/register_sign_in.py` beside the Glass and Superset. **The
   client secret and `OSPREY_PAGES_SESSION_SECRET` are minted by `apply`** (`token_urlsafe(32)` as the Superset's is; `harness/apply.py`'s keep-existing rule already keeps
   a name ending in `_SECRET` across re-applies) and written to `deployment.env` (mode 600) by name only in the rendered output. **The GOV.UK demo is protected:** this change must
   add only the client and the keys, and change nothing else in what an existing deployment renders; say in your report exactly what an existing deployment would gain on its next
   apply; the owner decides whether it is applied there.
7. **Not in this slice (PL9b):** token renewal and the refused-refresh behaviour, the provider-side logout (back-channel and front-channel), the Entra registration (it needs
   CO2, which is not on main), `kc_idp_hint`, the sign-in page's GOV.UK assets row.

Binding: process/CLAUDE.md rules 3, 4, 11, 12, 15; spec/06_DECISIONS.md ADR-152 decisions 2, 4, 5 and X1, ADR-044 and ADR-050 Amendment 4; the PL3 brief's secret rules; British English.
If something here turns out to need a Conduit change, **stop and say**.

## Acceptance test

Two new files: `OspreyFlow_Core/apps/pages/test/server/oidc.test.ts` and `OspreyFlow_Build/tests/harness/test_realm_pages_client.py` (the test the ADR names). The page service is
tested against a **fake identity provider that refuses what the real Keycloak refuses** (rule 15): extend `OspreyFlow_Build/tests/harness/fake_idp.py` (the pages tests can
start it or use a TypeScript twin of the same rules; do not weaken the existing Python users): **client authentication** (a wrong or missing secret at the token endpoint: `401
invalid_client`, as `tests/conftest.py` already models at about lines 152-190 with a comment recording the real refusal), a **code that is single use even when the first try
was wrong, and expires**, a wrong `redirect_uri` at authorise and at the token endpoint, a missing or wrong PKCE verifier, and a **real signed JWT access token** with `aud`
`osprey-conduit` (not an opaque string). Cases, each red first for its own reason, at the real call site (real HTTP requests through the app's server):
- the full round trip: start redirects with `state`, `nonce`, a `code_challenge` (S256) and the exact redirect URI; the callback creates a session, the session id changes, the
  cookie is `HttpOnly; Secure; SameSite=Lax`, the access token is in the server's store and **nowhere** in any response, header, cookie, log or error (generated sentinels);
- refused, each with the fake untouched afterwards where it applies, **no session created**, `403` in the fixed words: wrong or reused `state`; no login cookie; a login cookie
  from another browser; a second use of the same callback; a nonce mismatch; an ID token with the wrong `iss`, `aud`, signature or `exp`; the provider's `error=access_denied`;
  a wrong client secret (the fake's `401`); an expired code; a `returnTo` of `//evil.example`, `https://evil.example` and `/\evil` is dropped to `/`;
- the provider unreachable: `503`, nothing changed; sign-out destroys the session and the cookie (the CSRF check still guards it);
- config: unset all three settings leaves sign-in at 503; some set: the service refuses to start in words naming the missing setting; a secret under 32 characters refused; no value printed;
- the realm test: the `osprey-pages` client is confidential, S256, has the exact redirect URIs and the audience mapper (plant: the mapper removed: the test goes red), `register_sign_in`
  registers it on an existing realm and is idempotent, `apply` mints both secrets once and keeps them across a second apply (planted: a re-apply that re-mints), and no secret value
  is written anywhere but `deployment.env`.
State in each file's header which test fails if the flow returns the wrong thing (rule 12).

## Checks

Pure only. The **checks command** runs the existing page-service Vitest files (the new one excluded), `tests/harness/test_oidc.py`, `test_realm.py`, `test_register_sign_in.py`,
`test_dockerfiles_numeric_user.py`, `test_service_inventory.py` and the licence check. The **acceptance command** runs the two new files. **Owed to a live stack:** a real Keycloak
round trip with `osprey-pages` (the code exchange with the secret; the audience the Conduit accepts). Never `test_apply_env`.

## Out of scope

Everything in item 7; the /v1 forwarder (PL10); any workspace file; rendering `pages` into any deployment (PL7); the Conduit; the Makefile and `ci.yml`. The `apps/pages` fixed
secret-shaped string owed from PL3 is in PL10's scope, not this one.
