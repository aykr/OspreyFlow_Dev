# GDS baseline audit: evidence against the Service Standard

Build-order step 2b (`process/BUILD_ORDER_2026-11.md`), carried out 1 November 2026 on branch
`gds-baseline-audit`. Step 9b re-audits the finished product, with the monitoring features, and
updates this report.

This report sets out the evidence against each of the 14 points of the GOV.UK Service Standard and
says plainly where that evidence is thin or missing. It does not say OspreyFlow is "compliant": only
a service assessment panel decides that, and it assesses a service (a team running a product for
users) rather than a product alone. Automated accessibility tools find only part of what WCAG asks,
so a clean automated result is not a claim of WCAG conformance either.

The starting point was the mapping in the Prison Intelligence decks (`build_decks.py`, slides
`gds_a` to `gds_e`, `gds_ss1`, `gds_ss2`, `gds_tcop1`, `gds_tcop2`). Each status below keeps that
mapping's status unless the repository now shows something different, and says so where it changed.

## 1. Summary

**Readiness, plainly:** the product's own engineering evidence is strong on security, open source,
open standards and operability. Accessibility automation is broad and now covers every harness page.
Two of the deck's claims went further than the repository, and are corrected here and in the decks:

- **The Matrix view did not exist at the baseline. Since built (1 November 2026, build order step 2g; remediation A1 done).** `spec/02_GLASS_FRONTEND.md` §6 requires it ("the
  screen-reader-navigable rendering of the same data"), and the decks presented it as built. It is
  not in `apps/workspace/src`. A screen-reader user on the graph canvas today hears "Selection of 1"
  and the selection count, but not which node has focus. That is the largest accessibility gap
  (remediation A1).
- **"No outbound calls from the deployment"** is no longer true without qualification. Since
  ADR-135 (several model engines) and ADR-136 (egress decided per dataset), an administrator can
  enable a hosted model engine. Material leaves only for a dataset marked sendable and a handling
  code that allows it. Nothing leaves by default.

What an assessment would also ask for, and the repository does not yet hold: an independent WCAG 2.2
AA audit with assistive-technology testing, an accessibility statement (the page is a placeholder),
a penetration test, a DPIA, an SBOM, and the service team's own evidence for points 1, 6, 7 and 10.

Fixed in this step (each with a test shown red first; section 6): five accessibility defects and
one untested security mitigation. Nothing else was changed.

## 2. Accessibility (Service Standard point 5; WCAG 2.2 AA)

### 2.1 Automated results

| Scan | Scope | Result |
| --- | --- | --- |
| `apps/workspace/a11y/a11y.spec.ts` (existing) | sign-in, canvas, showcase, both themes; GOV.UK sign-in, shell, showcase | 9 pass |
| `apps/harness/a11y/a11y.spec.ts` (existing) | six install screens, both themes | 12 pass |
| **`apps/workspace/a11y/every-harness.spec.ts` (new)** | every one of the 38 keyboard harness pages, dark and light; GOV.UK where the harness applies the brand (10 pages); the start page as an analyst | 90 pass, after the fixes below |
| **`apps/workspace/a11y/reflow.spec.ts` (new)** | 1.4.10 at 320px: start, sign-in (both brands), GOV.UK shell | 5 pass, after the fix below |
| axe on the live deployment (read-only, as `osprey-demo-analyst`, synthetic HMP case) | sign-in, start page, workspace in Graph, Map, Reports, Alerts, Explore, History, Watches, Ownership | findings below |

The new scan uses WCAG 2.0, 2.1 and 2.2 A and AA tags. The existing specs use `wcag2a`/`wcag2aa`
only, which never runs `target-size` (2.5.8) or `label-content-name-mismatch` (2.5.3).

Findings, critical and serious first. axe reported no critical findings.

| # | Impact | WCAG | Where | Found by | Triage | Outcome |
| --- | --- | --- | --- | --- | --- | --- |
| F1 | serious | 1.4.3 Contrast (AA) | Start page, a gated panel (Studio, Admin) seen by an analyst: text at 4.25:1 | live scan | real: the text explains why the panel is closed, so it is not an inactive control | **fixed** (`4d189b8`) |
| F2 | serious | 3.1.1 Language of Page (A) | Keycloak sign-in page: no `lang` on `<html>` | live scan | real | **fixed** (`962b4d0`); live once the theme is next rendered |
| F3 | serious | 4.1.2 / 2.4.3 | A folded timeline: controls inside an `aria-hidden` box stayed in the Tab order (`aria-hidden-focus`) | live scan (Map, Alerts) | real | **fixed** (`8484b72`) |
| F4 | serious | 2.5.3 Label in Name (A) | Pipeline canvas node buttons: kind and label run together in the visible text | new harness scan | real | **fixed** (`ed1531d`) |
| F5 | serious | 1.4.10 Reflow (AA) | Start page at 320px: 35px of sideways scroll (340px column minimum) | manual probe, then `reflow.spec.ts` | real | **fixed** (`a675913`) |
| F6 | serious | 2.5.3 Label in Name (A) | Top bar brand button: visible "Osprey", name "OspreyFlow, go to Home" | live scan, every workspace view | real | **fixed in step 7b: "Osprey, go to Home"** (the owner's answer; remediation A3) |
| F7 | serious | 1.4.3 | Panel-frames harness, light and GOV.UK | new harness scan | false positive: the harness used a token that does not exist (`--surface-base`) | harness fixed (`ed1531d`) |
| F8 | serious | 2.5.8 Target Size | `#after-form` in the link-change harness | new harness scan | false positive: a harness-only focus sentinel | excluded by name in the spec |

### 2.2 Manual and structural review of the hardest surfaces

These are judgements made by reading the code and driving the harnesses. They are not
assistive-technology testing.

| Surface | Keyboard | Screen reader | Focus, contrast, motion | 320px reflow |
| --- | --- | --- | --- | --- |
| **Graph canvas** (`GlassCanvas.tsx`, WebGL) | Strong. 38 action registries; `keyboard.spec.ts` has 73 cases and the full keyboard suite 449, every canvas action proven end to end (rule 13). Ring-walk, `Ctrl+Shift+Arrow`, radial menu as a list, `Space` to select | **Gap.** `role="application"` named "Network canvas"; its description gives the selection count only. Moving between nodes announces nothing about the focused node. The Matrix view the spec requires is not built. Partial alternatives: the Inspector (details of the selected node), "What this case holds" (lists, counts, busiest links), Explore and search results | Brand focus ring on every element (`tokens.css` line 231); nine entity types each paired with a shape; `prefers-reduced-motion` zeroes transitions (`tokens.css` line 255) | Exempt: two-dimensional content (1.4.10) |
| **Map** (`MapView.tsx`, MapLibre) | Map region reachable; the plotted places are the same working set as the graph | **Gap.** A `region "Map"` with no text alternative for the plotted places. A list of located entities would serve | Attribution drawn as plain text (CVE mitigation, now tested) | Exempt (two-dimensional) |
| **Timeline** (`Timeline.tsx`, playback) | Controls named and reachable (Density, Cyclical, Play, speed); a folded timeline now leaves the Tab order (F3) | **Partial.** The controls are announced; the histogram itself has no table equivalent of its counts | As above | Exempt (two-dimensional) |
| Page-shaped screens (start, sign-in, shell) | Skip link first on every page (`shell.spec.ts`) | Headings and landmarks present | 24px targets (`hit-targets.spec.ts`); GOV.UK focus is `#ffdd00` with an ink shadow | Now held to it (`reflow.spec.ts`) |

**Contrast tokens.** `apps/workspace/src/design/tokens.css` is the only source of colour, held by
`make design-check` and `colour-drift-check` (both clean after this step) and
`designContract.test.ts`. axe found no contrast failure from a token itself. F1 came from opacity
applied over a token, which a token check cannot see. That is why the live-page scan matters.

**Not assessed in this step:** testing with assistive technology (JAWS, NVDA, VoiceOver, TalkBack,
Dragon, magnification); the Ingest Studio and Admin console beyond their harnesses; Superset
dashboards (`bi.`, a separate product with its own look); 400% zoom; and the GOV.UK deployment's
live pages (only one Lite deployment runs at a time, ADR-132 Amendment 3; GOV.UK was covered through
the harnesses). 28 of the 38 harnesses do not apply `?brand=govuk`, so under GOV.UK they are scanned
only in the default brand (remediation A6).

## 3. Security and access control (point 9)

### 3.1 Static analysis: bandit 1.9.4

Scope: `services`, `harness`, `packages` and `cli` (77,451 lines, tests excluded). Bandit ran from a
throwaway virtual environment and is not added to the product.

| Severity | Count | Triage |
| --- | --- | --- |
| High | 0 | |
| Medium: B608 SQL built from strings | 98 | **Accepted.** Every value is a bound parameter (`$1`, `:id`). The interpolated parts are module constants (`_COLUMNS`), access predicates the adapter builds itself (`predicate.where`, the rule-3 injection point), schema names through `_identifier`, and graph type and property names. Type names pass `groovy_identifier` (`gremlin_literals.py`); property keys come only from the ontology's indexed names (`serialization.py`), never from a request |
| Medium: B310 `urlopen` | 9 | **Accepted.** Every URL is operator configuration (the OIDC issuer, the release feed, the cloud endpoint), each marked `# noqa: S310` with its reason |
| Medium: B104 bind to all interfaces | 2 | **Accepted.** `harness.webapp` inside its container, reachability restricted at the port publish (`127.0.0.1:` in the compose file); the other is preflight text describing a port mapping |
| Medium: B108 `/tmp` | 3 | **Accepted.** The heartbeat file inside the report-sync container, and Caddy's data directory under a non-root user |
| Low: B105 "password" strings | 22 | **False positive.** Names of environment keys and secret references, not values |
| Low: B311 `random` | 13 | **False positive.** Seeded synthetic fixture generation (`demo_fixtures`), never security |
| Low: B101, B404, B603, B607, B405 | 152 | **Accepted.** Asserts, and `subprocess` without a shell over fixed argument lists. B405 is a type import only; parsing uses `defusedxml` (`tier4_registration.py`) |

### 3.2 Dependencies: `npm audit --omit=dev`

| Package | Severity | Triage |
| --- | --- | --- |
| `maplibre-gl` 4.7.1, through `@sigma/layer-maplibre` 3.0.0 (GHSA-jrc7-96c5-q579, CVE-2026-85061, XSS in `DOM.sanitize()`) | critical | **Accepted risk, already recorded:** ADR-014's amendment and `.trivyignore`. The fix is only in `maplibre-gl` 6.4.1 or later. `@sigma/layer-maplibre` 4.0.0 is now published, but its peer range is still `maplibre-gl ^4.5.0` and it needs Sigma v4, so the ADR's revisit trigger is still unmet. The mitigation (MapLibre's attribution control off, attribution drawn as text) **had no test**; it has one now (`map-view.spec.ts`, `ef16a2c`). No `setHTML` is used anywhere in `src` |
| Development only: 15 moderate (a `minimatch` ReDoS through ESLint, typescript-eslint and license-checker) | moderate | **Accepted for now:** these tools never ship. npm's suggested "fix" is a breaking downgrade (`eslint@4`). Remediation S5 |

The Python side is covered by `make trivy` (`trivy fs`, HIGH and CRITICAL) and per-image scans in CI.
The last red `make ci` (ADR-132 ruling 7) was resolved on 31 October.

### 3.3 Secrets: gitleaks 8.21.2 (Docker, redacted) over 1,201 commits

17 findings. None is a live secret. No value is reproduced here.

| Where | Kind | Triage |
| --- | --- | --- |
| `.github/workflows/ci.yml` lines 97 and 350 | `curl -u` literal | **Accepted.** The ephemeral ArcadeDB root password for CI's throwaway service containers, set in the same file |
| Historical `docs/DEMO_GUIDE.md` and `docs/demo/2026-09-24/RUNBOOK.md` (paths gone) | `curl -u` literal | **Accepted, historical.** The old local-development default. Deployments now mint their own secrets (`harness.apply`, `keep_existing_secrets`) |
| Historical `tests/test_launch*.py` (paths gone) | test password literal | **Accepted, historical.** Test fixtures |
| `harness/{compare,backup,restore}.py`, `tests/harness/test_sustained_load.py` (historical) | `curl -u` | **False positive.** Environment variable references |
| `packages/demo_fixtures/pid_plan.py:2356`, `docs/pdf/manifest.json:5`, `tests/cli/test_cloud_install.py:142` | generic key | **False positive.** A column name, file hashes, a placeholder |

Also checked: `deploy/generated/` is gitignored, `deployment.env` and `~/.ospreyflow/gemini.key` are
mode 0600 (ADR-137), and no `.env`, `.pem` or `.key` file is tracked.

### 3.4 Configuration: `osprey.yaml`, OpenTofu and Helm

`trivy config` 0.57.1 over `deploy/` (the generated folder skipped):

| Finding | Severity | Triage |
| --- | --- | --- |
| `cluster/aws` EKS public endpoint (AVD-AWS-0040) | critical | **Mitigated.** `public_access_cidrs = var.api_cidrs`, whose validation refuses `0.0.0.0/0`. A private-only option is remediation S2 |
| `small/aws` server security group: egress to `0.0.0.0/0` on all protocols | critical | **Real.** `05_DEPLOYMENT.md` says "default-deny egress". Inside the host, the compose `egress` network still confines which containers can reach out, but the perimeter allows everything. Remediation S1 |
| `small/azure` Key Vault without a network ACL (AVD-AZU-0013) | critical | **Real.** RBAC is on and purge protection is on, but the vault is reachable from any network. Remediation S1 |
| S3 and Secrets Manager with AWS-managed rather than customer-managed keys; Key Vault secrets with no expiry or content type; no EKS or AKS control-plane logging; RDS without IAM authentication; missing security-group descriptions; Superset image without a `HEALTHCHECK` | high to low | **Accepted for a pilot, hardening backlog** (S2, S3). Encryption at rest is on throughout |

`osprey.yaml` parsing: secrets never sit in `osprey.yaml` (`05_DEPLOYMENT.md`). A changed
`osprey.yaml` is applied by `ospreyflow apply` with preflight before anything is written, and a
refused run writes nothing (ADR-132 ruling 6, ADR-137;
`test_a_run_its_preflight_refuses_writes_nothing_to_the_deployment`). The demo configuration is held
to tier-1 maps (`test_demo_osprey_config_is_tier_1_only.py`). Brand and service-name values reach
the Glass as data, never markup.

### 3.5 Data protection: the invariants and the tests that prove them

**Access control in the adapter (rule 3).** The principal's clearance, unit, handling codes and case
datasets are injected into the traversal or `WHERE` clause, never filtered afterwards. What proves
it:

- `tests/conformance/graph_port/test_suite.py` (live ArcadeDB, CI's conformance job):
  `test_match_count_never_leaks_a_hidden_node`,
  `test_no_route_passes_through_a_hidden_node_or_link_and_the_fewest_degrees_do_not_move`,
  `test_path_length_in_one_dataset_matches_a_graph_without_the_other_datasets_hop`,
  `test_degree_in_one_dataset_matches_a_graph_without_the_other_datasets_neighbour`,
  `test_a_visible_links_weight_is_the_same_in_two_stores_that_differ_by_a_hidden_link`,
  `test_subgraph_has_no_filtered_count_field`,
  `test_an_unrecognised_clearance_sees_nothing_rather_than_everything`,
  `test_reverted_node_is_invisible_to_every_read_any_clearance`. Path length, degree and count, the
  three inference channels rule 3 names, each have a case. The analytics port's suite does the same
  for histogram buckets.
- Read paths at the Conduit: `test_pid_access_control.py`, `test_dossier_access_control.py`,
  `working_set/test_compute_access_control.py`,
  `working_set/test_no_corpus_count_reveals_a_secret_link.py`,
  `working_set/test_links_among_hides_hidden_ids.py`, `resolve/test_projection_access_control.py`,
  and the explain-cluster and resolution cases.
- `make authorized-query-check` (ADR-041) fails any `*_authorized` store method whose SQL does not
  carry the principal. This run: "108 files under services/api, no offenders".

**Sources withheld from a reader whose case does not read them all (ADR-130 Amendment 2).** Readers
project each element through `withhold_sources` (`working_set/service.py` lines 394, 405, 529, 532;
`link_changes.py` line 185). A writer that reads in order to write back wraps the read in
`sources_in_full()` (`link_changes.py` line 348, `extract/writer.py`, `resolve/trigger.py`,
`pipeline_run.py`, `entity_pictures.py`, `alert_queue.py`). The ArcadeDB adapter refuses to store
withheld provenance (`serialization.py`, `_refuse_withheld`), so a missed scope fails loudly instead
of erasing sources. What proves it:

- `ontology/test_withhold_sources.py` (8 cases, including
  `test_an_element_in_two_datasets_read_by_a_case_of_one_is_withheld`) and
  `ontology/test_sources_in_full.py` (including
  `test_the_scope_does_not_leak_across_concurrent_tasks`, so the scope cannot leak to a reader on
  another task)
- `tests/services/api/test_written_back_reads_in_full.py` and `..._stages.py` (confirm, retract, conflict
  annotation, geocode supersession, true positive)
- `working_set/test_fake_graph_matches_the_adapter_on_sources.py`, which includes
  `test_upsert_edges_refuses_withheld_provenance_as_the_adapter_does`. This is rule 15's point: the
  fake refuses what the real adapter refuses.
- `tests/services/api/test_sources_withheld_routes.py` and
  `tests/adapters/graph_arcadedb/test_sources_withheld_live.py` (live)

Run in this step: 97 passed (the non-live set above, with `test_link_changes.py` and
`test_connections_route.py`). No pinned test stack was up, and none was started, so the live suites
rest on CI. The last green `main` run was 29 October (`84304a6`); later work on `main` has not been
through CI yet.

**Model output stays `inferred`** until a person confirms it (rule 5). **Entities are never merged
in storage** (rule 6). **Egress:** a hosted engine is off by default. Once an administrator enables
it, material is sent only for datasets marked sendable and handling codes that allow it (ADR-135,
ADR-136), and each key carries an administrator's mark for whether a privacy contract stands behind
it.

## 4. Open standards and common platforms (points 11, 12, 13; TCoP 3, 4, 9)

| Component | Open standard or interface | Licence |
| --- | --- | --- |
| Conduit (FastAPI) | HTTP/JSON; **OpenAPI 3.1.0**, generated from the Pydantic models and served at `/openapi.json`, `/docs` and `/redoc` on the API container (200 paths, 199 under `/v1/`). The document is reachable inside the deployment only: the Glass's proxy forwards `/v1/` alone. **`info.version` is FastAPI's default `0.1.0`**, not the release. The API is versioned by path (`/v1/`) | MIT |
| Identity (Keycloak) | OpenID Connect with PKCE (S256, observed on the live sign-in), OAuth 2.0 Token Exchange (RFC 8693, ADR-043); works with any OIDC provider | Apache-2.0 |
| Graph (ArcadeDB) | Apache TinkerPop Gremlin, SQL; four typed ports with conformance suites, so the store can be replaced | Apache-2.0 |
| Analytics (DuckDB, ClickHouse) | SQL; Apache Parquet | MIT; Apache-2.0 |
| Maps (MapLibre GL JS) | Vector tiles (MVT), the MapLibre style specification, PMTiles; OGC WMTS for tier 4 (ADR-016); WGS84 storage; OS data under PSGA or the OGL | BSD-3-Clause |
| Front proxy (Caddy) | HTTP/1.1 and 2, TLS | Apache-2.0 |
| Dashboards (Superset) | SQL; embeds with its own look | Apache-2.0 |
| Model gateway (LiteLLM) | The OpenAI-compatible chat API, as a de facto interface | MIT |
| Infrastructure (OpenTofu, Helm) | HCL, Kubernetes manifests, OCI images; releases signed with Sigstore (cosign) | MPL-2.0; Apache-2.0 |
| Intelligence exchange | STIX where used; GeoJSON | |

Licences are recorded in the register (`spec/00_ARCHITECTURE.md`) and enforced by
`make licence-check`, which has been shown red (rule 15). The product is Apache-2.0.

Gaps: no SBOM is produced (CycloneDX or SPDX; S4); the OpenAPI document is neither published to
integrators nor versioned with the release, and the spec does not say whether it should be (O1,
which needs the owner's decision); no OpenTelemetry or Prometheus metrics yet (the monitoring
decisions, ADR-133 and ADR-134, are about intelligence alerting, not service telemetry).

## 5. The 14 points

Status: **met** means the product's evidence for what it can show is in the repository, named;
**partly** means some is, and the gap is named; **not yet** means it is planned; **service team**
means it is about the people running the service, which the product supports but cannot do for them.

| # | Point | Status | Evidence | Gap |
| --- | --- | --- | --- | --- |
| 1 | Understand users and their needs | service team | `spec/08_ACCEPTANCE_SCENARIOS.md`; the demo scripts | User research with the client's analysts |
| 2 | Solve a whole problem for users | met (product) | Ingest Studio to assessed report in one case; `test_phase8_exit_criterion_end_to_end.py` | The service's wider journey (requesting access, onboarding) is the client's |
| 3 | Provide a joined-up experience | partly | One sign-in (OIDC); GOV.UK preset on the Glass and on `id.` (ADR-132 Amendments 2 and 4) | Superset (`bi.`) keeps its own look; no server-rendered pages without JavaScript (ADR-132 consequence 3) |
| 4 | Make the service simple to use | partly | Copy rules (`02_GLASS_FRONTEND.md` §7); plain sign-in card (ADR-132 Am. 4) | Usability testing; GOV.UK form conventions (error summary, hints, legends) not yet in the primitives |
| 5 | Make sure everyone can use the service | partly (**changed**: was "in the product") | Section 2: axe on every harness page and both brands, reflow gate, 449 keyboard cases, focus and motion tokens; five defects fixed. **Since the audit:** the Matrix view, the graph's screen-reader equivalent, built (remediation A1, `bf6e323`; `keyboard/matrix.spec.ts`) | **The map has no text alternative; moving between nodes on the canvas announces nothing (A2); no independent audit; accessibility statement is a placeholder** |
| 6 | Have a multidisciplinary team | service team | — | The client's team |
| 7 | Use agile ways of working | supported | Phased build with exit criteria; more than 130 decision records | The service's own governance |
| 8 | Iterate and improve frequently | met (product) | `ospreyflow update` (verify and roll back); signed releases; Conventional Commits; CHANGELOG | Release cadence is the service's |
| 9 | Create a secure service which protects users' privacy | partly | Section 3: OIDC with PKCE; access control in the adapter, with conformance tests on every inference channel; sources withheld (ADR-130 Am. 2); per-dataset egress (ADR-136); secrets mode 0600 (ADR-137); bandit has no high findings; gitleaks has no live secret | Penetration test; DPIA; SBOM; small-profile egress and Key Vault network rules (S1); the maplibre accepted risk |
| 10 | Define what success looks like and publish performance data | service team | Performance budget as a CI gate (`02_GLASS_FRONTEND.md` §5) | Service KPIs and their publication; no service telemetry yet |
| 11 | Choose the right tools and technology | met | Section 4; recorded decisions; four typed ports with conformance suites | — |
| 12 | Make new source code open | met | Apache-2.0; `make licence-check` (shown red) | Publication of the repository is the owner's step (BUILD_ORDER 13) |
| 13 | Use and contribute to open standards, common components and patterns | partly | OIDC, OpenAPI 3.1, MVT and PMTiles, WMTS, Parquet, Gremlin; GOV.UK Design System preset (ADR-132) | GOV.UK form patterns; the `.gov.uk` guard rail is still planned; OpenAPI not published or versioned (O1); no contributions back yet |
| 14 | Operate a reliable service | met (product) | `ospreyflow doctor`, `status`, `backup`, `restore`, `apply`, `update`; preflight; three deployment modes | Service monitoring and alerting on the platform itself; on-call is the service's |

Technology Code of Practice: 2 follows point 5 (**partly**); 3, 4 and 9 are met as above; 6 follows
point 9 (**partly**); 7 is **partly** (ADR-136 egress, withheld sources; DPIA template planned); 8,
10 and 11 are unchanged from the deck; 12 is not assessed; 13 is this report (**partly**).

## 6. What this step fixed

Each fix has a test that was run red before the change and green after (rules 12 and 15).

| Commit | Fix | Red, then green |
| --- | --- | --- |
| `ed1531d` | F4: pipeline node buttons; `every-harness.spec.ts` added; F7's harness token corrected | 2 failed (pipeline canvas, dark and light), then 87 passed |
| `ef16a2c` | `map-view.spec.ts` case proving MapLibre's attribution control stays off (the CVE mitigation) | 1 control found with `attributionControl: true`, then 3 passed |
| `a675913` | F5: start page reflow at 320px; `reflow.spec.ts` added | 356px and 355px in a 320px viewport, then 5 passed |
| `4d189b8` | F1: a gated panel's words at full contrast; the analyst state added to the scan | 4.25:1; a first attempt failed the overlaid note (3.03 to 4.48:1); then 6 passed |
| `962b4d0` | F2: the sign-in page's `lang` | 2 failed (both brands), then 20 passed |
| `8484b72` | F3: a folded timeline is inert | focus landed inside the hidden timeline, then 12 passed |

| `899c81c` | The harness control added for F3 made a real product button | `hit-targets.spec.ts` 2 failed (under 24px), then 26 passed |

Final runs on this branch: workspace a11y 104 pass (9 existing, 90 `every-harness`, 5 `reflow`),
harness a11y 12, the full keyboard suite 449 (447 before, the two new cases), the data-protection
set 97, node theme tests 20; `authorized-query-check`, `design-check` and `colour-drift-check`
clean; `tsc` and ESLint clean.

## 7. Method and tools

All the tools were throwaway and nothing was added to the product's dependencies: bandit 1.9.4 in a
scratch virtual environment; gitleaks 8.21.2 and trivy 0.57.1 as Docker images; `npm audit` and
`@axe-core/playwright` already in the repository. Live pages were scanned read-only on the owner's
deployment as `osprey-demo-analyst`, in the synthetic HMP case only. No data was changed, no
container was restarted, and the real-data case was not opened. The full backlog is in
`gds_remediation_plan.md`.
