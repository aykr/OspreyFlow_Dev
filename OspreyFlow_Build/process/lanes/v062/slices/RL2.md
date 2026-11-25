# Slice RL2 · RL2 · Release 0.7.0 (DRAFT, NOT STARTED, NO ROW: it comes after the last builds; publishing is the owner's word)

- **Written by the conductor on 24 November 2026 from the owner's ruling D227 (in chat): "one release at the end of this plan, numbered 0.7.0. No interim release."** RL2 is the release, in the plan after the last builds. **It prepares the release and stops: the owner publishes.** Every text from now says 0.7.0; records already written that say v0.6.2 stay as they are and the lane folders (`v062`) are not renamed (RL1b does the rename of the version and the live texts).
- **Needs:** every build in the plan whose slices are to ship merged (the owner names the last one), RL1b merged.
- **Every finding that names a key, a credential, a certificate or a security rule is the owner's.**

## What it must show before the owner is asked to publish (each item has a test or a recorded run, not a sentence)

1. **Every release blocker in `BACKLOG.md` cleared** ("RELEASE BLOCKERS", read the section on the day): BLOCKER 1 (PL7f merged; `pages.enabled` still off for the demo and every deployment of the owner's unless he has said otherwise; no guide or release note describes the setting as available), BLOCKER 2 (AD1c landed: the fourth route closed and the already-orphaned engine tokens shown none left), and **every blocker added after this draft** (the section is the list; the part reads it, never a copy).
2. **The owed live tests run: `owed.py check` exits 0.** (325 distinct files were owed on 24 November 2026. They are paid by the merge script's live step when it is on, which writes `live-paid.json`; the line-fix session is building it. Until then the count falls only by that step. The count is reported every morning and must reach zero before this part starts.)
3. **GitHub green on the release commit,** by name: the run on the exact commit, every job, with no failure waved through as "known"; the keyboard flake, rows 22 and 23 and any other excepted failure are each **either fixed or listed to the owner by run id**; the owner decides whether a listed one blocks.
4. **An upgrade test from 0.6.1:** a deployment installed at v0.6.1 (the last release) is updated to the release commit with `ospreyflow start --build` and with `apply`, on the Mac under the stack lease, and **its data, its settings file and its secrets are intact** (no setting changed or lost, the plain lines PL14a adds are present, no secret changed), the demo opens and signs in, and the report shows each step's output. **The deployment it upgrades is a throwaway copy, never the owner's.** If the upgrade breaks, STOP and report with the step.
4b. **The cut sets `OspreyFlow_Core/VERSION` to the bare tag `v0.7.0` in the candidate commit and main moves to `v0.7.1-dev` (or the next planned `-dev`) afterwards** (ADR-114 Amendment 47, decision 4); until then `VERSION` is `v0.7.0-dev` (RL1b, round 2: the conductor's first brief wrongly said `v0.7.0`).
5. **Release notes** in the owner's wording rules (the rules he gave for the notes: read `RULINGS.md` and `BACKLOG.md` for every rule he stated about words, including "the release note's three cases are four", the plain statement of what the page service setting is and is not, and the rule that nothing says "coming" for what is built); **the CHANGELOG's *Unreleased* heading becomes `## v0.7.0 — <date>`** with those notes; a test that the section exists for `VERSION` and that `ospreyflow update --check` shows it.
6. **Images built, scanned, signed and listed** as the release path already does (`OspreyFlow_Build/tools/release_local.py`; the release list is a protected file: any change is a diff for the owner); **the signing key is the owner's** (the part never reads, prints or holds it).
7. **The maintainer's manifest generated for the release** (RL1's generator) and attached.
8. **The guides** (user, administration, architecture, developer) say 0.7.0 where they name the version, their PDFs and manifest regenerated, the guides' tests green.
9. **A one-page report to the owner:** each item above with its evidence (a path, a run id, a log); **nothing is published, tagged or pushed to a registry by this part**.

## Never merge another part's unmerged tip (the owner, 23 November 2026)

**Never merge another part's unmerged tip, or any branch but main, into your branch.** Take main in when the line tells you to, and nothing else.

## Out of scope

Publishing, tagging, pushing images, signing with the owner's key, and any change to the protected files (diffs for the owner). **A finding that names a key, a credential or a security rule is stopped and reported, never accepted narrower.**
