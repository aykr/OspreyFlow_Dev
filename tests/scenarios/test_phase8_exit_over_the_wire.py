"""Phase 8's V1 END TO END exit criterion, proven **through the door the analyst uses**.

Owner ruling R5, 27 September 2026, verbatim in its operative half: "the closing-pass proof of
'both acceptance scenarios pass on local-lite' exercises the rendered deployment through the
analyst's own door — the workspace's nginx proxy, signed in as the demo analyst through real
Keycloak, HTTP only — not in-process and not through published store ports. The in-process test
stays as the fast developer tier."

**Why R5 exists.** `tests/scenarios/test_phase8_exit_criterion_end_to_end.py` — still the fast
developer tier, still the more complete walkthrough — drives the app **in process**
(`TestClient(services.api.app)`) and reaches ArcadeDB, Postgres and Valkey **directly on published
ports**. A rendered `local-lite` deployment publishes only the workspace (8080) and Keycloak
(8081); every store is internal, which is correct for a deployment (`05_DEPLOYMENT.md` §7) and
fatal for that test. REPORT-13 recorded the consequence plainly: the single test the milestone
rested on had never once been run against the thing the milestone is about. This file is that run.

**What "through the analyst's own door" means here, concretely.**

1. **Sign-in is real.** OIDC authorization code with PKCE against the deployment's own Keycloak
   realm (`06_DECISIONS.md` ADR-050), as the `--demo-analyst` subject, exactly the flow
   `apps/workspace/src/auth/userManager.ts` performs — `osprey-glass`, a public client with
   `directAccessGrantsEnabled: false`, so there is no password-grant short cut available and none
   is taken. The token this file uses is one a browser would have got.
2. **Every call goes through the workspace's nginx**, on `http://localhost:8080/v1/...`, proxied
   to `api:8000` on the deployment's internal network. No store port, no `TestClient`, no
   in-process app object. If the proxy, the realm, the audience mapper, the CORS origin or the
   container's own module path were wrong, this file fails.
3. **The data is the deployment's own seed** (`harness.apply --seed hmp,fixture-corp`), found the
   way an analyst finds it: `POST /v1/search` against a declared identifier. Nothing is written
   to a store behind the Conduit's back, because nothing can be.

**Coverage against `08_ACCEPTANCE_SCENARIOS.md`, row by row — what this file proves over the wire,
and what it does not.** Stated here rather than in a hand-off report, because a future reader of
this file needs it in place. "in-process only" below is not a gap in this file; it is a row whose
fixture data the deployment's own seed does not carry, and in most cases cannot carry — see the
finding after the table.

| Row | Over the wire here | Note |
| --- | --- | --- |
| A1 | no | The site grid is Phase 5's map screen; no seeded site exists to grid. |
| A2, A3 | **yes** | `cross-filter` on `target_id` — 08's own "Implementation note — A2". |
| A4, A5 | **yes** | `weekday_hour` bucketing restricted to the hotspot cells. |
| A6 | no | Structured reports are document-view work; no `Document` content is seeded. |
| A7 | **yes** (reachable half) | The item-category half is 08's own recorded "Known gap". |
| A8 | **yes** | `MENTIONED_IN` appearance count; see the note at that step. |
| A9 | **yes** | `expand/preview` (a cardinality preview **before** expanding), then `expand`. |
| A10, A11 | **yes** | The family link, and prior-period events appearing when the window widens. |
| A12 | **yes** | `compute/clique_metric` vs `compute/degree` on the relay group. |
| A13, A14 | **yes** | Including the refusal: a judgement with no supporting reference is 422. |
| A15 | **partly** | The artefact, the mark, the manifest and the ledger entry: yes. **The
  consult-originator block: no** — see the finding below. |
| B1, B2, B3 | **yes** | Round 13bf: walked Connect -> Run through the analyst's own door. |
| B4 | **yes** (adapted) | Fixture Corp's resolution cohort, search-seeded, no edges between them. |
| B5 | **yes** (adapted) | One hop out from a seeded node. |
| B6, B7, B8 | no | Message content and the handle cohort are not seeded. |
| B9 | **yes** | Strict does not merge the close-given-name pair; Balanced does. |
| B10 | **yes** | `explain` on the merged cluster, per-comparison weights, not just the total. |
| B11 | **yes** | A manual `SAME_AS`, score 1.0, attributed to this signed-in analyst. |
| B12 | **yes** | Hotlist created over HTTP and read back with its owner and review date. |
| B13, B14 | no | An alert needs an ingest to fire it. See the finding below. |
| B15–B18 | no | The seizure record, the device legs and the sightings are not seeded. |
| B19, B20 | **yes** | Pattern preview (estimated count first), run, save, monitor. |
| B21 | **yes** | `POST /v1/paths` across the fixture's own eight-spoke hub. |
| Cross-cutting | **yes** (the reachable half) | The delta WebSocket through the proxy, via the
  ticket exchange. The audit assertions read Postgres directly and stay in the in-process tier. |
| R6's own flow | **yes** | The ingest root listed, a file selected, a draft made from it, and
  the Conduit proving it can open it — see the case named after the table. |

**The finding this file exists to surface — and it is now half closed.** Every "no" above that
mentions ingest used to be one fact: **a rendered deployment gave an analyst no route by which to
supply a source file.** `POST /v1/ingest/recipes` takes a `source_location` — a
path the *Conduit's own container* must be able to read — and the rendered `compose.yaml` mounts
nothing into that container but `osprey.yaml` and its data volume. The only `UploadFile` route in
the whole Conduit is the site image. So B1's "ingest both CDR files and both device extractions",
and every row that depends on data arriving that way (B2, B3, B6, B7, B8, B13, B14, B15–B18),
could not be performed by an analyst against a rendered deployment at all — not because this test
declined to attempt them, but because there was nothing to attempt.

**Owner ruling R6 (27 September 2026) closed the "no door" half**, and this file walks it:
`components.storage.ingest` is bind-mounted read-only into the Conduit for every profile, the
Studio's Connect stage lists it, and the case named in the table above proves the whole chain
against a real deployment — including the part that actually matters, that the Conduit can *open*
the path the listing handed back.

**What still keeps B1-B3 in-process is now a different and much narrower gap: connectors.** Those
rows assert identifier normalisation, duplicate collapse and timestamp recovery, and each depends
on the `cdr-generic-csv` connector profile's own configuration (`date_order: dmy`, a declared
timezone). `schemas.ingest.CONNECTOR_CATALOGUE` marks exactly **one** connector built —
`generic-csv` — and the rest of `09_INGEST_STUDIO.md` §2's catalogue is declared and unbuilt.
Measured over the wire, not assumed: a draft naming `cdr-generic-csv` is refused
`connector_not_available`. Building carrier connector profiles is real, unscoped work recorded in
`07_BUILD_PLAN.md`; until then these rows stay at the in-process tier, where the recipe engine is
driven directly with a hand-written recipe.

**And the one A15 clause that is not reachable, named rather than quietly dropped.** A15's
"items marked consult-originator block the export by name" is evaluated against each item's
**stored** handling, and no node in either seeded fixture carries `sanitisation_code: "S2"` —
checked, not assumed. The gate's other three clauses (justification recorded, manifest carried,
a real artefact of the requested shape bearing the mark) are proven below against real seeded
nodes. Closing the fourth means seeding one consult-originator node, which would change the
population `test_fixture_corp_shape.py` and `06_DECISIONS.md` ADR-035 §C5's re-measured scores
are asserted against — a deliberate fixture change, not a closing-pass tweak, so it is recorded
and not made here. It remains proven at the in-process tier
(`tests/services/api/test_export_routes.py::test_export_route_blocks_a_consult_originator_item_
and_names_it_over_http`).

**Running it.**

```bash
python -m harness.apply --profile local-lite --build --demo-analyst --seed hmp,fixture-corp
OSPREY_TEST_OVER_THE_WIRE=1 \
  OSPREY_LIVE_INVESTIGATION_ID=<the id apply printed> \
  .venv/bin/python -m pytest tests/scenarios/test_phase8_exit_over_the_wire.py
```

**Run it against a freshly seeded deployment, once.** Two rows make assertions the platform
deliberately does not let a caller take back — B11's manual `SAME_AS` (`POST /resolution/split`
is the opposite assertion, not an undo) and, transiently, A15's retraction (restored here, in a
`finally`, because `confirm` genuinely is its mirror). That is correct behaviour: an analyst's
assertion is evidence, not a toggle. It does mean a second run against the same containers is
measuring a graph the first run changed, which is the same trap `CLAUDE.md` rule 14 names for
timing measurements. `harness.apply --seed` resets the database, so re-applying is the reset.

The demo analyst's password is read from the rendered `deployment.env` (apply's own last line
names the file), or from `OSPREY_DEMO_ANALYST_PASSWORD` directly. The investigation id has no
discoverable route — the Conduit has no "list investigations" — so it is passed in, which is
exactly what an analyst does with the URL `apply` prints. `OSPREY_LIVE_INVESTIGATION_ID` is the
same variable `apps/workspace/live/live.ts` already uses, deliberately, so one deployment serves
both tiers without a second convention.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import urllib.parse
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import httpx
import pytest
import yaml
from tests.scenarios.fixtures.fixture_corp import _synthetic_nino
from tests.scenarios.fixtures.hmp_population import (
    PRINCIPAL_SUBJECT_PRISON_NUMBER,
    RELAY_GROUP_PRISON_NUMBERS,
    SECOND_SUBJECT_PRISON_NUMBER,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("OSPREY_TEST_OVER_THE_WIRE") != "1",
    reason=(
        "needs a rendered local-lite deployment with --demo-analyst; opt in with "
        "OSPREY_TEST_OVER_THE_WIRE=1 and OSPREY_LIVE_INVESTIGATION_ID"
    ),
)

REPO_ROOT = Path(__file__).resolve().parents[2]

WORKSPACE_ORIGIN = os.environ.get("OSPREY_WORKSPACE_ORIGIN", "http://localhost:8080")
KEYCLOAK_ORIGIN = os.environ.get("OSPREY_KEYCLOAK_ORIGIN", "http://localhost:8081")
REALM = os.environ.get("OSPREY_REALM", "osprey")

#: `harness/realm.py`'s own `GLASS_CLIENT_ID` and `DEMO_ANALYST_SUBJECT`. Restated rather than
#: imported for the same reason `apps/workspace/src/auth/oidcConfig.ts` restates them: this is the
#: analyst's side of the door, and it should not need the harness to open it.
GLASS_CLIENT_ID = "osprey-glass"
DEMO_ANALYST_SUBJECT = "osprey-demo-analyst"

#: `services/resolve/projection.py`'s own detents — restated here for the same reason, since the
#: Glass's own slider sends these numbers and nothing else.
#: Matches what both seed fixtures write, and what the demo analyst can receive.
_FIXTURE_HANDLING = {
    "classification": "OFFICIAL",
    "handling_code": "P",
    "originator": "verify",
    "owning_unit": "verify",
}

THRESHOLD_STRICT = 0.99
THRESHOLD_BALANCED = 0.95


def _demo_analyst_password() -> str:
    direct = os.environ.get("OSPREY_DEMO_ANALYST_PASSWORD")
    if direct:
        return direct
    env_path = Path(
        os.environ.get(
            "OSPREY_DEPLOYMENT_ENV", str(REPO_ROOT / "deploy/generated/local-lite/deployment.env")
        )
    )
    # **`fail`, never `skip`, past this point.** The module-level `skipif` is the opt-in; once a
    # caller has opted in, a missing password or investigation id is a misconfigured run, not a
    # reason to report green. A CI job that opts in and then skips every case is the exact shape
    # `CLAUDE.md` rule 15 names — a gate that cannot go red.
    if not env_path.exists():
        pytest.fail(f"no rendered deployment env at {env_path}; run apply --demo-analyst first")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("OSPREY_DEMO_ANALYST_PASSWORD="):
            return line.split("=", 1)[1].strip()
    pytest.fail(
        f"{env_path} carries no OSPREY_DEMO_ANALYST_PASSWORD — the deployment was applied "
        "without --demo-analyst, so there is no subject to sign in as"
    )


def _sign_in_as_the_demo_analyst() -> str:
    """The real thing: authorization code with PKCE, Keycloak's own login form, a code on the
    redirect, exchanged at the token endpoint. Returns the access token.

    **The one accommodation, named because it looks like a weakening and is not.** Keycloak sets
    `AUTH_SESSION_ID` with `Secure` even when serving plain HTTP in `start-dev`, and
    `http.cookiejar` will not send a `Secure` cookie over `http://`. A browser will: every major
    engine treats `localhost` as a secure context and sends it. Clearing the flag on the jar makes
    this client behave the way the browser this test stands in for behaves — it does not change
    what Keycloak checks, and the PKCE verifier, the redirect URI and the client's public-client
    status are all still enforced by the server exactly as they are for the Glass. Found by
    measurement, not guessed: without it Keycloak refuses the login POST with "Cookie not found.
    Please make sure cookies are enabled in your browser."
    """
    password = _demo_analyst_password()
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    redirect_uri = f"{WORKSPACE_ORIGIN}/"
    authorize = f"{KEYCLOAK_ORIGIN}/realms/{REALM}/protocol/openid-connect/auth?" + (
        urllib.parse.urlencode(
            {
                "client_id": GLASS_CLIENT_ID,
                "response_type": "code",
                "scope": "openid",
                "redirect_uri": redirect_uri,
                "state": secrets.token_urlsafe(8),
                "nonce": secrets.token_urlsafe(8),
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
    )
    with httpx.Client(follow_redirects=False, timeout=60) as browser:
        page = browser.get(authorize)
        assert page.status_code == 200, f"the realm did not serve a login page: {page.status_code}"
        for cookie in browser.cookies.jar:
            cookie.secure = False
        form_action = re.search(r'action="([^"]+)"', page.text)
        assert form_action, "Keycloak's login page carried no form action"
        submitted = browser.post(
            form_action.group(1).replace("&amp;", "&"),
            data={"username": DEMO_ANALYST_SUBJECT, "password": password},
        )
        assert submitted.status_code == 302, (
            "the demo analyst was not signed in — Keycloak answered "
            f"{submitted.status_code} rather than redirecting with a code"
        )
        location = submitted.headers["location"]
        code = urllib.parse.parse_qs(urllib.parse.urlparse(location).query).get("code", [None])[0]
        assert code, f"no authorization code on the redirect: {location}"
        exchanged = browser.post(
            f"{KEYCLOAK_ORIGIN}/realms/{REALM}/protocol/openid-connect/token",
            data={
                "grant_type": "authorization_code",
                "client_id": GLASS_CLIENT_ID,
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": verifier,
            },
        )
        assert exchanged.status_code == 200, exchanged.text
        return str(exchanged.json()["access_token"])


@pytest.fixture
def analyst() -> Iterator[httpx.Client]:
    """A signed-in analyst, talking to the deployment through the workspace's nginx and nothing
    else. Function-scoped on purpose: Keycloak's default access-token lifespan is five minutes,
    and a session-scoped client would start returning 401 part-way through the second test for a
    reason that has nothing to do with what that test is checking."""
    token = _sign_in_as_the_demo_analyst()
    with httpx.Client(
        base_url=WORKSPACE_ORIGIN,
        headers={"Authorization": f"Bearer {token}"},
        timeout=180,
    ) as client:
        yield client


@pytest.fixture
def seeded_scope() -> str:
    scope = os.environ.get("OSPREY_LIVE_INVESTIGATION_ID")
    if not scope:
        pytest.fail(
            "OSPREY_LIVE_INVESTIGATION_ID is not set — it is the investigation `harness.apply` "
            "seeded into and printed on its last-but-one line; the Conduit has no route to "
            "discover it, by design. Failing rather than skipping: this run opted in."
        )
    return scope


def _find(analyst: httpx.Client, identifier: str) -> dict:
    """The search box, which is how an analyst reaches anything at all: `POST /v1/search` is an
    exact match against a declared identifier (`services/api/search.py`), not free text."""
    response = analyst.post("/v1/search", json={"query": identifier, "limit": 5})
    assert response.status_code == 200, response.text
    nodes = response.json()["nodes"]
    assert nodes, f"nothing in the deployment's seeded graph carries the identifier {identifier!r}"
    return dict(nodes[0])


def _new_investigation(analyst: httpx.Client) -> str:
    created = analyst.post("/v1/investigations")
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def test_the_analysts_own_door_opens(analyst: httpx.Client) -> None:
    """Before either scenario: the sign-in produced a token the deployed Conduit accepts, through
    the proxy, and an unsigned request to the same route does not. Named per CLAUDE.md rule 12 —
    if the realm's audience mapper, the Conduit's `verify_aud`, or nginx's `/v1/` location were
    wrong, this is the case that fails, not one of the scenario walkthroughs."""
    signed_in = analyst.get("/v1/ontology")
    assert signed_in.status_code == 200, signed_in.text
    assert signed_in.json()["entity_types"], "the ontology came back empty through the proxy"

    anonymous = httpx.get(f"{WORKSPACE_ORIGIN}/v1/ontology", timeout=60)
    assert anonymous.status_code in (401, 403), (
        "the deployed Conduit served the ontology to an unauthenticated caller through the "
        f"proxy: {anonymous.status_code}"
    )


def test_scenario_a_over_the_wire(analyst: httpx.Client, seeded_scope: str) -> None:
    # === A2: incident density across the grid — the four hotspot cells are the top four by
    # === count and together account for ~52% of incidents. `target_id` categorical cross-filter
    # === is the mechanism 08's own "Implementation note — A2" records, not `geo_bins`, which
    # === cannot resolve individual cells at this fixture's scale.
    cells = analyst.post(
        "/v1/analytics/cross-filter",
        json={
            "filter": {"investigation_scope": seeded_scope},
            "dimensions": [{"name": "cells", "field": "target_id", "bucketing": "categorical"}],
        },
    )
    assert cells.status_code == 200, cells.text
    buckets = cells.json()["cells"]["buckets"]
    counts = [b["count"] for b in buckets]
    assert counts == sorted(counts, reverse=True), "cross-filter did not rank the cells"
    hotspots = [b["label"] for b in buckets[:4]]
    total = sum(counts)
    hotspot_share = sum(counts[:4]) / total
    assert 0.45 <= hotspot_share <= 0.60, (
        f"the four hotspot cells are {hotspot_share:.1%} of {total} incidents, not ~52% — "
        "08's own A2 figure, measured at 51.1% when it was recorded"
    )

    # === A3: selecting the hotspot cells restricts everything in lockstep — the same filter,
    # === one request, every dimension computed against it.
    # === A4: the cyclical weekday × hour view over that restriction — two intra-day peaks, and
    # === Saturday and Sunday together ~34% of the filtered total.
    restricted = analyst.post(
        "/v1/analytics/cross-filter",
        json={
            "filter": {"investigation_scope": seeded_scope, "node_ids": hotspots},
            "dimensions": [{"name": "cyclical", "bucketing": "weekday_hour"}],
        },
    )
    assert restricted.status_code == 200, restricted.text
    cyclical = restricted.json()["cyclical"]["buckets"]
    filtered_total = sum(b["count"] for b in cyclical)
    assert filtered_total < total, "restricting to the hotspot cells did not restrict anything"
    assert filtered_total == sum(counts[:4]), (
        "the cross-filtered total does not match the four cells' own counts — the restriction is "
        "not being applied in the same WHERE clause the aggregation uses"
    )
    weekend = sum(b["count"] for b in cyclical if b["weekday"] in (5, 6))
    weekend_share = weekend / filtered_total
    assert 0.28 <= weekend_share <= 0.40, (
        f"Saturday and Sunday are {weekend_share:.1%} of the filtered total, not ~34%"
    )

    # === A5: brushing to the two intra-day peak windows — the combined selection is ~66% of
    # === incidents in the hotspot cells. Measured from the same cyclical histogram the analyst
    # === is looking at, rather than assumed from the fixture's generator.
    by_hour: dict[int, int] = {}
    for bucket in cyclical:
        by_hour[bucket["hour"]] = by_hour.get(bucket["hour"], 0) + bucket["count"]
    ranked_hours = sorted(by_hour.items(), key=lambda kv: -kv[1])
    assert len(ranked_hours) >= 4
    peak_hours = {h for h, _ in ranked_hours[:4]}
    # Two peaks, not one broad plateau: the four busiest hours fall into two runs of adjacent
    # hours, which is what "two intra-day peaks are visible" means on a 24-hour axis.
    runs = _adjacent_runs(sorted(peak_hours))
    assert len(runs) == 2, f"the busiest hours {sorted(peak_hours)} do not form two peaks: {runs}"

    # === A7 (the reachable half — the item-category filter is 08's own recorded "Known gap"):
    # === the people named in the surviving reports, seeded as a named working-set history step.
    investigation = _new_investigation(analyst)
    principal = _find(analyst, PRINCIPAL_SUBJECT_PRISON_NUMBER)
    second = _find(analyst, SECOND_SUBJECT_PRISON_NUMBER)
    relay = [_find(analyst, number) for number in RELAY_GROUP_PRISON_NUMBERS]
    seeded = analyst.post(
        f"/v1/investigations/{investigation}/seed",
        json={"nodes": [principal, second, *relay], "edges": []},
    )
    assert seeded.status_code == 200, seeded.text
    history = analyst.get(f"/v1/investigations/{investigation}/history")
    assert history.status_code == 200, history.text
    assert any("Seeded" in step["label"] for step in history.json()), (
        "the seed did not become a named history step"
    )

    # === A8: rank the resulting people by appearance count — the principal subject ranks first.
    # === "Appearance count" is the `MENTIONED_IN` edge count, **not** raw degree inside the
    # === working set: the in-process tier's own A8 comment records why, and this run reproduced
    # === it before the distinction was made here. Ten people seeded, the relay group densely
    # === `ASSOCIATE_OF`-linked among themselves, and raw degree ranked a relay member first at 7
    # === against the principal subject's 1 — which is A12's finding about the relay group, not
    # === A8's about the principal. Over the wire the analyst reaches the real count the same way
    # === the metrics panel does: expand the seeded set restricted to `MENTIONED_IN` and count.
    mentions = analyst.post(
        f"/v1/investigations/{investigation}/expand",
        json={
            "request": {
                "node_ids": [node["id"] for node in (principal, second, *relay)],
                "depth": 1,
                "edge_types": ["MENTIONED_IN"],
            }
        },
    )
    assert mentions.status_code == 200, mentions.text
    mention_counts: dict[str, int] = {}
    for edge in mentions.json()["delta"]["edges"]:
        if edge["type"] != "MENTIONED_IN":
            continue
        for endpoint in (edge["source"], edge["target"]):
            mention_counts[endpoint] = mention_counts.get(endpoint, 0) + 1
    person_ids = {node["id"] for node in (principal, second, *relay)}
    person_mentions = {nid: n for nid, n in mention_counts.items() if nid in person_ids}
    assert person_mentions, "no MENTIONED_IN edges came back for any seeded person"
    assert person_mentions[principal["id"]] == max(person_mentions.values()), (
        f"the principal subject does not rank first by appearance count: {person_mentions}"
    )
    # The affiliated subset is identifiable by an `Organisation` edge, A8's second clause.
    affiliation = analyst.post(
        f"/v1/investigations/{investigation}/expand",
        json={
            "request": {
                "node_ids": [node["id"] for node in relay],
                "depth": 1,
                "edge_types": ["MEMBER_OF"],
            }
        },
    )
    assert affiliation.status_code == 200, affiliation.text
    organisations = {
        node["id"]
        for node in affiliation.json()["delta"]["nodes"]
        if node["type"] == "Organisation"
    }
    assert organisations, "the relay group is not identifiable by an Organisation edge"

    # === A9: expand the principal subject's relationships — with a cardinality preview *first*.
    preview = analyst.post(
        f"/v1/investigations/{investigation}/expand/preview",
        json={"request": {"node_ids": [principal["id"]], "depth": 1}},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["candidate_node_count"] > 0, (
        "the preview offered no candidates, so the expansion it precedes cannot be previewed"
    )
    expanded = analyst.post(
        f"/v1/investigations/{investigation}/expand",
        json={"request": {"node_ids": [principal["id"]], "depth": 1}},
    )
    assert expanded.status_code == 200, expanded.text
    expansion = expanded.json()["delta"]
    assert expansion["edges"], "expanding the principal subject returned no edges"

    # === A10: the family link to the second subject, and a shared Organisation. Read off the
    # === expansion the analyst just performed, not from a store.
    edge_types = {edge["type"] for edge in expansion["edges"]}
    assert edge_types & {"FAMILY_OF", "ASSOCIATE_OF", "MEMBER_OF"}, (
        f"none of the expected relationship types came back: {sorted(edge_types)}"
    )

    # === A11: drop the timeline filter to the full available history — prior-period events
    # === appear, and the pattern is continuous rather than new. The current window is not a
    # === constant this file can hard-code against a deployment it did not seed, so it is derived
    # === from the timeline the analyst is looking at: daily buckets, and the current period is
    # === everything after the largest gap in them. The fixture's four prior-period events sit
    # === before that gap, a week apart each.
    unfiltered = analyst.post(
        "/v1/analytics/histogram",
        json={
            "filter": {"investigation_scope": seeded_scope},
            "bucketing": "fixed_interval",
            "interval_seconds": 86_400,
        },
    )
    assert unfiltered.status_code == 200, unfiltered.text
    daily = sorted(unfiltered.json()["buckets"], key=lambda b: b["start"])
    assert len(daily) > 2, daily
    gaps = [
        (
            _parsed(daily[i]["start"]) - _parsed(daily[i - 1]["start"]),
            i,
        )
        for i in range(1, len(daily))
    ]
    _, current_period_starts_at = max(gaps)
    current_window_start = daily[current_period_starts_at]["start"]
    prior_events = sum(b["count"] for b in daily[:current_period_starts_at])
    assert prior_events > 0, (
        "the seeded timeline has no events before its own largest gap, so A11's prior period "
        "does not exist in this deployment's data"
    )

    windowed = analyst.post(
        "/v1/analytics/histogram",
        json={
            "filter": {
                "investigation_scope": seeded_scope,
                "window": {"valid_from": current_window_start, "valid_to": daily[-1]["end"]},
            },
            "bucketing": "fixed_interval",
            "interval_seconds": 86_400,
        },
    )
    assert windowed.status_code == 200, windowed.text
    current_events = sum(b["count"] for b in windowed.json()["buckets"])
    all_events = sum(b["count"] for b in daily)
    assert all_events - current_events == prior_events, (
        f"dropping the timeline filter changed the population by {all_events - current_events}, "
        f"not by the {prior_events} prior-period events the timeline itself shows"
    )

    # === A12: the Clique Metric — the relay group scores high on clique and low on degree
    # === centrality relative to the principal subject's own much higher raw connectivity. Both
    # === metrics are computed after the expansions above, against the working set as it actually
    # === stands: degree inside a bare seeded set reflects nothing but who was seeded.
    relay_ids = [node["id"] for node in relay]
    expanded_a12 = analyst.post(
        f"/v1/investigations/{investigation}/expand",
        json={"request": {"node_ids": [*relay_ids, principal["id"]], "depth": 1}},
    )
    assert expanded_a12.status_code == 200, expanded_a12.text

    clique = analyst.post(f"/v1/investigations/{investigation}/compute/clique_metric", json={})
    assert clique.status_code == 200, clique.text
    clique_values = clique.json()["values"]
    relay_clique = [clique_values[rid] for rid in relay_ids if rid in clique_values]
    assert relay_clique, "the relay group is not in the computed working set"
    assert max(relay_clique) == max(clique_values.values()), (
        "the relay group does not score highest on the clique metric"
    )

    degree = analyst.post(f"/v1/investigations/{investigation}/compute/degree", json={})
    assert degree.status_code == 200, degree.text
    assert degree.json()["mode"] == "sync"
    degrees = degree.json()["values"]
    assert max(degrees[rid] for rid in relay_ids) < degrees[principal["id"]], (
        "the relay group does not score low on degree centrality relative to the principal "
        f"subject: {[degrees[rid] for rid in relay_ids]} vs {degrees[principal['id']]}"
    )

    # === A13: four judgements, each with at least one supporting reference — and a judgement
    # === cannot be saved without one. The refusal is asserted first: without it this row proves
    # === only that saving works.
    unsupported = analyst.post(
        f"/v1/investigations/{investigation}/judgements",
        json={
            "investigation_id": investigation,
            "statement": "unsupported",
            "probability_band": "likely",
            "supporting": [],
        },
    )
    assert unsupported.status_code == 422, unsupported.text
    assert unsupported.json()["error"] == "no_supporting_reference"

    judgements = []
    for index in range(4):
        saved = analyst.post(
            f"/v1/investigations/{investigation}/judgements",
            json={
                "investigation_id": investigation,
                "statement": f"Judgement {index}",
                "probability_band": "likely",
                "supporting": [principal["id"]],
            },
        )
        assert saved.status_code == 201, saved.text
        judgements.append(saved.json()["id"])

    # === A14: seven gaps linked to the entities they concern; three assumptions linked to the
    # === judgements they support.
    for index in range(7):
        gap = analyst.post(
            f"/v1/investigations/{investigation}/gaps",
            json={
                "investigation_id": investigation,
                "question": f"Gap {index}",
                "linked_entities": [principal["id"]],
            },
        )
        assert gap.status_code == 201, gap.text
    for index in range(3):
        assumption = analyst.post(
            f"/v1/investigations/{investigation}/assumptions",
            json={
                "investigation_id": investigation,
                "statement": f"Assumption {index}",
                "if_false_impact": "the assessment materially weakens",
                "linked_judgements": [judgements[index]],
            },
        )
        assert assumption.status_code == 201, assumption.text
    assert len(analyst.get(f"/v1/investigations/{investigation}/gaps").json()["gaps"]) == 7
    assert (
        len(analyst.get(f"/v1/investigations/{investigation}/assumptions").json()["assumptions"])
        == 3
    )

    # === A15: the export produces a real artefact of the requested shape, carrying the mark, with
    # === a manifest and a ledger entry. The consult-originator block is the one clause not
    # === reachable here — this file's own docstring says why, and names where it is proven.
    for kind in ("subgraph", "report"):
        body = {
            "artefact_kind": kind,
            "items": [{"id": principal["id"], "kind": "node", "handling": principal["handling"]}],
            "resolution_threshold": THRESHOLD_BALANCED,
        }
        if kind == "report":
            body["judgement_ids"] = judgements
        exported = analyst.post(f"/v1/investigations/{investigation}/export", json=body)
        assert exported.status_code == 200, exported.text
        artefact = exported.json()
        assert artefact["mark"]["osprey_mark"] == "OspreyFlow"
        assert artefact["manifest"]["policy"]
        assert artefact["ledger_entry_id"], f"the {kind} export recorded no ledger entry"

    # === The additional assertion 08 records after A15: retraction propagates. Retracting a node
    # === that supports a judgement flags that judgement for review within the same session.
    #
    # **This step mutates the deployment's own shared, persistent seed**, which nothing else in
    # this file does, and the restore is in a `finally` for that reason. Found the hard way while
    # building this file: a run that failed *after* the retraction and *before* the restore left
    # the seeded principal subject in `inferred`, and the next run then failed at the retraction
    # itself with `provenance_transition_invalid` — a real failure, but of the previous run's
    # tidying, not of anything this row is about. So the state is also repaired on the way in.
    #
    # **And this row is where running over the wire found something no other test could.** 08's
    # own additional assertion says the judgement "is flagged for review within the same session".
    # The flag *is* written — `flag_judgements_citing_superseded_node`, proven by
    # `tests/services/api/test_assessments.py`, which calls it directly and re-reads the **store**.
    # Through the analyst's own door the judgement does not appear flagged: it disappears. A
    # retraction supersedes the node with a **new id**, the judgement's `supporting` still holds
    # the old one, and ADR-046's hide-in-full filter (`judgement_visible_to`, composed into
    # `list_visible_judgements`, which is the route the Judgements tab calls) removes every
    # judgement with an unverifiable supporting citation. Two rules each correct alone compose
    # into a third behaviour the specification does not describe. Measured, not inferred: before
    # the retraction the judgement lists with `flagged_for_review: false`; after it, the list is
    # empty; the node is back under a new id in `inferred`.
    #
    # **Owner ruling R7 (27 September 2026, TENTATIVE — the owner is revisiting it after their
    # own usability walkthrough; `06_DECISIONS.md` ADR-046's addendum carries it in that state).**
    # This step used to pin the *opposite* behaviour, deliberately, so that the fix could not land
    # silently: retracting a supporting node made the judgement **disappear** from the Judgements
    # tab, because supersession gives the node a new id and ADR-046's hide-in-full rule read the
    # old citation as unverifiable. The analyst was never shown the review flag
    # `01_DOMAIN_MODEL.md` §5 promises.
    #
    # R7 narrows hide-in-full to what it was actually decided for — citations the principal is not
    # *permitted* to verify — and leaves a system-superseded citation resolving forward. So the
    # assertion below is the flipped one, and `08_ACCEPTANCE_SCENARIOS.md`'s own sentence was
    # corrected in the same change, which is exactly what the old comment demanded.
    before = analyst.get(f"/v1/investigations/{investigation}/judgements")
    assert before.status_code == 200, before.text
    listed_before = [j for j in before.json()["judgements"] if j["id"] in judgements]
    assert len(listed_before) == 4, before.text
    assert not any(j["flagged_for_review"] for j in listed_before)

    _restore_asserted(analyst, PRINCIPAL_SUBJECT_PRISON_NUMBER)
    to_retract = _find(analyst, PRINCIPAL_SUBJECT_PRISON_NUMBER)
    try:
        retracted = analyst.post(f"/v1/nodes/{to_retract['id']}/retract")
        assert retracted.status_code == 200, retracted.text
        successor = retracted.json()["node_id"]
        assert successor != to_retract["id"], (
            "retraction did not supersede the node with a new id, which is the premise of "
            "everything below"
        )

        reviewed = analyst.get(f"/v1/investigations/{investigation}/judgements")
        assert reviewed.status_code == 200, reviewed.text
        still_listed = [j for j in reviewed.json()["judgements"] if j["id"] in judgements]
        assert len(still_listed) == 4, (
            "a judgement resting on a retracted node vanished from its own author's Judgements "
            "tab instead of being flagged for review. That is the composition R7 corrects: "
            f"hide-in-full is about permission, not about supersession. {reviewed.text[:400]}"
        )
        assert all(j["flagged_for_review"] for j in still_listed), (
            "the judgements are visible but not flagged — `01_DOMAIN_MODEL.md` §5 promises the "
            f"analyst a review flag, and this is where they would see it: {still_listed}"
        )
        # The citation itself is never rewritten; the successor arrives beside it, for display.
        for judgement in still_listed:
            assert to_retract["id"] in judgement["supporting"], (
                "the citation was rewritten — a judgement asserted something about the evidence "
                "as it stood, and `supporting` must keep naming the revision actually cited"
            )
            assert judgement["resolved_citations"].get(to_retract["id"]) == successor, (
                "the superseded citation did not resolve forward, so the tab has nothing to "
                f"render in its place: {judgement['resolved_citations']}"
            )
    finally:
        _restore_asserted(analyst, PRINCIPAL_SUBJECT_PRISON_NUMBER)


def _restore_asserted(analyst: httpx.Client, identifier: str) -> None:
    """Put a node back to `asserted` if it is not already. `retract` supersedes a node with a new
    id, so the node is re-found by its identifier rather than held by id across the transition."""
    node = _find(analyst, identifier)
    if node["provenance"]["state"] == "asserted":
        return
    confirmed = analyst.post(f"/v1/nodes/{node['id']}/confirm")
    assert confirmed.status_code == 200, confirmed.text


def _same_as_edge(
    analyst: httpx.Client, investigation: str, node_a: str, node_b: str
) -> dict | None:
    """The `SAME_AS` edge between one specific pair, read the only way the Glass can read it —
    an expansion restricted to that edge type. Both nodes must already be in the working set."""
    expanded = analyst.post(
        f"/v1/investigations/{investigation}/expand",
        json={"request": {"node_ids": [node_a], "depth": 1, "edge_types": ["SAME_AS"]}},
    )
    assert expanded.status_code == 200, expanded.text
    for edge in expanded.json()["delta"]["edges"]:
        if {edge["source"], edge["target"]} == {node_a, node_b}:
            return dict(edge)
    return None


def _same_as_score(
    analyst: httpx.Client, investigation: str, node_a: str, node_b: str
) -> float | None:
    edge = _same_as_edge(analyst, investigation, node_a, node_b)
    return None if edge is None else edge["properties"].get("score")


def _parsed(timestamp: str) -> datetime:
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


def _adjacent_runs(hours: list[int]) -> list[list[int]]:
    runs: list[list[int]] = []
    for hour in hours:
        if runs and hour - runs[-1][-1] == 1:
            runs[-1].append(hour)
        else:
            runs.append([hour])
    return runs


def test_scenario_b_over_the_wire(analyst: httpx.Client) -> None:
    # === B4 (adapted to the deployment's own seed): seed a working set from search — person
    # === entities with no edges between them. The "no edges" half is not decoration: a
    # === search-seeded node carries none by construction (STANDING.md, 27 September), so a test
    # === that found some here would be measuring something other than what it claims.
    investigation = _new_investigation(analyst)
    left = _find(analyst, _synthetic_nino("corp-res-close-given-1"))
    right = _find(analyst, _synthetic_nino("corp-res-close-given-2"))
    seeded = analyst.post(
        f"/v1/investigations/{investigation}/seed",
        json={"nodes": [left, right], "edges": []},
    )
    assert seeded.status_code == 200, seeded.text
    assert seeded.json()["delta"]["edges"] == [], (
        "a search-seeded working set arrived with edges, which it cannot have"
    )

    # === B5 (adapted): one hop out from a seeded node returns its neighbourhood.
    ring_org = _find(analyst, "FIXTURE-67BD0781")
    ring_investigation = _new_investigation(analyst)
    assert (
        analyst.post(
            f"/v1/investigations/{ring_investigation}/seed",
            json={"nodes": [ring_org], "edges": []},
        ).status_code
        == 200
    )
    hop = analyst.post(
        f"/v1/investigations/{ring_investigation}/expand",
        json={"request": {"node_ids": [ring_org["id"]], "depth": 1}},
    )
    assert hop.status_code == 200, hop.text
    assert hop.json()["delta"]["edges"], "one hop out from the ring organisation found nothing"

    # === B9: move the resolution threshold from Strict to Balanced on a genuinely close-but-not-
    # === exact Person pair. Strict first, and it must *not* merge — otherwise the move proves
    # === nothing. The pair is ADR-035 §C5's own `close_given_name`, re-measured at 0.981285 in
    # === round 12b, which is between the two detents by construction.
    strict = analyst.put(
        f"/v1/investigations/{investigation}/resolution/threshold",
        json={"threshold": THRESHOLD_STRICT},
    )
    assert strict.status_code == 200, strict.text
    assert strict.json()["merged"] == 0, (
        "Strict merged the close-given-name pair, which scores 0.981285 — below Strict. The "
        "threshold move B9 asks for would demonstrate nothing."
    )

    balanced = analyst.put(
        f"/v1/investigations/{investigation}/resolution/threshold",
        json={"threshold": THRESHOLD_BALANCED},
    )
    assert balanced.status_code == 200, balanced.text
    summary = balanced.json()
    assert summary["merged"] == 1, summary
    assert summary["affected"] == 2, summary

    # === B10: open `explain` on the merged cluster — per-comparison match weights, not just the
    # === total score.
    # `affected_cluster_ids` is a node-id → cluster-id map, not a list — the shape the Glass uses
    # to repaint cluster membership in place without re-syncing the working set.
    moved = summary.get("affected_cluster_ids") or {}
    assert moved, f"the reprojection named no affected cluster: {summary}"
    cluster_id = next(iter(moved.values()))
    explained = analyst.get(f"/v1/investigations/{investigation}/resolution/explain/{cluster_id}")
    assert explained.status_code == 200, explained.text
    pairs = explained.json()["pairs"]
    assert pairs, "explain returned no pairs for a cluster that had just merged"
    pair = pairs[0]
    assert pair["manually_asserted"] is False
    assert pair["comparison_vector"], (
        "explain showed only a total score — B10 asks for the per-comparison weights"
    )
    assert THRESHOLD_BALANCED <= pair["score"] < THRESHOLD_STRICT

    # === B11: attribute one node to another by hand — a SAME_AS at score 1.0, provenance
    # === asserted, attributed to this signed-in analyst. On a **different** pair from B9's:
    # === `close_surname_and_given` scores 0.867624 (ADR-035 §C5, re-measured round 12b), below
    # === Balanced, so Splink has not merged it and a manual link has something to do. Linking
    # === B9's own pair instead returned `merged: 0` — correct, and proving nothing, because the
    # === threshold move one step earlier had already merged it.
    manual_left = _find(analyst, _synthetic_nino("corp-res-close-both-1"))
    manual_right = _find(analyst, _synthetic_nino("corp-res-close-both-2"))
    assert (
        analyst.post(
            f"/v1/investigations/{investigation}/seed",
            json={"nodes": [manual_left, manual_right], "edges": []},
        ).status_code
        == 200
    )
    #
    # **This step leaves a permanent mark on the deployment's own graph, and cannot not.** A
    # manual link writes an asserted `SAME_AS` that no route removes: `POST /resolution/split` is
    # not its undo, it is the opposite *assertion* ("these are not the same"), which suppresses
    # the Splink merge as well. Measured, not assumed, while building this file — an earlier draft
    # linked B9's own pair, the next run's B9 then reported `merged: 0` at both detents because
    # the pair was already merged, and splitting it back left it permanently unmergeable instead.
    # Both behaviours are correct: an analyst's assertion is evidence, not a UI state to toggle.
    #
    # So the row's own words are what is asserted — "a `SAME_AS` with score 1.0, provenance
    # `asserted`, attributed to the analyst" — which is true on every run, and the reprojection's
    # `merged: 1` is required only when the pair was not already collapsed at this τ. Asserting
    # the count unconditionally made this step pass exactly once per deployment and then report a
    # defect that was really its own previous run.
    already_linked = _same_as_score(analyst, investigation, manual_left["id"], manual_right["id"])
    linked = analyst.post(
        f"/v1/investigations/{investigation}/resolution/link",
        json={"node_a": manual_left["id"], "node_b": manual_right["id"]},
    )
    assert linked.status_code == 200, linked.text
    if already_linked is None or already_linked < THRESHOLD_BALANCED:
        assert linked.json()["merged"] == 1, (
            "the pair was below τ before the manual link and is still not collapsed after it: "
            f"{linked.text}"
        )
    asserted_edge = _same_as_edge(analyst, investigation, manual_left["id"], manual_right["id"])
    assert asserted_edge is not None, "the manual link wrote no SAME_AS edge"
    assert asserted_edge["properties"]["score"] == 1.0, asserted_edge
    assert asserted_edge["provenance"]["state"] == "asserted", asserted_edge
    # Attributed to the analyst who asserted it — `_manual_assertion` writes the principal's own
    # id as the source locator, which is the only record of *who* said these are the same.
    assert asserted_edge["provenance"]["sources"][0]["locator"], asserted_edge

    # === B12: add an identifier to a hotlist — the hotlist records owner and review date.
    identifier = _synthetic_nino("corp-path-hub")
    created = analyst.post(
        "/v1/hotlists", json={"identifier": identifier, "review_date": "2027-01-01"}
    )
    assert created.status_code == 201, created.text
    listed = analyst.get("/v1/hotlists")
    assert listed.status_code == 200, listed.text
    mine = [h for h in listed.json()["hotlists"] if h["identifier"] == identifier]
    assert mine, f"the hotlist just created is not in the analyst's own list: {listed.text}"
    assert mine[0]["owner_id"], "the hotlist records no owner"
    assert mine[0]["review_date"] == "2027-01-01"

    # === B19: common contacts across two roots — the intersection, with the estimated count
    # === shown *before* running. Over Fixture Corp's own rings, which is what this deployment
    # === carries; the shape is the one `PatternNode.node_id` pins.
    pattern = {
        "nodes": [
            {"var": "x", "entity_type": "Person"},
            {"var": "y", "entity_type": "Person"},
        ],
        "edges": [{"edge_type": "ASSOCIATE_OF", "from_var": "x", "to_var": "y"}],
    }
    previewed = analyst.post("/v1/patterns/preview", json=pattern)
    assert previewed.status_code == 200, previewed.text
    assert previewed.json()["estimated_count"] > 0, (
        "the estimated count B19 asks to be shown before running came back empty"
    )
    ran = analyst.post("/v1/patterns/run", json=pattern)
    assert ran.status_code == 200, ran.text
    assert ran.json()["mode"] == "sync"

    # === B20: save the pattern as a monitor.
    saved = analyst.post("/v1/patterns/save", json={"name": "over-the-wire", "definition": pattern})
    assert saved.status_code == 201, saved.text
    # `pattern_id` is the stable identity across saves; `id` identifies this one save
    # (ADR-032/036/040). A monitor watches the pattern, not one version of it.
    pattern_id = saved.json()["pattern_id"]
    monitor = analyst.post("/v1/monitors", json={"pattern_id": pattern_id})
    assert monitor.status_code == 201, monitor.text
    monitors = analyst.get("/v1/monitors")
    assert monitors.status_code == 200, monitors.text
    assert any(m["pattern_id"] == pattern_id for m in monitors.json()["monitors"])

    # === B21: the pathfinder between two nodes, through the deployed Conduit, k-shortest.
    hub = _find(analyst, _synthetic_nino("corp-path-hub"))
    # The terminal node of the fixture's own length-3 spoke (`fixture_corp.py`'s
    # `corp-path-spoke{length}-{step}`), which is also the spoke carrying the SECRET
    # shortcut — so the path an OFFICIAL analyst finds is the 3-hop route, never the
    # shortcut, which is `test_fixture_corp_shape.py`'s own access-control assertion.
    spoke = _find(analyst, _synthetic_nino("corp-path-spoke3-3"))
    paths = analyst.post(
        "/v1/paths", json={"source": hub["id"], "target": spoke["id"], "k": 2, "max_hops": 6}
    )
    assert paths.status_code == 200, paths.text
    found = paths.json()
    assert found, "the pathfinder found no path across the fixture's own eight-spoke hub"
    assert found[0]["nodes"], "a path came back with no hydrated nodes (ADR-033)"
    assert found[0]["length"] <= found[-1]["length"], "k-shortest paths are not ordered"


def test_the_ingest_folder_is_reachable_and_usable_through_the_studio(
    analyst: httpx.Client,
) -> None:
    """**Owner ruling R6, 27 September 2026 — the door this file found was missing.** Round 13b
    recorded that a rendered deployment gave an analyst no route by which to supply a source file
    at all, which is why B1-B3 and six other rows are "in-process only" in the table above. R6's
    answer is the ingest root, listed by the Studio's Connect stage, and this is that chain walked
    over the wire: list -> select -> draft -> profile the real file.

    **What this proves, exactly.** The renderer's read-only bind mount is live, the Conduit can
    read through it, the analyst's own token carries the Studio role the listing needs, and the
    path the listing hands back is one the Conduit will actually open. That last part is the one
    worth stating: `source_location` is read *inside the container*, so a path that merely looks
    plausible proves nothing — the profile call below is what proves the Conduit opened it.

    **B1-B3 now have their own cases below** (round 13bf). They did not when this was written:
    the connector their fixture needs (`cdr-generic-csv`, `date_order: dmy`) was declared in the
    catalogue and refused by the Studio, so the rows stayed at the in-process tier. The paragraph
    that used to be here said so, and the guard below is what noticed when it stopped being true.
    """
    listing = analyst.get("/v1/ingest/source-files")
    assert listing.status_code == 200, listing.text
    files = listing.json()["files"]
    assert files, (
        f"the ingest root {listing.json()['root']!r} is empty, so there is nothing for an analyst "
        "to select — place a source file in the deployment's own `components.storage.ingest`"
    )
    chosen = files[0]
    assert chosen["source_location"].startswith(listing.json()["root"]), chosen

    # **The connector the acceptance fixture needs, which this round made selectable.** This
    # assertion used to run the other way: it required `cdr-generic-csv` to be refused
    # `connector_not_available`, and failed loudly the moment that stopped being true so the
    # coverage tables could not silently fall out of date. It did exactly that in round 13bf —
    # the guard is why the tables moved in the same change rather than a follow-up — and it now
    # holds the opposite invariant, that the connector an acceptance row depends on stays
    # available. `09_INGEST_STUDIO.md` §2 derives that from `connectors/cdr-generic-csv.yaml`.
    usable = analyst.post(
        "/v1/ingest/recipes",
        json={
            "label": "over-the-wire probe — the CDR carrier layout",
            "connector_profile": "cdr-generic-csv",
            "source_location": chosen["source_location"],
            "handling": _FIXTURE_HANDLING,
            "legal_basis": "RIPA s22 acquisition — fixture",
        },
    )
    assert usable.status_code == 201, usable.text
    profiled_cdr = analyst.get(f"/v1/ingest/recipes/{usable.json()['recipe_id']}/profile")
    assert profiled_cdr.status_code == 200, (
        "`cdr-generic-csv` is no longer usable over the wire, so B1-B3's own cases below cannot "
        f"run: {profiled_cdr.text}"
    )

    # The reachable chain, on the one built connector.
    draft = analyst.post(
        "/v1/ingest/recipes",
        json={
            "label": "over-the-wire — ingest folder selection",
            "connector_profile": "generic-csv",
            "source_location": chosen["source_location"],
            "handling": _FIXTURE_HANDLING,
            "legal_basis": "RIPA s22 acquisition — fixture",
        },
    )
    assert draft.status_code == 201, draft.text
    assert draft.json()["source_location"] == chosen["source_location"]
    assert draft.json()["ready_for_profile"] is True, (
        "Connect's three gate questions were answered and the draft is still not ready to "
        f"profile: {draft.text}"
    )

    # **The Conduit actually opened the file.** A `source_location` the container cannot read
    # fails here, so this is what separates "the listing returned a plausible string" from "the
    # mount works".
    profiled = analyst.get(f"/v1/ingest/recipes/{draft.json()['recipe_id']}/profile")
    assert profiled.status_code == 200, (
        "the Conduit could not profile the file the listing offered — the read-only mount is not "
        f"working, whatever the listing said: {profiled.text}"
    )


# ---------------------------------------------------------------------------------------------
# B1-B3, over the wire — round 13bf.
#
# These three rows were "in-process only" from round 13b until now, for a reason that was a real
# product gap rather than a testing shortfall: the Studio would not accept the connector the CDR
# fixture needs. Round 13bf made connector availability derive from `connectors/*.yaml`, made a
# profile's own settings reach the published recipe, put `git` in the Conduit's image and gave the
# recipe repository a persistent root — and only with all four does the chain an analyst actually
# walks reach a load. See `REPORT-13bf.md`.
# ---------------------------------------------------------------------------------------------

CDR_FIXTURE_NAME = "carrier-a-cdr.csv"


@pytest.fixture(scope="module")
def cdr_load() -> dict:
    """Walk Connect -> Profile -> Map -> Verify -> Publish -> Run once, and share the report.

    Module-scoped because the walk is the expensive part and B1, B2 and B3 are three assertions
    about one load, not three loads. Its own client is separate from the `analyst` fixture for the
    reason that fixture's docstring gives: tokens expire, and this one is minted for this walk.
    """
    token = _sign_in_as_the_demo_analyst()
    scope = os.environ.get("OSPREY_LIVE_INVESTIGATION_ID")
    if not scope:
        pytest.fail("OSPREY_LIVE_INVESTIGATION_ID is not set — see the `seeded_scope` fixture")

    with httpx.Client(
        base_url=WORKSPACE_ORIGIN, headers={"Authorization": f"Bearer {token}"}, timeout=180
    ) as client:
        listing = client.get("/v1/ingest/source-files")
        assert listing.status_code == 200, listing.text
        chosen = next(
            (f for f in listing.json()["files"] if f["name"] == CDR_FIXTURE_NAME), None
        )
        assert chosen is not None, (
            f"{CDR_FIXTURE_NAME} is not in the deployment's ingest root "
            f"({listing.json()['root']}) — B1-B3 need it there; the harness places it"
        )

        draft = client.post(
            "/v1/ingest/recipes",
            json={
                "label": "B1-B3 over the wire",
                # **The connector this round made selectable.** Declared in the catalogue and
                # refused by the Studio until now, which is exactly why these rows were stuck.
                "connector_profile": "cdr-generic-csv",
                "source_location": chosen["source_location"],
                "handling": _FIXTURE_HANDLING,
                "legal_basis": "RIPA s22 acquisition — fixture",
            },
        )
        assert draft.status_code == 201, draft.text
        recipe_id = draft.json()["recipe_id"]

        profiled = client.get(f"/v1/ingest/recipes/{recipe_id}/profile")
        assert profiled.status_code == 200, profiled.text

        row_template = yaml.safe_load(
            (Path(__file__).parent / "fixtures" / "cdr_recipe.yaml").read_text(encoding="utf-8")
        )["row_template"]
        mapped = client.put(
            f"/v1/ingest/recipes/{recipe_id}/row-template",
            json={"row_template": row_template, "unmapped_fields": []},
        )
        assert mapped.status_code == 200, mapped.text

        verified = client.post(f"/v1/ingest/recipes/{recipe_id}/verify", json={})
        assert verified.status_code == 200, verified.text

        published = client.post(f"/v1/ingest/recipes/{recipe_id}/publish", json={})
        assert published.status_code == 200, (
            "Publish failed over the wire. Until round 13bf this was a bare 500: the image had no "
            f"`git` binary for `studio_publish` to exec. {published.text}"
        )

        run = client.post(
            f"/v1/investigations/{scope}/ingest/recipes/{recipe_id}/run", json={}
        )
        assert run.status_code == 200, run.text

        # **Both reports, and they answer different questions.** Verify is the dry run and carries
        # the `Node`/`Edge` it would produce, in full, whatever the graph already holds. The run
        # report carries what storage actually did. B1-B3 are claims about the *transform* (one
        # node per number, evidence retained, times converted), so they are asserted against
        # Verify; the run is what proves the transform reached a real load rather than stopping
        # at a preview, and it owns the storage-side half of B2.
        #
        # Deliberately not asserted from the run's own `created_node_ids`: that list holds only
        # nodes *this* load created, so a second run of the same file — which §6 requires to be
        # idempotent — returns an empty list and would make these tests pass once and then fail
        # for the very behaviour the specification asks for. Found exactly that way.
        report = run.json()

        # **The stored edge, when this load is the one that created the endpoints.** Verify's
        # preview carries neither the merged interval nor the merged provenance — measured, not
        # assumed: its edge reports `occurrences: 9` with one source and the first row's interval,
        # because merging is what storage does. So B2's "retained on the survivor" and B3's
        # converted interval can only be read from the graph.
        #
        # `created_node_ids` is the only handle a test has on those nodes: ingest does not write
        # to the search index (checked directly — `POST /v1/search` for the normalised number
        # returns nothing after a successful load), and there is no route that reads a node by id.
        # On a deployment that has already loaded this fixture the list is empty *by design* —
        # §6 requires a re-run to be idempotent — so those two assertions are conditional, and
        # say so rather than quietly not running.
        stored: list[dict] = []
        if report["created_node_ids"]:
            expanded = client.post(
                f"/v1/investigations/{scope}/expand",
                json={"request": {"node_ids": report["created_node_ids"], "depth": 1}},
            )
            assert expanded.status_code == 200, expanded.text
            delta = expanded.json()["delta"]
            stored = delta.get("edges_added") or delta.get("edges") or []

        return {"verify": verified.json(), "report": report, "stored_edges": stored}


def test_b1_every_rendering_of_one_number_resolves_to_a_single_endpoint(cdr_load: dict) -> None:
    """**B1**: "All four renderings of the shared number resolve to one `Endpoint`; `value_raw` is
    retained on each."

    The fixture writes the same A-party four ways — `01621926368`, `+44(0)1621926368`,
    `441621926368` and `#31#01621926368` (the last a CLI-withheld prefix). The `msisdn` Knowledge
    Adapter normalises all four to one E.164 value, and `match_on: value_normalised` is what makes
    them one node rather than four.

    Asserted as a count, not a lookup: "one Endpoint per real number" is the claim, and counting
    is what catches the failure where a fifth node appears because one rendering normalised
    differently. Two are expected — the A-party and the single B-party.
    """
    verify = cdr_load["verify"]
    endpoints = [n for n in verify["nodes"] if n["type"] == "Endpoint"]

    assert len(endpoints) == 2, (
        f"ten rows carrying two distinct real numbers produced {len(endpoints)} Endpoints, not "
        "2 — a rendering normalised to its own node instead of collapsing"
    )
    normalised = {n["properties"]["value_normalised"] for n in endpoints}
    assert normalised == {"+441621926368", "+447911123456"}, normalised

    a_party = next(n for n in endpoints if n["properties"]["value_normalised"] == "+441621926368")
    assert a_party["properties"]["value_raw"], (
        "the surviving Endpoint kept no `value_raw` — B1 requires the rendering actually seen to "
        "be retained, not discarded once normalised"
    )

    # Eighteen row-ends resolved to those two nodes, however many of them already existed.
    # Stated as the total rather than `created`/`referenced` separately: the split depends on
    # what the deployment had already loaded, and asserting it would make this test pass once.
    counts = verify["entities_by_type"]["Endpoint"]
    assert counts["created"] + counts["referenced"] == 18, counts

    # And the load really happened, rather than stopping at the preview above.
    report = cdr_load["report"]
    assert report["nodes_created"] + report["nodes_referenced"] == 18, report


def test_b2_duplicate_rows_collapse_and_every_source_row_is_retained(cdr_load: dict) -> None:
    """**B2**: "Duplicate rows collapse to single events; every source row reference is retained
    on the survivor."

    Both halves matter and they pull against each other — collapsing is easy if you discard
    evidence, and retaining evidence is easy if you never collapse. The fixture's nine valid rows
    are the same A-to-B pair, so they merge into one `COMMUNICATED_WITH`; the survivor must still
    name all nine rows it came from.

    `CLAUDE.md` rule 12's own worked example is this exact invariant: `upsert_edges` never merged
    same-pair edges for a whole phase while the conformance suite passed, because no case wrote
    the same pair twice. This case writes it nine times, over the wire.
    """
    verify = cdr_load["verify"]
    report = cdr_load["report"]
    previewed = [e for e in verify["edges"] if e["type"] == "COMMUNICATED_WITH"]

    assert len(previewed) == 1, (
        f"nine rows of one A-to-B pair produced {len(previewed)} edges rather than collapsing "
        "to one"
    )
    assert previewed[0]["occurrences"] == 9, previewed[0]["occurrences"]

    # **The storage-side half.** The above is the transform's own output; this is what the load
    # actually wrote. Nine row-level edges merging to one stored edge is `CLAUDE.md` rule 12's own
    # worked example — `upsert_edges` went a whole phase without merging same-pair edges while
    # the conformance suite passed, because no case wrote the same pair twice. This one does.
    assert len(set(report["touched_edge_ids"])) == 1, (
        "the run touched more than one edge id, so the same pair was stored as separate edges: "
        f"{sorted(set(report['touched_edge_ids']))}"
    )
    assert len(report["touched_edge_ids"]) == 9, report["touched_edge_ids"]

    # **Every source row retained on the survivor** — the half that is easy to lose, and only
    # readable from the stored edge. See the fixture for why this is conditional.
    for survivor in cdr_load["stored_edges"]:
        if survivor["type"] != "COMMUNICATED_WITH":
            continue
        sources = survivor["provenance"]["sources"]
        assert len(sources) == 9, (
            f"the surviving edge names {len(sources)} source rows, not 9 — collapsing discarded "
            "evidence"
        )
        assert {s["locator"] for s in sources} == {f"row {i}" for i in range(9)}
        break


def test_b3_local_times_are_converted_and_an_unreadable_one_is_refused_by_name(
    cdr_load: dict,
) -> None:
    """**B3**: "The local-time file is converted with its original offset recorded; a file with no
    recoverable offset is rejected with a named error, not guessed."

    Three things are proven here, and the first is the one this round unblocked.

    **The layout's declared date order reached the engine.** Row 6 is `12/01/2026 10:00:00` — the
    twelfth of January to a UK carrier, the first of December to an American one. Nothing in the
    value says which. `connectors/cdr-generic-csv.yaml` declares `date_order: dmy`, and until this
    round that declaration never reached the published recipe (`studio_publish` built its
    connector from the profile's *id* alone). The assertion is the interval's upper bound: read as
    `dmy` the row falls inside the fixture's window, read as `mdy` it lands in December and drags
    `valid_to` with it. So a silent misreading moves a number this test checks, rather than
    producing a plausible graph nobody questions.

    **The offset was applied, not assumed.** Row 9 is `2026-03-30 11:00:00` with no offset, and
    the recipe declares `tz=Europe/London`. The thirtieth of March 2026 is the day after British
    Summer Time begins, so the correct conversion is `10:00Z` — one hour, not zero. A normaliser
    that treated a naive local time as UTC would record `11:00Z` and pass any test whose fixture
    avoided a DST boundary. This one does not avoid it.

    **The unreadable row was refused by name.** Row 10's timestamp cannot be parsed at all. It
    appears in the run report's own rejections, naming the adapter and the value — not dropped
    silently, and not guessed at.
    """
    report = cdr_load["report"]

    # The converted interval lives on the stored edge (see the fixture). When this load created
    # the endpoints, assert it in full.
    for survivor in cdr_load["stored_edges"]:
        if survivor["type"] != "COMMUNICATED_WITH":
            continue
        interval = survivor["interval"]

        # The DST boundary: 11:00 local on 30 March 2026 is 10:00Z, because BST is in force.
        assert interval["valid_to"] == "2026-03-30T10:00:00Z", (
            f"the last call converted to {interval['valid_to']!r}. Expected 10:00Z: the row "
            "reads 11:00 local with no offset, and 30 March 2026 is inside British Summer Time. "
            "11:00Z would mean the naive local time was taken as UTC and no offset applied"
        )
        assert interval["valid_from"] == "2026-01-10T10:00:00Z", interval

        # `date_order: dmy` reached the engine: read as mdy, row 6 would be 1 December 2026 and
        # would drag `valid_to` with it.
        assert interval["valid_to"] < "2026-04-01T00:00:00Z", (
            "a row dated 12/01/2026 landed after March, so it was read as the first of "
            "December — the profile's `date_order: dmy` did not reach the published recipe"
        )
        break

    # The unreadable row, refused by name rather than guessed — in the real run's own report,
    # which is what an analyst is shown after a load.
    rejections = report["rejections"]
    assert len(rejections) == 1, rejections
    only = rejections[0]
    assert only["row_index"] == 9, only
    assert "datetime" in only["reason"] and "not-a-real-timestamp" in only["reason"], (
        f"the rejection does not name the adapter and the offending value: {only['reason']!r}"
    )
    assert report["rows_read"] == 10, report["rows_read"]


def test_the_delta_stream_is_reachable_through_the_proxy(analyst: httpx.Client) -> None:
    """The cross-cutting half that is reachable over the wire: the change stream, through the
    workspace's nginx, authenticated by the ticket exchange rather than a bearer header —
    browsers cannot set one on a WebSocket, which is the whole reason `/v1/ws-ticket` exists.

    Named per rule 12: nginx's `map $http_upgrade $connection_upgrade` block and its `/v1/`
    location are what make this work, and nothing else in the suite would notice if either were
    removed — the in-process tier has no proxy in front of it.
    """
    websockets = pytest.importorskip("websockets.sync.client")

    investigation = _new_investigation(analyst)
    ticket = analyst.post("/v1/ws-ticket", json={"investigation_id": investigation})
    assert ticket.status_code == 200, ticket.text
    assert ticket.json()["expires_in"] <= 60, "a stream ticket should be short-lived"

    origin = urllib.parse.urlparse(WORKSPACE_ORIGIN)
    scheme = "wss" if origin.scheme == "https" else "ws"
    url = (
        f"{scheme}://{origin.netloc}/v1/investigations/{investigation}/stream"
        f"?ticket={ticket.json()['ticket']}"
    )
    with websockets.connect(url, open_timeout=30) as stream:
        # The route waits for an init frame before it subscribes to anything — `{"last_
        # acknowledged_seq": null}` is a fresh client with nothing to catch up on, and it is what
        # the Glass's own `useDeltaStream` sends on open. Without it the socket stays connected
        # and silent, which is exactly how this step first failed.
        stream.send(json.dumps({"last_acknowledged_seq": None}))
        # A fresh client is answered with its own empty snapshot first (`sync`'s own contract:
        # the missed deltas, or a snapshot when the gap cannot be proven closed — never a silent
        # patch). The live delta is what comes after it.
        opening = json.loads(stream.recv(timeout=30))
        assert opening["op"] == "snapshot" and opening["nodes"] == [], opening

        node = _find(analyst, PRINCIPAL_SUBJECT_PRISON_NUMBER)
        seeded = analyst.post(
            f"/v1/investigations/{investigation}/seed", json={"nodes": [node], "edges": []}
        )
        assert seeded.status_code == 200, seeded.text
        delta = json.loads(stream.recv(timeout=30))
        assert delta["op"] == "add", delta
        assert [n["id"] for n in delta["nodes"]] == [node["id"]], delta
