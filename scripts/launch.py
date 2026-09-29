"""One screen to start and open the Glass, the Ingest Studio or the Admin console.

**Why this exists (friction log, 29 September 2026).** Starting the product meant knowing that
three interfaces are three different things: the Glass is the workspace at `localhost:8080` and
asks for a sign-in; the Ingest Studio is not an address at all but the "Ingest" tab inside the
Glass; and the admin console is the harness's own process on `localhost:7000` — the workspace does
not serve it (`localhost:8080/admin` answers with the Glass's sign-in page). Nothing put the three
in one place, so the way in was a run book rather than a click.

Run it as the project's other operational modules are (`CLAUDE.md`'s conventions — no `osprey` CLI
yet), from the repository root:

    PYTHONPATH=.:packages .venv/bin/python -m scripts.launch        # or: make launch

It serves a small page on `127.0.0.1:7070` and opens it. Each tile shows in words and a shape
whether that interface is running, and offers exactly one button for its state: **Start** when it
is not running, a disabled **Starting…** while it comes up, **Open** when it answers.

- **The Glass** and **Ingest Studio** need the deployment up. Start runs
  `docker compose up -d --wait` against the already-rendered `deploy/generated/<profile>/` — the
  same command, with the same `--env-file`, `harness.apply` uses (`harness.apply._compose`), and
  nothing else: it does not regenerate, rebuild or re-seed anything. With no rendered deployment it
  says so and names `python -m harness.apply` rather than guessing.
- **Admin console** starts `python -m harness`, building `apps/harness` first when its `dist/` is
  missing (the server mounts nothing without it, and every page would 404).

**Styling (friction log, second item).** The page is styled only from the workspace's own
`apps/workspace/src/design/tokens.css`, served as it is on disk at `/tokens.css` — not copied here,
so a token change reaches this page with no second edit — and it defines no colour of its own
(`tokens.css`: "Do not introduce a colour that is not defined here"). Status is a word plus a shape
(filled, half, hollow), never a colour alone. The state-to-buttons mapping is written once, in
Python (`render_tiles`), and the script only swaps in the fragment `/tiles` returns, so the tests
exercise what the browser shows.

**What it deliberately does not do.**

- It never reads `deployment.env` beyond the one `OSPREY_WORKSPACE_PORT` line, so no password or
  client secret can reach the page. The demo analyst signs in at the Glass as before; the page
  names the username and which file holds the password, and does not show it.
- It never probes or starts anything on the Conduit's port (8000, which another container holds on
  this machine). Readiness is judged from the workspace, whose `/healthz` the workspace's own
  proxy forwards to the Conduit — so a half-started stack reads `starting`, not `up`.
- It does not mint tokens, sign anyone in, or touch identity or access. (Whether it should sign a
  person in and show only the interfaces their role allows is a design question put to the owner,
  not something this module does.)

**Security of a launcher that starts processes.** It binds loopback only; refuses any request whose
`Host` is not `127.0.0.1:<port>` or `localhost:<port>` (DNS rebinding); and requires a per-run
random token, carried in the page it serves, on every start request (a web page in the same
browser cannot read that page across origins, so it cannot start anything). The commands it can
run are the fixed two above; no request value ever reaches an argument list.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Protocol

from harness.apply import _compose
from harness.render import HARNESS_PORT

REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER_PORT = 7070
DEFAULT_WORKSPACE_PORT = 8080
DEFAULT_PROFILE = "local-lite"
LOOPBACK = "127.0.0.1"
TOKENS_RELATIVE_PATH = Path("apps") / "workspace" / "src" / "design" / "tokens.css"

#: `docker compose up --wait` takes about a minute; for that long a press of Start reads as
#: "starting" even though nothing answers yet. Past it, with still nothing answering, the tile
#: says "not running" again rather than claiming progress for ever.
START_GRACE_SECONDS = 180.0

GLASS = "The Glass"
INGEST = "Ingest Studio"
ADMIN = "Admin console"
NAMES = (GLASS, INGEST, ADMIN)

#: Word and shape for each state — the design system's rule that hue never carries a
#: distinction on its own.
STATE_LABELS = {"up": "Running", "starting": "Starting", "down": "Not running"}
STATE_SHAPES = {"up": "filled", "starting": "half", "down": "hollow"}

Prober = Callable[[str], int | None]


class Spawner(Protocol):
    """`(argv, cwd=..., wait=...)` — runs a command; a protocol so the tests can fake it."""

    def __call__(self, argv: Sequence[str], *, cwd: Path, wait: bool = False) -> None: ...


class LaunchError(Exception):
    """A start that cannot go ahead; the message is shown to the person at the screen."""


class NothingToStart(LaunchError):
    """No rendered deployment to start."""


@dataclass(frozen=True)
class Surface:
    name: str
    url: str
    purpose: str
    hint: str
    starts: str  # "stack" or "admin"
    audience: str  # "analysts" or "admin"


@dataclass(frozen=True)
class Step:
    argv: tuple[str, ...]
    wait: bool = False


def read_workspace_port(env_file: Path) -> int:
    """`OSPREY_WORKSPACE_PORT` from a rendered `deployment.env` — the only line read."""
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "OSPREY_WORKSPACE_PORT":
                return int(value.strip())
    except (OSError, ValueError):
        pass
    return DEFAULT_WORKSPACE_PORT


def http_probe(url: str) -> int | None:
    """The HTTP status a URL answers with, or None when nothing answers."""
    try:
        with urllib.request.urlopen(url, timeout=1.5) as resp:  # noqa: S310 - loopback URLs only
            return int(resp.status)
    except urllib.error.HTTPError as err:
        return err.code
    except (urllib.error.URLError, OSError, ValueError):
        return None


class ProcessSpawner:
    """Runs commands with the repository's own import path, logging to a temp file."""

    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root
        self._children: list[subprocess.Popen[bytes]] = []
        self.log_dir = Path(tempfile.gettempdir()) / "ospreyflow-launch"

    def __call__(self, argv: Sequence[str], *, cwd: Path, wait: bool = False) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        log = (self.log_dir / f"{Path(argv[0]).name}.log").open("ab")
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(
            [str(self._repo_root), str(self._repo_root / "packages")]
        )
        try:
            if wait:
                done = subprocess.run(  # noqa: S603
                    list(argv), cwd=cwd, env=env, stdout=log, stderr=log, check=False
                )
                if done.returncode != 0:
                    raise LaunchError(
                        f"`{' '.join(argv[:3])} …` failed (exit {done.returncode}); "
                        f"the output is in {self.log_dir}"
                    )
                return
            child = subprocess.Popen(  # noqa: S603
                list(argv), cwd=cwd, env=env, stdout=log, stderr=log, start_new_session=True
            )
            if Path(argv[0]).name != "docker":
                # The containers are meant to outlive the launcher; the admin console is not.
                self._children.append(child)
        except FileNotFoundError as err:
            raise LaunchError(f"`{argv[0]}` was not found on this machine's PATH.") from err

    def stop_children(self) -> None:
        for child in self._children:
            if child.poll() is None:
                child.terminate()


class Launcher:
    def __init__(
        self,
        *,
        repo_root: Path,
        prober: Prober,
        spawner: Spawner,
        frontend_built: bool | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.repo_root = repo_root
        self._prober = prober
        self._spawner = spawner
        self._clock = clock
        self._frontend_built = (
            (repo_root / "apps" / "harness" / "dist").is_dir()
            if frontend_built is None
            else frontend_built
        )
        self.token = secrets.token_urlsafe(24)
        self.bound_port = LAUNCHER_PORT
        self._threads: list[threading.Thread] = []
        self._running: set[str] = set()
        self._started_at: dict[str, float] = {}
        self._lock = threading.Lock()

    # -- what the deployment is ------------------------------------------------------------

    def _deployment_dir(self) -> Path | None:
        generated = self.repo_root / "deploy" / "generated"
        preferred = generated / DEFAULT_PROFILE
        if (preferred / "compose.yaml").is_file():
            return preferred
        found = sorted(p.parent for p in generated.glob("*/compose.yaml"))
        return found[0] if len(found) == 1 else None

    def workspace_url(self) -> str:
        directory = self._deployment_dir()
        port = (
            read_workspace_port(directory / "deployment.env")
            if directory is not None
            else DEFAULT_WORKSPACE_PORT
        )
        return f"http://localhost:{port}/"

    def env_file_hint(self) -> str:
        directory = self._deployment_dir()
        if directory is None:
            return "deploy/generated/<profile>/deployment.env"
        return f"{directory.relative_to(self.repo_root)}/deployment.env"

    def surfaces(self) -> list[Surface]:
        workspace = self.workspace_url()
        return [
            Surface(
                GLASS,
                workspace,
                "Where analysts work: the network, timeline, map, dossier and search, "
                "together in one workspace.",
                "Sign in as osprey-demo-analyst. The details are under “Signing in” below.",
                "stack",
                "analysts",
            ),
            Surface(
                INGEST,
                workspace,
                "Bring a new source of data in: connect it, map it, check it, publish it.",
                "It is part of The Glass, so it starts and opens together with it. "
                "Sign in, then choose the Ingest tab at the top.",
                "stack",
                "analysts",
            ),
            Surface(
                ADMIN,
                f"http://localhost:{HARNESS_PORT}/",
                "Settings and set-up for the person who looks after OspreyFlow. "
                "Not needed for analysis.",
                "It opens on this computer only, without a sign-in.",
                "admin",
                "admin",
            ),
        ]

    # -- status ----------------------------------------------------------------------------

    def _within_grace(self, target: str) -> bool:
        started = self._started_at.get(target)
        return started is not None and self._clock() - started < START_GRACE_SECONDS

    def status(self) -> dict[str, str]:
        out: dict[str, str] = {}
        workspace = self.workspace_url()
        stack: str | None = None
        for surface in self.surfaces():
            if surface.starts == "stack":
                if stack is None:
                    if self._prober(f"{workspace}healthz") == 200:
                        stack = "up"
                    elif self._prober(workspace) == 200 or self._within_grace("stack"):
                        stack = "starting"
                    else:
                        stack = "down"
                out[surface.name] = stack
            elif self._prober(surface.url) == 200:
                out[surface.name] = "up"
            else:
                out[surface.name] = "starting" if self._within_grace("admin") else "down"
        return out

    # -- starting --------------------------------------------------------------------------

    def plan(self, target: str) -> list[Step]:
        if target == "stack":
            directory = self._deployment_dir()
            if directory is None:
                raise NothingToStart(
                    "There is no rendered deployment under deploy/generated/ to start. "
                    "Run `python -m harness.apply` once (README.md, “Running it”) to build one."
                )
            argv = [*_compose(directory / "compose.yaml"), "up", "-d", "--wait"]
            return [Step(tuple(argv))]
        if target == "admin":
            steps: list[Step] = []
            if not self._frontend_built:
                steps.append(
                    Step(
                        (
                            "npm",
                            "--prefix",
                            str(self.repo_root / "apps" / "harness"),
                            "run",
                            "build",
                        ),
                        True,
                    )
                )
            steps.append(Step((sys.executable, "-m", "harness")))
            return steps
        raise KeyError(target)

    def _execute(self, target: str, steps: Sequence[Step]) -> None:
        self._started_at[target] = self._clock()
        try:
            for step in steps:
                self._spawner(list(step.argv), cwd=self.repo_root, wait=step.wait)
        except LaunchError:
            self._started_at.pop(target, None)
            raise
        if any(step.argv[0] == "npm" for step in steps):
            self._frontend_built = True

    def start(self, target: str) -> None:
        self._execute(target, self.plan(target))

    def start_in_background(self, target: str) -> None:
        steps = self.plan(target)  # validates now, so a refusal reaches the screen
        with self._lock:
            if target in self._running:
                return
            self._running.add(target)
        self._started_at[target] = self._clock()

        def run() -> None:
            try:
                self._execute(target, steps)
            except LaunchError as err:
                sys.stderr.write(f"launch: {err}\n")
            finally:
                with self._lock:
                    self._running.discard(target)

        thread = threading.Thread(target=run, daemon=True)
        self._threads.append(thread)
        thread.start()

    def wait_idle(self, timeout: float = 5.0) -> None:
        for thread in list(self._threads):
            thread.join(timeout)

    # -- the page --------------------------------------------------------------------------

    def _tile(self, surface: Surface, state: str) -> str:
        name = html.escape(surface.name)
        slug = surface.name.lower().replace(" ", "-")
        label = STATE_LABELS[state]
        shape = STATE_SHAPES[state]
        if state == "up":
            action = (
                f'<a class="btn primary" href="{html.escape(surface.url)}" '
                f'target="_blank" rel="noopener">Open {name}</a>'
            )
            wait = ""
        elif state == "starting":
            action = '<button type="button" class="btn primary" disabled>Starting…</button>'
            wait = (
                '<p class="wait">This usually takes about a minute. '
                "This page updates by itself.</p>"
            )
        else:
            action = (
                f'<button type="button" class="btn primary" '
                f'data-target="{html.escape(surface.starts)}">Start {name}</button>'
            )
            wait = ""
        return f"""      <section class="tile" data-name="{name}" data-state="{state}" aria-labelledby="t-{slug}">
        <header>
          <h3 id="t-{slug}">{name}</h3>
          <span class="chip" data-state="{state}"><span class="shape" data-shape="{shape}" aria-hidden="true"></span>{label}</span>
        </header>
        <p class="purpose">{html.escape(surface.purpose)}</p>
        <p class="hint">{html.escape(surface.hint)}</p>
        <p class="actions">{action}</p>
        {wait}<p class="message" role="status"></p>
      </section>"""  # noqa: E501

    def render_tiles(self, status: dict[str, str] | None = None) -> str:
        status = self.status() if status is None else status
        groups = (
            ("analysts", "For analysts"),
            ("admin", "For whoever looks after OspreyFlow"),
        )
        parts: list[str] = []
        for audience, heading in groups:
            tiles = "\n".join(
                self._tile(s, status.get(s.name, "down"))
                for s in self.surfaces()
                if s.audience == audience
            )
            parts.append(
                f'    <h2 class="group">{heading}</h2>\n    <div class="grid">\n{tiles}\n    </div>'
            )
        return "\n".join(parts)  # noqa: E501

    def render_signin(self) -> str:
        return f"""    <section class="panel" aria-labelledby="signin-title">
      <h2 id="signin-title" class="group">Signing in</h2>
      <p>To use The Glass or the Ingest Studio, sign in as the demo analyst.</p>
      <p>Username: <span class="value">osprey-demo-analyst</span>
        <button type="button" class="btn" data-copy="osprey-demo-analyst">Copy</button></p>
      <p>Password: it was created when OspreyFlow was set up and is kept in
        <span class="value">{html.escape(self.env_file_hint())}</span>, on the line that starts
        <span class="value">OSPREY_DEMO_ANALYST_PASSWORD</span>. It is not shown on this page.</p>
    </section>"""  # noqa: E501

    def render_page(self) -> str:
        return (
            _PAGE.replace("__TILES__", self.render_tiles())
            .replace("__SIGNIN__", self.render_signin())
            .replace("__TOKEN__", html.escape(self.token))
        )

    def tokens_css(self) -> str | None:
        path = self.repo_root / TOKENS_RELATIVE_PATH
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return None


_PAGE = """<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OspreyFlow — choose what to open</title>
<link rel="stylesheet" href="/tokens.css">
<style>
  .wrap { max-width: 960px; margin: 0 auto; padding: var(--sp-40) var(--sp-24); }
  h1 { margin: 0; font-size: var(--fs-23); line-height: var(--lh-23); font-weight: 700; }
  .lede { margin: var(--sp-8) 0 0; max-width: 62ch; font-size: var(--fs-14); line-height: var(--lh-14); color: var(--text-secondary); }
  h2.group { margin: var(--sp-32) 0 var(--sp-12); font-size: var(--fs-19); line-height: var(--lh-19); font-weight: 600; }
  .grid { display: grid; gap: var(--sp-16); grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }
  .tile, .panel { background: var(--surface-panel); border: 1px solid var(--border-subtle); border-radius: var(--r-panel); padding: var(--sp-20); }
  .panel { margin-top: var(--sp-32); }
  .panel h2.group { margin-top: 0; }
  .tile header { display: flex; align-items: center; justify-content: space-between; gap: var(--sp-12); }
  .tile h3 { margin: 0; font-size: var(--fs-16); line-height: var(--lh-16); font-weight: 600; }
  .tile p, .panel p { margin: var(--sp-12) 0 0; font-size: var(--fs-14); line-height: var(--lh-14); }
  .hint, .wait { color: var(--text-tertiary); }
  .chip { display: inline-flex; align-items: center; gap: var(--sp-6); padding: var(--sp-2) var(--sp-8); border: 1px solid currentColor; border-radius: var(--r-chip); font-size: var(--fs-12); line-height: var(--lh-12); font-weight: 600; white-space: nowrap; }
  .chip[data-state="up"] { color: var(--success); }
  .chip[data-state="starting"] { color: var(--warning); }
  .chip[data-state="down"] { color: var(--text-tertiary); }
  .shape { width: 10px; height: 10px; box-sizing: border-box; border: 2px solid currentColor; border-radius: 50%; }
  .shape[data-shape="filled"] { background: currentColor; }
  .shape[data-shape="half"] { background: linear-gradient(90deg, currentColor 50%, transparent 50%); }
  .btn { display: inline-block; padding: var(--sp-8) var(--sp-16); border: 1px solid var(--border); border-radius: var(--r-control); background: var(--surface-raised); color: var(--text-primary); font: 600 var(--fs-14) / var(--lh-14) var(--ui); text-decoration: none; cursor: pointer; transition: background var(--dur-fast) var(--ease); }
  .btn:hover { background: var(--surface-hover); }
  a.btn, a.btn:hover { color: var(--text-primary); border-bottom-color: var(--border); }
  .btn.primary { background: var(--brass); border-color: var(--brass); color: var(--brass-ink); }
  .btn.primary:hover { background: var(--brass-hover); border-color: var(--brass-hover); }
  .btn.primary:active { background: var(--brass-press); }
  a.btn.primary, a.btn.primary:hover { color: var(--brass-ink); border-bottom-color: var(--brass-hover); }
  .btn:disabled { background: var(--surface-raised); border-color: var(--border-subtle); color: var(--text-disabled); cursor: default; }
  .message { min-height: var(--lh-14); color: var(--text-secondary); }
  .foot { margin-top: var(--sp-32); font-size: var(--fs-12); line-height: var(--lh-12); color: var(--text-tertiary); }
  .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
</style>
</head>
<body>
<div class="wrap">
  <main>
    <h1>OspreyFlow</h1>
    <p class="lede">OspreyFlow has two parts: the workspace where analysts work, which includes the Ingest Studio, and an Admin console for whoever looks after it. Choose what you want to use. If it is not running yet, press Start and this page will update when it is ready.</p>
    <div id="tiles">
__TILES__
    </div>
__SIGNIN__
    <p class="foot">Closing this page does not stop OspreyFlow. To stop this launcher, press Ctrl-C in the terminal where you started it; the Admin console it started stops with it, and The Glass keeps running.</p>
  </main>
</div>
<p id="announce" class="sr-only" role="status" aria-live="polite"></p>
<script>
const TOKEN = "__TOKEN__";
const tiles = document.getElementById("tiles");
const announce = document.getElementById("announce");
const LABELS = { up: "running", starting: "starting", down: "not running" };

async function refresh() {
  let markup;
  try { markup = await (await fetch("/tiles")).text(); } catch (_) { return; }
  const next = new DOMParser().parseFromString(markup, "text/html");
  next.querySelectorAll(".tile").forEach((fresh) => {
    const name = fresh.dataset.name;
    const current = [...tiles.querySelectorAll(".tile")].find((t) => t.dataset.name === name);
    if (!current || current.dataset.state === fresh.dataset.state) return;
    const hadFocus = current.contains(document.activeElement);
    const replacement = document.importNode(fresh, true);
    current.replaceWith(replacement);
    announce.textContent = name + " is now " + LABELS[fresh.dataset.state] + ".";
    if (hadFocus) (replacement.querySelector(".primary") || replacement).focus();
  });
}

tiles.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-target]");
  if (!button || button.disabled) return;
  const message = button.closest(".tile").querySelector(".message");
  button.disabled = true;
  message.textContent = "Starting…";
  try {
    const response = await fetch("/start/" + button.dataset.target, {
      method: "POST", headers: { "X-Launch-Token": TOKEN },
    });
    const body = await response.json();
    message.textContent = body.message;
    if (!response.ok) button.disabled = false;
  } catch (_) {
    message.textContent = "The launcher is no longer running. Start it again from the terminal.";
  }
  refresh();
});

document.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-copy]");
  if (!button) return;
  try {
    await navigator.clipboard.writeText(button.dataset.copy);
    button.textContent = "Copied";
    setTimeout(() => { button.textContent = "Copy"; }, 2000);
  } catch (_) { /* select-and-copy by hand still works */ }
});

setInterval(refresh, 3000);
</script>
</body>
</html>
"""  # noqa: E501


def _handler(launcher: Launcher) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "OspreyFlowLaunch"

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

        def _host_ok(self) -> bool:
            allowed = {f"127.0.0.1:{launcher.bound_port}", f"localhost:{launcher.bound_port}"}
            return self.headers.get("Host", "") in allowed

        def _send(self, code: int, body: str, content_type: str) -> None:
            data = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def _json(self, code: int, payload: object) -> None:
            self._send(code, json.dumps(payload), "application/json")

        def do_GET(self) -> None:  # noqa: N802
            if not self._host_ok():
                self._json(403, {"message": "Unexpected host name."})
            elif self.path == "/":
                self._send(200, launcher.render_page(), "text/html")
            elif self.path == "/tiles":
                self._send(200, launcher.render_tiles(), "text/html")
            elif self.path == "/tokens.css":
                css = launcher.tokens_css()
                if css is None:
                    self._json(404, {"message": "The design tokens file was not found."})
                else:
                    self._send(200, css, "text/css")
            elif self.path == "/status":
                self._json(200, launcher.status())
            else:
                self._json(404, {"message": "Not found."})

        def do_POST(self) -> None:  # noqa: N802
            if not self._host_ok():
                self._json(403, {"message": "Unexpected host name."})
                return
            token = self.headers.get("X-Launch-Token", "")
            if not secrets.compare_digest(token, launcher.token):
                self._json(403, {"message": "This request did not come from the launcher page."})
                return
            prefix = "/start/"
            if not self.path.startswith(prefix):
                self._json(404, {"message": "Not found."})
                return
            try:
                launcher.start_in_background(self.path[len(prefix) :])
            except KeyError:
                self._json(404, {"message": "Not found."})
            except LaunchError as err:
                self._json(409, {"message": str(err)})
            else:
                self._json(202, {"message": "Started. This tile updates when it is ready."})

    return Handler


def make_server(launcher: Launcher, *, port: int = LAUNCHER_PORT) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((LOOPBACK, port), _handler(launcher))
    launcher.bound_port = server.server_address[1]
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.launch",
        description="Start and open the Glass, the Ingest Studio or the Admin console.",
    )
    parser.add_argument("--port", type=int, default=LAUNCHER_PORT)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--no-browser", action="store_true", help="Print the address, do not open it."
    )
    args = parser.parse_args(argv)

    spawner = ProcessSpawner(args.repo_root)
    launcher = Launcher(repo_root=args.repo_root, prober=http_probe, spawner=spawner)
    try:
        server = make_server(launcher, port=args.port)
    except OSError as err:
        sys.stderr.write(
            f"Could not listen on 127.0.0.1:{args.port} ({err.strerror}). "
            "Is the launcher already running? Try --port with a free port.\n"
        )
        return 1
    url = f"http://localhost:{launcher.bound_port}/"
    sys.stdout.write(f"OspreyFlow launcher: {url}   (Ctrl-C to stop)\n")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        spawner.stop_children()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
