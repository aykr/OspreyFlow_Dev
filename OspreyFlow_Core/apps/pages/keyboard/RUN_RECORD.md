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

## The dataset map (slice IS3, 22 November 2026)

`studio-dataset-map.spec.ts`: DK1 with scripts and DO1 with scripts switched off, run in the same runner (no new job: the CI job
`pages-keyboard` in `ci-wiring.patch` runs `npm run test:keyboard --workspace apps/pages`, which takes every `*.spec.ts` here). Each
reads the page by Tab alone, in its own order (the skip link, Sign out, the dataset switch, Switch dataset, the help, the five
places), reads the table by its roles (a table named by its caption, four column headers, a row header and three cells for each
pipeline), and presses Enter on Switch dataset to come back to the same map.

Rule 15: shown red against a fault planted in the page's own template, then green again.

| Planted fault (restored after) | Red | Green after |
| --- | --- | --- |
| each pipeline's row header made a tab stop (`tabindex="0"` on the `th`) | DK1 and DO1 (two extra stops, "th: Calls" and "th: Visits") | both |

Green run, 22 November 2026: 2 passed (Chromium).

## The Model step (slice IS2a, 23 November 2026)

`studio-model.spec.ts`: MK1 to MK3 with scripts and MO1 to MO3 with scripts switched off, in the same runner (no new job). MK1 and
MO1 read the page by Tab alone, in its own order (the frame's stops, then the three pack fields, Save draft and Discard draft), and
read the draft's types by their roles (a table named by its caption, five column headers, a row header and four cells for the
type). MK2 and MO2 type a pin and save it with Enter on Save draft, then discard the draft with Enter on Discard draft, each
carried out by the fake Conduit (the draft's own type is still there after the save). MK3 and MO3 save after the draft changed
since the page was read: the page says the copy was out of date and the typed pin is still in the field.

Rule 15: shown red against a fault planted in the page's own template, then green again.

| Planted fault (restored after) | Red | Green after |
| --- | --- | --- |
| each type's row header made a tab stop (`tabindex="0"` on the `th`) | all six (an extra stop in the tab order, and the Tab count to Save draft is off by one in the others) | all six |
| Save draft made a `type="button"` instead of a submit | MK2, MK3, MO2, MO3 (Enter saves nothing) | all six |

A first attempt typed the pin with `Control+A`, which on macOS moves to the start of the line, so "9" was inserted before the
"3": the cases now use `ControlOrMeta+A`.

Green run, 23 November 2026: 6 passed (Chromium).

## The dataset map's order form (slice IS6a, 24 November 2026)

`studio-dataset-map.spec.ts`: DK1 and DO1 (the tab order through the page, now ending in the order form's tick boxes and its button),
DK2 and DO2 (the edit action end to end: Space ticks a link, Tab reaches *Save the run order*, Enter saves it; the fake Conduit holds
version 1 and the page has its "Runs after" column), DK3 and DO3 (a cycle saved from the keyboard is refused in words naming its
pipelines, the tick is still there and nothing is saved), each with scripts and with scripts switched off, in the same runner (no new
job). DK1 and DO1 were red before the page changed (they said there was no "runs after" text anywhere), as the spec required.

Rule 15: shown red against a fault planted in the page's own template, then green again.

| Planted fault (restored after) | Red | Green after |
| --- | --- | --- |
| *Save the run order* made a `type="button"` instead of a submit | DK2, DK3, DO2, DO3 (Enter saves nothing) | all six |
| each tick box's label pointed at another id (`for="x-…"`) | all six (no tick box is found by its name) | all six |
| each tick box made `tabindex="-1"` | all six (the tab order loses its stops) | all six |

Green run, 24 November 2026: 6 passed (Chromium).
