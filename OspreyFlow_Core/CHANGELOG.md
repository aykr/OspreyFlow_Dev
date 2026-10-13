# Changelog

Each release of OspreyFlow has a section here, newest first: `## vMAJOR.MINOR.PATCH — YYYY-MM-DD`.
A release's section is its release notes, and what `ospreyflow update --check` shows before you
update. Work not yet in a release is listed under *Unreleased*.

## Unreleased

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
