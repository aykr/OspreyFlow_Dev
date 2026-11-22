# The pages' keyboard runner: runs on record (slice IS5a, round 3)

The runner is `npm run test:keyboard --workspace apps/pages` (Playwright, Chromium, the real pages server and a fake Conduit that
refuses what the real one refuses). Its CI job is `ci-wiring.patch`, for the owner to apply: until it is applied, nothing in
`make ci` or `npm test --workspace apps/pages` runs it, so the run below is the record, and it is run by hand before a report.

Rule 15: each case was shown red against a fault planted in the page's own code, then green again.

| Planted fault (restored after) | Red | Green after |
| --- | --- | --- |
| `bundlePath` keeps the folder's own name (a browser's relative paths are not stripped) | SK2, SK3, SO2, SO3 and the replace-alone case | all eight |
| the download route serves nothing (`text` undefined, a 404 page) | SK1, SO1 (the download is `canceled`) | all eight |
| the help panel is a `div`, not a `details` (it does not open) | SK4 | all eight |

A first attempt at the download fault removed `Content-Disposition`; SK1 and SO1 stayed green, because the link's `download`
attribute already names the file. The cases then checked only the suggested file name, which a failed download also has. They
now also require no failure and the file's own text (`savedAs` in the spec); the 404 fault above is the one that shows them red.

Green run, 22 November 2026, on the round's tree: 8 passed (SK1 to SK4 with scripts; SO1 to SO3 and the replace-alone case with
scripts switched off). SO2 is the evidence that a real browser (Chromium) sends a `webkitdirectory` input's files named by their
path below the folder: the fake Conduit received the bundle with both of its files, at their relative paths.
