# Changelog

Each release of OspreyFlow has a section here, newest first: `## vMAJOR.MINOR.PATCH — YYYY-MM-DD`.
A release's section is its release notes, and what `ospreyflow update --check` shows before you
update. Work not yet in a release is listed under *Unreleased*.

## Unreleased

- **Install and look after it with one command**: `ospreyflow install`, `start`, `stop`, `status`,
  `logs`, `backup`, `restore`, `demo`, and `update --check`, which says whether a newer release
  exists (Admin → System shows the answer).
- **Nothing leaves the deployment unless a configured feature needs it**: every service sits on an
  internal network; only the front door and the model downloads reach outside.
- **Find connections**: how two people are connected, by degrees of separation, widened one degree
  at a time, with any route put on the canvas.
- **A client's own model provider**, used only for material whose handling code allows it.
- **Scheduled pipelines** with a run ledger, notices to their owners, and *Run now* and *Change
  schedule* in the Admin area.
- **The Glass to the design review**: the welcome page and sign-in, Home, smaller nodes with their
  icons from closer zoom, the theme in the top bar, and each case's datasets beside its name.
