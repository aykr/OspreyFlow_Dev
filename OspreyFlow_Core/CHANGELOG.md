# Changelog

Each release of OspreyFlow has a section here, newest first: `## vMAJOR.MINOR.PATCH — YYYY-MM-DD`.
A release's section is its release notes, and what `ospreyflow update --check` shows before you
update. Work not yet in a release is listed under *Unreleased*.

## Unreleased

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
