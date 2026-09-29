"""`scripts/launch.py` — the one-screen launcher for the Glass, the Ingest Studio and the Admin
console.

**Seen on the running `local-lite` deployment, 29 September 2026.** Starting the product meant
knowing that three interfaces are three different things: the Glass is `localhost:8080` and asks
for a sign-in; the Ingest Studio is not an address at all but the "Ingest" tab inside the Glass;
and the admin console is the harness's own process on `localhost:7100`, which the workspace does
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
import re
import threading
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator, Sequence
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from harness.render import HARNESS_PORT
from scripts import launch

from tools.layout import REPO as _REPO

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
    tokens = tmp_path / "apps" / "workspace" / "src" / "design" / "tokens.css"
    tokens.parent.mkdir(parents=True)
    tokens.write_text(":root { --brass: #c08a34; } /* fixture marker 41d7 */\n", encoding="utf-8")
    return tmp_path


def _launcher(
    repo: Path,
    prober: FakeProber | None = None,
    spawner: FakeSpawner | None = None,
    clock: Callable[[], float] | None = None,
) -> launch.Launcher:
    return launch.Launcher(
        repo_root=repo,
        prober=prober or FakeProber(),
        spawner=spawner or FakeSpawner(),
        frontend_built=True,
        clock=clock or (lambda: 0.0),
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
    assert by_name["The Glass"].url.startswith("http://localhost:9191/")
    assert by_name["Ingest Studio"].url.startswith("http://localhost:9191/")


def test_the_glass_and_the_studio_open_different_places_and_say_they_came_from_the_launcher(
    repo: Path,
) -> None:
    """Seen: both tiles opened the identical page (the Studio is a tab inside the Glass), and the
    Glass then asked a person who had just signed in to sign in again. `from=launcher` tells the
    Glass to carry the sign-in on; `view=ingest` lands the Studio tile on the Ingest tab."""
    by_name = {s.name: s for s in _launcher(repo).surfaces()}
    assert by_name["The Glass"].url == "http://localhost:8080/?from=launcher"
    assert by_name["Ingest Studio"].url == "http://localhost:8080/?from=launcher&view=ingest"
    assert by_name["The Glass"].url != by_name["Ingest Studio"].url


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


def test_starting_the_stack_runs_the_refresh_sequence_and_never_renders_again(
    repo: Path,
) -> None:
    """Catches the original fault: a bare `docker compose up` never rebuilt an image, so a code
    change did not reach the running stack. Start runs `scripts.refresh` (its own tests hold the
    order and the guarantees); it must not re-render, which would mint new secrets."""
    spawner = FakeSpawner()
    _launcher(repo, spawner=spawner).start("stack")
    (argv,) = spawner.calls
    assert argv[1:] == ["-m", "scripts.refresh"]
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


# --- The page: design system and plain language (friction log, 29 September 2026, second item) ---
#
# Seen in the owner's own screenshot: the first version styled itself with the browser's default
# colours (`AccentColor`, `GrayText`, `ButtonFace`) although "no colour outside the tokens" is a
# standing rule; every tile showed both "Open" and "Start" whatever its state; the Glass and the
# Ingest Studio looked like two things when one deployment serves both; and status was a small
# coloured dot, which the design system says must never carry a distinction alone.

REAL_TOKENS = (
    _REPO / "apps" / "workspace" / "src" / "design" / "tokens.css"
)


def _tile(fragment: str, name: str) -> str:
    match = re.search(
        rf'<section class="tile"[^>]*data-name="{re.escape(name)}".*?</section>', fragment, re.S
    )
    assert match, f"no tile for {name!r}"
    return match.group(0)


def _visible_text(page: str) -> str:
    page = re.sub(r"<(script|style)\b.*?</\1>", " ", page, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page))


def _page_css(page: str) -> str:
    return "\n".join(re.findall(r"<style>(.*?)</style>", page, flags=re.S))


def test_the_page_takes_its_styling_from_the_workspaces_own_tokens_file(
    served: tuple[str, launch.Launcher, FakeProber, FakeSpawner], repo: Path
) -> None:
    """One source: the file is served as it is on disk, not copied into the launcher, so a token
    change in the workspace reaches this page with no second edit."""
    base, _, _, _ = served
    _, page = _request(base + "/")
    assert '<link rel="stylesheet" href="/tokens.css">' in page
    code, css = _request(base + "/tokens.css")
    assert code == 200
    on_disk = repo / "apps" / "workspace" / "src" / "design" / "tokens.css"
    assert css == on_disk.read_text(encoding="utf-8")


def test_the_page_defines_no_colour_of_its_own(
    served: tuple[str, launch.Launcher, FakeProber, FakeSpawner],
) -> None:
    """`tokens.css`: "Do not introduce a colour that is not defined here." The first version used
    the browser's system colours, which no hex-literal scan would have caught, so they are named."""
    base, _, _, _ = served
    _, page = _request(base + "/")
    css = _page_css(page)
    assert css, "the page carries no stylesheet of its own to check"
    forbidden = [
        r"#[0-9a-fA-F]{3,8}\b",
        r"\b(?:rgb|rgba|hsl|hsla|hwb|lab|lch|oklab|oklch|color)\(",
        r"\b(?:AccentColor|AccentColorText|ButtonFace|ButtonText|ButtonBorder|Canvas|CanvasText"
        r"|GrayText|LinkText|VisitedText|ActiveText|Highlight|HighlightText|Field|FieldText|Mark"
        r"|MarkText|SelectedItem|SelectedItemText)\b",
        r"(?<![-\w])(?:white|black|red|green|blue|gray|grey|orange|yellow|purple)(?![-\w])",
    ]
    for pattern in forbidden:
        assert not re.search(pattern, css), (
            f"colour outside the tokens: /{pattern}/ in the page CSS"
        )
    assert "style=" not in page, "an inline style attribute bypasses the stylesheet check"


def test_every_token_the_page_uses_exists_in_the_real_tokens_file(
    served: tuple[str, launch.Launcher, FakeProber, FakeSpawner],
) -> None:
    """A misspelt `var(--brass-hovr)` resolves to nothing and fails silently in a browser. Checked
    against the repository's real `tokens.css`, not the fixture's."""
    base, _, _, _ = served
    _, page = _request(base + "/")
    used = set(re.findall(r"var\((--[a-z0-9-]+)", _page_css(page)))
    defined = set(re.findall(r"(--[a-z0-9-]+)\s*:", REAL_TOKENS.read_text(encoding="utf-8")))
    assert used, "the page's CSS uses no token at all"
    assert used <= defined, f"tokens used but not defined: {sorted(used - defined)}"


@pytest.mark.parametrize(
    ("state", "label", "shape"),
    [
        ("up", "Running", "filled"),
        ("starting", "Starting", "half"),
        ("down", "Not running", "hollow"),
    ],
)
def test_each_state_is_a_word_and_a_shape_never_a_colour_alone(
    repo: Path, state: str, label: str, shape: str
) -> None:
    """The design system's own rule: hue never carries a distinction on its own."""
    tile = _tile(_launcher(repo).render_tiles(dict.fromkeys(launch.NAMES, state)), launch.GLASS)
    assert f">{label}<" in re.sub(r"\s+", "", tile).replace(
        "</span>", "<"
    ) or label in _visible_text(tile)
    assert f'data-shape="{shape}"' in tile


def test_a_running_interface_offers_open_and_nothing_else(repo: Path) -> None:
    tile = _tile(_launcher(repo).render_tiles(dict.fromkeys(launch.NAMES, "up")), launch.GLASS)
    assert "Open The Glass" in tile
    assert "Start" not in _visible_text(tile)
    assert tile.count('class="btn primary"') == 1


def test_an_interface_that_is_not_running_offers_start_and_not_open(repo: Path) -> None:
    tile = _tile(_launcher(repo).render_tiles(dict.fromkeys(launch.NAMES, "down")), launch.GLASS)
    assert "Start The Glass" in tile
    assert "href=" not in tile
    assert 'data-target="stack"' in tile
    assert tile.count('class="btn primary"') == 1


def test_a_starting_interface_shows_a_disabled_button_so_it_cannot_be_started_twice(
    repo: Path,
) -> None:
    tile = _tile(
        _launcher(repo).render_tiles(dict.fromkeys(launch.NAMES, "starting")), launch.GLASS
    )
    assert "disabled" in tile
    assert "href=" not in tile
    assert tile.count('class="btn primary"') == 1


def test_pressing_start_reads_as_starting_until_it_answers_then_gives_up_honestly(
    repo: Path,
) -> None:
    """`docker compose up --wait` takes a minute; for that minute nothing answers, and a tile that
    went straight back to "Not running" invited a second press. After the grace period with still
    nothing answering, it says so rather than claiming progress for ever."""
    now = [100.0]
    launcher = _launcher(repo, clock=lambda: now[0])
    launcher.start("stack")
    assert launcher.status()[launch.GLASS] == "starting"
    now[0] += launch.START_GRACE_SECONDS + 1
    assert launcher.status()[launch.GLASS] == "down"


def test_the_grace_period_never_hides_an_interface_that_is_actually_up(repo: Path) -> None:
    prober = FakeProber({"http://localhost:8080/healthz": 200})
    launcher = _launcher(repo, prober)
    launcher.start("stack")
    assert launcher.status()[launch.GLASS] == "up"


def test_a_refused_start_does_not_claim_the_interface_is_starting(tmp_path: Path) -> None:
    launcher = _launcher(tmp_path)
    with pytest.raises(launch.NothingToStart):
        launcher.start("stack")
    assert launcher.status()[launch.GLASS] == "down"


def test_the_analyst_interfaces_and_the_admin_console_are_grouped_and_explained(
    repo: Path,
) -> None:
    fragment = _launcher(repo).render_tiles(dict.fromkeys(launch.NAMES, "up"))
    text = _visible_text(fragment)
    assert text.index("For analysts") < text.index("The Glass") < text.index("Ingest Studio")
    assert text.index("Ingest Studio") < text.index("Admin console")
    assert "Admin console" not in text[: text.index("For analysts")]
    ingest = _visible_text(_tile(fragment, launch.INGEST))
    assert "part of The Glass" in ingest, "the Studio must say it runs inside the Glass"
    assert "Ingest tab" in ingest and "choose the Ingest tab" not in ingest, (
        "the Studio opens on its tab; it must not tell a person to go and find it"
    )


def test_the_page_speaks_in_the_product_s_own_words_not_the_machinery_s(
    served: tuple[str, launch.Launcher, FakeProber, FakeSpawner],
) -> None:
    """The first version told a first-time user about "the harness". Visible text only — the
    addresses the buttons open are attributes, not prose."""
    base, _, _, _ = served
    _, page = _request(base + "/")
    text = _visible_text(page).lower()
    for jargon in ("harness", "conduit", "docker", "compose", "proxy", "localhost", "container"):
        assert jargon not in text, f"{jargon!r} in the page's visible text"


def test_the_page_says_how_to_sign_in_without_showing_the_password(
    served: tuple[str, launch.Launcher, FakeProber, FakeSpawner],
) -> None:
    base, _, _, _ = served
    _, page = _request(base + "/")
    text = _visible_text(page)
    assert "osprey-demo-analyst" in text
    assert "deployment.env" in text
    assert DEMO_PASSWORD not in page


def test_the_tiles_the_page_refreshes_from_are_the_ones_it_first_shows(
    served: tuple[str, launch.Launcher, FakeProber, FakeSpawner],
) -> None:
    """One implementation of the state-to-buttons mapping, in Python, so the tests above are about
    what the browser really shows and the script only swaps fragments in."""
    base, _, _, _ = served
    _, page = _request(base + "/")
    code, fragment = _request(base + "/tiles")
    assert code == 200
    for name in launch.NAMES:
        assert f'data-name="{name}"' in fragment
    assert fragment.strip() in page
