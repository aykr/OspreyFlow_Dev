# 05 — Deployment and the Setup Harness

Written as a runbook. Where a step could be expressed as infrastructure-as-code, it is expressed
here as a decision made on screen, and the harness generates the code. You should be able to
stand up and understand a deployment without reading a template language — and, apart from one
bootstrap command, without a terminal.

## 1. Profiles

Three, not two. The Gemini specification proposes `local-lite` and `enterprise-cluster` and both
are right, but the gap between them is too wide to cross in one step — the first real
deployment is almost always a few machines in a single room, and if that case has no profile
someone will improvise one.

| Profile | Runs on | Graph | OLAP | Models | Orchestration |
| --- | --- | --- | --- | --- | --- |
| `local-lite` | One laptop, 16 GB | ArcadeDB | DuckDB | Ollama, CPU or one consumer GPU | Docker Compose |
| `small` | One cloud server on the cloud's managed services (ADR-114 decision 8, §3a) | ArcadeDB | DuckDB | Ollama | Docker Compose |
| `cluster` | Kubernetes — EKS or AKS (ADR-114 decision 9, §3b) | ArcadeDB, three Raft replicas | ClickHouse, a replicated pair with Keeper | Ollama in the cluster for now — decision 11's vLLM on a GPU pool is not built; a client's provider through LiteLLM | Kubernetes, from the Helm chart |

The same container images run in all three. Only configuration differs. That is the
transportability requirement, and it is verifiable: the acceptance scenarios in
`08_ACCEPTANCE_SCENARIOS.md` must pass unchanged on `local-lite` and on `cluster`.

## 2. The setup harness

> **Superseded by design, not yet by build — `06_DECISIONS.md` ADR-114 (11 October 2026).** One
> command, `ospreyflow` (`install`, `start`, `stop`, `status`, `open`, `update`, `demo`, `doctor`, …),
> replaces this harness's Set-up console, `make refresh`, `make launch` and the welcome service; one
> front proxy gives each app a name instead of a port; Small runs on one AWS or Azure VM with managed
> services, Enterprise on EKS or AKS from a Helm chart. Until each stage of ADR-114 is built
> (`process/HANDOVER_2026-10-11.md`), what this section describes is what runs.


The harness is a **browser application**, not a command-line tool. One bootstrap command starts
it; everything after that happens on screen.

```bash
docker run --rm -p 127.0.0.1:7100:7100 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$PWD:/workspace" \
  ghcr.io/ospreyflow/harness:latest \
  --config /workspace/osprey.yaml --out-root /workspace/deploy/generated
# → INFO:     Uvicorn running on http://0.0.0.0:7100 (Press CTRL+C to quit)
```

**The console's port is 7100, not 7000.** Port 7000 is macOS's own AirPlay Receiver (`ControlCenter`),
which is on by default, so on a Mac the console exited at start-up with "address already in use". One
definition (`harness.realm.HARNESS_PORT`) feeds the runbook, the console's default and the sign-in
client's redirect. The launcher now notices when the console (or the stack start) has stopped, shows
the tile as "Not running" with the last line of its log and the log's location, and names an occupied
port in plain words. `make register-sign-in` brings an existing client's redirect address up to date, so
a deployment registered before this change needs that one command.

**Two corrections, found running the real image rather than by reading the code.**
`-p 127.0.0.1:7100:7100`, not a bare `-p 7100:7100` — R2's own loopback-only guarantee
needs the port itself bound to loopback on the host side; a bare `7100:7100` publishes to every
interface, which the application-layer refusal in `harness/webapp.py` cannot fully make up for on
its own. **The `-p 127.0.0.1:` port-binding above is R2's own enforcement for this documented
command; `harness/webapp.py`'s own `loopback_only_middleware` is real defence only for the
non-Docker path, redundant-but-harmless here** (`harness/webapp_auth.py`'s own docstring
has the full Docker-NAT reasoning). And the trailing `--config`/`--out-root` are not optional
flourishes: `harness.webapp`'s own
default `--config` resolves relative to *where the harness package lives inside the image*
(`/app/osprey.yaml`), not to whatever the operator happens to mount at `/workspace` — a bare
`docker run` with no arguments after the image name writes and reads a config file the operator's
own bind mount never sees, and it is lost the moment `--rm` removes the container. Confirmed both
ways directly: with the flags, a `PUT /api/config` produces a real `$PWD/osprey.yaml` on the host;
without them, nothing appears there at all.

That is the only command in this document that has to be typed. It is unavoidable — something
has to serve the page before anything is deployed — so it is kept to one line and does nothing
except start the harness.

After launch the harness does not go away: it stays the **Set-up console**, where the deployment's
profile, components and models are changed (provider registration, gazetteer loading, upgrades and
verification). **The admin console is not the harness** (ADR-110 Amendment 1): it is the *Admin*
area of the deployed workspace — people and their roles, dashboard identities, the system's health,
and with ADR-110 the schedules — started with the stack, behind the same single sign-on, shown to an
account holding an administration right (ADR-112), with nothing to start by hand. The launcher's
*Admin console* tile opens it (`?from=launcher&view=admin`); its *Set-up console* tile starts the
harness. Per the brand foundations, the console carries the Nexus mark and the
analyst workspace carries Osprey; from inside the workspace the data layer is plumbing, not a
brand.

### 2.1 What the harness does

Six screens, navigable in any order once the profile is chosen, with a persistent summary rail
showing what has been decided and what is outstanding.

| Screen | Decides |
| --- | --- |
| **Profile** | Laptop, small or cluster. Every later screen filters its options to what is valid here |
| **Components** | Graph store, analytics engine, and the storage roots for data, staging and backups |
| **Models** | The deployment's own model for each job, from the list of pinned models (ADR-095): entity extraction (default `qwen2.5:7b-instruct`, a 4.68 GB download on the first Launch; `qwen2.5:14b-instruct` is the other choice, 8.99 GB), image description, transcription and embedding (each with today's one model). Then local only, or local with a named hosted fallback — and if hosted, which handling codes may be sent to it. Defaults to none |
| **Governance** | Identity provider, handling scheme, ontology. Ships with a UK law-enforcement scheme, a US criminal-intelligence scheme, and the default ontology |
| **Geospatial** | Provider tier and basemap registry; gazetteers and boundary sets to load |
| **Preflight** | Environment checks, then generate, review and launch |

Three properties make this worth building as a UI rather than a questionnaire in a terminal.

**Consequences are shown, not described.** Choosing `cluster` renders the machine count, the
components that appear, and the estimated memory footprint, updating as later screens change.
Enabling a hosted model draws the egress exception it creates on the deployment diagram. Nobody
has to hold the architecture in their head to see what a choice costs.

**Preflight runs live.** Each check appears as it completes — available memory against the
profile floor, disk against the projected staging volume, GPU presence and driver version, port
availability, container runtime version, and for `cluster` connectivity to every declared host. A
failure explains what is wrong and what to do about it, with a **Re-check** button rather than a
loop of edit-and-rerun. Preflight must pass before Launch is enabled.

**Memory and disk verdict on the container runtime's own daemon, not the operator's shell.**
The host running Preflight and the Docker Desktop VM every container actually
runs inside can have very different resources (this document's own memory and disk figures below
are what the daemon must provide); the operator's host figure is still shown alongside each result,
as context, never as what either check passed or failed on.

**A warning does not block Launch — owner's decision, 24 September 2026.** Not everything Preflight
finds is a reason to refuse to start. A check reports a **warning** when it has found something
real whose remedy is available *after* install, and Launch proceeds. The basemap is the case this
was decided for: tiles that have not been built yet make the Map view show "Basemap not built" and
affect nothing else, and blocking on it would mean a fresh install could never reach a running
system at all. A warning still carries a remedy — one with none is noise, and noise is how a real
finding gets missed.

**A check that cannot run reports that it did not run — it never reports success.** Some of the
list above is not answerable on every platform or in every profile: a GPU driver version cannot be
read headlessly on macOS, and cluster connectivity has nothing to connect to at `local-lite`. Each
such case is reported as *skipped, with the reason*, and a skipped check does not block Launch.
What it must never do is report a pass, which would tell an operator their GPU driver is fine when
nobody looked.

**What projects the staging volume is not specified, and the check says so — Proposed, 24 September
2026 (found building Preflight).** "Disk against the projected staging volume" names a comparison
without naming what produces the projection: nothing in this document derives a staging figure from
a deployment's own sources, formats, retention or expected load. The headless check therefore
compares free space against an assumed default and labels it, in its own output, as an assumption
rather than a derived requirement. **The proposal:** the projection is a function of the declared
sources and a retention window, both of which the Ingest and Components screens already collect, and
this section should say so and name the inputs. **Not decided here** — a wrong projection is worse
than a labelled assumption, because staged Parquet is what every migration and rebuild replays from,
and an operator who trusts a fabricated number discovers it is wrong at the point of recovery.

**The generated artefacts are shown before anything runs.** The final screen is a diff, not a
progress bar: `osprey.yaml` on the left, and the files that will be written on the right —
compose or Kubernetes manifests, environment files, `versions.lock` with every image digest
pinned, and `RUNBOOK.md` written for *this* deployment with the real hostnames, ports and paths
filled in. All of it is readable, all of it is downloadable, and Launch is the last click rather
than the first.

`osprey.yaml` is the deployment. Version it, review it in a pull request, and never hand-edit a
generated artefact — regenerate instead.

**Where the generated artefacts live — a gap in this section, settled by the owner.** This
document named two fixed paths for
generated
output, `deploy/compose/dev.yaml` (§2.4) and `deploy/versions.lock` (§5, §7), and says
nothing about how either coexists with the four artefacts listed above being renderable for more
than one profile.

For a deployment the fixed paths are exactly right: a deployment is one profile, and a single
`deploy/versions.lock` is what §5's rollback and §7's digest pinning both assume. For a repository
that can render `local-lite`, `small` and `cluster` — which the harness must be able to do before a
profile has been chosen at all — two renders overwrite each other at those paths silently: no
error, and no drift report either, because the second render is self-consistent with itself.

**Owner's decision, 24 September 2026.** Rendered output goes to
`deploy/generated/<profile>/`, and the two fixed paths named above are amended to that: there is no
single `deploy/compose/dev.yaml` and no single `deploy/versions.lock`, because a harness
that can render three profiles cannot have one of either without the second render destroying the
first. Each profile's four artefacts sit under its own directory and are read from there by
Preflight, by the scripted deploy and by the Set-up console alike.

The directory is **not** version-controlled in this repository, which is a separate point from
where it sits: this repository is not a deployment — the committed `osprey.yaml` describes itself as
the demo and CI configuration and says a real deployment's own is generated — so committing output
rendered from it would assert something untrue. A real deployment's own repository versions
`deploy/generated/<profile>/` exactly as the paragraph above requires, and reviews it in a pull
request along with `osprey.yaml` itself.

*The renderer already writes to these paths; this document describes the real behaviour rather
than a still-pending change.*

### 2.1.1 What the rendered identity-provider realm must carry

The Governance screen's answers render an identity-provider realm alongside the other artefacts.
Three of its requirements are recorded here because each was found by running the thing rather than
by reading the documentation, and each fails **silently** when missing — the deployment comes up,
nothing errors, and the fault surfaces later as something else entirely.

**Protocol mappers for the four custom claims.** The Conduit builds a principal from `clearance`,
`org_unit`, `receivable_handling_codes` and `roles`. Without a mapper putting each into the issued
token, an exchanged token verifies perfectly *as a token* and then fails *as a principal*, so the
error names a missing claim rather than a missing mapper.

**The sign-in rules (ADR-115 decisions 5 and 6).** Brute-force protection on — five failures lock an
account for 900 seconds — a reset link living 1800 seconds, and reset by email only when the
deployment has a mail server (`resetPasswordAllowed`). Measured on Keycloak 26.0.8: four wrong
passwords then the right one sign in, five then the right one are refused for exactly 900 seconds
(failures under a second apart also trip Keycloak's own 60-second quick-login lock), and a reset
asked for with no mail server ends on Keycloak's error page. Keycloak says "Invalid username or
password." for a locked account too, so the sign-in page's words name the rule. Registration
writes these each time, since a kept realm never re-reads the file.

**`unmanagedAttributePolicy` set to `ENABLED`.** Keycloak 26 discards user attributes it does not
recognise, by default and **without reporting it**: the attributes are accepted on write, stored
nowhere, and absent from the token, with no error at any point. A realm that looks correctly
configured produces principals with no clearance.

**A view-users grant separate from the impersonation grant.** The Conduit checks that a principal
is still enabled before exchanging for them, and it must do so with an authority other than the one
that would mint the token. A pre-check sharing the impersonation grant would be asking the
component that has already said yes, which is no check at all.

**That pre-check is proven against a real identity provider, not a fixture: `make idp-test`.**
It starts a real Keycloak 26.0 carrying the realm
`harness/realm.py` renders, applies the grants through `harness/keycloak_admin.py` exactly as
`harness.apply` does, and runs `tests/services/api/test_revoked_principal_precheck.py`'s five
cases; CI runs the same target as `token-exchange-idp-test`, and `make test-all` depends on it.
The distinction matters here more than elsewhere, because the realm's own behaviour is the
finding: Keycloak **does** issue a token for a disabled subject when asked by a client holding
impersonation, so the refusal has to be the Conduit's. A fixture IdP written to suit the test
would have agreed with whatever the code did.

**The model tier arrives shortly after `apply` reports ready, not before it.**
`04_VAULT_BACKEND.md` §4's LiteLLM proxy and Ollama are both rendered, and Ollama pulls and
digest-verifies its models (ADR-020) on a persistent volume: the three pinned ones, and the
deployment's own extraction model (`models.extraction`, ADR-095: `qwen2.5:7b-instruct` by default,
4.68 GB; 8.99 GB for the 14b). The deployment deliberately does **not wait** for that pull: on a slow
link it is several gigabytes, and gating readiness on it
made a CI gate ten times slower — measured, Floor A 9m40s → 1h43m, because the test suite applies
ten deployments and destroys the model volume each time.

**So on a first install, extraction and the review queue fail until the pull finishes.** Watch it
with `docker compose logs -f ollama`, or `docker compose exec ollama ollama list` — when
the deployment's extraction model and `all-minilm:22m-l6-v2-fp16` appear, extraction works;
`moondream` backs image description only, and `qwen2.5:0.5b-instruct` is the conformance suite's.
The deployment says when they have arrived rather than waiting for them (ADR-095 Amendment 2):
`GET /v1/readiness`, signed in, lists the extraction, vision and embedding models and whether each
is present, and is `ready` only when all are. A model extraction asked for before its model is in is
refused in words (`503 model_unavailable`). On any later start the models are already on the volume and the
tier is ready in seconds.

**Closed by ADR-114 Amendment 5 (12 October 2026): Keycloak runs in production mode with its data
in the deployment's Postgres, so accounts and passwords survive a restart; its database goes when
Postgres's does.** The history, kept: **an open defect from 27 September 2026 — a stopped-and-started
deployment lost the demo analyst's password.** `--demo-analyst` sets that password *after* the realm import, through the admin API,
and Keycloak's database is not on a persistent volume, so `docker compose down` discards it. On
the next `up` the realm and the subject come back from the import but the credential does not: the
sign-in page appears and refuses the operator's own password, with nothing naming the cause. Found
when a deployment that had passed the over-the-wire exit test 8/8 an hour earlier failed at
sign-in after a restart.

**Persisting Keycloak's database is not the fix by itself, and was tried.** Keycloak creates its
bootstrap admin only on a first start against an empty database; start it again on the same volume
and `KC_BOOTSTRAP_ADMIN_PASSWORD` is ignored — measured, the new password returns 401 and the old
one still works. Because `harness.apply` mints a fresh admin password on every apply, a persistent
volume makes *any re-apply* fail at the grants step. Closing this needs apply to either reuse an
existing deployment's admin credential or reset the volume deliberately — a change to what `apply`
means for an existing deployment, and so a decision rather than a patch.
`tests/harness/test_render.py`'s
`test_keycloaks_data_lives_and_dies_with_the_deployments_postgres` now guards the coupling: Keycloak's
data has no volume of its own, so it never outlives the Postgres data a fresh install re-mints.

**Client secrets are generated at deployment time, never carried in the repository** (§2.5): the
realm names the client, the deployment's own environment file carries the secret, and nothing
version-controlled contains either.

### 2.2 The geospatial screen

**Building the basemap is a post-install step, not a precondition of Launch** (owner's decision,
24 September 2026). The deployment comes up without it; the Map view says "Basemap not built" until
one command has run, and Preflight reports it as a warning rather than refusing to start. Everything
else — ingest, the graph, search, assessment, export — works meanwhile.

Tier 1 is one button. **Build local basemap** asks for an area — Great Britain, a US state or
region, or a custom bounding box — then downloads the extract, runs planetiler, loads the OSM
gazetteer and registers the provider, with progress and the resulting tile size shown as it goes.
Nothing to sign, no account, and the result works offline. The demo, the acceptance scenarios and
CI all run on this, so the test suite never depends on anyone's entitlement.

Moving up a tier is the same screen:

- **Tier 2** — drop in an OS OpenData download; the harness converts it to PMTiles and registers
  it. No account needed, because Open Government Licence data is open to anyone.
- **Tier 3** — enter a credential *reference* (an environment variable name, never a value). The
  harness states plainly that this enables the tile proxy's egress exception, and offers
  **Prefetch area of operations** with a drawn or uploaded boundary. Prefetching matters: live
  tile requests to a hosted API disclose where you are looking, and a prefetched area makes no
  live requests during routine work.
- **Tier 4** — paste a WMTS, WMS, WFS or OGC API endpoint. The harness fetches the capabilities
  document and lists the available layers, projections and zoom ranges to choose from, rather
  than asking anyone to type them.
- **Anything else** — pick from the shipped profiles, or upload a profile YAML, which is
  validated against the schema in `00_ARCHITECTURE.md` §1.2 on upload.

**Verify** runs after any provider change and renders its result rather than printing it: sample
tiles at three zoom levels, the coordinate reference system and zoom range asserted, and a
fixture graph drawn over the basemap so the contrast floor is checked by eye as well as by
measurement. It catches the two common failures — a provider whose maximum zoom stops short of
what site analysis needs, and a basemap bright enough to swallow the entity palette.

Gazetteer loading sits alongside it, with the UK and US tier tables from `00_ARCHITECTURE.md`
§1.2 rendered as the choices. Both basemap registration and gazetteer loading are re-runnable; a
gazetteer refresh loads a new version of the reference partition rather than merging into the old
one, and investigations record which version was in force when a place name was resolved.

### 2.3 Everything has a headless equivalent

The browser is the primary path; it is not the only one. Continuous integration, air-gapped
transfer and scripted rebuilds all need automation, so every screen maps to a subcommand with the
same behaviour and the same validation:

```bash
osprey apply osprey.yaml          # generate and launch, non-interactive
osprey preflight                  # the Preflight checks, exit code 0 or 1
osprey geo build --osm great-britain
osprey map add --profile os-zoomstack --file /data/tiles/os-open-zoomstack.pmtiles
osprey verify map
osprey bundle --images            # signed tarball for air-gapped transfer
```

The rule is that the UI never has a capability the headless path lacks. A deployment that was
built by clicking must be reproducible by a script, or it is not reproducible.

### 2.4 The harness drives the orchestrator, so nobody types the dangerous commands

The profile choice determines the orchestrator — Compose for `local-lite` and `small`,
Kubernetes for `cluster` — and the harness invokes it. Nobody runs
`docker compose -f deploy/compose/docker-compose.yaml up -d` or `kubectl apply -f deploy/cluster/`
by hand. That closes the error class where the right manifest is applied to the wrong place, or
the wrong manifest to the right one.

Five guards, each closing a specific mistake:

| Guard | The mistake it prevents |
| --- | --- |
| **Target confirmation** | The harness shows the resolved target before every action — the Docker context, or the Kubernetes cluster, context and namespace — and requires it to be confirmed when it differs from the last action. Applying to the wrong cluster is the classic incident, and it is almost always a stale `kubectl` context nobody looked at |
| **Drift detection** | On open, the harness compares the running deployment against `osprey.yaml` and shows any divergence. Hand-edited manifests and out-of-band `kubectl edit` are the second commonest cause of an unreproducible environment |
| **Change preview** | Every switch shows what will be created, changed and destroyed before it runs, as a diff against the current state, not only at first generate |
| **Ordering enforcement** | A profile switch with live data cannot skip backup and restore. The harness greys out Launch until a current backup exists, and states why |
| **Capacity check** | A downgrade — cluster to small, small to laptop — runs preflight against the *existing data volume*, not the empty case, and refuses if it will not fit. Moving down is legitimate; discovering halfway through the restore that it cannot fit is not |

The destroy path is deliberately slower than the create path. Tearing down an environment
requires typing its name, and the confirmation states what is not recoverable from backup — the
audit stream in particular, which by design is neither rebuildable nor deletable.

Where the switch genuinely changes the architecture rather than the configuration, the harness
says so rather than presenting it as a toggle. Compose to Kubernetes is not a setting change: it
is a new environment, a replay from staged Parquet, and a cutover. §4 sets out that path, and the
harness walks it as a sequence of confirmed steps with its own progress rather than a single
button.

### 2.5 What the harness deliberately does not do

- **It does not hold state the repository lacks.** Everything it produces is a file in
  `/workspace`. Delete the harness container and nothing is lost.
- **It never sees a secret.** Credentials are entered as references — an environment variable
  name or a secret-manager path. The harness records where to look, never what it found.
- **It does not run as a privileged long-lived service.** During setup it needs the container
  socket; the Set-up console it stays afterwards does not, and runs with the same non-root,
  read-only-root posture as every other component (§7).

#### 2.5.1 Signing in to the Set-up console — `06_DECISIONS.md` ADR-051

(Named the admin console until ADR-110 Amendment 1; the post-launch Admin area is the Glass's, §3.)
Once a realm has been rendered (`deploy/generated/<profile>/realm.json` exists) the Set-up console
requires a signed-in account holding the `osprey-admin` role, on **every** route including the pages
themselves. Sign-in is the deployment's own realm through the public client `osprey-harness`
(authorization code with PKCE), so the console needs the identity provider running: with it down
the console says so and admits nobody, and the launcher (`make launch`) is how the stack is started
first. A demonstration deployment (`apply --demo-analyst`) includes the account `osprey-demo-admin`,
which holds `osprey-admin` and also every role the demo analyst holds, so one demonstration login
can open the Set-up console, the Glass with its Admin area, and the Ingest Studio (each right is
still enforced by the Conduit itself); its password is `OSPREY_DEMO_ADMIN_PASSWORD` in `deployment.env`. A deployment applied earlier gets
the client and the account with `make register-sign-in`, which also switches on custom user
attributes in the realm and restores the account's attributes if it was created without them (the
`osprey-admin` role travels as one, and Keycloak discards it silently when they are off).

**The sign-in page's look.** Keycloak's own sign-in page is restyled with the design system
(`apps/workspace/src/design/tokens.css`) so the journey from launcher to workspace does not change
character in the middle. `apply` writes a Keycloak login theme beside the compose file
(`keycloak-theme/osprey/`, from `harness/keycloak_theme.py`); compose mounts it into Keycloak
beside, not over, Keycloak's own themes, and the realm names it (`loginTheme`) and calls itself
"OspreyFlow" (`displayName`). Like `realm.json` and `litellm.yaml` it is a service's own config, not
one of §2.1's four artefacts. The page's header is the brand's horizontal lockup (the mark, then
the wordmark with Osprey bold and Flow regular), set through Keycloak's `loginTitleHtml` message and
the `#kc-header-wrapper` element Keycloak 26 renders (ADR-051 Amendment 5). It changes only appearance
and wording: who may sign in, and what they may then do, are untouched. A running Keycloak sees it only after it is recreated from a
compose file that mounts it, so `make register-sign-in` names the theme only when Keycloak lists it.

- **Before any realm is rendered the console is open**, loopback only, because there is nothing to
  sign in to; the enforcement is decided when the console starts, so the Launch that renders the
  realm does not lock the operator out mid-flow. The next start enforces.
- **The console must be served on port 7100 when enforced.** The realm registers one exact redirect
  address, `http://localhost:7100/callback`, and the console refuses to start on another port
  rather than fail at the provider's error page.
- **Run the console on the host (`make launch`, or `python -m harness`) once a deployment exists.**
  The `docker run` bootstrap above reaches the identity provider as `localhost`, which inside the
  container is the container itself, so an enforced console started that way reports the provider
  as not running. This is a known limit, not a fault to work around.
- `/admin` in console mode is unchanged: bearer-only, and `404` when refused.
- The session is held in the console's memory (a restart signs everyone out), lasts eight hours from
  sign-in whatever happens in between, and is not re-checked against the provider: an administrator
  whose role is removed stays signed in until then. Signing out (`/logout`) also ends the provider's
  own session.

### 2.6 How the Glass reaches the Conduit, and how an analyst signs in

Two holes, found running the seeded golden path: a rendered `local-lite` deployment came up
healthy, seeded both fixtures and passed its three-sided verify — and the Glass served by that same
deployment could not talk to it at all. **Both are now decided, differently.**

#### 2.6.1 Reaching the Conduit — DECIDED, 25 September 2026: same-origin

**The workspace's own image proxies the Conduit.** Its nginx serves the Glass and forwards `/v1`
and the delta WebSocket to `api:8000` on the internal network; the bundle is built with an empty
base URL and issues relative paths only.

**An empty base URL is this origin, never "no Conduit".** No Glass code tests the address for
truth. Found 8 October 2026: the canvas did, so the deployed Glass never asked for the node menu's
link counts and never offered links among the view or adding files, while every test, run with a
non-empty address, passed; and the map attached the token to its own Conduit reads only under a
non-empty address. Which of MapLibre's reads carry the token is decided by resolving the address
against the page's origin and matching that origin's `/v1/` (`map/conduitRequest.ts`), so a tile
server's URL never receives it. The keyboard harness runs the canvas in both shapes
(`?api=same-origin`).

What this replaces: `apps/workspace/src/App.tsx` resolved the address as
`import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"`, which Vite inlines during
`docker build`. Every image therefore shipped `http://localhost:8000` baked into its JavaScript,
invisible to every deployment made from it. A deployment that moved its published API port — which
§2.1's own Preflight actively encourages, and which that run had to do because an unrelated
container held 8000 — could not tell the Glass. Neither could a deployment on any host that was not
the browser's own `localhost`.

Why same-origin rather than a runtime configuration document, which was the alternative considered:
the bundle ends up holding **no address at all**, so it is portable across every deployment
unchanged rather than correctly configured in each; there is no cross-origin request left, so no
CORS policy to get wrong; and the Glass's boot stays synchronous, where fetching a `/config.json`
before first render would have made it asynchronous and changed `App.tsx`'s top-level constants and
the tests around them.

**The consequence for §3 and §7**: the Conduit no longer needs a published host port, and does not
get one. `network.expose_conduit: true` in `osprey.yaml` publishes it, off by default. §7 states the
posture; the enforcing tests are `test_the_conduit_is_not_published_by_default_and_is_when_asked_for`
and `test_the_bundle_built_for_a_deployment_contains_no_absolute_api_url`, the second asserted
against the built artefact rather than the source, because the source was never wrong.

#### 2.6.2 Signing in — ADR-050, and it blocks the milestone

**There is no sign-in.** `DEV_BEARER_TOKEN` is `import.meta.env.VITE_DEV_BEARER_TOKEN ?? ""`, and
`App.tsx` says so plainly: a real login flow is not yet built, and the
token is "a stand-in until a real sign-in screen exists, not a production auth path." Nothing has
owned building it yet. Every rendered deployment therefore serves a Glass that sends an empty bearer token
to a Conduit that correctly refuses it.

**ADR-050** is where this is decided: OIDC authorization code with PKCE against the realm §2.1.1
already renders, the Glass as a public client. It is **not** harness work and it is
**milestone-blocking** — the build plan's own sign-in stage carries the exit
test. Until it is built, the dev-token path is fenced so that no rendered deployment can carry it.

### 2.7 The reporting components — `report-sync` and Superset (ADR-111 Amendment 2)

Both are **off by default** and switched on in `osprey.yaml`:

```yaml
reporting:
  sync: true                  # run report-sync
  sync_interval_seconds: 900  # how often each case is pulled
  sync_memory: 256m
  superset: true              # run the reference dashboard
  superset_memory: 2g
```

Each is a container of its own with its own memory limit, outside the three tiers
(`harness/reporting.py`; `00_ARCHITECTURE.md` §1.4):

- **`report-sync`** runs the Conduit's own image with its entrypoint replaced
  (`python -m services.report_sync`) — the same code, not a second copy. Its health check is a
  heartbeat written after every pass; `--health` fails once it is two intervals old, so a hung loop
  is unhealthy rather than merely running. It reads `REPORT_SYNC_DASHBOARDS` (a JSON list of
  `{client_id, secret, weeks}`, one per dashboard identity registered in the Admin area — the secret
  is shown there once), `REPORT_SYNC_TOKEN_URL` and `REPORT_SYNC_CONDUIT_URL`, and creates the mart's
  read-only login from `REPORT_MART_READER` / `REPORT_MART_READER_PASSWORD`.
- **Superset** is `deploy/superset/`: the official image pinned by digest, plus psycopg2-binary (the
  recorded LGPL exception, §7 of `00_ARCHITECTURE.md`) and Authlib. Reached at `bi.` in front of the
  deployment's name through the front proxy, publishing nothing of its own (ADR-114 Amendment 4). Its start is idempotent: it makes its metadata database, migrates,
  and registers the mart as its one data source through the read-only login. People sign in through
  the realm's confidential client `osprey-superset` — the browser to the identity provider's public
  address, Superset's own calls (token, keys) to the internal one; the id_token's issuer is the public
  realm unless `SUPERSET_IDP_ISSUER` names another. Rate limits are counted in the deployment's Valkey.

**Embedded in the Glass (ADR-111 Amendment 3).** Superset runs with `EMBEDDED_SUPERSET`, a guest role
(`OspreyEmbedded`: read-only, the mart's schema only) and its own security policy as shipped plus the
Glass's origin as the one permitted framer (`SUPERSET_GLASS_ORIGIN`). At every start
`osprey_setup.py` puts the guest role and the local service user `osprey-embedder` in place; the
Conduit signs in as that user (`SUPERSET_INTERNAL_URL`, `SUPERSET_EMBEDDER_PASSWORD`) to issue guest
tokens signed with `SUPERSET_GUEST_TOKEN_SECRET`. Without these settings the Glass lists no boards.

**Secrets** — `REPORT_MART_READER_PASSWORD`, `SUPERSET_SECRET_KEY`, `SUPERSET_OIDC_CLIENT_SECRET`,
`SUPERSET_EMBEDDER_PASSWORD`, `SUPERSET_GUEST_TOKEN_SECRET` and an empty `REPORT_SYNC_DASHBOARDS=[]` — are minted at apply, only for what is switched on, and never
appear in the deterministic render. Every `make refresh` registers the `osprey-superset` client when
its secret is in `deployment.env`.

**Wiring a dashboard, end to end:** register it in the Admin area (Dashboards); put its client id and
the one-time secret into `REPORT_SYNC_DASHBOARDS`; a case's Author gives its account id Viewer in the
Share panel; the next pass pulls it (or restart `report-sync` for one now). The Admin area's Figures
column then says when it last pulled, or why it is failing.

**Known limits, recorded rather than hidden.** `make refresh` builds the Conduit's and the Glass's
images but not `osprey/superset:local`; after a change under `deploy/superset/`, build it
(`docker build -t osprey/superset:local deploy/superset`) and recreate the `superset` service. On
the local demonstration deployment, whose generated compose had drifted from a fresh render
(hand-edited ingest mounts), the two services and their settings were appended by hand with the
owner's agreement (11 October 2026) rather than re-rendering over the drift.

## 3. Standing it up on a laptop

```bash
docker run --rm -p 127.0.0.1:7100:7100 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$PWD:/workspace" \
  ghcr.io/ospreyflow/harness:latest \
  --config /workspace/osprey.yaml --out-root /workspace/deploy/generated
```

Then open `http://localhost:7100` and work through the six screens. For a laptop: choose
**local-lite** on Profile, accept the defaults on Components, Models and Governance, press
**Register a local provider** (or **Build local basemap**, once §2.2's own pipeline reaches a
machine with Java/planetiler — `harness/geospatial.py`'s own docstring has the current, disclosed
limit: this button is not yet reachable from inside the harness image) on Geospatial, generate and
confirm the artefacts, and let Preflight run. Click Launch, then **Seed demo data** on the screen
that follows.

Roughly fifteen minutes end to end, most of it pulling model weights and building tiles, with
progress shown throughout. The workspace is then at `http://ospreyflow.localhost` (ADR-114 Amendment 4: one address per
app, the identity provider at `id.`, the dashboards at `bi.`), its *Admin* area
included (ADR-110 Amendment 1). **The Set-up console stays at `http://localhost:7100`** — the
harness's own port, its screens served at the root; its old `/admin` placeholder for a post-launch
console is superseded by the workspace's Admin area.
The seeded demo credentials are displayed once and written nowhere.

**Afterwards, `make launch` is the way in.** It serves one page on `127.0.0.1:7070` with a tile each
for the Glass, the Ingest Studio, the Admin console — the Glass's Admin area, opened with
`?from=launcher&view=admin` — and the Set-up console, shows which answer, and starts one that does
not: the deployment by `python -m scripts.refresh` (also `make refresh`) against the
already-rendered `deploy/generated/<profile>/` — it writes the sign-in theme, builds the owned
images, runs `docker compose up -d --wait`, restarts Keycloak when the theme changed and registers
the sign-in accounts again, brings in a service the checkout renders and the deployment lacks, moves a
third-party service whose pin changed to the new image with its launch options and health probe
(ADR-101 Amendment 1), and never re-renders, removes a volume or seeds (ADR-049 Amendment,
29 September 2026) — the Set-up console by `python -m harness`. The Ingest Studio has no address of its own — it is a view of the Glass,
reached from the left rail — so its tile opens the workspace on the Ingest tab (`?view=ingest`), and both tiles carry
`?from=launcher` so the Glass carries the person's sign-in on without asking again
(`02_GLASS_FRONTEND.md` §2.2). The launcher reads only `OSPREY_WORKSPACE_PORT`
from `deployment.env`, so no credential reaches its page (`scripts/launch.py`,
`tests/test_launch.py`).

**Once a deployment has been rendered the launcher asks you to sign in first** (ADR-051), through the
realm's public client `osprey-launcher`, and then shows only the interfaces your roles allow: the
Glass to any signed-in account, the Ingest Studio to an account holding a role that grants `edit_pipelines` (Data Engineer, or a
legacy Studio role — `06_DECISIONS.md` ADR-112), the Admin console and the Set-up console to
`osprey-admin`. Before you
sign in it shows one tile, which is **Start OspreyFlow** when the stack is not running (the identity
provider is part of it, so it has to be startable first) and **Sign in** when it is. Starting the
Set-up console needs an `osprey-admin` session, which the launcher checks itself; hiding a tile is a
courtesy and is not what protects anything. Sessions are held in memory for eight hours from
sign-in, and `/logout` ends the identity provider's session too. Before any realm has been rendered
the launcher is open, as it always was. It must be served on port 7070 when sign-in is required.
Cookies are per host name, not per port, so the launcher's and the Set-up console's session cookies
(different names) are also sent to other services on `localhost`; on a machine you own that is a
known limit, not a hole to close here (`tests/test_launch_sign_in.py`).

**The bootstrap command above works as documented, with
no operator checkout at all.** `harness/render.
py`'s render step used to refuse by name (`MissingDockerfileError`) unless `services/api/Dockerfile`,
`services/ingest/Dockerfile` and `apps/workspace/Dockerfile` were present at the image's own
filesystem root — which `harness/Dockerfile`'s own header comment already says this image
deliberately does not carry. The fix is `osprey.yaml`'s new `components.source_path`
(`packages/schemas/deployment.py`): **undeclared, the default, the operator path** — each owned
service's own `image:` is a pull-mode registry reference, pinned by the digest `versions.lock`
records, and the render step never looks for a local Dockerfile at all. Declared (to a checkout
root containing the three Dockerfiles above) — **the developer path** — renders exactly as before:
a `build:` stanza, a local tag, `versions.lock`'s own `local-build` entry. Confirmed directly
against the real, rebuilt image with only an empty workspace mounted (`tests/harness/
test_harness_image.py`'s own case): render succeeds, the rendered `compose.yaml` carries no
`build:` stanza for any owned service, and `docker compose config` validates it.

**The developer path, for this repository, CI, and the exit tests below: `--build` on either
headless command**, or declare `components.source_path` in `osprey.yaml` directly.

**From a fresh clone, in full — corrected after running exactly
what this section used to say and watching it fail.** The three lines before the `apply` command
were missing entirely: this document jumped from "clone it" to "run it" with no environment step,
and the command as written raised `ModuleNotFoundError: No module named 'schemas'` because
nothing puts the repository root and `packages/` on `sys.path`.

```bash
git clone https://github.com/ospreyflow/ospreyflow-dev.git && cd ospreyflow-dev
uv sync                       # creates .venv from uv.lock; ~30s warm, a few minutes cold
export PYTHONPATH=.:packages  # the repo root AND packages/ — neither is installed on the path

.venv/bin/python -m harness.apply --profile local-lite --build --seed hmp,fixture-corp,scenarios
```

`PYTHONPATH` is the same requirement `DEMO_GUIDE.md` §3.2 already spells out for the Conduit
("neither a bare `python -m` nor `uvicorn` puts them on `sys.path`, which is why
`services/api/Dockerfile` sets it explicitly") — it applies here too, and saying it only there
was the gap.

**The three seed datasets, and what each is for.** `--seed` takes a comma-separated list:

| Dataset | What it seeds | Which acceptance rows need it |
| --- | --- | --- |
| `hmp` | The incident/event corpus and its yards | Scenario A's analytics rows (A2–A5, A8–A12) |
| `fixture-corp` | Resolution cohorts, community rings, the path-spoke hub | B4, B5, B9–B11, B21 |
| `scenarios` | Scenario B's person layer, the shared handle, the seized handset and its SIMs, and the device's sightings | B7, B8, B15, B16–B18 |

`scenarios` was added on 27 September 2026 under **owner ruling R8**, which set the bar that every
acceptance row must be performable through the analyst's own door on a rendered deployment — a row
proven only in process does not count. Before it, those rows had no data to walk against on a real
deployment at all. Seeding is still run from a checkout (`apply` mounts the seed scripts from it), but the
synthetic generators the seeds call are now in the image (`packages/demo_fixtures/`, ADR-054), not
in the test tree, and re-seeding `scenarios` is idempotent: it pins its own ids, so a second
seed upserts the same elements rather than building a second, parallel cohort.

**Each seed writes into its own dataset** (`demo_fixtures/datasets.py`: Enron, Fixture Corp, HMP,
PaySim, the acceptance scenarios; ADR-099 Amendment 2), and the case it seeds reads that dataset; a
dataset of that id held by another unit is refused. **A deployment that held data before ADR-099** runs
`python -m scripts.stamp_datasets --dry-run`, then without `--dry-run`, inside the deployment: it
stamps what each seed loaded by its provenance, gives each case its datasets, stamps what analysts
wrote onto canvases, rewrites the working set's copies, and places link-type proposals and alerts in
their case's dataset (Amendment 5). It ends by counting what is still in no dataset, which no case
reads until something claims it. Each step is safe to run again.

**Where source files go — the ingest folder.** A rendered deployment bind-mounts
`components.storage.ingest` (default `/var/lib/osprey/ingest`) **read-only** into the Conduit, for
every profile, with one exception laid over it (ADR-067): its `uploaded/` sub-folder is mounted
writable, which is where files an analyst uploads from the browser land. On Linux the host
`uploaded/` folder must be writable by the Conduit's user (uid 10001):
`sudo mkdir -p /var/lib/osprey/ingest/uploaded && sudo chown 10001 /var/lib/osprey/ingest/uploaded`.
A Docker Desktop host (macOS, Windows) maps ownership itself and needs only the folder to exist —
and it must exist *on the host*: on macOS the default `/var/lib/osprey/ingest` does not, and Docker
Desktop then mounts an empty folder from its own VM, which the Studio lists as "no files on the
server yet". Set `components.storage.ingest` to a folder in the operator's home there. A deployment
rendered before ADR-067 has no writable `uploaded/` mount at all, and `make refresh` does not
re-render it; an upload to it is refused with a 503 (found 9 October 2026). That folder is what the Ingest Studio's Connect stage lists, so an analyst picks a
file from it rather than typing a path — and in a rendered deployment there is no path they could
usefully type, because `source_location` is read inside the Conduit's own container. Put source
files there, as the operator, before asking an analyst to ingest anything:

```bash
sudo mkdir -p /var/lib/osprey/ingest
sudo cp carrier-a-cdr.csv device-extract.xml /var/lib/osprey/ingest/
```

For the synthetic demo source files this repository ships, there is a module rather than a copy —
they are generated, so there is nothing to copy from a checkout:

```bash
PYTHONPATH=.:packages .venv/bin/python -m scripts.seed_ingest_folder \
  --osprey-config deploy/generated/local-lite/osprey.yaml
```

The Conduit writes only to its `uploaded/` sub-folder (ADR-067), never to the rest. Set a different location on the harness's Components screen
(`§2.1`), or in `osprey.yaml` directly; Preflight reports the folder's state and free space, and
the generated `RUNBOOK.md` names it. An analyst without the `source_author` Studio role cannot
list it at all. Owner ruling R6, 27 September 2026; `09_INGEST_STUDIO.md` §2 has the route and
what it refuses. A browser upload writes into `uploaded/<dataset>/` (ADR-067, ADR-099 Amendment 4);
Map's two recorded gaps remain post-milestone.

**Add `--demo-analyst` if you intend to sign in.** The command above provisions no user, so the
Glass has nobody to authenticate as; the flag creates a disposable analyst subject and writes its
password beside the rendered artefacts, which is what "the seeded demo credentials are displayed
once" above refers to. Omitting it is right for a headless exit test and wrong for a demo.

**The pull path's own registry reference resolves for a real customer, with
no flag.** `.github/workflows/release.yml` builds, trivy-scans and pushes all four owned images
(`api`, `ingest`, `workspace`, `harness`) to `ghcr.io/ospreyflow/<service>:<sha>` on a version tag,
tagged by the exact commit `harness.render.git_sha()` computes — including for the harness image
itself, which carries no `.git` (its own Dockerfile's header says so) and so needs that commit
baked in at build time (`--build-arg OSPREY_BUILT_FROM_SHA`) to compute the same tag a pull-mode
render resolves against. `render`'s own default resolver (`daemon_then_registry_digest_resolver`)
checks the local daemon first, then the image's own registry — no local pull needed — so a bare
customer laptop resolves a real, published digest on its very first render. `--allow-unpinned`
remains what it always was: a **developer** flag, for a machine with no Docker daemon at all or a
checkout with no release yet, never the customer-facing remedy (§5, §7).

What is running afterwards: the workspace, one Conduit, three workers, ArcadeDB, DuckDB
in-process, Valkey, MinIO, OpenSearch single-node, PostgreSQL, Keycloak, Ollama, and a
faster-whisper container. Twelve containers, roughly 11 GB of RAM at rest. Since 6 October 2026 also `ner`,
the fast named-entity recogniser (ADR-098 decision 2): Stanza 1.10.1 on the CPU with its English model in
the image (about 1.2 GB on disk, under 1 GB of RAM), on the internal network only; the Conduit is told
`OSPREY_RECOGNISER_URL` and does not wait on it, so without it only *Extract entities* is unavailable.
`make refresh` brings it, and any service a later render adds, into an existing deployment without
re-rendering it.

**Correction, 24 September 2026 — the model gateway is missing from this list, but it is *not* why
the Conduit would not start.** An earlier version of this paragraph said the Conduit fail-fasts
against an absent model gateway. **That was an inference from a partial traceback and it was
wrong.** The exception was `asyncpg`'s, not the model client's: the Conduit could not reach
**PostgreSQL**, because `services/api/config.py` defaults `POSTGRES_PORT` to 5433 — a workaround for
the development stack publishing there — while a rendered container listens on 5432. The model
client is constructed during startup but **opens no connection**, so it cannot have raised it. The
real fault is fixed; this paragraph is the correction, left in place rather than quietly rewritten.

**The list does still omit the model gateway, and that remains a real gap — Proposed.** A decision
on this was taken and **withdrawn by the
owner**, because its premise was the misdiagnosis corrected above: the gateway was never why the
Conduit would not start. It returns here on its own merits, to be decided separately.

**The proposal:** the Conduit tolerates the gateway's absence. ModelPort-backed routes return a
typed "model backend unavailable" error rather than a silent result, Preflight reports the gateway
absent, and when `osprey.yaml` enables models the renderer includes the gateway beside Ollama —
thirteen containers with models on, eleven off. **The argument for it, which is not the argument it
was first decided on:** §1 makes models optional at `local-lite` ("Ollama, CPU or one consumer
GPU"), so a deployment that refuses to start without a model backend refuses to start over an
optional component. **Not decided**, and deliberately not built.

**A provisional measurement for the "roughly 11 GB at rest" figure above, 24 September 2026 —
recorded as provisional on the owner's own instruction, and it should not be quoted as settled.**
Eleven of the twelve containers reached health on a 9.7 GiB Docker VM at a **peak total of 3.6
GiB** — ArcadeDB 2.0 GiB, OpenSearch 0.9 GiB with its heap capped at 512 MiB by the renderer,
Keycloak 0.6 GiB, everything else under 250 MiB each.

**Two reasons it is provisional, both named by the owner:** it was taken with **the Conduit exited**,
so the one long-lived Python process in the stack contributed only its startup footprint before
dying; and **ArcadeDB was below its schema-creation floor**, which this document's own §8 records as
the point where its memory climbs and does not come back. A re-measurement with the Conduit up is
owed. The 11 GB estimate is left as written until then.

**Read "three workers" as three replicas of the job worker — owner's decision, 24 September
2026.** There is one worker *implementation*, a generic dispatcher keyed by job type (ADR-025), and
three replicas of it is what the code is shaped like rather than three distinct worker services.
The entrypoint it needed now exists (`python -m services.api.worker_main`), and each replica takes
a distinct consumer name from its hostname — which is the property the arrangement actually rests
on, since Valkey's consumer group delivers each entry to exactly one consumer but keys its
pending-entries list by consumer name.

**What "wait for health" waits on — owner's decision, 24 September 2026.** The Conduit exposes
`GET /healthz`, unauthenticated, fixed body, touching no store and disclosing nothing (§3.0 of
`03_CONDUIT_MIDDLEWARE.md` has the route and the reasoning), and its image declares a health check
against it. The Glass's image declares one too. **The batch loader declares none**, because a job
that runs once and exits has no health to report and a check on it would be a permanently-failing
gate. The deploy waits on **liveness**: readiness stays authenticated and is a different question,
and a deploy that waited on readiness would be waiting on the identity provider to answer before it
could tell whether its own processes had started.

If Preflight finds less than 16 GB it offers a reduced variant that drops OpenSearch and falls
back to PostgreSQL full-text, stating the trade-off on screen: search quality degrades and
semantic search is unavailable, and the platform otherwise works. It is offered, not applied
silently.

## 3a. Small on a cloud's managed services (ADR-114 decision 8, Amendment 10)

A `small` deployment names what the cloud runs for it in `osprey.yaml`'s `external:` section; what it
names is not rendered as a container. `osprey.yaml` still holds no secret: every password and key
arrives at apply from the environment, put there by the server's first boot from the cloud's secret
store (Secrets Manager, Key Vault) with the server's own identity.

```yaml
profile: small
external:
  postgres:                 # RDS / Azure Database for PostgreSQL; password: OSPREY_POSTGRES_PASSWORD
    host: osprey-db.abc.eu-west-2.rds.amazonaws.com
    port: 5432
    database: ospreyflow
    user: osprey
    sslmode: require
  object_store:             # AWS only: S3 for staging, site images, the tile cache, backups, media
    endpoint: s3.eu-west-2.amazonaws.com
    region: eu-west-2
    credentials: instance   # the server's role; no key anywhere
    bucket_prefix: osprey-small-   # each bucket is <prefix><name>
  media:                    # Azure only: media on Blob; key: AZURE_STORAGE_KEY
    blob_account: ospreymedia1a2b
    blob_container: media
```

- **Postgres external** — no `postgres` container; Keycloak and the one-shot step that makes its
  database reach the managed server over TLS; the deployment's own login needs `CREATEROLE` and
  `CREATEDB` there (RDS's master user and Azure's administrator have both).
- **Object store external (AWS)** — no `objectstore` container; every S3 client uses the server's
  instance role (pyarrow's default credential chain) in the named region, over HTTPS.
- **Media on Blob (Azure)** — the Conduit's media store is the Blob adapter; SeaweedFS stays on the
  server for the S3-protocol stores (Amendment 10 point 2).
- Any container that reaches a managed service joins the `egress` network (Amendment 7): reaching
  it is a configured feature's need.
- `object_store.credentials: keys` instead reads `OSPREY_S3_ACCESS_KEY` and `OSPREY_S3_SECRET_KEY`
  at apply, for an S3 store that has no instance identity to offer.
- **How a Small server comes to exist** (Amendment 10): `ospreyflow install --mode small --cloud
  aws|azure` runs OpenTofu (`deploy/opentofu/small/<cloud>`, state in `.cloud/` of the checkout,
  owner-only) — plan, then apply on confirmation; the server's first boot reads its passwords with
  its own identity, installs onto the services above, and leaves the first administrator's one-time
  code (`harness.first_admin`, made with Keycloak's own `kcadm.sh` inside its container) in the
  cloud's secret store; the operator's command waits for the name and the server, shows the code
  once and deletes it. Servers start at 32 GB: a nominal 16 GB machine shows its system less than
  Preflight's 16 GiB floor.
- **`ospreyflow backup` refuses a deployment with an external Postgres**, in words: the cloud's own
  backups (AWS Backup, RDS snapshots, Azure Backup) protect it, and a dump from inside the server
  would be a second, unscheduled copy no one restores from.

## 3b. Enterprise on Kubernetes (ADR-114 decision 9, Amendments 10, 12 and 13)

`profile: cluster` renders no compose file. `harness.render` writes `deploy/generated/cluster/`:
`values.yaml` for the chart `deploy/helm/ospreyflow`, and its `versions.lock`. **Every workload in it
is translated from the compose stanza Lite and Small are written from** (`harness/cluster.py`):
image, environment, command, health check, files and volumes; a cluster then changes only what a
cluster changes (replicas, the stores' clustering, the job workers, what the cloud runs). One
renderer, so a cluster and a laptop cannot disagree about what a service is. The configuration files
Lite writes beside its compose file (`osprey.yaml`, `Caddyfile` without the loopback doors,
`realm.json`, `litellm.yaml`, `glass.json`, the sign-in theme) are in `values.yaml` itself, since a
chart reads no file outside it; the chart carries them as one ConfigMap, and Lite's `deployment.env`
as another. The Kubernetes service names are the compose service names, so every rendered address
works unchanged. The chart is generic: it creates nothing from its own defaults.

A cluster runs ClickHouse and ArcadeDB and pulls the release's images: `analytics_engine: duckdb`
(each replica would keep its own events), `graph_store: janusgraph` and `source_path` are refused in
words.

**What the cloud runs** (`external:`, §3a, all required at `cluster`): PostgreSQL, Valkey
(`external.valkey`: host, port, TLS — ElastiCache or Azure Cache for Redis), and the object store
(`object_store` on AWS, `media` plus in-cluster SeaweedFS on Azure, as Small). Search is
`external.search` (Amazon OpenSearch Service) on AWS, and OpenSearch in the cluster on Azure, which has
no managed one (decision 9).

**What the chart runs:**

| Workload | Kind | Replicas | Notes |
| --- | --- | --- | --- |
| `workspace`, `api`, `report-sync`, `superset` | Deployment | 2 | Stateless; the Conduit's state is in Valkey and the stores |
| `worker` | Deployment | 3 | The job worker; each replica its own consumer name (its pod name) |
| `proxy` | Deployment + LoadBalancer Service | 2 | Caddy, the same routes; its certificates on a shared volume |
| `keycloak` | StatefulSet + headless Service | 2 | Clustered: caches over JGroups, found through the headless Service |
| `arcadedb` | StatefulSet | 3 | Raft (`arcadedb.ha.*`), each on its own volume |
| `clickhouse`, `clickhouse-keeper` | StatefulSet | 2, 3 | A replicated table set, coordinated by Keeper |
| `opensearch`, `objectstore` | StatefulSet | 1 | Only where the cloud has none (Azure) |
| `ollama`, `litellm`, `ner`, `whisper` | Deployment | 1 | Models; `ollama` may name a GPU node pool. vLLM (decision 11) is not built: it needs the models in another format |

**How the Conduit uses the replicated stores** (measured on the images the chart runs, 14 October
2026):

- **ArcadeDB is written through its leader.** The chart sets `ARCADEDB_HA=true`; the client asks the
  `arcadedb` Service which node leads and sends every request there, saying `eventual` (ADR-101
  Amendment 2: on 26.10.1 with the Groovy engine a Gremlin command sent anywhere else, or without
  `eventual`, either loses its parameters or runs twice). The servers name each other by the headless
  Service (`arcadedb-N.arcadedb-headless:2434:2480`), which is the address `/api/v1/cluster` hands back.
  The followers are standby: an election refuses writes for some seconds, in words, and loses none.
- **ClickHouse is one shard of two replicas.** The chart sets `CLICKHOUSE_CLUSTER=osprey` and gives
  each server its `{shard}` and `{replica}` macros, the `osprey` cluster and the three Keepers. The
  Conduit makes its database `ON CLUSTER osprey` with the `Replicated` engine, and the tables
  `ReplicatedMergeTree` (`adapters/analytics_clickhouse/schema.py`): a plain `MergeTree` in that
  database had its definition on both servers and its rows on one, so the servers' profile also sets
  `database_replicated_allow_only_replicated_engine`, which refuses one. An insert reached the other
  replica within 50 ms; a mutation (`mutations_sync = 2`) is on both when it returns. The analytics
  conformance suite passes on the pair unchanged.

The ingest folder and the recipes repository are one shared volume (ReadWriteMany) mounted by every
Conduit replica, as Lite mounts a host folder. **Secrets** are never in `values.yaml`: the chart reads
one Kubernetes Secret (`secrets.name`, `ospreyflow-secrets` by default) holding what `deployment.env`
holds on Lite, which the install creates. Every image is pinned by digest from the release's lock.

**Translated, in particular** (Amendment 13):

- A compose `${VAR}` becomes a read of the Secret, or of the environment ConfigMap when the render
  writes it there; one inside a longer value is defined first and named as `$(VAR)`, which Kubernetes
  expands only from earlier entries.
- A one-shot step becomes a **Job** when it reaches out (the model downloads: the server reading case
  content keeps no route out, and a policy is per pod), and a service that waited for it waits for
  the Job's mark on the volume they share; Keycloak's database step runs **before Keycloak**, in its
  pod, at every start, as compose runs it at every `up`.
- The networks become **NetworkPolicies**: every pod reaches the deployment's pods and the cluster's
  DNS; what Lite puts on its `egress` network (and the job workers, which reach the managed Valkey)
  may reach out; only the proxy is reached from outside, through the one LoadBalancer.
- The job workers run the release's own images (`worker`, `report-sync`), as does Superset, which
  the release now builds beside the Conduit; the Conduit and the workers reach a managed Valkey with
  its password (`VALKEY_PASSWORD`, in the Secret) over TLS (`VALKEY_TLS`).

**Not in the chart yet:** resource requests and limits; a GPU node pool for `ollama` (a workload may
carry a `nodeSelector`, which nothing sets); the on-demand loader (`ingest`), which Lite runs with
`compose run`; the update notice (`state/`, written on a Lite host); and two Conduit replicas share
the recipes repository on the shared volume, where one at a time publishes safely and two at once
are not yet guarded.

**The install** (Amendment 16): `ospreyflow install --mode enterprise`, from a machine whose
`kubectl` and `helm` reach the cluster, with the answers naming the managed services (`external:`)
and the cluster's `namespace` and `shared_storage_class` (`cluster:`). It renders the values, makes
the namespace and the Secret (minting only what is missing, keeping every value already there),
installs the chart and waits for it, configures the identity provider through a port-forward, makes
the first administrator with a one-time code, and says where the deployment answers. Run again, it
changes no password and replaces no account. A site's own Helm values go in with `--chart-values`.

**Proved in a running cluster** (Amendment 14): k3s with the cloud's services stood in for — the
stores formed their clusters and kept them through a restart, the Conduit was reached by name
through the one load balancer, the policies refused what they should, and the Conduit's client
followed a new ArcadeDB leader and wrote once.

**The chart's test** (Amendment 10 point 5; `make chart-check`): `helm lint`, and the chart rendered
with `helm template` from the values both clouds produce, validated against Kubernetes 1.31's schemas
(kubeconform, strict), with no Secret, no workload for any store the cloud manages, every store on
volumes of its own and its peers named by a headless Service, every Service selecting a workload,
every `$(VAR)` defined before it is named, nothing but the proxy published, and only what needs a
route out given one (`tests/harness/test_helm_chart.py`, `test_cluster_render.py`); every image a
pulled deployment names is one the release builds (`test_release_matrix.py`); and the proxy's own
health check passes against the real Caddy on HTTPS and HTTP (`test_proxy_health.py`).

## 4. Moving up a profile

The migration path is the property that makes the setup-time choices safe, so it is specified
rather than assumed.

**Laptop to small, or small to cluster:**

1. **Back up** from the Admin area (designed: ADR-110 Amendment 1 puts post-launch operations there),
   or `osprey backup`. Writes a portable bundle: staged
   Parquet, object store contents, Postgres dump, ontology, handling scheme, and `osprey.yaml`.
2. **Change profile** in the harness. It loads the existing `osprey.yaml` and re-opens only the
   screens whose answers are invalid at the new profile, marking the rest as carried forward.
3. Review the regenerated artefacts and launch the new environment empty.
4. **Restore** the bundle. This replays staged Parquet through load and index rather than copying
   graph-store internals between engines.

Point four is the whole reason for the staging layer. Migration is a replay of staged data
through the ingest pipeline's final stages, so it works between any pair of engines, revalidates
against the current ontology, and never depends on one engine's on-disk format. It is slower
than a binary copy and it is the only version that is actually portable.

**Estimate the replay before running it.** Restore opens with a dry run showing the row count and
a projected duration, and will not proceed until that estimate is acknowledged. A national-scale
replay is measured in days and must be planned, not discovered.

## 5. Upgrades and vulnerability response

The maintainability requirement, made concrete.

- **Every image is independently versioned.** No service pins another's major version. The only
  shared pin is the port contract version in `packages/ports`.
- **How a customer gets `versions.lock`'s own digests.** They do not fetch it
  separately: `.github/workflows/release.yml` publishes the three owned images to
  `ghcr.io/ospreyflow` on every version tag, and `harness.render`'s own default resolver finds
  those digests over the network the moment a render runs, the same way it has always resolved a
  third-party image. `--allow-unpinned` is a developer flag (no Docker daemon, or a checkout ahead
  of any release) — never the customer path, and never required once a release has been cut.
- **Renovate** raises dependency pull requests continuously. CI runs the conformance suites on
  every one, so an upgrade that breaks a port contract is visible before merge.
- **Weekly** — `trivy` scans every image; anything critical or high raises an issue
  automatically.
- **Rolling a single component** is to be a screen in the Admin area (designed, ADR-110 Amendment
  1): pick the component, pick the target version, and it runs preflight, rolls the container or the Kubernetes
  deployment, then runs **verify** — the port conformance suite against the *running* deployment
  rather than a test fixture. Under two minutes, and it is what makes the upgrade safe rather
  than hopeful. The headless equivalent is `osprey upgrade opensearch --to 3.2.1 && osprey verify
  opensearch`.
- **Upgrading ArcadeDB on a kept store** (ADR-101 and its Amendment 1, done on the owner's deployment
  on 7 October 2026 from 25.5.1 to 26.10.1): (1) back up first (`BACKUP DATABASE`, copied off the
  volume), since a minor-version downgrade needs an export and re-import, not the old image; (2) if
  the new image runs as another user (25.5.1 uid 1001, 26.10.1 uid 1000), hand the volumes to it in a
  one-off container (`chown -R`), or the server stops at start before opening a database; (3) replace
  the config volume's untouched defaults with the new release's, keeping `server-users.jsonl`;
  (4) `make refresh`, which moves the pinned service to its new image with its launch options and
  probe (it does not do step 2); (5) `CHECK DATABASE`, and remove duplicates by id (never by record
  id alone: two copies can share a stored chunk, and deleting one breaks both) or with
  `CHECK DATABASE FIX`, until it reports 0 errors; (6) `REBUILD INDEX *`, which a duplicate in a
  unique index would otherwise drop and fail to rebuild.
- **Rollback** is one click to a previous digest, then verify again. `deploy/versions.lock`
  records every digest that has been live, so there is always a known-good target.
- **Airgapped upgrades** — `osprey bundle --images` produces a signed tarball of every image and
  weight file for transfer to a disconnected environment, where the harness runs from the bundle
  rather than from a registry. This path must be tested each release, because it is the path that
  will be needed under time pressure.

## 6. Backup and recovery

| What | Frequency | Method |
| --- | --- | --- |
| Staged Parquet | Continuous | Object store replication |
| PostgreSQL | Hourly WAL, nightly full | `pg_basebackup` |
| Graph store | Nightly | Engine-native snapshot |
| Analytics database | Nightly | File copy from the data volume |
| OpenSearch | Nightly | Snapshot repository to object store |
| Configuration | On change | Version control |

**The graph store and the search index are both rebuildable from staged Parquet.** Their backups
exist to shorten recovery, not to make it possible. State the recovery time for each path in
`deploy/RUNBOOK.md` and test the long path — full rebuild from staging — at least annually.
A backup nobody has restored is a hypothesis.

Audit data is the exception: it is not rebuildable and it is not deletable. Replicate it
separately, with its own retention policy set by the deployment's legal basis.

### 6.1 How secrets are re-supplied on a restore — DECIDED, 25 September 2026

**A backup carries no secrets. A restore re-mints them. Nothing in a backup may ever be encrypted
with a deployment-scoped key.** That last sentence is the load-bearing one and it is repeated as a
standing constraint in §7, because it binds every future feature rather than only the restore path.

The problem this settles: every credential is minted at apply
time into the generated, gitignored environment file (§2.5, §7 — "never in `osprey.yaml`, never in
an image"), so a restore lands old data in a **new** deployment holding **new** secrets, and
nothing reconciles the two. It worked, and only because nothing in the backed-up data was
encrypted with a deployment secret. The moment anything were — a stored connector credential, an
export ledger entry, an at-rest volume — a restore would begin to succeed while producing data
nobody can read, which is the worst available failure mode because it reports success.

The decision forecloses that by constraint rather than by machinery: there is nothing to
re-supply, so there is nothing to get wrong. What it costs is that this deployment may not encrypt
anything at rest with a key of its own. A connector credential that must survive a restore is
therefore held by reference — an environment variable name or a secret-manager path, which is what
§2.5 already requires of the harness — and never as ciphertext in a store.

**For `cluster`, the answer is different and not yet built.** Holding secrets outside the
deployment, in a secret manager the restored deployment is pointed at, is recorded as the cluster
profile's approach. It does not apply to `local-lite` or `small`, where standing up a secret
manager to restore a laptop would be machinery in place of a constraint.

### 6.2 What the current implementation does and does not satisfy

`deploy/RUNBOOK.md` is the operational document; this is the specification's own ledger of where the
build stands against the table above:

- **`pg_dump`, not `pg_basebackup`.** The table names the latter. `local-lite` has no WAL archive to
  ship and a physical copy is tied to the server's page layout, so the implementation takes a
  logical dump. A `small` or `cluster` profile must revisit it.
- **The analytics DuckDB is in the backup set and in no row of the table above.** It holds every
  event `/v1/analytics/*` reads and is not rebuildable from the graph store. The table should gain
  a row for it.
- **Audit data is not separately replicated.** `audit_log` shares a PostgreSQL instance with sites,
  monitors, alerts, the export ledger and the review queue, so it shares their retention and their
  backup. §2.4's destroy confirmation assumes the opposite. A deployment whose legal basis requires
  this section's behaviour does not have it.

## 7. Security posture

- Every service on an internal network. Only the workspace and the Conduit are exposed, behind a
  reverse proxy terminating TLS. **Since 25 September 2026 the workspace's own image *is* that
  reverse proxy for the Conduit** (§2.6 item 1): its nginx proxies `/v1` and the delta WebSocket to
  `api:8000` on the internal network, so a normal deployment publishes **one** port and the Conduit
  is reachable without being exposed. `network.expose_conduit: true` in `osprey.yaml` publishes it
  as well — off by default, for an operator debugging the Conduit directly or for a second client
  that is not the Glass — and turning it on widens the exposed surface by a whole tier.
- **Nothing in a backup may be encrypted with a deployment-scoped key** (§6.1, decided 25 September
  2026). A backup carries no secrets and a restore re-mints them, so any value encrypted with a
  key that dies with the deployment would restore as unreadable bytes — a restore that reports
  success and returns nothing. This constrains every future feature that might want to encrypt
  something at rest, which is why it is stated here rather than only in §6.
- Default-deny egress. The model gateway is the only component with a documented exception, and
  the exception is off by default (`04_VAULT_BACKEND.md` §4).
- Secrets from the environment or a secret manager, never in `osprey.yaml`, never in an image.
- Containers run as non-root, read-only root filesystem, no capabilities beyond the defaults.
- Images signed and verified at pull; digests pinned in `deploy/versions.lock`. For the three
  OspreyFlow-owned images, that pin now comes from a real published release (
  `.github/workflows/release.yml`, §5 above), resolved over the network rather than assumed.
- Audit written to a separate volume with a separate retention policy and separate access.
- No telemetry leaves the deployment. OpenTelemetry collection terminates inside it.

## 8. A running instance will need periodic restarts — the interval is not yet known

**Found 23 September 2026, measured directly against the real `local-lite` graph store, not
inferred.** Across a sequence of closing-pass runs against the same, never-reset ArcadeDB
database — the same store every profile uses — memory climbed with every successful run
(8.651GiB → 9.097GiB → 9.396GiB) and never gave any of it back, and the same fixture load took
measurably longer each time it ran (117s → 151s → 203s, a 74% slowdown by the third repetition of
an identical workload against the same, larger database). **This happened while every one of
those runs passed** — this is not a bug that fails loudly; it is a live store that neither
reclaims memory across workloads nor holds its own query performance steady as data accumulates.
In any real deployment, data always accumulates — an investigation is added to, not replaced.

**Cause found, and largely fixed — this section is narrowed, not
withdrawn.** The mechanism behind "never gave any of it back" is now named: ArcadeDB **24.11.1**
retained memory per *database lifecycle*, independent of workload. Isolated to its smallest form,
five bare `create` → `apply_schema` → `drop` cycles — writing no data, running no query — took the
server from **141.7 MiB to 8.2 GiB**, and dropping the database returned none of it. Raising the
JVM heap was measured **not** to help (the live set simply grew with it), and neither did bounding
`arcadedb.dbPageCacheSize`.

**Fixed upstream in ArcadeDB 25.5.1**, the pinned version until ADR-101 moved the pin to 26.10.1 (an index defect of 25.5.1's); the figures below are of 25.5.1 and have not been repeated on 26.10.1. The identical reproduction
plateaus at ~1.5 GiB and stays flat (1.499 GiB at five cycles, 1.516 GiB at twenty), and the
six-cycle sustained-load curve improves accordingly, measured on the same host with the same
workload:

| | ArcadeDB 24.11.1, `-Xmx6G` | ArcadeDB 25.5.1, `-Xmx8G` |
| --- | --- | --- |
| ArcadeDB RSS, cycle 1 → 6 | 6555.6 → 7174.1 MiB | **2165.8 → 2470.9 MiB** |
| growth per cycle | 123.7 MiB | **61.0 MiB** |
| heap used at cycle 6 | 5201.9 / 6144 MiB | **976.5 / 8192 MiB** |
| query latency, cycle 6 ÷ cycle 1 | 1.29× | **1.12×** |

The full curve for both versions is kept alongside this record.

**What this does not settle, and why the section stays.** Growth per cycle is halved and
flattening (cycles 5→6 added 7.2 MiB), not zero — so a long-running instance still accumulates,
and **the safe restart interval is still not known**. What has changed is that the accumulation
no longer has an unbounded component that exhausts the heap outright, and the degradation this
section was first written from (117s → 151s → 203s on an identical workload) had that component
in it. Re-measuring the original three-run sequence against 25.5.1 is the work that would let this
section be closed rather than narrowed; it has not been done.

**Re-measured — §8 STAYS OPEN.** The original closing-pass fixture
load is no longer runnable as written (`test_phase8_exit_over_the_wire.py` supersedes it); the
sustained-load harness's own per-cycle load is the fallback the brief names, run fresh against a
`local-lite` deployment on the then-current pin (`25.5.1`, `-Xmx8G`; the pin is now 26.10.1, ADR-101,
and this has not been re-measured), never torn down between cycles:

| Cycle | ArcadeDB RSS (`docker stats`) | Query-sample wall time |
| --- | --- | --- |
| 1 | 2620.4 MiB | 0.26 s |
| 2 | 2737.2 MiB | 0.16 s |
| 3 | 2837.5 MiB | 0.16 s |
| 4 | 2882.6 MiB | 0.15 s |
| 5 | 2912.3 MiB | 0.20 s |
| 6 | 2993.2 MiB | 0.20 s |

**Wall time is flat within noise** (0.15–0.26 s across all six — this is the light, fixed query
sample the harness runs, not the closing-pass walkthrough §8's own original figures came from;
`test_arcadedb_memory_and_query_latency_under_sustained_ingest_cycles` already draws that
distinction). **RSS does not plateau over three cycles, or six**: +116.8 MiB (1→2), +100.3 MiB
(2→3), +74.6 MiB/cycle on average across all six — the same order of magnitude as the ~61 MiB/cycle
this section already recorded, not a new number, but not flat either. Under this round's own
closure test (flat wall time **and** plateaued RSS), that fails on the RSS half, so **§8 stays
open** rather than closing.

**A first estimate of the restart interval, from these six points, labelled as an estimate and
nothing firmer.** This host's Docker VM reports 19968.0 MiB total (`docker info`); the sustained-
load test's own already-decided ceiling is 85% of that, 16972.8 MiB. At cycle 6 (2993.2 MiB) that
leaves 13979.6 MiB of headroom. At the six-cycle average growth rate (74.6 MiB/cycle), the ceiling
is reached around **cycle ~193** of this specific, light workload; at the steeper cycles-1–3 rate
(~108.5 MiB/cycle), around **cycle ~135**. Neither number is a restart-interval recommendation on
its own — this workload seeds a fixed, small fixture every cycle, not the growing working set a
real investigation accumulates — but both say the same thing directionally: this is a long runway
at this workload's scale, not an imminent ceiling, and the growth is real and unbounded so far
measured, not settled. Two upstream issue drafts for the ArcadeDB tracker — this section's own leak and the readiness-endpoint finding beside it — are kept internally, for the owner to file.

**The operational consequence, stated plainly:** a running instance should be expected to need
periodic restarts to recover memory, and **the safe interval between them is not yet known** —
nobody has measured how far this degradation goes, whether it plateaus at some working-set size
or continues climbing without bound toward the same resource ceiling that a single heavy session
can already reach on its own (a separate, single-session measurement closed against a
fresh-install criterion sits alongside this finding, not on top of it; this finding is what
happens *after* a fresh install, under continued real use, and neither measurement answers the
other's question).

**Built — `tests/harness/test_sustained_load.py::test_arcadedb_memory_and_
query_latency_under_sustained_ingest_cycles`. Full account: methodology, the six-cycle curve, a real defect found
(`seed_fixture_corp.py` is not safe to re-seed against the same database — `GraphArcadeDBAdapter.
upsert_nodes` is insert-only), and a platform-dependence finding about `ramOsUsed`/`ramOsTotal`
being the Docker Desktop VM's own memory on macOS rather than this container's cgroup scope.**
Six real cycles against the rendered `local-lite` deployment (not `dev.yaml`) found `docker
stats`'s own container-scoped RSS growing far more slowly and non-monotonically (≈113MiB/cycle
average across six cycles) than this section's own dev.yaml figures above (≈250-350MiB/cycle,
climbing steadily) — not a contradiction of the finding above, which stands as measured against
`dev.yaml`, but a real, disclosed difference in degree between the two deployment shapes and
workloads that a reader comparing the two figures should not average together. Query-sample
latency showed no growth trend across six cycles, though the fixed query sample this test runs
(geobins, one Search Around, one pathfinder call, three resolution-threshold projections) is a much
lighter workload than the closing-pass walkthrough this section's own figures above were measured
against, so the two latency figures are not directly comparable either. **Decided** — RSS growth
≤400MiB/cycle average, query-sample wall time at cycle 6 ≤3× cycle
1, cycle 6's own RSS below 85% of the Docker VM's own configured memory (read live via `docker
info`, never hard-coded); the measured numbers from this test's own runs are recorded beside
each threshold. The test now asserts all three for real.
