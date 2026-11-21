# Slice BL1c · BL1 · The citation check skips the slice line's own working papers, by folder, and says how many files it skipped

- **Build id:** BL1 (Ground; run as the slice BL1c, a follow-up of BL1b: the owner's word of 21 November, "Run it as BL1c. No plan page change."). **The five skipped locations (items 1 to 5 below) are approved by the owner as the conductor read them, including the files directly in `process/lanes/v062/`.** The owner's ruling 1 of 21 November 2026, in full: *`tools/doc_citations_check.py` scans every `.md` in the repository, so a brief or table of the conductor's that cites a file not yet written (or mistyped) turns `main` red and stops whichever slice picks it up. Four stops in two days; none was a fault in the product. One small slice in Ground, no scout. (1) The check skips the line's working papers under `OspreyFlow_Build/process/lanes/v062/`: slice briefs, tables, reports, scout notes, morning notes and proposals; the brief names the exact folders. (2) It still checks everything else exactly as now: product code, tests, specifications, ADRs, the build plan, the guides, and the slice line's own README and scripts. (3) Skipped by path, not by allowlist entries. (4) Shown red first (rule 15): a planted broken citation in a working paper passes; the same citation in a specification still fails. (5) Its last line of output says how many files it skipped, so the skip is visible. It does not jump the PL4 chain or anything on keys.*
- **Dial setting:** balanced
- **Rounds limit:** the dial's (8)
- **After:** nothing. Run it when a builder is free.
- **Status of this brief:** written by the conductor on 21 November 2026. Not in the owner's wording: the folder list below, which is the conductor's reading.

## The folders skipped (exact, relative to `OspreyFlow_Build/`)

All under `process/lanes/v062/`, and nothing else:

1. `process/lanes/v062/slices/` (slice briefs, tables, reports, scout notes, the `_OUT` deliverable folders)
2. `process/lanes/v062/backlog/` (the backlog's tables)
3. `process/lanes/v062/slice-line/proposals/` (line-fix briefs and the diffs proposed to the owner)
4. `process/lanes/v062/slice-line/diffs/` (applied-diff records and helper scripts)
5. The files directly in `process/lanes/v062/` (`RULINGS.md`, `CONDUCTOR_BRIEF.md`, `BACKLOG.md`, `SLICE_BRIEF.template.md`, the morning notes, `LINE_FAULTS_*`, `PL11_LICENCE_TABLE_*` and any later dated note): skipped as files of that one folder, **not** its sub-folders other than the four above.

**Still checked exactly as now:** `process/lanes/v062/slice-line/README.md` (the slice line's own README), `OspreyFlow_Build/scripts/slice_line/` (its scripts and their docs), every other folder under `process/`, `spec/`, `docs`, the guides, the build plan, `tests/`, `tools/`, the product code. **If the folder list above is wrong for a file you find (for example a sub-folder of v062 the conductor did not name), say so in your report and do not widen it yourself.**

## What (in this order; each red first)

1. **Skip by path, in code, not by allowlist.** In `OspreyFlow_Build/tools/doc_citations_check.py`, a constant naming the skipped folders (and the direct-file rule of item 5), applied in `scanned_files`; not an entry in `tests/fixtures/citation_allowlist.txt`; the allowlist stays as it is.
2. **Last line of output.** `main()` (and `find_broken` if the count belongs there) prints as its last line `citation-check: skipped N files (the slice line's working papers under process/lanes/v062/)` on success and on failure; N is the number of `.md` (and any other scanned suffix) files the skip removed from the scan, counted, not hard-coded.
3. **Tests, red first (rule 15), in `OspreyFlow_Build/tests/test_doc_citations_check.py` (extend) and the shape the check really sees (a temporary tree with the real folder names):** a broken citation in a working paper under each skipped folder passes; the same broken citation in `spec/`, in a guide under `OspreyFlow_Core/docs/`, in `process/lanes/v062/slice-line/README.md` and in a file under `process/lanes/` outside `v062/` still fails; the count printed equals the number of files planted in skipped folders; a sub-folder of `v062/` not in the list is still checked (planted: `process/lanes/v062/other/x.md`); the existing tests stay green; **`test_the_repository_itself_is_clean` passes on a tree in which a working paper cites a missing file.** Plant: widen the skip to all of `process/` (red); drop the count line (red).
4. **Report the skipped count on the real tree** and list the folders actually skipped, so the owner sees what the skip covers.

## Acceptance test

`OspreyFlow_Build/tests/test_doc_citations_check.py` (extended; the new cases red first on main). **Say which folders it walks** (a scan row is written from that if it is a new walker).

## Checks (pure; store ports pinned to 9)

`tests/test_doc_citations_check.py`, `tests/test_spec_doc_paths.py`, `tests/test_lanes_check*.py` if any reads the same list, `ruff check .`. **No `tests/test_layout.py`.**

## Out of scope

Any other check; the allowlist's contents; the product; the protected files (the `citation-check` target is unchanged).
