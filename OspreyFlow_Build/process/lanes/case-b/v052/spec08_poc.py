"""Spec 08's acceptance scenarios on the poc shape (ROUTE_052 step 6, BRIEF_v052): the closing-pass proof,
`tests/scenarios/test_phase8_exit_over_the_wire.py`, run **unchanged** against the kind deployment, as a
pytest plugin that

- signs in at the Entra stand-in as the Glass does (authorization code with PKCE, the stand-in's own
  signature) in place of the module's Keycloak login, so every token is one Entra would have issued;
- skips each case that cannot run on this shape, with its reason (`DISPOSITIONS`);
- stops the run when the module has a case with no disposition, or a disposition names a case that is
  gone: a case nobody placed is never run or skipped unremarked.

**Why most rows are skipped: no seed path on poc.** The scenarios rest on the `hmp`, `fixture-corp` and
`scenarios` seed datasets, and `harness.apply`'s seed is compose-only (`harness/apply.py` `seed()`: it
stops the compose `api`, seeds, starts it). A cloud-platform deployment has no way to take them, so the
rows built on them cannot be performed there. What runs is what an analyst can do from an empty case:
sign in, the ingest root and the Studio on the CDR fixture (B1-B3, uploaded through
`POST .../ingest/source-files`, the analyst's own door), the site grid (A1's first three), and B13-B14 on
the uploaded seizure record, the stream through the ingress (ticket, upgrade, snapshot) and A7's refusal of a
hostile field name: 14 of 29, each split from its seeded half. (B13-B14's fixture asked routes the Conduit had moved; fixed in c6c6044,
held by tests/scenarios/test_over_the_wire_routes_exist.py.)

    # on the kind cluster, after the install and under a lease (from OspreyFlow_Core), with r1_kind.sh's own
    # environment (its tools, its kubeconfig, the kind platform's folder): `r1_kind.sh py` hands its arguments to
    # r1_kind.py's argparse and cannot run this file
    bash ../OspreyFlow_Build/process/lanes/case-b/v052/spec08_live.sh [pytest arguments]
"""


from __future__ import annotations

import ast
import os
import secrets
import subprocess
import sys
import urllib.parse
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
BUILD = HERE.parents[3]
#: The module (overridable only so plants.py can run a planted copy of this file elsewhere).
MODULE = Path(os.environ.get("OSPREY_V052_SPEC08_MODULE") or BUILD / "tests" / "scenarios" / "test_phase8_exit_over_the_wire.py")

NO_SEED = "no seed path on poc: it rests on the hmp/fixture-corp/scenarios seed datasets, and harness.apply's seed is compose-only"

#: Every case of MODULE: None runs on poc; a string is why it cannot.
DISPOSITIONS: dict[str, str | None] = {
    "test_the_analysts_own_door_opens": None,
    "test_scenario_a_over_the_wire": NO_SEED,  # A2-A5, A8-A14 on the hmp seed
    "test_scenario_b_over_the_wire": NO_SEED,  # B4, B5, B9-B12, B19-B21 on the fixture-corp seed
    "test_the_ingest_folder_is_reachable_and_usable_through_the_studio": None,
    "test_what_an_analyst_ingests_an_analyst_can_find_and_open": None,
    "test_b1_every_rendering_of_one_number_resolves_to_a_single_endpoint": None,
    "test_b2_duplicate_rows_collapse_and_every_source_row_is_retained": None,
    "test_b3_local_times_are_converted_and_an_unreadable_one_is_refused_by_name": None,
    "test_b7_a_shared_messaging_handle_is_common_to_the_second_cohort": NO_SEED,
    "test_b8_the_handle_is_linked_to_the_shared_endpoint_asserted_at_one": NO_SEED,
    "test_b15_both_sims_link_to_one_device_in_one_traversal": NO_SEED,
    "test_b17_the_devices_location_events_are_reachable_and_windowed": NO_SEED,
    "test_b18_the_sightings_form_an_ordered_track": NO_SEED,
    "test_b16_both_event_sets_are_retrievable_for_a_shared_axis": NO_SEED,
    # B13/B14 assert nothing seeded: the ingest of the uploaded seizure record makes their SIM and referents.
    "test_b13_an_ingest_fires_an_alert_naming_the_identifier_document_and_rule": None,
    "test_b13_a_hotlist_alone_fires_nothing_until_the_ingest_arrives": None,
    "test_b14_an_alert_opens_at_its_address_in_its_own_case_with_its_entities": None,
    "test_a1_a_site_grid_is_placed_and_its_cells_become_location_entities": None,
    "test_a1_redrawing_the_grid_does_not_duplicate_its_cells": None,
    "test_a1_a_cells_geometry_reference_resolves_to_its_centroid": None,
    "test_a1_incidents_geocode_into_the_cells_that_contain_them": NO_SEED,  # the hmp incidents
    "test_a7_reports_can_be_filtered_to_one_item_category": NO_SEED,
    "test_a7_an_unknown_field_name_is_refused_rather_than_ignored": None,  # the boundary's refusal, on the run's own case
    "test_a7_the_events_table_survives_a_refused_field_name": NO_SEED,  # it counts the hmp events after
    "test_a15_a_consult_originator_item_blocks_the_export_by_name_then_proceeds_with_a_justification": NO_SEED,
    "test_a6_the_reports_for_the_selection_open_with_a_source_locator_each": NO_SEED,
    "test_b6_the_shared_endpoints_messages_open_with_the_entity_spans_in_place": NO_SEED,
    "test_the_stream_opens_through_the_proxy_with_a_ticket": None,  # ticket, upgrade and snapshot: the only test of the poc ingress's WebSocket
    "test_the_delta_stream_is_reachable_through_the_proxy": NO_SEED,  # it seeds an hmp subject into the stream
}


class Undisposed(Exception):
    """The module and DISPOSITIONS disagree: the run stops before any case runs."""


def cases_in(source: str) -> list[str]:
    return [n.name for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]


def check_cases(cases: Iterable[str]) -> None:
    cases = list(cases)
    unknown = sorted(set(cases) - set(DISPOSITIONS))
    gone = sorted(set(DISPOSITIONS) - set(cases))
    if unknown or gone:
        raise Undisposed("spec 08 on poc: " + "; ".join(
            [f"a case with no disposition: {c}" for c in unknown] + [f"a disposition for no case: {c}" for c in gone]))


def mark(items: list[Any], *, mint: Callable[[], str]) -> None:
    """The plugin's work on the collected items: the dispositions held both ways, the skips, the sign-in."""
    import pytest

    ours = [i for i in items if Path(str(i.path)).name == MODULE.name]
    if not ours:
        return
    check_cases(cases_in(MODULE.read_text(encoding="utf-8")))  # the module as written, whatever the selection
    unplaced = sorted({getattr(i, "originalname", i.name) for i in ours} - set(DISPOSITIONS))
    if unplaced:
        raise Undisposed("spec 08 on poc: collected with no disposition: " + ", ".join(unplaced))
    for item in ours:
        reason = DISPOSITIONS[getattr(item, "originalname", item.name)]
        if reason is not None:
            item.add_marker(pytest.mark.skip(reason=f"not on poc: {reason}"))
    for module in {id(i.module): i.module for i in ours}.values():
        module._sign_in_as_the_demo_analyst = mint


def code_from_redirect(location: str, state: str) -> str:
    query = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)
    if query.get("state", [None])[0] != state:
        raise ValueError(f"the redirect's state is not the request's: {location}")
    code = query.get("code", [None])[0]
    if not code:
        raise ValueError(f"no code on the redirect: {location}")
    return code


# ---- the plugin's hooks (loaded by `-p spec08_poc`) ------------------------------------------------


def _mint_by_command() -> str:
    command = os.environ["OSPREY_V052_TOKEN_COMMAND"]
    return subprocess.run(command, shell=True, check=True, capture_output=True, text=True).stdout.strip()


def pytest_configure(config: Any) -> None:
    door_ip, host = os.environ.get("OSPREY_V052_DOOR_IP"), os.environ.get("OSPREY_V052_DOOR_HOST")
    if door_ip and host:  # the deployment's name resolved to the kind node, nothing else (r1_kind.door's way)
        import socket

        real = socket.getaddrinfo
        socket.getaddrinfo = lambda name, *a, **k: real(door_ip if name == host else name, *a, **k)  # type: ignore[assignment]


def pytest_collection_modifyitems(session: Any, config: Any, items: list[Any]) -> None:
    mark(items, mint=_mint_by_command)


# ---- the run on kind (under a lease) -------------------------------------------------------------

#: The Glass's sign-in, in two calls from the api pod (which resolves and trusts the stand-in): authorize
#: with PKCE, printing the redirect it answers with; the code is read here (`code_from_redirect`), then
#: exchanged at the token endpoint with the verifier. Needs platform's signing stand-in
#: (lane/platform-v052-standin, its /authorize and /token); R1's own stand-in on main only publishes keys.
_AUTHORIZE = r"""
import sys, httpx
tenant, client, api, redirect, state, challenge = sys.argv[1:7]
r = httpx.get(f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize", params={"client_id": client,
    "response_type": "code", "redirect_uri": redirect, "scope": f"openid profile api://{api}/access_as_user", "state": state,
    "nonce": state, "code_challenge": challenge, "code_challenge_method": "S256"}, follow_redirects=False, timeout=30)
print(r.headers.get("location") or f"no redirect: {r.status_code} {r.text[:300]}")
"""
_EXCHANGE = r"""
import sys, httpx
tenant, client, redirect, code, verifier = sys.argv[1:6]
t = httpx.post(f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token", data={"grant_type": "authorization_code",
    "client_id": client, "code": code, "redirect_uri": redirect, "code_verifier": verifier}, timeout=30)
print(t.json()["access_token"] if t.status_code == 200 else f"refused: {t.status_code} {t.text[:300]}")
"""


def _r1() -> Any:  # pragma: no cover - the live half
    sys.path.insert(0, str(HERE.parents[1] / "platform" / "gates"))
    import r1_kind

    return r1_kind


def token() -> str:  # pragma: no cover - the live half
    """The stand-in's own token, as the Glass gets it; `OSPREY_V052_TOKEN_BY=r1` takes r1_kind.token()'s
    instead (the driver's key, which the stand-in also publishes) for a run before the signing stand-in."""
    import base64
    import hashlib

    import yaml

    r1 = _r1()
    if os.environ.get("OSPREY_V052_TOKEN_BY") == "r1":
        return str(r1.token())
    claims = yaml.safe_load(r1.CONFIG.read_text())["cloud_platform"]["claims"]
    verifier, state = secrets.token_urlsafe(64), secrets.token_urlsafe(8)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    redirect = f"https://{r1.GLASS}/"

    def in_pod(code: str, *args: str) -> str:
        return r1.kubectl("-n", r1.NS, "exec", "deployment/api", "--", "/app/.venv/bin/python", "-c", code, *args).strip()

    location = in_pod(_AUTHORIZE, claims["tenant_id"], claims["client_id"], claims["api_client_id"], redirect, state, challenge)
    code = code_from_redirect(location, state)
    answer = in_pod(_EXCHANGE, claims["tenant_id"], claims["client_id"], redirect, code, verifier)
    if answer.startswith("refused:"):
        raise SystemExit(f"the stand-in refused the Glass's code: {answer}")
    return answer


def run(extra: list[str]) -> int:  # pragma: no cover - the live half, under a lease
    """A case for the run, the ingest fixtures uploaded into it through the analyst's own door, then the
    module under this plugin. Leaves the case (an install test's deployment is decommissioned after)."""
    import tempfile

    import yaml
    from scripts.seed_ingest_folder import write_cdr_fixture, write_seizure_fixture

    r1 = _r1()
    claims = yaml.safe_load(r1.CONFIG.read_text())["cloud_platform"]["claims"]
    c = r1.door()
    signed = {"Authorization": f"Bearer {token()}"}
    me = c.get("/v1/me", headers=signed)
    me.raise_for_status()
    roles = sorted({*me.json().get("roles", []), "analyst", "data_engineer"})
    c.put(f"/v1/admin/people/{claims['first_administrators'][0]}/roles", headers=signed, json={"roles": roles}).raise_for_status()
    made = c.post("/v1/investigations", headers=signed, json={"name": "v0.5.2 spec 08 on poc", "new_dataset_name": f"spec08 {secrets.token_hex(3)}"})
    made.raise_for_status()
    case = made.json()["id"]
    with tempfile.TemporaryDirectory() as tmp:
        for write in (write_cdr_fixture, write_seizure_fixture):  # what running cases read: B1-B3's load, B13's
            path = write(Path(tmp))
            up = c.post(f"/v1/investigations/{case}/ingest/source-files", params={"name": path.name},
                        headers={**signed, "Content-Type": "text/csv"}, content=path.read_bytes())
            up.raise_for_status()
    ip = r1.sh("docker", "inspect", "-f", "{{.NetworkSettings.Networks.kind.IPAddress}}", "osprey-r1-control-plane").strip()
    bundle = r1.STATE / "door-bundle.pem"
    bundle.write_text(r1.bundle())
    env = {**os.environ, "OSPREY_TEST_OVER_THE_WIRE": "1", "OSPREY_LIVE_INVESTIGATION_ID": case,
           "OSPREY_WORKSPACE_ORIGIN": f"https://{r1.GLASS}", "OSPREY_V052_DOOR_IP": ip, "OSPREY_V052_DOOR_HOST": r1.GLASS,
           "SSL_CERT_FILE": str(bundle), "OSPREY_V052_TOKEN_COMMAND": f"{sys.executable} {Path(__file__)} token",
           "PYTHONPATH": os.pathsep.join([str(HERE), os.environ.get("PYTHONPATH", "")])}
    log = r1.record("spec08-poc")
    done = subprocess.run([sys.executable, "-m", "pytest", "-c", str(BUILD / "pytest.ini"), "-p", "no:cacheprovider", "-p", "spec08_poc",
                           "-rs", "-v", str(MODULE), *extra], env=env, capture_output=True, text=True, check=False)
    log.write_text(done.stdout + done.stderr)
    print(done.stdout[-4000:] + f"\n(record {log})")
    return done.returncode


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["token"]:
        print(token())
        return 0
    if args[:1] == ["run"]:
        return run(args[1:])
    if args[:1] == ["table"]:
        for case, reason in DISPOSITIONS.items():
            print(f"{'runs' if reason is None else 'skip'}  {case}" + ("" if reason is None else f"  ({reason})"))
        return 0
    print("usage: spec08_poc.py table | token | run [pytest arguments]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
