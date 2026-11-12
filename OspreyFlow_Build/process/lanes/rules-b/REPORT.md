# rules-b lane · report · guides, the guides from Home by the places a person may open (12 November 2026)

(T3b's report is in git history, at 2102d21 and before.) Branch `lane/rules-b-guides`, rebased on main a536c34.
Gated head: **09dda7a**. ADR-145 Amendment 10 is written; the orchestrator flips its reservation at merge.

## Reconciliation at the start
There was no HANDOFF.md and no wip commit, and the step was untouched. No route, link, test or amendment existed;
`lane/rules-b-guides` did not exist. T3b (2102d21) was already in main.

## Exit criteria
| Criterion (BRIEF.md) | Met | Proved by |
| --- | --- | --- |
| User guide under the Glass, developer under the Studio, administration under Admin; none under R&M; no architecture guide | yes | `HomePage.test.tsx` *links each guide under its own place's card*; `test_guides.py` *the glass links each guide under the place the conduit serves it for* |
| No card, no guide | yes | `HomePage.test.tsx`'s six rights sets and the rights-unread case (red 7 ways with links outside the cards); `start.spec.ts` *only the guides of the cards a person's rights open are linked* |
| `GET /v1/guides/{…}` serves the deployment's PDF only to whom the place opens; 403 in words otherwise; the place's own check | yes | `test_guides.py` matrix (every role, preset, legacy role, single right, nobody; 64 red with the check removed); live `test_route_rights.py` *…signed in for real*, including a person with no roles claim (PASSED, `gates/02f3752.live-rights.txt`) |
| `test_route_rights.py` rows | yes | `read_guide_route: None` (a place, not a right; its check is `require_guide_place`) |
| Byte for byte the file in the image | yes | `test_guides.py` byte test; the live case against the checkout's file; `guides/image_check.sh`, green at 09dda7a and red with a stale PDF planted (`gates/09dda7a.image.txt`) |
| Image carries `docs/pdf/` | yes, ratified | Dockerfile: the folder made 755, then the three PDFs and the manifest `--chmod=0444`; `test_guides.py` holds the line (red removed, with the architecture guide, without `--chmod`, without the folder made first) |
| Glass: a link under each card's words, new tab, token never in a URL | yes | `guides.test.ts` (11 cases, red 5 ways); `HomePage.test.tsx` (link, handled click, words on failure, the catch) |
| Keyboard (rule 13) | yes | `start.spec.ts`: `read-a-place-s-guide-from-home-by-keyboard`, `read-why-a-guide-was-refused-on-home-by-keyboard`; red 3 ways (`guides/keyboard-plants.txt`) |
| Axe in dark, light and GOV.UK; tokens only; British English | yes | `every-harness` start-harness's default and new `guide=refused` states, 18 passed with reflow (`gates/02f3752.browser.txt`) |
| ADR-145 Amendment 10, each sentence with its test | yes | `spec/06_DECISIONS.md` |
| Docs lines | as a patch | `docs-guides.patch` |

## Gates (raw, under `gates/`)
- `make test` at 09dda7a: 12,847 passed, 2 failed in pytest and 1 in test-js; live-collect clean (`09dda7a.test.txt`). The same at 02f3752.
- `make -k ci` at 09dda7a: red on `route-coverage-check` alone, with the trivy scans green (`09dda7a.ci.txt`). The same at 02f3752.
- Failures, each explained:
  - `route-coverage-check` and `test_route_coverage_check.py`: expected. `spec03-guides.patch` holds the row; green with it applied.
  - `test_webapp_preflight.py::test_gpu_is_skipped…`: the GPU server's own; other lanes' gates fail it too.
  - `MatrixView.budget` (3,995 ms against 2,500): load, recorded in MORNING.md. It passed alone on the Mac. Untouched here.
- Live, leased on stack b, at 02f3752 (`02f3752.live.txt`): 410 passed and 11 failed.
  - The 11 are in `test_apply_env.py` and `test_phase8_exit_criterion_end_to_end.py`, the harness's apply on the server. They fail the same way in rules', case's and studio's live gates.
  - `test_route_rights.py` and `test_guides.py`, verbose: 86 passed at 02f3752 and again at 09dda7a (`09dda7a.live-rights.txt`).
  - The broad live run was not repeated at 09dda7a. Only the Dockerfile, a static test and the check script changed, and no live file reaches them.
- The image check found a real defect at 02f3752 (`02f3752.image-red.txt`): `--chmod` gave the folders 0444, so the Conduit's user could not enter them and the route would have answered 503. Fixed in 09dda7a, which is why the gates were run again.
- Browser on the Mac, slot 9, at 02f3752: keyboard and hit targets 26 passed, axe and reflow 18, unit 185. The code those runs reach is unchanged since.

## Decisions taken
- **The place check is a dependency, not a static place or right.** `require_guide_place` follows the guide's name; `test_place_routes.py` reads static checks only. One route, as the orchestrator accepted; `test_guides.py` asks every principal.
- **A name not among the three is 404 `no_such_guide`, before the place check.** Guide names are public, so nothing is learnt. A refused reader still gets 403 before any file is touched, so cannot tell whether the deployment carries the PDF.
- **A missing PDF is 503 `guide_not_carried`, in words.** It is never an empty or another document.
- **`OSPREY_GUIDES_DIR` overrides the folder for a test.** The default is `/app/docs/pdf` in the image and the checkout's folder in development.
- **A real `<a href>` to the route, its click and middle click handled.** It is announced as a link; the token goes in a header.
- **Where the browser shows no PDFs (`navigator.pdfViewerEnabled` false), the PDF is saved as `ospreyflow-<guide>-guide.pdf` and no tab is opened.** A tab sent to a blob would download it under a random name. Headless Chromium takes this path, so the keyboard case checks the saved file's name and bytes; `guides.test.ts` holds the tab's path.
- **A shown guide's blob is kept while its tab is open** (checked every 5 s). A saved one is kept for 60 s.
- **The folder is made before the `--chmod=0444` copy.** This is the image check's finding.

## Out of the lane's map
- Committed, ratified by the orchestrator: `services/api/Dockerfile`; `shell/startScreen.tsx` (rules'); `home/**` and `keyboard/start*.{ts,tsx}` (rules', named by the brief).
- Committed: the tests `test_route_rights.py`, `test_no_corpus_counts_on_the_wire.py`, `test_reports_viewer_journey.py`.
- As patches (`PATCHES.md`):
  - `registry-guides.patch`: goes in at merge. `actionRegistry.ts` is not committed on the branch.
  - `every-harness-guides.patch`: the refused state.
  - `spec03-guides.patch`: route-coverage needs it.
  - `spec02-guides.patch`.
  - `docs-guides.patch`: for docs. The PDFs are re-rendered by docs.

## Requests to the orchestrator
- Apply the five patches at merge.
- Flip ADR-145 Am 10 to written.

## Questions for the owner
None.

## Still running
Nothing. Stack b is down and released; no containers, check images or remote processes are left.
