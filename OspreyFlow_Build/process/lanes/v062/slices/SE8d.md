# Slice SE8d · SE8d · The route SE8c added, `POST /v1/session-events` (`record_session_event`), is named in the rights table

- **Build id:** SE8d. **What GitHub found (run `45020903945` on `e890b0d`, 22 November 2026, the `conformance` job):** `OspreyFlow_Build/tests/services/api/test_route_rights.py::test_every_route_names_the_right_the_table_gives_it` fails with "in the app, not the table: ['record_session_event']". The route is SE8c's (`c03d059`, merged 21 November). No slice's own checks and not the Mac's gate ran that test, so it reached main; this slice closes it. **It is an access-control table (rule 4): every route names the right it needs, and a route the table lacks is a route nobody has said who may call.**
- **Dial setting:** balanced. **Rounds limit:** the dial's (8).
- **After:** SE8c (merged).

## The owner's condition (22 November 2026, binding; it comes before any edit)

**Before you write the table entry, find out and put in your report, as the first thing in it: what right the route `record_session_event` (`POST /v1/session-events`) actually enforces, and who can call it** (which dependencies run, in order: `page_service_only`, the bearer scheme, the principal; what each refuses; whether a person's own token, the page service's token, or any token at all is required; what a caller without the right receives). **If it enforces nothing (no dependency refuses an unauthorised caller), STOP: do not write the entry, do not commit anything, and say so in one line at the top of your report: the owner decides before any merge.** A table entry that names a right the route does not enforce is worse than a missing one.

## What

1. **First, show the test red on main** (run it on a clean copy of main; it needs no stack: say so, or say what it needs). Then read `ROUTE_RIGHTS` (about line 29 of the test) and how it names the rights of the other routes that only the page service may call (`page_service_only`, `OspreyFlow_Core/services/api/app.py` about line 20270) and the audit-write routes; **add the one entry for `record_session_event` with the right the route actually enforces (the page service's own token; the person's own token for the recording), not a guess: read the route and its dependency, and say in your report which right you named and why.**
2. **Say whether the table's test is reachable from the Mac's gate.** If it only runs in GitHub's `conformance` job, **do not change the gate**: list it in your report with the reason (which stack it needs), so the conductor takes it to the owner as a gap in the Mac's gate.
3. **Check that no other route is missing from the table:** run the test's own comparison over main's app and report both sets (the one for the app but not the table, the table but not the app). Add nothing but the one entry unless the comparison names another; if it does, stop and say so.
4. **A plant, red then green (rule 15), at the shape the test really sees:** a route registered on the app and left out of the table must make the test fail with that route's name; show it, then remove it.

## Acceptance test

`OspreyFlow_Build/tests/services/api/test_route_rights.py::test_every_route_names_the_right_the_table_gives_it` (existing; red on main now, green after; the slice's row names it).

## Checks (pure where they can be; store ports pinned to 9)

The acceptance test; `ruff check .`; `mypy packages services harness`; `make route-coverage-check`; `make test-file-coverage-check`. **Say what you could not run without a stack.**

## Out of scope

The route itself, `app.py` (a collision point today: this slice touches the test file only), the gate, any key, token or address, and every other route.
