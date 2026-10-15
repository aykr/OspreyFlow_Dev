# Changelog

Each release of OspreyFlow has a section here, newest first: `## vMAJOR.MINOR.PATCH — YYYY-MM-DD`.
A release's section is its release notes, and what `ospreyflow update --check` shows before you
update. Work not yet in a release is listed under *Unreleased*.

## Unreleased

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
