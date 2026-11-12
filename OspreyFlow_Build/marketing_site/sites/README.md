# OspreyFlow's two websites: ospreyflow.org and ospreyflow.net

| Folder | Site | Pages |
| --- | --- | --- |
| `org/` | **ospreyflow.org**, the open-source project | Home, Features, UK public sector, Get started, Team, Contribute, Governance |
| `net/` | **ospreyflow.net**, Solirius Reply's services | Home, Where it applies, UK public sector, Services, Contact |

Both are plain static files: system fonts, their own style sheet and images, no script, and nothing fetched from
anywhere else. The current six-page site, in `../deploy/`, is separate and unchanged.

## How they are made

`build.py` writes every page and both style sheets. Its output in `org/` and `net/` is committed, because it is what
GitHub Pages will serve and what the tests read. Change a page by changing `build.py`, then run it with Python 3.12
or later (the repository's own; macOS's `python3` is older and cannot read it):

    OspreyFlow_Core/.venv/bin/python OspreyFlow_Build/marketing_site/sites/build.py

`tests/test_sites.py` fails when a committed page differs from what `build.py` writes. Run it before committing.

The images in `org/assets/` and `net/assets/` are committed and are not remade by a plain build. Fresh captures are
turned into them with `--images <folder of captures>`, which needs Pillow. Each capture's file name is listed in
`build.py`'s `SHOTS`. The images now in place are the drafts', and are to be replaced by captures from the rebuilt
demonstration after Friday 13 November (item 6). Captures use synthetic data only, in both looks.

## The rules every page is held to (`tests/test_sites.py`)

- The product's statement, and "Solirius Reply".
- "Designed to meet the GDS Service Standard", never a status only an assessment panel gives. The three checks are
  named as planned wherever the Standard is named.
- No client named. The names are held as SHA-256 hashes in `../client_names.local.sha256`, which is gitignored and
  stays on the machine that publishes: a hash of a short public name is not a secret, since anyone who hashes a list
  of candidates can tell which are in it (the owner's ruling, 12 November 2026). The owner makes it with
  `../client_hashes.py`, which prints a count and never a name. Where the file is present, the test checks every page
  against it. Where it is absent, the test is skipped with words saying the pages were not checked, never passed. The
  publish path refuses to publish without it (item 4's proposal). The test's own red cases use a synthetic name in a
  file of their own.
- The check reads what a page shows and every attribute's value (an address, a file name), with accents folded,
  invisible characters dropped and an abbreviation's full stops removed. It does not see a name broken by a tag in
  the middle of a word.
- No competitor named. i2 is not named until an ADR deciding it is accepted. Laurium is not named (the owner's
  decision, 12 November 2026).
- No local path, no credential and no placeholder. The only email address is `servicecentre@solirius.com`.
- No script, and no request outside the site. Every internal link and anchor resolves, including links between the
  two sites.

Each rule has a case that plants a violation and shows the check fails. The first run against the drafts as delivered
is in `process/lanes/docs/gates/sites-red-first.txt`.

## Before the owner publishes

- [ ] The two repositories exist, and their addresses are written where the publish script reads them (item 5's
      proposal, `process/lanes/docs/sites-proposal/`).
- [ ] Each domain's DNS points at GitHub Pages, both domains are verified on the account, and HTTPS is enforced.
- [ ] The service centre knows to expect OspreyFlow enquiries and security reports, and who they go to.
- [ ] The client's names are added with `client_hashes.py`, and the check is shown red with each name planted, in a
      session the owner runs.
- [ ] The publish script's identifier rule allows the Team page's six names (item 4's proposal). Until then it refuses
      `team.html`.
- [ ] The images are fresh captures from the rebuilt demonstration (item 6).
- [ ] What each page marks as in the release, and as only on `main`, is still true for the release then current.
      These pages were checked against v0.5.0 and `main` on 12 November 2026.

## The current site once these are live (item 7, proposed)

The current site is the product repository's `gh-pages` branch, at `https://aykr.github.io/OspreyFlow/`.
Recommendation: **redirect it, then retire it**.

1. **On the day the new sites are live**, publish a replacement for each of the four pages the publish script puts
   on that branch (`index.html`, `intro-video.html`, `public-sector.html`, `monitoring.html`), under the same
   name. `drawing-boards.html` and `three-places.html` are in `../deploy/` but have never been published. Each replacement is a small page that sends the reader on. It uses a meta
   refresh, a canonical link and a visible link, with no script. GitHub Pages cannot send a server redirect, so
   this is the nearest it allows.

   | Current page | Sends to |
   | --- | --- |
   | `index.html` | `https://ospreyflow.org/` |
   | `public-sector.html` | `https://ospreyflow.org/public-sector.html` |
   | `monitoring.html` | `https://ospreyflow.org/features.html#monitoring` |
   | `intro-video.html` | `https://ospreyflow.org/index.html` |

   The new sites carry no video. The animated overview stays in this repository, and whether it comes back on
   ospreyflow.org is the owner's to say.
2. **The owner changes the repository's website field** on GitHub to `https://ospreyflow.org`.
3. **After six months**, the owner switches Pages off for the product repository and deletes `gh-pages`. Six months
   lets links in decks, emails and search results catch up.
4. **In this repository, when the redirects are published:**
   - `../deploy/` is reduced to the four redirect pages;
   - `test_website_wording.py`'s checks of the current pages are retired, since `test_sites.py` already holds the
     same rules for the new pages;
   - the publish script's default path publishes the redirects.

   The decision log's mention of the address (ADR-114 Amendment 31) is history and stays. A new amendment records
   the move.

Leaving the current site up as it stands is not recommended: it would be a second, older account of the product,
contradicting the new one. Deleting it on the day would break every link already shared.
