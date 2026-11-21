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
- **A release folder** read from a form is held by `server/staging.ts` in the session store, under a random token the page's
  forms carry in a hidden field: half an hour at most, never past the session, 2 MB, three at once, removed after the import and
  on sign-out. It is never in a page, a URL, a cookie or a log line.
- **An upload page** says `upload: true` in its `PageModule`; its handler reads the form with `server/upload.ts`, which checks the
  anti-forgery token as the form's first part before any file is read.
- **The keyboard runner** is `apps/pages/keyboard/` (`npm run test:keyboard --workspace apps/pages`): Playwright against this
  service started in the test with a fake Conduit, with scripts and without. It resolves `@playwright/test` from the workspace's
  hoisted copy.

