"""Loads an internal demo dataset into the running deployment, in one command.

    PYTHONPATH=.:packages:../OspreyFlow_Build python -m scripts.seed_internal paysim [--stop-api]
    (or: make seed-paysim)

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
    data_folder: str


DATASETS: dict[str, Dataset] = {
    "paysim": Dataset(
        script="scripts.seed_paysim",
        case_name="PaySim mobile money (internal)",
        data_folder="PaySIM_Dataset",
    ),
}


def _run(argv: Sequence[str]) -> str:
    result = subprocess.run(list(argv), capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise SeedFailed(f"`{' '.join(argv[:6])} …` exited {result.returncode}\n{result.stderr}")
    return result.stdout


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
) -> list[str]:
    """Return the seed report, one line each. Raises `SeedRefused` before starting anything."""
    if dataset not in DATASETS:
        raise SeedRefused(f"unknown dataset {dataset!r}; known: {', '.join(sorted(DATASETS))}")
    spec = DATASETS[dataset]
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
    if not (data_root / spec.data_folder).is_dir():
        raise SeedRefused(
            f"the dataset is not provisioned: {data_root / spec.data_folder} is missing"
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
    argv = [
        *compose,
        "run",
        "--rm",
        "--no-deps",
        "--entrypoint",
        "python",
        "-v",
        f"{repo_root}/scripts:/app/scripts:ro",
        "-v",
        f"{data_root}:{CONTAINER_DATA}:ro",
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
        "--data-dir",
        CONTAINER_DATA,
        "--attested-checkout",
    ]
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
    names = [a for a in args if not a.startswith("--")]
    if len(names) != 1:
        print(f"usage: seed_internal <{'|'.join(sorted(DATASETS))}> [--stop-api]", file=sys.stderr)
        return 2
    try:
        for line in seed_internal(names[0], stop_api=stop_api):
            print(f"  seed[{names[0]}]: {line}")
    except (SeedRefused, SeedFailed) as error:
        print(f"seed: {error}", file=sys.stderr)
        return 1
    print(f"seed: {names[0]} is loaded. Sign in and choose it from the case picker.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
