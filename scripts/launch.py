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

It serves a small page on `127.0.0.1:7070` and opens it. Each tile shows whether that interface is
answering and starts it if it is not:

- **The Glass** and **Ingest Studio** need the deployment up. Start runs
  `docker compose up -d --wait` against the already-rendered `deploy/generated/<profile>/` — the
  same command, with the same `--env-file`, `harness.apply` uses (`harness.apply._compose`), and
  nothing else: it does not regenerate, rebuild or re-seed anything. With no rendered deployment it
  says so and names `python -m harness.apply` rather than guessing.
- **Admin console** starts `python -m harness`, building `apps/harness` first when its `dist/` is
  missing (the server mounts nothing without it, and every page would 404).

**What it deliberately does not do.**

- It never reads `deployment.env` beyond the one `OSPREY_WORKSPACE_PORT` line, so no password or
  client secret can reach the page. The demo analyst signs in at the Glass as before; the page
  says which file holds the password and does not show it.
- It never probes or starts anything on the Conduit's port (8000, which another container holds on
  this machine). Readiness is judged from the workspace, whose `/healthz` the workspace's own
  proxy forwards to the Conduit — so a half-started stack reads `starting`, not `up`.
- It does not mint tokens, sign anyone in, or touch identity or access.

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

GLASS = "The Glass"
INGEST = "Ingest Studio"
ADMIN = "Admin console"

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
    blurb: str
    hint: str
    starts: str  # "stack" or "admin"


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
    ) -> None:
        self.repo_root = repo_root
        self._prober = prober
        self._spawner = spawner
        self._frontend_built = (
            (repo_root / "apps" / "harness" / "dist").is_dir()
            if frontend_built is None
            else frontend_built
        )
        self.token = secrets.token_urlsafe(24)
        self.bound_port = LAUNCHER_PORT
        self._threads: list[threading.Thread] = []
        self._running: set[str] = set()
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

    def surfaces(self) -> list[Surface]:
        workspace = self.workspace_url()
        directory = self._deployment_dir()
        where = (
            f"{directory.relative_to(self.repo_root)}/deployment.env"
            if directory is not None
            else "deploy/generated/<profile>/deployment.env"
        )
        return [
            Surface(
                GLASS,
                workspace,
                "The analyst workspace: canvas, timeline, map, dossier, query.",
                f"Sign in as osprey-demo-analyst; the password is in {where}.",
                "stack",
            ),
            Surface(
                INGEST,
                workspace,
                "Connect a source, map it, verify it, publish it.",
                "It has no address of its own: sign in to the Glass, then open the Ingest tab.",
                "stack",
            ),
            Surface(
                ADMIN,
                f"http://localhost:{HARNESS_PORT}/",
                "The harness: profile, components, models, governance, geospatial, preflight.",
                "No sign-in. It runs as its own process, separate from the workspace.",
                "admin",
            ),
        ]

    # -- status ----------------------------------------------------------------------------

    def status(self) -> dict[str, str]:
        out: dict[str, str] = {}
        workspace = self.workspace_url()
        stack: str | None = None
        for surface in self.surfaces():
            if surface.starts == "stack":
                if stack is None:
                    if self._prober(f"{workspace}healthz") == 200:
                        stack = "up"
                    elif self._prober(workspace) == 200:
                        stack = "starting"
                    else:
                        stack = "down"
                out[surface.name] = stack
            else:
                out[surface.name] = "up" if self._prober(surface.url) == 200 else "down"
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

    def _execute(self, steps: Sequence[Step]) -> None:
        for step in steps:
            self._spawner(list(step.argv), cwd=self.repo_root, wait=step.wait)
        if any(step.argv[0] == "npm" for step in steps):
            self._frontend_built = True

    def start(self, target: str) -> None:
        self._execute(self.plan(target))

    def start_in_background(self, target: str) -> None:
        steps = self.plan(target)  # validates now, so a refusal reaches the screen
        with self._lock:
            if target in self._running:
                return
            self._running.add(target)

        def run() -> None:
            try:
                self._execute(steps)
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

    def render_page(self) -> str:
        tiles = "\n".join(
            f"""    <section class="tile" data-name="{html.escape(s.name)}">
      <h2>{html.escape(s.name)}</h2>
      <p>{html.escape(s.blurb)}</p>
      <p class="hint">{html.escape(s.hint)}</p>
      <p class="state" aria-live="polite"><span class="dot"></span><span class="label">Checking…</span></p>
      <p class="actions">
        <a class="open" href="{html.escape(s.url)}" target="_blank" rel="noopener">Open {html.escape(s.name)}</a>
        <button type="button" class="start" data-target="{html.escape(s.starts)}">Start</button>
      </p>
      <p class="message" role="status"></p>
    </section>"""  # noqa: E501
            for s in self.surfaces()
        )
        return _PAGE.replace("__TILES__", tiles).replace("__TOKEN__", html.escape(self.token))


_PAGE = """<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OspreyFlow — launch</title>
<style>
  :root { color-scheme: light dark; }
  body { font: 16px/1.5 system-ui, sans-serif; margin: 0; padding: 2rem 1rem; background: Canvas; color: CanvasText; }
  main { max-width: 64rem; margin: 0 auto; }
  h1 { margin: 0 0 .25rem; }
  .lede { margin: 0 0 1.5rem; opacity: .75; }
  .tiles { display: grid; gap: 1rem; grid-template-columns: repeat(auto-fit, minmax(17rem, 1fr)); }
  .tile { border: 1px solid GrayText; border-radius: .5rem; padding: 1rem 1.25rem; }
  .tile h2 { margin: 0 0 .5rem; font-size: 1.15rem; }
  .tile p { margin: .4rem 0; }
  .hint { font-size: .9rem; opacity: .75; }
  .dot { display: inline-block; width: .7rem; height: .7rem; border-radius: 50%; margin-right: .5rem; border: 2px solid GrayText; }
  .up .dot { background: AccentColor; border-color: AccentColor; }
  .starting .dot { border-style: dotted; }
  .actions { display: flex; gap: .75rem; align-items: center; flex-wrap: wrap; }
  a.open, button { font: inherit; padding: .4rem .9rem; border-radius: .35rem; border: 1px solid GrayText; background: ButtonFace; color: ButtonText; cursor: pointer; text-decoration: none; }
  a.open:focus-visible, button:focus-visible { outline: 3px solid AccentColor; outline-offset: 2px; }
  .up button.start { display: none; }
  .message { min-height: 1.4em; font-size: .9rem; }
</style>
</head>
<body>
<main>
  <h1>OspreyFlow</h1>
  <p class="lede">Choose an interface. Start brings it up if it is not running; Open shows it in a new tab.</p>
  <div class="tiles">
__TILES__
  </div>
</main>
<script>
const TOKEN = "__TOKEN__";
const LABELS = { up: "Running", starting: "Starting…", down: "Not running" };
async function refresh() {
  try {
    const status = await (await fetch("/status")).json();
    document.querySelectorAll(".tile").forEach((tile) => {
      const state = status[tile.dataset.name] || "down";
      tile.classList.remove("up", "starting", "down");
      tile.classList.add(state);
      tile.querySelector(".label").textContent = LABELS[state];
    });
  } catch (_) { /* the launcher itself was stopped */ }
}
document.querySelectorAll("button.start").forEach((button) => {
  button.addEventListener("click", async () => {
    const message = button.closest(".tile").querySelector(".message");
    message.textContent = "Starting…";
    const response = await fetch("/start/" + button.dataset.target, {
      method: "POST", headers: { "X-Launch-Token": TOKEN },
    });
    const body = await response.json();
    message.textContent = body.message;
    refresh();
  });
});
refresh();
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
                self._json(202, {"message": "Started. This tile updates when it answers."})

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
