# The sites step: items 4 and 5, proposed for the owner and not applied

Nothing here runs or is wired in. `publish_pages.sh` is unchanged on this branch, and pytest does not collect this
folder (its `testpaths` is `tests`). Applying them means moving each file to the place named below.

| File | Where it would go | What it is |
| --- | --- | --- |
| `identifier_check.py` | `marketing_site/identifier_check.py` | Item 4. The personal-identifier rule, in place of `publish_pages.sh`'s grep. The owner's identifiers and a path on this machine are refused on every page, as before. ospreyflow.org's `team.html` alone names the six people in `TEAM_NAMES`, in their own person cards, each once. None of those six is named on any other page of either site. |
| `TEAM_NAMES` | `marketing_site/TEAM_NAMES` | The six names (the owner's decision 1: Couldridge). It changes together with the Team page. |
| `test_site_identifiers.py` | `tests/test_site_identifiers.py` | 19 cases. Red first: 17 fail against the old rule written as the same checker (`RED_RECORD.txt`): among them a seventh card, a renamed card, a name twice, each other name on another page, and a name in another case or spacing. One case plants the shared mailbox, `servicecentre@solirius.com`, on a page naming nobody, and shows it is not a personal identifier. |
| `publish_pages.diff` | `marketing_site/publish_pages.sh` | Items 4 and 5. The new check called in place of the grep. `--site org\|net` publishes `sites/<site>/` whole to that site's own repository, through a checkout beside this one (`OspreyFlow_site_<site>`) whose origin must match `sites/REPOSITORIES`, and writes the site's `.nojekyll` and `CNAME` (`ospreyflow.org`, `ospreyflow.net`) itself, so `build.py`'s output is unchanged. The arguments are taken in any order; an unknown one, or `--site` with no site, stops. With no `--site`, the current site is published exactly as before. |
| `REPOSITORIES` | `marketing_site/sites/REPOSITORIES` | Empty until the owner creates the two repositories and writes their addresses; until then `--site` stops in words. |

**Limit of item 4.** People are recognised by the Team page's person cards and the list of six, read in any case and
spacing. A seventh name written in running prose, outside a card, is not detected; the current rule has never detected
names in general either.

**What the owner does for item 5, outside the script.** Create the two repositories and set Pages to serve
`gh-pages`. Each site's domain needs DNS records: the apex's A and AAAA records to GitHub Pages, and `www` as a CNAME.
Verify both domains on the account, and enforce HTTPS.
