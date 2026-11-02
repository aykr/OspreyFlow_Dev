# OspreyFlow website: going live

The site is five files and a folder:

| File | What it is |
| --- | --- |
| `index.html` | The home page: one file exported from the design tool, with fonts, screenshots, the Solirius Reply logo and the animation inside it. |
| `intro-video.html` | The animated overview, shown in the home page's video carousel. Keep it next to `index.html`. |
| `public-sector.html` | The UK public sector option: the GOV.UK theme for gov.uk services, designed to meet the GDS Service Standard, for every UK department (build order step 12). Hand-written, no external requests. |
| `monitoring.html` | Monitoring and alerting (build order step 12). Hand-written, no external requests. |
| `assets/` | The two new pages' screenshots (about 1 MB, nine JPEGs, 1440 × 900, no metadata), taken from synthetic demonstration cases only. |
| `.nojekyll` | Tells GitHub Pages to serve the files as they are. |

## How it is published: within the repository move (build order step 13)

The site is **not published until the repository move**, and then with the rest of the product's pages
(`process/REPO_MOVE_PLAN.md`, Stage 3, step 5). Nothing here is pushed before then.

1. In Stage 2, change the home page's `repoUrl` to `https://github.com/Solirius/ospreyflow` and export
   the site again (see "Changes waiting for the next export" below).
2. In Stage 3, `marketing_site/publish_pages.sh` (aimed at the new repository) copies `index.html`,
   `intro-video.html`, `public-sector.html`, `monitoring.html`, `assets/`, `.nojekyll` and, if present,
   `CNAME` onto the product repository's `gh-pages` branch, and Pages serves them at
   `https://solirius.github.io/ospreyflow/`.
3. In Stage 4, check the pages at the new address (the checklist below).

The new pages link to each other, to `index.html`, to `index.html#start` and to `intro-video.html`
only. They do not link to the repository, so `repoUrl` is the one place the address changes.

## How the home page was edited, and what the design source still needs

`index.html` keeps its visible page in a `<script type="__bundler/template">` block: one JSON string,
written with `</` as `</` and non-ASCII characters kept as they are. There is no checksum. On
2 November 2026 (step 12) the template was decoded, edited and encoded again with exactly that
encoding; the unedited template re-encodes to the same bytes, so nothing else in the file changed.
The edit added:

- two links in the header's navigation, **UK public sector** (`public-sector.html`) and **Monitoring**
  (`monitoring.html`);
- a section, **For the UK public sector, with monitoring at its core** (`#public-sector`, before
  *Get started*), with a card for each new page.

**Changes waiting for the next export.** The design source, `OspreyFlow Site.dc.html`, is not in this
repository, so the next export from it would undo the edit above. Before exporting again:

- add the two navigation links and the `#public-sector` section to the design source (copy them from
  the template in this `index.html`);
- set `repoUrl` to `https://github.com/Solirius/ospreyflow`, within the repository move (step 13), not
  before;
- run `OspreyFlow_Build/tests/test_website_wording.py` on the new export.

Found in the browser check (step 12), and already in the export before it: the home page asks the
server for three addresses that are its own unrendered placeholders (`{{ videoUrl }}`,
`{{ overviewUrl }}`, `{{ f.src }}`), which give "not found" in the console; and the *Get started*
commands run together on one line. Both are for the design source.

## The wording rule

The owner's rule (1 November 2026): the site says OspreyFlow is **designed to meet the GDS Service
Standard**. It never says "GDS-compliant", "compliant with", "certified", "accredited" or "assessed",
because only a service assessment panel decides whether a service meets the Standard. Every page that
names the Standard also lists the three independent checks as **planned**: an independent accessibility
audit, a penetration test and a DPIA. The public sector page claims only what the step 9b re-audit
evidences (`process/gds/`). `OspreyFlow_Build/tests/test_website_wording.py` holds every page to this,
reading the home page's decoded template, and runs in `make test`.

## Checklist before going live

- [ ] `repoUrl` points to `https://github.com/Solirius/ospreyflow` (step 13), and the export carries the
      two navigation links and the `#public-sector` section.
- [ ] `test_website_wording.py` passes on the files about to be published.
- [ ] The independent accessibility audit, penetration test and DPIA are still listed as planned. When
      one is done, change the pages to say so, and update the test.
- [ ] The Service Standard points on `public-sector.html` still match the latest re-audit in
      `process/gds/gds_compliance_report.md`.
- [ ] Every page opens at the new address, with no request to another site, no horizontal scroll at
      phone width, and the light and dark themes both readable.
- [ ] The screenshots are still the current product. They come from the synthetic Prison Intelligence
      and Operation Ledger demonstrations (`OspreyFlow_presentations/`, captured 2 November 2026); no
      image from any other case is used.
- [ ] The Solirius Reply logo and the team photo on the home page are cleared for use on this site.
- [ ] No GOV.UK crown, GDS Transport typeface or GOV.UK logo appears on the site's own pages; they
      appear only inside OspreyFlow's own screenshots of its GOV.UK theme.

## Other hosting

GitHub Pages is the way the site is published (ADR-114 Amendment 28). To show it in Google Sites,
publish on Pages first, then in Google Sites use **Insert → Embed → By URL** with the Pages address
and **Whole page**. Pasting the file into an embed-code box is not reliable: `index.html` is about
2.5 MB.

## Adding the introduction video later

The home page shows a placeholder until a video address is set. Upload the video to YouTube or Vimeo,
set the design source's `videoUrl` setting to its **embed** URL (for example
`https://www.youtube.com/embed/VIDEO_ID`), export the site again and replace `index.html`.
