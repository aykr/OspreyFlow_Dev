# GDS remediation plan

The backlog from the step 2b baseline audit, 1 November 2026 (`gds_compliance_report.md`), **brought
up to date by the step 9b re-audit, 2 November 2026** (the report's section 8): closed items are
marked **Closed**, and the re-audit's new items are in "New from the 9b re-audit" and prioritised in
"Order of work after 9b". Each task
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

## Fixed in 9b (2 November 2026)

| Task | Priority | Test | Commit |
| --- | --- | --- | --- |
| R1: 14 form fields' spoken names contain their visible labels (2.5.3, level A): Monitoring's queue filter, close and send-back reasons, give-to; the sentence builder's blanks; the lists' schedule and subscribe form; Admin's dashboard clearance; Ownership's threshold; the schedule editor | P1 | `a11y/every-harness.spec.ts`, "every labelled field's name contains its visible label (2.5.3)", on every page and state (red: 13 failed) | `aabe9c7` |
| The guided install page scanned at WCAG 2.2 A and AA (it had none), with the starter states | P1 | `apps/harness/a11y/install-page.spec.ts` (shown red with a planted fault) | `0da7563` |
| The administration guide says which modes are HTTP and which HTTPS, and that Lite is never opened to a network (the owner's request) | P2 | `test_docs_pdf.py` | `e9bf37d` |
| D2: the re-audit results slide and the mapping slides' statuses in the Prison Intelligence decks | P2 | Read back with python-pptx | `build_decks.py` (outside git) |

## Epic A: accessibility (point 5, TCoP 2)

| # | Task | Priority | Acceptance criterion | Proving test | Slot |
| --- | --- | --- | --- | --- | --- |
| A1 | **Closed.** **The Matrix view** (`02_GLASS_FRONTEND.md` §6): a table or grid rendering of the working set (entities and their links, sortable, with each row's actions) that a screen reader navigates | P1 | Every node and link on the canvas is reachable as a table row with its name, type and link count; the canvas's actions (expand, select, open details) work from a row | `keyboard/matrix.spec.ts` (rule 13; registry `MATRIX_ACTIONS`, 11 actions), and the axe scans of `keyboard/matrix-harness.html` that `every-harness.spec.ts` picks up (dark, light, GOV.UK; also selected and paged states) | **Done**, `bf6e323` (1 November 2026). Also proven by `src/matrix/MatrixView.test.tsx`, `src/matrix/matrixRows.test.ts`, `src/App.matrix.test.tsx` (selection both ways in the real App), `src/matrix/MatrixView.budget.test.tsx` (50k nodes, 250k links, inside §5's 2.5 s) and `keyboard/hit-targets.spec.ts`; each shown red first. What it is: `02_GLASS_FRONTEND.md` §6 |
| A2 | Announce the focused node on the canvas: a polite live region giving name, type and link count when arrow keys move focus | P1 | Arrowing to a node announces "OKAFOR, Callum, Person, 12 links" | `keyboard.spec.ts` case reading the live region after `ArrowRight` | **Closed, step 3 (1 November 2026):** `a11y/canvas-focus.spec.ts` reads the polite status region and scans the page in that state; re-audited 2 November |
| A3 | **Closed.** Top bar brand button: name contains its visible text (2.5.3) | P1 | Name begins "Osprey", e.g. "Osprey, go to Home" (**the owner's word on the name**, ADR-132 Am. 4 ruling 5) | Add `top-bar-harness.html` with the button to `every-harness.spec.ts`; update `start.spec.ts`, `App.test.tsx` and `StartPage.test.tsx` | **Done, step 7b (1 November 2026):** "Osprey, go to Home" (the owner's answer); `src/shell/brandButton.test.tsx` checks both bars in both brands, shown red; `start.spec.ts`, `App.test.tsx`, `StartPage.test.tsx` updated (ADR-132 Amendment 4, ruling 5's record) |
| A4 | Map text alternative: a list of the located entities beside the map (name, place, coordinates) | P2 | Every plotted place appears as a list item and selecting one selects the node | `map-view.spec.ts` case | **Open (P2).** Step 4 did not touch the map; now its own change, first in the order of work |
| A5 | Timeline table equivalent: the histogram's counts as a table on request | P2 | "Show as table" gives one row per bucket with its count | `timeline-playback.spec.ts` case | **Open (P2).** Step 5's preview does not use the timeline; its own change |
| A6 | All harnesses apply `?brand=govuk` (**9b: 14 of 42 do; 28 do not**) | P2 | `every-harness.spec.ts` scans every page under GOV.UK too | The spec's own `appliesBrand` check; add an assertion that every harness applies it | Own change |
| A7 | Bring `a11y.spec.ts` up to the WCAG 2.1 and 2.2 tags | P2 | Same tag list as `every-harness.spec.ts` | The spec itself | **Open.** 9b: `a11y.spec.ts`'s screen scans use `wcag2a`/`wcag2aa`; with A15 |
| A8 | Live-page axe scan as a repeatable script against a synthetic deployment, covering states harnesses miss (F1 to F3 were found only live) | P2 | A `live/` Playwright spec, signed in as the analyst and the admin, synthetic case only | The spec | **Open.** Not done in 9b, which touches no deployment; the Monitoring surfaces are scanned through their harnesses. Step 11 (the rehearsal) is the natural slot |
| A9 | Independent WCAG 2.2 AA audit, with JAWS, NVDA, VoiceOver, TalkBack, Dragon and magnification | P2 | An audit report on file | — | **Open: planned, for the owner to commission.** The draft statement says no audit has been done |
| A10 | The accessibility statement (`public/accessibility-statement.html` is a placeholder) | P2 | Statement in the GDS model format, naming known issues A1 to A5 | `test_doc_site`-style check that the page is not the placeholder | **Draft written in 9b** (`accessibility_statement_draft.md`, marked DRAFT); the product page stays a placeholder until the audit sets the compliance status |
| A11 | GOV.UK form conventions in the primitives (error summary, hints, legends as headings; ADR-132 consequence 4) | P2 | The Admin and Studio forms use them under GOV.UK | Primitive unit tests and a GOV.UK axe scan | **Open.** Step 7 shipped its forms with inline `role="alert"` messages, not the GOV.UK error summary |
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
| S9 | Run the live rule-3 conformance suites again under CI once the current `main` is pushed (last green 29 October) | P1 | CI green on the step 2b merge | CI | **Open.** `main` is still not pushed (no pushes in this run); step 12b runs `make ci` locally once |

## Epic O: open standards (points 11 and 13, TCoP 4)

| # | Task | Priority | Acceptance criterion | Proving test | Slot |
| --- | --- | --- | --- | --- | --- |
| O1 | **Closed.** **Done, step 7b (1 November 2026), the owner's answer:** "publish it at the deployment's address, versioned with the release". `GET /v1/openapi.json`, through the workspace's proxy with every other `/v1` route, behind sign-in; FastAPI's unauthenticated `/openapi.json`, `/docs` and `/redoc` switched off; `info.version` is `OSPREY_RELEASE_VERSION`, the release tag the deployment was rendered from (the one source Admin → System also reads), never `0.1.0` | P2 | `03_CONDUIT_MIDDLEWARE.md` §3.0a and `05_DEPLOYMENT.md` §2.6.1 state it | `tests/services/api/test_openapi_published.py`: the version rendered from a checkout tagged `v0.4.1` is the document's; refused without sign-in; shown red first (404, and `0.1.0` served unauthenticated at `/openapi.json`) | Built |
| O2 | **Closed.** **Done, step 9e (2 November 2026), as the owner ruled it:** "refuse … Lite for a `.gov.uk` address". `osprey.yaml` refuses, in words naming Small or Enterprise, a `local-lite` deployment whose `network.public_origin` is `gov.uk` or ends in `.gov.uk`; `ospreyflow apply` refuses it with nothing changed. The GOV.UK *brand* on a `localhost` address stays allowed for a demonstration on one computer (both of the owner's deployments), and the Appearance tab's own guard rail waits for the tab (ADR-132 consequence 5, noted there) | P2 | `05_DEPLOYMENT.md` §7 states it | `test_deployment_schema.py::test_a_gov_uk_address_refuses_lite_in_words` and `test_apply_changed_settings.py::test_apply_refuses_plain_http_for_small_and_lite_for_gov_uk_in_words`, shown red (`red/s9e_s11_o2_red.txt`) | Built |
| O3 | Service telemetry in an open format (OpenTelemetry or Prometheus) for point 10 and 14 evidence | P3 | Request rate, error rate and latency exposed for the Conduit | A scrape test | After step 9b |

## Epic D: decks and claims (point 13 honesty, the owner's requirement)

| # | Task | Priority | Status |
| --- | --- | --- | --- |
| D1 | **Closed.** The decks no longer claim the Matrix view or "no outbound calls" without qualification; a baseline-results slide is added | P1 | Done in 2b (`build_decks.py`, outside git) |
| D2 | Step 9b: a re-audit results slide, the mapping statuses brought up to date, and the website claiming only what 9b evidences (step 12) | P2 | **Closed for the decks in 9b** (the `gds_audit_9b` slide and the mapping slides); the website is step 12's, held to `gds_pitch_deck_content.md`'s wording |

## New from the 9b re-audit (2 November 2026)

| # | Task | Priority | Acceptance criterion | Proving test | Slot |
| --- | --- | --- | --- | --- | --- |
| S10 | **Closed.** **Done, step 9e (2 November 2026), the owner's ruling:** "Bind Lite to `127.0.0.1`". Every port a `local-lite` deployment publishes is bound to `127.0.0.1` (`harness/site.py` `_bind`): the front proxy (`127.0.0.1:<port>:8080`, or 80 and 443 on an HTTPS `localhost` address), the graph store's door and the Conduit's door under `expose_conduit`; named deployments are Lite and follow. Small keeps 80 and 443 on every interface | P1 | A Lite render publishes nothing on every interface; another machine cannot reach the Glass by sending `Host: ospreyflow.localhost` | `test_front_proxy.py::test_no_lite_published_port_binds_every_interface` (four Lite shapes) and `…small_still_publishes_80_and_443…`, `test_named_render.py::test_a_named_deployment_answers_on_this_computer_only`, `test_preflight.py::test_lites_loopback_ports_from_the_real_render_are_each_checked`, shown red (`red/s9e_s10_render_red.txt`, `red/s9e_s10_named_and_preflight_red.txt`); live through the pinned Caddy: from this machine's LAN address `main`'s mapping answered (Caddy's 502, `red/s9e_s10_live_caddy_all_interfaces_red.txt`), the new one did not connect, while `*.localhost` names still route through `127.0.0.1` (`red/s9e_s10_live_caddy_loopback.txt`) | Built. Both deployments take it at their next rebuild (step 11) |
| S11 | **Closed.** **Done, step 9e (2 November 2026), the owner's ruling:** "refuse `http://` for Small and Enterprise". `osprey.yaml` refuses, in words, a `small` or `cluster` deployment whose `network.public_origin` is not `https://` (the Lite default included); `ospreyflow apply` refuses it with nothing changed. The guided page writes Small's profile to its draft only with its address (the Domain screen); the Set-up console's Profile screen asks for the `https://` address when Small or Enterprise is chosen and saves both in one write | P2 | `ospreyflow apply` refuses, in plain words, a Small `osprey.yaml` whose origin is `http://` | `test_deployment_schema.py::test_small_and_enterprise_refuse_a_plain_http_address_in_words` (both profiles, four addresses), `test_apply_changed_settings.py::test_apply_refuses_plain_http_for_small_and_lite_for_gov_uk_in_words`, `test_webapp_screens.py::test_small_or_enterprise_without_an_https_address_is_refused_in_words`, `InstallApp.test.tsx` and `ProfileScreen.test.tsx`, each shown red (`red/s9e_s11_*`); the starters, the committed `osprey.yaml` and copies of both deployments' own validated (`red/s9e_s11_configs_validate.txt`) | Built |
| A13 | The guided install page's "Map" button opens a screen headed "Geospatial" (2.4.6, 3.2.4) | P3 | The button and the heading use the same word | `install-page.spec.ts` waits for the heading the button names, without the special case it has today | Own change (small) |
| A14 | **Closed.** **Done, step 9e (2 November 2026).** The approval group has no `aria-label`, so its name is its visible legend ("A second person decides this close"); a disabled "Close the alert" (or "Propose the close") has a visible line saying what is missing ("To close it, choose a closing reason and say why, in words."), updating as each is given, as its description | P3 | The group is named by its legend; the disabled button is described by a line saying what is missing | `StageD.test.tsx` (two cases), shown red (`red/s9e_a14_red.txt`) | Built |
| A15 | The Set-up console's scan (`apps/harness/a11y/a11y.spec.ts`) uses `wcag2a`/`wcag2aa` only, and neither harness page has the label-in-name check | P2 | Both harness specs use the WCAG 2.0, 2.1 and 2.2 tags and the label-in-name check (moved to a shared helper) | The specs themselves | Own change, with A7 |

## Order of work after 9b

1. ~~**S10**~~ (closed in step 9e), then **S9** (P1, CI on the current `main`, step 12b).
2. **S1** (P1, perimeter egress and the Key Vault network rule; needs a cloud account to check).
3. **A4** and **A5** (P2: the map's list and the timeline's table, the two known WCAG failures the draft
   statement names).
4. **A9** and **S7** (P2: the independent audit, the penetration test and the DPIA, for the owner to
   commission), then **A10** (publish the statement from the audit).
5. **A6**, **A7**, **A15**, **A8** (P2: the scans' remaining reach).
6. **A11** (P2: GOV.UK form patterns; A14 closed in step 9e), **S4** (SBOM). S11 and O2 closed in step 9e.
7. **A12**, **A13**, **S2**, **S3**, **S5**, **S8**, **O3** (P3).
