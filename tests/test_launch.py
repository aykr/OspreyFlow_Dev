"""`scripts/launch.py` — the one-screen launcher for the Glass, the Ingest Studio and the Admin
console.

**Seen on the running `local-lite` deployment, 29 September 2026.** Starting the product meant
knowing that three interfaces are three different things: the Glass is `localhost:8080` and asks
for a sign-in; the Ingest Studio is not an address at all but the "Ingest" tab inside the Glass;
and the admin console is the harness's own process on `localhost:7000`, which the workspace does
not serve (`localhost:8080/admin` answers with the Glass's sign-in page). Nothing put the three in
one place.

Each test below names the invariant it protects and would fail if it were violated (`CLAUDE.md`
rule 12). The fixture `deployment.env` has the shape `harness.apply` really writes — including the
demo analyst's password line — because a launcher tested only against an env file with nothing
secret in it cannot show that it never reads one (rule 15: plant the violation in the shape the
real call site receives).
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator, Sequence
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from harness.render import HARNESS_PORT
from scripts import launch

DEMO_PASSWORD = "correct-horse-battery-staple-9f31"
CLIENT_SECRET = "s3cr3t-client-abc123"

DEPLOYMENT_ENV = f"""\
OSPREY_PROFILE=local-lite
OSPREY_WORKSPACE_PORT=8080
OSPREY_API_PORT=8000
OSPREY_OIDC_CLIENT_SECRET={CLIENT_SECRET}
OSPREY_POSTGRES_PASSWORD=pg-secret-77
OSPREY_DEMO_ANALYST_PASSWORD={DEMO_PASSWORD}
"""


class FakeProber:
    """Answers per URL; records every URL it was asked about."""

    def __init__(self, answers: dict[str, int | None] | None = None) -> None:
        self.answers = answers or {}
        self.asked: list[str] = []

    def __call__(self, url: str) -> int | None:
        self.asked.append(url)
        return self.answers.get(url)


class FakeSpawner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, argv: Sequence[str], *, cwd: Path, wait: bool = False) -> None:
        self.calls.append(list(argv))


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    out = tmp_path / "deploy" / "generated" / "local-lite"
    out.mkdir(parents=True)
    (out / "deployment.env").write_text(DEPLOYMENT_ENV, encoding="utf-8")
    (out / "compose.yaml").write_text("name: osprey-local-lite\nservices: {}\n", encoding="utf-8")
    return tmp_path


def _launcher(
    repo: Path, prober: FakeProber | None = None, spawner: FakeSpawner | None = None
) -> launch.Launcher:
    return launch.Launcher(
        repo_root=repo,
        prober=prober or FakeProber(),
        spawner=spawner or FakeSpawner(),
        frontend_built=True,
    )


@pytest.fixture
def served(repo: Path) -> Iterator[tuple[str, launch.Launcher, FakeProber, FakeSpawner]]:
    prober, spawner = FakeProber(), FakeSpawner()
    launcher = _launcher(repo, prober, spawner)
    server: ThreadingHTTPServer = launch.make_server(launcher, port=0)
    port = server.server_address[1]
    launcher.bound_port = port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}", launcher, prober, spawner
    finally:
        server.shutdown()
        server.server_close()


def _request(
    url: str, *, method: str = "GET", headers: dict[str, str] | None = None
) -> tuple[int, str]:
    req = urllib.request.Request(url, method=method, headers=headers or {})  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf-8")


def test_the_launcher_offers_exactly_the_three_interfaces_by_their_own_names(repo: Path) -> None:
    names = [s.name for s in _launcher(repo).surfaces()]
    assert names == ["The Glass", "Ingest Studio", "Admin console"]


def test_the_glass_and_ingest_studio_use_the_deployments_own_workspace_port(
    repo: Path,
) -> None:
    """The port comes from the rendered `deployment.env` (`OSPREY_WORKSPACE_PORT`, overridable —
    Preflight once found 8000 held by an unrelated container), never a literal in the launcher."""
    env = repo / "deploy" / "generated" / "local-lite" / "deployment.env"
    env.write_text(
        env.read_text(encoding="utf-8").replace("WORKSPACE_PORT=8080", "WORKSPACE_PORT=9191"),
        encoding="utf-8",
    )
    by_name = {s.name: s for s in _launcher(repo).surfaces()}
    assert by_name["The Glass"].url == "http://localhost:9191/"
    assert by_name["Ingest Studio"].url == "http://localhost:9191/"


def test_the_admin_console_is_on_the_harness_port_never_the_workspace(repo: Path) -> None:
    """The defect the sibling runbook fix corrects: `localhost:<workspace>/admin` is the Glass."""
    admin = {s.name: s for s in _launcher(repo).surfaces()}["Admin console"]
    assert admin.url == f"http://localhost:{HARNESS_PORT}/"
    assert ":8080" not in admin.url


def test_the_ingest_studio_tile_says_where_it_is_because_it_has_no_address_of_its_own(
    repo: Path,
) -> None:
    studio = {s.name: s for s in _launcher(repo).surfaces()}["Ingest Studio"]
    assert "Ingest" in studio.hint
    assert "tab" in studio.hint.lower()


def test_no_secret_from_the_deployment_env_reaches_the_page_or_the_status(
    served: tuple[str, launch.Launcher, FakeProber, FakeSpawner],
) -> None:
    base, _, _, _ = served
    for path in ("/", "/status"):
        _, body = _request(base + path)
        for secret in (DEMO_PASSWORD, CLIENT_SECRET, "pg-secret-77"):
            assert secret not in body, f"{secret!r} leaked into GET {path}"


def test_the_launcher_reads_only_the_workspace_port_line_of_the_env_file(repo: Path) -> None:
    env = repo / "deploy" / "generated" / "local-lite" / "deployment.env"
    assert launch.read_workspace_port(env) == 8080
    env.write_text("OSPREY_DEMO_ANALYST_PASSWORD=x\n", encoding="utf-8")
    assert launch.read_workspace_port(env) == launch.DEFAULT_WORKSPACE_PORT


def test_the_launcher_never_probes_or_starts_anything_on_port_8000(
    served: tuple[str, launch.Launcher, FakeProber, FakeSpawner],
) -> None:
    """Port 8000 belongs to an unrelated container on this machine; the launcher's own status
    checks and start commands must not touch it."""
    base, launcher, prober, spawner = served
    _request(base + "/status")
    launcher.start("stack")
    launcher.start("admin")
    assert prober.asked, "the status check probed nothing"
    assert not any(":8000" in url for url in prober.asked)
    assert not any(":8000" in " ".join(call) for call in spawner.calls)


def test_status_reports_each_interface_up_only_when_it_answers(repo: Path) -> None:
    prober = FakeProber(
        {
            "http://localhost:8080/healthz": 200,
            f"http://localhost:{HARNESS_PORT}/": None,
        }
    )
    status = _launcher(repo, prober).status()
    assert status["The Glass"] == "up"
    assert status["Ingest Studio"] == "up"
    assert status["Admin console"] == "down"


def test_a_workspace_that_answers_while_the_conduit_does_not_is_starting_not_up(
    repo: Path,
) -> None:
    """`/healthz` is proxied to the Conduit; a 502 there with the workspace serving means the stack
    is half up — reporting that as `up` would send the analyst to a Glass that cannot sign in."""
    prober = FakeProber({"http://localhost:8080/healthz": 502, "http://localhost:8080/": 200})
    status = _launcher(repo, prober).status()
    assert status["The Glass"] == "starting"


def test_starting_the_stack_reuses_the_rendered_deployment_without_regenerating_it(
    repo: Path,
) -> None:
    spawner = FakeSpawner()
    _launcher(repo, spawner=spawner).start("stack")
    (argv,) = spawner.calls
    compose = repo / "deploy" / "generated" / "local-lite" / "compose.yaml"
    env = compose.parent / "deployment.env"
    assert argv[:2] == ["docker", "compose"]
    assert argv[argv.index("--env-file") + 1] == str(env), (
        "without --env-file the generated secrets are invisible to compose"
    )
    assert argv[argv.index("-f") + 1] == str(compose)
    assert argv[-3:] == ["up", "-d", "--wait"]
    assert "harness.apply" not in " ".join(argv), "a start must not regenerate or re-seed"


def test_with_no_rendered_deployment_the_stack_start_says_so_instead_of_guessing(
    tmp_path: Path,
) -> None:
    spawner = FakeSpawner()
    with pytest.raises(launch.NothingToStart) as err:
        _launcher(tmp_path, spawner=spawner).start("stack")
    assert "harness.apply" in str(err.value)
    assert spawner.calls == []


def test_starting_the_admin_console_runs_the_harness_module(repo: Path) -> None:
    spawner = FakeSpawner()
    _launcher(repo, spawner=spawner).start("admin")
    (argv,) = spawner.calls
    assert argv[1:] == ["-m", "harness"]


def test_an_unbuilt_admin_frontend_is_built_first_rather_than_served_blank(repo: Path) -> None:
    """Seen on this machine: `apps/harness/dist` did not exist, and `harness.webapp` then mounts
    nothing — the console would start and every page would 404."""
    spawner = FakeSpawner()
    launcher = launch.Launcher(
        repo_root=repo, prober=FakeProber(), spawner=spawner, frontend_built=False
    )
    launcher.start("admin")
    assert spawner.calls[0][0] == "npm"
    assert spawner.calls[0][-1] == "build"
    assert spawner.calls[1][1:] == ["-m", "harness"]


def test_a_start_request_without_the_session_token_is_refused_and_starts_nothing(
    served: tuple[str, launch.Launcher, FakeProber, FakeSpawner],
) -> None:
    """The launcher spawns processes; any web page open in the same browser could POST to a
    loopback port. The per-run token is what stops that."""
    base, _, _, spawner = served
    code, _ = _request(base + "/start/stack", method="POST")
    assert code == 403
    code, _ = _request(base + "/start/stack", method="POST", headers={"X-Launch-Token": "guess"})
    assert code == 403
    assert spawner.calls == []


def test_a_start_request_with_the_token_starts_only_a_known_target(
    served: tuple[str, launch.Launcher, FakeProber, FakeSpawner],
) -> None:
    base, launcher, _, spawner = served
    headers = {"X-Launch-Token": launcher.token}
    code, body = _request(base + "/start/admin", method="POST", headers=headers)
    assert code == 202, body
    code, _ = _request(base + "/start/rm-rf", method="POST", headers=headers)
    assert code == 404
    launcher.wait_idle()
    assert len(spawner.calls) == 1


def test_a_request_addressed_to_another_host_name_is_refused(
    served: tuple[str, launch.Launcher, FakeProber, FakeSpawner],
) -> None:
    """DNS rebinding: a hostile page can point its own name at 127.0.0.1 and read `/`, which
    carries the session token."""
    base, launcher, _, spawner = served
    code, _ = _request(base + "/", headers={"Host": "evil.example"})
    assert code == 403
    code, _ = _request(
        base + "/start/admin",
        method="POST",
        headers={"Host": "evil.example", "X-Launch-Token": launcher.token},
    )
    assert code == 403
    assert spawner.calls == []


def test_the_launcher_binds_loopback_only(repo: Path) -> None:
    server = launch.make_server(_launcher(repo), port=0)
    try:
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.server_close()


def test_the_page_shows_three_tiles_and_the_status_endpoint_is_json(
    served: tuple[str, launch.Launcher, FakeProber, FakeSpawner],
) -> None:
    base, _, _, _ = served
    _, page = _request(base + "/")
    for name in ("The Glass", "Ingest Studio", "Admin console"):
        assert name in page
    code, body = _request(base + "/status")
    assert code == 200
    assert set(json.loads(body)) == {"The Glass", "Ingest Studio", "Admin console"}
