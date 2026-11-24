# Slice PL7f · PL7 · The page service's addresses are derived in one place, and the front proxy's Caddyfile is validated by the real Caddy on every merge (the table of cases approved by the owner on 24 November 2026 with three changes, now in it; every finding that names sign-in, a certificate or a key is his)

- **Build id:** PL7 (ADR-152 Amendment 3, decisions 4 and 7; the owner's rulings of 23 November 2026). **Why it exists:** PL7a2b went nine rounds and stopped on a family of faults, "sign-in cannot work and the render does not say so": the page service's issuer, public origin, identity listener, alias and trust were each worked out in a different place, and each round found a new place two of them disagreed. Round 8: the origin `https://host:443` is refused by the service (`config.ts` wants the origin alone). Round 9: with the own certificate and an origin on port 8080 the identity listener clashes with the proxy's plain-HTTP health port and Caddy refuses to load the Caddyfile, so **the deployment's only door does not start**.
- **Dial setting:** balanced
- **Rounds limit:** the dial's (8)
- **After:** PL7a2b (merged), **before PL7d**. **The owner's ruling of 24 November 2026 (in chat): "PL7f: the table is approved with three changes: case 14 refuses IP and bracketed origins outright; add a case for an HTTPS origin on the proxy's plain-HTTP port, refused; case 12 covers every port the proxy publishes. Then cut its row and start it. Every finding naming sign-in, a certificate or a key is mine."** The three changes are in the table below (cases 12, 14 and 19).
- **Release blocker (the owner, 23 November 2026): until PL7f has merged, no release ships; `pages.enabled` is not turned on for the demo or any deployment of his; no guide or release note describes the setting as available.** (Recorded in `BACKLOG.md`, "Release blockers", and `RULINGS.md`.)
- **Every finding in this part that names sign-in, a certificate or a key is the owner's.**

## What (in this order; each red first, planted faults at the shape the code really sees: rule 15)

0. **The specification first (CLAUDE.md rule 11: the rulings fill a gap, so the spec says them).** Write the derivation rules (the table below: what is derived, what is refused and why) into `OspreyFlow_Build/spec/05_DEPLOYMENT.md` in a short section on the page service's addresses, **citing the owner's ruling of 24 November 2026**, and say in the section that `derive` is the only place that computes them. If a rule needs a decision-record amendment (ADR-152 Amendment 3 or the deployment decisions), **write the amendment text as a diff for the owner and do not apply it** (`spec/06_DECISIONS.md` amendments are approved by diff).
1. **One place derives every address.** `OspreyFlow_Core/harness/page_addresses.py` (new): `derive(config)` returns the page service's **issuer, public origin (default port removed), identity alias, the identity listener's port, the trust variable and the three sign-in variables, or a refusal in plain words.** **It is the only code that computes any of them.** The page-service render module (`pages_service`) and the proxy's (`site`) module (the Caddyfile and the proxy's published ports) and the cloud-platform renderer **read the derived object and compute none of it.** The refusals that live in `pages_service.py` today (plain HTTP, the own certificate's trust, the cloud-platform shape, a default port, the cutover without the setting) move into `derive` and keep their words. **Nothing in the Caddyfile, the compose file or the chart names a port, a host or an alias that `derive` did not return.**
2. **One table of cases, read by both sides.** `OspreyFlow_Build/tests/fixtures/page_addresses_cases.json` (the table below, one row per case: the configuration and the derived values or the refusal's key words). **The Python tests and a node test both read it.** The node test runs **the page service's own checks in `apps/pages/server/config.ts`** (`publicOrigin()`, `oidcSettings()` and `addressSetting`) on every derived value, by calling the real functions, **not a stand-in**: a value the real service refuses fails the node test. **Delete `_page_service_refuses` (round 8's stand-in) or make it read this table.**
3. **The real Caddy validates every case's Caddyfile.** Each case's rendered front-proxy configuration is run through `caddy validate` (Caddy 2.11, the image the deployment uses: `caddy:2.11.4-alpine`). **Where it runs, so every merge passes through it (the owner's condition, 23 November):**
   - **The Mac's gate** has Docker and the image (`caddy:2.11.4-alpine` is on the Mac), but **no `caddy` binary** on its path, and `OspreyFlow_Build/tests/harness/access_key_proxy_fixtures.py` **skips in words** when it finds none (`NEEDS_CADDY`), so today the real Caddy runs on **no** merge. **This part's validation test runs the image** (`docker run --rm --network none -v <folder>:/etc/caddy:ro caddy:2.11.4-alpine caddy validate --config /etc/caddy/Caddyfile`, or the binary taken once from the image) **and must not skip on the Mac: if neither a binary nor the image can be run, it fails in words** (it is not marked as skippable; say how you kept the repository's Docker guard satisfied).
   - **GitHub** already has the image's Caddy in its `access-key-proxy-test` job (`.github/workflows/ci.yml`, "Take the proxy image's own Caddy"); GitHub is no merge gate (the release's), so it is a second place, not the one. A diff for the owner adds this part's test to that job's command (the workflow is a protected file: write the diff, do not apply it).
   - **The server** has no container tooling (its runs list the container-needing checks as "not run"): it is not a place. The test is listed there as not run, never as passed.
   - **The pure model of the port clash stays as a fast check, never alone.** **Red first:** a planted Caddyfile with the round-9 clash (an HTTPS identity site on the port the catch-all serves plain HTTP) fails the real Caddy.
4. **The cases below, each rendered, each shown red against a planted fault at the shape `derive` returns, each green after.**
5. **The text:** a short line in the guide where the page service is named, **only when the owner says the setting is available** (it is not, until this part has merged and he has said so). The part does **not** write "available" anywhere; where PL7a2b's release-note paragraph and guide sentence say the setting turns the page service on, **reword them** to say it exists, is off, and is not for use (the owner's condition 1).
6. **Report:** the derived values per case in a table; how the node test calls `config.ts`; which place runs the real Caddy and what it said on each case; what changed in `pages_service.py` and `site.py` (lines removed, not only added).

## The table of cases (for the owner to read before a builder starts)

Each row is an input and what `derive` returns. "Refuse" means a plain-words refusal naming `pages.enabled` and the cause, and no render. "Derived" means the values the service and the proxy are given. **Every derived value passes `config.ts`; every derived Caddyfile passes `caddy validate`.**

| # | The deployment | What `derive` returns | Raised in |
| --- | --- | --- | --- |
| 1 | local-lite, `public_origin` plain HTTP (a `.localhost` name) | **Refuse:** the identity address is neither https nor loopback; serve it over HTTPS or leave `pages.enabled` off | PL7a2b rounds 1, 3 |
| 2 | local-lite over HTTPS on a `.localhost` name (Caddy's internal authority), no trust given | **Refuse:** no trust for the proxy's own authority | round 4 |
| 3 | small, ACME public name, default port | Derived: issuer `https://id.<host>/realms/osprey`, origin without a port, alias `id.<host>` on the proxy inside `osprey`, listener 443, no extra trust | rounds 2, 4 |
| 4 | small, own certificate with `ca`, public name, default port | Derived: as 3, listener port the proxy's own HTTPS port (8443) in the container, `NODE_EXTRA_CA_CERTS` the CA | round 4 |
| 5 | small, own certificate **without** `ca`, an ordinary name (a private authority) | **Refuse:** the page service has no trust for the certificate | rounds 6, 7 |
| 6 | small, own certificate without `ca`, a `.internal`, `.local` or `.home.arpa` name, `localhost` or an IP address | **Refuse** (as 5) | round 6 |
| 7 | small, `public_origin` with an explicit default port (`https://host:443`) | Derived: the origin **without** `:443` (the service refuses `raw !== new URL(raw).origin`) | **round 8** |
| 8 | small, `public_origin` an explicit `:80` on plain HTTP | **Refuse** (as 1; and the origin without `:80`) | round 8 |
| 9 | small, own certificate, origin port **8080** | **Refuse:** the identity listener would clash with the proxy's plain-HTTP port (Caddy would not load the file) | **round 9** |
| 10 | small, own certificate, origin port 8443 (the proxy's own HTTPS port) | Derived: no extra listener | round 5 |
| 11 | small, own certificate, origin port 9443 | Derived: an extra identity listener on 9443, no clash | round 5 |
| 12 | small, origin port equal to **any port the proxy publishes** other than its own HTTPS port (the plain-HTTP port, the loopback doors the proxy publishes such as the graph store's and the Conduit's when exposed, and every other published port: `derive` takes the list from the one place that publishes them, so a port added there is covered at once) | **Refuse:** the port is taken | round 9's family; the owner, 24 November |
| 13 | small, `public_origin` with a path, a trailing slash, a query, a fragment or userinfo | **Refuse** (the schema or `derive`, one place, in words) | rounds 1, 8 |
| 14 | small, an upper-case host: Derived in the form `new URL(...).origin` gives (lower case). **A bracketed origin (IPv6) or an IP address origin: refuse outright**, in plain words (the identity address needs a name a certificate can carry) | round 8's family; **the owner, 24 November: "refuses IP and bracketed origins outright"** |
| 15 | small with the shared key (`network.access_key`) | Derived: the page service's routes sit **inside** the key's `route`; none reachable without the key; the identity alias and the issuer fetch are on the key's open list | round 7 (a security rule: the owner's) |
| 16 | cluster without a managed cache | as small (3 to 14) | round 2 |
| 17 | cloud-platform, the setting on | **Refuse:** the cloud-platform shape has no page-service sign-in until PL7e | the owner, 23 November |
| 18 | a GOV.UK deployment whose tree is complete, the setting off | **Refuse** (the existing words) | PL7a2b |
| 19 | small, **an HTTPS origin on the proxy's plain-HTTP port** (for example `https://host:8080`), with any certificate shape (ACME, own certificate with or without `ca`) | **Refuse:** the plain-HTTP port serves HTTP; an HTTPS identity site there cannot be reached (and Caddy would not load the file) | **the owner, 24 November** (case 9 is this case for the own certificate; this one covers every shape) |

**The cases the table cannot settle alone** (the part says so in its report): whether the node test can call `config.ts` without a build (a small entry with `tsx` or the built output), and the Docker guard for the real Caddy.

## Acceptance test

`OspreyFlow_Build/tests/harness/test_page_addresses.py` (new, pure, red first) reading the table; the node test `OspreyFlow_Core/apps/pages/test/server/pageAddresses.test.ts` (new, vitest) reading the same table; and the real-Caddy test `OspreyFlow_Build/tests/harness/test_page_addresses_caddy.py` (new; runs the image). **Say which folders each walks** (a scan-map row is written from that; a builder cannot add it).

## Checks (pure except the Caddy test; store ports pinned to 9)

The three new tests; PL7a2b's pages-setting test (changed only where the stand-in goes), `test_reference_render.py`, `test_render.py`, `test_cloud_platform_render.py`, `tests/test_doc_citations_check.py`; `npm test --workspace apps/pages`; `ruff check .`; `make -C OspreyFlow_Build design-check` and the Caddy validation by hand. **No `tests/test_layout.py`.**

## Out of scope

The cloud-platform sign-in (PL7e); the issuer check in `apps/pages/server/config.ts` (not weakened: the owner's ruling); turning the setting on anywhere; the protected files and the workflow (diffs for the owner).

## Never merge another part's unmerged tip (the owner, 23 November 2026)

**Never merge another part's unmerged tip, or any branch but main, into your branch.** Take main in when the line tells you to, and nothing else. A part that did this (AD1b, with AD1a's tip) had the hook count the other part's tests as its own. If your part needs another part's change that has not merged, stop and tell the conductor.
