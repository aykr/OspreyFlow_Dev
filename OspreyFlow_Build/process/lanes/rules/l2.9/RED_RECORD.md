# L2.9 red record (rules lane)

Each case was shown red by a plant at the real call site, then the plant removed (rule 15). Offline
runs, every port closed; no stack.

## 1. `/alerts/<id>` (`tests/services/api/test_alert_address.py`)

**Plant A — the route's case check skipped** (`app.py::open_alert_at_address`, the
`investigations.get_authorized(...)` call replaced by `pass`). The alert of another case, and the
alert of a case the reader is no member of, were answered (200, with their words); the readable
case's own test failed on the level check no longer made:

```
    FAILED ../OspreyFlow_Build/tests/services/api/test_alert_address.py::test_a_readable_alert_is_answered_with_its_case_and_explanation
    FAILED ../OspreyFlow_Build/tests/services/api/test_alert_address.py::test_an_alert_the_reader_may_not_see_is_answered_as_a_missing_one[a link it cites is hidden-alerts0-hidden0-levels0]
    FAILED ../OspreyFlow_Build/tests/services/api/test_alert_address.py::test_an_alert_the_reader_may_not_see_is_answered_as_a_missing_one[a transaction it cites is hidden-alerts1-hidden1-levels1]
    FAILED ../OspreyFlow_Build/tests/services/api/test_alert_address.py::test_an_alert_the_reader_may_not_see_is_answered_as_a_missing_one[the reader is no member of its case-alerts2-hidden2-levels2]
    FAILED ../OspreyFlow_Build/tests/services/api/test_alert_address.py::test_an_alert_the_reader_may_not_see_is_answered_as_a_missing_one[its case is another's-alerts3-hidden3-levels3]
```

**Plant B — the evidence check skipped** (`alert_queue._visible_row` and `explain_with_evidence`:
the whole-evidence test and the cited links' and transactions' counts removed). The alerts over a
hidden link and over a hidden transaction were answered:

```
    FAILED ../OspreyFlow_Build/tests/services/api/test_alert_address.py::test_an_alert_the_reader_may_not_see_is_answered_as_a_missing_one[a link it cites is hidden-alerts0-hidden0-levels0]
    FAILED ../OspreyFlow_Build/tests/services/api/test_alert_address.py::test_an_alert_the_reader_may_not_see_is_answered_as_a_missing_one[a transaction it cites is hidden-alerts1-hidden1-levels1]
```

## 2. Rules and Monitoring's gate (`tests/services/api/test_place_routes.py`)

**Plant C — the gate taken off one real route** (`app.py`, `deploy_typology_rule`'s decorator
without `Depends(require_rules_place)`, its own `deploy_rules` left). The gate test names it, the
record of places by role goes stale, and the route answers the Data Engineer and `deploy_rules`
granted alone, for whom R&M is hidden:

```
    FAILED ../OspreyFlow_Build/tests/services/api/test_place_routes.py::test_the_record_of_places_by_role_is_the_routes
    FAILED ../OspreyFlow_Build/tests/services/api/test_place_routes.py::test_every_route_of_a_hidden_place_refuses_the_role[data_engineer]
    FAILED ../OspreyFlow_Build/tests/services/api/test_place_routes.py::test_every_route_of_a_hidden_place_refuses_the_role[right:deploy_rules]
    FAILED ../OspreyFlow_Build/tests/services/api/test_place_routes.py::test_every_route_of_rules_and_monitoring_carries_its_gate_but_the_shared_reads
```

**Plant D — the gate open to everyone** (`rules_place.opens_rules_place` returning `True`). Every
gated route answers past the gate the three roles R&M is not offered to, and the address answers
the Data Engineer:

```
    FAILED ../OspreyFlow_Build/tests/services/api/test_place_routes.py::test_every_route_of_a_hidden_place_refuses_the_role[data_engineer]
    FAILED ../OspreyFlow_Build/tests/services/api/test_place_routes.py::test_rules_and_monitoring_refuses_a_role_it_is_not_offered_to_at_its_gate[data_engineer]
    FAILED ../OspreyFlow_Build/tests/services/api/test_place_routes.py::test_rules_and_monitoring_refuses_a_role_it_is_not_offered_to_at_its_gate[osprey-admin]
    FAILED ../OspreyFlow_Build/tests/services/api/test_place_routes.py::test_rules_and_monitoring_refuses_a_role_it_is_not_offered_to_at_its_gate[reports_viewer]
    FAILED ../OspreyFlow_Build/tests/services/api/test_alert_address.py::test_a_reader_rules_and_monitoring_is_not_offered_to_is_refused_at_its_gate
```

## 3. The workspace: keyboard (rule 13) and unit cases

Each plant is at the real component (not the harness), run with the registry ids of
`registry-L2.9.patch` applied, then restored. The first plant run against the tabs selected no
test (a title mismatch) and was re-run.

```
### address: a queue row no longer gives its alert an address
  plant: src/alerts/AlertQueue.tsx: 'props.onOpenAlert?.(alertId);' -> ''
    ✘  1 keyboard/rules-place.spec.ts:31:1 › an alert opened from the queue is given its address, and Back leaves it, by keyboard (5.3s)
    Error: expect(page).toHaveURL(expected) failed
    14 × locator resolved to <html lang="en" data-theme="dark" data-brand="ospreyflow">…</html>
    1 failed
### back to the queue: its handler dropped
  plant: src/alerts/RulesPlace.tsx: 'onClick={() => props.onOpenAlert?.(null)}' -> 'onClick={() => undefined}'
    ✘  1 keyboard/rules-place.spec.ts:57:1 › an address the reader may not see says so as for a missing alert, and Back to the queue leaves it, by keyboard (5.3s)
    Error: expect(page).toHaveURL(expected) failed
    14 × locator resolved to <html lang="en" data-theme="dark" data-brand="ospreyflow">…</html>
    1 failed
### home row: opens the case, not the alert
  plant: src/home/HomePage.tsx: 'a.alertId && onOpenAlert' -> 'false && onOpenAlert'
    ✘  1 keyboard/shell.spec.ts:291:1 › an alert on Home is reached by Tab and opened at its address by keyboard (5.2s)
    1 failed
### home key R: no card for the place
  plant: src/home/HomePage.tsx: 'rules: { who: "For analysts and rule authors",' -> 'zrules: { who: "For analysts and rule authors",'
    ✘  1 keyboard/shell.spec.ts:303:1 › Rules and Monitoring's card opens by its key, and a case is chosen for it by keyboard (5.2s)
    Error: expect(locator).toBeVisible() failed
    1 failed
### switcher count: dropped
  plant: src/shell/PlaceSwitcher.tsx: '{counts[place] ? (' -> '{false ? ('
    ✘  1 keyboard/shell.spec.ts:215:1 › Rules and Monitoring carries the count, and the Glass is returned to its last view by keyboard (5.3s)
    Error: expect(locator).toBeVisible() failed
    1 failed
### inbox Open the alert: handler dropped
  plant: src/watches/AlertInbox.tsx: '<Button onClick={() => onOpen(alert.id)} disabled={unavailable}>' -> '<Button onClick={() => undefined} disabled={unavailable}>'
    ✘  1 keyboard/watch-panels.spec.ts:247:1 › an inbox alert is opened at its own address, reachable by keyboard alone (ADR-146 decision 6) (5.2s)
    ✘  2 keyboard/alerts.spec.ts:281:1 › the watches are reached with the rules, and an inbox alert opened at its address, by keyboard (5.2s)
    2 failed
### needs: placesFor reads only the opening rights
  plant: src/shell/places.ts: '&& (place.needs ?? []).every((right) => rights.has(right))' -> ''
    × offers Rules and Monitoring only to triage_alerts or author_rules, with the queue's read 2ms
    × offers each role exactly the places the routes answer it in 2ms
    Test Files  1 failed (1)
    Tests  2 failed | 15 passed (17)
    FAIL  src/shell/places.test.tsx > the places' table > offers Rules and Monitoring only to triage_alerts or author_rules, with the queue's read
    FAIL  src/shell/places.test.tsx > the places' table > offers each role exactly the places the routes answer it in
### tabs: the place's Tabs onChange dropped
  plant: src/alerts/RulesPlace.tsx: 'onChange={(id) => setTab(id as RulesTab)}' -> 'onChange={() => undefined}'
    ✘  2 keyboard/rules-place.spec.ts:18:3 › govuk: each of the place's tabs is reached and opened by keyboard (5.2s)
    Error: expect(locator).toHaveAttribute(expected) failed
    14 × locator resolved to <button role="tab" type="button" class="tabs__tab" aria-selected="false">What raises alerts</button>
    Error: expect(locator).toHaveAttribute(expected) failed
    14 × locator resolved to <button role="tab" type="button" class="tabs__tab" aria-selected="false">What raises alerts</button>
    2 failed
### switch to R&M: the switcher's choice dropped (PlaceSwitcher onClick)
  plant: src/shell/PlaceSwitcher.tsx: 'onClick={() => onChoose(place)}' -> 'onClick={() => place !== "rules" && onChoose(place)}'
    ✘  1 keyboard/shell.spec.ts:183:3 › ospreyflow: the place switcher lists only the places the rights open, and moves between them by keyboard (5.3s)
    ✘  2 keyboard/shell.spec.ts:183:3 › govuk: the place switcher lists only the places the rights open, and moves between them by keyboard (5.2s)
    Error: expect(locator).toBeVisible() failed
    Error: expect(locator).toBeVisible() failed
    2 failed
### router: Back and navigate not followed (no popstate subscription)
  plant: src/shell/router.ts: 'window.addEventListener("popstate", onChange);' -> ''
    ❯ src/shell/router.test.ts (5 tests | 1 failed) 15ms
    × follows navigate, and Back returns to where the person was 9ms
    Test Files  1 failed (1)
    Tests  1 failed | 4 passed (5)
    FAIL  src/shell/router.test.ts > an alert's address > follows navigate, and Back returns to where the person was
### router: the sign-in note not kept
  plant: src/shell/router.ts: 'storage.setItem(ADDRESS_NOTE_KEY, location.pathname);' -> 'void storage;'
    ❯ src/shell/router.test.ts (5 tests | 1 failed) 17ms
    × is kept over the sign-in round trip, once 2ms
    Test Files  1 failed (1)
    Tests  1 failed | 4 passed (5)
    FAIL  src/shell/router.test.ts > an alert's address > is kept over the sign-in round trip, once
### address: a 404 read as a failure, not as missing
  plant: src/alerts/api.ts: 'if (response.status === 404) return null;' -> ''
    × is missing on a 404, whatever the reason the Conduit had 1023ms
    Test Files  1 failed (1)
    Tests  1 failed | 4 passed (5)
    FAIL  src/alerts/address.test.tsx > an alert at its address > is missing on a 404, whatever the reason the Conduit had
    AssertionError: expected { status: 'failed', …(1) } to deeply equal { status: 'missing' }
    +   "status": "failed",
### address: another case's alert opened in place (no reload into its case)
  plant: src/alerts/address.ts: 'go(alertInItsCaseUrl(alertId, caseId));' -> 'void go;'
    ❯ src/alerts/address.test.tsx (5 tests | 1 failed) 174ms
    × opens another case on the alert, keeping the address, as every case switch is opened 3ms
    Test Files  1 failed (1)
    Tests  1 failed | 4 passed (5)
    FAIL  src/alerts/address.test.tsx > an alert at its address > opens another case on the alert, keeping the address, as every case switch is opened
```
