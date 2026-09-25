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
| `small` | 3 machines | ArcadeDB with Raft, or JanusGraph on a single Scylla | DuckDB or ClickHouse single node | Ollama or vLLM on one GPU | Docker Compose across hosts, or a small Kubernetes |
| `cluster` | 10+ machines | JanusGraph + ScyllaDB + OpenSearch | ClickHouse cluster | vLLM on a GPU pool | Kubernetes |

The same container images run in all three. Only configuration differs. That is the
transportability requirement, and it is verifiable: the acceptance scenarios in
`08_ACCEPTANCE_SCENARIOS.md` must pass unchanged on `local-lite` and on `cluster`.

## 2. The setup harness

The harness is a **browser application**, not a command-line tool. One bootstrap command starts
it; everything after that happens on screen.

```bash
docker run --rm -p 7000:7000 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$PWD:/workspace" \
  ghcr.io/ospreyflow/harness:latest
# → Setup harness ready at http://localhost:7000
```

That is the only command in this document that has to be typed. It is unavoidable — something
has to serve the page before anything is deployed — so it is kept to one line and does nothing
except start the harness.

After launch the harness does not go away. It becomes the deployment's **admin console** at
`/admin`, which is where provider registration, gazetteer loading, upgrades and verification live
for the life of the system. Per the brand foundations, the console carries the Nexus mark and the
analyst workspace carries Osprey; from inside the workspace the data layer is plumbing, not a
brand.

### 2.1 What the harness does

Six screens, navigable in any order once the profile is chosen, with a persistent summary rail
showing what has been decided and what is outstanding.

| Screen | Decides |
| --- | --- |
| **Profile** | Laptop, small or cluster. Every later screen filters its options to what is valid here |
| **Components** | Graph store, analytics engine, and the storage roots for data, staging and backups |
| **Models** | Local only, or local with a named hosted fallback — and if hosted, which handling codes may be sent to it. Defaults to none |
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

**Where the generated artefacts live — a gap in this section, found while building the renderer and
settled by the owner the same day, 24 September 2026.** This document named two fixed paths for
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
Preflight, by the scripted deploy and by the admin console alike.

The directory is **not** version-controlled in this repository, which is a separate point from
where it sits: this repository is not a deployment — the committed `osprey.yaml` describes itself as
the demo and CI configuration and says a real deployment's own is generated — so committing output
rendered from it would assert something untrue. A real deployment's own repository versions
`deploy/generated/<profile>/` exactly as the paragraph above requires, and reviews it in a pull
request along with `osprey.yaml` itself.

*Confirmed by the owner in writing on 24 September 2026, in the same message that split Stage 2 §5.
The renderer already wrote to these paths; this amendment is the document catching up.*

### 2.1.1 What the rendered identity-provider realm must carry

The Governance screen's answers render an identity-provider realm alongside the other artefacts.
Three of its requirements are recorded here because each was found by running the thing rather than
by reading the documentation, and each fails **silently** when missing — the deployment comes up,
nothing errors, and the fault surfaces later as something else entirely.

**Protocol mappers for the four custom claims.** The Conduit builds a principal from `clearance`,
`org_unit`, `receivable_handling_codes` and `roles`. Without a mapper putting each into the issued
token, an exchanged token verifies perfectly *as a token* and then fails *as a principal*, so the
error names a missing claim rather than a missing mapper.

**`unmanagedAttributePolicy` set to `ENABLED`.** Keycloak 26 discards user attributes it does not
recognise, by default and **without reporting it**: the attributes are accepted on write, stored
nowhere, and absent from the token, with no error at any point. A realm that looks correctly
configured produces principals with no clearance.

**A view-users grant separate from the impersonation grant.** The Conduit checks that a principal
is still enabled before exchanging for them, and it must do so with an authority other than the one
that would mint the token. A pre-check sharing the impersonation grant would be asking the
component that has already said yes, which is no check at all.

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
  socket; the admin console it becomes afterwards does not, and runs with the same non-root,
  read-only-root posture as every other component (§7).

### 2.6 How the Glass reaches the Conduit, and how an analyst signs in

Two holes, found running the seeded golden path on 24 September 2026 (`07_BUILD_PLAN.md`'s Stage 2
§3 entry has the measurement and the screenshot): a rendered `local-lite` deployment came up
healthy, seeded both fixtures and passed its three-sided verify — and the Glass served by that same
deployment could not talk to it at all. **Both are now decided, differently.**

#### 2.6.1 Reaching the Conduit — DECIDED, 25 September 2026: same-origin

**The workspace's own image proxies the Conduit.** Its nginx serves the Glass and forwards `/v1`
and the delta WebSocket to `api:8000` on the internal network; the bundle is built with an empty
base URL and issues relative paths only.

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
`App.tsx` has said so plainly since Phase 4: a login flow was not in that phase's bullets, and the
token is "a stand-in until a real sign-in screen exists, not a production auth path." No phase has
owned it since. Every rendered deployment therefore serves a Glass that sends an empty bearer token
to a Conduit that correctly refuses it.

**ADR-050** is where this is decided: OIDC authorization code with PKCE against the realm §2.1.1
already renders, the Glass as a public client. It is **not** harness work and it is
**milestone-blocking** — `07_BUILD_PLAN.md`'s sign-in stage, after Stage 2 §3, carries the exit
test. Until it is built, the dev-token path is fenced so that no rendered deployment can carry it.

## 3. Standing it up on a laptop

```bash
docker run --rm -p 7000:7000 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$PWD:/workspace" \
  ghcr.io/ospreyflow/harness:latest
```

Then open `http://localhost:7000` and work through the six screens. For a laptop: choose
**local-lite** on Profile, accept the defaults on Components, Models and Governance, press
**Build local basemap** on Geospatial, and let Preflight run. Review the generated files, click
Launch, then **Seed demo data** on the screen that follows.

Roughly fifteen minutes end to end, most of it pulling model weights and building tiles, with
progress shown throughout. The workspace is then at `http://localhost:8080` and the admin console
at `http://localhost:8080/admin`. The seeded demo credentials are displayed once and written
nowhere.

What is running afterwards: the workspace, one Conduit, three workers, ArcadeDB, DuckDB
in-process, Valkey, MinIO, OpenSearch single-node, PostgreSQL, Keycloak, Ollama, and a
faster-whisper container. Twelve containers, roughly 11 GB of RAM at rest.

**Correction, 24 September 2026 — the model gateway is missing from this list, but it is *not* why
the Conduit would not start.** An earlier version of this paragraph said the Conduit fail-fasts
against an absent model gateway. **That was an inference from a partial traceback and it was
wrong.** The exception was `asyncpg`'s, not the model client's: the Conduit could not reach
**PostgreSQL**, because `services/api/config.py` defaults `POSTGRES_PORT` to 5433 — a workaround for
the development stack publishing there — while a rendered container listens on 5432. The model
client is constructed during startup but **opens no connection**, so it cannot have raised it. The
real fault is fixed; this paragraph is the correction, left in place rather than quietly rewritten.

**The list does still omit the model gateway, and that remains a real gap — Proposed, after
Stage 2 §3.** A decision on this was taken on 24 September 2026 and **withdrawn the same day by the
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

## 4. Moving up a profile

The migration path is the property that makes the setup-time choices safe, so it is specified
rather than assumed.

**Laptop to small, or small to cluster:**

1. **Back up** from the admin console, or `osprey backup`. Writes a portable bundle: staged
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
- **Renovate** raises dependency pull requests continuously. CI runs the conformance suites on
  every one, so an upgrade that breaks a port contract is visible before merge.
- **Weekly** — `trivy` scans every image; anything critical or high raises an issue
  automatically.
- **Rolling a single component** is a screen in the admin console: pick the component, pick the
  target version, and the console runs preflight, rolls the container or the Kubernetes
  deployment, then runs **verify** — the port conformance suite against the *running* deployment
  rather than a test fixture. Under two minutes, and it is what makes the upgrade safe rather
  than hopeful. The headless equivalent is `osprey upgrade opensearch --to 3.2.1 && osprey verify
  opensearch`.
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

The problem this settles, found building ADR-049's Stage 2 §4: every credential is minted at apply
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

**For `cluster`, the answer is different and is Phase 8a's.** Holding secrets outside the
deployment, in a secret manager the restored deployment is pointed at, is recorded as the cluster
profile's approach. It does not apply to `local-lite` or `small`, where standing up a secret
manager to restore a laptop would be machinery in place of a constraint.

### 6.2 What the current implementation does and does not satisfy

`deploy/RUNBOOK.md` is the operational document; this is the specification's own ledger of where the
build stands against the table above, as of 24 September 2026 (ADR-049 Stage 2 §4):

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
- Images signed and verified at pull; digests pinned in `deploy/versions.lock`.
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

**The operational consequence, stated plainly:** a running instance should be expected to need
periodic restarts to recover memory, and **the safe interval between them is not yet known** —
nobody has measured how far this degradation goes, whether it plateaus at some working-set size
or continues climbing without bound toward the same resource ceiling that a single heavy session
can already reach on its own (`07_BUILD_PLAN.md`'s own Phase 8 "ArcadeDB stability" stage has the
single-session measurement this finding sits alongside, not on top of — that stage closed against
a fresh-install criterion; this finding is what happens *after* a fresh install, under continued
real use, and neither stage's own measurement answers the other's question).

**Built, 25 September 2026 — `tests/harness/test_sustained_load.py::test_arcadedb_memory_and_
query_latency_under_sustained_ingest_cycles`, pulled forward per `07_BUILD_PLAN.md` Stage 2a's own
addendum, which has the full account: methodology, the six-cycle curve, a real defect found
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
against, so the two latency figures are not directly comparable either. Thresholds for what this
test should assert are **Proposed, not decided** (`07_BUILD_PLAN.md` Stage 2a's addendum has the
three proposals and the measured numbers beside each); the test today asserts only that all six
cycles complete and every query in the sample returns 2xx, per this round's own brief.
