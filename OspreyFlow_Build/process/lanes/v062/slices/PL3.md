# Slice PL3 · PL3 · The empty server-rendered application: its pure core (session, headers, anti-forgery, who is signed in) as a Node service (ADR-152 R1)

- **Build id:** PL3
- **Dial setting:** balanced
- **Rounds limit:** 4
- **After:** nothing (BL4, ADR-152, is on main)
- **Status of this brief:** written by the conductor on 19 November 2026 under the owner's standing approval and his word of
  that day to start stage 3, from ADR-152 and a scout of the same day. The plan's PL3 reads "the empty server-rendered
  application, as a Node service in every deployment: sign-in, session, security headers (R1)". ADR-152 does not itself say
  what R1 holds ("R1 to R8 of the parallel front-end specification, sized by the build session"; that specification is not in the
  repository), so this brief sizes it: **this slice is the part that is pure-testable.** What is left out, and why, is under "Out of
  scope"; the owner numbers the rest.

## What

A new Node service, `pages`, at OspreyFlow_Core/apps/pages (ADR-152 decision 3's layout: server/, modules/, tree-default/,
tree-govuk/, test/; this slice makes server/ and test/ only). Express, Nunjucks, helmet, Vitest; no React, nothing fetched from
another address (ADR-152 decision 3, about lines 40777-40788). It starts, answers a health check, holds a server-side session,
sends the security headers, refuses a state-changing request without its anti-forgery token, and serves one server-rendered page
that says who is signed in. The identity provider is an **interface** in this slice, with a fake in the tests; the real
authorization-code exchange is not here.

1. **The session** (ADR-152 decision 4, about lines 40797-40808; ADR-050 Amendment 4, about lines 41125-41144). The person's
   tokens live on the server only, in Valkey under the service's own key prefix and database number, **every key with a
   TTL**; the browser holds one opaque identifier in one cookie: HttpOnly, Secure, SameSite=Lax, no Domain. No token appears in any
   response body, header or cookie but that opaque identifier (the refresh token never leaves the server). Choices the ADR
   leaves open, **settled by the conductor** (the owner is told afterwards): the identifier is 32 random bytes, base64url;
   the cookie's name is `osprey_pages`; the key prefix is `pages-session:`; the database number comes from
   `OSPREY_PAGES_VALKEY_DB`, default 1 (the Conduit's is 0); idle lifetime **one hour**, sliding (the ADR: the proxy's hour), absolute
   lifetime **eight hours**, each key's TTL never longer than either and never longer than the identity provider's session;
   a record past its absolute lifetime is refused and deleted. A session store module with one interface and two
   implementations: Valkey (`ioredis`-compatible client, or the one the scout's choice of package list says is allowed; every
   package passes `make licence-check` and is entered in OspreyFlow_Build/spec/00_ARCHITECTURE.md section 7 before use) and an
   in-memory one **that refuses what Valkey refuses** (rule 15, CLAUDE.md): a write with no TTL, a key without the prefix, a
   value over the limit.
2. **The security policy on every response** (ADR-152 decision 6, about lines 40876-40882): default-src 'self'; script-src and
   style-src 'self' plus a per-response nonce; img-src 'self' data:; worker-src 'self'; connect-src 'self'; frame-src 'none';
   frame-ancestors 'none'; object-src 'none'; base-uri 'self'; form-action 'self'. **No** unsafe-inline, **no** unsafe-eval, no
   inline style attribute, no Superset exception. Also (conductor's choice): X-Content-Type-Options nosniff, Referrer-Policy
   same-origin, Cross-Origin-Opener-Policy same-origin, and **no HSTS from this service** (the front proxy terminates TLS and
   owns it).
3. **Anti-forgery** (ADR-152 decision 5, about lines 40812-40814). A state-changing request (POST, PUT, PATCH, DELETE) with no valid
   token for its session is refused 403 in words; GET, HEAD and OPTIONS are not. The mechanism (the ADR leaves it open) is a
   **synchroniser token** held in the session, sent in the form field `_csrf` or the header `X-CSRF-Token`, compared in constant time.
4. **One page**: GET / with no session answers 302 to /session/sign-in; with a session it renders, by Nunjucks and with
   scripts off working, the person's display name and nothing else from the session. A route /session/sign-in that, with the
   fake provider, starts a session; a route /session/sign-out that ends it (POST, with its token). A health route /healthz
   (no session, no secrets, no Conduit call).
5. **The image and the inventory.** OspreyFlow_Core/apps/pages/Dockerfile: a numeric non-root user (`USER 10001:10001`), a
   multi-stage build on the Node version the workspace image pins, EXPOSE **8090** (the conductor's choice: the Conduit is 8000,
   the workspace 8080, the identity-provider tests 8081 and 8082), a health check. A row for it in
   OspreyFlow_Core/harness/service_inventory.py (every folder under apps/ is inventoried: test_service_inventory.py). The
   Dockerfile satisfies the numeric-user test and the cloud-platform policy check as they stand. **Not wired into the render
   or the compose output in this slice** (see Out of scope).
6. **The citation allowlist.** ADR-152 says each slice removes its own lines when it writes the file it names
   (OspreyFlow_Build/tests/fixtures/citation_allowlist.txt, its header, and the entries for the apps/pages/test/server files
   and the tests/glass_trees files). This slice removes only the lines for files it writes (apps/pages/test/server/session.test.ts
   and csrf.test.ts if it writes them under those names); no other change to that file.

Binding: process/CLAUDE.md rules 3, 4, 7, 11, 12, 15; spec/06_DECISIONS.md ADR-152 (decisions 3, 4, 5, 6, about lines 40717-41254);
ADR-050 Amendment 4; spec/02_GLASS_FRONTEND.md for the Glass's own conventions (British English in copy).

## Acceptance test

New Vitest files under OspreyFlow_Core/apps/pages/test/server (they become the acceptance files; each red today because the
service does not exist, and each failing for the reason it names once the folder exists, not for a missing import or fixture):

- OspreyFlow_Core/apps/pages/test/server/session.test.ts: a session is created with a TTL on every key (plant: a store call with
  no TTL is refused by the in-memory store, as Valkey's configuration would make it a leak); the cookie is HttpOnly, Secure,
  SameSite=Lax with no Domain; **no token** appears in any response body, header or cookie but the opaque identifier (plant a
  sentinel token in the session and request every route); a record past its idle or absolute lifetime is refused and gone;
  the sign-out deletes the key and clears the cookie.
- OspreyFlow_Core/apps/pages/test/server/csrf.test.ts: each of POST, PUT, PATCH, DELETE without a token, with another
  session's token, and with an empty token: refused 403; with the session's own token: accepted; GET, HEAD and OPTIONS need
  none (control).
- OspreyFlow_Core/apps/pages/test/server/headers.test.ts: the policy's exact directive list on the page, the health route and a
  404; no unsafe-inline, no unsafe-eval, a fresh nonce on each response and the same nonce in the policy and on the page's
  script tag; the other three headers; no Strict-Transport-Security.
- OspreyFlow_Core/apps/pages/test/server/page.test.ts: no session: 302 to the sign-in route; with a session: the display name,
  and nothing else of the session in the body; works with scripts off (no script tag the page needs); health answers with no
  session.

Plant the violation in the shape the code meets at its real call site (rule 15, second paragraph): the request as Express receives
it (a cookie header, a method, an Origin), the store through its interface with the Valkey-shaped refusals, the page through the
real app factory and an HTTP client (supertest or Node's own), not through a helper.

## Checks

Pure only (no store, no network): the acceptance files above, run from OspreyFlow_Core/apps/pages; and the neighbours a new
service touches (ports 9): OspreyFlow_Build/tests/harness/test_dockerfiles_numeric_user.py, test_service_inventory.py,
test_helm_chart.py and OspreyFlow_Build/tests/cp_policy_check/test_cp_policy_check.py. The line adds every mapped pure test that
scans a folder the slice changes. Also `make licence-check` from OspreyFlow_Build, and the citation check.

## Out of scope (each needs the owner's ruling or a deployment; the owner numbers the follow-ons)

- **The real sign-in**: the authorization-code with PKCE exchange against Keycloak and Entra ID (openid-client), single sign-on,
  sign-out at the identity provider, the "cannot reach the provider is not access revoked" wording; and the Keycloak realm's
  `osprey-pages` client with its test (ADR-152 names tests/harness/test_realm_pages_client.py). These need a real identity
  provider to prove (rule 15: a fake that only grants proves nothing): **live tests, owed** while the live step is off.
- **Wiring into the deployment**: the render's images list and compose service, the front proxy's path routes (ADR-152 wants
  paths on one origin; today's Caddy table routes by host: a front-proxy design change that touches every deployment, the
  GOV.UK demo's among them), the Helm values, the cloud-platform shape (ADR-148 Amendment 23), the local-lite 16 GB measurement.
- **The CI job** that builds and scans the pages image (a change to the CI workflow: a patch for the owner, not a slice).
- **The proxy to the Conduit** (/v1 and the WebSocket with the bearer added on the server) and its tests (ADR-152 X2).
- Any page beyond the one above; the GOV.UK and default trees; the shared package (PL4). Do not touch the Glass, the Conduit,
  the Makefile or the CI workflow.
- **If npm cannot reach its registry** in the builder's environment, stop and say: do not vendor a package by hand.
