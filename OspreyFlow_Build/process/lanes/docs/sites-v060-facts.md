# The sites against release v0.6.0

The docs lane, 15 November 2026, for v0.6.0's item 9, the rename (the owner's plan of 15 November: one release, v0.6.0,
installed fresh; v0.5.2 never published). The CHANGELOG's v0.5.2 section became v0.6.0's, so `build.py` refused to
build while `CHECKED_AGAINST` was `v0.5.2`. The pages were checked against v0.5.2 that same morning
(`sites-v052-facts.md`), against main at the code v0.6.0 ships so far. The rename changes no code they describe, so
each claim was read again for what the rename does change: how a deployment reaches the release. Checked against main
at 7dd860e. `CHECKED_AGAINST` is now `v0.6.0`.

## What the rename touches

- **Features, *Backups and updates*:** "On one computer or a server of your own, installed from a release, an update is
  backed up first and rolled back on failure". Still true of an update from v0.6.0 to a later release (administration
  guide §14). The pages say nothing about moving an earlier deployment onto a release, so v0.6.0's fresh-install rule
  makes no claim on them untrue. The rule is the CHANGELOG's first sentence and §14's opening.
- **Get started, *Releases*:** "A checkout of a release tag installs that release's own signed images", and
  `ospreyflow update --check`. Both unchanged.
- **The release badge** on every page reads v0.6.0, from the CHANGELOG at build time. The pages differ from their v0.5.2
  build in the badge alone.

## Not checked again

Everything `sites-v052-facts.md` records. v0.6.0's own items, built after today, are checked against the tag before
the owner says "publish" (the sites' publication is on v0.6.1's list).

**Next check:** at v0.6.0's tag. If anything merged for v0.6.0 changes a claim the pages make, check it again then.
