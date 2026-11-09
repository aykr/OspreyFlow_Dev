# OspreyFlow

> **Draft for the owner's approval (9 November 2026).** This page is published with the repository,
> so what it claims is published too. It describes the product as built on `main`; anything not yet
> built is marked *coming*. It replaces the earlier README once the owner approves it.

OspreyFlow is an open source intelligence mapping platform for crime analysis, anti-money-laundering,
fraud detection, and event monitoring and alerting, developed by Solirius Reply and released under the
Apache License 2.0.

## The problem it solves

An analyst's picture of a network is usually spread across tools: one for the network, one for the
map, one for the timeline, another for reports, and a separate system for alerts. Each holds its own
copy of the data, each decides access its own way, and the picture is joined up by hand. OspreyFlow
holds a case's people, organisations, accounts, phones, places, documents and events as **one
graph**, and gives the analyst one workspace in which the network, the map, the timeline, the
Matrix tables and the case's figures are views of the same working set. A filter in one view applies
in all of them.

It ingests structured records and unstructured material (text, audio, imagery), resolves records that
look like the same person or organisation without ever merging them, and keeps where every element
came from.

## Who uses it

| Role | What they do |
| --- | --- |
| **Analyst** | Investigates cases, works alerts and keeps watches. Reads figures and boards. |
| **Data Engineer** | Builds and runs pipelines, reviews promotions into a dataset and decides held rows. |
| **Administrator** | Looks after people, roles, teams, datasets and the deployment. Does not investigate by being one. |
| **Reports Viewer** | Reads a case's figures and the dashboards, and sees the alerts on cases they can read. Never works an alert. |
| **Rule author** | Writes the rules that raise alerts, and works the alerts in the queue. |

An administrator can also define roles of their own from the same rights, and give a **Super user**
(Analyst, Data Engineer and Rule author together). Nobody can give more than they hold.

## What you see, where you work, what you may do

- **What you see** is decided by your clearance, your unit, your handling codes and the cases you are
  given. A record you may not see is not drawn, not counted and cannot be found by its links.
- **Where you work** is one of **four places**, each with one job. You see only the places your
  roles open:

  | Place | For |
  | --- | --- |
  | **The Glass** | Investigate a case: search, expand, map, read its figures and its boards |
  | **Ingest Studio** | Bring data in: sources, pipelines, the domain model and held rows |
  | **Rules and Monitoring** | Work the alerts that rules and watches raise, and see what raises them |
  | **Admin** | Run the deployment: people, roles, teams, datasets, models, maps and operations |

- **What you may do** is your roles' rights, and your level in each case (Viewer, Editor or Author).
  Seeing is not doing: a level never widens what you can see.

## What it does

- **Intelligence mapping.** One case, read as a network, a map, a timeline, the Matrix (the graph as
  tables a screen reader can walk) and the case's figures. Communities, centrality, paths between
  two people, ownership traced through every layer, and connection strength, each counted only over
  what the reader may see.
- **Drawing boards.** On a case's board an analyst declares a person, an account or a place and draws
  the links between them, each item marked, graded and sourced, in the case's own analyst layer. A
  drawing begun with no case makes a dataset, a case and a board of its own. *Coming:* promoting drawn
  items into a dataset as a reviewed load.
- **Case views, not copies.** A saved view is a lens on a case: what was drawn, the filters and the
  period. Opening one reads the case through it. There are no branches.
- **Monitoring and alerting.** Alerts are worked in Rules and Monitoring: hotlists with review dates,
  rules written as plain sentences and previewed on the last 90 days before they go live, typology and
  anti-money-laundering templates, and screening lists (connectors for the UK Sanctions List, OFAC, the
  EU, the UN and OpenSanctions, proven on synthetic files) re-screened when a new version arrives. Rules
  run on each load, before or after it commits, or on a schedule. Closing an alert takes a reason, and a
  second person approves a whole-deployment rule or a high-severity close. *Coming:* the rule editor
  with its draft, test and live stages.
- **Bringing data in.** The Ingest Studio's four steps (the domain model, sources, pipelines, runs)
  load files, a watched folder and connections to SQL databases, HTTP APIs and JSON, with guided
  mapping, staging steps, a live sample at each step, and rows a check could not judge held for a
  person. *Coming:* releases between environments as YAML.
- **Datasets and their Authors.** Every dataset has a home case, and its Authors answer for it. The
  administrator sees each dataset's kind, unit, highest marking, Authors and linked cases.
- **Models and maps, administered.** Model engines, each job's model and their keys (write-only, never
  shown back), with usage and limits; map providers and their keys, the local basemap built and
  checked, and prefetched areas. The local model answers by default; material leaves only when both its
  handling code and its dataset allow it.
- **Starters.** `ospreyflow install --starter <theme>-<domain>`: the OspreyFlow or GOV.UK theme with a
  crime, anti-money-laundering, fraud, cyber or blank domain and its synthetic demo data. Several
  deployments can run side by side, and `ospreyflow demo add public` loads a public dataset of your
  choosing (you download it yourself).

## Use cases

- **Crime analysis**: networks, the rhythm of a case on the timeline, the people who join two groups,
  and a prison intelligence picture of cell shares, visits, calls and payments.
- **Anti-money-laundering**: screening on onboarding before a customer goes live, transaction
  monitoring as typology rules, beneficial ownership traced layer by layer, and a decision on the
  record.
- **Fraud detection**: rings that share a phone, an address or an account drawn as one cluster.
- **Event monitoring and alerting**: hotlists, watches and rules that find a match as new data arrives.

## Reporting

A case's own counts are on its **Figures** tab. Dashboards (Apache Superset, or another BI tool reading
the same reporting database) are behind the Glass's **Dashboards**, including an **Alert monitoring**
board. A Reports Viewer reads figures and boards and follows an alert to its case's figures, without
working it. Every figure is counted as its reader, or the dashboard's own account, may see it, and
every pull is recorded.

## Guarantees and safeguards

- **Access control is in the store.** The reader travels with every query, counts included, and the
  filter is part of the query itself. Hiding a screen is never the control.
- **Nothing is cut silently.** A result too large is refused with choices, never truncated.
- **A model's findings are suggestions.** They stay *inferred* until a person confirms them; no
  threshold promotes them.
- **Records are never merged.** Matches are scored links, shown as one at the strictness you choose.
- **What you draw stays in your case.** A case's analyst layer is never written into the dataset, and
  no other case can see it or infer it.
- **Every read and write is recorded.** Handling travels with the data and is checked again, item by
  item, at export.
- **A second person** approves the decisions that matter, and never the person who proposed them.
- **No real data.** OspreyFlow ships synthetic data only.

## How it is built

Three tiers, separated by four typed ports so any one of them can be swapped without touching the
others:

- **The Glass**: the browser workspace and its four places.
- **The Conduit**: stateless middleware: the API, the working-set service, extraction, entity
  resolution, model routing and access control.
- **The Vault**: the graph store, the analytics engine, graph compute, the models and the object
  store.

A port is a narrow interface (a Python `Protocol`) that everything above it is allowed to call and
nothing else. Swapping the engine behind a port (a laptop's in-process DuckDB for ClickHouse shared
by a cluster's Conduits, say) means writing one adapter and changing one line of configuration, and
the adapter is supported only once it passes the conformance suite every adapter behind that port
passes. The [Architecture Guide](docs/architecture-guide.md) draws it at two levels: level 0, the
people, the tiers and what sits beside them; level 1, every component and the technology it is built
on.

**Licence traps avoided.** The build fails on a dependency whose licence is not on the allowlist; GPL
and AGPL never pass. Redis 7.4 and later (Valkey instead), Elasticsearch (OpenSearch), Neo4j Community,
ArangoDB and FalkorDB (ArcadeDB and rustworkx), MongoDB (PostgreSQL), Grafana (never bundled), Stanford
CoreNLP (Stanza) and Terraform (OpenTofu) were each avoided for their licence. Two screening lists'
licences are not confirmed for a customer's use (the UN list; OpenSanctions, non-commercial only), so
their connectors read synthetic lists until they are.

## Honest limits

- No real-time streaming ingestion; loads are batches, on demand, on a schedule or from a folder.
- No multi-tenancy: one deployment serves one organisation.
- No mobile client: the workspace is for a desktop.
- Designed to meet the GDS Service Standard, not assessed: an independent accessibility audit, a
  penetration test and a DPIA are planned, and only a service assessment panel can say a service
  meets the Standard.
- Enterprise's in-cluster graph store and analytics database are not backed up by `ospreyflow backup`
  yet; Small on a managed database is not updated by `ospreyflow update` yet.
- Coming: promotion of drawn items into a dataset, the rule editor, releases between environments,
  and backups to a folder the administrator names at setup.

## Start here

New to OspreyFlow? Begin with the guide for what you will do with it. Each is in `docs/`, as
Markdown and as a PDF with screenshots (`docs/pdf/`):

| If you are… | Read | It covers |
| --- | --- | --- |
| **Installing or running it** | [Installation and Administration Guide](docs/administration-guide.md) ([PDF](docs/pdf/administration-guide.pdf)) | Choosing Lite, Small or Enterprise; what each needs; installing, running, people, roles and teams, datasets, models and maps, backups, updates; every setting |
| **An analyst** | [User Guide](docs/user-guide.md) ([PDF](docs/pdf/user-guide.pdf)) | Signing in, the four places, cases and views, the graph, map, timeline and figures, drawing boards, alerts and watches, and how what you see is decided |
| **A data engineer** | [Developer Guide](docs/developer-guide.md) ([PDF](docs/pdf/developer-guide.pdf)) | The Ingest Studio from a first pipeline to a scheduled one, the domain model, connectors, held rows, screening lists, the analyst layer, the API |
| **Deciding whether it fits** | [Architecture Guide](docs/architecture-guide.md) ([PDF](docs/pdf/architecture-guide.pdf)) | The two architecture levels, the tiers and ports, cases and datasets, access control, every interface, the licence traps and the limits |

The rest of this page is the short version: what you need, and the commands to install it.

## Before you install

| Mode | What you need |
| --- | --- |
| **Lite** — one machine | Docker (Docker Desktop on Windows with the WSL 2 back end, and on macOS; Docker Engine with Compose v2 on Linux), set to start when you sign in; 16 GB of memory for Docker (32 GB is comfortable); 60 GB of free disk plus the demo packs you choose; Git; internet for the first install; on Linux, optionally, an NVIDIA GPU for the local model, with its driver and the NVIDIA Container Toolkit (administration guide, section 5a.4) |
| **Small** — one VM in your cloud | an AWS or Azure account with the permissions the install lists; OpenTofu; that cloud's command line, signed in; a DNS name you control |
| **Small on your own server** — one Linux VM in your network | the server: `amd64`, 32 GB of memory, 60 GB free where Docker keeps its data, Docker Engine with Compose v2 enabled at boot, Git, uv, Python 3.12, a synchronised clock, port 443 free; from your organisation: three names in its DNS and a certificate naming them, with its key; outbound access to the releases; for sign-in through the organisation, OspreyFlow registered as an application with its identity provider and a route from the server to it; optionally, an NVIDIA GPU for the local model, with its driver and the NVIDIA Container Toolkit installed (`server.gpu: nvidia`, section 5a.4) |
| **Enterprise** — Kubernetes | to build the cluster: an AWS or Azure account, OpenTofu, that cloud's command line signed in (and `kubelogin` on Azure), kubectl, Helm, Git and uv, the addresses you work from, and a DNS name you control; or an EKS or AKS cluster `kubectl` already reaches, with the cloud's managed PostgreSQL, Valkey and object store and a storage class several pods can share (EFS on AWS, Azure Files on Azure). The models run on ordinary nodes for now |

`ospreyflow doctor` checks these for the mode you choose and says what to fix.

## Installing and running it

Install the command once, from a checkout of this repository, `https://github.com/aykr/OspreyFlow`
(`install.ps1` on Windows):

```
git clone https://github.com/aykr/OspreyFlow.git
cd OspreyFlow
sh install.sh
```

Then:

```
ospreyflow doctor                      # are the prerequisites in place?
ospreyflow install --mode lite         # asks a few questions; --gui opens the guided page instead
ospreyflow open                        # the Glass in your browser
```

Every question `install` asks can be answered in a file instead (`--config install.yaml --yes`), so
a tester or a CI job installs without prompts. The other verbs: `status`, `start` (`--build` to
rebuild from this checkout), `stop`, `logs`, `demo list` and `demo add`, `backup`, `restore`,
`repair-sign-in` (when nobody can sign in), `apply` (a changed `osprey.yaml`, keeping every secret),
`models` (the model engines and their keys), `starters`, `deployments`, `switch` and `uninstall`.
Every operator task is an `ospreyflow`
verb; `make` targets are for developers working on OspreyFlow itself.

**Demo packs** load into cases of their own: six synthetic ones generated here, and two you
download — PaySim (simulated) and the **Enron email corpus, which is real people's data**: you fetch
it from Carnegie Mellon University yourself, and `ospreyflow demo add enron --file <file>` checks it,
says what it is and loads it only once you accept. No install adds it. The administration guide's
section 11 has the details.

**Small** is built from your own machine: `ospreyflow install --mode small --cloud aws` (or
`azure`) creates the server and the cloud's managed database and storage with OpenTofu, and the
server installs OspreyFlow on its first boot. **Small on your own server** is installed on the
server itself, with every store in a container and your organisation's own certificate:
`ospreyflow doctor --mode small --config install.yaml`, then `ospreyflow install --mode small
--config install.yaml --force`, with a `server:` section naming the address and the certificate's
files (the administration guide, section 5a). It publishes port 443 alone, sizes the stores to the
server's memory (`server.memory_gib: auto`), writes its backups to `server.backups`, and moves to a
new release with `ospreyflow update`. With a `sign_in:` section, people sign in with their
organisation's own account — Microsoft Entra ID, ADFS or any OpenID Connect provider — and have no
role until an administrator grants one (section 5a.1). **Enterprise** is built the same way:
`ospreyflow install --mode enterprise --cloud aws` (or `azure`) makes an EKS or AKS cluster and the
cloud's managed services with OpenTofu (`deploy/opentofu/cluster/`), its API open only to the
addresses you name in `cloud.api_cidrs`, then installs onto it. Onto a cluster your `kubectl` and
`helm` already reach, leave out `--cloud` and name the managed services and the cluster's storage
classes in the answers yourself. It installs the Helm chart in `deploy/helm/ospreyflow`, makes its Secret and the first
administrator (who signs in with a one-time code it prints once), and tells you the address to point
your names at. Running it again changes no password and replaces no account.

The sign-in details of the accounts the install makes are in the deployment's own
`deploy/generated/<profile>/deployment.env`; the command never prints a password.

## Releases and updates

A checkout of a release tag (`vMAJOR.MINOR.PATCH`) installs that release's own images, after
checking they are signed by this repository's release workflow; any other checkout builds from
source (`install --build` builds on a tag too). Each release's notes are its section of
`CHANGELOG.md`.

**Is there a newer release?** Nothing checks on its own — the deployment never calls out. Ask:

```
ospreyflow update --check     # asks the repository's releases; Admin → System shows the answer
```

Run it whenever you like, or add it to this computer's scheduler (`0 8 * * 1 ospreyflow update
--check` in cron, each Monday). A private repository needs `GITHUB_TOKEN` set to a token that can
read it.

**Updating** depends on how you installed:

| Your install | Update it with |
| --- | --- |
| Lite, from a release tag | `ospreyflow update` (or `--to vX.Y.Z`) |
| Lite, built from this checkout | `git pull`, then `ospreyflow start --build` — `update` refuses a built install |
| Small | not yet by `update`: its backup step refuses a managed database (see the administration guide, section 14) |
| Enterprise | check out the release's tag and run the install again; the chart upgrades in place |

`update` checks every image's signature first and changes nothing if one fails; then it backs up
every store, moves to the release and checks it is running. If anything goes wrong, it puts the
previous release and its data back. For a machine that cannot reach GitHub, make one file on a
machine that can and carry it across; it is checked again there with no network at all:

```
ospreyflow update --make-bundle ospreyflow-v1.2.0.tar --to v1.2.0     # on the connected machine
ospreyflow update --from ospreyflow-v1.2.0.tar                         # on the one to update
```

## Where things are

- **`apps/`** — the Glass (`apps/workspace`) and the guided install page (`apps/harness`).
- **`services/`, `packages/`** — the Conduit, the workers, and the shared schemas, ports and
  adapters.
- **`harness/`** — what renders, starts, checks, backs up and restores a deployment; the
  `ospreyflow` command (`cli/`) drives it.
- **`deploy/`** — the Helm chart for Enterprise (`helm/ospreyflow`), the OpenTofu modules that build
  Small's server (`opentofu/small/aws`, `opentofu/small/azure`) and Enterprise's cluster
  (`opentofu/cluster/aws`, `opentofu/cluster/azure`), and the Superset image.
- **`scripts/`** — the demo packs (`python -m scripts.demo_packs`) and their seeds.
- **`docs/`** — the four guides, their screenshots, and their PDFs.

The full specification and the build's own record are kept in the developer repository, alongside
the test suites and the release tooling.

## Licence

Apache License 2.0 — see `LICENSE`. Copyright 2026 The OspreyFlow Authors; see `NOTICE`.
