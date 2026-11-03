# OspreyFlow

OspreyFlow is an open source intelligence mapping, anti-money-laundering and fraud detection
platform, developed by Solirius Reply and released under the Apache License 2.0.

It serves crime analysis, anti-money-laundering, fraud detection, and event monitoring and alerting.
It ingests structured records and unstructured material (text, audio, imagery), resolves entities across
sources, persists them in a property graph, and gives an analyst a single workspace in which
network, social-network, pattern, temporal and geospatial analysis are five views of one working
set rather than five separate tools.

## What it does

- **Intelligence mapping.** One case, read as a network, a map, a timeline and reports, with a
  filter in one view applying in all of them; the network also as accessible tables (the Matrix
  view). Every element keeps where it came from, and anything a model suggests stays *inferred*
  until a person confirms it.
- **Monitoring and alerting.** One queue for every alert an analyst may see: hotlists with review
  dates, rules written as plain sentences and previewed on the last 90 days before they go live,
  typology and anti-money-laundering templates, and screening lists (connectors for the UK Sanctions
  List, OFAC, the EU, the UN and OpenSanctions, proven on synthetic files) re-screened when a new
  version arrives. Rules run on each load, before or after it commits, or on a schedule; the data
  engineer chooses each pipeline's checks and sees what a sample would raise. Closing an alert
  takes a reason, and a second person approves a whole-deployment rule or a high-severity close.
  Alerts go into report packs and alert trends, and their figures reach a monitoring dashboard.
- **Connection strength.** How strong a link is drawn rests on its own count and recency, on
  influencers that boost a kind of link (direct contact, or a record or dataset that evidences it),
  and on how rare a shared value is. All of it is worked out over what each viewer may see, shown
  in the legend, filtered in Metrics, explained in the Inspector and usable in a rule. An
  installation can reproduce a client's own scoring (client parity); installation-wide changes need
  a second person.
- **Starters.** `ospreyflow install --starter <theme>-<domain>`: the OspreyFlow or GOV.UK theme with
  a crime, anti-money-laundering, fraud, cyber or blank domain and its synthetic demo data. Several
  deployments can run side by side (`--name`, `ospreyflow deployments`, `ospreyflow switch`), and
  `ospreyflow demo add public` loads a public dataset of your choosing (the IEEE VAST Challenge
  datasets are catalogued; you download them yourself).
- **GOV.UK.** The GOV.UK theme (header, footer, crown, GDS Transport, phase banner and the service's
  own name) is a deployment setting, not a fork. OspreyFlow is designed to meet the GDS Service
  Standard; an independent accessibility audit, a penetration test and a DPIA are planned, and only
  a service assessment panel can say a service meets the Standard. A gov.uk service is served over
  HTTPS (Small or Enterprise); Lite answers on its own computer alone.
- **Model engines.** The local model answers by default. An administrator may enable hosted engines
  and give each its key (`ospreyflow models key <name>`); material leaves only when both its
  handling code and its dataset allow it, and each engine shows whether a privacy contract covers it.

## Start here

New to OspreyFlow? Begin with the guide for what you will do with it. Each is in `docs/`, as
Markdown and as a PDF with screenshots (`docs/pdf/`):

| If you are… | Read | It covers |
| --- | --- | --- |
| **Installing or running it** | [Installation and Administration Guide](docs/administration-guide.md) ([PDF](docs/pdf/administration-guide.pdf)) | How it is built; choosing Lite, Small or Enterprise; what each needs; installing, running, people and accounts, backups, updates; every setting |
| **An analyst** | [User Guide](docs/user-guide.md) ([PDF](docs/pdf/user-guide.pdf)) | Signing in, cases, the graph, map, timeline and reports, alerts and watches, and how what you see is decided |
| **A data engineer** | [Developer Guide](docs/developer-guide.md) ([PDF](docs/pdf/developer-guide.pdf)) | The Ingest Studio from a first pipeline to a scheduled one, the domain model, held rows, screening lists, the API |

The rest of this page is the short version: how it is built, what you need, and the commands to
install it.

## How it is built

Three tiers, separated by four typed ports so any one of them can be swapped without touching the
others:

- **The Glass** — the analyst workspace: canvas, timeline, map, dossier, query.
- **The Conduit** — stateless middleware: API, working-set service, extraction orchestration,
  entity resolution, model routing, access control.
- **The Vault** — persistence and compute: graph store, columnar analytics engine, graph compute
  engine, model servers, object store.

A port is a narrow interface (a Python `Protocol`) that everything above it is allowed to call and
nothing else. Swapping the engine behind a port — a laptop's in-process DuckDB for ClickHouse shared
by a cluster's Conduits, say — means writing one adapter and changing one line of configuration;
nothing above the port changes, and the adapter is only supported once it passes the same
conformance suite every other adapter behind that port passes. The guides above describe the
architecture each reader needs.

## Before you install

| Mode | What you need |
| --- | --- |
| **Lite** — one machine | Docker (Docker Desktop on Windows with the WSL 2 back end, and on macOS; Docker Engine with Compose v2 on Linux), set to start when you sign in; 16 GB of memory for Docker (32 GB is comfortable); 60 GB of free disk plus the demo packs you choose; Git; internet for the first install |
| **Small** — one VM in your cloud | an AWS or Azure account with the permissions the install lists; OpenTofu; that cloud's command line, signed in; a DNS name you control |
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

**Demo packs** load into cases of their own: three synthetic ones generated here, and two you
download — PaySim (simulated) and the **Enron email corpus, which is real people's data**: you fetch
it from Carnegie Mellon University yourself, and `ospreyflow demo add enron --file <file>` checks it,
says what it is and loads it only once you accept. No install adds it. The administration guide's
section 11 has the details.

**Small** is built from your own machine: `ospreyflow install --mode small --cloud aws` (or
`azure`) creates the server and the cloud's managed database and storage with OpenTofu, and the
server installs OspreyFlow on its first boot. **Enterprise** is built the same way:
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
- **`docs/`** — the three guides, their screenshots, and their PDFs.

The full specification and the build's own record are kept in the developer repository, alongside
the test suites and the release tooling.

## Licence

Apache License 2.0 — see `LICENSE`. Copyright 2026 The OspreyFlow Authors; see `NOTICE`.
