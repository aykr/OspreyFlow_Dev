# Changelog

Each release of OspreyFlow has a section here, newest first: `## vMAJOR.MINOR.PATCH — YYYY-MM-DD`.
A release's section is its release notes, and what `ospreyflow update --check` shows before you
update. Work not yet in a release is listed under *Unreleased*.

## Unreleased

- **An install is ready only once its extraction model is in.** A fresh install said it was ready
  while the model server was still downloading the extraction model (the 14b on a GPU is about
  9 GB), and Ask answered "not found" for a minute or two. The install now says which model is
  downloading, and its size, waits until it is downloaded and its digest checked, and only then
  says it is installed. A refused download stops the install, naming `ospreyflow logs
  ollama-models`.
- **A server of your own needs its certificate and key.** An answers file whose `server:` gives
  no `certificate` or no `key` is now refused, in words naming both and section 5a of the
  administration guide, before anything is installed. It used to fall back to a certificate the
  front proxy obtains itself, which needs port 80 and a public name a server inside an
  organisation's network does not have. A cloud's server is unchanged.
- **The Prison Intelligence pack looks after post-ingest resolution itself.** An install that
  chooses it (the `crime` starter does) now writes `components.post_ingest_resolution: false` and
  says so, so a fresh install no longer turns resolution back on under the pack. Added later with
  `ospreyflow demo add prison-intelligence`, it refuses, in words and with nothing added, while
  resolution is on, naming the setting and `ospreyflow apply`. Resolution is the whole
  deployment's setting: the deployment's other demo cases gain no automatic "same as" links either;
  an analyst's own Resolve now still works.

## v0.4.10 — 2026-11-04

- **On a GPU the model stays loaded.** The first question after a few idle minutes no longer
  waits about a minute for the model to load into the GPU again (`OLLAMA_KEEP_ALIVE=-1`, with
  `resources.gpu: nvidia` only).
- Update with `ospreyflow update`, then `ospreyflow apply` on a deployment with a GPU, so the model
  server is started again with the setting.

## v0.4.9 — 2026-11-04

- **No service-name band under the GOV.UK header.** Under the GOV.UK theme the band that named the
  service below the GOV.UK header is gone, on the workspace, the start and welcome pages and the
  sign-in page alike, so the workspace gets that height back (the owner's ruling, ADR-132
  Amendment 5). The service's name is in the page title, "<service> – GOV.UK", now on the sign-in
  page too. The "Beta" banner is unchanged: `appearance.phase: none` turns it off.
- **Uploads and demo packs work on Linux.** On a Linux server or computer, the folder the Ingest
  Studio's uploads and the demo packs' files go to (`uploaded/` in the ingest folder) was made by
  Docker, owned by root, and the Conduit could not write it: `ospreyflow demo add` and every upload
  failed with "Permission denied". Before anything starts, `install`, `apply`, `start` and `update`
  now make that folder and give it to the Conduit's user (uid 10001) when it cannot write it, with
  the Conduit's own image; it is never made writable by every account, and a folder the Conduit can
  already write is left as it is. A deployment updated from v0.4.8 or earlier is put right by its
  first `ospreyflow apply` or `ospreyflow start` afterwards.
- **The local engine fits the 14b wholly on a 16 GB GPU.** With `resources.gpu: nvidia`, the model
  server now keeps its KV cache at q8_0 with flash attention (`OLLAMA_FLASH_ATTENTION=1`,
  `OLLAMA_KV_CACHE_TYPE=q8_0`). Measured on the first server (RTX 5060 Ti, 16 GB), the same question:
  before, 18 GB, 15%/85% CPU/GPU, 9–11 s an answer; now 14 GB, 100% GPU, 3.3–3.6 s. The doctor now
  asks for at least 14 GiB of GPU memory for the 14b (12 before); below that it warns and names the
  7b. Without a GPU nothing changes. Run `ospreyflow apply` on a GPU deployment to take it.
- **`ospreyflow apply` fetches a newly chosen model.** Switching the GPU on (which chooses the 14b)
  or changing `models.extraction` re-rendered the deployment and restarted the gateway and the
  Conduit, but never fetched the new model, so every Ask on the local engine went to a model that
  was not there. `apply` now fetches it, and waits, before anything that uses it starts again; if
  the download fails, nothing is changed and it says so. `ospreyflow start --build` and
  `ospreyflow update` also wait for a changed model before starting the rest.
- **`ospreyflow backup` works once the object store holds files.** On Linux, after a demo pack or an
  upload, every backup failed with "Permission denied": the object store's working copy belonged
  to the Conduit's user, and the installing account could not remove it. It is now made as the
  account that runs the backup. A failed backup that cannot remove its partial set says so, renames
  it `<set>.incomplete` with an `INCOMPLETE` file in it, and `ospreyflow restore` refuses it. A
  partial set left by v0.4.8 or earlier has to be removed as root (`sudo rm -rf <set>`).
- Update with `ospreyflow update`. On a Linux server updating from v0.4.8 or earlier, run
  `ospreyflow apply` once afterwards, so the Conduit is given its upload folder.

## v0.4.8 — 2026-11-04

- **`ospreyflow update` works for an install from a release.** Every earlier release's update
  brought the deployment's files up to date with OspreyFlow's own images named in the project's old
  registry (`ghcr.io/ospreyflow`) instead of the release's (`ghcr.io/aykr`), so they were not pinned
  and the pull was refused ("denied"). The update rolled back each time, with nothing lost. It now
  uses the registry the release's lock names, as `install` does.
- **Updating from v0.4.6 or earlier, on a deployment where no recipe has been published yet,** the
  old release's backup stops the update before it starts ("Could not find the file
  /var/lib/osprey/data/recipes"; nothing is changed). Move the checkout to the new release first,
  then update: `git -C <your checkout> fetch --tags`, `git -C <your checkout> checkout v0.4.8`,
  `sh install.sh` in the checkout, then `ospreyflow update --to v0.4.8`.

## v0.4.7 — 2026-11-04

- **Installing on a hardened server works.** On a server whose installing account has a strict
  umask (077, or a CIS-hardened 027), the identity provider could not read its own settings and the
  install stopped at "build and start the deployment". Every file a service reads from the
  deployment's folder is now readable by it, whatever the umask; `deployment.env` stays readable by
  its owner alone. `ospreyflow doctor` and `install` refuse, in words, an organisation's root
  certificate (`server.ca`) that the identity provider could not read.
- **Demo packs load on Small.** The answers' `demo_packs` were accepted and silently not loaded on a
  server of your own; they now load once the first administrator exists. And `ospreyflow demo add`
  refused every pack on a deployment with no demo accounts; each now loads into its own case with
  the first administrator, `admin`, as its Author.
- **The first administrator can open the cases they author.** On a deployment without demo
  accounts (Small, and Enterprise), the first administrator, `admin`, is now made with both the
  Admin and the Analyst roles, whether or not demo packs load. The Admin role alone does not open a
  case's graph. An `admin` made by an earlier release keeps Admin alone: add the Analyst role in
  Admin, People and roles.
- **The local engine on an NVIDIA GPU.** On Small on a server of your own, or Lite on a Linux
  computer, the deployment's own model can run on the server's NVIDIA GPU: `gpu: nvidia` under
  `server:` in the answers file, or `resources.gpu: nvidia` in `osprey.yaml`. It answers much faster,
  and uses the larger `qwen2.5:14b-instruct` unless `models.extraction` names another. `ospreyflow
  doctor`, `install` and `apply` check the NVIDIA driver, Docker's NVIDIA Container Toolkit and the
  GPU's memory before anything starts; OspreyFlow installs neither. Off by default; not for Small
  in a cloud or Enterprise. See the administration guide, §5a.4.
- **The first backup of a new deployment works.** `ospreyflow backup` failed on 'recipes' before
  any recipe had been published, and left a half-written set behind. Items a new deployment does
  not have yet are now recorded as empty, and a backup that fails removes what it had started.
- Update with `ospreyflow update`.

## v0.4.6 — 2026-11-04

- **Installing and updating on a Linux server works.** Earlier releases refused every install and
  update on Linux with "permission denied" before checking any image: the release's signature was
  checked by cosign's container as a user that could not read the private folder the release was
  written to. cosign now runs as you. (Docker Desktop on a Mac hid the problem.)
- **An offline package can be made again.** `ospreyflow update --make-bundle` failed on the three
  model images pinned by digest alone (Ollama, LiteLLM, Speaches), which the release's lock named
  wrongly; it names them by repository and digest now.
- **The administration guide** (§5a) shows a firewall rule for the `DOCKER-USER` chain that limits
  who reaches the service without cutting off the server's own outbound HTTPS.
- Update with `ospreyflow update` (on a Mac or Windows). On Linux, no earlier release could install
  from a release, so install v0.4.6 afresh.

## v0.4.5 — 2026-11-04

- **Small on a server of your own.** Small can now run on one Linux server with every store in a
  container, without managed cloud services: HTTPS with your organisation's own certificate (checked
  before anything starts, by `ospreyflow doctor` and on each renewal), sign-in through your
  organisation's identity provider (OIDC, such as Entra ID) or local accounts, the stores sized to
  the server's memory, and backups to a folder you choose. Answer the new `server:` section and run
  `ospreyflow install --mode small`; the administration guide's section 5a has the steps.
- **Staying signed in.** A window renews its sign-in by itself before it expires. When your session
  has ended, it asks you to sign in again where you are, without losing the page.
- **`ospreyflow repair-sign-in`** also sets the Conduit's own client secret again, so a deployment
  whose stores were wiped can act for its people again.
- **What OspreyFlow says it is**, the same everywhere (README, About, the install page, the sign-in
  page and the website): "an open source intelligence mapping platform for crime analysis,
  anti-money-laundering, fraud detection, and event monitoring and alerting".
- **An offline update can verify on a machine that has never had cosign.** A bundle made with
  `ospreyflow update --make-bundle` now carries the cosign image that checks the release's
  signatures, pinned by digest; `ospreyflow update --from` loads it and runs it only if it is that
  exact image. Before, a machine with no network that had never pulled cosign could verify nothing.
- **A release's lock names every image any option can run**, Superset and ClickHouse included, so a
  deployment with dashboards on can take Superset from a release or a bundle; Superset's signature is
  checked like the other images OspreyFlow builds.
- **Fixes from the demo rehearsal.**
  - Connections: each route names its links, so routes through the same people read apart; a node
    put back on the canvas brings back its links; a search result chosen joins the working set
    before it is drawn.
  - Add from a list says how many different records were found and how many are in the view.
  - The timeline's weekly grid draws no stripes over its cells, and choosing it makes the timeline
    tall enough.
  - The reports' Outcomes figures count every closing reason.
  - Relationships, typologies and source files are named as a person reads them, never by a key.
  - The Connection strength legend is read again when you return to the window; the Matrix shows
    each strength as it arrives.
  - An alert can be given to people only, never to a service account.
  - The Prison Intelligence demo's chapter 4 draft is a whole, mapped branch the Studio completes.
- Update with `ospreyflow update`; an install from `Solirius/ospreyflow` must reinstall from
  `https://github.com/aykr/OspreyFlow.git` first (see v0.4.3).

## v0.4.4 — 2026-11-03

- **Architecture in the guides.** The administration guide's "How OspreyFlow is built" now opens
  with a level 0 diagram (who uses OspreyFlow and what it talks to) and a level 1 diagram naming
  the technology in every component and what each mode runs on, and a new section, "The
  interfaces, and what crosses each", gives every interface's direction, protocol, what crosses it
  and what guards it. The developer guide has the level 0 diagram.
- **Images built on fresh bases.** Every image build, including `ospreyflow start --build`, now
  pulls its base image first, so a base's security fixes arrive without waiting for a change of
  ours.
- **The Glass is served by nginx 1.30**, the maintained stable line, in place of 1.27, which
  reached its end of life.
- Update with `ospreyflow update`; an install from `Solirius/ospreyflow` must reinstall from
  `https://github.com/aykr/OspreyFlow.git` first (see v0.4.3).

## v0.4.3 — 2026-11-03

**OspreyFlow stays at `https://github.com/aykr/OspreyFlow`.** The move to `Solirius/ospreyflow`
announced with v0.4.2 has been withdrawn, and that repository, its images and its site are deleted.
Images and the Enterprise chart stay under `ghcr.io/aykr/`, and the site at
`https://aykr.github.io/OspreyFlow/`. OspreyFlow is an open source intelligence mapping,
anti-money-laundering and fraud detection platform, developed by Solirius Reply and released under the
Apache License 2.0.

- **Installed from `aykr/OspreyFlow` (v0.4.1 or earlier):** `ospreyflow update` brings you to this
  release; nothing else to do.
- **Installed from `Solirius/ospreyflow` (v0.4.2):** that install cannot update, because it looks for
  releases in the deleted repository and accepts only its signatures. Back up anything you need
  (`ospreyflow backup`), uninstall, and install again from a fresh clone:
  `git clone https://github.com/aykr/OspreyFlow.git`, then `sh install.sh` (`install.ps1` on Windows).

Everything in v0.4.2 below is in this release.

## v0.4.2 — 2026-11-02

Published only at `Solirius/ospreyflow`, since withdrawn (see v0.4.3); its changes are in v0.4.3.

- **Monitoring and alerting, a core feature.**
  - One alert queue for every kind of alert, with severity, team, assignment and who claimed each one.
  - Rules written as plain sentences, blank by blank from the ontology, shown as the pattern they draw
    and previewed on the last 90 days before they go live. Rules run on each load, before or after it
    commits, or on a schedule; a rule change and an alert's close can need a second person to approve
    (maker–checker).
  - Four more anti-money-laundering templates: a high-risk jurisdiction, large cash, a dormant account
    reactivated, and a sudden rise in velocity.
  - Screening lists as managed sources, with versions and re-screening against the changed entries
    only: connectors for the UK Sanctions List (FCDO), OFAC, the EU, the UN and OpenSanctions, proven on
    synthetic files. UN and OpenSanctions are marked "licence not confirmed".
  - Closing an alert takes one of five reasons and words, kept on the record.
  - Alerts in reports: an alert as a report pack item, alert trends in the trend builder, and the
    monitoring dashboard's sections.
- **Connection strength.** A link's strength and a shared attribute's rarity, in the legend, the
  Inspector and the canvas, with installation influencers set by maker–checker and overridden per case,
  a "client parity" composition, and sentence rules on strength and rarity.
- **The Matrix view.** The network as two tables a screen reader can walk.
- **The GOV.UK theme.** A deployment can take the GOV.UK brand for a gov.uk service: header, service
  navigation, phase banner, footer, the GOV.UK type scale and a matching sign-in page. OspreyFlow is
  credited in the footer and in About.
- **Starters and several deployments.** `ospreyflow install --starter <theme>-<domain>`, also on the
  guided install page's Mode screen; `deployment.name` lets one computer hold several Lite deployments,
  and `ospreyflow switch` runs one at a time.
- **Model engines.** Several engines, each with its own key (`ospreyflow models`, or the guided install
  page's Models screen). An analyst chooses the engine in Ask the case and Ask to search, within what the
  case's datasets allow: egress is set per dataset as well as by handling code.
- **`ospreyflow apply`** applies a changed `osprey.yaml` safely, and `deployment.env` is kept private
  (600, and a named deployment's folder 700).
- **Security.**
  - Lite answers on this computer only (loopback); Small and Enterprise are HTTPS.
  - Names, not identity-provider ids, wherever a person is shown.
  - pyasn1 and pypdf updated, and Superset's pyasn1 pin raised.
- **Accessibility.** Fixes from the GDS re-audit: each labelled field's spoken name contains its
  visible label, the start page reflows at 320 pixels, and the sign-in page names its language.
- **New demo material.** Public datasets with a VAST catalogue and a cyber-intrusion pack; Operation
  Ledger's monitoring week; the prison demo's monitoring batches.
- **The API's OpenAPI document** is published at `/v1/openapi.json`, behind sign-in, versioned with the
  release.

## v0.4.1 — 2026-10-29

Nothing to do before updating.

- **Fixed: the top bar never pushes the account menu off screen.** From 1,100 pixels the bar was held
  to one line, but a case's name and its scope badge can make it wider than the window (a Prison
  Intelligence case at 1,440 pixels was 1,466 wide, the account menu and its clearance off screen).
  Whole items now wrap to a second line whenever they do not fit, at any width.
- **Fixed: opening the timeline over a drawn map no longer blanks the map.** The map's camera jumped
  to the bottom edge of the world whenever its box changed height, because the map layer that draws
  the graph tied a node's position to that height. The layer is now part of OspreyFlow (MIT; see
  NOTICE), positions no longer depend on the box, and the map keeps the area it showed.
- **New demo pack: the Prison Intelligence scale cohort.** `ospreyflow demo add
  prison-intelligence-scale` adds 3,000 prisoners and 30,000 links across six establishments in a
  case of their own, for showing a large network grouped by community. Its 3,000 prison numbers, for
  *Add many from a list*, come from `python -m scripts.write_pid_files --out <folder> --profile
  scale`. Adding it again changes nothing.
- **Administration guide:** both Prison Intelligence packs are listed in §11.

## v0.4.0 — 2026-10-28

**Before you update.** Every published Ingest Studio pipeline is flagged once and must be
republished before it runs again: the core model moves to version 17 and the NIEM pack to version
3. If anyone on the deployment has changed a link or removed a picture, run this once after the
update, while the deployment is up:
`docker exec osprey-local-lite-api-1 python -m scripts.strip_change_provenance`
(see the bullet on link history). A second run changes nothing.

- **A new demonstration case, Prison Intelligence.** It adds a prison estate of prisoners, cells,
  visits, prison-phone calls, seized phones, prisoner money, throw-overs, incidents and
  intelligence reports, all invented. Add it with `ospreyflow demo add prison-intelligence`.
- **The Ingest Studio loads richer sources.**
  - A column can carry a row's own handling, tightened only, never loosened.
  - A Document holds its own text, so one report row gives both the report and its links.
  - A link can be a span from two columns, open or closed.
  - Account references in three spellings load as one account.
  - A pipeline remembers the rows it has loaded into each case, so running the same file again
    creates nothing. Verify says how many rows a run would skip.
  - An operator can revert a load. A revert that would take back someone else's data is refused.
  - Every entity and link on the Map screen can be reached and edited by keyboard.
- **For analysts.**
  - Add many from a list.
  - Select what is lit, and branch the slice.
  - The case brief.
  - Icons chosen by a property's value.
  - A property condition on a pattern node.
  - Graph facts cited in a Questions answer, and Ask to search, which turns a question into a
    draft pattern.
  - A weekday-by-hour cell brush on the timeline.
- **A hotlist alert explains itself.** It shows the hotlist, what matched, and which files and
  rows it was read from.
- **Row numbers count from 1.** Wherever a row is shown, the first row after the header is now
  row 1: an alert's "From:", the Inspector's source, a link's details, Verify's rejected rows and
  held rows. Data already loaded keeps its meaning and is not reloaded. The API still counts from
  0 (developer guide §6.1).
- **A case's domain packs.** A case is created with its domain models, an Author can change them,
  and they decide what Reports and Trends offer: KYC for an AML case, a POLE summary for the rest.
- **Large working sets.** One with more than 10,000 links opens grouped by community. Zoomed out,
  it draws one link per pair of communities, and above 10,000 nodes it draws nodes as dots.
- **Security: nothing withheld leaks through a count or a source.**
  - The status bar says only "This case holds material you are not cleared to see", never a
    figure.
  - A link's weight and counts come from the link alone, never from the whole corpus.
  - A link merges only within one audience.
  - An element's sources are shown only when every dataset it belongs to is one the case reads.
    Otherwise the Glass says "Its sources are in data this case does not read".
  - Link history is filtered for each reader, and a changed link no longer names the one it
    replaced. Links changed before this release still name it until the script above runs.
- **Security: pypdf 6.21.2.** It fixes three denial-of-service advisories, each caused by a
  malformed PDF (CVE-2026-115572, CVE-2026-115580, CVE-2026-115585).
- **Security: the dashboard's image (Superset).** It takes Authlib 1.9.1, brotli 1.2.1 and certifi
  2026.10.18, and an up-to-date uv. Thirty newer findings in Pillow, msgpack and dnspython cannot be
  fixed inside Superset 6.1.0, so they are excepted until Superset 7.0, as six were before. Superset
  here makes no thumbnails, screenshots or PDFs, so it decodes no image with Pillow. It unpacks only
  its own cached results with msgpack, and does not use dnspython.
- **Security: the name-recognition image** takes filelock 4.2.1, past CVE-2026-112940 (an arbitrary
  file overwrite).
- **Removed:** the unused hover overlay for links. A link's details are in the Inspector, which a
  click or `L` opens.
- **Fixed:**
  - A notice on the canvas no longer closes the Layout menu.
  - Overlays close on Escape from the moment they appear.
  - Hotlists and monitors fire on a deployment that checks their owners with the identity
    provider. It looked owners up by username, but they are recorded by subject id, so every owner
    read as unknown and nothing fired.

## v0.3.0 — 2026-10-19

- **Dependencies brought up to date.** Python: every package to its newest release (among them
  FastAPI 0.146, Starlette 1.9, pydantic 2.14, pyarrow 26, torch 2.14, transformers 5.20), and the
  name-recognition image's FastAPI, Starlette, uvicorn and torch with them. The Glass: React 19,
  Vite 8, Playwright 1.64, jsdom 29, immer 11, and every minor release. Held back, each for a
  reason: the graph renderer Sigma stays on 3.x (version 4 changes the APIs the canvas is drawn
  with; it is its own piece of work), MapLibre on 4.x (Sigma's map layer accepts no newer), splink
  on 3.9.9 and Stanza on 1.10.1 (their next releases bring GPL dependencies), and the Superset
  image as pinned.
- **About MapLibre's advisory GHSA-jrc7-96c5-q579** (an XSS bypass in its HTML sanitiser, fixed only
  in MapLibre 6.4.1): the Glass never passes HTML through that sanitiser — it shows no MapLibre
  popups, and draws the map's attribution itself as plain text — so the flaw is not reachable.
  MapLibre moves past it with the Sigma 4 work.
- **A clone keeps your deployment's secrets out of its commits.** The product's `.gitignore` now
  covers what `ospreyflow` writes into the folder — the rendered deployment (its `deployment.env`
  holds the generated passwords), backup sets, local data, the real-data exceptions list, and
  build output — so `git add -A` in a clone or fork no longer picks them up. If you have committed
  any of these already, remove them from your history.

## v0.2.0 — 2026-10-18

- **Prison and custody cases.** The crime case analysis pack (NIEM) gains an **incident** — an
  assault, a disorder or a find, with what was found and when — and the links a prison intelligence
  analyst works with: **shared a cell with** (the cell and the dates), **co-defendant of**, **in
  conflict with** (the reason), **visited** (in person or by video), and a person's **role in** an
  incident. Each link type has its own colour. The core model is unchanged, so no pipeline needs
  republishing.
- **The legend lists the links in view and filters them.** Under the types, each link type in its
  colour with how many, and a box to leave the type out of the view or bring it back.
- **The HMP demonstration case is a prison intelligence network.** Around its principal subject and
  relay group: cell histories, co-defendants, conflicts (one known only from intelligence, and so
  SECRET), incidents with who was involved, visitors in person and by video, prison-phone and outside
  numbers with their calls, and accounts with their payments — on the graph, the timeline and the
  map, where the prison, its yards and the outside towns are places. Everything in it is invented.
  A deployment that added HMP before this release gains the
  network with `ospreyflow demo add hmp`; the people and incidents it has are not added twice.
- **Security: a pipeline reads its source only from the ingest folder.** A pipeline author could
  give a draft any server path and read the file back as sample rows; a path outside the ingest
  folder is now refused, whether or not it exists. Every deployment on v0.1.x should update.
- **Fixed: an account is on the map where it is held, and a payment draws as a line.** The map
  placed only locations, so an account's branch point was never shown.
- **Fixed: the legend no longer runs over the open timeline;** it scrolls inside the canvas.
- **Fixed: Explore's *Add… → Just this entity* adds just that entity.** It drew the entity three
  links out, as choosing a search result does, and *with all n links* did the same before its own
  one-link step; on a busy case that put hundreds of nodes on the canvas. What Explore adds now
  also reaches the case's working set, so the counts and legend see it straight away.
- **Fixed: a resolution run no longer undoes an analyst's link.** A model's later match of a pair an
  analyst had linked by hand (or confirmed) replaced the link's confirmation and score with the
  model's, so the pair could stop showing as one. An analyst's decision now stands until an analyst
  changes it.
- **Fixed: new evidence for a corrected link is kept.** Once a link had been corrected or confirmed,
  a later load touching the same pair could add its evidence to the old version, which no view
  shows. It now goes to the current link.

## v0.1.1 — 2026-10-15

- **The Glass stays responsive while a large case's icons load.** When a node icon finished
  loading, the canvas redrew the whole graph in one go; on a slow machine a 50,000-node case froze
  for several seconds just after it appeared. It now redraws only the nodes, a share per frame.
- Includes everything in v0.1.0, among it the fix for a model download that stopped with
  `rename …-partial …: no such file or directory`.

## v0.1.0 — 2026-10-15

The first release.

- **Install and look after it with one command**: `ospreyflow install`, `start`, `stop`, `status`,
  `logs`, `backup`, `restore`, `demo` and `update`.
- **Signed releases and safe updates**: every image of a release, and its list of image digests,
  is signed by the release workflow and checked before it is used. `ospreyflow update` backs up,
  moves to the release, checks it, and puts the previous release and its data back if anything
  fails; `update --check` (and Admin → System) says whether a newer release exists; a release can
  be carried to a machine with no network in one file (`--make-bundle`, `--from`).
- **Nothing leaves the deployment unless a configured feature needs it**: every service sits on an
  internal network; only the front door and the model downloads reach outside.
- **Find connections**: how two people are connected, by degrees of separation, widened one degree
  at a time, with any route put on the canvas.
- **A client's own model provider**, used only for material whose handling code allows it.
- **Scheduled pipelines** with a run ledger, notices to their owners, and *Run now* and *Change
  schedule* in the Admin area.
- **The Glass to the design review**: the welcome page and sign-in, Home, smaller nodes with their
  icons from closer zoom, the theme in the top bar, and each case's datasets beside its name.
- **Three ways to install**: Lite on one machine, Small on one AWS or Azure server with managed
  services, and Enterprise on EKS or AKS from a Helm chart (`ospreyflow install --mode …`).
- **Demo packs**, added with `ospreyflow demo add`: three synthetic cases, PaySim from its published
  file, and the Enron email corpus as an optional download — real people's email, which you fetch
  from its source yourself and accept before anything is loaded; it is never part of a release.
- **Guides** for administrators, analysts and data engineers in `docs/`, as Markdown and PDF.
- **Cases and their branches in one tree**, a branch renamed or deleted where it is listed, and
  *Show links among these* across one to six degrees.
- **`ospreyflow repair-sign-in`** brings an existing deployment's sign-in up to date.
- **Fixed: a model download could fail** with `rename …-partial …: no such file or directory` when
  the model server started while the download was running.
- **The recogniser's models are checked**: every file is pinned by its SHA-256 when the image is
  built, and nothing else may be loaded.
