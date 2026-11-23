# apps/pages: the server-rendered pages (ADR-152)

A Node service that sends each page complete: with scripts off a page still does its job. Express, Nunjucks, esbuild for the
browser files. No React, anywhere (`scripts/no_react_check.mjs`).

## Where a page's files go

| What | Where |
| --- | --- |
| The route module (`{ id, path, methods, handler }`) and the view model it builds | `server/` (a file of its own per page family) |
| The page's Nunjucks template, extending `layout.njk` | `tree-default/` (the Default tree; `tree-govuk/` is the other tree's) |
| The page's client module, plain TypeScript | `modules/<name>.ts` (one bundle per file) |
| Shared plain logic the module imports | `packages/glass-shared` (`import ... from "@ospreyflow/glass-shared"`) |
| Colours, type, spacing, the faces | `packages/design`: the build reads them; this folder holds no stylesheet and copies none of their rules |
| The page's tests | `test/server/` (vitest, the real app with an in-memory store, as `test/server/foundation.test.ts`) |

## Adding a page

1. Add the page's row to `FUNCTIONS.yaml` (its `id`); a page whose id is no row stops the service starting.
2. Write `server/<family>.ts` exporting a `PageModule` (`server/pages.ts`): `id`, a plain `path`, `methods`, and a handler that calls `res.render("<template>", viewModel)`.
3. Write `tree-default/<template>.njk` with `{% extends "layout.njk" %}` and fill the `title`, `content`, `page_data` and `scripts` blocks; the content must be complete without a script.
4. If it needs a script, write `modules/<name>.ts` and name it in the `scripts` block: a `script` element of type `module` whose `src` is `asset('modules/<name>.ts')`. Never inline code, never a `style` attribute.
5. Add the module to `PAGES` in `server/pageList.ts`; the session check, the anti-forgery check and the headers are applied to it, and a path or id claimed twice is refused at start-up.

## Building and serving the assets

`npm run build --workspace apps/pages` compiles the server, copies the templates and `FUNCTIONS.yaml` into `dist/`, and runs
`apps/pages/scripts/assets.mjs`, which writes one content-hashed stylesheet and each module to `dist/assets/` with a `manifest.json`.
The service serves that folder at `/assets/pages/*` with no session: hashed files only, immutable for a year, GET and HEAD
only, nothing outside the folder. A production start refuses to run without the build.

The Default tree never loads or serves the GOV.UK tree's face (`packages/design/fonts.json` says which entries carry a
condition): the build leaves the GOV.UK brand's rules out of the stylesheet and fails if its face or its files arrive another way.

## The Studio pages (slice IS5a)

`/studio` is the Ingest Studio's frame and `/studio/releases` its Releases screen, on the Default tree. The frame is the layout
partial every Studio page extends (`tree-default/studio/frame.njk`: the dataset switch, the help panel, the readiness strip, the
Needs-you reminder, the five places as links); a page fills its `place` block. Their words and plain helpers are
`server/views/studioWords.ts`, their routes `server/studio.ts`.

- **Calls to the Conduit** are the person's own: `server/conduit.ts` sends the bearer from `accessTokenFor` to the forwarder's
  address and builds every header itself. The Conduit authorises each route; the page's checks of a right are words only.
- **A release folder** read from a form is held by `server/staging.ts` in the pages process's own memory, under a random token
  the page's forms carry in a hidden field: half an hour at most, never past the session, 2 MB, three at once, removed after the
  import and on sign-out. It is not in the session store: the deployment's Valkey saves its keys to disk, so `ValkeySessionStore`
  refuses the folder's key prefix and the folder is never written to disk. The cost is that a pages restart loses a held folder
  (the person is told, and chooses the folder again) and a second pages process would not see the first's. It is never in a page,
  a URL, a cookie or a log line.
- **The Model place** (slice IS2a) is a page: `/studio/model?case=<case>[&dataset=<dataset>]`, so the "1 Model" tab goes to it and no
  longer opens the workspace. The proposed link types are still decided in the workspace (the proposals are not yet a page), so the
  Needs-you reminder keeps its jump (`data-opens-model`, href to the workspace) and the Model page carries a link of its own that does
  the same while proposals wait; the tab never asks (`modules/studio-frame.ts` stays for them and for the places still to come). The page shows the draft's types and the live version's, each as a table (type, class, identifiers, matching rule,
  properties with the indexed flag), says who holds the draft, and opens, saves and discards it by native forms. A save and a discard
  carry the version the person's copy was read at, and the Conduit refuses a stale one; the page says the copy was out of date and
  keeps what was typed. Its route is `server/model.ts`, its words and rows `server/views/modelWords.ts`, its template
  `tree-default/studio/model.njk` (`spec/09_INGEST_STUDIO.md` section 1.3, `spec/08_ACCEPTANCE_SCENARIOS.md` Scenario MS).
- **An upload page** says `upload: true` in its `PageModule`; its handler reads the form with `server/upload.ts`, which checks the
  anti-forgery token as the form's first part before any file is read.
- **The dataset map** (slice IS3) is `/studio/dataset-map?case=<case>[&dataset=<dataset>]`: a read-only table of the pipelines that
  load one dataset (pipeline, status, version, stages), in the same frame, so the frame's dataset switch works from it. Its route is
  `server/datasetMap.ts`, its words and table rows `server/views/datasetMapWords.ts`, its template `tree-default/studio/dataset-map.njk`.
  It reads the case's recipe registry as the person and draws only the rows of the open dataset; every reason it cannot draw the table
  (a right not held, a case or dataset that is not the person's, a dataset that does not exist) is one sentence. It has no column for
  the order pipelines run in: that is slice IS6's, drawn only once the order is stored (`spec/09_INGEST_STUDIO.md` section 1.2,
  `spec/08_ACCEPTANCE_SCENARIOS.md` Scenario DM). Nothing links to it yet: the frame's places are IS5a's, and the Pipelines place is IS4's.
- **The keyboard runner** is `apps/pages/keyboard/` (`npm run test:keyboard --workspace apps/pages`): Playwright against this
  service started in the test with a fake Conduit, with scripts and without. `@playwright/test` is a dev dependency of this
  workspace at the same version as the others'. The root `tsconfig.json` compiles the cases (`npm run typecheck`), and the job that
  runs them in CI is `keyboard/ci-wiring.patch` (the owner's to apply to the workflow file: an agent never writes it).

