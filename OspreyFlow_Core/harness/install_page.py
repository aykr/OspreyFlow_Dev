"""The guided install page (`06_DECISIONS.md` ADR-114 Amendment 3, decision 6; stage B2c).

`ospreyflow install --gui` serves the Set-up console's own screens (`apps/harness`) on `127.0.0.1`
at a free port behind a one-time token, only while an install runs, then it is gone. This module is
the server for that page. It is built on `harness.webapp.create_app` so the existing `/api/config`,
`/api/profile-options`, `/api/model-choices`, `/api/consequences`, governance and geospatial routes
work unchanged — against a DRAFT `osprey.yaml`, never the product's own — and adds four routes of
its own:

| Route | What it is |
| --- | --- |
| `GET /api/install/state` | the saved answers, the demo packs, and which modes install here |
| `PUT /api/install/answers` | the answers, checked by `load_answers`, then saved |
| `GET /api/install/doctor` | `ospreyflow doctor --mode <mode>`, its lines and exit code |
| `POST /api/install/run` | Lite only: `ospreyflow install --config <answers>`, streamed |

**The token.** The link `ospreyflow` prints carries a one-time token. The first request,
`GET /?token=<t>`, sets an HttpOnly, SameSite=Strict cookie and redirects to `/`; every other
request needs that cookie or an `X-Install-Token` header, and is otherwise refused in a sentence.
The comparison is `hmac.compare_digest`. The middleware is the outermost, so it covers every route
the console adds or will add. An install has no identity provider yet, so the console's own sign-in
(`require_sign_in=False`) is never turned on, whatever is rendered.

**Small and Enterprise save their answers and say when they arrive** (stages B6 and B7); there is
never a button that silently does nothing. Lite installs: the page runs the command's own
redactor over every line it shows, and shuts itself down when the install ends.
"""

from __future__ import annotations

import argparse
import asyncio
import hmac
import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import yaml
from fastapi import Body, FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from starlette.routing import Mount

# The command lives in `cli/` (it is a `uv` tool, not part of this package's environment); making
# the page self-sufficient means it works however it was started.
_CLI = str(Path(__file__).resolve().parents[1] / "cli")
if _CLI not in sys.path:
    sys.path.append(_CLI)

from ospreyflow.answers import AnswersRefused, load_answers  # noqa: E402
from ospreyflow.home import deployment_dir, python_for  # noqa: E402
from ospreyflow.run import Redactor  # noqa: E402

from harness.webapp import create_app  # noqa: E402

COOKIE = "osprey_install"
HEADER = "X-Install-Token"
REFUSED = "This install page opens only from the link ospreyflow printed."
LOOPBACK = "127.0.0.1"
MODE_SAYS = {
    "small": (
        "Your answers are saved. A small server is built from a terminal on this computer: "
        "ospreyflow install --mode small --cloud aws (or azure) --config .install/install.yaml"
    ),
    "enterprise": "The enterprise install arrives with stage B7. Your answers are saved for it.",
}
_ALREADY = "The install is already running."
_NO_ANSWERS = "Save your answers first: the install runs from them."


def install_argv(product: Path, answers: Path) -> list[str]:
    """The Lite install the page runs: the command itself, from the saved answers. `--force` is safe
    because the draft started as a copy of the product's own `osprey.yaml` and every change to it
    was made on these screens."""
    return [
        *python_for(product), "-m", "ospreyflow", "install", "--mode", "lite",
        "--config", str(answers), "--yes", "--force",
    ]  # fmt: skip


def doctor_argv(product: Path) -> list[str]:
    return [*python_for(product), "-m", "ospreyflow", "doctor"]


def _child_env(product: Path) -> dict[str, str]:
    cli = str(product / "cli")
    existing = os.environ.get("PYTHONPATH")
    return {
        **os.environ,
        "PYTHONPATH": f"{cli}{os.pathsep}{existing}" if existing else cli,
        "OSPREYFLOW_HOME": str(product),
        "PYTHONUNBUFFERED": "1",
    }


def _pack_rows() -> list[dict[str, Any]]:
    from scripts.demo_packs import packs

    return [
        {
            "id": p.id,
            "title": p.title,
            "shows": p.shows,
            "delivery": p.delivery,
            "licence": p.licence,
        }
        for p in packs()
    ]


def _redactor(product: Path) -> Redactor:
    try:
        env_file = deployment_dir(product) / "deployment.env"
    except Exception:  # noqa: BLE001 - a notice's path must never stop an install being shown
        env_file = product / "deploy" / "generated" / "deployment.env"
    return Redactor(env_file)


def _saved(answers_path: Path) -> dict[str, Any]:
    try:
        loaded = yaml.safe_load(answers_path.read_text(encoding="utf-8")) or {}
    except OSError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _event(payload: dict[str, Any], name: str | None = None) -> bytes:
    head = f"event: {name}\n" if name else ""
    return f"{head}data: {json.dumps(payload)}\n\n".encode()


def create_install_app(
    *,
    product: Path,
    token: str,
    draft_config: Path,
    answers_path: Path,
    install_command: Callable[[Path], list[str]],
    doctor_command: list[str],
    packs: list[dict[str, Any]],
    shutdown: Callable[[], None],
) -> FastAPI:
    scratch = draft_config.parent
    app = create_app(
        mode="setup",
        config_path=draft_config,
        # Nothing on these screens may reach the product's own rendered output or the owner's own
        # real-data exceptions list; the console's defaults for both are those real files.
        out_root=scratch / "generated",
        real_data_exceptions_path=scratch / "real-data-exceptions.yaml",
        require_sign_in=False,
    )
    app.state.running = False
    app.state.last_seen = time.monotonic()
    pack_ids = [str(p["id"]) for p in packs]
    secret = token.encode("utf-8")

    def matches(supplied: str | None) -> bool:
        return supplied is not None and hmac.compare_digest(supplied.encode("utf-8"), secret)

    def refused() -> PlainTextResponse:
        return PlainTextResponse(REFUSED, status_code=403)

    @app.middleware("http")
    async def token_gate(request: Request, call_next):  # type: ignore[no-untyped-def]
        app.state.last_seen = time.monotonic()  # any request, even a refused one, is use
        if request.method == "GET" and request.url.path == "/" and "token" in request.query_params:
            if not matches(request.query_params["token"]):
                return refused()
            reply = RedirectResponse("/", status_code=303)
            reply.set_cookie(COOKIE, token, httponly=True, samesite="strict", path="/")
            return reply
        if matches(request.cookies.get(COOKIE)) or matches(request.headers.get(HEADER)):
            return await call_next(request)
        return refused()

    def mode_now() -> str:
        return str(_saved(answers_path).get("mode") or "lite")

    def state() -> dict[str, Any]:
        answers = {k: v for k, v in _saved(answers_path).items() if k != "config"}
        return {
            "mode": mode_now(),
            "answers": answers,
            "packs": packs,
            "home": str(Path.home()),
            "modes": {
                "lite": {"available": True},
                "small": {"available": False, "says": MODE_SAYS["small"]},
                "enterprise": {"available": False, "says": MODE_SAYS["enterprise"]},
            },
        }

    @app.get("/api/install/state")
    def get_state() -> dict[str, Any]:
        return state()

    @app.put("/api/install/answers", response_model=None)
    def put_answers(body: Any = Body(...)) -> Any:
        if not isinstance(body, dict):
            return JSONResponse({"error": "The answers are a set of settings."}, status_code=422)
        raw = {k: v for k, v in body.items() if v not in (None, "", [], {})}
        raw["config"] = str(draft_config)  # the draft, as the screens left it, is used as it is
        try:
            load_answers(raw, packs=pack_ids)
        except AnswersRefused as refusal:
            return JSONResponse({"error": str(refusal)}, status_code=422)
        answers_path.parent.mkdir(parents=True, exist_ok=True)
        answers_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
        return state()

    @app.get("/api/install/doctor")
    def get_doctor() -> dict[str, Any]:
        try:
            done = subprocess.run(
                [*doctor_command, "--mode", mode_now()],
                cwd=product,
                env=_child_env(product),
                capture_output=True,
                text=True,
                errors="replace",
                check=False,
                timeout=120,
            )
        except (OSError, subprocess.SubprocessError) as failed:
            return {"lines": [f"The doctor could not be run: {failed}"], "returncode": 127}
        text = "\n".join(t for t in (done.stdout, done.stderr) if t)
        return {"lines": text.splitlines(), "returncode": done.returncode}

    async def run_events(argv: list[str]) -> AsyncIterator[bytes]:
        redact = _redactor(product)
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(product),
                env=_child_env(product),
            )
        except OSError as failed:
            yield _event({"line": f"The install could not be started: {failed}"})
            yield _event({"returncode": 127}, "complete")
            app.state.running = False
            shutdown()
            return
        assert process.stdout is not None
        try:
            async for raw_line in process.stdout:
                line = redact(raw_line.decode(errors="replace").rstrip("\r\n"))
                yield _event({"line": line})
            returncode = await process.wait()
            yield _event({"returncode": returncode}, "complete")
        except BaseException:
            # The page was closed mid-install. The install itself is not cut off half way; it is
            # left to finish (its output drained, so it never blocks) and then the page goes.
            asyncio.ensure_future(_finish(process))
            raise
        app.state.running = False
        shutdown()  # the page is gone after the install

    async def _finish(process: asyncio.subprocess.Process) -> None:
        assert process.stdout is not None
        try:
            async for _ in process.stdout:
                pass
            await process.wait()
        finally:
            app.state.running = False
            shutdown()

    @app.post("/api/install/run", response_model=None)
    def post_run() -> Any:
        saved = _saved(answers_path)
        if not saved:
            return JSONResponse({"error": _NO_ANSWERS}, status_code=409)
        mode = str(saved.get("mode") or "lite")
        if mode in MODE_SAYS:
            return JSONResponse({"error": MODE_SAYS[mode]}, status_code=409)
        if app.state.running:
            return JSONResponse({"error": _ALREADY}, status_code=409)
        app.state.running = True
        return StreamingResponse(
            run_events(install_command(answers_path)), media_type="text/event-stream"
        )

    # `create_app` mounts the built frontend at `/` before returning, which would shadow the routes
    # added above; the mount goes last, as it would had they been registered first.
    routes = app.router.routes
    mounts = [r for r in routes if isinstance(r, Mount)]
    for mount in mounts:
        routes.remove(mount)
        routes.append(mount)
    return app


def idle_check(
    app: FastAPI, *, minutes: float, now: Callable[[], float] = time.monotonic
) -> Callable[[], bool]:
    """A function that says whether the page has had no request for `minutes`."""

    def idle() -> bool:
        return (now() - float(app.state.last_seen)) >= minutes * 60

    return idle


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m harness.install_page",
        description="The guided install page. Started by `ospreyflow install --gui`; binds "
        "127.0.0.1 only.",
    )
    parser.add_argument("--product", type=Path, required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--idle-minutes", type=float, default=30)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    import uvicorn

    args = _parse_args(sys.argv[1:] if argv is None else argv)
    holder: dict[str, Any] = {}

    def shutdown() -> None:
        server = holder.get("server")
        if server is not None:
            server.should_exit = True

    app = create_install_app(
        product=args.product,
        token=args.token,
        draft_config=args.draft,
        answers_path=args.answers,
        install_command=lambda answers: install_argv(args.product, answers),
        doctor_command=doctor_argv(args.product),
        packs=_pack_rows(),
        shutdown=shutdown,
    )
    server = uvicorn.Server(uvicorn.Config(app, host=LOOPBACK, port=args.port, log_level="warning"))
    holder["server"] = server

    done = threading.Event()
    idle = idle_check(app, minutes=args.idle_minutes)

    def watch() -> None:
        while not done.wait(5.0):
            if idle():
                shutdown()
                return

    threading.Thread(target=watch, daemon=True).start()
    try:
        server.run()
    finally:
        done.set()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
