# GDS remediation plan

The backlog from the step 2b baseline audit, 1 November 2026 (`gds_compliance_report.md`). Each task
has a priority, an acceptance criterion, the test that proves it (to be shown red first, rules 12 and
15) and where it slots in. **P1** is a WCAG A/AA failure, or a security gap an assessor would stop
on. **P2** is needed before a service assessment. **P3** is hardening.

Steps 3 to 7 of `BUILD_ORDER_2026-11.md` are the monitoring features (ADR-133 and ADR-134). A task
"rides with" the first of those steps that changes the same surface. A task that touches no such
surface is marked "own change", to be done before step 9b re-audits.

## Fixed in 2b

| Task | Priority | Test | Commit |
| --- | --- | --- | --- |
| Pipeline node button names contain their visible text (2.5.3) | P1 | `a11y/every-harness.spec.ts`, pipeline-canvas | `ed1531d` |
| Start page reflows at 320px (1.4.10) | P1 | `a11y/reflow.spec.ts` | `a675913` |
| Gated start-page panel text at 4.5:1 (1.4.3) | P1 | `every-harness.spec.ts`, `start-harness.html rights=investigate` | `4d189b8` |
| Sign-in page names its language (3.1.1) | P1 | `keycloak_theme/govuk_sign_in.test.mjs`, "the sign-in page is marked English" | `962b4d0` |
| Folded timeline leaves the Tab order (2.4.3, 4.1.2) | P1 | `keyboard/panel-frames.spec.ts`, "a hidden timeline's controls are out of the Tab order" | `8484b72` |
| The CVE-2026-85061 mitigation has a test | P1 | `keyboard/map-view.spec.ts`, "MapLibre's attribution control is never drawn" | `ef16a2c` |
| Every harness page scanned at WCAG 2.2 A and AA; new pages picked up automatically | P1 | `every-harness.spec.ts` (and its "the scan found the harness pages" guard) | `ed1531d` |

## Epic A: accessibility (point 5, TCoP 2)

| # | Task | Priority | Acceptance criterion | Proving test | Slot |
| --- | --- | --- | --- | --- | --- |
| A1 | **The Matrix view** (`02_GLASS_FRONTEND.md` §6): a table or grid rendering of the working set (entities and their links, sortable, with each row's actions) that a screen reader navigates | P1 | Every node and link on the canvas is reachable as a table row with its name, type and link count; the canvas's actions (expand, select, open details) work from a row | `keyboard/matrix.spec.ts` (rule 13; registry `MATRIX_ACTIONS`, 11 actions), and the axe scans of `keyboard/matrix-harness.html` that `every-harness.spec.ts` picks up (dark, light, GOV.UK; also selected and paged states) | **Done**, `bf6e323` (1 November 2026). Also proven by `src/matrix/MatrixView.test.tsx`, `src/matrix/matrixRows.test.ts`, `src/App.matrix.test.tsx` (selection both ways in the real App), `src/matrix/MatrixView.budget.test.tsx` (50k nodes, 250k links, inside §5's 2.5 s) and `keyboard/hit-targets.spec.ts`; each shown red first. What it is: `02_GLASS_FRONTEND.md` §6 |
| A2 | Announce the focused node on the canvas: a polite live region giving name, type and link count when arrow keys move focus | P1 | Arrowing to a node announces "OKAFOR, Callum, Person, 12 links" | `keyboard.spec.ts` case reading the live region after `ArrowRight` | Rides with step 3 (the alert queue opens nodes on the canvas) |
| A3 | Top bar brand button: name contains its visible text (2.5.3) | P1 | Name begins "Osprey", e.g. "Osprey, go to Home" (**the owner's word on the name**, ADR-132 Am. 4 ruling 5) | Add `top-bar-harness.html` with the button to `every-harness.spec.ts`; update `start.spec.ts`, `App.test.tsx` and `StartPage.test.tsx` | **Done, step 7b (1 November 2026):** "Osprey, go to Home" (the owner's answer); `src/shell/brandButton.test.tsx` checks both bars in both brands, shown red; `start.spec.ts`, `App.test.tsx`, `StartPage.test.tsx` updated (ADR-132 Amendment 4, ruling 5's record) |
| A4 | Map text alternative: a list of the located entities beside the map (name, place, coordinates) | P2 | Every plotted place appears as a list item and selecting one selects the node | `map-view.spec.ts` case | Rides with step 4 (the monitoring board may plot alerts) |
| A5 | Timeline table equivalent: the histogram's counts as a table on request | P2 | "Show as table" gives one row per bucket with its count | `timeline-playback.spec.ts` case | Rides with step 5 (preview and backtest use the timeline) |
| A6 | All 38 harnesses apply `?brand=govuk` (28 do not) | P2 | `every-harness.spec.ts` scans every page under GOV.UK too | The spec's own `appliesBrand` check; add an assertion that every harness applies it | Own change |
| A7 | Bring `a11y.spec.ts` up to the WCAG 2.1 and 2.2 tags | P2 | Same tag list as `every-harness.spec.ts` | The spec itself | Own change (small) |
| A8 | Live-page axe scan as a repeatable script against a synthetic deployment, covering states harnesses miss (F1 to F3 were found only live) | P2 | A `live/` Playwright spec, signed in as the analyst and the admin, synthetic case only | The spec | Step 9b |
| A9 | Independent WCAG 2.2 AA audit, with JAWS, NVDA, VoiceOver, TalkBack, Dragon and magnification | P2 | An audit report on file | — | Step 9b, then commissioned by the owner |
| A10 | The accessibility statement (`public/accessibility-statement.html` is a placeholder) | P2 | Statement in the GDS model format, naming known issues A1 to A5 | `test_doc_site`-style check that the page is not the placeholder | Step 9b (already in its scope) |
| A11 | GOV.UK form conventions in the primitives (error summary, hints, legends as headings; ADR-132 consequence 4) | P2 | The Admin and Studio forms use them under GOV.UK | Primitive unit tests and a GOV.UK axe scan | Rides with step 7 (the Studio "Checks on load" step and maker–checker forms) |
| A12 | 400% zoom and text-spacing (1.4.12) checks on the page-shaped screens | P3 | No loss of content at 1280px and 400%; spacing override does not clip | Extend `reflow.spec.ts` | Own change |

## Epic S: security (point 9, TCoP 6 and 7)

| # | Task | Priority | Acceptance criterion | Proving test | Slot |
| --- | --- | --- | --- | --- | --- |
| S1 | Default-deny egress at the perimeter for the small profiles: AWS server egress limited to what it needs (DNS, HTTPS to the registry and ACME; the model gateway's documented exception only when enabled); Azure Key Vault `network_acls` default `Deny`, allowing the VNet | P1 | `trivy config` reports neither critical; `05_DEPLOYMENT.md`'s "default-deny egress" holds at the perimeter | A `trivy config` gate over `deploy/opentofu` in CI, shown red on today's files | Own change (deployment). Not small: an install has to be re-run against a cloud account to check it |
| S2 | EKS private-only endpoint option; control-plane logging on (EKS, AKS) | P2 | Variables `private_api_only` and logging on by default | `tofu validate` and `trivy config` | With S1 |
| S3 | Customer-managed keys for S3 and Secrets Manager; Key Vault secret expiry; RDS IAM authentication; security-group descriptions; Superset `HEALTHCHECK` | P3 | `trivy config` high and low findings cleared or accepted with a reason in `.trivyignore` | `trivy config` gate | With S1 |
| S4 | An SBOM (CycloneDX) for each release image and the npm and uv locks, attached to the signed release | P2 | The release carries an SBOM, and cosign attests it | `tests/` check that `release_local` writes it | Own change (release) |
| S5 | Development-only `minimatch` ReDoS (15 moderate, through ESLint and license-checker) | P3 | `npm audit` clean, or each accepted in a documented list | `npm audit` | When ESLint and typescript-eslint publish fixed ranges |
| S6 | Revisit ADR-014's accepted risk: `@sigma/layer-maplibre` 4.0.0 exists but still peers on `maplibre-gl ^4.5.0` and needs Sigma v4 | P2 | Trigger re-checked at every map-dependency change | `map-view.spec.ts` (now guards the mitigation) | Rides with any step touching `apps/workspace` map dependencies |
| S7 | Penetration test (CHECK or CREST) and a DPIA (a template, then the client's) | P2 | Reports on file | — | Step 9b onwards, commissioned by the owner |
| S8 | Wire `bandit` (medium and above, with the B608 and B310 triage as a baseline) and `gitleaks` into `make ci` as dev-only tools, through the licence gate | P3 | Each shown red with a planted finding (rule 15) before it is wired | A test per gate that plants a finding and asserts the gate reports it (to be written) | Own change |
| S9 | Run the live rule-3 conformance suites again under CI once the current `main` is pushed (last green 29 October) | P1 | CI green on the step 2b merge | CI | On merge of this branch |

## Epic O: open standards (points 11 and 13, TCoP 4)

| # | Task | Priority | Acceptance criterion | Proving test | Slot |
| --- | --- | --- | --- | --- | --- |
| O1 | **Done, step 7b (1 November 2026), the owner's answer:** "publish it at the deployment's address, versioned with the release". `GET /v1/openapi.json`, through the workspace's proxy with every other `/v1` route, behind sign-in; FastAPI's unauthenticated `/openapi.json`, `/docs` and `/redoc` switched off; `info.version` is `OSPREY_RELEASE_VERSION`, the release tag the deployment was rendered from (the one source Admin → System also reads), never `0.1.0` | P2 | `03_CONDUIT_MIDDLEWARE.md` §3.0a and `05_DEPLOYMENT.md` §2.6.1 state it | `tests/services/api/test_openapi_published.py`: the version rendered from a checkout tagged `v0.4.1` is the document's; refused without sign-in; shown red first (404, and `0.1.0` served unauthenticated at `/openapi.json`) | Built |
| O2 | The `.gov.uk` guard rail: the GOV.UK preset only when `network.public_origin` ends in `.gov.uk` (ADR-132 consequence 5) | P2 | `ospreyflow apply` refuses `brand: govuk` on another domain, with a plain message | Harness unit test, shown red | With the Admin Appearance tab |
| O3 | Service telemetry in an open format (OpenTelemetry or Prometheus) for point 10 and 14 evidence | P3 | Request rate, error rate and latency exposed for the Conduit | A scrape test | After step 9b |

## Epic D: decks and claims (point 13 honesty, the owner's requirement)

| # | Task | Priority | Status |
| --- | --- | --- | --- |
| D1 | The decks no longer claim the Matrix view or "no outbound calls" without qualification; a baseline-results slide is added | P1 | Done in 2b (`build_decks.py`, outside git) |
| D2 | Step 9b: a re-audit results slide, the mapping statuses brought up to date, and the website claiming only what 9b evidences (step 12) | P2 | Step 9b |
