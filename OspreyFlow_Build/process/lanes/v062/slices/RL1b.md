# Slice RL1b · RL1 · The version is 0.7.0 (the owner's one release at the end of this plan; D227)

- **Build id:** RL1 (the release line; a follow-up of RL1's manifest). **The owner's ruling of 24 November 2026 (D227, in chat):** "One release at the end of this plan, numbered 0.7.0. No interim release. **Rename once, now: the product's `VERSION` and every text still to be written (CHANGELOG heading, release notes, guides) say 0.7.0. Records already written that say v0.6.2 stay as they are; the lane folders (`v062`) are not renamed. Write any slice brief from now with 0.7.0.**"
- **Dial setting:** balanced. **Rounds limit:** the dial's (8).
- **After:** nothing unmerged. **Every finding that names a key, a credential or a security rule is the owner's.**

## What exists (read each before you change it)

`OspreyFlow_Core/VERSION` says `v0.6.1` (the last release). `OspreyFlow_Core/CHANGELOG.md`: "Each release has a section here, newest first: `## vMAJOR.MINOR.PATCH — YYYY-MM-DD`", with work not yet in a release under *Unreleased*. Text that names `0.6.2` today, outside the process folder (the scout's list; re-run `git grep -n "0\.6\.2"` yourself): `OspreyFlow_Build/spec/10_ADMINISTRATION_GUIDE.md`, `OspreyFlow_Core/docs/administration-guide.md`, `OspreyFlow_Core/docs/architecture-guide.md`, `OspreyFlow_Build/tests/test_intent_in_the_guides.py`, `OspreyFlow_Build/tests/test_release_owed.py`, `OspreyFlow_Build/tools/release_local.py`, `OspreyFlow_Build/scripts/publish_user_repo_update.sh`, `OspreyFlow_Build/Makefile`, `OspreyFlow_Build/spec/06_DECISIONS.md` and `OspreyFlow_Build/spec/ADR_RESERVATIONS.md` (**records: leave**), `OspreyFlow_Build/tests/harness/test_image_references.py` and `OspreyFlow_Core/harness/render.py` (about line 630: `ghcr.io/speaches-ai/speaches:0.6.2` is **a third party's image tag, not this product's version: leave it**), `OspreyFlow_Core/apps/pages/test/server/forward.test.ts`, `OspreyFlow_Build/tests/harness/test_refresh_plain_lines.py`. The guides have PDFs and a manifest (`tools.docs_pdf --write` makes them again; `OspreyFlow_Core/docs/pdf/manifest.json`).

## What (in this order; red first, planted at the shape the code really reads)

1. **Sort every `0.6.2` into three heaps and say so in your report (a table: file, line, heap):** (a) **this product's coming version, in text still to be read** (guides, the CHANGELOG, release-note text, a message a user sees, a docstring that says what this release does): **change to 0.7.0**; (b) **a record of what was written** (decision records, ADR reservations, merge and lane papers, the lane folder `v062`, a test's comment that quotes a record): **leave exactly as it is**; (c) **not this product's version** (a third party's image tag, a dependency): **leave**. **When in doubt, leave it and list it for the conductor.** Do not rename any folder.
2. **`OspreyFlow_Core/VERSION` becomes `v0.7.0`** (the owner ruled the product's `VERSION` says 0.7.0 now). **Find every reader of `VERSION`** (the CLI's `update --check`, the bundle, the release script, the image tags, the chart's appVersion, the docs build) **and every test that reads it; say in your report what each now does with `v0.7.0` before a release exists** (for example `update --check` on a deployment at 0.6.1 sees a version with no CHANGELOG section: **it must not break; if it does, STOP and tell the conductor what breaks**: the release part (RL2) owns the section, and this part must not invent one). The CHANGELOG's *Unreleased* heading stays *Unreleased* (RL2 turns it into `## v0.7.0 — <date>`); **only the text that names the coming version changes.**
3. **A pure test (new, red first):** `VERSION` reads `v0.7.0`; **no file in heap (a) still says `0.6.2`** (the test holds the list of allowed files, each with its heap, so a new `0.6.2` in a guide or the CHANGELOG is red); the records' files are not in the scan (planted: `0.6.2` added to a guide is red; added to an ADR is not). **Say which folders it walks** (a scan-map row is written from that; a builder cannot add it).
4. **Regenerate** the guides' PDFs and manifest with `tools.docs_pdf --write` if you changed a guide's text; run the guides' tests.
5. **Report:** the three-heap table, the `VERSION` readers and what each does now, the list of files left and why.

## Acceptance test

`OspreyFlow_Build/tests/test_version_is_0_7_0.py` (new, pure, red first).

## Checks (pure; store ports pinned to 9)

The new test; `tests/test_intent_in_the_guides.py`, `tests/test_release_owed.py`, `tests/test_doc_citations_check.py`; the guides' PDF test and the docs manifest check; every other test that reads `VERSION` or the CHANGELOG (find them: `git grep -ln "VERSION\|CHANGELOG" -- OspreyFlow_Build/tests`); `ruff check .`. Before your final report run by hand what the conductor runs again: ruff on every file changed and the scan-map check for the new test.

## Never merge another part's unmerged tip (the owner, 23 November 2026)

**Never merge another part's unmerged tip, or any branch but main, into your branch.** Take main in when the line tells you to, and nothing else. If your part needs another part's change that has not merged, stop and tell the conductor.

## Out of scope

The release itself (RL2); the CHANGELOG's section for 0.7.0; tags, images, signing; any renaming of folders or lane papers; the protected files. **A finding that names a key, a credential or a security rule is stopped and reported, never accepted narrower.**
