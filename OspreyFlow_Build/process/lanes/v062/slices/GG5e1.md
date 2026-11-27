# Slice GG5e1 · GG5 · Site plans on the GOV.UK pages: a case's site plan uploaded, calibrated by four control points and given a grid, then viewed over the map; scripts off whole (a draft)

**Status: a draft, not ruled.** Written in an away drafting session (D246), 26 to 27 November 2026, on the branch
`drafts/2026-11-27`, read from `origin/main` at `7f4f9554a`. No row in `slices.tsv`; no builder starts from this paper.
**Size M to L** (the upload, the calibration and the view; if the count passes 15 cases, the builder splits the view
off as its first round). Release scope A-full (D273). **It needs GG5b built, and GG5d's keyboard route for placing a
point on the map** (or builds it, if GG5d has not merged). It draws nothing with Sigma. Rotation and pitch are GG5e2.

**Where it comes from.** `FUNCTIONS.yaml` row `map-and-site-plans` ("… site calibration", scenarios A1 to A3:
`apps/pages/FUNCTIONS.yaml:388-394`). `spec/02_GLASS_FRONTEND.md` §3.5, "Site geospatial is not an afterthought …
Support an uploaded image with two or more control points and a drawn grid, and let a `Location` entity be a grid
cell". Scenario A1 (`spec/08_ACCEPTANCE_SCENARIOS.md:382`): "Upload the site image, place four control points, draw a
10×10 grid … Grid cells become `Location` entities; incidents geocode into cells", over the wire since round 13cf
(:66).

## What exists today (read on `origin/main` at `7f4f9554a`; re-read, lines move)

- **The routes** (`services/api/app.py`):
  - `POST .../sites` (`create_site`, :10197-10237), 201, `EDIT_GRAPH` and the case's Editor gate
    (`InvestigationEditorDep`, :2968); **multipart**: a `label` field and an `image` file. The file is read whole
    (:10216), checked by `image_dimensions` (PNG and JPEG only, `packages/geo/image_dimensions.py:37-56`; anything else
    is a 422 by the handler at `app.py:4199`). Audited `create_site`.
  - `GET .../sites/{site_id}` (:10240-10252) and `GET .../sites/{site_id}/image` (:10255-10264), `INVESTIGATE` and
    the site's Viewer gate (`SiteViewerDep`, :3078); the image is sent as `image/png` or `image/jpeg` by its own bytes.
  - `PATCH .../sites/{site_id}/control-points` (:10267-10287), `EDIT_GRAPH`, `SiteEditorDep` (:3079): exactly four
    `ControlPointRecord`s (`services/api/sites.py:46-60`: `px`, `py` image pixels from the top left; `lon`, `lat`), in
    top-left, top-right, bottom-right, bottom-left order.
  - `POST .../sites/{site_id}/grid` (:10290 onward), `EDIT_GRAPH`, `SiteEditorDep`: `rows` and `cols`, default 10; it
    loads the cells as `Location` entities with their polygons and geocodes the case's incidents into them; redrawing
    does not duplicate.
  - **No route lists a case's sites**, and none deletes one: `SiteStore` has `create`, `get`, `get_authorized`,
    `set_control_points` and `set_grid` only (`sites.py:102-202`). A site of another unit is the same 404 as none
    (`SiteNotFoundError`, :84-88).
  - **A site carries no handling**: `Site` (:63-81) has a label, the image's key and size, the points and the grid,
    and no marking.
- **The page service and this upload.** The forwarder **refuses** a multipart post to `.../sites` ("not carried: the
  owner's ruling is needed", `apps/pages/server/forward.ts:48-52`, the 415 at :437). A page route may read a browser's
  upload itself (`server/upload.ts:1-10`, slice IS5a: the anti-forgery token first, a hook before any byte of the file,
  held in memory up to a cap); **the server half's Conduit client sends JSON only** (`server/conduit.ts:59-62`).
- **The React wizard.** `apps/workspace/src/site/SiteCalibrationWizard.tsx` (450 lines): upload, four paired clicks
  (image, then map), a grid size, confirm; "no drag-to-reposition a point, no undo" (:15-18). Points on the map by
  `onNextMapClick` (`site/siteLayer.ts:138-150`, a mouse listener): **no keyboard route** (no registry id). The image is
  drawn by MapLibre's `image` source at the four points (`siteLayer.ts:40-56`), from a `blob:` URL made of an
  authorised fetch (`packages/glass-shared/src/site/api.ts:152`). `formsASimpleQuadrilateral` and `computeGridCells`
  are already in `glass-shared` (`site/bilinear.ts:81`, :104).
- **GG5a did not take an `image` source** under the policy (`away/GG5a_AWAY_REPORT.md`, the `img-src` row: "An `image`
  source (the site plans' likely path) is not in this style either. GG5b's own run must take both").

## Acceptance (red before, green after)

Scenario **MP**'s site-plan rows, written first, A1's steps on the GOV.UK tree: upload the synthetic site image, place
four points, draw a 10×10 grid, and see the plan over the map with its grid. `apps/pages/test/govuk/site-plans.test.ts`
and the site page's browser spec (the image drawn at its points, I2 and I3 with an `image` source), red (no page),
green after; GG5b's cases unchanged.

## Questions for the owner (the proposal first)

1. **Carrying the upload (owner, D274: security and widening).** Each option is the owner's for its own reason: (a)
   opens a new path that carries untrusted file bytes to the Conduit, around the reservation in `forward.ts:48-52`
   (security); (b) widens the forwarder's allow-list (widening). `forward.ts` is not a protected file (the line's
   guard, `scripts/slice_line/guard.py:33`, names only the Core build file and the CI workflow); the mark is for what
   it carries. (a) **A page route of its own reads the form
   (`upload.ts`), checks the right before any byte of the file (`EDIT_GRAPH` from `GET /v1/me/rights`), caps the file
   at the page service's upload cap, and the server half sends one multipart post to `.../sites`**; `conduit.ts` gains a
   multipart body for this call. The forwarder's refusal stays. (b) The forwarder carries `.../sites` multipart (its
   translation table widened). (c) No upload on the GOV.UK tree; a parity line.
2. **Finding a case's sites (owner: an amendment, decision 11).** No route lists them, so a site is reachable only by
   the address made at its creation. (a) **A Conduit amendment, `GET /v1/investigations/{id}/sites`**, the case's
   sites the reader may see (Viewer; the unit's own), label and whether calibrated, its access case written first
   (`test_a_site_of_another_unit_is_not_listed`), as a diff file. (b) No list: the page links to the site it made, and
   a site is lost to the page once left.
3. **A site's handling (owner, security).** A site plan carries no marking, so its image is read by anyone at the case's
   Viewer level in its unit. (a) **Built as the routes are, said in this draft as a finding**; whether a site gains a
   marking is a Conduit security part for the owner to order. (b) Stop until it does.
4. **The address.** (a) **A page of its own, `/cases/sites?case=…&site=…`, with a new `FUNCTIONS.yaml` row
   `site-plans`** (as GR4a's board got its own row), the map row keeping the map. (b) A part of the map page.
5. **Placing a point on the image, scripts off.** (a) **The image as an `<input type="image">`** in a form: a click
   sends the pixel (`x`, `y`) with no script; beside it, two number fields for the same pixel, which a keyboard reader
   uses (a keyboard press on an image button sends 0, 0, so the page ignores those two values when the fields are
   filled). (b) The number fields only.
6. **Placing a point on the map.** (a) **Scripts on: by pointer or by GG5d's key route (arrow keys and Enter); scripts
   off: a "latitude, longitude" field, or a place chosen by GG5d's place search.** (b) The field only.
7. **The four points in one go.** (a) **One point pair a step, four steps, each kept in the page's form state, then one
   `PATCH` with the four in order**, refused in words before sending if they do not form a simple quadrilateral
   (`formsASimpleQuadrilateral`, the same function the workspace runs, I11). **The Conduit checks no shape**:
   `set_site_control_points` (`app.py:10267-10287`) stores any four points, so a crossed plan sent by hand is stored
   (a Conduit finding, for a later part; the page's check is the only one today). (b) One form with all eight values.
8. **The grid.** `GridRequest` has no bounds (`app.py:10192-10195`: `rows: int = 10`, `cols: int = 10`), so the Conduit
   takes 0, a negative or a very large grid (a Conduit finding: the bound belongs in the route, an amendment, recorded
   for the owner). (a) **Rows and columns, 10 by default, 1 to 50 each, checked by the page, one `POST`**, then the page says "The grid is
   drawn: its cells are places in this case" with the route's answer, and nothing more (no count of incidents
   geocoded, which the route does not send). (b) Your bounds.
9. **Drawing the plan.** (a) **MapLibre's `image` source with the image read through the page's own origin** (the
   forwarder's `GET .../image`, the session's cookie), so no `blob:` is needed; the grid as a line layer from
   `computeGridCells`; colours from the tokens. Scripts off: the image itself (`<img>`, the same address) with the grid
   drawn as server-rendered SVG lines, and a table of the four points. (b) The workspace's `blob:` path, which would
   need `img-src blob:` (owner: the policy).

## The table of cases (each red first; the planted fault at the real call site: rule 15)

| # | Case | Expected | The planted fault that shows it red |
| --- | --- | --- | --- |
| 1 | Upload a synthetic 800×600 PNG with a label | one multipart post to `.../sites` with `label` and `image`; `303` to the site's page | the file sent as a JSON body (today's `conduit.ts`) |
| 2 | A reader without `EDIT_GRAPH` posts a file | refused before any byte of the file is read; nothing sent | the hook asked after the file is read |
| 3 | A GIF, an SVG, or a file over the cap | the 422 said "Only a PNG or JPEG picture can be a site plan"; the cap said in words | the 422's detail passed through; the cap's bytes held whole |
| 4 | No `_csrf` as the form's first part | refused, nothing read (I17) | the token checked after the file |
| 5 | The four points by `<input type="image">` and map clicks | one `PATCH` with four `ControlPointRecord`s in TL, TR, BR, BL order | the points sent in click order |
| 6 | The same by the number fields and the latitude, longitude field (keyboard, scripts off) | the same `PATCH` | the image button's 0, 0 taken over the typed pixel |
| 7 | Four points that cross | refused in words; **no `PATCH` sent** | the page's own check left out (the `PATCH` is sent, and the Conduit stores the crossed plan: it checks no shape) |
| 8 | Grid 10 × 10 | one `POST .../grid` `{"rows": 10, "cols": 10}`; the sentence | the grid offered before the points are set: the route answers 422 "the site needs 4 control points before a grid can be drawn" (`app.py:10341-10346`), the fixture answers the same, and the page shows it raw |
| 9 | Grid 0 or 51 | refused in words; nothing sent | the bound left to the route (which has none: the 0 or 51 grid is sent) |
| 10 | The plan over the map, scripts on | the image drawn at its four points, the grid's lines over it; `idle` | the `image` source given the four points in the wrong order (a mirrored plan) |
| 11 | The policy with an `image` source (I2, I3) | no violation, Chromium and WebKit; the image read from the page's own origin | the image given as a `blob:` (the workspace's path) |
| 12 | Scripts off | the image, the grid as SVG lines, the table of points | the grid drawn only by the module |
| 13 | A site of another unit, or a site id of another case | the same 404 page as no site | at the page's call site: the site page's render cache keyed by the site id, not the session (another reader's render served); or the route's 404 detail shown |
| 14 | Two readers, Viewer and Editor | the Viewer sees the plan and no form; the Editor the forms | a form offered from the case's level alone, not `EDIT_GRAPH` |
| 15 | No id on the page | none in text (ids only in a form's hidden field or a link's query) | the site's id printed |
| 16 | Keyboard | upload, each point, the grid: each reachable and working (rule 13), one case per action, ids in the page's registry | the map step that only a click can take |

## Waits on

GG5b built; GG5d's key route for placing a point on the map (or built here); the owner on questions 1 (the upload), 2
(the list route, an amendment) and 3 (a site's handling).

## Files touched

`spec/08` (MP's site rows; A1 on the GOV.UK tree); `spec/02` §3.5 (the page service's site plans); for question 2 (a),
`OspreyFlow_Build/process/lanes/v062/` the amendment's diff file, `services/api/app.py` and `sites.py` (the list route)
with `tests/services/api/test_sites_list_access.py`; `apps/pages/FUNCTIONS.yaml` (the `site-plans` row);
`apps/pages/server/` (the site page, its upload route, `conduit.ts`'s multipart call), `server/views/` (the words),
`server/pageList.ts`; `packages/glass-shared/src/keyboard/actionRegistry.ts` (the page service's map and site registry, case 16's ids); `tree-govuk/` (the page and its route); `apps/pages/modules/map/` (the image and grid layers);
the tests above, `test/govuk/keyboard/sites.spec.ts`, `test/govuk/scripts-off/sites.spec.ts`;
`OspreyFlow_Build/tests/harness/test_pages_setting.py`'s route list.

## Checks (frozen when cut)

GG5b's list, with the forwarder's and the upload reader's tests (`test/server/forward.test.ts`), the parity and
functions checks, and, for question 2 (a), the Conduit's access tests for sites.

## Out of scope

Rotation and pitch (GG5e2); the heat and hotspot cells over a plan (GG5c reads them); deleting or re-calibrating a site
(no route); a site's marking (question 3); the workspace's missing keyboard route for its wizard.
