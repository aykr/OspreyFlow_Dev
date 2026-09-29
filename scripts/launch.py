"""One screen to start and open the Glass, the Ingest Studio or the Admin console.

**Why this exists (friction log, 29 September 2026).** Starting the product meant knowing that
three interfaces are three different things: the Glass is the workspace at `localhost:8080` and
asks for a sign-in; the Ingest Studio is not an address at all but the "Ingest" tab inside the
Glass; and the admin console is the harness's own process on `localhost:7100` — the workspace does
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
import urllib.parse
import urllib.request
import webbrowser
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Protocol

from harness.apply import _compose
from harness.oidc import (
    Identity,
    IdentityProviderUnreachable,
    LoginAttempts,
    SessionStore,
    SignInConfig,
    default_issuer,
    handle_callback,
    rendered_realm_exists,
)
from harness.realm import (
    ADMIN_ROLE,
    HARNESS_PORT,
    LAUNCHER_CLIENT_ID,
    LAUNCHER_ORIGIN,
    LAUNCHER_PORT,
    LAUNCHER_REDIRECT_URI,
)

from harness import oidc
from schemas.ingest import StudioRole

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKSPACE_PORT = 8080
DEFAULT_PROFILE = "local-lite"
LOOPBACK = "127.0.0.1"
TOKENS_RELATIVE_PATH = Path("apps") / "workspace" / "src" / "design" / "tokens.css"

#: `docker compose up --wait` takes about a minute; for that long a press of Start reads as
#: "starting" even though nothing answers yet. Past it, with still nothing answering, the tile
#: says "not running" again rather than claiming progress for ever.
START_GRACE_SECONDS = 180.0
#: Appended to the Glass's address. It tells the Glass this person has just signed in through the
#: launcher, so it carries the sign-in on instead of asking again (the identity provider already
#: knows them, so no password is asked). It grants nothing: the Glass still signs in, and the
#: Conduit still checks every request.
HANDOFF = "from=launcher"

GLASS = "The Glass"
INGEST = "Ingest Studio"
ADMIN = "Admin console"
NAMES = (GLASS, INGEST, ADMIN)

#: ADR-051. The roles that show the Ingest Studio tile: any one of the Studio's own roles. Taken
#: from the Studio's definition so a role added there is not silently missing here.
STUDIO_ROLES = frozenset(role.value for role in StudioRole)
SESSION_COOKIE = "osprey_launcher_session"
LOGIN_COOKIE = "osprey_launcher_login"
SESSION_TTL_SECONDS = 8 * 3600.0
#: What the person sees before signing in: one tile, which is either "start it" or "sign in".
SIGN_IN_TILE = "OspreyFlow"

#: Word and shape for each state — the design system's rule that hue never carries a
#: distinction on its own.
STATE_LABELS = {"up": "Running", "starting": "Starting", "down": "Not running"}
STATE_SHAPES = {"up": "filled", "starting": "half", "down": "hollow"}

Prober = Callable[[str], int | None]


class Handle(Protocol):
    """What a background start leaves behind: whether it is still running, and where it logs."""

    log_path: Path

    def poll(self) -> int | None:
        """None while running, otherwise the exit code."""
        ...


class Spawner(Protocol):
    """`(argv, cwd=..., wait=...)` — runs a command; a protocol so the tests can fake it.

    A command started without waiting returns a `Handle`, so the launcher can tell that it has
    stopped. (A spawner with nothing to report may return None.)"""

    def __call__(
        self, argv: Sequence[str], *, cwd: Path, wait: bool = False
    ) -> Handle | None: ...


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
    #: Who is shown this tile once sign-in is required: None means any signed-in account, otherwise
    #: an account holding at least one of these roles. A courtesy to the person at the screen, not
    #: an access control (the Conduit and the Admin console enforce their own).
    roles: frozenset[str] | None = None


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


@dataclass(frozen=True)
class _Child:
    process: subprocess.Popen[bytes]
    log_path: Path

    def poll(self) -> int | None:
        return self.process.poll()


class ProcessSpawner:
    """Runs commands with the repository's own import path, logging to a temp file."""

    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root
        self._children: list[subprocess.Popen[bytes]] = []
        self.log_dir = Path(tempfile.gettempdir()) / "ospreyflow-launch"

    def __call__(self, argv: Sequence[str], *, cwd: Path, wait: bool = False) -> Handle | None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.log_dir / f"{Path(argv[0]).name}.log"
        log = log_path.open("ab")
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
                return None
            child = subprocess.Popen(  # noqa: S603
                list(argv), cwd=cwd, env=env, stdout=log, stderr=log, start_new_session=True
            )
            if Path(argv[0]).name != "docker":
                # The containers are meant to outlive the launcher; the admin console is not.
                self._children.append(child)
            return _Child(child, log_path)
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
        oidc_issuer: str | None = None,
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
        self._handles: dict[str, Handle] = {}
        self._lock = threading.Lock()
        # ADR-051. Once a deployment has been rendered there is a realm to sign in to, and this
        # launcher asks first and shows each account only what its roles allow. Before that it is
        # open, because there is nothing to sign in to and the Admin console that renders the realm
        # would otherwise be unreachable. Decided now, for the life of this process.
        generated = repo_root / "deploy" / "generated"
        self.enforced = rendered_realm_exists(generated)
        self.sign_in_config = SignInConfig(
            issuer=oidc_issuer or default_issuer(generated),
            client_id=LAUNCHER_CLIENT_ID,
            redirect_uri=LAUNCHER_REDIRECT_URI,
            post_logout_uri=f"{LAUNCHER_ORIGIN}/",
        )
        self.sessions = SessionStore(ttl_seconds=SESSION_TTL_SECONDS, clock=clock)
        self.attempts = LoginAttempts(clock=clock)

    # -- who is signed in -----------------------------------------------------------------------

    def identity(self, session_token: str | None) -> Identity | None:
        return self.sessions.get(session_token)

    def can_see(self, surface: Surface, identity: Identity | None) -> bool:
        if not self.enforced:
            return True
        if identity is None:
            return False
        return surface.roles is None or any(identity.has_role(r) for r in surface.roles)

    def mode(self, identity: Identity | None) -> str:
        if not self.enforced:
            return "open"
        return "signed-in" if identity is not None else "signed-out"

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

    def surfaces(self, identity: Identity | None = None) -> list[Surface]:
        workspace = self.workspace_url()
        who = identity.username if identity is not None else None
        signed_in = self.enforced and who is not None
        return [
            Surface(
                GLASS,
                f"{workspace}?{HANDOFF}",
                "Where analysts work: the network, timeline, map, dossier and search, "
                "together in one workspace.",
                (
                    f"You are signed in as {who}."
                    if signed_in
                    else "Sign in as osprey-demo-analyst. The details are under “Signing in” below."
                ),
                "stack",
                "analysts",
            ),
            Surface(
                INGEST,
                f"{workspace}?{HANDOFF}&view=ingest",
                "Bring a new source of data in: connect it, map it, check it, publish it.",
                "It is part of The Glass, so it starts and opens together with it, on its "
                "Ingest tab.",
                "stack",
                "analysts",
                STUDIO_ROLES,
            ),
            Surface(
                ADMIN,
                f"http://localhost:{HARNESS_PORT}/",
                "Settings and set-up for the person who looks after OspreyFlow. "
                "Not needed for analysis.",
                (
                    "Sign in there with an account that holds the osprey-admin role, such as "
                    "osprey-demo-admin."
                    if signed_in
                    else "It opens on this computer only, without a sign-in."
                ),
                "admin",
                "admin",
                frozenset({ADMIN_ROLE}),
            ),
        ]

    # -- status ----------------------------------------------------------------------------

    def _within_grace(self, target: str) -> bool:
        started = self._started_at.get(target)
        return (
            started is not None
            and self._clock() - started < START_GRACE_SECONDS
            and not self._stopped(target)
        )

    def _stopped(self, target: str) -> bool:
        """The process started for this target has ended when it should not have. The console is
        meant to keep running; `docker compose up --wait` is meant to finish, so only a non-zero
        exit from it is a failure."""
        handle = self._handles.get(target)
        code = handle.poll() if handle is not None else None
        return code is not None and (target == "admin" or code != 0)

    def failure_text(self, target: str) -> str:
        """Why a start ended, in the words a person can act on; empty while nothing has failed."""
        handle = self._handles.get(target)
        if handle is None or not self._stopped(target):
            return ""
        name = ADMIN if target == "admin" else GLASS
        try:
            text = handle.log_path.read_text(encoding="utf-8", errors="replace")
            lines = [line.strip() for line in text.splitlines() if line.strip()]
        except OSError:
            lines = []
        tail = "\n".join(lines[-3:])
        if "address already in use" in tail:
            cause = (
                f"another program on this computer is already using port {HARNESS_PORT}. "
                "Close it, then press Start again."
            )
        elif lines:
            cause = f"its last log line reads: {lines[-1]}"
        else:
            cause = "it wrote nothing to its log."
        return f"{name} stopped before it was ready: {cause} The full log is {handle.log_path}."

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

    def status_for(self, identity: Identity | None) -> dict[str, str]:
        """Only the interfaces this account may see."""
        visible = {s.name for s in self.surfaces(identity) if self.can_see(s, identity)}
        return {name: state for name, state in self.status().items() if name in visible}

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
        self._handles.pop(target, None)
        try:
            for step in steps:
                handle = self._spawner(list(step.argv), cwd=self.repo_root, wait=step.wait)
                if handle is not None and not step.wait:
                    self._handles[target] = handle
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

    def _tile(
        self,
        surface: Surface,
        state: str,
        *,
        open_text: str | None = None,
        start_text: str | None = None,
        new_tab: bool = True,
    ) -> str:
        name = html.escape(surface.name)
        slug = surface.name.lower().replace(" ", "-")
        label = STATE_LABELS[state]
        shape = STATE_SHAPES[state]
        if state == "up":
            target = ' target="_blank" rel="noopener"' if new_tab else ""
            action = (
                f'<a class="btn primary" href="{html.escape(surface.url)}"{target}>'
                f"{html.escape(open_text or f'Open {surface.name}')}</a>"
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
                f'data-target="{html.escape(surface.starts)}">'
                f"{html.escape(start_text or f'Start {surface.name}')}</button>"
            )
            wait = ""
        hint = f'<p class="hint">{html.escape(surface.hint)}</p>' if surface.hint else ""
        problem = html.escape(self.failure_text(surface.starts)) if state == "down" else ""
        return f"""      <section class="tile" data-name="{name}" data-state="{state}" aria-labelledby="t-{slug}">
        <header>
          <h3 id="t-{slug}">{name}</h3>
          <span class="chip" data-state="{state}"><span class="shape" data-shape="{shape}" aria-hidden="true"></span>{label}</span>
        </header>
        <p class="purpose">{html.escape(surface.purpose)}</p>
        {hint}
        <p class="actions">{action}</p>
        {wait}<p class="message" role="status">{problem}</p>
      </section>"""  # noqa: E501

    def _signed_out_tile(self, status: dict[str, str]) -> str:
        """Before sign-in there is one tile: start OspreyFlow if it is not running (nobody can sign
        in to something that is not there), sign in if it is."""
        door = Surface(
            SIGN_IN_TILE,
            "/login",
            "Sign in to see what you can open. Each person is shown only the parts their role "
            "allows.",
            "",
            "stack",
            "everyone",
        )
        return self._tile(
            door,
            status.get(GLASS, "down"),
            open_text="Sign in",
            start_text="Start OspreyFlow",
            new_tab=False,
        )

    def render_tiles(
        self, status: dict[str, str] | None = None, identity: Identity | None = None
    ) -> str:
        status = self.status() if status is None else status
        if self.enforced and identity is None:
            return self._signed_out_tile(status)
        groups = (
            ("analysts", "For analysts"),
            ("admin", "For whoever looks after OspreyFlow"),
        )
        parts: list[str] = []
        for audience, heading in groups:
            shown = [
                s
                for s in self.surfaces(identity)
                if s.audience == audience and self.can_see(s, identity)
            ]
            if not shown:
                continue
            tiles = "\n".join(self._tile(s, status.get(s.name, "down")) for s in shown)
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

    def render_accounts(self) -> str:
        """Before sign-in: which accounts exist and where their passwords are kept. Names and file
        locations only; a password is never shown."""
        return f"""    <section class="panel" aria-labelledby="signin-title">
      <h2 id="signin-title" class="group">Signing in</h2>
      <p>This set-up has two demonstration accounts.</p>
      <p><span class="value">osprey-demo-analyst</span>, for analysts: opens The Glass and the Ingest Studio.
        <button type="button" class="btn" data-copy="osprey-demo-analyst">Copy</button></p>
      <p><span class="value">osprey-demo-admin</span>, for whoever looks after OspreyFlow: opens The Glass and the Admin console.
        <button type="button" class="btn" data-copy="osprey-demo-admin">Copy</button></p>
      <p>The passwords were created when OspreyFlow was set up and are kept in
        <span class="value">{html.escape(self.env_file_hint())}</span>, on the lines that start
        <span class="value">OSPREY_DEMO_ANALYST_PASSWORD</span> and
        <span class="value">OSPREY_DEMO_ADMIN_PASSWORD</span>. They are not shown on this page.</p>
      <p>If OspreyFlow was set up before the admin account existed, run
        <span class="value">make register-sign-in</span> once to add it.</p>
    </section>"""  # noqa: E501

    def render_who(self, identity: Identity) -> str:
        return (
            '    <p class="who">Signed in as '
            f'<span class="value">{html.escape(identity.username)}</span> '
            '<a class="btn" href="/logout">Sign out</a></p>'
        )

    def render_page(self, identity: Identity | None = None) -> str:
        mode = self.mode(identity)
        if mode == "signed-out":
            lede = (
                "Sign in to see what you can open. OspreyFlow shows each person only the parts "
                "their role allows. If it is not running yet, press Start and this page will "
                "update when it is ready."
            )
            extra = self.render_accounts()
        elif mode == "signed-in" and identity is not None:
            lede = (
                "These are the parts of OspreyFlow your account can open. If one is not running "
                "yet, press Start and this page will update when it is ready."
            )
            extra = self.render_who(identity)
        else:
            lede = (
                "OspreyFlow has two parts: the workspace where analysts work, which includes the "
                "Ingest Studio, and an Admin console for whoever looks after it. Choose what you "
                "want to use. If it is not running yet, press Start and this page will update when "
                "it is ready."
            )
            extra = self.render_signin()
        who = extra if mode == "signed-in" else ""
        signin = extra if mode != "signed-in" else ""
        return (
            _PAGE.replace("__LEDE__", html.escape(lede))
            .replace("__WHO__", who)
            .replace("__TILES__", self.render_tiles(identity=identity))
            .replace("__SIGNIN__", signin)
            .replace("__MODE__", mode)
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
  .who { margin: var(--sp-16) 0 0; font-size: var(--fs-14); line-height: var(--lh-14); }
  .message { min-height: var(--lh-14); color: var(--text-secondary); }
  .foot { margin-top: var(--sp-32); font-size: var(--fs-12); line-height: var(--lh-12); color: var(--text-tertiary); }
  .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
</style>
</head>
<body data-mode="__MODE__">
<div class="wrap">
  <main>
    <h1>OspreyFlow</h1>
    <p class="lede">__LEDE__</p>
__WHO__
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
  try {
    const reply = await fetch("/tiles");
    // The person signed in or out (or their session ended) since this page was made: start over.
    if (reply.headers.get("X-Launcher-Mode") !== document.body.dataset.mode) { location.reload(); return; }
    markup = await reply.text();
  } catch (_) { return; }
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

        def _host(self) -> str:
            return self.headers.get("Host", "")

        def _host_ok(self) -> bool:
            allowed = {f"127.0.0.1:{launcher.bound_port}", f"localhost:{launcher.bound_port}"}
            return self._host() in allowed

        def _session_token(self) -> str | None:
            jar: SimpleCookie = SimpleCookie()
            try:
                jar.load(self.headers.get("Cookie", ""))
            except Exception:  # a malformed Cookie header is no cookie
                return None
            morsel = jar.get(SESSION_COOKIE)
            return morsel.value if morsel else None

        def _login_cookie(self) -> str | None:
            jar: SimpleCookie = SimpleCookie()
            try:
                jar.load(self.headers.get("Cookie", ""))
            except Exception:
                return None
            morsel = jar.get(LOGIN_COOKIE)
            return morsel.value if morsel else None

        def _identity(self) -> Identity | None:
            return launcher.identity(self._session_token())

        def _send(
            self,
            code: int,
            body: str,
            content_type: str,
            headers: Sequence[tuple[str, str]] = (),
        ) -> None:
            data = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
            for name, value in headers:
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(data)

        def _json(self, code: int, payload: object) -> None:
            self._send(code, json.dumps(payload), "application/json")

        def _redirect(
            self, location: str, code: int = 303, cookies: Sequence[str] = ()
        ) -> None:
            self._send(
                code,
                "",
                "text/plain",
                [("Location", location), *(("Set-Cookie", c) for c in cookies)],
            )

        def _simple_page(self, code: int, title: str, body: str) -> None:
            self._send(
                code,
                "<!doctype html><html lang=\"en-GB\"><meta charset=\"utf-8\">"
                f"<title>{html.escape(title)} — OspreyFlow</title>"
                '<link rel="stylesheet" href="/tokens.css">'
                "<style>main { max-width: 62ch; margin: 0 auto; "
                "padding: var(--sp-40) var(--sp-24); }</style>"
                f"<main><h1>{html.escape(title)}</h1>{body}</main></html>",
                "text/html",
            )

        def _page_headers(self, identity: Identity | None) -> list[tuple[str, str]]:
            return [("X-Launcher-Mode", launcher.mode(identity))]

        def do_GET(self) -> None:  # noqa: N802
            if not self._host_ok():
                self._json(403, {"message": "Unexpected host name."})
                return
            parts = urllib.parse.urlsplit(self.path)
            path = parts.path
            if launcher.enforced and self._host().startswith("127.0.0.1"):
                # The sign-in redirect and the cookie are both for `localhost`; keep them together.
                target = f"http://localhost:{launcher.bound_port}{path}"
                self._redirect(target + (f"?{parts.query}" if parts.query else ""), 307)
                return
            identity = self._identity()
            if path == "/":
                self._send(
                    200, launcher.render_page(identity), "text/html", self._page_headers(identity)
                )
            elif path == "/tiles":
                self._send(
                    200,
                    launcher.render_tiles(identity=identity),
                    "text/html",
                    self._page_headers(identity),
                )
            elif path == "/tokens.css":
                css = launcher.tokens_css()
                if css is None:
                    self._json(404, {"message": "The design tokens file was not found."})
                else:
                    self._send(200, css, "text/css")
            elif path == "/status":
                if launcher.enforced and identity is None:
                    self._json(401, {"message": "Sign in first."})
                else:
                    self._json(200, launcher.status_for(identity))
            elif launcher.enforced and path == "/login":
                self._login(identity)
            elif launcher.enforced and path == "/callback":
                self._callback(urllib.parse.parse_qs(parts.query))
            elif launcher.enforced and path == "/logout":
                launcher.sessions.destroy(self._session_token())
                self._redirect(
                    launcher.sign_in_config.logout_url,
                    cookies=[f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"],
                )
            else:
                self._json(404, {"message": "Not found."})

        def _not_running_page(self) -> None:
            self._simple_page(
                503,
                "The sign-in service is not running",
                "<p>OspreyFlow did not answer, so nobody can be signed in. "
                "This is not a problem with your account.</p>"
                '<p><a href="/">Go back</a>, press Start, wait until it says it is running, '
                "then sign in.</p>",
            )

        def _login(self, identity: Identity | None) -> None:
            if identity is not None:
                self._redirect("/")
                return
            try:
                oidc.probe(launcher.sign_in_config)
            except IdentityProviderUnreachable:
                self._not_running_page()
                return
            url, state = launcher.attempts.begin(launcher.sign_in_config)
            self._redirect(
                url,
                cookies=[f"{LOGIN_COOKIE}={state}; Path=/; HttpOnly; SameSite=Lax; Max-Age=600"],
            )

        def _callback(self, query: dict[str, list[str]]) -> None:
            outcome = handle_callback(
                launcher.sign_in_config,
                launcher.attempts,
                code=_first(query, "code"),
                state=_first(query, "state"),
                error=_first(query, "error"),
                login_cookie=self._login_cookie(),
            )
            again = '<p><a href="/login">Start again</a></p>'
            if outcome.kind == "invalid_link":
                self._simple_page(400, "This sign-in link is not valid", again)
            elif outcome.kind == "not_completed":
                self._simple_page(403, "Sign-in was not completed", again)
            elif outcome.kind == "unreachable":
                self._not_running_page()
            elif outcome.kind == "refused" or outcome.identity is None:
                self._simple_page(403, "Sign-in was refused", again)
            else:
                # Any account that signs in gets a session; which tiles it sees is decided by its
                # roles, and what each interface allows is decided by that interface itself.
                token = launcher.sessions.create(outcome.identity)
                self._redirect(
                    "/",
                    cookies=[
                        f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax",
                        f"{LOGIN_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0",
                    ],
                )

        def do_POST(self) -> None:  # noqa: N802
            if not self._host_ok():
                self._json(403, {"message": "Unexpected host name."})
                return
            token = self.headers.get("X-Launch-Token", "")
            if not secrets.compare_digest(token, launcher.token):
                self._json(403, {"message": "This request did not come from the launcher page."})
                return
            origin = self.headers.get("Origin")
            if origin is not None and origin != f"http://{self._host()}":
                self._json(403, {"message": "This request came from another site."})
                return
            prefix = "/start/"
            if not self.path.startswith(prefix):
                self._json(404, {"message": "Not found."})
                return
            target = self.path[len(prefix) :]
            if launcher.enforced and target == "admin":
                identity = self._identity()
                if identity is None or not identity.has_role(ADMIN_ROLE):
                    self._json(
                        403,
                        {"message": "Starting the Admin console needs an administrator account."},
                    )
                    return
            try:
                launcher.start_in_background(target)
            except KeyError:
                self._json(404, {"message": "Not found."})
            except LaunchError as err:
                self._json(409, {"message": str(err)})
            else:
                self._json(202, {"message": "Started. This tile updates when it is ready."})

    return Handler


def _first(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    return values[0] if values else None


def port_problem(port: int, *, enforced: bool) -> str | None:
    """Sign-in redirects to one exact address, so another port could never complete it."""
    if enforced and port != LAUNCHER_PORT:
        return (
            f"sign-in is required and the identity provider only redirects to port "
            f"{LAUNCHER_PORT}; start the launcher on {LAUNCHER_PORT}, not {port}"
        )
    return None


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
    problem = port_problem(args.port, enforced=launcher.enforced)
    if problem:
        sys.stderr.write(f"launcher: {problem}\n")
        return 2
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
    if launcher.enforced:
        sys.stdout.write("Sign-in is required; the identity provider must be running.\n")
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
