# Slice CO3 · CO3 · Live updates through the page service: it forwards the WebSocket upgrade with the bearer kept on the server (ADR-152 X2)

- **Build id:** CO3
- **Dial setting:** balanced
- **Rounds limit:** 4
- **After:** PL3 (the page service, OspreyFlow_Core/apps/pages, must be on main)
- **Status of this brief:** written by the conductor on 19 November 2026 under the owner's standing approval (his word for the
  night: CO3 first, as soon as PL3 merges), from ADR-152 decision 5 and the X2 row of decision 11 and a scout of the same day. The
  plan's id is kept from when this was thought a Conduit route: **there is no Conduit change.**

## What

The Glass opens its live stream in two steps (OspreyFlow_Core/apps/workspace/src/App.tsx about lines 1472-1513): it mints a
single-use ticket (POST /v1/ws-ticket with its bearer) and opens GET /v1/investigations/{id}/stream?ticket=... The Conduit's only
WebSocket route is that stream (OspreyFlow_Core/services/api/app.py about lines 21551-21580), authenticated in
`_authenticate_websocket` (about lines 21269-21302): an "authorization: Bearer" header first, else the query parameter `ticket`,
else refused ("missing bearer token or ws-ticket"); a bearer in the URL is ignored and so refused; a refused credential closes
1008, an unavailable store 1013. It checks no Origin (CORS does not gate a WebSocket). The page service holds the person's tokens
on the server (PL3's session) and must therefore be the one that opens the socket to the Conduit. This slice adds that proxy to
OspreyFlow_Core/apps/pages, and nothing else.

Choices the ADR leaves open, **settled by the conductor** (the owner is told afterwards):
1. **The path** the page service exposes: the same as the Conduit's, GET /v1/investigations/{id}/stream, upgraded only on that
   path (any other upgrade path is refused 404 before upgrading).
2. **How the upgrade carries the person:** the browser's upgrade carries the page service's session cookie (PL3). The service
   loads the session; with none, or an ended one, the upgrade is refused 401 **before** it upgrades and the Conduit is not
   contacted. With one, the service opens its own WebSocket to the Conduit with the person's access token as an
   "Authorization: Bearer" header (the Conduit tries the header first; no ticket is minted). **Nothing the browser sent is
   forwarded**: not its cookie, not its Authorization, not its query string (the forwarded URL is the path alone).
3. **Origin:** the upgrade's Origin header must equal the deployment's own origin, a new setting `OSPREY_PAGES_PUBLIC_ORIGIN`
   (scheme, host and port; no trailing slash). A different Origin, or none, is refused 403 before upgrading. The proxy is mounted
   **only when** `OSPREY_PAGES_CONDUIT_URL` (the Conduit's address, for example http://api:8000) is set; with it set and no public
   origin the service refuses to start, in words. With it unset, the upgrade path answers 404 (PL3's tests stay valid).
4. **Idle and end of session:** the socket closes after `OSPREY_PAGES_STREAM_IDLE_SECONDS` (default 3600, the proxy's hour) with
   no frame in either direction, and when the person's session ends (its idle or absolute lifetime): both sides close 1008.
5. **Upstream closes are relayed as they are** (1008, 1013 and the reason text) to the browser; an upstream that cannot be
   reached closes the browser's socket 1013 ("try again later"). Frames, text and binary, pass both ways unchanged.
6. **The library:** `ws` (MIT; the workspace app already has it as a dev dependency) as a runtime dependency of apps/pages; no
   proxy package. It must pass the licence check and be entered in OspreyFlow_Build/spec/00_ARCHITECTURE.md section 7 before use.

Binding: process/CLAUDE.md rules 3, 4, 7, 11, 12, 15; spec/06_DECISIONS.md ADR-152 decision 5 (about lines 40835-40841) and the X2
row (about line 40965); the secret rules in PL3's brief still hold (no token in any response, log or output).

## Acceptance test

One new Vitest file, OspreyFlow_Core/apps/pages/test/server/stream.test.ts, using a fake Conduit WebSocket server built with `ws`
that **records** what it receives (the request URL, every header, each frame) and **refuses what the real Conduit refuses**
(rule 15): no Authorization header and no ticket: close 1008 "missing bearer token or ws-ticket"; a bad token: 1008; a
`token` in the URL: ignored, so refused as missing. It holds the three tests ADR-152 names, with these exact names, plus the cases
under them:

- `test_the_stream_through_pages_carries_only_what_the_person_may_read`: the pure half. With a session, the fake Conduit receives
  exactly one connection, with "Authorization: Bearer <that session's access token>", the path alone (no query), and **no**
  Cookie header and nothing else the browser sent; text and binary frames pass both ways; an upstream close 1008 (and 1013) reaches
  the browser with its code and reason; two people's sessions reach their own tokens, never each other's. With no session or an
  ended one: 401 and the fake Conduit sees **no connection at all**. The Conduit's own filtering of what a person may read is
  proved against the real Conduit, which this slice cannot start: **that live proof is owed** (a backlog row, once the page
  service is wired into a deployment); say so in the test's comment.
- `test_an_upgrade_from_another_origin_is_refused_by_pages`: another origin, a near-miss (same host, another port; another scheme;
  a trailing path) and no Origin: each 403, the fake Conduit sees no connection; the deployment's own origin: upgraded (control).
- `test_a_bearer_in_the_url_is_still_refused_through_pages`: a signed token as `?token=` or `?access_token=` or `?ticket=` with no
  session: 401, no upstream connection; with a session: upgraded, and the fake Conduit's recorded URL has no query string and the
  URL's token appears nowhere in what it received (plant: a proxy that forwards the query would fail this).
- also: an upgrade on another path: 404; the proxy absent when `OSPREY_PAGES_CONDUIT_URL` is unset; the idle timeout and a session
  that ends mid-stream close both sides 1008 (use a controllable clock); the service refuses to start in words with the Conduit
  address set and no public origin; the access token appears in no log, stdout or stderr of the service (a generated sentinel
  token, rule 15).

Plant the violation in the shape the code meets at its real call site: a real HTTP upgrade request through the app's server (a `ws`
client with a Cookie header and an Origin), not a call to a helper.

## Checks

Pure only. The **checks command** runs the existing page-service Vitest files (the new file excluded), the neighbours
(OspreyFlow_Build/tests/harness/test_dockerfiles_numeric_user.py, test_service_inventory.py) and the licence check. The
**acceptance command** runs the new file alone (the rest of the folder is green on main, so it could not be red there). The line adds every mapped pure test that
scans a folder the slice changes.

## Round 2 (19 November 2026): what the first verifier found, and the conductor's ruling

The round-1 verifier found one fault in behaviour and one gap in a test at tip 3cdad3f5fc. Fix those and nothing else.

**The ruling: choice 5 above is amended.** The real Conduit sends every refusal on the stream **before** it accepts the socket
(OspreyFlow_Core/services/api/app.py about lines 21563-21598, the close before `websocket.accept()`), and under uvicorn that reaches
a client as HTTP 403 with **no close code and no reason**. So a refused credential (1008) and an unavailable principal store
(1013, "try again later") cannot be told apart by the page service, and the brief's "relay 1013 as it is" cannot hold for them.
The Conduit is not changed (ADR-152 X2: no Conduit change). The rule is now:
1. An upstream handshake answered 401 or 403 (a refusal before accept): the browser's socket closes **1008**, reason "the
   Conduit refused the connection". This is what the Glass gets today through nginx. Record in the code and in the test header that a
   store outage looks the same, and why.
2. A close **after** accept (the stream running): its code and reason are relayed as they are, 1008 and 1013 included.
3. An upstream that cannot be reached or times out: 1013 to the browser, as before.
4. The Conduit accepting then closing (so the code survives the handshake) is a backlog row for the owner, not this slice's.

**The gap: the fake Conduit must refuse as the real one does** (rule 15). Its default refusal is the real shape: the handshake
answered HTTP 403 with no body, no code and no reason, for a missing or bad credential and for a store that is down, and the
tests assert the browser receives 1008 with the reason above in both. Keep one case where the fake accepts and then closes with a
code and reason (1008, 1013), asserting they are relayed unchanged, labelled as the running-stream case. Delete any test or comment
that claims a Conduit refusal arrives as a close code with a reason.

## Out of scope

The /v1 HTTP forwarding of the page service and its anti-forgery handling (no slice yet); the real sign-in; the render, compose,
front proxy and Helm wiring; the CI image job; any change to the Conduit, the Glass or the Makefile. If the Conduit turns out to need
a change for this to work, stop and say.
