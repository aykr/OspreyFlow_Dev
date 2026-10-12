"""The `ospreyflow` command (`06_DECISIONS.md` ADR-114 Amendment 3, stage B2b).

A small command over the harness: it decides nothing about what a deployment is. Rendering,
preflight, build, up and verify stay in `harness.apply`; this runs them inside the checkout's own
environment, drives `docker compose` against the rendered deployment, and says what happened in
words. Every outside dependency (the runner, the machine probes, the prompt, the browser) is
injectable, which is how the tests drive it without Docker.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import webbrowser
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

import yaml

from . import demo
from .answers import MODES, Answers, AnswersRefused, load_answers, osprey_config
from .doctor import Check, Probes, SystemProbes, format_check, run_doctor
from .home import (
    CommandRefused,
    deployment_dir,
    find_product,
    public_origin,
    python_for,
    read_config,
    read_recorded_home,
)
from .run import (
    Capture,
    Redactor,
    Runner,
    StepFailed,
    SubprocessRunner,
    compose,
    subprocess_capture,
)

VERBS = (
    "doctor", "install", "start", "stop", "status", "open", "logs", "demo", "backup", "restore",
    "uninstall",
)  # fmt: skip
_NOT_INSTALLED = "Nothing is installed here yet — run ospreyflow install."
_STAGE = {"small": "B6", "enterprise": "B7"}

Ask = Callable[[str, str], str]


class PageProcess(Protocol):
    """The guided page's server, as far as the command cares: it can be waited for."""

    def wait(self) -> int: ...


class StartServer(Protocol):
    def __call__(
        self, argv: Sequence[str], *, env: Mapping[str, str], cwd: Path
    ) -> PageProcess: ...


def _start_server(argv: Sequence[str], *, env: Mapping[str, str], cwd: Path) -> PageProcess:
    return subprocess.Popen(list(argv), cwd=cwd, env={**os.environ, **env})


def _free_port() -> int:
    """A port nothing is listening on, asked of the system (bind 0, read it, close)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _ask(prompt: str, default: str = "") -> str:
    reply = input(f"{prompt} [{default}] " if default else f"{prompt} ").strip()
    return reply or default


def _yes(reply: str) -> bool:
    return reply.strip().lower() in ("y", "yes")


class _Context:
    """What a verb needs, resolved once."""

    def __init__(
        self,
        product: Path,
        env: Mapping[str, str],
        run: Runner,
        capture: Capture,
        probes: Probes,
        ask: Ask,
        open_url: Callable[[str], object],
        start_server: StartServer = _start_server,
        free_port: Callable[[], int] = _free_port,
    ) -> None:
        self.start_server = start_server
        self.free_port = free_port
        self.product = product
        self.env = env
        # Every step runs a module of the checkout (`harness.*`, `scripts.*`), which imports the
        # checkout's own packages (`schemas`, `ports`), as the Makefile's `PYTHONPATH=.:packages`
        # allowed. Found running `ospreyflow backup` for B2e: without it the first import failed.
        # Given to every step, so no verb can forget it.
        importable = {"PYTHONPATH": os.pathsep.join((str(product), str(product / "packages")))}

        def run_in_checkout(
            argv: Sequence[str], *, env: Mapping[str, str] | None = None, cwd: Path | None = None
        ) -> int:
            return run(argv, env={**importable, **(env or {})}, cwd=cwd)

        def capture_in_checkout(
            argv: Sequence[str], *, env: Mapping[str, str] | None = None, cwd: Path | None = None
        ) -> tuple[int, str]:
            return capture(argv, env={**importable, **(env or {})}, cwd=cwd)

        self.run: Runner = run_in_checkout
        self.capture: Capture = capture_in_checkout
        self.probes = probes
        self.ask = ask
        self.open_url = open_url
        self.python = python_for(product)

    @property
    def deployment(self) -> Path:
        return deployment_dir(self.product)

    def deployed(self) -> Path:
        directory = self.deployment
        if not (directory / "compose.yaml").is_file():
            raise CommandRefused(_NOT_INSTALLED)
        return directory

    def step(self, name: str, argv: Sequence[str], **kwargs: Any) -> None:
        code = self.run(list(argv), cwd=self.product, **kwargs)
        if code != 0:
            raise StepFailed(name, code)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ospreyflow",
        description="Install, run and look after an OspreyFlow deployment.",
    )
    verbs = parser.add_subparsers(dest="verb", required=True, metavar="VERB")

    doctor = verbs.add_parser("doctor", help="check the machine's prerequisites")
    doctor.add_argument("--mode", choices=MODES, default="lite")
    doctor.add_argument("--cloud", choices=("aws", "azure"))

    install = verbs.add_parser("install", help="install a deployment")
    install.add_argument("--mode", choices=MODES, required=True)
    install.add_argument("--config", type=Path, help="an answers file (install.yaml)")
    install.add_argument("--yes", action="store_true", help="ask nothing; take the defaults")
    install.add_argument("--force", action="store_true", help="replace a different osprey.yaml")
    install.add_argument("--no-demo-accounts", action="store_true")
    install.add_argument("--gui", action="store_true", help="answer on a guided page")

    start = verbs.add_parser("start", help="bring the deployment up")
    start.add_argument("--build", action="store_true", help="rebuild from the checkout first")
    verbs.add_parser("stop", help="stop the deployment")
    verbs.add_parser("status", help="say each service's state")
    verbs.add_parser("open", help="open the Glass in the browser")

    logs = verbs.add_parser("logs", help="show service logs")
    logs.add_argument("service", nargs="?")
    logs.add_argument("--follow", action="store_true")
    logs.add_argument("--tail", type=int, default=200)

    demo_verb = verbs.add_parser("demo", help="list or add demo packs")
    actions = demo_verb.add_subparsers(dest="action", required=True, metavar="ACTION")
    actions.add_parser("list", help="the demo packs")
    add = actions.add_parser("add", help="add a demo pack")
    add.add_argument("pack")
    add.add_argument("--file", type=Path, help="the PaySim download")

    verbs.add_parser("backup", help="back up every store (arguments go to harness.backup)")
    verbs.add_parser("restore", help="restore a backup (arguments go to harness.restore)")

    uninstall = verbs.add_parser("uninstall", help="remove the deployment")
    uninstall.add_argument("--keep-data", action="store_true")
    uninstall.add_argument("--yes", action="store_true")
    return parser


# ---- verbs -------------------------------------------------------------------------------------


def _print_checks(checks: list[Check]) -> bool:
    for check in checks:
        print(format_check(check))
    return all(check.ok for check in checks)


def _doctor(args: argparse.Namespace, probes: Probes, product: Path) -> int:
    ok = _print_checks(run_doctor(args.mode, probes, product=product, cloud=args.cloud))
    return 0 if ok else 1


def _prompted_answers(ctx: _Context, mode: str, packs: Sequence[str]) -> dict[str, Any]:
    raw: dict[str, Any] = {"mode": mode}
    raw["components"] = {
        "dashboards": _yes(ctx.ask("Turn on dashboards (Superset and report sync)? [Y/n]", "y"))
    }
    if mode == "lite":
        raw["folders"] = {
            "ingest": ctx.ask("Folder the Ingest Studio lists", "~/OspreyFlow/ingest"),
            "tiles": ctx.ask("Folder for the basemap", "~/OspreyFlow/basemap"),
        }
    else:
        raw["cloud"] = {
            "provider": ctx.ask("Cloud (aws or azure)", "aws"),
            "region": ctx.ask("Region", ""),
            "domain": ctx.ask("Domain name you control", ""),
        }
    chosen = [
        p.strip()
        for p in ctx.ask(
            f"Demo packs to load, separated by commas ({', '.join(packs)}); blank for none", ""
        ).split(",")
        if p.strip()
    ]
    if chosen:
        raw["demo_packs"] = chosen
    if "paysim" in chosen:
        raw["paysim_file"] = ctx.ask("Where is the PaySIM download?", "")
    return {k: v for k, v in raw.items() if v != ""}


def _raw_answers(args: argparse.Namespace, ctx: _Context, packs: Sequence[str]) -> dict[str, Any]:
    if args.config is not None:
        path = args.config.expanduser()
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except OSError as unreadable:
            raise CommandRefused(f"Could not read {path}: {unreadable.strerror}.") from unreadable
        if not isinstance(loaded, dict):
            raise AnswersRefused(f"{path} does not hold settings")
        if loaded.setdefault("mode", args.mode) != args.mode:
            raise AnswersRefused(
                f"{path} says mode {loaded['mode']}, but --mode {args.mode} was given; "
                "they must agree"
            )
        return loaded
    if args.yes:
        return {"mode": args.mode}
    return _prompted_answers(ctx, args.mode, packs)


def _write_config(ctx: _Context, answers: Answers, force: bool) -> None:
    path = ctx.product / "osprey.yaml"
    config = osprey_config(answers, read_config(ctx.product))
    if config == read_config(ctx.product):
        return  # what the answers make is what is there, or the owner's own file used as it is
    if not force:
        raise CommandRefused(
            f"{path} already exists and differs from what these answers make. Nothing was "
            "changed; run again with --force to replace it, or put your settings in the answers "
            "file (or name your own file there with config:)."
        )
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    print(f"Wrote {path}.")


def _gui(ctx: _Context) -> int:
    """The guided page (ADR-114 Amendment 3, decision 6): the Set-up console's screens, served on
    127.0.0.1 at a free port behind a one-time token, working on a draft copy of `osprey.yaml`, for
    as long as the install lasts. The doctor is not run first: the page runs it on its Review
    screen, where a failure can be shown beside its fix."""
    scratch = ctx.product / ".install"
    scratch.mkdir(exist_ok=True)
    draft = scratch / "osprey.draft.yaml"
    shutil.copyfile(ctx.product / "osprey.yaml", draft)
    token = secrets.token_urlsafe(32)
    port = ctx.free_port()
    paths = os.pathsep.join(str(ctx.product / name) for name in ("cli", "packages", ""))
    server = ctx.start_server(
        [
            *ctx.python, "-m", "harness.install_page",
            "--product", str(ctx.product),
            "--token", token,
            "--port", str(port),
            "--draft", str(draft),
            "--answers", str(scratch / "install.yaml"),
        ],
        env={"PYTHONPATH": paths.rstrip(os.pathsep), "OSPREYFLOW_HOME": str(ctx.product)},
        cwd=ctx.product,
    )  # fmt: skip
    link = f"http://127.0.0.1:{port}/?token={token}"
    ctx.open_url(link)
    print("The install page is open in your browser. If it did not open, use this link:")
    print(f"  {link}")
    print(
        "It works only from this link and only on this computer. Closing this window or pressing "
        "Ctrl+C ends the install page; it also closes itself when the install finishes."
    )
    try:
        return server.wait()
    except KeyboardInterrupt:
        stop = getattr(server, "terminate", None)
        if callable(stop):
            stop()
        print("The install page was closed.")
        return 130


def _install(args: argparse.Namespace, ctx: _Context) -> int:
    if args.gui:
        return _gui(ctx)
    if not _print_checks(run_doctor(args.mode, ctx.probes, product=ctx.product)):
        print("Nothing was installed. Fix the above and run ospreyflow install again.")
        return 1
    packs = demo.pack_ids(ctx.product, ctx.capture)
    raw = _raw_answers(args, ctx, packs)
    answers = load_answers(raw, packs=packs)

    if args.mode != "lite":
        target = ctx.product / "install.yaml"
        target.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
        print(
            f"Your answers are saved in {target}. The {args.mode} install arrives with stage "
            f"{_STAGE[args.mode]}; nothing was installed."
        )
        return 0

    _write_config(ctx, answers, args.force)
    apply = [*ctx.python, "-m", "harness.apply", "--build"]
    if not args.no_demo_accounts:
        apply.append("--demo-analyst")
    ctx.step("build and start the deployment", apply)
    if not args.no_demo_accounts:
        ctx.step("register the sign-in", [*ctx.python, "-m", "harness.register_sign_in"])
    for pack in answers.demo_packs:
        file = answers.paysim_file if pack == "paysim" else None
        demo.add_pack(ctx.product, ctx.run, ctx.env, pack, file)

    print()
    print(f"OspreyFlow is installed. Open it at {public_origin(ctx.product)}")
    print(f"Sign in with the accounts in {ctx.deployment / 'deployment.env'}")
    print("Look after it with: ospreyflow status, ospreyflow open")
    return 0


def _start(args: argparse.Namespace, ctx: _Context) -> int:
    directory = ctx.deployed()
    if args.build:
        ctx.step("rebuild from the checkout", [*ctx.python, "-m", "scripts.refresh"])
    else:
        ctx.step("start the deployment", [*compose(directory), "up", "-d", "--wait"])
    return 0


def _stop(ctx: _Context) -> int:
    ctx.step("stop the deployment", [*compose(ctx.deployed()), "stop"])
    return 0


def _services(text: str) -> list[dict[str, Any]]:
    stripped = text.strip()
    if not stripped:
        return []
    if stripped.startswith("["):  # older Compose prints one array
        loaded = json.loads(stripped)
        return [row for row in loaded if isinstance(row, dict)]
    return [json.loads(line) for line in stripped.splitlines() if line.strip()]


def _status(ctx: _Context) -> int:
    directory = ctx.deployed()
    code, output = ctx.capture(
        [*compose(directory), "ps", "--all", "--format", "json"], cwd=ctx.product
    )
    if code != 0:
        print("Could not ask Docker about the deployment. Is Docker running?", file=sys.stderr)
        return 1
    try:
        rows = _services(output)
    except ValueError:
        print("Docker answered in a form this command does not understand.", file=sys.stderr)
        return 1
    if not rows:
        print("Nothing is running. Start it with ospreyflow start.")
        return 1
    healthy = True
    for row in sorted(rows, key=lambda r: str(r.get("Service", ""))):
        state, health = str(row.get("State", "unknown")), str(row.get("Health") or "")
        print(f"{row.get('Service', '?')}: {state}" + (f", {health}" if health else ""))
        healthy &= state == "running" and health in ("", "healthy")
    return 0 if healthy else 1


def _logs(args: argparse.Namespace, ctx: _Context) -> int:
    argv = [*compose(ctx.deployed()), "logs"]
    if args.follow:
        argv.append("--follow")
    argv += ["--tail", str(args.tail)]
    if args.service:
        argv.append(args.service)
    return ctx.run(argv, cwd=ctx.product)


def _uninstall(args: argparse.Namespace, ctx: _Context) -> int:
    directory = ctx.deployed()
    kept = "Your checkout, osprey.yaml and your own folders are never touched."
    if args.keep_data:
        what = f"This removes the OspreyFlow containers; the stored data volumes are kept. {kept}"
    else:
        what = (
            "This removes the OspreyFlow containers and the stored data volumes (cases, "
            f"accounts, search indexes). {kept}"
        )
    if not args.yes and not _yes(ctx.ask(f"{what} Continue? [y/N]", "n")):
        print("Nothing was removed.")
        return 1
    ctx.step(
        "remove the deployment",
        [*compose(directory), "down", *([] if args.keep_data else ["-v"])],
    )
    return 0


def _dispatch(args: argparse.Namespace, ctx: _Context) -> int:
    verb = args.verb
    if verb == "install":
        return _install(args, ctx)
    if verb == "start":
        return _start(args, ctx)
    if verb == "stop":
        return _stop(ctx)
    if verb == "status":
        return _status(ctx)
    if verb == "open":
        address = public_origin(ctx.product)
        ctx.open_url(address)
        print(f"Opening {address}")
        return 0
    if verb == "logs":
        return _logs(args, ctx)
    if verb == "demo":
        if args.action == "list":
            return demo.list_packs(ctx.product, ctx.run)
        demo.add_pack(ctx.product, ctx.run, ctx.env, args.pack, args.file)
        return 0
    if verb == "uninstall":
        return _uninstall(args, ctx)
    raise AssertionError(verb)  # pragma: no cover - argparse refuses any other verb


def main(
    argv: Sequence[str] | None = None,
    *,
    runner: Runner | None = None,
    probes: Probes | None = None,
    home_env: Mapping[str, str] | None = None,
    recorded_home: Callable[[], Path | None] = read_recorded_home,
    capture: Capture | None = None,
    ask: Ask = _ask,
    open_url: Callable[[str], object] = webbrowser.open,
    start: Path | None = None,
    start_server: StartServer = _start_server,
    free_port: Callable[[], int] = _free_port,
) -> int:
    args_in = list(sys.argv[1:] if argv is None else argv)
    if args_in and args_in[0].startswith("--") and args_in[0][2:] in VERBS:
        args_in[0] = args_in[0][2:]  # `--install` is `install`
    env = os.environ if home_env is None else home_env

    passthrough: list[str] = []
    if args_in and args_in[0] in ("backup", "restore"):
        args_in, passthrough = args_in[:1], args_in[1:]
    try:
        args = _parser().parse_args(args_in)
    except SystemExit as stop:
        return stop.code if isinstance(stop.code, int) else 2

    try:
        try:
            product = find_product(start, env, recorded=recorded_home)
        except CommandRefused:
            if args.verb != "doctor":
                raise
            product = Path.cwd()
        directory = deployment_dir(product) if (product / "osprey.yaml").is_file() else product
        real_probes = probes or SystemProbes(
            compose(directory) if (directory / "compose.yaml").is_file() else None
        )
        if args.verb == "doctor":
            return _doctor(args, real_probes, product)
        ctx = _Context(
            product,
            env,
            runner or SubprocessRunner(Redactor(directory / "deployment.env")),
            capture or subprocess_capture,
            real_probes,
            ask,
            open_url,
            start_server,
            free_port,
        )
        if args.verb in ("backup", "restore"):
            module = f"harness.{args.verb}"
            return ctx.run([*ctx.python, "-m", module, *passthrough], cwd=product)
        return _dispatch(args, ctx)
    except (CommandRefused, AnswersRefused) as refusal:
        print(f"ospreyflow: {refusal}", file=sys.stderr)
        return 1
    except StepFailed as failed:
        print(f"ospreyflow: {failed}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
