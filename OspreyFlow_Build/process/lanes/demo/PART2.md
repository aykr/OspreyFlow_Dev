# Part 2, step 1: the owner's questions on the two public demos, answered read-only

The demo lane, 12 November 2026. These answers are about main at **b380d456**, the code osprey-small runs.
- Code is cited as `path:line` under `OspreyFlow_Core/`. Spec is cited as `spec/…` under `OspreyFlow_Build/`.
- The server was only inspected: `ss`, `free`, `docker stats`, `docker inspect`, `iptables -S`. Nothing was built, changed, or run in a way that writes.
- osprey-small stayed frozen.
- The questions are numbered as in the owner's prompt (1, 2, 2a, 3–8). Number 9 is the listener check the owner's rules ask for "before any name goes live". The orchestrator's "question 3 (memory)" is 2a here, and its "question 10 (answers files)" is 8.

## Summary

| # | Question | Answer |
| --- | --- | --- |
| 1 | Bare domain as `server.address` | **Yes.** `id.` and `bi.` go in front of the whole host. |
| 2 | Two Smalls on one server and one 443 | **Not in the product today.** Needs an ADR-114 amendment, code changes and an edge proxy. |
| 2a | Memory | Two demos fit **only if** each is capped (`memory_gib` 24) and the lanes run three or four stacks at most. They **cannot** share one model server. |
| 3 | GOV.UK theme off gov.uk | **Installs, with a warning only.** The banner wording is fixed text; changing it is a small product change. |
| 4 | The gate | **A separate edge proxy.** The product's proxy has no hook for it and its config is generated. |
| 5 | Gemini budget | **The gateway enforces it.** The next call is refused with a clear message. There is no automatic fall-back to the local model. |
| 6 | Certificates | DNS-01 outside the product, then a deploy hook copies the files and runs `ospreyflow apply`. Only the proxy restarts. No port 80 needed. |
| 7 | Nightly reset | No built-in schedule. A cron job runs `down -v`, `start`, `restore --yes`, then restarts the api. Measured time for a Small is unknown; estimate 5–10 min. |
| 8 | Draft answers files | **Both are refused as written.** Corrected text is below. |
| 9 | Listeners | **Today only sshd (1099) and 443 face the internet.** 443 is open to the owner's IP alone. Every store and lane port is loopback. |

## 1. A bare domain as the address: yes

- **The answers file checks only the shape:** https, a host, and no path, query or fragment (`cli/ospreyflow/answers.py:282-298`).
- **The schema checks only:**
  - the scheme and a trailing slash (`packages/schemas/deployment.py:1421-1433`);
  - no plain HTTP for Small (`deployment.py:2086-2106`).
  - Its one host rule is gov.uk under *Lite* (`deployment.py:2099`).
  - It does not refuse a bare domain, a `.app` TLD or a port.
- **Names are derived by prefixing the full host** (`harness/site.py:47-55`, `named("id.")`, `named("bi.")`; `deployment.py:1385-1386`):
  - `https://ospreyflow.app` gives `id.ospreyflow.app` and `bi.ospreyflow.app`.
  - `https://govuk.ospreyflow.app` gives `id.govuk.ospreyflow.app` and `bi.govuk.ospreyflow.app`.
- **The certificate must cover the host, `id.`, and `bi.` when dashboards are on** (`harness/tls_check.py:234-243`).
  - A wildcard covers one label (`tls_check.py:70-79`), so `*.ospreyflow.app` does not cover `id.govuk.ospreyflow.app`.

## 2. Two Small deployments on one server and one address

**Short answer: not within the product today.** Three refusals in main's own code stand in the way.

**(a) The ports check.**
- Install runs the server doctor (`cli/ospreyflow/main.py:791-793`).
- It checks the address's port by binding `0.0.0.0` (`cli/ospreyflow/doctor.py:228-235, 629-633`): "Port 443 is already in use on one of this server's interfaces" (`doctor.py:822`).
- It also checks the literal 2480 by connecting to loopback (`doctor.py:224-226, 634`). It ignores `listen_address` and `deployment.graph_port`.

**(b) `--name` is Lite-only.**
- `main.py:732-736`: "--name keeps a deployment beside others on this computer, which is Lite. A Small server or an Enterprise cluster is a deployment of its own: install it without --name."
- `spec/06_DECISIONS.md:22380` (ADR-138 Amendment 1, item 11) says the same.

**(c) `server.listen_address` is for multi-NIC servers.**
- It binds one interface (`answers.py:311-319`; `deployment.py:1412-1417`; ADR-114 Amendment 33 at `06_DECISIONS.md:23236-23243`).
- This server has **one** public IPv4 (`ip -4 addr`: `enp42s0 185.154.146.242/27`).
- A private address such as `127.0.0.2` would be reachable only through an edge on the same host.

**(d) Compose project.**
- Without a name the project is `osprey-{profile}`, which is `osprey-small` (`deployment.py:2265-2268`).
- A second Small from another checkout would therefore share osprey-small's project and **volumes**. That is the dangerous clash.
- `deployment.name` set through the answers file's `config:` key passes the schema (`deployment.py:1608-1616`), but this is untested for Small, and the doctor's 2480 check still refuses.

**What does separate by name, once a name is set:**
- folders: `deploy/generated/<name>`, `deployment.py:2271-2274`;
- backups: `<backups>/<name>/`, `harness/backup.py:148-152`;
- volumes, which are prefixed with the project name;
- the graph port: `deployment.graph_port`, `deployment.py:1581-1590`.

**There is no router in the product.**
- The Caddyfile routes only the deployment's own three names. Anything else gets `respond 404` (`harness/site.py:58-65, 122-123`).
- Multi-deployment support is Lite with separate ports (ADR-132 Amendment 1, `06_DECISIONS.md:20737-20769`; ADR-138 decision 2, `:22269`).

**Proposed routing.**
- **An edge proxy on the public IP:443.** It routes the six names by SNI and Host:
  - `ospreyflow.app`, `id.`, `bi.` go to deployment A on `127.0.0.2:443`.
  - `govuk.ospreyflow.app`, `id.govuk.`, `bi.govuk.` go to deployment B on `127.0.0.3:443`, with the gate (§4).
- **Each deployment:**
  - its own name, so its own project, volumes, folder and backups subfolder;
  - `server.listen_address` set to its private address;
  - its own `graph_port`.

**This is a product change.** It needs a new **ADR-114 amendment** (Small on a server). The last reserved is 40 (`spec/ADR_RESERVATIONS.md:194`), so this is 41 or later. The amendment would amend ADR-138 Amendment 1 item 11, and would need to:
1. allow `--name`, or `deployment.name`, for Small;
2. make the doctor's 443 check honour `listen_address`, and its 2480 check honour `graph_port`;
3. add the edge, either as a product component or as a documented recipe outside the product.

**Does osprey-small become one of the two?**
- Recommendation: **osprey-small becomes demo B** (it is already GOV.UK and holds the synthetic packs).
- Make the move only after the product change, with one deliberate `apply` that sets its `listen_address`.
- osprey-small binds 443 on every interface today, so no edge can take 443 without that change.

**Tonight's narrower question** (a second Small beside an unchanged osprey-small) is answered in the orchestrator messages: **no** without the code change above.
- A different port avoids the 443 refusal, but not the 2480 refusal or the project clash.
- A new port would also need its own owner-only firewall rule.

## 2a. Memory and load (measured 17:40 UTC; no lease; read-only; the whole server)

**What was measured:**
- `free -m`: total 64,224 MiB, available 37,187 MiB, swap 32 of 4,095 MiB used.
- `nvidia-smi`: 9,112 of 16,311 MiB in use.
- **The lane stacks were all stopped at that moment**: 31 `osprey-test-*` containers exited, stacks b–g.

**osprey-small, per `docker stats`:**
- ArcadeDB 15.45 GiB. Its heap is `-Xmx24G`, so it can grow by about 9 GB more.
- Ollama 8.98 GiB.
- OpenSearch 4.46 GiB (heap 3,968 MB).
- Keycloak 0.8, LiteLLM 0.58, NER 0.63, Postgres 0.42, Superset 0.39, api 0.24; the rest are small.

**Why it is so large:** `memory_gib: auto` measured 62 GiB, so the sizing rule gives:
- graph heap 0.4×62 = 24;
- OpenSearch heap 62/16 = 3.9;
- Postgres shared buffers 62/32 = 1.9.
- Source: `harness/profiles.py:110-118`; `deployment.py:1865-1885`.
- **Two demos left on `auto` would each claim a 24 GB graph heap.** Set `server.memory_gib: 24` in each answers file. The minimum is 16 (`answers.py:109`).

**One demo at `memory_gib: 24`:**
- stores: graph heap 9 + search 1.5 + Postgres 0.75;
- other services: about 3.5 GB;
- **about 15 GB at peak**, plus its model server.

**The model server cannot be shared:**
- Local models are wired to the literal `http://ollama:11434` (`harness/render.py:426-451`); readiness uses the same (`render.py:1046`).
- A provider's `api_base` must be https and makes a hosted engine (`deployment.py:405-412`).
- ADR-138: deployments "share no volume, folder, Compose project or port" (`06_DECISIONS.md:22300`).

**The GPU cannot hold two:**
- With `gpu: nvidia`, each Ollama reserves every GPU (`render.py:1178-1183`) and keeps the model loaded for ever (`OLLAMA_KEEP_ALIVE: "-1"`, `render.py:1190-1195`).
- The code measures the 14b at its 32k context at about 14 GB of the 16 GB card (`render.py:1184-1188`).
- Two cannot both hold it. The second runs on the CPU (very slow, roughly 18 GB as the code notes), or the product gains a keep-alive setting and the two take turns.
- **There is no keep-alive setting today:** it is fixed at -1 in render. The Friday task "unload when idle" is therefore a code change, not an `apply`.

**The lanes:**
- 7 stacks are defined. Each has ArcadeDB at `-Xms2G -Xmx2G` plus Postgres, Valkey, the object store and ClickHouse: roughly 3–4 GB each when running.
- Seven at once is about 25 GB.

**Do both demos fit?**
- 2 × 15 (stores and services) + 14 (one GPU model, the other demo on a hosted engine or on the CPU) is about 44 GB, leaving roughly 15 GB for the lanes and the OS. That is **three or four lane stacks at a time, not seven**.
- **What the build gives up:** no more than three or four leased stacks while the demos run. Heavy runs, such as PI's 100k-row load (3.2 GB peak), slow a demo.
- **Recommendation:**
  - The GOV.UK demo keeps the GPU model.
  - The standard demo uses `gpu: none` with the small local model as default, or Gemini under a budget.
  - Keep the owner's "quiet window" for demos the owner presents.

## 3. The GOV.UK theme on a non-gov.uk address: accepted, with a warning only

**Code:**
- The answers check only that the brand is known, the phase valid, and `service_name` present (`answers.py:197-223`).
- The schema states the rule but does not enforce it (`deployment.py:1630`).
- The one check is a **warning** (`doctor.py:699-707`): "The GOV.UK header and typeface are for services on a gov.uk domain." It is listed among warnings, not failures (`06_DECISIONS.md:23680`).

**ADRs:**
- ADR-132: a service on any other domain "must not" look like GOV.UK (`06_DECISIONS.md:20618-20621`).
- The GDS Transport font files are "restricted by the GOV.UK Design System to GOV.UK domains" (`:20680-20682`).
- ADR-114 Amendment 33 §10 keeps it *allowed with a one-line notice* for internal tools (`:23458-23466, 23612-23614`).
- No ADR covers a public demonstration under the GOV.UK look.

**Font:**
- `--ui:"GDS Transport",arial,sans-serif` (`apps/workspace/src/design/tokens.css:189`).
- The files are served by the deployment itself under `/assets/govuk/`, whatever the domain.
- "Keeps its default font" therefore means GDS Transport on a non-gov.uk domain. That is contrary to the licence note above.
- **This is a decision for the owner.** Arial would need a product change.

**Phase banner:**
- `PhaseBanner.tsx:7-8, 14` shows only `alpha` or `beta`, with fixed text: "This is a new service."
- `live` and `none` draw nothing. `appearance` forbids extra keys (`deployment.py:1624`; `answers.py:126`).
- **"Demonstration: not a government service" cannot be set today.**

**Smallest change.** Record it as an ADR-132 amendment (Amendment 6 exists at `06_DECISIONS.md:27146`, so the next is 7) under the owner's ruling for gated demonstrations:
1. an optional `appearance.banner_text` in `AppearanceConfig` and in the answers file;
2. pass it through `deployment.json` (`site.py:350`);
3. render it in `PhaseBanner.tsx`, showing the banner when the text is set even at `none`;
4. optionally, require `banner_text` for GOV.UK off gov.uk, beside `doctor.py:699`.

## 4. The gate: a separate edge proxy, not the product's own

**Why not inside the product:**
- The product's Caddyfile has no hook for extra directives. It emits only `reverse_proxy`, the GOV.UK assets block, `redir` and `respond` (`site.py:58-124`).
- `NetworkConfig` has no such option (`deployment.py:1360-1417`).
- The file is generated ("Do not hand-edit … reported by `python -m harness.render --check` as drift", `harness/render.py:231-237`), and every `apply` re-renders it.
- No `noindex`, `X-Robots-Tag` or `robots.txt` exists anywhere in the product.

**Recommendation:** the same edge as §2, a Caddy on the public IP:443. For B's three names it:
- serves `4_gate_disclaimer.html` and handles `POST /_gate`;
- checks the access code. The owner sets it on the server, in a root-only file the edge reads; it is never in a file the repository holds.
- sets a signed, `HttpOnly`, `Secure` cookie with `Domain=govuk.ospreyflow.app` and a limited `Max-Age` (for example 8 h), which covers all three names;
- adds `X-Robots-Tag: noindex, nofollow` to **every** response, the gate's included, and serves a `robots.txt` that disallows everything;
- then proxies to B on its private address, keeping Host and SNI.

**Two implementation notes:**
- Plain Caddy has no signed-cookie check, so use `forward_auth` to a tiny gate service (a few dozen lines) or a vetted plugin.
- The host's own tools (seeds, `repair-sign-in`) reach B on its listen address (`site.py:436-447`), so they bypass the gate, which is correct.

**What this keeps:** the gate stays outside the product's upgrades and its security boundary.

## 5. Models: Gemini with a token budget

**Adding Gemini:**
- `gemini` is a **provider name**, not an engine kind. Off the cloud platform the only kind is `provider` (`deployment.py:303, 336-338, 480-484`; ADR-135 decision 1, `06_DECISIONS.md:21251-21253`).
- It is added in Admin › Models (`POST /v1/admin/models/engines`, `services/api/app.py:19400`).
- The key goes to LiteLLM's own database, encrypted; neither the Conduit nor any file holds it (`model_admin.py:431-440`).
- **No restart or `apply` is needed** (`app.py:1465-1466`).

**The budget:**
- A token budget per day or per month (UTC), with optional requests-a-minute and tokens-a-minute limits (`packages/schemas/model_admin.py:52-74`).
- It is enforced **by the gateway** on the engine's own virtual key (`model_admin.py:327-340, 470-493`). Local calls have no limits.
- **Confirmed: it stops calls.** The call that crosses the budget is answered, and **the next is refused** with a 429 `budget_exceeded` (`06_DECISIONS.md:29906-29910`). The Conduit turns it into `ModelLimitReached` without retrying (`packages/adapters/model_litellm/usage.py:101-122`, `client.py:152-156`).
- It resets at midnight UTC, or on the 1st for a monthly budget.

**What a visitor sees:**
- The API answers 429 `{"error":"model_limit_reached","detail":…}` (`app.py:3591-3603`).
- Ask the case shows the detail as an alert (`apps/workspace/src/questions/QuestionsPanel.tsx:99-100, 269-271`), for example: "Gemini has used its token budget for today on this deployment, set in Admin › Models. It can be used again from midnight UTC, or ask someone who manages models. Nothing was sent to it."
- **There is no automatic fall-back to the local model.** The visitor picks "This deployment's own model" and asks again (`model_routing.py:339-340`; `06_DECISIONS.md:29984`).

**When Gemini is used:**
- Only if the visitor picks it in the engine picker, or an admin makes it a role's default (`model_routing.py:288`). With every default left as `local`, background work stays local.
- Egress needs **both** a sendable handling code **and** every dataset's egress allowing it (ADR-136 decision 3, `06_DECISIONS.md:21532-21539`; `model_routing.py:290-298`).
- **A failed egress check falls back to local silently.** Only a spent limit refuses.

**Setting the sendable codes:**
- `sendable_handling_codes` cannot go in the answers file. It goes in `osprey.yaml`, and needs `hosted_fallback` or a provider named first (`deployment.py:751-755`).
- On osprey-small tonight this was met with `hosted_fallback: gemini`, which nothing reads (`deployment.py:648`). The Gemini engine's name in Admin need not match it.

**Font:** see §3. GDS Transport is served regardless of domain.

## 6. Certificates by Let's Encrypt DNS-01, without port 80

**What the product does:**
- It takes **paths** to a full-chain PEM and an unencrypted key. It mounts them read-only into the proxy and never copies them (`deployment.py:1328-1357`; `site.py:187-211`).
- The proxy runs as the **key file's owner** (`harness/apply.py:1299-1322`).
- There is no ACME on a Small server (ADR-114 Amendment 33 decision 3, `06_DECISIONS.md:23261-23270`).
- Port 80 only with `redirect_http` (`spec/05_DEPLOYMENT.md:872-874`).

**Every `apply` re-checks** (`tls_check.py`):
- PEM, key match, validity, and the SAN names (CN ignored);
- a chain is accepted (`:133`), and RSA or EC keys (`:144, 153-154`);
- extra names are allowed, so one certificate naming all six passes for both deployments.

**Proposal:**
1. On the server, run `certbot` (or `lego`) with the registrar's DNS plugin. The owner enters the API token into a root-only credentials file, or adds the `_acme-challenge` TXT records by hand.
2. Take two certificates:
   - A: `ospreyflow.app` + `*.ospreyflow.app`, or the three names;
   - B: `govuk.ospreyflow.app` + `*.govuk.ospreyflow.app`.
   - Or one certificate naming all six. The edge (§4) uses the same files.
3. A **deploy hook** copies `fullchain.pem` and `privkey.pem` to fixed paths, for example `/etc/ospreyflow/tls/<name>.crt|.key`, as `osprey:osprey` with the key at mode 600 (`deployment.py:1339-1342`).
   - Do not point the product at `/etc/letsencrypt/live/` directly. It is root-only, so `apply` (run as `osprey`) could not read it, and the proxy would run as root.
4. Then the hook runs, as `osprey`: `cd /opt/<checkout> && ospreyflow apply [--name <name>]`. It also reloads the edge.
   - `apply` writes the leaf's fingerprint to `tls-fingerprint`, which only the proxy mounts, so **only the proxy restarts** (`apply.py:1359-1364`; `spec/05_DEPLOYMENT.md:869-871`). That is a few seconds' gap per deployment.
5. certbot's timer renews from 30 days out, and the product warns under 30 days (`tls_check.py:43, 185-190`).

## 7. A nightly reset from a verified backup

**There is no reset schedule in the product.** The only scheduler is the Enterprise backup CronJob. A Small uses the service account's crontab (`spec/10_ADMINISTRATION_GUIDE.md:601-607`).

**How restore behaves:**
- `restore` without `--yes` is a dry run, and it is the verification: manifest, SHA-256 of every file, schema compatibility, writing nothing (`harness/restore.py:32-33, 751-756`).
- It refuses a non-empty graph store: "Destroy the deployment's volumes first (`docker compose … down -v`) …" (`restore.py:758-765`).

**The reset, as a cron job for each deployment, run as `osprey`:**
1. `ospreyflow restore <golden set>`: the dry run verifies the set.
2. `docker compose -f <generated>/compose.yaml down -v`.
3. `ospreyflow start`.
4. `ospreyflow restore <golden set> --yes`. This restarts Keycloak only (`restore.py:493-509`).
5. `docker compose … restart api`. The restore says the Conduit must be restarted (`restore.py:905`).

**What it restarts:** everything; the whole stack goes down and comes up empty.

**How long it is down:** no measured Small figure exists.
- Lite took 28 s to start empty and 8 s to restore (`deploy/RUNBOOK.md:8-11, 42-48`).
- Enterprise took 70.8 s end to end (`06_DECISIONS.md:34193-34194`).
- osprey-small's own start tonight took 78 s to healthy, with Keycloak the slowest, and its set is 88 MB (projection 0.35 s/MB, `restore.py:101-108`).
- **Estimate: 5–10 minutes per demo.** It must be measured once before it is relied on.

**What a backup does not carry:**
- `deployment.env` (so the demo accounts' passwords and the model keys), the TLS key, the ingest folder (`restore.py:38-51`);
- OpenSearch and Valkey: search is rebuilt, the cache is empty.
- So a reset keeps the accounts' passwords **only** because it keeps the same `deployment.env`.

**Further notes:**
- PI's own rehearsal reset is `python -m scripts.seed_internal prison-intelligence --reset-live --stop-api`. It restarts only the api, and lists what it **cannot** undo (alerts, rules, working sets, hotlists; `scripts/seed_pid.py:1817-1829`). A full nightly reset should use the restore path above.
- Restore does not check other deployments (`restore.py:758, 877-880`). Stagger the two jobs.
- The golden set for osprey-small exists: `/srv/ospreyflow/backups/small/20261112T173107Z-small-2be985a…`, taken after the seeds and before any check.

## 8. The draft answers files: both refused as written

**What the schema allows:**
- Top level: `mode, components, folders, models, demo_packs, paysim_file, cloud, config, mail, external, cluster, starter, appearance, demo_accounts, server, admin_email, sign_in, grading` (`answers.py:94-98`).
- `server:` takes `address, certificate, key, ca, ingest, redirect_http, listen_address, backups, memory_gib, gpu` (`:101-104`).
- `models:` takes `local_only` **only** (`:122`).
- Unknown keys are refused by name (`:226-232`).

**What that means for the drafts:**
- `starter: ospreyflow-aml` is real: OspreyFlow's look, with the Operation Ledger pack and the `fibo` domain (`starters.py:57-66`). Add the other packs with `demo_packs` or `ospreyflow demo add`.
- `service_name`, `organisation` and `phase` belong **under `appearance:`** (`:126`). As top-level keys they are refused.
- `models.sendable_handling_codes` is **refused** in the answers file (`:122`). Set it in `osprey.yaml` after install, with `hosted_fallback` or a provider (§5).
- `memory_gib: auto` would size each to the whole 62 GiB (§2a), so use 24.
- The deployment name and the listen address need the §2 change. They are shown here as they would be used.
- Listing `prison-intelligence` in `demo_packs` makes the install turn post-ingest resolution off (`answers.py:680-707`). That avoids tonight's second apply.
- The demo accounts are never made on a Small (ADR-114 Amendment 33, `harness/register_sign_in.py:388`). For a public demo that is right: the owner invites Analyst accounts in Admin.

```yaml
# 2_install_standard.yaml: corrected (no secrets in this file)
mode: small
starter: ospreyflow-aml            # OspreyFlow's look; packs: operation-ledger (starters.py:57-66)
demo_packs: [operation-ledger, fixture-corp, cyber-intrusion]   # synthetic only (scripts/demo_packs.py)
server:
  address: https://ospreyflow.app  # id.ospreyflow.app and bi.ospreyflow.app follow (site.py:47-55)
  certificate: /etc/ospreyflow/tls/ospreyflow.app.crt   # full chain; SANs: the three names (tls_check.py:234-243)
  key: /etc/ospreyflow/tls/ospreyflow.app.key           # owned by osprey, mode 600
  listen_address: 127.0.0.2        # behind the edge (needs the §2 change)
  ingest: /srv/ospreyflow/ingest-standard
  redirect_http: false
  backups: /srv/ospreyflow/backups # sets go to <backups>/<name>/
  memory_gib: 24                   # not auto: two demos share the server (§2a)
  gpu: none                        # the GPU is the GOV.UK demo's (§2a)
components: {dashboards: true}
models:
  local_only: false                # sendable_handling_codes: [P] goes in osprey.yaml after install (§5)
```

```yaml
# 3_install_govuk.yaml: corrected (no secrets in this file)
mode: small
starter: govuk-crime               # GOV.UK theme; packs: prison-intelligence, hmp (starters.py:49-56)
demo_packs: [prison-intelligence, hmp]   # PI here makes the install turn resolution off (answers.py:680-707)
appearance:                        # answers.py:126: these three live here, not at the top level
  service_name: Prison Intelligence (demonstration)   # starters.py:40-42 advises a name not tied to one case
  organisation: Solirius Reply demonstration
  phase: beta                      # draws "Beta: This is a new service." (fixed text; §3)
server:
  address: https://govuk.ospreyflow.app   # id.govuk.ospreyflow.app and bi.govuk.ospreyflow.app follow
  certificate: /etc/ospreyflow/tls/govuk.ospreyflow.app.crt   # SANs: govuk.ospreyflow.app + *.govuk.ospreyflow.app
  key: /etc/ospreyflow/tls/govuk.ospreyflow.app.key
  listen_address: 127.0.0.3        # behind the edge and its gate (§4; needs the §2 change)
  ingest: /srv/ospreyflow/ingest   # osprey-small's, if this becomes osprey-small
  redirect_http: false
  backups: /srv/ospreyflow/backups
  memory_gib: 24
  gpu: nvidia
components: {dashboards: true}
models:
  local_only: false
```

**Not checked:** whether two deployments may share one `server.ingest` folder. Separate folders are the safe choice.

## 9. Listeners (the owner's rule: before any name goes live)

Measured at 17:45 UTC with `ss -H -ltnu`, `iptables -S DOCKER-USER`, `ip6tables -S DOCKER-USER`, `ip -6 addr`.

| Listener | Bound to | Reachable from the internet |
| --- | --- | --- |
| sshd :1099 | 0.0.0.0, [::] | Yes. SSH is aside, by the owner's rule. |
| osprey-small proxy :443 | 0.0.0.0, [::] | From the owner's IP only. The DOCKER-USER rule drops every other source (`! -s <owner>/32 … --ctorigdstport 443 -j DROP`). |
| ArcadeDB door :2480 | 127.0.0.1 | No |
| DNS :53 (systemd-resolved) | 127.0.0.53 and 127.0.0.54 | No |
| DHCP client :68 | 185.154.146.242 | Outbound only |

- **Lane stacks** (stopped at the time; their bindings are from `docker inspect`): every port is `127.0.0.1` (ArcadeDB 2492–2497, Postgres 55434–55439, Valkey 6380–6385, object store 9002–9012, ClickHouse 18124–18129).
- **IPv6:** there is no global IPv6 address on the public interface; there is only a private ULA on a Docker bridge. ip6tables also drops 443 on `enp42s0`.

**Before the names go live, all of this changes:**
- the 443 rule must open to everyone, for the edge only;
- the deployments must move to private listen addresses;
- this table must be measured again.

## Findings raised along the way

- **ArcadeDB root password is readable.** osprey-small's ArcadeDB root password sits in the container's environment (`JAVA_OPTS`), so anyone who can run `docker inspect` on the server can read it. The value is not repeated here. Worth an ADR note if the server ever has more than one administrator.
- **Stale version string.** `glass.json`'s version and the backup names read the checkout's git HEAD (2be985a, v0.5.0), not the code installed.
- **Out-of-date comment.** `apps/workspace/src/patterns/api.ts:28-30` says Ask to search "never leaves the deployment"; it can since ADR-135 Amendment 1 (`services/api/pattern_ask.py:616`).
- **Friday task.** "Unload the local model when idle" has no setting: `OLLAMA_KEEP_ALIVE` is fixed at -1 by `render.py:1195`. In `osprey.yaml` the memory key is `resources.memory_gib` (`answers.py:662-664`).
