# The owner's rulings for the v0.6.2 slice line

Rulings given in conversation, written here so the conductor and every seat read them (rule 11). Newest first. No
client's name or abbreviation is written in this file, nor in any message about it.

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
