"""Step 4's stack runner (`process/lanes/platform/v052-measure/step4_stack.py`), held offline to
what it claims before it runs on a leased stack: the subjects as rules granted them, the poc
manifest's own limits, nothing bound beyond the host's loopback, no token or password on a command
line, each token in the command's environment alone, and the preflight refusing a run whose grants
are not what is measured. Its live red and green (a subject with no grant refused) are on a small
leased stack, recorded in `process/lanes/platform/v052-measure/`."""

from __future__ import annotations

import importlib.util
import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
import yaml

_PATH = Path(__file__).resolve().parents[1] / "process/lanes/platform/v052-measure/step4_stack.py"
_SPEC = importlib.util.spec_from_file_location("step4_stack", _PATH)
assert _SPEC and _SPEC.loader
step4 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(step4)

_MANIFEST = (
    Path(__file__).resolve().parents[2] / "OspreyFlow_Core/harness/cloud_platform/poc_manifest.yaml"
)


def test_the_subjects_are_the_ones_rules_granted() -> None:
    """Rules' grants on stack d (14 November 2026): a control per R-owning unit, SECRET with P, C
    and R in its own unit; m10-part OFFICIAL-SENSITIVE without R in unit-records; m10-measure
    OFFICIAL-SENSITIVE in unit-intel; and a probe granted nothing."""
    by_name = {s["username"]: s for s in step4.SUBJECTS}
    controls = sorted(n for n, s in by_name.items() if s["use"] == "control")
    assert controls == [
        "m10-cleared-unit-border", "m10-cleared-unit-covert",
        "m10-cleared-unit-fiu", "m10-cleared-unit-intel-covert",
    ]  # fmt: skip
    for name in controls:
        s = by_name[name]
        assert (s["clearance"], s["codes"]) == ("SECRET", ["P", "C", "R"])
        assert s["org_unit"] == name.removeprefix("m10-cleared-")
    assert (by_name["m10-part"]["clearance"], by_name["m10-part"]["org_unit"]) == (
        "OFFICIAL-SENSITIVE", "unit-records")  # fmt: skip
    assert "R" not in by_name["m10-part"]["codes"]
    assert by_name["m10-measure"]["org_unit"] == "unit-intel"
    assert step4.PROBE["username"] not in by_name


def test_each_subject_s_claims_are_the_attributes_the_realm_maps() -> None:
    from harness.realm import PRINCIPAL_CLAIMS

    users = {u["username"]: u for u in step4.realm_users()}
    assert set(users) == {*(s["username"] for s in step4.SUBJECTS), step4.PROBE["username"]}
    claims = {name for name, _many in PRINCIPAL_CLAIMS}
    for user in users.values():
        assert set(user["attributes"]) == claims and user["enabled"]
        assert "credentials" not in user, "no password: tokens are minted by exchange alone"
    assert users["m10-cleared-unit-fiu"]["attributes"]["receivable_handling_codes"] == [
        "P",
        "C",
        "R",
    ]


@pytest.mark.parametrize("workload", ["api", "worker"])
def test_the_conduit_and_worker_run_at_the_poc_manifest_s_own_limits(workload: str) -> None:
    limits = yaml.safe_load(_MANIFEST.read_text(encoding="utf-8"))["workloads"][workload]["limits"]
    argv = step4.service_argv("r1", "n", "img", workload, {}, ["x"])
    memory = str(limits["memory"]).replace("Gi", "g").replace("Mi", "m")
    assert f"--cpus={limits['cpu']}" in argv and f"--memory={memory}" in argv
    assert f"--memory-swap={memory}" in argv, "no swap beyond the limit"


def test_nothing_is_bound_beyond_the_host_s_loopback() -> None:
    conduit = step4.conduit_command(8123)
    assert conduit[conduit.index("--host") + 1] == "127.0.0.1"
    keycloak = step4.keycloak_argv("r1", "n", 8124)
    assert "--http-host=127.0.0.1" in keycloak and not any("-p" == a for a in keycloak)


def test_no_value_reaches_a_command_line_and_every_container_carries_the_run_s_label() -> None:
    secret = "s3cr3t-value"
    environment = {"POSTGRES_PASSWORD": secret, "ARCADEDB_ROOT_PASSWORD": secret,
                   "OSPREY_MEASURE_TOKEN": secret, "HOME": "/root"}  # fmt: skip
    argvs = [
        step4.service_argv("run-7", "n", "img", "api", environment, step4.conduit_command(1)),
        step4.service_argv("run-7", "n", "img", "worker", environment, step4.WORKER_COMMAND),
        step4.keycloak_argv("run-7", "n", 1),
    ]
    for argv in argvs:
        assert not any(secret in a for a in argv), argv
        assert "osprey.run=run-7" in argv and "osprey.lane=" + step4.LANE in argv
    api = argvs[0]
    assert api[api.index("POSTGRES_PASSWORD") - 1] == "-e", "passed by name"
    assert "OSPREY_MEASURE_TOKEN" not in api and "HOME" not in api


def test_the_command_is_given_each_use_s_token() -> None:
    tokens = {s["username"]: f"tok-{s['username']}" for s in step4.SUBJECTS}
    env = step4.measure_environment(tokens, "http://127.0.0.1:1", "case-9")
    assert env["OSPREY_MEASURE_TOKEN"] == "tok-m10-measure"
    assert env["OSPREY_MEASURE_PART_TOKEN"] == "tok-m10-part"
    assert json.loads(env["OSPREY_MEASURE_CONTROLS"]) == {
        n: f"tok-{n}" for n in tokens if n.startswith("m10-cleared-")
    }
    assert env["OSPREY_MEASURE_CASE"] == "case-9"


class _Case(BaseHTTPRequestHandler):
    allowed: dict[str, int] = {}

    def do_GET(self) -> None:  # noqa: N802 - http.server's name
        token = self.headers.get("Authorization", "").removeprefix("Bearer ")
        self.send_response(self.allowed.get(token, 404))
        self.end_headers()

    def log_message(self, *args: Any) -> None:
        pass


@pytest.fixture
def conduit() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Case)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


def test_the_preflight_passes_a_granted_measure_and_a_refused_probe(conduit: str) -> None:
    _Case.allowed = {"measure": 200}
    assert step4.preflight(conduit, "c", "measure", "probe") == ""


@pytest.mark.parametrize(
    ("allowed", "said"),
    [
        ({}, "m10-measure is not granted the case"),  # the red: no grant on the stack yet
        ({"measure": 200, "probe": 200}, "a subject granted nothing read the case"),
        ({"measure": 200, "probe": 500}, "not a refusal"),
    ],
)
def test_the_preflight_stops_a_run_whose_grants_are_not_what_is_measured(
    conduit: str, allowed: dict[str, int], said: str
) -> None:
    _Case.allowed = allowed
    assert said in step4.preflight(conduit, "c", "measure", "probe")


def test_the_realm_is_the_deployment_s_own_with_step_4_s_subjects_alone() -> None:
    from harness.realm import CONDUIT_CLIENT_ID, PRINCIPAL_CLAIMS

    realm = step4.realm_document()
    conduit = next(c for c in realm["clients"] if c["clientId"] == CONDUIT_CLIENT_ID)
    mapped = {m["config"].get("claim.name") for m in conduit["protocolMappers"]}
    assert {name for name, _many in PRINCIPAL_CLAIMS} <= mapped
    assert any(m["protocolMapper"] == "oidc-audience-mapper" for m in conduit["protocolMappers"])
    assert [u["username"] for u in realm["users"]] == [u["username"] for u in step4.realm_users()]
    assert "secret" not in conduit, "the client's secret is set after import, never in the document"
