# The sites against release v0.5.2

The docs lane, 15 November 2026, at the orchestrator's word: the cut was brought forward, and the owner's word to do
this before it was the orchestrator's message. The CHANGELOG now names v0.5.2, and `build.py` refused to build while
`CHECKED_AGAINST` was `v0.5.1`. Every claim the pages mark as in the release, or as only on main, was checked again,
and `CHECKED_AGAINST` is now `v0.5.2`. The checks were against main at 33804f9, the candidate's base, since no v0.5.2 tag
exists yet, and against v0.5.1 (e024f7d). Paths are relative to `OspreyFlow_Core/`.

**Next check:** at v0.5.3. If the cut's candidate differs from main at 33804f9 in anything these pages claim, check it again
before the tag. The results-over-canvas fix does not touch them.

## Moved from "On main, coming with the next release" into the release

These are the three items v0.5.1's CHANGELOG said v0.5.2 brings. Each is in v0.5.2's CHANGELOG section and on main.

| Claim | Where it now stands | Source on main |
| --- | --- | --- |
| Scheduled runs on the shared-platform profile, as their owner, while the owner has signed in within the last 24 hours | Features, *Admin and access*, *A shared government platform*: "There, scheduled runs act as their owner while the owner has signed in within the last 24 hours" | administration guide §6a.7, "A run acts as its owner as Admin › People and roles holds them" (ADR-148 Amendment 16); `packages/principal_auth/__init__.py` |
| Reporting on the shared-platform profile, through Apache Superset | The same card: "and reporting runs through Apache Superset" | administration guide §6a.1 and §9 (ADR-148 Amendments 9 to 11); `harness/cloud_platform/profile.yaml`'s `superset` workload |
| The shared-platform profile's data-safety fixes | Not named on its own: the card's "Installed and checked on a test cluster" and the guide's section 6a cover it. The Features page names no backup detail for any profile | administration guide §6a.8; `harness/cloud_platform_backups.py` |

The section "On main, coming with the next release" is removed, with its entry in the page's contents and the hero's
"except" clause. At the cut, nothing merged on main is outside the release.

## Added: search

v0.5.2 is the release that searches (its CHANGELOG, *Search*). Features, *The Glass: analysis*, gains a first line: "Names found
with typos, variants and sounds-like matches, full text with the passage highlighted, and suggestions as you type, with
your access inside every query."

The sources: ADR-149 and ADR-150; `services/api/search_access.py`'s `index_access_filter`, given to every search by
its route (held by `tests/test_guides_ports_and_search.py`); and user guide §5.5. Step 4's M3, M4 and M1 measured
names, full text and suggestions (`process/lanes/platform/v052-measure/RESULTS.md`). The architecture card's
"OpenSearch for search" is unchanged and true.

## Checked and unchanged

- **Get started.** The three commands are in main: `install.sh` still runs `uv tool install --editable "$product/cli"`,
  and so are `ospreyflow doctor`, `install --mode lite` with `--gui` and `--config install.yaml --yes`, and `open`.
  Lite still needs at least 16 GB for Docker (32 GB is comfortable) and 60 GB free, and Small's own server still needs
  32 GB (administration guide §2). `ospreyflow update --check` is still `harness/update.py`'s `--check`.
- **Extraction's** "a second, open-source extraction engine … no screen uses it yet": still true. The administration
  guide's §6a.10 lists "Laurium reached from a screen" as coming.
- **Hosted engines'** "checked so far against a stand-in gateway, not yet against AWS or an organisation's own": still
  true. The administration guide's §6a.9 says "Not yet tried. The route is checked as rendered, against a stand-in
  gateway". Step 6's install test does not change this.
- **ospreyflow.net, Services**, "A shared government platform … in the current release: installed and checked on a
  test cluster, not yet on a platform": true of v0.5.2.
- **The release badge** on every page reads v0.5.2, from the CHANGELOG at build time. The other pages differ from their
  v0.5.1 build in the badge alone.
- **Ask & Chat, search and navigation words:** the pages already say Ask & Chat (step 5's sweep). Nothing on them names
  *More views*, *Views in this case* or *Clear view* (`tests/test_guide_navigation_words.py` reads `build.py` and the
  built pages).

## Left for §10, the screenshots

Some image alt text says "view" in the sense ADR-145 Amendment 17 retired on screen: "The Matrix view", and
"History: every step taken in a view". Those captures are replaced after the cut (item 6, §10), and their alt text
goes with them.
