"""Loads an internal demo dataset into the running deployment, in one command.

    PYTHONPATH=.:packages:../OspreyFlow_Build python -m scripts.seed_internal <dataset> [--stop-api]
    (or: make seed-paysim | seed-hmp | seed-fixture-corp | seed-enron)

The seed runs in a one-shot container from the Conduit's own image, **inside the deployment's
network**, the way `harness.apply` runs its own seeds: the deployment's analytics store is a Docker
volume only the Conduit's image can see, and its Postgres, ArcadeDB and their passwords are only
reachable (and only known) there, so nothing here handles a password. The checkout's `scripts/` and
the data folder are mounted read-only.

The case the data goes into is made by the seed itself, named, and shared with the two demo accounts
by their identity-provider subjects (the Conduit's principal ids): the demo administrator as Author,
the demo analyst as Editor. Those subjects are read from Keycloak here, on the host, where its admin
API is published.

**The Conduit must be stopped while a seed runs** (DuckDB's exclusive lock). With it running this
refuses and names `--stop-api`; stopping it is yours to choose, as in `harness.apply`. When it was
stopped for the seed it is started again afterwards, whether the seed worked or not.

An internal dataset is never seeded from anything that left this project (ADR-035 §C1, ADR-053):
this refuses outside a checkout, and passes the container `--attested-checkout` only after checking.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from harness.apply import _compose
from harness.realm import DEMO_ADMIN_SUBJECT, DEMO_ANALYST_SUBJECT
from scripts.refresh import NothingToRefresh, _deployment_dir, _keycloak_port

REPO_ROOT = Path(__file__).resolve().parents[1]
#: Where the data folder is mounted inside the seed's container.
CONTAINER_DATA = "/internal-data"
#: The demo accounts' organisational unit, which the case must share to be visible to them.
DEMO_UNIT = "verify"


class SeedRefused(Exception):
    """Something to fix before anything is started."""


class SeedFailed(Exception):
    """The seed ran and failed."""


@dataclass(frozen=True)
class Dataset:
    script: str
    case_name: str
    #: The folder under `OspreyFlow_Data` the seed reads; `None` for a demo that generates its own.
    data_folder: str | None = None
    #: The name a real dataset is admitted under in the local exceptions list; `None` if synthetic.
    real_dataset: str | None = None
    #: Whether the seed takes `--graph-fraud-rows` (a sample of the graph; PaySim's is huge).
    sampled: bool = False


#: The PaySim graph sample: the first fraud transactions and everything touching their accounts.
#: The full neighbourhood is ~74,000 accounts and takes many hours to write to a real ArcadeDB.
DEFAULT_GRAPH_SAMPLE = 500

#: Real data is admitted for this use only (ADR-035 §C3, ADR-053).
REAL_DATA_USE = "owner_run_demonstration"

DATASETS: dict[str, Dataset] = {
    "hmp": Dataset(script="scripts.seed_hmp_fixture", case_name="HMP fixture (synthetic demo)"),
    "fixture-corp": Dataset(
        script="scripts.seed_fixture_corp", case_name="Fixture Corp (synthetic demo)"
    ),
    "enron": Dataset(
        script="scripts.seed_enron",
        case_name="Enron corpus (real data, this machine only)",
        data_folder="Enron_Mails",
        real_dataset="enron",
    ),
    "paysim": Dataset(
        script="scripts.seed_paysim",
        case_name="PaySim mobile money (internal)",
        data_folder="PaySIM_Dataset",
        sampled=True,
    ),
}


def _run(argv: Sequence[str]) -> str:
    """Run a command, showing each line of its output as it arrives (a seed takes minutes, and a
    silent one looks hung), and return everything it printed."""
    process = subprocess.Popen(  # noqa: S603
        list(argv), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    lines: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        lines.append(line)
        print(f"  {line.rstrip()}", flush=True)
    code = process.wait()
    text = "".join(lines)
    if code != 0:
        raise SeedFailed(f"`{' '.join(argv[:6])} …` exited {code}\n{text}")
    return text


def _permitted(dataset: str, use: str) -> bool:
    """The local exceptions list, which only this side of the container can see."""
    from scripts import real_data_exceptions

    try:
        return real_data_exceptions.is_permitted(dataset, use)
    except (OSError, ValueError):
        return False


def _api_running(compose: list[str]) -> bool:
    out = subprocess.run(
        [*compose, "ps", "--status", "running", "--services"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    return "api" in out.split()


def _lookup_subs(directory: Path) -> dict[str, str]:
    """The demo accounts' subjects, from the published Keycloak admin API."""
    from harness import keycloak_admin
    from harness.register_sign_in import ADMIN_PASSWORD_KEY, _read_env

    values = _read_env(directory / "deployment.env")
    issuer = f"http://127.0.0.1:{_keycloak_port(directory / 'deployment.env')}"
    token = keycloak_admin.admin_token(
        issuer=issuer, admin_user="admin", admin_password=values[ADMIN_PASSWORD_KEY]
    )
    found: dict[str, str] = {}
    for username in (DEMO_ADMIN_SUBJECT, DEMO_ANALYST_SUBJECT):
        try:
            found[username] = keycloak_admin.user_id(
                issuer=issuer, realm="osprey", token=token, username=username
            )
        except keycloak_admin.RealmConfigurationFailed:
            continue
    return found


def seed_internal(
    dataset: str,
    repo_root: Path = REPO_ROOT,
    *,
    run: Callable[[Sequence[str]], str] = _run,
    lookup_subs: Callable[[Path], dict[str, str]] = _lookup_subs,
    api_running: Callable[[list[str]], bool] = _api_running,
    stop_api: bool = False,
    permitted: Callable[[str, str], bool] = _permitted,
    replace_graph: bool = False,
    reset_graph_database: bool = False,
    vault: str | None = None,
    graph_fraud_rows: int | None = None,
    inspect: bool = False,
    inspect_record: str | None = None,
    repair_strays: bool = False,
    apply: bool = False,
    repair_limit: int | None = None,
    clear_shared_stores: bool = False,
    confirm: str | None = None,
) -> list[str]:
    """Return the seed report, one line each. Raises `SeedRefused` before starting anything."""
    if dataset not in DATASETS:
        raise SeedRefused(f"unknown dataset {dataset!r}; known: {', '.join(sorted(DATASETS))}")
    spec = DATASETS[dataset]
    if apply and not repair_strays:
        raise SeedRefused("--apply only goes with --repair-strays")
    if clear_shared_stores and not spec.sampled:
        raise SeedRefused("--clear-shared-stores is only built for paysim so far")
    if clear_shared_stores and vault is None:
        raise SeedRefused(
            "--clear-shared-stores needs --vault <id>: it only clears the shared stores once that "
            "vault has been checked"
        )
    if confirm is not None and not clear_shared_stores:
        raise SeedRefused("--confirm only goes with --clear-shared-stores")
    if repair_strays and not spec.sampled:
        raise SeedRefused("--repair-strays is only built for paysim so far")
    if reset_graph_database and not spec.sampled:
        raise SeedRefused("--reset-graph-database is only built for paysim so far")
    if vault is not None:
        if not spec.sampled:
            raise SeedRefused("--vault is only built for paysim so far")
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,30}", vault):
            raise SeedRefused(
                f"{vault!r} is not a vault id: lower-case letters, digits and hyphens, starting "
                "with a letter, at most 31 characters"
            )
    if spec.real_dataset and not permitted(spec.real_dataset, REAL_DATA_USE):
        raise SeedRefused(
            f"the local real-data exceptions list has no entry for {spec.real_dataset!r} "
            f"permitting {REAL_DATA_USE!r}. Add one with `python -m scripts.real_data_exceptions "
            "add` (ADR-035 §C3, ADR-053); nothing was started"
        )
    if not (repo_root.parent / ".git").exists():
        raise SeedRefused(
            "this is not a checkout of the repository: an internal dataset is only ever seeded "
            "from one, never from a built bundle"
        )
    try:
        directory = _deployment_dir(repo_root)
    except NothingToRefresh as error:
        raise SeedRefused(str(error)) from error
    data_root = repo_root.parent / "OspreyFlow_Data"
    if spec.data_folder and not (data_root / spec.data_folder).is_dir():
        raise SeedRefused(
            f"the dataset is not provisioned: {data_root / spec.data_folder} is missing"
        )
    if inspect:
        return _inspect(spec, repo_root, directory, run, inspect_record, vault)
    if repair_strays:
        return _repair_strays(spec, repo_root, directory, run, vault, apply, repair_limit)
    if clear_shared_stores:
        return _clear_shared_stores(
            repo_root, directory, run, api_running, stop_api, vault or "", confirm
        )
    subs = lookup_subs(directory)
    missing = [name for name in (DEMO_ADMIN_SUBJECT, DEMO_ANALYST_SUBJECT) if name not in subs]
    if missing:
        raise SeedRefused(
            f"{', '.join(missing)} not found in the identity provider, so the case could not be "
            "shared with it. Run `make register-sign-in` and try again"
        )

    compose = _compose(directory / "compose.yaml")
    running = api_running(compose)
    if running and not stop_api:
        raise SeedRefused(
            "the Conduit is running, and a seed needs it stopped (DuckDB's exclusive lock). "
            "Run again with --stop-api to stop it for the seed and start it again after; "
            "stopping it is your choice, so it is not done for you"
        )
    mounts = ["-v", f"{repo_root}/scripts:/app/scripts:ro"]
    if spec.data_folder:
        mounts += ["-v", f"{data_root}:{CONTAINER_DATA}:ro"]
    argv = [
        *compose,
        "run",
        "--rm",
        "--no-deps",
        "--entrypoint",
        "python",
        *mounts,
        "api",
        "-m",
        spec.script,
        "--case-name",
        spec.case_name,
        "--org-unit",
        DEMO_UNIT,
        "--grant",
        f"{subs[DEMO_ADMIN_SUBJECT]}=author",
        "--grant",
        f"{subs[DEMO_ANALYST_SUBJECT]}=editor",
    ]
    if spec.data_folder:
        argv += ["--data-dir", CONTAINER_DATA, "--attested-checkout"]
    if spec.real_dataset:
        argv.append("--attested-permission")
    if replace_graph and spec.data_folder:
        argv.append("--replace-graph")
    if reset_graph_database:
        argv.append("--reset-graph-database")
    if vault is not None:
        argv += ["--vault", vault]
    if spec.sampled:
        sample = DEFAULT_GRAPH_SAMPLE if graph_fraud_rows is None else graph_fraud_rows
        if sample > 0:
            argv += ["--graph-fraud-rows", str(sample)]
    if running:
        run([*compose, "stop", "api"])
    try:
        output = run(argv)
    finally:
        if running:
            run([*compose, "up", "-d", "--wait", "api"])
    return [line.strip() for line in output.splitlines() if line.strip()]


def _inspect(
    spec: Dataset,
    repo_root: Path,
    directory: Path,
    run: Callable[[Sequence[str]], str],
    record: str | None,
    vault: str | None = None,
) -> list[str]:
    """Read the graph without changing anything: no case, no grants, and the Conduit is left
    running (only `SELECT` is sent, and nothing is written to the analytics store)."""
    argv = [
        *_compose(directory / "compose.yaml"),
        "run",
        "--rm",
        "--no-deps",
        "--entrypoint",
        "python",
        "-v",
        f"{repo_root}/scripts:/app/scripts:ro",
        "api",
        "-m",
        spec.script,
        "--inspect",
    ]
    if record:
        argv += ["--inspect-record", record]
    if vault is not None:
        argv += ["--vault", vault]
    output = run(argv)
    return [line.strip() for line in output.splitlines() if line.strip()]


def _repair_strays(
    spec: Dataset,
    repo_root: Path,
    directory: Path,
    run: Callable[[Sequence[str]], str],
    vault: str | None,
    apply: bool,
    limit: int | None,
) -> list[str]:
    """Remove the stray edge records a load left (ADR-056 Amendment 16). Like an inspection it makes
    no case and loads nothing, and leaves the Conduit running: it touches only the graph database.
    Without `apply` it is a dry run."""
    argv = [
        *_compose(directory / "compose.yaml"),
        "run",
        "--rm",
        "--no-deps",
        "--entrypoint",
        "python",
        "-v",
        f"{repo_root}/scripts:/app/scripts:ro",
        "api",
        "-m",
        spec.script,
        "--repair-strays",
    ]
    if apply:
        argv.append("--apply")
    if limit is not None:
        argv += ["--repair-limit", str(limit)]
    if vault is not None:
        argv += ["--vault", vault]
    output = run(argv)
    return [line.strip() for line in output.splitlines() if line.strip()]


def _clear_shared_stores(
    repo_root: Path,
    directory: Path,
    run: Callable[[Sequence[str]], str],
    api_running: Callable[[list[str]], bool],
    stop_api: bool,
    vault: str,
    confirm: str | None,
) -> list[str]:
    """Report, and with the owner's exact confirmation delete, the shared graph database and the
    shared analytics events, after checking the vault (ADR-056 Amendment 16, stage 0b). The
    Conduit must be stopped (DuckDB's exclusive lock) and is started again after."""
    compose = _compose(directory / "compose.yaml")
    running = api_running(compose)
    if running and not stop_api:
        raise SeedRefused(
            "the Conduit is running, and clearing the shared stores needs it stopped (DuckDB's "
            "exclusive lock). Run again with --stop-api to stop it and start it again after; "
            "stopping it is your choice, so it is not done for you"
        )
    argv = [
        *compose,
        "run",
        "--rm",
        "--no-deps",
        "--entrypoint",
        "python",
        "-v",
        f"{repo_root}/scripts:/app/scripts:ro",
        "api",
        "-m",
        "scripts.clear_shared_stores",
        "--vault",
        vault,
    ]
    if confirm is not None:
        argv += ["--confirm", confirm]
    if running:
        run([*compose, "stop", "api"])
    try:
        output = run(argv)
    finally:
        if running:
            run([*compose, "up", "-d", "--wait", "api"])
    return [line.strip() for line in output.splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    stop_api = "--stop-api" in args
    replace_graph = "--replace-graph" in args
    reset_database = "--reset-graph-database" in args
    vault: str | None = None
    if "--vault" in args:
        value = args[args.index("--vault") + 1 :][:1]
        if not value or value[0].startswith("--"):
            print("--vault takes a vault id, for example --vault paysim", file=sys.stderr)
            return 2
        vault = value[0]
    inspect = "--inspect" in args
    repair_strays = "--repair-strays" in args
    clear_shared_stores = "--clear-shared-stores" in args
    confirm: str | None = None
    if "--confirm" in args:
        value = args[args.index("--confirm") + 1 :][:1]
        if not value or value[0].startswith("--"):
            print("--confirm takes the counts the dry run reported, v:e:n", file=sys.stderr)
            return 2
        confirm = value[0]
    apply = "--apply" in args
    repair_limit: int | None = None
    if "--repair-limit" in args:
        value = args[args.index("--repair-limit") + 1 :][:1]
        if not value or not value[0].isdigit():
            print("--repair-limit takes a number, for example --repair-limit 1", file=sys.stderr)
            return 2
        repair_limit = int(value[0])
    record: str | None = None
    if "--inspect-record" in args:
        record = (args[args.index("--inspect-record") + 1 :] or [None])[0]  # type: ignore[list-item]
    sample: int | None = None
    if "--graph-fraud-rows" in args:
        value = args[args.index("--graph-fraud-rows") + 1 :][:1]
        if not value or not (value[0] == "all" or value[0].isdigit()):
            print("--graph-fraud-rows takes a number, or 'all'", file=sys.stderr)
            return 2
        sample = 0 if value[0] == "all" else int(value[0])
    takes_a_value = {
        "--vault",
        "--inspect-record",
        "--graph-fraud-rows",
        "--repair-limit",
        "--confirm",
    }
    names = [
        a
        for i, a in enumerate(args)
        if not a.startswith("--") and not (i > 0 and args[i - 1] in takes_a_value)
    ]
    if len(names) != 1:
        print(
            f"usage: seed_internal <{'|'.join(sorted(DATASETS))}> [--stop-api] "
            "[--replace-graph] [--reset-graph-database] [--vault ID] [--graph-fraud-rows N|all] "
            "[--repair-strays [--apply] [--repair-limit N]] "
            "[--clear-shared-stores --vault ID [--confirm V:E:N]]",
            file=sys.stderr,
        )
        return 2
    try:
        # Its output was shown as it arrived.
        seed_internal(
            names[0],
            stop_api=stop_api,
            replace_graph=replace_graph,
            reset_graph_database=reset_database,
            vault=vault,
            graph_fraud_rows=sample,
            inspect=inspect,
            inspect_record=record,
            repair_strays=repair_strays,
            apply=apply,
            repair_limit=repair_limit,
            clear_shared_stores=clear_shared_stores,
            confirm=confirm,
        )
    except (SeedRefused, SeedFailed) as error:
        print(f"seed: {error}", file=sys.stderr)
        return 1
    if inspect:
        print("seed: inspection finished; nothing was changed.")
        return 0
    if clear_shared_stores:
        print("seed: clearing finished; read the report above for what was, or was not, deleted.")
        return 0
    if repair_strays:
        print(
            "seed: repair finished; stray records were removed."
            if apply
            else "seed: dry run finished; nothing was changed."
        )
        return 0
    print(f"seed: {names[0]} is loaded. Sign in and choose it from the case picker.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
