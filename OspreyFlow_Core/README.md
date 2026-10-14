# OspreyFlow

OspreyFlow is an open-source intelligence analysis and network discovery platform. It ingests
structured records and unstructured material (text, audio, imagery), resolves entities across
sources, persists them in a property graph, and gives an analyst a single workspace in which
network, social-network, pattern, temporal and geospatial analysis are five views of one working
set rather than five separate tools.

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

Install the command once, from this repository (`install.ps1` on Windows):

```
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
rebuild from this checkout), `stop`, `logs`, `demo list` and `demo add`, `backup`, `restore` and
`uninstall`.

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
