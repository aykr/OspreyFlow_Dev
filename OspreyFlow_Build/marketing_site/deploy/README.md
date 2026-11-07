# OspreyFlow website: going live

The site is seven pages and a folder:

| File | What it is |
| --- | --- |
| `index.html` | The home page: one file exported from the design tool, with fonts, screenshots, the Solirius Reply logo and the animation inside it. |
| `intro-video.html` | The animated overview, shown in the home page's video carousel. Keep it next to `index.html`. |
| `public-sector.html` | The UK public sector option: the GOV.UK theme for gov.uk services, designed to meet the GDS Service Standard, for every UK department (build order step 12). Hand-written, no external requests. |
| `monitoring.html` | Monitoring and alerting (build order step 12). Hand-written, no external requests. |
| `drawing-boards.html` | Drawing boards (7 November 2026): ADR-143's design, every section marked **Coming**. Hand-written, no screenshots, no external requests. |
| `three-places.html` | Three places (7 November 2026): ADR-145's design, every section marked **Coming**. Hand-written, no screenshots, no external requests. |
| `assets/` | The screenshots of `public-sector.html` and `monitoring.html` (about 1.2 MB, ten JPEGs, 1440 × 900, no metadata), taken from synthetic demonstration cases only. |
| `.nojekyll` | Tells GitHub Pages to serve the files as they are. |

## How it is published

The site is the product repository's `gh-pages` branch, served at `https://aykr.github.io/OspreyFlow/`
(ADR-114 Amendment 31, which withdrew the move to `Solirius/ospreyflow`).

1. The home page's `repoUrl` is `https://github.com/aykr/OspreyFlow`, edited in the bundle's template the
   same way as step 12's edit (below), since the design source is not in this repository.
2. `marketing_site/publish_pages.sh --push` (which stops unless the product checkout's `origin` is
   `https://github.com/aykr/OspreyFlow.git`) copies `index.html`, `intro-video.html`,
   `public-sector.html`, `monitoring.html`, `assets/`, `.nojekyll` and, if present, `CNAME` onto the
   product repository's `gh-pages` branch. **It does not copy `drawing-boards.html` or `three-places.html`**
   (7 November 2026): published as it stands, the home page's and the other pages' links to them would give
   "not found". The script's file list is the orchestrator's to change; until it is, do not publish.
3. Check the pages at that address (the checklist below).

The hand-written pages link to each other, to `index.html`, to `index.html#start` and to `intro-video.html`
only. They do not link to the repository, so `repoUrl` is the one place the address changes.
`OspreyFlow_Build/tests/test_website_wording.py` holds every page to that one address, and the home page
to the product's statement: "OspreyFlow is an open source intelligence mapping, anti-money-laundering
and fraud detection platform, developed by Solirius Reply and released under the Apache License 2.0."

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
- check `repoUrl` is `https://github.com/aykr/OspreyFlow` (the bundle has it; Amendment 31);
- run `OspreyFlow_Build/tests/test_website_wording.py` on the new export.

Found in the browser check (step 12), and already in the export before it: the home page asks the
server for three addresses that are its own unrendered placeholders (`{{ videoUrl }}`,
`{{ overviewUrl }}`, `{{ f.src }}`), which give "not found" in the console; and the *Get started*
commands run together on one line. Both are for the design source.

## Pages that describe what is not built

`drawing-boards.html` and `three-places.html` describe accepted design (ADR-143 to ADR-145), not a release.
Each section carries a **Coming** mark, the home page's `#coming` section and navigation links say
"(coming)", and neither page has a screenshot. When a part is merged and checked, change its mark and
sentence to the built form and add a capture; never mark a section built before its merge. The home page's
`#coming` section and the two navigation links were added to the template the same way as step 12's edit
(decode, edit, re-encode with the export's own encoding), so the design source needs them too before its
next export.

## The wording rule

The owner's rule (1 November 2026): the site says OspreyFlow is **designed to meet the GDS Service
Standard**. It never says "GDS-compliant", "compliant with", "certified", "accredited" or "assessed",
because only a service assessment panel decides whether a service meets the Standard. Every page that
names the Standard also lists the three independent checks as **planned**: an independent accessibility
audit, a penetration test and a DPIA. The public sector page claims only what the step 9b re-audit
evidences (`process/gds/`). `OspreyFlow_Build/tests/test_website_wording.py` holds every page to this,
reading the home page's decoded template, and runs in `make test`.

## Checklist before going live

- [x] `repoUrl` points to `https://github.com/aykr/OspreyFlow` (3 November 2026, Amendment 31), and the
      export carries the two navigation links and the `#public-sector` section.
- [ ] `test_website_wording.py` passes on the files about to be published.
- [ ] The independent accessibility audit, penetration test and DPIA are still listed as planned. When
      one is done, change the pages to say so, and update the test.
- [ ] The Service Standard points on `public-sector.html` still match the latest re-audit in
      `process/gds/gds_compliance_report.md`.
- [ ] `publish_pages.sh` copies every page in this folder, `drawing-boards.html` and `three-places.html` included.
- [ ] `drawing-boards.html` says "importing a chart from another tool"; name i2 only once the import's ADR is accepted (the owner, 7 November 2026).
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
