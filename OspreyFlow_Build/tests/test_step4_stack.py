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
    """Rules' grants on stack d (14 November 2026, lane/rules-m10-subjects): a case is opened only
    to its own unit (`investigations.py`), so a control per case unit, SECRET with P, C and R in its
    own unit (the leak cases use unit-intel's; a never-join case its partner case's unit), ten in
    all; m10-part OFFICIAL-SENSITIVE without R in unit-intel, the measured case's unit; m10-measure
    OFFICIAL-SENSITIVE in unit-intel; and a probe granted nothing."""
    by_name = {s["username"]: s for s in step4.SUBJECTS}
    controls = sorted(n for n, s in by_name.items() if s["use"] == "control")
    assert controls == [
        f"m10-cleared-{unit}"
        for unit in (
            "unit-border", "unit-comms", "unit-covert", "unit-custody", "unit-economic",
            "unit-fiu", "unit-intel", "unit-intel-covert", "unit-investigations", "unit-records",
        )
    ]  # fmt: skip
    for name in controls:
        s = by_name[name]
        assert (s["clearance"], s["codes"]) == ("SECRET", ["P", "C", "R"])
        assert s["org_unit"] == name.removeprefix("m10-cleared-")
    assert (by_name["m10-part"]["clearance"], by_name["m10-part"]["org_unit"]) == (
        "OFFICIAL-SENSITIVE", "unit-intel")  # fmt: skip
    assert by_name["m10-part"]["codes"] == ["P", "C"]
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


def test_the_preflight_passes_a_granted_measure_and_part_and_a_refused_probe(conduit: str) -> None:
    _Case.allowed = {"measure": 200, "part": 200}
    assert step4.preflight(conduit, "c", "measure", "probe", part_token="part") == ""


@pytest.mark.parametrize(
    ("allowed", "said"),
    [
        ({}, "m10-measure is not granted the case"),  # the red: no grant on the stack yet
        ({"measure": 200, "part": 200, "probe": 200}, "a subject granted nothing read the case"),
        ({"measure": 200, "part": 200, "probe": 500}, "not a refusal"),
        # M10's first measured run on d (14 November): m10-part outside the case's unit got 404,
        # and every leak case proved nothing. The run stops before it measures instead.
        ({"measure": 200}, "m10-part cannot open the case (HTTP 404)"),
    ],
)
def test_the_preflight_stops_a_run_whose_grants_are_not_what_is_measured(
    conduit: str, allowed: dict[str, int], said: str
) -> None:
    _Case.allowed = allowed
    assert said in step4.preflight(conduit, "c", "measure", "probe", part_token="part")


def test_the_realm_is_the_deployment_s_own_with_step_4_s_subjects_alone() -> None:
    from harness.realm import CONDUIT_CLIENT_ID, PRINCIPAL_CLAIMS

    realm = step4.realm_document()
    conduit = next(c for c in realm["clients"] if c["clientId"] == CONDUIT_CLIENT_ID)
    mapped = {m["config"].get("claim.name") for m in conduit["protocolMappers"]}
    assert {name for name, _many in PRINCIPAL_CLAIMS} <= mapped
    assert any(m["protocolMapper"] == "oidc-audience-mapper" for m in conduit["protocolMappers"])
    assert [u["username"] for u in realm["users"]] == [u["username"] for u in step4.realm_users()]
    assert "secret" not in conduit, "the client's secret is set after import, never in the document"


def test_each_subject_s_principal_id_is_its_name_as_the_grants_name_it() -> None:
    """The Conduit's principal id is the token's `sub`, Keycloak's user id: B's cases are granted
    to the subjects' names, so each user's id is its name, never one Keycloak makes."""
    for user in step4.realm_users():
        assert user["id"] == user["username"]


def test_a_run_tag_that_is_a_folder_gives_names_docker_takes_and_keeps_its_label_whole() -> None:
    """stack_lease.sh gives OSPREY_RUN_TAG as the run's folder (found on stack f, 14 November: the
    first proof's docker run refused its name); the reaper matches the label, so it stays whole."""
    import re

    run = "/root/osprey-runs/platform.meta/runs/20261114T091020Z-0f15af13"
    name = f"osprey-step4-idp-{step4.slug(run)}"
    assert re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", name)
    assert step4.slug(run) == "20261114t091020z-0f15af13"
    assert f"osprey.run={run}" in step4.keycloak_argv(run, name, 1)


def test_a_failed_start_s_log_is_shown_with_every_secret_masked() -> None:
    env = {"POSTGRES_PASSWORD": "pg-secret-1", "KC_BOOTSTRAP_ADMIN_PASSWORD": "kc-secret-2",
           "OSPREY_MEASURE_TOKEN": "eyJ-token-3", "POSTGRES_PORT": "55438"}  # fmt: skip
    text = "auth failed for pg-secret-1; admin kc-secret-2; bearer eyJ-token-3 on 55438"
    shown = step4.mask(text, step4.secret_values(env))
    assert "secret-1" not in shown and "secret-2" not in shown and "token-3" not in shown
    assert "55438" in shown, "a port is no secret here; the runner prints no port itself"


def test_the_conduit_has_the_poc_s_own_settings_less_the_named_ones_with_the_stack_s() -> None:
    """The third proof on stack f: given none of the poc's settings, the Conduit opened DuckDB in a
    folder it could not write and never started. It takes the poc render's own environment, less
    `DROPPED` by name, each kept key the poc's unless the stack's replaces it."""
    poc = step4.poc_environment()
    lease = {
        "CLICKHOUSE_HTTP_PORT": "18128",
        "OPENSEARCH_PORT": "19205",
        "MINIO_ENDPOINT": "localhost:9010",
    }
    env = step4.conduit_environment(poc, lease)
    assert set(poc) - set(env) == set(step4.DROPPED) & set(poc), "a poc setting lost unnamed"
    assert env["OSPREY_ANALYTICS_ENGINE"] == "clickhouse" == poc["OSPREY_ANALYTICS_ENGINE"]
    assert env["OSPREY_PROFILE"] == "cloud-platform" and env["OSPREY_DATA_ROOT"].startswith(
        step4.DATA_ROOT
    )
    assert {env[h] for h in ("ARCADEDB_HOST", "CLICKHOUSE_HOST", "OPENSEARCH_HOST")} == {
        "127.0.0.1"
    }
    assert env["CLICKHOUSE_HTTP_PORT"] == "18128" and env["OPENSEARCH_SIGNING"] == "none"
    assert env["OSPREY_HIGHEST_MARKING"] == "SECRET"
    assert not any("microsoftonline" in v for v in env.values()), "nothing of Entra's"


def test_the_conduit_s_settings_are_passed_by_name_and_its_directories_writable() -> None:
    argv = step4.service_argv("r", "n", "img", "api", {"OSPREY_DATA_ROOT": "/var/lib/osprey/data"},
                              ["x"], settings=["OSPREY_DATA_ROOT"])  # fmt: skip
    assert argv[argv.index("OSPREY_DATA_ROOT") - 1] == "-e"
    assert not any("=/var/lib/osprey/data" in a for a in argv)
    assert any(a.startswith(f"{step4.DATA_ROOT}:rw,uid=10001") for a in argv)


def test_the_conduit_reads_the_poc_s_own_files_where_the_chart_mounts_them() -> None:
    """The fourth proof on stack f: the Conduit read osprey.yaml at start and found none. Each
    workload's files are the render's, mounted read-only at the chart's own paths."""
    values = step4.poc_values()
    files = step4.workload_files(values, "api")
    assert [(k, at) for k, at, _t in files] == [("osprey.yaml", "/app/osprey.yaml")]
    assert files[0][2] == values["files"]["osprey.yaml"]
    argv = step4.service_argv(
        "r", "n", "img", "api", {}, ["x"], mounts=[("/tmp/f/osprey.yaml", "/app/osprey.yaml")]
    )
    assert "/tmp/f/osprey.yaml:/app/osprey.yaml:ro" in argv
    for writable in step4.WRITABLE:
        assert any(a.startswith(f"{writable}:rw,uid=10001") for a in argv)


def test_each_workload_s_own_plain_settings_are_the_render_s_and_none_from_a_secret() -> None:
    values = step4.poc_values()
    api = step4.workload_settings(values, "api")
    assert api["OSPREY_MAP_SETTINGS_DIR"].startswith("/run/osprey")
    assert "POSTGRES_PASSWORD" not in api and "POSTGRES_HOST" not in api, (
        "the stack's, from the lease"
    )
    assert all(v for v in api.values()), "no empty setting given"


@pytest.mark.parametrize("dockerfile", ["services/api/Dockerfile", "services/worker/Dockerfile"])
def test_each_image_builds_from_core_whatever_directory_the_runner_starts_in(
    dockerfile: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rules' first run on d started the runner at the repository root, where there is no
    `services/`, and docker refused the build; `-f` is read from the process's directory."""
    monkeypatch.chdir(tmp_path)
    argv = step4.build_argv(dockerfile, "ospreyflow/api:step4-x")
    given = Path(argv[argv.index("-f") + 1])
    assert given.is_absolute() and given.is_file(), given
    assert given == step4.CORE / dockerfile
    assert argv[0] == "build" and argv[-1] == str(step4.CORE)


# --- the tokens outlive the run (step 4's rerun on d, 14 November 2026) ---------------------------


def _jwt(life: int, subject: str = "m10-measure") -> str:
    """A token as Keycloak shapes it: header.payload.signature, base64url, `iat` and `exp`."""
    import base64

    def part(value: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")

    payload = {"sub": subject, "iat": 1_763_000_000, "exp": 1_763_000_000 + life}
    return f"{part({'alg': 'RS256'})}.{part(payload)}.c2ln"


def test_the_realm_grants_tokens_a_life_longer_than_the_run() -> None:
    """The deployment's rendered realm sets no `accessTokenLifespan`, so Keycloak's 300 s applied
    and every send after about five minutes was refused."""
    realm = step4.realm_document()
    assert realm.get("accessTokenLifespan", 300) >= step4.TOKEN_LIFE_NEEDED_S, realm.get(
        "accessTokenLifespan"
    )
    for client in realm.get("clients", []):
        own = (client.get("attributes") or {}).get("access.token.lifespan")
        assert own is None or int(own) >= step4.TOKEN_LIFE_NEEDED_S, client["clientId"]


def test_a_token_minted_shorter_than_the_run_stops_the_run_before_it_measures() -> None:
    """The IdP's own answer is what counts, not the realm we asked for: a fake IdP's 300 s token
    is refused by name, as the run would otherwise die mid-measure."""
    tokens = {"m10-measure": _jwt(4 * 3600), "m10-part": _jwt(300, "m10-part")}
    said = step4.short_lived(tokens)
    assert said is not None and "m10-part" in said and "300" in said, said
    assert "m10-measure" not in said
    assert step4.short_lived({"m10-measure": _jwt(4 * 3600)}) is None
