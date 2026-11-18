# Slice BL6 · BL6 · The client-name check, and the reword

- **Build id:** BL6
- **Dial setting:** balanced
- **Rounds limit:** 2
- **After:** nothing
- **Status of this brief:** APPROVED by the owner, 18 November 2026. The owner adds the full name to the hashed list
  (`marketing_site/client_hashes.py`) before the builder runs: today it held only the abbreviation, so a check built
  without it would pass the full name. After `slice_start.py BL6` the conductor copies the list into the slice's worktree
  (a worktree is a fresh checkout and the list is gitignored, so the builder could not see a single hit without it).
  The owner accepts that the slice's first merge attempt may fail on the form of its acceptance command (the line has
  never run a product slice's acceptance through the merge script: `slice-line/LINE_FAULTS_2026-11-18.md`, F4).

## What

The rulings of 18 November 2026 (`RULINGS.md`, "the client's name and Laurium"), in full; they are the brief:
the client's name (full name and abbreviation) stays only in `OspreyFlow_Core/NOTICE`,
`OspreyFlow_Core/services/laurium/NOTICE`, `OspreyFlow_Build/tools/licence_check.py` and
`OspreyFlow_Core/services/laurium/licence_gate.py`; everywhere else it is reworded to "UK public sector client", and
where text credits Laurium, to "the library's publisher". Laurium's own name may stay in the product and its records but
never in a published website file (`publish_pages.sh`'s set: `deploy/index.html`, `intro-video.html`,
`public-sector.html`, `monitoring.html`, `assets/`, and `sites/org/` and `sites/net/` whole; never the two READMEs).

1. **The check** (new `OspreyFlow_Build/tools/client_name_check.py`, target `client-name-check` in
   `OspreyFlow_Build/Makefile`, added to `ci:`). It uses `marketing_site/client_hashes.py` (`known`, `named`, `ABSENT`)
   so no name is ever written down or printed; a hit prints file and line and the count, never the hash or the name.
   Scope: git-tracked files (`git ls-files`), non-UTF-8 files read as `identifier_check._read` does. The four keep-files
   are exempt for the client. Laurium's name is checked in the published website files only (the pattern at
   `tests/test_sites.py:61`). Where the list is absent the check says so in the words of `client_hashes.ABSENT` and
   exits 0, as `identifier_check` does: on GitHub (which runs no `make ci` today) and in a worktree without the list.
   The Mac's merge gate refuses a merge without the list, so there it always runs.
2. **The reword**, found by the check, in `spec/`, `process/`, tests, and wherever else it reports; including the two
   occurrences inside a cited file path in `06_DECISIONS.md` (no file has that path; reword the citation).
   Two hits in tests are a docstring and a comment; no code depends on them.

## Acceptance test

New file `OspreyFlow_Build/tests/test_client_name_check.py`, in the style of `tests/test_sites.py` (rule 15: a synthetic
name hashed into a temp list, planted in the shape each real caller produces): a tracked file naming it is flagged;
each of the four keep-files is not; Laurium in a published website file is flagged and in `sites/README.md` is not;
the list absent prints the words and exits 0; a hit never prints the name or its hash; and a case that runs the check
over the real tree with the real list, which is red today because the tree names the client and green after the reword.
Where the real list is absent that case must say it did not run (not skip silently).

## Checks

`tests/test_sites.py`, `tests/test_site_identifiers.py`, the acceptance file, and `make -C OspreyFlow_Build
client-name-check`. In the merge tree the gate copies the list in before `make -k ci` (`merge_slice.bring_client_hashes`).

## Out of scope

Git history; the owner's four keep-files; any website text beyond the reword; adding names to the list (the owner's).
A hit the builder cannot reword without changing meaning: stop and ask, never delete a record.
