"""The `ospreyflow` command (`06_DECISIONS.md` ADR-114 Amendment 3, stage B2b).

A small command over the harness: it decides nothing about what a deployment is. Rendering,
preflight, build, up and verify stay in `harness.apply`; this runs them inside the checkout's own
environment, drives `docker compose` against the rendered deployment, and says what happened in
words. Every outside dependency (the runner, the machine probes, the prompt, the browser) is
injectable, which is how the tests drive it without Docker.
"""

from __future__ import annotations

import argparse
import dataclasses
import getpass
import json
import os
import re
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

from . import demo, starters
from . import deployments as named
from . import models as engine_keys
from .answers import (
    MODES,
    ORGANISATION_SECRET_VARIABLE,
    Answers,
    AnswersRefused,
    load_answers,
    osprey_config,
)
from .cloud import build_enterprise, build_small
from .doctor import (
    Check,
    GpuPlan,
    Probes,
    ServerPlan,
    SystemProbes,
    format_check,
    TRUST_EMAIL_FIX,
    TRUST_EMAIL_SAYS,
    gpu_checks,
    gpu_plan,
    joins_by_email,
    run_doctor,
)
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
    "update", "uninstall", "repair-sign-in", "switch", "models", "apply", "deployments",
    "starters",
)  # fmt: skip
_NOT_INSTALLED = "Nothing is installed here yet — run ospreyflow install."

Ask = Callable[[str, str], str]
#: A prompt whose answer is not shown as it is typed (a model provider's key, ADR-135).
AskSecret = Callable[[str], str]


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
        ask_secret: AskSecret = getpass.getpass,
        target: named.Target | None = None,
    ) -> None:
        #: ADR-138: the deployment the verb acts on — `default` (the checkout's) or one by name.
        self.target = target or named.default_target(product)
        #: A new deployment's address and graph-store port, chosen before anything is written.
        self.named_install: tuple[str, int] = ("", 0)
        self.ask_secret = ask_secret
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
        return self.target.rendered if self.target.named else deployment_dir(self.product)

    @property
    def config_path(self) -> Path:
        """The target's `osprey.yaml`: the checkout's, or its own folder's (ADR-138)."""
        return self.target.config_path

    def origin(self) -> str:
        return self.target.origin() if self.target.named else public_origin(self.product)

    def named_args(self, out_flag: str = "--out-root") -> list[str]:
        """For a step of the checkout's own, the arguments that point it at a deployment kept by
        name: its `osprey.yaml` and the folder it is rendered under. None for `default`, so the
        checkout's deployment runs every step exactly as before."""
        if not self.target.named:
            return []
        return ["--config", str(self.config_path), out_flag, str(self.target.rendered.parent)]

    def named_env(self) -> dict[str, str]:
        """For a script that finds the deployment itself (`scripts.refresh`, the seeds)."""
        if not self.target.named:
            return {}
        return {"OSPREYFLOW_DEPLOYMENT_DIR": str(self.target.rendered)}

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
    # ADR-138 decision 2: every verb acts on one deployment, chosen by name.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        # SUPPRESS, so a nested parser (`demo add`) given no --name keeps the one given before it.
        "--name", dest="deployment_name", default=argparse.SUPPRESS,
        help="the deployment to act on: one installed with --name, or 'default' (the checkout's); "
        "default: the only one, or the one last used",
    )  # fmt: skip
    original = verbs.add_parser

    def add_parser(name: str, **kwargs: Any) -> argparse.ArgumentParser:
        return original(name, parents=[common], **kwargs)

    verbs.add_parser = add_parser  # type: ignore[method-assign]

    doctor = verbs.add_parser("doctor", help="check the machine's prerequisites")
    doctor.add_argument("--mode", choices=MODES, default="lite")
    doctor.add_argument("--cloud", choices=("aws", "azure"))
    doctor.add_argument(
        "--config", type=Path,
        help="small, on a server of your own: the answers file whose server: section to check",
    )  # fmt: skip

    install = verbs.add_parser("install", help="install a deployment")
    install.add_argument("--mode", choices=MODES)
    # ADR-138 decision 1: a theme and a domain, pre-filling the answers.
    install.add_argument(
        "--starter", metavar="THEME-DOMAIN", help="a starter (ospreyflow starters)"
    )
    install.add_argument(
        "--list-starters", action="store_true", help="list the starters; install nothing"
    )
    install.add_argument("--service-name", help="GOV.UK: the service's name, in the page title")
    install.add_argument("--organisation", help="GOV.UK: the organisation in its footer")
    install.add_argument("--phase", choices=starters.PHASES, help="GOV.UK: the phase banner")
    install.add_argument(
        "--address", help="with --name: the address it answers at (default "
        "http://<name>.localhost:<next free port>)",
    )  # fmt: skip
    install.add_argument("--config", type=Path, help="an answers file (install.yaml)")
    install.add_argument("--yes", action="store_true", help="ask nothing; take the defaults")
    install.add_argument("--force", action="store_true", help="replace a different osprey.yaml")
    install.add_argument("--no-demo-accounts", action="store_true")
    install.add_argument("--gui", action="store_true", help="answer on a guided page")
    install.add_argument(
        "--chart-values", type=Path, action="append", default=[],
        help="enterprise: a site's own Helm values, applied over the rendered ones",
    )  # fmt: skip
    install.add_argument(
        "--build", action="store_true", help="build from this checkout even on a release tag"
    )
    install.add_argument(
        "--cloud", choices=("aws", "azure"),
        help="small or enterprise: build the server or cluster on this cloud with OpenTofu, from "
        "this machine",
    )  # fmt: skip
    install.add_argument(
        "--first-admin-code-file", type=Path,
        help="small, on the server: where the first boot collects the first administrator's code",
    )  # fmt: skip

    # ADR-137 decision 1: a changed osprey.yaml, applied to the deployment installed from it.
    verbs.add_parser(
        "apply",
        help="apply a changed osprey.yaml to the installed deployment: keep every secret, ask "
        "for a newly enabled provider's key, restart only what changed",
    )

    start = verbs.add_parser("start", help="bring the deployment up")
    start.add_argument("--build", action="store_true", help="rebuild from the checkout first")
    verbs.add_parser("stop", help="stop the deployment")
    # ADR-114 Amendment 22: what `make register-sign-in` did, as the operator's own verb.
    repair = verbs.add_parser(
        "repair-sign-in",
        help="register the sign-in again (its clients, roles and demo accounts); safe to repeat",
    )
    repair.add_argument(
        "--no-demo-accounts", action="store_true", help="for an install made without them"
    )
    verbs.add_parser("status", help="say each service's state")
    switch = verbs.add_parser(
        "switch",
        help="make this the deployment running: stop any other OspreyFlow deployment, then start "
        "and open this one",
    )
    switch.add_argument(
        "deployment", nargs="?", help="the deployment to switch to (as --name takes it)"
    )
    switch.add_argument(
        "--list",
        action="store_true",
        help="list this machine's OspreyFlow deployments; change nothing",
    )
    verbs.add_parser("open", help="open the Glass in the browser")
    verbs.add_parser(
        "deployments", help="list this machine's deployments: name, starter, address, state"
    )
    verbs.add_parser("starters", help="list the starters (a theme and a domain) an install offers")

    logs = verbs.add_parser("logs", help="show service logs")
    logs.add_argument("service", nargs="?")
    logs.add_argument("--follow", action="store_true")
    logs.add_argument("--tail", type=int, default=200)

    demo_verb = verbs.add_parser("demo", help="list or add demo packs")
    actions = demo_verb.add_subparsers(dest="action", required=True, metavar="ACTION")
    actions.add_parser("list", help="the demo packs", parents=[common])
    add = actions.add_parser("add", help="add a demo pack", parents=[common])
    add.add_argument("pack")
    add.add_argument("--file", type=Path, help="the downloaded file (PaySim, Enron, public)")
    add.add_argument(
        "--manifest",
        help="public: the dataset's manifest (a path, or a catalogue id such as vast-2012-mc2)",
    )
    add.add_argument(
        "--accept-real-data", action="store_true",
        help="enron, or a public dataset holding real personal data: accept, without being asked "
        "(a scripted run)",
    )  # fmt: skip

    verbs.add_parser("backup", help="back up every store (arguments go to harness.backup)")
    verbs.add_parser("restore", help="restore a backup (arguments go to harness.restore)")
    verbs.add_parser(
        "update", help="check for or move to a newer release (arguments go to harness.update)"
    )

    # ADR-135 decision 3: the model engines, and each provider's key, on a running deployment.
    models = verbs.add_parser(
        "models",
        help="list the model engines, each role's default and whether each key is present; set or "
        "remove a provider's key",
    )
    key_actions = models.add_subparsers(dest="action", metavar="ACTION")
    set_key = key_actions.add_parser(
        "key",
        help="set or rotate a provider's key (from OSPREY_MODEL_KEY_<NAME>, else asked for)",
        parents=[common],
    )
    set_key.add_argument("name", help="the provider, as osprey.yaml names it (gemini, openai, …)")
    remove = key_actions.add_parser(
        "remove-key", help="remove a provider's key", parents=[common]
    )
    remove.add_argument("name")

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
    server = None
    base = _product_config(product)
    gpu = gpu_plan(base)
    if args.config is not None:
        raw = _file_or_default_answers(args)
        answers = load_answers(raw, packs=[str(p) for p in raw.get("demo_packs") or ()])
        server = server_plan(answers)
        gpu = _gpu_of(answers, base)
    ok = _print_checks(
        run_doctor(
            args.mode, probes, product=product, cloud=args.cloud, server=server, gpu=gpu,
            # ADR-114 Amendment 33, "Step 33": the installed deployment's own setting, when the
            # answers are not given (their own setting is checked with the server's).
            joins_by_email=server is None and joins_by_email(base),
        )
    )  # fmt: skip
    return 0 if ok else 1


def _product_config(product: Path) -> dict[str, object]:
    """The product's `osprey.yaml`, or nothing where there is none yet (`doctor` may come first)."""
    return read_config(product) if (product / "osprey.yaml").is_file() else {}


def _gpu_of(answers: Answers, base: Mapping[str, Any]) -> GpuPlan | None:
    """ADR-135 Amendment 1: what the `osprey.yaml` these answers make asks of the GPU."""
    return gpu_plan(osprey_config(answers, base))


def server_plan(answers: Answers) -> ServerPlan | None:
    """ADR-114 Amendment 33: what the server's own checks need from `server:`, or None."""
    if not answers.server:
        return None
    from urllib.parse import urlsplit

    origin = urlsplit(answers.server["public_origin"])
    tls = answers.server["tls"]
    return ServerPlan(
        host=origin.hostname or "",
        port=origin.port or 443,
        dashboards=answers.dashboards,
        certificate=tls["certificate"],
        key=tls["key"],
        ca=tls.get("ca"),
        redirect_http=bool(answers.server.get("redirect_http")),
        govuk=answers.appearance.get("brand") == "govuk",
        backups=str(answers.backups) if answers.backups is not None else None,
        organisation=dict(answers.organisation) or None,
        organisation_secret_given=bool(os.environ.get(ORGANISATION_SECRET_VARIABLE)),
    )


def _govuk_flags(args: argparse.Namespace) -> dict[str, str]:
    given = {
        "service_name": args.service_name,
        "organisation": args.organisation,
        "phase": args.phase,
    }
    return {k: v for k, v in given.items() if v}


def _prompted_answers(
    ctx: _Context, mode: str, packs: Sequence[str], starter: starters.Starter | None = None,
    flags: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    raw: dict[str, Any] = {"mode": mode}
    flags = dict(flags or {})
    if starter is not None:
        raw["starter"] = starter.name
        if starter.govuk:
            # ADR-138 decision 1: the GOV.UK theme asks for the service's name, organisation and
            # phase. The name offered names the whole service, never one case (step 9d finding 3).
            raw["appearance"] = {
                "service_name": flags.get("service_name")
                or ctx.ask("The service's name (page title)", starter.domain.service_name or ""),
                "organisation": flags.get("organisation")
                or ctx.ask("The organisation (GOV.UK footer)", ""),
                "phase": flags.get("phase")
                or ctx.ask("The phase (alpha, beta, live or none)", starters.DEFAULT_PHASE),
            }
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
    offered_first = (
        ",".join(p for p in starter.domain.demo_packs if p in packs) if starter is not None else ""
    )
    chosen = [
        p.strip()
        for p in ctx.ask(
            f"Demo packs to load, separated by commas ({', '.join(packs)}); blank for none",
            offered_first,
        ).split(",")
        if p.strip()
    ]
    if chosen or starter is not None:
        raw["demo_packs"] = chosen
    if "paysim" in chosen:
        raw["paysim_file"] = ctx.ask("Where is the PaySIM download?", "")
    if isinstance(raw.get("appearance"), dict):
        raw["appearance"] = {k: v for k, v in raw["appearance"].items() if v}
    return {k: v for k, v in raw.items() if v != ""}


def _starter_into(raw: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    """`--starter` and the GOV.UK flags written into answers that came from a file or `--yes`. A
    file naming another starter is refused rather than one silently winning."""
    if args.starter:
        if raw.setdefault("starter", args.starter) != args.starter:
            raise AnswersRefused(
                f"the answers name the starter {raw['starter']}, but --starter {args.starter} was "
                "given; they must agree"
            )
    flags = _govuk_flags(args)
    if flags:
        appearance = raw.setdefault("appearance", {})
        if not isinstance(appearance, dict):
            raise AnswersRefused(f"appearance holds settings, not {appearance!r}")
        appearance.update(flags)
    return raw


def _raw_answers(args: argparse.Namespace, ctx: _Context, packs: Sequence[str]) -> dict[str, Any]:
    if args.config is None and not args.yes:
        starter = None
        if args.starter:
            try:
                starter = starters.parse(args.starter)
            except starters.UnknownStarter as unknown:
                raise AnswersRefused(str(unknown)) from None
        return _prompted_answers(ctx, args.mode, packs, starter, _govuk_flags(args))
    return _starter_into(_file_or_default_answers(args), args)


def _file_or_default_answers(args: argparse.Namespace) -> dict[str, Any]:
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
    return {"mode": args.mode}


def _write_config(ctx: _Context, answers: Answers, force: bool) -> None:
    path = ctx.config_path
    config = osprey_config(answers, read_config(ctx.product))
    header = starters.comment(answers.starter, answers.demo_packs) if answers.starter else ""
    if config == read_config(ctx.product) and (not header or _begins_with(path, header)):
        _say_resolution_off(answers)
        return  # what the answers make is what is there, or the owner's own file used as it is
    if not force:
        raise CommandRefused(
            f"{path} already exists and differs from what these answers make. Nothing was "
            "changed; run again with --force to replace it, or put your settings in the answers "
            "file (or name your own file there with config:)."
        )
    path.write_text(header + yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    print(f"Wrote {path}.")
    _say_resolution_off(answers)


def _begins_with(path: Path, header: str) -> bool:
    try:
        return path.read_text(encoding="utf-8").startswith(header)
    except OSError:
        return False


def _gui(ctx: _Context) -> int:
    """The guided page (ADR-114 Amendment 3, decision 6): the Set-up console's screens, served on
    127.0.0.1 at a free port behind a one-time token, working on a draft copy of `osprey.yaml`, for
    as long as the install lasts. The doctor is not run first: the page runs it on its Review
    screen, where a failure can be shown beside its fix.

    The page itself is made ready first (ADR-114 Amendment 11): built from this checkout, or the
    release's own, its signature checked — and refused in words, naming the build, otherwise."""
    ctx.step(
        "make the install page ready",
        [*ctx.python, "-m", "harness.install_page_build", "--product", str(ctx.product)],
    )
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
    if args.list_starters:
        print("\n".join(starters.listing()))
        return 0
    if args.mode is None:
        raise CommandRefused(
            "Say which mode to install: --mode lite, small or enterprise (section 1 of the "
            "administration guide)."
        )
    if ctx.target.named and args.mode != "lite":
        raise CommandRefused(
            "--name keeps a deployment beside others on this computer, which is Lite. A Small "
            "server or an Enterprise cluster is a deployment of its own: install it without --name."
        )
    if args.address and not ctx.target.named:
        raise CommandRefused(
            "--address goes with --name. To move the checkout's own deployment, change "
            "network.public_origin in its osprey.yaml and run ospreyflow apply."
        )
    if args.gui:
        if ctx.target.named:
            raise CommandRefused(
                "The guided page installs the checkout's own deployment. Install one by name from "
                "the terminal: ospreyflow install --mode lite --name <name> --starter <starter>."
            )
        return _gui(ctx)
    packs = demo.pack_ids(ctx.product, ctx.capture)
    raw = _raw_answers(args, ctx, packs)
    # ADR-114 Amendment 23: real data is never added by an install, only on its own, after asking.
    real = sorted(set(demo.REAL_DATA_PACKS) & {str(p) for p in raw.get("demo_packs") or ()})
    if real:
        raise CommandRefused(
            f"{', '.join(real)} is real people's data and is never added by an install. Install "
            "without it, then add it on its own with "
            + " / ".join(f"ospreyflow demo add {pack}" for pack in real)
            + ", which says what it is and asks first."
        )
    answers = load_answers(raw, packs=packs)
    # ADR-114 Amendment 10 point 1: Small is built from the operator's machine (`--cloud`), and
    # installed on the server by its first boot, whose answers name the managed services.
    on_server = args.mode == "small" and not args.cloud and bool(answers.external)
    # ADR-114 Amendment 33 decision 1: or installed onto a server of your own (`server:`), every
    # store in a container.
    own_server = args.mode == "small" and bool(answers.server)
    if own_server and args.cloud:
        raise CommandRefused(
            "Build a server with --cloud, or install onto one you have with server: in the "
            "answers file, not both. Nothing was installed."
        )
    if args.mode == "enterprise" and not answers.external and not args.cloud:
        raise CommandRefused(
            "enterprise runs on the cloud's managed services: name them under external: in the "
            "answers file (postgres, valkey, and object_store or media), with the cluster's "
            "shared_storage_class under cluster: — or give --cloud aws or --cloud azure to build "
            "the cluster and its services with OpenTofu"
        )
    if args.mode == "small" and not args.cloud and not on_server and not own_server:
        raise CommandRefused(
            "small needs one of three: a server: section in the answers file, to install onto a "
            "server of your own with every store in a container (section 5a of the administration "
            "guide); --cloud aws or --cloud azure here, to build a cloud server; or, on that cloud "
            "server, the answers its first boot wrote, whose external: names its managed services"
        )
    named_ports: tuple[int, ...] | None = None
    if ctx.target.named:
        named_ports = _prepare_named(ctx, args)
    # The server runs the stack as Lite does, so it needs what Lite needs (Docker and its ports).
    doctor_mode = "lite" if on_server else args.mode
    checks = run_doctor(
        doctor_mode, ctx.probes, product=ctx.product, cloud=args.cloud, ports=named_ports,
        server=server_plan(answers) if own_server else None,
        gpu=_gpu_of(answers, _product_config(ctx.product)),
    )  # fmt: skip
    if not _print_checks(checks):
        print("Nothing was installed. Fix the above and run ospreyflow install again.")
        return 1
    if args.mode == "small" and args.cloud:
        return build_small(ctx, args, answers)
    if on_server or own_server:
        return _install_on_server(ctx, args, answers)
    if args.mode == "enterprise" and args.cloud:
        return build_enterprise(ctx, args, answers)
    if args.mode == "enterprise":
        return _install_on_cluster(ctx, args, answers)

    if ctx.target.named:
        _write_named_config(ctx, args, answers)
    else:
        _write_config(ctx, answers, args.force)
    demo_accounts = answers.demo_accounts and not args.no_demo_accounts
    apply = _apply_argv(ctx, args)
    if demo_accounts:
        apply.append("--demo-analyst")
    ctx.step("build and start the deployment", apply)
    if ctx.target.named:
        named.remember(ctx.env, ctx.target.name)
    if demo_accounts:
        ctx.step(
            "register the sign-in",
            [*ctx.python, "-m", "harness.register_sign_in", *ctx.named_args()],
        )
    _add_demo_packs(ctx, answers)

    print()
    print(f"OspreyFlow is installed. Open it at {ctx.origin()}")
    if demo_accounts:
        print(f"Sign in with the accounts in {ctx.deployment / 'deployment.env'}")
    else:
        print(f"The sign-in details are in {ctx.deployment / 'deployment.env'}")
    if answers.starter is not None:
        missing = [p for p in answers.starter.domain.demo_packs if p not in packs]
        if missing:
            print(f"This checkout has no {', '.join(missing)} demo pack, so it was not loaded.")
        if answers.starter.domain.note:
            print(answers.starter.domain.note)
    name = f" --name {ctx.target.name}" if ctx.target.named else ""
    print(f"Look after it with: ospreyflow status{name}, ospreyflow open{name}")
    return 0


def _add_demo_packs(ctx: _Context, answers: Answers) -> None:
    """The answers' demo packs, each into its own case, in the order given."""
    for pack in answers.demo_packs:
        file = answers.paysim_file if pack == "paysim" else None
        demo.add_pack(
            ctx.product, ctx.run, ctx.env, pack, file,
            case_domains=answers.case_domains, **_pack_target(ctx),
        )  # fmt: skip


def _pack_target(ctx: _Context) -> dict[str, Any]:
    """Where a demo pack loads: the deployment, its `osprey.yaml` and the `apply` that applies it
    (for the Prison Intelligence pack's resolution check, ADR-127 Amendment 46)."""
    name = f" --name {ctx.target.name}" if ctx.target.named else ""
    return {
        "deployment_env": ctx.named_env(),
        "deployment": ctx.deployment,
        "settings": ctx.config_path,
        "apply_command": f"ospreyflow apply{name}",
    }


def _say_resolution_off(answers: Answers) -> None:
    """ADR-127 Amendment 46: said whenever the answers' packs turn post-ingest resolution off."""
    packs = sorted(set(answers.demo_packs) & set(demo.RESOLUTION_OFF_PACKS))
    if packs:
        print(
            f"Post-ingest resolution is off (components.post_ingest_resolution: false), because "
            f"{', '.join(packs)} needs it off: its live loads must not add automatic \"same as\" "
            "links. An analyst's own Resolve now still works (section 11 of the administration "
            "guide)."
        )


def _docker_projects(ctx: _Context) -> dict[str, list[Path]]:
    code, output = ctx.capture(
        ["docker", "compose", "ls", "--all", "--format", "json"], cwd=ctx.product
    )
    if code != 0:
        raise CommandRefused(
            "Could not ask Docker which Compose projects exist, so a new deployment's name cannot "
            "be checked. Is Docker running?"
        )
    return named.compose_projects(_services(output))


def _prepare_named(ctx: _Context, args: argparse.Namespace) -> tuple[int, ...]:
    """ADR-138 decision 2, before anything is written: the name is free (no Compose project of
    another folder has it, and no deployment is installed under it), and the deployment is given
    an address and a graph-store port nobody else has. Returns the ports the doctor checks."""
    target = ctx.target
    if (target.rendered / "compose.yaml").is_file():
        raise CommandRefused(
            f"A deployment called '{target.name}' is already installed, in {target.folder}. "
            f"Change a setting with ospreyflow apply --name {target.name}; start it with "
            f"ospreyflow start --name {target.name}. Nothing was changed."
        )
    named.refuse_a_taken_project(target.name, target.folder, _docker_projects(ctx))
    taken = named.ports_in_use(ctx.product, ctx.env)
    if args.address:
        named.check_address(args.address)
        address = args.address.rstrip("/")
        port = named._port_of(address)
        if port in taken:
            raise CommandRefused(
                f"Port {port} of {address} is already another deployment's. Give another "
                "--address, or leave it out to be given a free port."
            )
    else:
        port = named.next_free_port(named.FIRST_ADDRESS_PORT, taken, ctx.probes.port_free)
        address = named.default_address(target.name, port)
    graph = named.next_free_port(named.FIRST_GRAPH_PORT, taken | {port}, ctx.probes.port_free)
    ctx.named_install = (address, graph)
    return (port, graph)


def _write_named_config(ctx: _Context, args: argparse.Namespace, answers: Answers) -> None:
    """The deployment's own `osprey.yaml`, in its own folder (mode 700): the checkout's settings
    less what names the checkout's deployment and its look (`deployment`, `appearance`), with the
    answers over them, then its name, address and graph-store port."""
    address, graph = ctx.named_install
    base = {
        k: v for k, v in read_config(ctx.product).items() if k not in ("deployment", "appearance")
    }
    config = osprey_config(answers, base)
    config["deployment"] = {"name": ctx.target.name, "graph_port": graph}
    config.setdefault("network", {})["public_origin"] = address
    header = starters.comment(answers.starter, answers.demo_packs) if answers.starter else ""
    text = header + yaml.safe_dump(config, sort_keys=False)
    path = ctx.config_path
    if path.is_file() and path.read_text(encoding="utf-8") != text and not args.force:
        raise CommandRefused(
            f"{path} already exists and differs from what these answers make. Nothing was "
            "changed; run again with --force to replace it."
        )
    named.private_folder(ctx.target.folder)
    path.write_text(text, encoding="utf-8")
    print(f"Wrote {path}.")
    _say_resolution_off(answers)


def _apply_argv(ctx: _Context, args: argparse.Namespace) -> list[str]:
    release = None if args.build else _release_at_head(ctx)
    if release is None:
        return [*ctx.python, "-m", "harness.apply", "--build", *ctx.named_args()]
    # ADR-114 Amendment 8 point 10: a release's signed images, verified before anything starts.
    (ctx.product / ".install").mkdir(exist_ok=True)
    lock = ctx.product / ".install" / "release.lock"
    ctx.step(
        "verify the release's images",
        [*ctx.python, "-m", "harness.update", "--deployment", str(ctx.deployment),
         "--verify-install", release, "--lock-out", str(lock)],
    )  # fmt: skip
    return [*ctx.python, "-m", "harness.apply", "--images-from", str(lock), *ctx.named_args()]


def _install_on_server(ctx: _Context, args: argparse.Namespace, answers: Answers) -> int:
    """A Small server's install, run by its first boot (ADR-114 Amendment 10 points 1 and 4): onto
    the managed services, with no demo accounts — its first administrator signs in by a one-time
    code, which goes to `--first-admin-code-file` for the first boot to hand to the secret store.

    Or run by hand on a server of your own (Amendment 33): the same steps, every store in a
    container; without `--first-admin-code-file` the code is printed once, on this terminal."""
    if answers.memory_gib == "auto":
        answers = dataclasses.replace(answers, memory_gib=_measured_memory_gib(ctx))
    _write_config(ctx, answers, args.force)
    ctx.step("build and start the deployment", _apply_argv(ctx, args))
    # ADR-114 Amendment 16: the identity provider's settings beyond its realm import — Superset's
    # sign-in among them — with no demo account.
    ctx.step(
        "configure the sign-in",
        [*ctx.python, "-m", "harness.register_sign_in", "--profile", "small", "--no-demo-accounts"],
    )
    admin = [*ctx.python, "-m", "harness.first_admin", "--deployment", str(ctx.deployment)]
    email = answers.cloud.get("admin_email") or answers.admin_email
    if email:
        admin += ["--email", email]
    if args.first_admin_code_file is not None:
        admin += ["--code-file", str(args.first_admin_code_file)]
    ctx.step("make the first administrator", admin)
    # As Lite's, once the stack and the first administrator exist: with no demo accounts the
    # administrator is each case's Author (as found on the first server, 4 November 2026, when the
    # answer was accepted here and never loaded).
    _add_demo_packs(ctx, answers)
    print()
    print(f"OspreyFlow is installed. It answers at {public_origin(ctx.product)}")
    plan = server_plan(answers)
    if plan is not None:
        print(
            f"In the organisation's DNS, point {', '.join(plan.names)} at this server. Port "
            f"{plan.port} is the only one other machines reach; who may reach it is set in front "
            "of the server (its firewall or security group), not with ufw."
        )
        if plan.organisation:
            redirect, logout = plan.organisation_uris
            print(
                "For sign-in through the organisation, its identity team registers OspreyFlow's "
                f"application with the redirect URI {redirect} and the post-logout redirect URI "
                f"{logout}, assigned to the people who may sign in. A person signing in that way "
                "has no role until an administrator grants one in Admin, People and roles."
            )
            if plan.organisation.get("trust_email") == "true":
                # ADR-114 Amendment 33, "Step 33": said again as the install ends.
                print(f"WARNING: {TRUST_EMAIL_SAYS} {TRUST_EMAIL_FIX}")
    return 0


def _measured_memory_gib(ctx: _Context) -> int:
    """ADR-114 Amendment 33 decision 6: the memory Docker reports, in whole GiB, measured once, at
    install, and written to `resources.memory_gib`; the render then reads the number, never the
    machine."""
    info = ctx.probes.docker_info() or {}
    total = info.get("MemTotal")
    if not isinstance(total, int | float) or total <= 0:
        raise CommandRefused(
            "server.memory_gib is auto, and Docker did not say how much memory it has. Give the "
            "number of GiB instead (for example memory_gib: 64). Nothing was installed."
        )
    gibibytes = int(total // 2**30)
    print(
        f"The stores are sized to {gibibytes} GiB of memory, as Docker reports it "
        "(resources.memory_gib in osprey.yaml; change it and run ospreyflow apply to resize)."
    )
    return gibibytes


def _install_on_cluster(
    ctx: _Context,
    args: argparse.Namespace,
    answers: Answers,
    env: Mapping[str, str] | None = None,
) -> int:
    """Enterprise (ADR-114 Amendment 16): onto the cluster `kubectl` reaches, from this machine —
    the chart, its Secret, the identity provider and the first administrator. `env` carries what
    a cluster built here hands on (Amendment 19): its kubeconfig and the managed services'
    secrets."""
    _write_config(ctx, answers, args.force)
    step = [*ctx.python, "-m", "harness.cluster_install", "--config",
            str(ctx.product / "osprey.yaml")]  # fmt: skip
    if answers.cloud.get("admin_email"):
        step += ["--email", answers.cloud["admin_email"]]
    for extra in args.chart_values:
        step += ["--values", str(extra)]
    ctx.step("install onto the cluster", step, env=dict(env or {}))
    return 0


_RELEASE_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def _release_at_head(ctx: _Context) -> str | None:
    """The release the checkout sits on (its newest `vX.Y.Z` tag at HEAD), or None to build."""
    code, said = ctx.capture(
        ["git", "-C", str(ctx.product), "tag", "--points-at", "HEAD"], cwd=ctx.product
    )
    tags = (
        [t.strip() for t in said.splitlines() if _RELEASE_TAG.match(t.strip())] if code == 0 else []
    )
    if not tags:
        return None
    return max(tags, key=lambda t: tuple(int(p) for p in _RELEASE_TAG.match(t).groups()))  # type: ignore[union-attr]


def _start(args: argparse.Namespace, ctx: _Context) -> int:
    directory = ctx.deployed()
    if args.build:
        ctx.step(
            "rebuild from the checkout",
            [*ctx.python, "-m", "scripts.refresh"],
            env=ctx.named_env(),
        )
    else:
        _uploads_ready(ctx, directory)
        _stores_named(ctx, directory)
        ctx.step("start the deployment", [*compose(directory), "up", "-d", "--wait"])
    return 0


def _uploads_ready(ctx: _Context, directory: Path) -> None:
    """ADR-114 Amendment 33, "as found on the first server": the Ingest Studio's upload folder the
    Conduit's to write before `up` (`harness.ingest_uploads`, which says why when it cannot)."""
    ctx.step(
        "prepare the upload folder",
        [*ctx.python, "-m", "harness.ingest_uploads", str(directory / "compose.yaml")],
    )


def _stores_named(ctx: _Context, directory: Path) -> None:
    """ADR-114 Amendment 35: a deployment whose stores' data is not yet in their named volumes has
    it moved there once, before `up` (`harness.store_volumes`, which says why when it cannot; the
    stores are then never started on empty named volumes beside their data)."""
    ctx.step(
        "move the stores' data to named volumes",
        [*ctx.python, "-m", "harness.store_volumes", str(directory / "compose.yaml")],
    )


def _apply_settings(ctx: _Context) -> int:
    """ADR-137 decision 1: the harness's own `--reapply` — the same rendering an install does, with
    every secret kept and only the services whose files changed started again. No install step is
    run. A newly enabled provider's key comes from `OSPREY_MODEL_KEY_<NAME>` in this terminal, which
    the harness inherits, or the harness asks for it at a hidden prompt.

    ADR-135 Amendment 1 decision 4: a GPU asked for is checked first, and nothing is changed if it
    is not ready."""
    directory = ctx.deployed()
    plan = gpu_plan(yaml.safe_load(ctx.config_path.read_text(encoding="utf-8")) or {})
    if plan is not None and not _print_checks(gpu_checks(ctx.probes, plan)):
        print("Nothing was changed. Fix the above and run ospreyflow apply again.")
        return 1
    ctx.step(
        "apply the changed settings",
        [*ctx.python, "-m", "harness.apply", "--reapply",
         "--config", str(ctx.config_path), "--out-root", str(directory.parent)],
    )  # fmt: skip
    print(f"The settings in {ctx.config_path} are applied.")
    return 0


def _repair_sign_in(args: argparse.Namespace, ctx: _Context) -> int:
    """ADR-114 Amendment 22: the deployment's sign-in registered again, for its own profile."""
    step = [*ctx.python, "-m", "harness.register_sign_in", "--profile", ctx.deployed().name,
            *ctx.named_args()]  # fmt: skip
    if args.no_demo_accounts:
        step.append("--no-demo-accounts")
    ctx.step("register the sign-in", step)
    print("The sign-in is registered. Sign in again in the browser.")
    return 0


def _stop(ctx: _Context) -> int:
    ctx.step("stop the deployment", [*compose(ctx.deployed()), "stop"])
    return 0


def _deployments(ctx: _Context) -> list[tuple[str, bool, Path]] | None:
    """This machine's OspreyFlow deployments, as Docker's own Compose labels name them: `(project,
    running, rendered folder)` for each project whose compose file is a product's
    `deploy/generated/<name>/compose.yaml` (ADR-132 Amendment 3). Any other project is left out, so
    it is never stopped. `None` when Docker cannot be asked."""
    code, output = ctx.capture(
        ["docker", "compose", "ls", "--all", "--format", "json"], cwd=ctx.product
    )
    if code != 0:
        return None
    found: list[tuple[str, bool, Path]] = []
    root = named.deployments_root(ctx.env).resolve()
    for row in _services(output):
        for config in str(row.get("ConfigFiles", "")).split(","):
            compose_file = Path(config.strip())
            folder = compose_file.parent
            if compose_file.name == "compose.yaml" and folder.resolve().parent == root:
                # ADR-138: a deployment kept by name under ~/.ospreyflow/deployments/.
                if (folder / "osprey.yaml").is_file():
                    running = "running" in str(row.get("Status", ""))
                    found.append((str(row.get("Name", "")), running, folder))
                continue
            if compose_file.name != "compose.yaml" or folder.parent.name != "generated":
                continue
            if folder.parent.parent.name != "deploy":
                continue
            if not (folder.parents[2] / "osprey.yaml").is_file():
                continue
            running = "running" in str(row.get("Status", ""))
            found.append((str(row.get("Name", "")), running, folder))
    return found


def _switch(args: argparse.Namespace, ctx: _Context) -> int:
    """ADR-132 Amendment 3: one deployment running at a time on a machine with room for one. Stops
    every other OspreyFlow deployment that is running (with its own env file), then starts and
    opens this one. `--list` only says what there is."""
    own = ctx.deployed().resolve()
    deployments = _deployments(ctx)
    if deployments is None:
        print(
            "Could not ask Docker about this machine's deployments. Is Docker running?",
            file=sys.stderr,
        )
        return 1
    if args.list:
        for name, running, folder in deployments:
            state = "running" if running else "stopped"
            if folder.resolve() == own:
                print(f"{name}: {state} (this one)")
                continue
            if (folder / "osprey.yaml").is_file() and folder.resolve().parent == (
                named.deployments_root(ctx.env).resolve()
            ):
                address = named.address_of(folder / "osprey.yaml")
                print(f"{name}: {state} \u2014 {folder} \u2014 {address}")
                continue
            product = folder.parents[2]
            print(f"{name}: {state} \u2014 {product} \u2014 {public_origin(product)}")
        return 0
    for name, running, folder in deployments:
        if running and folder.resolve() != own:
            print(f"Stopping {name}, so this one has the machine to itself.")
            ctx.step(f"stop {name}", [*compose(folder), "stop"])
    _uploads_ready(ctx, ctx.deployed())
    _stores_named(ctx, ctx.deployed())
    ctx.step("start the deployment", [*compose(ctx.deployed()), "up", "-d", "--wait"])
    named.remember(ctx.env, ctx.target.name)
    address = ctx.origin()
    ctx.open_url(address)
    print(f"Opening {address}")
    return 0


def _list_deployments(ctx: _Context) -> int:
    """ADR-138 decision 2: every deployment this command knows — the checkout's own as `default`,
    each one kept by name — with its starter, address and whether it is running. Changes nothing."""
    code, output = ctx.capture(
        ["docker", "compose", "ls", "--all", "--format", "json"], cwd=ctx.product
    )
    projects = _services(output) if code == 0 else []
    running: dict[Path, bool] = {}
    for row in projects:
        for config in str(row.get("ConfigFiles", "")).split(","):
            if config.strip():
                running[Path(config.strip()).resolve()] = "running" in str(row.get("Status", ""))
    targets = [named.default_target(ctx.product)]
    targets += [named.named_target(ctx.env, n) for n in named.named(ctx.env)]
    chosen = ctx.target.name
    for target in targets:
        compose_file = target.rendered / "compose.yaml"
        if not compose_file.is_file():
            state = "not installed" if target.named else None
            if state is None:
                continue  # the checkout has no deployment of its own
        elif code != 0:
            state = "state unknown (Docker did not answer)"
        else:
            state = "running" if running.get(compose_file.resolve()) else "stopped"
        starter = named.starter_of(target.config_path) or "no starter"
        here = " (the one commands act on)" if target.name == chosen else ""
        print(f"{target.name}: {starter}, {target.origin()}, {state}{here}")
        print(f"  {target.folder}")
    if code != 0:
        print("Docker did not answer, so whether each is running is not known.", file=sys.stderr)
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
    one_shots = _one_shot_steps(directory)
    healthy = True
    for row in sorted(rows, key=lambda r: str(r.get("Service", ""))):
        service = str(row.get("Service", "?"))
        state, health = str(row.get("State", "unknown")), str(row.get("Health") or "")
        if service in one_shots and state == "exited":
            # A step that runs once and exits (Keycloak's database, a model download).
            code = row.get("ExitCode")
            print(f"{service}: finished" if code == 0 else f"{service}: exited (code {code})")
            healthy &= code == 0
            continue
        print(f"{service}: {state}" + (f", {health}" if health else ""))
        healthy &= state == "running" and health in ("", "healthy")
    return 0 if healthy else 1


def _one_shot_steps(directory: Path) -> set[str]:
    """The services the deployment runs once (`restart: "no"`), read from its compose file."""
    try:
        services = yaml.safe_load((directory / "compose.yaml").read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return set()
    return {
        name for name, service in (services.get("services") or {}).items()
        if isinstance(service, dict) and str(service.get("restart")) in ("no", "False")
    }  # fmt: skip


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


def _models(args: argparse.Namespace, ctx: _Context) -> int:
    """ADR-135 decision 3. A key goes to `deployment.env` alone and is never printed; then only the
    services whose environment it changes are started again (`cli/ospreyflow/models.py`)."""
    directory = ctx.deployed()
    env_file = directory / "deployment.env"
    models = engine_keys.read_models(ctx.product, directory)
    wanted = engine_keys.read_wanted(ctx.config_path.parent)
    if args.action is None:
        print("\n".join(engine_keys.list_engines(models, env_file)))
        return 0
    if args.action == "key":
        label = engine_keys.set_key(
            models, args.name, env_file, ctx.env, ctx.ask_secret, wanted=wanted
        )
        said = f"The key for {label} is set, in {env_file}."
    else:
        label, removed = engine_keys.remove_key(models, args.name, env_file, wanted=wanted)
        if not removed:
            print(f"{label} has no key here; nothing was changed.")
            return 0
        said = (
            f"The key for {label} is removed; {label} is not offered to analysts until one is set."
        )
    ctx.step(
        "start the model gateway and the Conduit again",
        [*compose(directory), "up", "-d", "--no-deps", "--wait", *engine_keys.RESTARTED],
    )
    print(said)
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
    if verb == "switch":
        return _switch(args, ctx)
    if verb == "deployments":
        return _list_deployments(ctx)
    if verb == "starters":
        print("\n".join(starters.listing()))
        return 0
    if verb == "open":
        address = ctx.origin()
        ctx.open_url(address)
        print(f"Opening {address}")
        return 0
    if verb == "logs":
        return _logs(args, ctx)
    if verb == "demo":
        if args.action == "list":
            return demo.list_packs(ctx.product, ctx.run)
        if args.pack == "public":
            demo.add_public(
                ctx.product, ctx.run, ctx.env, args.file, args.manifest, capture=ctx.capture,
                ask=ctx.ask, accept_real_data=args.accept_real_data,
                deployment_env=ctx.named_env(),
            )  # fmt: skip
            return 0
        demo.add_pack(
            ctx.product, ctx.run, ctx.env, args.pack, args.file,
            ask=ctx.ask, accept_real_data=args.accept_real_data, **_pack_target(ctx),
        )  # fmt: skip
        return 0
    if verb == "uninstall":
        return _uninstall(args, ctx)
    if verb == "repair-sign-in":
        return _repair_sign_in(args, ctx)
    if verb == "models":
        return _models(args, ctx)
    if verb == "apply":
        return _apply_settings(ctx)
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
    ask_secret: AskSecret = getpass.getpass,
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
    if args_in and args_in[0] in ("backup", "restore", "update"):
        args_in, passthrough = args_in[:1], args_in[1:]
        # ADR-138: `--name` is the command's own, whatever else goes to the harness.
        for index, word in enumerate(passthrough):
            if word == "--name" and index + 1 < len(passthrough):
                args_in += passthrough[index : index + 2]
                passthrough = passthrough[:index] + passthrough[index + 2 :]
                break
            if word.startswith("--name="):
                args_in.append(word)
                passthrough = passthrough[:index] + passthrough[index + 1 :]
                break
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
        given = getattr(args, "deployment_name", None)
        wanted = args.deployment if args.verb == "switch" and args.deployment else given
        if args.verb == "switch" and args.deployment and given and given != args.deployment:
            raise CommandRefused("Name the deployment once: ospreyflow switch <name>.")
        target = (
            named.resolve(wanted, product, env, creating=args.verb == "install")
            if args.verb not in ("doctor", "starters")
            else named.default_target(product)
        )
        if target.named:
            directory = target.rendered
        elif (product / "osprey.yaml").is_file():
            directory = deployment_dir(product)
        else:
            directory = product
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
            ask_secret,
            target,
        )
        if wanted is not None and args.verb != "install":
            named.remember(env, target.name)
        if args.verb == "update":
            # ADR-114 Amendment 8: the checkout's own `harness.update`, told which deployment.
            directory = ctx.deployed()
            return ctx.run(
                [*ctx.python, "-m", "harness.update", "--deployment", str(directory), *passthrough],
                cwd=product,
            )
        if args.verb in ("backup", "restore"):
            module = f"harness.{args.verb}"
            # ADR-138: a deployment kept by name is named to the harness by its own osprey.yaml and
            # rendered folder; its backups are kept in its own folder, never mixed with another's.
            pointed = ctx.named_args("--generated-root")
            if target.named and args.verb == "backup" and "--out-root" not in passthrough:
                pointed += ["--out-root", str(target.folder / "backups")]
            return ctx.run([*ctx.python, "-m", module, *pointed, *passthrough], cwd=product)
        return _dispatch(args, ctx)
    except (CommandRefused, AnswersRefused) as refusal:
        print(f"ospreyflow: {refusal}", file=sys.stderr)
        return 1
    except StepFailed as failed:
        print(f"ospreyflow: {failed}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
