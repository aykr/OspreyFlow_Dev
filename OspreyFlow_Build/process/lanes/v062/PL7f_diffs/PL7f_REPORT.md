# Slice PL7f, round 1: report

## Round 2 (the conductor, 24 November 2026)

1. **The Caddy test did not run in this session's gate.** The conductor's message says the switch was lifted
   (`no-local-stacks` renamed `no-local-stacks.off`), but on this Mac, at the time of the last run, `~/.ospreyflow/` holds
   `no-local-stacks` (empty, dated 9 November) and no `.off` file, so the guard still refuses and the test failed in its own
   words (42 errors in the Caddy file; everything else green). The image `caddy:2.11.4-alpine` is present. I did not point
   `OSPREY_LEASE_DIR` elsewhere to get round the switch (that is the owner's decision), and I did not rename his file. An
   earlier line here that said "43 passed" was a run made by hand with `OSPREY_LEASE_DIR` on an empty folder (section 1); it
   is not a gate result. When the switch file is gone, the file needs no change.
2. The override variable is renamed `OSPREY_CADDY_BINARY` (test, messages, docstring, this report, the README).
   `make test-file-coverage-check`: "1279 test file(s), 0 allowlisted, no new drift." The round-1 diff that wired the test
   as live-service (an `--ignore` in `ci.yml` and a Makefile hunk) is **withdrawn**; `PL7f_CI_YML.diff` keeps only the
   GitHub step that runs the test in the proxy job. Nothing else changed.

## 1. The decision that is the owner's (found building, not in the table)

**On this Mac the real-Caddy test cannot run in the gate.** The owner's per-machine switch of 9 November 2026
(`~/.ospreyflow/no-local-stacks`, held here) makes the repository's Docker guard (`tests/local_docker_guard.py`) skip
every test that calls the docker CLI, in its own words: "a server-only test". The server has no container tooling. So
under the guard no merge passes through the real Caddy, which is what the owner's condition of 23 November asks.
The guard is not mine to loosen (an exemption is the owner's). What the test does, so it never skips quietly: it asks
the switch first and **fails in words** where it is held (and no Caddy 2.11 binary is given in `OSPREY_CADDY_BINARY`), so on
this Mac the gate is red on that one file until he decides. Options, recommendation first:

1. **Exempt this one test's one command in the guard** (`docker run --rm --network none`, three read-only mounts, the
   pinned image; no stack, no port, no volume, no network): the guard names the test, and the test runs on every merge.
2. Run the merge gate with `OSPREY_LEASE_DIR` pointing at a folder with no switch, for this file alone.
3. Leave the switch as it is and accept that the real Caddy runs on GitHub only (`access-key-proxy-test`), which is
   not the owner's condition.

I ran the test by hand with `OSPREY_LEASE_DIR` set to an empty folder (a hermetic `docker run --rm --network none`, no
stack touched; the owner's containers were not touched): **43 passed**. Results in section 4.

## 2. What is built

| Part | Where | What |
| --- | --- | --- |
| One place | `OspreyFlow_Core/harness/page_addresses.py` (new, 504 lines, about 140 of them prose) | `derive(config)` returns a `PageAddresses` (public origin without its default port, identity, issuer, alias, identity port, extra listener, the proxy's own HTTPS port, trust, and the three sign-in variables by `sign_in()`), a `Refusal` (key and words; `.error()` is the typed error), or `None` (setting off). `require` raises. Each refusal is a function of its own (`_on_cloud_platform`, `_origin_problem`, `_needs_https`, `_port_taken`, `_needs_trust`, `_needs_ca`), in that order. |
| The ports | `OspreyFlow_Core/harness/site.py` | `proxy_ports(config)`: the one list of what the compose proxy uses (container port, host port, words, compose spelling). The compose file's `ports` are built from it; `derive` refuses an origin on any entry but the proxy's own HTTPS port. `PLAIN_HTTP_PORTS` (80, 8080): plain HTTP in some shape, refused in every shape (case 19). |
| Table | `OspreyFlow_Build/tests/fixtures/page_addresses_cases.json` | 50 rows for cases 1 to 19 and one "off" row. |
| Python | `tests/harness/test_page_addresses.py` (+ `page_addresses_fixtures.py`, shared) | the table against `derive`, the render's refusals, the rendered files, the real `config.ts` through node, a scan that no other module computes an address, and the planted faults. |
| Node | `OspreyFlow_Core/apps/pages/test/server/pageAddresses.test.ts` | below. |
| Caddy | `tests/harness/test_page_addresses_caddy.py` | below. |

**Lines.** `pages_service.py` 483 to 147: **362 lines removed**, 26 added (its exceptions, words, `service_accepts_issuer`,
`origin_problem`, `caddy_signs_itself`, `identity_listener_port`, `identity_alias`, `refuse_*`, `CA_IN_SERVICE` are gone;
`service_environment` copies what `derive` returns). `site.py`: 89 added, 23 removed (`identity_listener_port` call,
`_own_certificate_service`'s ports and the three port branches of `proxy_service` replaced by `proxy_ports`).
`render.py` 20/16 (the alias, the trust mount and the sign-in flag read `derive`'s object), `cloud_platform/__init__.py`
2/2. `test_pages_setting.py` 81/56: round 8's stand-in `_page_service_refuses` is deleted (it asks the real `config.ts`
through node); the patched functions moved to `harness.page_addresses`; and the rows the owner's table changes (below).

**How the node test calls `config.ts`.** vitest reads `apps/pages/server/config.ts` as it is (no build, no `tsx`) and
calls the exported `loadConfig`, which runs `publicOrigin()`, `oidcSettings()` and `addressSetting` (not exported, and not
re-implemented). It finds the table in whichever sibling of `OspreyFlow_Core` holds it (Core may not name the Build
folder: `test_core_stands_alone.py`), fails in words if the monorepo has no table, and skips only outside the monorepo.
It is shown red inside itself (a `:443` on the origin, an upper-case host, a plain-HTTP issuer, a path, a user name, an
issuer that is no address), and by hand against a table row planted with `:443` (4 tests fail, with config.ts's own
words). The Python test also runs the real `loadConfig` through node (`--experimental-strip-types`) on every
rendered environment.

**Folders each test walks (for the scan-map row).**
`test_page_addresses.py`: reads `OspreyFlow_Build/tests/fixtures/page_addresses_cases.json`; imports
`OspreyFlow_Core/harness/` and `OspreyFlow_Core/packages/schemas/`; runs `OspreyFlow_Core/apps/pages/server/config.ts`
(node); reads, as text, the top-level `*.py` of `OspreyFlow_Core/harness/` and `harness/cloud_platform/__init__.py` (no
recursion); writes only to `tmp_path`. `test_page_addresses_caddy.py`: the same table and renderers and `PROXY_IMAGE`;
writes a Caddyfile per case, a self-made certificate and the shared-key file under `tmp_path`; runs the image.
`pageAddresses.test.ts`: the table and `config.ts`. **It is an ordinary test for `tools/test_file_coverage_check.py`**
(round 2: its binary override is `OSPREY_CADDY_BINARY`, not an `OSPREY_TEST_*` variable), so it runs in `make test`.

## 3. The table, case by case (what `derive` returns; what the real Caddy said)

"Real Caddy" is `caddy validate` of the rendered Caddyfile under each brand (derived rows), or of the Caddyfile the render
would write **with the refusal taken out** (refused rows: the pure round-9 plant at the shape the render writes).

| Row | Configuration | derive returns | Real Caddy (ospreyflow / govuk) |
| --- | --- | --- | --- |
| 1-lite-plain-http (case 1) | local-lite, `http://reference.ospreyflow.localhost:8081` | **refuse** `needs_https` | - |
| 1-small-plain-http (case 1) | small, `http://osprey.example.org:8081` | **refuse** `schema` | - |
| 2-lite-https-localhost (case 2) | local-lite, `https://reference.ospreyflow.localhost:8443` | **refuse** `needs_trust` | - |
| 3-acme-default-port (case 3) | small, `https://osprey.example.org` | origin `https://osprey.example.org`; issuer `https://id.osprey.example.org/realms/osprey`; alias `id.osprey.example.org`; port 443; extra listener None; trust none | valid / valid |
| 4-own-certificate-with-ca (case 4) | small, `https://osprey.example.org`, own certificate with ca | origin `https://osprey.example.org`; issuer `https://id.osprey.example.org/realms/osprey`; alias `id.osprey.example.org`; port 443; extra listener 443; trust `/etc/ssl/organisation-ca.pem` | valid / valid |
| 5-own-certificate-no-ca-private-authority (case 5) | small, `https://osprey.intra.example.gov.uk`, own certificate no ca | **refuse** `needs_ca` | - |
| 6-own-certificate-no-ca-internal (case 6) | small, `https://osprey.internal`, own certificate no ca | **refuse** `needs_ca` | - |
| 6-own-certificate-no-ca-local-port (case 6) | small, `https://osprey.local:9443`, own certificate no ca | **refuse** `needs_ca` | - |
| 6-own-certificate-no-ca-home-arpa (case 6) | small, `https://osprey.home.arpa`, own certificate no ca | **refuse** `needs_ca` | - |
| 6-own-certificate-no-ca-localhost (case 6) | small, `https://localhost`, own certificate no ca | **refuse** `needs_ca` | - |
| 6-own-certificate-no-ca-ip (case 6) | small, `https://10.1.2.3`, own certificate no ca | **refuse** `needs_origin` | - |
| 7-acme-explicit-443 (case 7) | small, `https://osprey.example.org:443` | origin `https://osprey.example.org`; issuer `https://id.osprey.example.org/realms/osprey`; alias `id.osprey.example.org`; port 443; extra listener None; trust none | valid / valid |
| 7-own-certificate-explicit-443 (case 7) | small, `https://osprey.example.org:443`, own certificate with ca | origin `https://osprey.example.org`; issuer `https://id.osprey.example.org/realms/osprey`; alias `id.osprey.example.org`; port 443; extra listener 443; trust `/etc/ssl/organisation-ca.pem` | valid / valid |
| 8-lite-plain-http-explicit-80 (case 8) | local-lite, `http://reference.ospreyflow.localhost:80` | **refuse** `needs_https` | - |
| 9-own-certificate-8080 (case 9) | small, `https://osprey.example.org:8080`, own certificate with ca | **refuse** `port_taken` | refusal out: REFUSED (Error: adapting config using caddyfile: server block 1, key 1 (https:/...) |
| 10-own-certificate-8443 (case 10) | small, `https://osprey.example.org:8443`, own certificate with ca | origin `https://osprey.example.org:8443`; issuer `https://id.osprey.example.org:8443/realms/osprey`; alias `id.osprey.example.org`; port 8443; extra listener None; trust `/etc/ssl/organisation-ca.pem` | valid / valid |
| 11-own-certificate-9443 (case 11) | small, `https://osprey.example.org:9443`, own certificate with ca | origin `https://osprey.example.org:9443`; issuer `https://id.osprey.example.org:9443/realms/osprey`; alias `id.osprey.example.org`; port 9443; extra listener 9443; trust `/etc/ssl/organisation-ca.pem` | valid / valid |
| 11-acme-9443 (case 11) | small, `https://osprey.example.org:9443` | origin `https://osprey.example.org:9443`; issuer `https://id.osprey.example.org:9443/realms/osprey`; alias `id.osprey.example.org`; port 9443; extra listener 9443; trust none | valid / valid |
| 12-own-certificate-graph-store-door (case 12) | small, `https://osprey.example.org:2480`, own certificate with ca | **refuse** `port_taken` | refusal out: REFUSED (Error: adapting config using caddyfile: server listening on [:2480] is...) |
| 12-own-certificate-conduit-door (case 12) | small, `https://osprey.example.org:8000`, own certificate with ca, Conduit door exposed | **refuse** `port_taken` | refusal out: REFUSED (Error: adapting config using caddyfile: server listening on [:8000] is...) |
| 12-own-certificate-conduit-door-not-exposed (case 12) | small, `https://osprey.example.org:8000`, own certificate with ca | origin `https://osprey.example.org:8000`; issuer `https://id.osprey.example.org:8000/realms/osprey`; alias `id.osprey.example.org`; port 8000; extra listener 8000; trust `/etc/ssl/organisation-ca.pem` | valid / valid |
| 12-own-certificate-redirect-port (case 12) | small, `https://osprey.example.org:80`, own certificate with ca, redirect | **refuse** `port_taken` | refusal out: valid |
| 12-acme-plain-http-port (case 12) | small, `https://osprey.example.org:80` | **refuse** `port_taken` | refusal out: REFUSED (Error: adapting config using caddyfile: server block 1, key 1 (https:/...) |
| 12-acme-graph-store-door (case 12) | small, `https://osprey.example.org:2480` | **refuse** `port_taken` | refusal out: REFUSED (Error: adapting config using caddyfile: server listening on [:2480] is...) |
| 12-acme-conduit-door (case 12) | small, `https://osprey.example.org:8000`, Conduit door exposed | **refuse** `port_taken` | refusal out: REFUSED (Error: adapting config using caddyfile: server listening on [:8000] is...) |
| 12-acme-conduit-door-not-exposed (case 12) | small, `https://osprey.example.org:8000` | origin `https://osprey.example.org:8000`; issuer `https://id.osprey.example.org:8000/realms/osprey`; alias `id.osprey.example.org`; port 8000; extra listener 8000; trust none | valid / valid |
| 12-acme-own-https-port-8443 (case 12) | small, `https://osprey.example.org:8443` | origin `https://osprey.example.org:8443`; issuer `https://id.osprey.example.org:8443/realms/osprey`; alias `id.osprey.example.org`; port 8443; extra listener 8443; trust none | valid / valid |
| 13-path (case 13) | small, `https://osprey.example.org/app` | **refuse** `needs_origin` | - |
| 13-query (case 13) | small, `https://osprey.example.org?x=1` | **refuse** `needs_origin` | - |
| 13-fragment (case 13) | small, `https://osprey.example.org#x` | **refuse** `needs_origin` | - |
| 13-userinfo (case 13) | small, `https://user:pw@osprey.example.org` | **refuse** `needs_origin` | - |
| 13-trailing-slash (case 13) | small, `https://osprey.example.org/` | **refuse** `schema` | - |
| 14-upper-case-host (case 14) | small, `https://OSPREY.Example.ORG` | origin `https://osprey.example.org`; issuer `https://id.osprey.example.org/realms/osprey`; alias `id.osprey.example.org`; port 443; extra listener None; trust none | valid / valid |
| 14-ipv6-bracketed-port (case 14) | small, `https://[::1]:8443` | **refuse** `needs_origin` | - |
| 14-ipv6-bracketed (case 14) | small, `https://[2001:db8::1]` | **refuse** `needs_origin` | - |
| 14-ipv4 (case 14) | small, `https://10.1.2.3` | **refuse** `needs_origin` | - |
| 14-ipv4-port (case 14) | small, `https://10.1.2.3:9443` | **refuse** `needs_origin` | - |
| 15-access-key-acme (case 15) | small, `https://osprey.example.org`, shared key | origin `https://osprey.example.org`; issuer `https://id.osprey.example.org/realms/osprey`; alias `id.osprey.example.org`; port 443; extra listener None; trust none | valid / valid |
| 15-access-key-own-certificate (case 15) | small, `https://osprey.example.org:9443`, own certificate with ca, shared key | origin `https://osprey.example.org:9443`; issuer `https://id.osprey.example.org:9443/realms/osprey`; alias `id.osprey.example.org`; port 9443; extra listener 9443; trust `/etc/ssl/organisation-ca.pem` | valid / valid |
| 16-cluster-default-port (case 16) | cluster, `https://osprey.example.org` | origin `https://osprey.example.org`; issuer `https://id.osprey.example.org/realms/osprey`; alias `id.osprey.example.org`; port 443; extra listener None; trust none | valid / valid |
| 16-cluster-9443 (case 16) | cluster, `https://osprey.example.org:9443` | origin `https://osprey.example.org:9443`; issuer `https://id.osprey.example.org:9443/realms/osprey`; alias `id.osprey.example.org`; port 9443; extra listener None; trust none | valid / valid |
| 16-cluster-explicit-443 (case 16) | cluster, `https://osprey.example.org:443` | origin `https://osprey.example.org`; issuer `https://id.osprey.example.org/realms/osprey`; alias `id.osprey.example.org`; port 443; extra listener None; trust none | valid / valid |
| 16-cluster-ip (case 16) | cluster, `https://10.1.2.3` | **refuse** `needs_origin` | - |
| 17-cloud-platform (case 17) | cloud-platform, `https://osprey.example.org` | **refuse** `cloud_platform` | - |
| 17-cloud-platform-poc (case 17) | cloud-platform-poc, `https://osprey.example.org` | **refuse** `cloud_platform` | - |
| 18-govuk-cutover-setting-off (case 18) | small, `https://osprey.example.org` | **refuse** `cutover` | - |
| 19-acme-8080 (case 19) | small, `https://osprey.example.org:8080` | **refuse** `port_taken` | refusal out: valid |
| 19-own-certificate-8080 (case 19) | small, `https://osprey.example.org:8080`, own certificate with ca | **refuse** `port_taken` | - |
| 19-own-certificate-no-ca-8080 (case 19) | small, `https://osprey.example.org:8080`, own certificate no ca | **refuse** `port_taken` | - |
| 0-off (case 0) | small, `https://osprey.example.org:443` | nothing (setting off) | - |

Readings of the table that the owner should confirm (none is a guess about sign-in; each is a refusal or a value):

* **Case 4** says "listener port the proxy's own HTTPS port (8443)". I return both: `proxy_https_port` 8443 and an
  **extra listener 443** (the issuer carries the origin's default port, the alias reaches the proxy at 443, and nothing
  listens there with an own certificate unless the extra listener is added: measured on 23 November in PL7a2b round 5).
* **Case 6, the IP address row**: refused by case 14's rule first (an IP is no name), so its key is `needs_origin`, not
  `needs_ca`. Both name `pages.enabled`.
* **Case 8 and case 1 (small)**: a Small cannot be plain HTTP (the schema refuses it before the page service is asked), so
  case 8 is a local-lite row; the small plain-HTTP row is the schema's refusal.
* **Case 16**: a cluster always has a managed cache (the schema refuses a cluster without `external.valkey`), so there is
  no "without a managed cache" configuration; the rows are the cluster as the schema allows it. A cluster has no
  alias, no extra listener and no doors, so no port can clash.
* **Case 19 with ACME, and case 12 with the plain-HTTP port in every shape.** Port 80 and 8080 are refused whichever
  certificate the deployment has. The real Caddy **accepts** two of those Caddyfiles (ACME on 8080, own certificate on 80
  with the redirect): the refusals are the owner's policy, not Caddy's, and the Caddy test says so. Two origins the old
  tests rendered (own certificate on 80, ACME on 8080) are now refused, and `test_pages_setting.py` says so.
* **Case 12, host-side**: the redirect's published port 80 beside an own certificate is refused (Docker would publish it
  twice); the list is `proxy_ports`'s, so a port added there is covered at once.
* **Case 13, trailing slash**: refused by the schema (with the setting off too, as before); the other four by `derive`.

## 4. Where the real Caddy ran, and what it said

The Mac, by hand, with the guard's switch folder pointed at an empty folder (section 1): the image `caddy:2.11.4-alpine`,
`--network none`, one container for all 48 Caddyfiles, in about 17 seconds for the whole file.
**All 32 derived Caddyfiles (16 derived rows, both brands) load ("Valid configuration").**
**Red first**: with `_port_taken` taken out, the render writes the round-9 Caddyfile and the real Caddy **refuses six
of eight**, for the clash it was built to refuse: own certificate on 8080 ("scheme and port violate convention", the
round-9 case), the graph store's and the Conduit's doors beside either shape ("server listening on [:2480] is configured
for HTTPS and cannot natively multiplex HTTP and HTTPS: http://:2480"), ACME on port 80. The same deployments with the
setting off load. It loads the other two (policy rows above). The pure model of the clash finds the same six and none in a
Caddyfile the real Caddy loads. **Where it runs:** the Mac's gate (once the owner decides section 1); GitHub's
`access-key-proxy-test` job as a second place (diff, section 5); the server runs no containers, so it lists the file as
not run, never as passed.

## 5. Diffs for the owner (none applied): `README.md` beside this file

`PL7f_ADR152_AM5.diff` (Amendment 5 text and its reservation row); `PL7f_CI_YML.diff` (the GitHub step that runs the Caddy
test in `access-key-proxy-test`; not needed for the merge gate, and `make test-file-coverage-check` is clean without it).

## 6. The text

`spec/05_DEPLOYMENT.md` section 2.8 says what is derived and refused, cites the owner's ruling of 24 November 2026, and says
`derive` is the only place. The release note (`CHANGELOG.md`), and the setting's description (so the generated guide
appendix and both guide copies) say the setting exists, is off and is not for use. **Nothing says "available"**, and no
guide line names the page service as turned on.

## 7. Checks run

Acceptance: `vitest run pageAddresses` 22 passed; `test_page_addresses.py` 182 passed, 1 skipped (the cutover row runs
only under its own brand). Checks: `npm test --workspace apps/pages` 718 passed; the six pytest files 1120 passed, 1 skipped
(with the Caddy file run by hand as in section 1); `ruff check .` clean; `make design-check` clean; `make schemas-check`,
`citation-check`, `client-name-check` clean; the guide tests 122 passed. The whole of `tests/harness`, `tests/schemas`
and `test_core_stands_alone.py` ran with one failure, the schema drift gate, caused by my own edit of the setting's
description before I regenerated the types, and green after.

## Round 2, the verifier's findings (sign-in: the owner's)

**1. The realm client.** `realm.pages_client` now takes its origin from `derive` (`derived.public_origin` where the setting is
on; `sites(config).glass` where it is off, which is the same one normaliser, `page_addresses.parse_origin`). Redirect, web
origin and post-logout address are made from it. Case 7 registers `https://osprey.example.org/session/callback`; case 14
registers the lower-case origin. Every place under `harness/` that touches `public_origin`, with whether it reads `derive`:
`page_addresses.py` (makes it); `pages_service.py:133` (copies `derived.public_origin`); `realm.py` `pages_client` (reads
`derive`, above); `register_sign_in.py:277` (calls `pages_client(config)`, so reads `derive`; its own `origin` at :260 is
Superset's, from `SUPERSET_PUBLIC_ORIGIN`); `site.py` `sites()` (builds every address from `page_addresses.parse_origin`,
`identity_name`, `dashboards_name` and `address`, so Keycloak's `KC_HOSTNAME` at `render.py:1253` and the Caddyfile's identity
site are the same strings as the service's, and a default port is written nowhere); `cloud_platform/__init__.py:172` (an https
check, no address); `webapp.py:402` (a placeholder value for a preview); `tls_check.py` (advice text); `site.py:92` (a header
comment).

**2. The tests.** `test_no_other_module_computes_an_address` now walks every module under `harness/` (the folder and its
sub-folders) and looks for the raw setting and for `id.`/`bi.` names, not only for the variable names: each hit is listed in
`ORIGIN_TOUCHES_ALLOWED` with its reason, and a listing that no longer matches a line fails. The `:443` stripping is gone from
`test_the_derived_identity_is_the_address_the_deployment_already_names`. `test_keycloaks_issuer_the_realm_client_and_the_service_agree`
compares, per table row, the issuer Keycloak will publish (from its rendered `KC_HOSTNAME`), the realm client's redirect, web
origin and post-logout address, and the page service's settings, as strings. Red first (commit `e1fede0`): the verifier's
cases 7 and 14 against the client as it was, Keycloak given a port the service is not, and a planted change to `derive`'s
`public_origin` that turns a case red; each fails for the stated reason.

**3. Case 7 stays derived, and why no measurement was needed.** The origin `https://host:443` is normalised once to
`https://host`, and Keycloak is given `https://id.host` with no port: the same string as case 3 (an origin written without the
port), which the deployment already serves. The issuer is therefore equal by construction on both sides, and no claim is made
about what Keycloak would publish if it were handed `:443`, because it never is. If the owner prefers case 7 refused again
(the conductor's fallback), it is one refusal in `derive` and the rows 7 and 8 flipped in the table. Backlog line, for the
conductor: measure against a real Keycloak whether a hostname written with `:443` publishes `:443` in `iss`, so the deployment
can say whether a written default port may ever be passed through.
