# The owner's rulings for the v0.6.2 slice line

Rulings given in conversation, written here so the conductor and every seat read them (rule 11). Newest first. No
client's name or abbreviation is written in this file, nor in any message about it.

## 18 November 2026: how the line runs, to cut down what needs the owner's hand

The owner's four rulings of 18 November 2026 (about 12:40 UTC).

1. **Standing approval to start a slice.** The conductor may start any slice whose build id is already on the owner's
   plan without asking, once it has (a) run the slice's acceptance and checks commands in a scratch worktree on main and
   shown the acceptance **red for the right reason** and the checks **green**, and (b) passed the citation check on the
   brief. Still the owner's: scope, rulings, protected files, the GOV.UK demo, the live step, a new build id, and anything
   that loosens or exempts a check. *How the conductor reads (a):* where the checks command names the slice's own new test
   file, which cannot exist on main, the check is run without that file and the table says so.
2. **Batches.** A stopped slice does not interrupt the owner. The conductor carries on with every other slice it can and
   brings the open decisions together, as numbered questions with options, at **13:00 and 18:00** the owner's time
   (this Mac's clock), or sooner only if every track is stopped. Security faults and anything that cannot be undone still
   come at once.
3. **The conductor's own malformed command.** Once the line has a step for it, the conductor may correct and resume a
   slice that stopped **only because the conductor's own command was malformed**, provided the corrected command runs the
   same test files, is proved on main first, is logged, and the owner is told afterwards. Never to change what a check
   tests. Until that step exists, the conductor keeps giving the owner a resume script. (The step's own limits are in the
   line, not in this file: the conductor can edit this file, so no authority here is enough on its own.)
4. **Fix the line's gaps now** (reverses "leave them"). One session outside the line, started by the owner, with the brief
   `slice-line/proposals/LINE_FIXES_BRIEF.md`, in this priority order: (a) a resume step, and the step in 3; (b) a dry run
   of a slice's frozen commands at `slice_start`, which refuses to start a slice whose commands do not run; (c) the test
   settings the Stop hook and the merge script lack (the Playwright slot, `env: full`: F4, F6, F8); (d) the hashed list
   reaching a slice's worktree without the owner (F5); (e) usage recorded per slice, seat and account; (f) a red GitHub run
   stops merging and shows on the board (F2); (g) BL1's record name (F3), then F1's three protections. Each with a test
   shown failing first; one set of diffs and one list of commands for the owner to apply.

## 18 November 2026: three compressed files exempt from the client-name check (BL6)

The owner's word, 18 November 2026, on the verifier's findings for BL6 round 2:

- The client-name check (`OspreyFlow_Build/tools/client_name_check.py`) exempts **exactly these three paths, and only
  while each is not text**: `OspreyFlow_Build/marketing_site/OspreyFlow Intro Video.mp4`,
  `OspreyFlow_Build/marketing_site/deploy/assets/ps-govuk-matrix.jpg`, and `OspreyFlow_Core/docs/pdf/user-guide.pdf`. Each
  holds the client's abbreviation only as chance bytes in compressed data.
- **Adding any other file to that list needs the owner's word each time.** The list's comment in the tool says so.
- The check cannot read real text inside a PDF, an image or a video, so those files are not covered by it. That is a
  backlog row (`BACKLOG.md`, "The client-name check cannot read inside a PDF, an image or a video").
- As worded, the exemption is the whole client check for those paths while they are not text (the full name too, not only
  the abbreviation). The verifier noted that this is wider than its reason; the conductor asked the owner whether to
  narrow it to the abbreviation.

## 18 November 2026: the live step

- Off, a change that reaches live tests merges on the offline gates; each live test not run is owed, the board shows
  what is owed, and a release is refused until every owed live test has run.
- The merge script's live step is off (`OspreyFlow_Build/process/lanes/v062/live_step.yaml`), until the demo's
  images no longer share tags with test builds. The owner turns it on. On, it waits for the server's run queue or
  refuses (`OspreyFlow_Build/process/lanes/v062/slice-line/README.md`, "The live step").

## 18 November 2026: the client's name and Laurium (build id BL6)

1. **Where the client's name stays.** Only in `OspreyFlow_Core/NOTICE`, `OspreyFlow_Core/services/laurium/NOTICE`,
   `OspreyFlow_Build/tools/licence_check.py` and `OspreyFlow_Core/services/laurium/licence_gate.py`, as the licences
   require. Everywhere else it goes, in every form (the full name and the abbreviation), including beside Laurium in
   specifications, notes and recorded gate output.
2. **The wording.** "UK public sector client"; where the text credits Laurium, "the library's publisher".
3. **Laurium** may be named in the product and its records. Neither Laurium nor the client is ever named in a
   website file under `OspreyFlow_Build/marketing_site` that is published.
4. **BL6 is the first real slice through the line**: the reword, together with a gate check. Any naming of the client
   outside the four files above fails; any naming of Laurium or the client in a published website file fails. The
   check uses the hashed list (`OspreyFlow_Build/marketing_site/client_hashes.py`), so no name is written down. The
   owner adds the full name to the hashed list.

### What BL6's builder needs to know (found 18 November 2026, on main at a4c441f)

- **What exists.** By the hashed list (which today holds the abbreviation, not the full name): 21 occurrences in 14
  files, 2 of them in `OspreyFlow_Core/services/laurium/NOTICE`, which stay. By the full name, read from the NOTICE
  files' copyright line: 23 lines in 13 files, 9 of them in the four files that keep it. Two of the occurrences are
  inside a cited file path in `OspreyFlow_Build/spec/06_DECISIONS.md`; no file in the repository has that path, and the
  ruling covers it too. The two hits in tests are a docstring and a comment, which no code depends on.
- **The hashed list is local.** `client_names.local.sha256` is gitignored (the owner's ruling, 12 November 2026) and
  never committed. The owner, 18 November 2026: the merge gate reads it from the main checkout and refuses the merge
  if it is missing (built: the full gate copies it into the merge tree); on GitHub the check says in words that it was
  not run, never passes silently (as `client_hashes.ABSENT` does today).
- **What "published" means.** `OspreyFlow_Build/marketing_site/publish_pages.sh` publishes, from `deploy/`,
  `index.html`, `intro-video.html`, `public-sector.html`, `monitoring.html`, `assets/` and `.nojekyll`; and each of
  `sites/org/` and `sites/net/` whole. `OspreyFlow_Build/marketing_site/sites/README.md` and
  `OspreyFlow_Build/marketing_site/deploy/README.md` are never published, and the product export
  (`OspreyFlow_Build/tools/publish_user_repo.py`) takes `OspreyFlow_Core` alone. The one Laurium mention under `marketing_site` is in
  `sites/README.md`: the wording rule "Laurium is not named (the owner's decision, 12 November 2026)".
- **Laurium beside the client.** Where a record credits Laurium to its publisher, the publisher becomes "the library's
  publisher"; Laurium's own name stays.
