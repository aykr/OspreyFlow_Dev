# Slice SE4 · SE4 · Three security faults in the Conduit and the ingest ceiling: the map address check (C016), the unset ceiling (C164), the board list cut at 100 (Superset)

- **Build id:** SE4
- **Dial setting:** balanced
- **Rounds limit:** 4
- **After:** nothing (SE1 is merged)
- **Status of this brief:** written by the conductor on 19 November 2026 under the owner's standing approval, from the
  owner's SE4 request ("Split it if it is too large for one slice"). This slice is the three items below that need no new
  ruling. The other four items are not in this slice: see "Out of scope".

## What

Three faults, each a pure-testable access-control or rule-2 fault. Scouted 19 November; the key points are re-read by the
builder before it writes anything.

1. **C016: the map administrator's address check misses three ranges.** In the Conduit's map administration module
   (OspreyFlow_Core/services/api/map_admin.py, the function `_is_inside`, about lines 411-415) a host is judged "inside" by
   unwrapping an IPv4-mapped IPv6 address and asking Python's loopback, link-local, private, reserved, unspecified and
   multicast predicates. It misses NAT64 (64:ff9b::/96), 6to4 (2002::/16) and shared space (100.64.0.0/10). The same
   question is already answered correctly by `address_is_inside` in OspreyFlow_Core/packages/schemas/sources.py (about lines
   92-102), which the connector reads use and test (OspreyFlow_Build/tests/services/api/test_connector_private_hosts.py).
   The row's fix: `_is_inside` calls `address_is_inside`. The module's callers (`host_inside`, `_checked_address` and the
   per-fetch recheck) keep their behaviour for every address they refuse today.
2. **C164: an unset deployment ceiling is read as the scheme's highest marking even where the profile has a ceiling of its
   own.** OspreyFlow_Core/services/ingest/ceiling.py, `DeploymentCeiling.from_env` and `of` (about lines 87-96) and
   `refuse_writes_above_the_ceiling` (about line 223): nothing set means the scheme's highest. The harness gives the
   cloud-platform profile OFFICIAL-SENSITIVE (OspreyFlow_Core/harness/site.py, `PROFILE_CEILINGS`, ADR-148 decision 10 and
   Amendment 5) and renders both OSPREY_PROFILE and OSPREY_HIGHEST_MARKING into the Conduit's environment, so a rendered
   deployment is right; a Conduit or script that runs without the rendered ceiling (hand-started, or a script run directly)
   is not: a cloud-platform source gets the scheme's highest. Fix: where the ceiling is unset, the profile's own ceiling
   (from OSPREY_PROFILE) applies before the scheme's highest. Mind the import direction: services do not import from the
   harness; if the default has to be shared, say where it moves and why. One sentence in the spec says what "unset" means
   (rule 11; the builder finds the place, ADR-148 decision 10 is the source).
3. **The board list stops at 100 without saying so (rule 2).** OspreyFlow_Core/services/api/superset_embed.py, `dashboards`
   (about lines 144-153), asks Superset for one page of 100 (`page_size:100`) and never reads the count or a next page;
   the route GET /v1/reports/dashboards (OspreyFlow_Core/services/api/app.py, about lines 20015-20031, through
   `_openable_dashboards`) returns whatever came back. A deployment with 101 registered dashboards shows 100 and says
   nothing. Fix, either shape: every board is listed (pages are read to the count Superset reports), or the route answers
   a typed refusal that says the list is too long and what to do. Never a quiet cut. The builder chooses and says which.
   If the answer changes the route's response shape the Glass reads (OspreyFlow_Core/apps/workspace/src/reports/dashboards.ts),
   stop and say; the Glass is not in this slice.

Binding: process/CLAUDE.md rules 2, 3, 4, 11, 12, 15; spec/03_CONDUIT_MIDDLEWARE.md.

## Acceptance test

Three new pure test files (they become the acceptance files), one per item, each red today for the reason it names:

- OspreyFlow_Build/tests/services/api/test_map_admin_inside_addresses.py: through the map administration's own address check
  (`host_inside`, and a route case if the existing tests in test_map_admin_routes.py show how), a shared-space address
  (100.64.3.2), a NAT64 address that embeds a link-local one (64:ff9b::a9fe:a9fe) and a 6to4 address that embeds loopback
  (2002:7f00:1::) are each judged inside, as the connector reads judge them. Controls (rule 15): a public address is not
  inside; the addresses the existing route tests refuse today are still refused. Red today because those three are judged
  outside, not because of a missing import or fixture.
- OspreyFlow_Build/tests/services/api/test_superset_board_list_cut.py: a fake Superset that honours `page_size` and holds 101
  registered dashboards (the existing fake in test_superset_embed.py ignores it and never returns more than three). The route
  answers either all 101, or a typed refusal naming the limit; it must not answer exactly 100 with a success. Control: with
  three dashboards nothing changes. Red today because the route answers 100 with a success.
- OspreyFlow_Build/tests/services/api/test_deployment_ceiling_unset_profile.py: with OSPREY_PROFILE set to cloud-platform and
  the ceiling variable absent, the deployment ceiling is OFFICIAL-SENSITIVE and a write marked SECRET is refused at the
  backstop; with no profile and no ceiling, nothing changes; with the ceiling variable set, it wins over the profile.
  Red today because the ceiling comes out as the scheme's highest.

Plant the violation in the shape the code meets at its real call site (rule 15, second paragraph): the addresses as the
route receives them (a URL host, with brackets for IPv6); the board list through the route, not through the helper; the
ceiling through the environment the Conduit reads.

## Checks

Pure only (ports 9): the three acceptance files and the existing tests of the touched modules: test_map_admin_routes.py,
test_map_admin.py, test_connector_private_hosts.py, test_superset_embed.py, test_deployment_ceiling.py,
test_deployment_ceiling_backstop.py, test_deployment_ceiling_uploads.py, test_deployment_ceiling_verify.py,
test_deployment_ceiling_staged.py, test_deployment_ceiling_drawn_items.py, test_promotion_ceiling.py, all under
OspreyFlow_Build/tests/services/api/, and OspreyFlow_Build/tests/test_seed_internal_ceiling.py. The line adds, beside these,
every mapped pure test that scans a folder the slice changes. No packages/ schema change is expected, so no TypeScript to
regenerate; if one is needed, stop and say.

## Out of scope

Four items from the owner's SE4 request are not here; each needs a decision first, and two need a new build id:

- **`cases_pulled` shown to an administrator who may not see those cases** (OspreyFlow_Core/services/api/report_freshness.py,
  `by_dashboard`, route GET /v1/admin/dashboards). The count comes from the mart's pulls table, which has no marking column:
  the fix changes the mart's schema or the way the count is withheld (the project's withheld-count idiom).
- **C170** (IAM `*` in the backup roles' resource patterns matches `/`): IAM has no one-segment wildcard in object ARNs, so
  the fix may be a key-layout change, which is a spec decision.
- **C246** (the policy check polices only OspreyFlow's own Secret): the allow-list of pods that may read the platform's
  database secret is not yet known.
- **L09** (a disabled engine's way out closed): the render needs an input that carries which engines are disabled in
  Admin, which is a design decision (ADR-135 Amendment 10).
- Do not touch the Glass, the Makefile or the CI workflow.
