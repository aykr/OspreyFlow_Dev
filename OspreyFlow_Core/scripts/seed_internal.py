"""Loads an internal demo dataset into the running deployment, in one command.

    PYTHONPATH=.:packages python -m scripts.seed_internal <dataset> [--stop-api]
    (or, for a demo pack: ospreyflow demo add paysim | hmp | fixture-corp | operation-ledger |
    prison-intelligence)

A caller may run a dataset of its own (`seed_internal(datasets=…, code_mounts=…)`, `main(…)`): its
code folder is mounted read-only beside this checkout's, and every check below — the local
real-data exceptions list, the attested checkout — applies to it unchanged (`06_DECISIONS.md`
ADR-114 Amendment 2: code that exists only for an internal demo lives outside this folder).

The seed runs in a one-shot container from the Conduit's own image, **inside the deployment's
network**, the way `harness.apply` runs its own seeds: the deployment's analytics store is a Docker
volume only the Conduit's image can see, and its Postgres, ArcadeDB and their passwords are only
reachable (and only known) there, so nothing here handles a password. The checkout's `scripts/` and
`packages/` and the data folder are mounted read-only (the image's copy of the packages lags it).

The case the data goes into is made by the seed itself, named, and shared with the two demo accounts
by their identity-provider subjects (the Conduit's principal ids): the demo administrator as Author,
the demo analyst as Editor. Those subjects are read from Keycloak here, on the host, where its admin
API is published. **A deployment with no demo accounts** (a Small, administration guide §5a) shares
it with its first administrator, `admin`, as Author, with no Editor, in the administrator's own unit
— a case of another unit is never listed, whatever its grants — and the Prison Intelligence
Dataset's loads are run as the administrator, there being no demo engineer (ADR-114 Amendment 33, as
found on the first server, 4 November 2026: every pack had been refused there).

**The Prison Intelligence Dataset's three steps** (ADR-127 Amendment 23): `--reset-live` restores it
between rehearsals and, like a seed, needs the Conduit stopped (`--stop-api`); `--release-batch-2`
and `--publish-reports-fallback` are run mid-demo and leave the Conduit running (`_mid_demo`).

**A load's revert** (`--revert-load <load or run id> --reverted-by <you> --stop-api`, build order
step 15) runs `scripts.revert_load` the same way, inside the deployment's network with the Conduit
stopped, since on the host it has no store settings.

**The Conduit must be stopped while a seed runs** (DuckDB's exclusive lock). With it running this
refuses and names `--stop-api`; stopping it is yours to choose, as in `harness.apply`. When it was
stopped for the seed it is started again afterwards, whether the seed worked or not.

An internal dataset is never seeded from anything that left this project (ADR-035 §C1, ADR-053):
this refuses outside a checkout, and passes the container `--attested-checkout` only after checking.
"""

from __future__ import annotations

import dataclasses
import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from harness.apply import _compose
from harness.first_admin import FIRST_ADMIN_USERNAME
from harness.realm import (
    DEMO_ADMIN_SUBJECT,
    DEMO_ANALYST_SUBJECT,
    DEMO_ENGINEER_SUBJECT,
    DEMO_REPORT_VIEWER_SUBJECT,
)
from scripts import real_data_acknowledgement
from scripts.refresh import NothingToRefresh, _deployment_dir, _identity_origin

REPO_ROOT = Path(__file__).resolve().parents[1]
#: Where the data folder is mounted inside the seed's container.
CONTAINER_DATA = "/internal-data"
#: The demo accounts' organisational unit, which the case must share to be visible to them.
DEMO_UNIT = "verify"
#: ADR-138: where `scripts.public_dataset stage` places a public dataset, under the data folder.
PUBLIC_DATA = "public"


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
    #: Whether the seed writes its edges through the bulk loader, its default since ADR-058
    #: Amendment 5 (`--method upsert` still takes the older path).
    bulk: bool = False
    #: Whether the seed keeps its addresses and rewrites its links on `--replace-links`.
    rewrites_links: bool = False
    #: ADR-148 decision 10: the highest marking the pack's data holds, declared only where a test
    #: proves every write it makes is within it (`tests/test_seed_internal_ceiling.py`). None is
    #: judged as the scheme's highest, so a pack is refused under a lower ceiling (fails closed).
    highest_marking: str | None = None
    #: Whether the seed has a rehearsal reset and two mid-demo commands (`--reset-live`,
    #: `--release-batch-2`, `--publish-reports-fallback`: ADR-127 Amendment 23).
    rehearsal: bool = False
    #: The seed's own mid-demo file steps, run as the PID's `--release-batch-2` is, leaving the
    #: Conduit running (Operation Ledger's monitoring week, ADR-108 Amendment 5).
    mid_demo_steps: tuple[str, ...] = ()


#: The PaySim graph sample: the first fraud transactions and everything touching their accounts.
#: The full neighbourhood is ~74,000 accounts and takes many hours to write to a real ArcadeDB.
DEFAULT_GRAPH_SAMPLE = 500

#: Real data is admitted for this use only (ADR-035 §C3, ADR-053).
REAL_DATA_USE = "owner_run_demonstration"

DATASETS: dict[str, Dataset] = {
    "hmp": Dataset(script="scripts.seed_hmp_fixture", case_name="HMP fixture (synthetic demo)"),
    "ledger": Dataset(
        script="scripts.seed_ledger_fixture",
        case_name="Operation Ledger (synthetic demo)",
        mid_demo_steps=("--release-week-2", "--release-list-update", "--reset-week-2"),
    ),
    "fixture-corp": Dataset(
        script="scripts.seed_fixture_corp", case_name="Fixture Corp (synthetic demo)"
    ),
    "paysim": Dataset(
        script="scripts.seed_paysim",
        case_name="PaySim mobile money (internal)",
        highest_marking="OFFICIAL",
        data_folder="PaySIM_Dataset",
        sampled=True,
        bulk=True,
    ),
    # ADR-127 Amendment 23: the synthetic Prison Intelligence Dataset, loaded through the Ingest
    # Studio's own engine from files the seed writes into the dataset's folder of the ingest root.
    "prison-intelligence": Dataset(
        script="scripts.seed_pid",
        case_name="Prison Intelligence Dataset (synthetic demo)",
        rehearsal=True,
    ),
    # ADR-127 Amendment 40: the scale cohort, written straight from the plan (no Studio recipes, no
    # load record), so not a rehearsal; its edges go in bulk.
    "prison-intelligence-scale": Dataset(
        script="scripts.seed_pid_scale",
        case_name="Prison Intelligence Dataset: scale cohort (synthetic demo)",
        bulk=True,
    ),
    # ADR-138: the cyber starter's demo, a synthetic STIX 2.1 intrusion generated deterministically.
    "cyber-intrusion": Dataset(
        script="scripts.seed_cyber_intrusion",
        case_name="Cyber intrusion (synthetic demo)",
        highest_marking="OFFICIAL",
    ),
    # ADR-138 decision 3: a public dataset the administrator downloaded, placed by
    # `scripts.public_dataset stage` under `public/<id>/`; its case is named from its manifest.
    "public": Dataset(script="scripts.seed_public", case_name="", data_folder=PUBLIC_DATA),
    # ADR-114 Amendment 23: real data, an optional download each user makes and accepts.
    "enron": Dataset(
        script="scripts.seed_enron",
        case_name="Enron corpus (real data, this machine only)",
        data_folder="Enron_Mails",
        real_dataset="enron",
        bulk=True,
        rewrites_links=True,
    ),
}


def _checkout_mounts(repo_root: Path, code: Sequence[tuple[Path, str]] = ()) -> list[str]:
    """What every seed container takes from the checkout, read-only: the scripts **and the
    packages they import**. The image carries its own copy of both, built when it was last
    refreshed, so a script that imports something added since (ADR-058's `BulkGraphLoader`, which
    `seed_support` imports) fails with an ImportError unless the packages come from the checkout
    too, as the scripts do. One list for every container run, so no run can be left with the
    image's older copy. `services` too, since ADR-099: the seeds write through
    `services.api.dataset_scope` and make their case's datasets with `services.api.datasets`, and
    the image's older copy of the stamping graph refused the Enron seed's bulk write after it had
    deleted its links (7 October 2026)."""
    mounts = [
        "-v",
        f"{repo_root}/scripts:/app/scripts:ro",
        "-v",
        f"{repo_root}/packages:/app/packages:ro",
        "-v",
        f"{repo_root}/services:/app/services:ro",
        # The connector layouts the recipes read (the call recipe's, the profile a publish builds
        # its recipe from): the image holds only the copy it was built with (ADR-127 Amendment 34).
        "-v",
        f"{repo_root}/connectors:/app/connectors:ro",
    ]
    # A caller's own code folder, read-only too, at the place its modules are imported from.
    for host, container in code:
        mounts += ["-v", f"{host}:{container}:ro"]
    return mounts


RESOLUTION_SWITCH = "OSPREY_POST_INGEST_RESOLUTION"


def _switch_args(directory: Path) -> list[str]:
    """The deployment's rendered `OSPREY_POST_INGEST_RESOLUTION`, passed into the one-shot so the
    seed judges the switch the Conduit runs with (ADR-127 Amendment 34). A deployment rendered
    before the setting existed runs with it on, the default, and is told so."""
    value = "on"
    env = directory / "deployment.env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{RESOLUTION_SWITCH}="):
                value = line.partition("=")[2].strip() or "on"
    return ["-e", f"{RESOLUTION_SWITCH}={value}"]


def _refuse_a_pack_above_the_ceiling(name: str, spec: Dataset, directory: Path) -> None:
    """ADR-148 decision 10: a pack whose data is marked above the deployment's highest marking (its
    rendered `OSPREY_HIGHEST_MARKING`) is refused before its seed starts, so a pack written in
    several transactions is never partly written. Its declared highest, or the scheme's highest
    where it declares none. The engine and the stamping graph refuse each write too."""
    from services.ingest.ceiling import CeilingUnknown, DeploymentCeiling

    from ontology.handling import load_uk_le_scheme

    scheme = load_uk_le_scheme()
    rendered = ""
    env = directory / "deployment.env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("OSPREY_HIGHEST_MARKING="):
                rendered = line.partition("=")[2].strip()
    try:
        ceiling = DeploymentCeiling.of(rendered, scheme)
    except CeilingUnknown as error:
        raise SeedRefused(f"{error}, so no pack is loaded") from error
    held = spec.highest_marking or scheme.classification[-1]
    if ceiling.above(held):
        holds = (
            f"holds data marked up to {held}"
            if spec.highest_marking is not None
            else f"declares no highest marking, so it is judged as the scheme's highest, {held}"
        )
        raise SeedRefused(
            f"the {name} demo pack {holds}, above this deployment's highest marking, "
            f"{ceiling.marking}, so nothing was loaded"
        )


def _run_as_args(subs: Mapping[str, str]) -> list[str]:
    """The demo engineer's sign-in subject, the id the Conduit knows him by, where the identity
    provider has him; a local stack without one takes his username, and the seed says so."""
    return ["--run-as", subs[DEMO_ENGINEER_SUBJECT]] if DEMO_ENGINEER_SUBJECT in subs else []


@dataclass(frozen=True)
class Sharing:
    """Whom a seeded case is shared with, in which unit, and whom a pipeline load runs as."""

    grants: tuple[str, ...]
    unit: str
    run_as: tuple[str, ...]
    #: Said after the seed, when the case's Author needs something more to open it.
    note: str | None = None


#: Said when the first administrator is the case's Author. They hold the Analyst role as well as
#: Admin from the start (`harness.first_admin.FIRST_ADMIN_ROLES`), so the case opens for them.
ADMIN_AUTHOR_NOTE = (
    "{username}, the first administrator, is its Author, in the unit '{unit}' (there are no "
    "demo accounts)."
)


def _sharing(
    directory: Path,
    subs: Mapping[str, str],
    lookup_unit: Callable[[Path, str], str],
    *,
    required: bool,
) -> Sharing:
    """The demo accounts where they exist, as before; else the first administrator, in their own
    unit. With neither, a seed is refused (a case nobody can open), and a mid-demo step, which makes
    no case, keeps the demo unit and the engineer's username, as a local stack always has."""
    demo = [name for name in (DEMO_ADMIN_SUBJECT, DEMO_ANALYST_SUBJECT) if name in subs]
    if len(demo) == 2:
        return Sharing(
            grants=(f"{subs[DEMO_ADMIN_SUBJECT]}=author", f"{subs[DEMO_ANALYST_SUBJECT]}=editor"),
            unit=DEMO_UNIT,
            run_as=tuple(_run_as_args(subs)),
        )
    if not demo and FIRST_ADMIN_USERNAME in subs:
        unit = lookup_unit(directory, FIRST_ADMIN_USERNAME)
        return Sharing(
            grants=(f"{subs[FIRST_ADMIN_USERNAME]}=author",),
            unit=unit,
            run_as=("--run-as", subs[FIRST_ADMIN_USERNAME]),
            note=ADMIN_AUTHOR_NOTE.format(username=FIRST_ADMIN_USERNAME, unit=unit),
        )
    if not required:
        return Sharing(grants=(), unit=DEMO_UNIT, run_as=tuple(_run_as_args(subs)))
    if demo:
        missing = [n for n in (DEMO_ADMIN_SUBJECT, DEMO_ANALYST_SUBJECT) if n not in subs]
        raise SeedRefused(
            f"{', '.join(missing)} not found in the identity provider, so the case could not be "
            "shared with it. Run `ospreyflow repair-sign-in` and try again"
        )
    raise SeedRefused(
        f"neither the demo accounts ({DEMO_ADMIN_SUBJECT}, {DEMO_ANALYST_SUBJECT}) nor the first "
        f"administrator ({FIRST_ADMIN_USERNAME}) is in the identity provider, so the case could "
        "not be shared with anyone who could open it; nothing was started. On a deployment with "
        "demo accounts run `ospreyflow repair-sign-in`; on one without them, make the first "
        "administrator (`python -m harness.first_admin --deployment <its folder>`) and try again"
    )


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
    issuer = _identity_origin(directory / "deployment.env")
    token = keycloak_admin.admin_token(
        issuer=issuer, admin_user="admin", admin_password=values[ADMIN_PASSWORD_KEY]
    )
    found: dict[str, str] = {}
    for username in (DEMO_ADMIN_SUBJECT, DEMO_ANALYST_SUBJECT, DEMO_ENGINEER_SUBJECT,
                     DEMO_REPORT_VIEWER_SUBJECT, FIRST_ADMIN_USERNAME):  # fmt: skip
        try:
            found[username] = keycloak_admin.user_id(
                issuer=issuer, realm="osprey", token=token, username=username
            )
        except keycloak_admin.RealmConfigurationFailed:
            continue
    return found


def _lookup_unit(directory: Path, username: str) -> str:
    """The unit an account belongs to (its `org_unit` attribute), from the published Keycloak admin
    API, so the case is made where that account will see it."""
    from harness import keycloak_admin
    from harness.register_sign_in import ADMIN_PASSWORD_KEY, _read_env

    values = _read_env(directory / "deployment.env")
    issuer = _identity_origin(directory / "deployment.env")
    token = keycloak_admin.admin_token(
        issuer=issuer, admin_user="admin", admin_password=values[ADMIN_PASSWORD_KEY]
    )
    status, found = keycloak_admin._call(
        f"{issuer}/admin/realms/osprey/users?username={username}&exact=true", token=token
    )
    units = (found[0].get("attributes") or {}).get("org_unit") if status == 200 and found else None
    if not units:
        raise SeedRefused(
            f"{username} has no unit in the identity provider, so the case could not be made "
            f"where {username} would see it. Set one in Admin, People and roles and try again"
        )
    return str(units[0])


def seed_internal(
    dataset: str,
    repo_root: Path = REPO_ROOT,
    *,
    run: Callable[[Sequence[str]], str] = _run,
    lookup_subs: Callable[[Path], dict[str, str]] = _lookup_subs,
    lookup_unit: Callable[[Path, str], str] = _lookup_unit,
    api_running: Callable[[list[str]], bool] = _api_running,
    stop_api: bool = False,
    permitted: Callable[[str, str], bool] = _permitted,
    replace_graph: bool = False,
    replace_events: bool = False,
    replace_links: bool = False,
    reset_graph_database: bool = False,
    vault: str | None = None,
    graph_fraud_rows: int | None = None,
    method: str | None = None,
    compare_vaults: tuple[str, str] | None = None,
    spike_bulk_transport: bool = False,
    spike_edges: int | None = None,
    probe_lookup_cost: bool = False,
    probe_sizes: str | None = None,
    inspect: bool = False,
    inspect_record: str | None = None,
    repair_strays: bool = False,
    restore_missing: bool = False,
    apply: bool = False,
    repair_limit: int | None = None,
    clear_shared_stores: bool = False,
    confirm: str | None = None,
    accept_strays: int = 0,
    reset_live: bool = False,
    release_batch_2: bool = False,
    publish_reports_fallback: bool = False,
    check: bool = False,
    mid_demo_step: str | None = None,
    datasets: Mapping[str, Dataset] = DATASETS,
    code_mounts: Sequence[tuple[Path, str]] = (),
    case_domains: Sequence[str] | None = None,
    public_id: str | None = None,
    revert_load: tuple[str, str] | None = None,
) -> list[str]:
    """Return the seed report, one line each. Raises `SeedRefused` before starting anything.

    `case_domains` (ADR-138: a starter's) are the domain packs the case is set to while nobody has
    chosen, instead of the seed's own. `public_id` names the public dataset `public` loads."""
    if dataset not in datasets:
        raise SeedRefused(f"unknown dataset {dataset!r}; known: {', '.join(sorted(datasets))}")
    spec = datasets[dataset]
    public_args: list[str] = []
    if (dataset == "public") != (public_id is not None):
        raise SeedRefused("--public-id goes with the dataset public, and public needs it")
    if public_id is not None:
        spec, public_args, case_domains = _public_dataset(
            spec, public_id, case_domains, repo_root
        )
    if repair_strays and restore_missing:
        raise SeedRefused("--repair-strays and --restore-missing are run one at a time")
    if apply and not (repair_strays or restore_missing):
        raise SeedRefused("--apply only goes with --repair-strays or --restore-missing")
    rehearsal_steps = [
        flag
        for flag, asked in (
            ("--reset-live", reset_live),
            ("--release-batch-2", release_batch_2),
            ("--publish-reports-fallback", publish_reports_fallback),
            ("--check", check),
        )
        if asked
    ]
    if rehearsal_steps and not spec.rehearsal:
        raise SeedRefused(
            f"{', '.join(rehearsal_steps)} is only built for prison-intelligence so far"
        )
    if len(rehearsal_steps) > 1:
        raise SeedRefused(f"{' and '.join(rehearsal_steps)} are run one at a time")
    if mid_demo_step is not None:
        if mid_demo_step not in spec.mid_demo_steps:
            built = [n for n, d in datasets.items() if mid_demo_step in d.mid_demo_steps]
            raise SeedRefused(
                f"{mid_demo_step} is only built for {', '.join(built) or 'no dataset'} so far"
            )
        if rehearsal_steps:
            raise SeedRefused(f"{mid_demo_step} and {rehearsal_steps[0]} are run one at a time")
    if clear_shared_stores and not spec.sampled:
        raise SeedRefused("--clear-shared-stores is only built for paysim so far")
    if clear_shared_stores and vault is None:
        raise SeedRefused(
            "--clear-shared-stores needs --vault <id>: it only clears the shared stores once that "
            "vault has been checked"
        )
    if confirm is not None and not clear_shared_stores:
        raise SeedRefused("--confirm only goes with --clear-shared-stores")
    if accept_strays and not clear_shared_stores:
        raise SeedRefused("--accept-strays only goes with --clear-shared-stores")
    if (repair_strays or restore_missing) and not spec.sampled:
        raise SeedRefused("--repair-strays and --restore-missing are only built for paysim so far")
    if reset_graph_database and not spec.sampled:
        raise SeedRefused("--reset-graph-database is only built for paysim so far")
    if method is None:
        method = "bulk" if spec.bulk else "upsert"
    if method not in ("upsert", "bulk"):
        raise SeedRefused(f"unknown --method {method!r}; use upsert or bulk")
    if compare_vaults is not None:
        if not spec.sampled:
            raise SeedRefused("--compare-vaults is only built for paysim so far")
        for name in compare_vaults:
            if not re.fullmatch(r"[a-z][a-z0-9-]{0,30}", name):
                raise SeedRefused(f"{name!r} is not a vault id")
    if spike_edges is not None and not spike_bulk_transport:
        raise SeedRefused("--spike-edges only goes with --spike-bulk-transport")
    if spike_edges is not None and not 100 <= spike_edges <= 100_000:
        raise SeedRefused("--spike-edges takes a number from 100 to 100000")
    if spike_bulk_transport and not spec.sampled:
        raise SeedRefused("--spike-bulk-transport is only built for paysim so far")
    if probe_sizes is not None and not probe_lookup_cost:
        raise SeedRefused("--probe-sizes only goes with --probe-lookup-cost")
    if probe_sizes is not None and not _valid_probe_sizes(probe_sizes):
        raise SeedRefused(
            "--probe-sizes takes two to five account counts, rising, each from 100 to 50000, "
            "for example 1000,5000,15000"
        )
    if probe_lookup_cost and not spec.sampled:
        raise SeedRefused("--probe-lookup-cost is only built for paysim so far")
    if method != "upsert" and not spec.bulk:
        raise SeedRefused(
            f"--method bulk is not built for {dataset}: its seed does not write in bulk"
        )
    if vault is not None:
        if not spec.sampled:
            raise SeedRefused("--vault is only built for paysim so far")
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,30}", vault):
            raise SeedRefused(
                f"{vault!r} is not a vault id: lower-case letters, digits and hyphens, starting "
                "with a letter, at most 31 characters"
            )
    chosen_data = os.environ.get("OSPREYFLOW_DEMO_DATA")
    data_root = Path(chosen_data) if chosen_data else repo_root.parent / "OspreyFlow_Data"
    # ADR-114 Amendment 23: accepted on this machine by the person who added it, or the owner's
    # local exceptions entry (ADR-035 §C3, ADR-053).
    if spec.real_dataset == "public":
        folder = data_root / (spec.data_folder or "")
        if not (folder / real_data_acknowledgement.RECORD).is_file():
            raise SeedRefused(
                f"{spec.case_name} holds real personal data and has not been accepted on this "
                "machine: add it with `ospreyflow demo add public`, which says what it is and asks "
                "first; nothing was started"
            )
    elif spec.real_dataset and not (
        real_data_acknowledgement.accepted(data_root / (spec.data_folder or ""), spec.real_dataset)
        or permitted(spec.real_dataset, REAL_DATA_USE)
    ):
        raise SeedRefused(
            f"{spec.real_dataset!r} is real data and has not been accepted on this machine: add it "
            f"with `ospreyflow demo add {spec.real_dataset} --file <the downloaded file>`, which "
            "says what it is and asks first; nothing was started"
        )
    # The developer repository keeps the product one folder below the checkout; the user
    # repository (ADR-114) is the product itself.
    if not ((repo_root / ".git").exists() or (repo_root.parent / ".git").exists()):
        raise SeedRefused(
            "this is not a checkout of the repository: an internal dataset is only ever seeded "
            "from one, never from a built bundle"
        )
    try:
        directory = _deployment_dir(repo_root)
    except NothingToRefresh as error:
        raise SeedRefused(str(error)) from error
    if revert_load is not None:
        return _revert_load(repo_root, directory, run, api_running, stop_api, *revert_load)
    if not (inspect or inspect_record or compare_vaults or check):
        _refuse_a_pack_above_the_ceiling(dataset, spec, directory)
    if spec.data_folder and not (data_root / spec.data_folder).is_dir():
        raise SeedRefused(
            f"the dataset is not provisioned: {data_root / spec.data_folder} is missing"
        )
    if mid_demo_step is not None:
        return _mid_demo(
            spec, repo_root, directory, run,
            _sharing(directory, lookup_subs(directory), lookup_unit, required=False),
            mid_demo_step, code_mounts,
        )  # fmt: skip
    if release_batch_2 or publish_reports_fallback or check:
        return _mid_demo(
            spec,
            repo_root,
            directory,
            run,
            _sharing(directory, lookup_subs(directory), lookup_unit, required=False),
            "--release-batch-2"
            if release_batch_2
            else "--check"
            if check
            else "--publish-reports-fallback",
            code_mounts,
        )
    if compare_vaults is not None:
        return _compare_vaults(repo_root, directory, run, *compare_vaults)
    if spike_bulk_transport:
        return _spike_bulk_transport(repo_root, directory, run, spike_edges)
    if probe_lookup_cost:
        return _probe_lookup_cost(repo_root, directory, run, probe_sizes)
    if inspect:
        return _inspect(spec, repo_root, directory, run, inspect_record, vault, code_mounts)
    if repair_strays or restore_missing:
        return _repair_strays(
            spec,
            repo_root,
            directory,
            run,
            vault,
            apply,
            repair_limit,
            restore=restore_missing,
            graph_fraud_rows=graph_fraud_rows,
            data_root=data_root,
        )
    if clear_shared_stores:
        return _clear_shared_stores(
            repo_root, directory, run, api_running, stop_api, vault or "", confirm, accept_strays
        )
    subs = lookup_subs(directory)
    sharing = _sharing(directory, subs, lookup_unit, required=True)

    compose = _compose(directory / "compose.yaml")
    running = api_running(compose)
    if running and not stop_api:
        raise SeedRefused(
            "the Conduit is running, and a seed needs it stopped (DuckDB's exclusive lock). "
            "Run again with --stop-api to stop it for the seed and start it again after; "
            "stopping it is your choice, so it is not done for you"
        )
    mounts = _checkout_mounts(repo_root, code_mounts)
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
        *_switch_args(directory),
        "api",
        "-m",
        spec.script,
        "--case-name",
        spec.case_name,
        "--org-unit",
        sharing.unit,
        *(sharing.run_as if spec.rehearsal else ()),
        *(word for grant in sharing.grants for word in ("--grant", grant)),
    ]
    # ADR-113 decision 8: the engineer edits and the report viewer reads each seeded *synthetic*
    # case — where those personas exist (a deployment registered before them seeds without them).
    # A real dataset (rule 9's local exception) is shared with no further persona.
    for persona, level in (
        (DEMO_ENGINEER_SUBJECT, "editor"),
        (DEMO_REPORT_VIEWER_SUBJECT, "viewer"),
    ):
        if persona in subs and not spec.real_dataset:
            argv += ["--grant", f"{subs[persona]}={level}"]
    if spec.data_folder:
        argv += ["--data-dir", CONTAINER_DATA, "--attested-checkout"]
    if spec.real_dataset and spec.real_dataset != "public":
        argv.append("--attested-permission")
    argv += public_args
    if case_domains is not None:
        argv += ["--case-domains", ",".join(case_domains)]
    if replace_graph and spec.data_folder:
        argv.append("--replace-graph")
    if replace_events and spec.data_folder:
        argv.append("--replace-events")
    if replace_links:
        # Only a seed that keeps its addresses rewrites its links (the Enron seed, 7 October 2026).
        if not spec.rewrites_links:
            raise SeedRefused(f"--replace-links is not built for {dataset}")
        argv.append("--replace-links")
    if reset_graph_database:
        argv.append("--reset-graph-database")
    if reset_live:
        argv.append("--reset-live")
    if vault is not None:
        argv += ["--vault", vault]
    if spec.bulk:
        # Always said, so the script's own default never decides (ADR-058 Amendment 5).
        argv += ["--method", method]
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
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if sharing.note is not None:
        print(sharing.note, flush=True)
        lines.append(sharing.note)
    return lines


def _revert_load(
    repo_root: Path,
    directory: Path,
    run: Callable[[Sequence[str]], str],
    api_running: Callable[[list[str]], bool],
    stop_api: bool,
    load_id: str,
    reverted_by: str,
) -> list[str]:
    """`scripts.revert_load` inside the deployment (build order step 15; `DEMO_GUIDE.md` §8b): run
    on the host it has no store settings and would reach ArcadeDB's default port, 2480, so it runs
    here as a seed does, in a one-shot from the Conduit's image on the deployment's own network,
    with the checkout's code. The Conduit is stopped for it (DuckDB's lock; with ClickHouse a quiet
    Conduit is advised, `scripts/revert_load.py`) and started again, whether it worked or not.
    `load_id` is a load's, a branch's, a pipeline run's or a ledger run's id."""
    compose = _compose(directory / "compose.yaml")
    running = api_running(compose)
    if running and not stop_api:
        raise SeedRefused(
            "the Conduit is running, and a revert needs it stopped (DuckDB's exclusive lock). "
            "Run again with --stop-api to stop it for the revert and start it again after; "
            "stopping it is your choice, so it is not done for you"
        )
    argv = [
        *compose, "run", "--rm", "--no-deps", "--entrypoint", "python",
        *_checkout_mounts(repo_root), "api",
        "-m", "scripts.revert_load", load_id, "--reverted-by", reverted_by,
    ]  # fmt: skip
    if running:
        run([*compose, "stop", "api"])
    try:
        output = run(argv)
    finally:
        if running:
            run([*compose, "up", "-d", "--wait", "api"])
    return [line.strip() for line in output.splitlines() if line.strip()]


def _public_dataset(
    spec: Dataset, public_id: str, case_domains: Sequence[str] | None, repo_root: Path
) -> tuple[Dataset, list[str], Sequence[str] | None]:
    """The `public` seed made particular to one staged dataset: its folder, its case's name and
    domains from its manifest, and whether it is real data (ADR-138 decision 3)."""
    import yaml

    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,47}", public_id):
        raise SeedRefused(f"{public_id!r} is not a public dataset's id")
    chosen = os.environ.get("OSPREYFLOW_DEMO_DATA")
    root = Path(chosen) if chosen else repo_root.parent / "OspreyFlow_Data"
    folder = f"{PUBLIC_DATA}/{public_id}"
    manifest_path = root / folder / "dataset.yaml"
    if not manifest_path.is_file():
        raise SeedRefused(
            f"the public dataset {public_id} is not placed: {manifest_path} is missing. Add it "
            "with "
            "`ospreyflow demo add public --file <path> --manifest <dataset.yaml>`"
        )
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    name = str(manifest.get("name") or public_id)
    real = bool(manifest.get("real_personal_data"))
    particular = dataclasses.replace(
        spec,
        case_name=f"{name} ({'real data, this machine only' if real else 'public dataset'})"[:200],
        data_folder=folder,
        real_dataset="public" if real else None,
    )
    domains = case_domains if case_domains is not None else list(manifest.get("domains") or [])
    return particular, ["--dataset-id", public_id], domains


def _inspect(
    spec: Dataset,
    repo_root: Path,
    directory: Path,
    run: Callable[[Sequence[str]], str],
    record: str | None,
    vault: str | None = None,
    code_mounts: Sequence[tuple[Path, str]] = (),
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
        *_checkout_mounts(repo_root, code_mounts),
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


def _mid_demo(
    spec: Dataset,
    repo_root: Path,
    directory: Path,
    run: Callable[[Sequence[str]], str],
    sharing: Sharing,
    flag: str,
    code_mounts: Sequence[tuple[Path, str]] = (),
) -> list[str]:
    """The two commands a presenter runs mid-demo (ADR-127 Amendment 23): `--release-batch-2` copies
    a file into the dataset's folder, and `--publish-reports-fallback` writes only Postgres and the
    recipe repository, so neither needs DuckDB and **the Conduit is left running**: it is never
    stopped or started here, and no case is made or shared. Run in a one-shot container from the
    Conduit's image with the checkout's code mounted (as the inspection modes are), not by `exec`
    into the running one, whose image may hold an older copy of the code. The unit is passed because
    the fallback publishes in it."""
    argv = [
        *_compose(directory / "compose.yaml"),
        "run",
        "--rm",
        "--no-deps",
        "--entrypoint",
        "python",
        *_checkout_mounts(repo_root, code_mounts),
        *_switch_args(directory),
        "api",
        "-m",
        spec.script,
        flag,
        "--org-unit",
        sharing.unit,
        *sharing.run_as,
    ]
    if flag == "--check":
        # It reads the case, so it is told which (it makes none, and shares none).
        argv += ["--case-name", spec.case_name]
    output = run(argv)
    return [line.strip() for line in output.splitlines() if line.strip()]


def _compare_vaults(
    repo_root: Path,
    directory: Path,
    run: Callable[[Sequence[str]], str],
    left: str,
    right: str,
) -> list[str]:
    """Compare two vaults' graphs (`scripts.compare_vaults`, ADR-058 D9). Read only: `SELECT`
    alone is sent, no case is made, and the Conduit is left running."""
    argv = [
        *_compose(directory / "compose.yaml"),
        "run",
        "--rm",
        "--no-deps",
        "--entrypoint",
        "python",
        *_checkout_mounts(repo_root),
        "api",
        "-m",
        "scripts.compare_vaults",
        left,
        right,
    ]
    output = run(argv)
    return [line.strip() for line in output.splitlines() if line.strip()]


def _spike_bulk_transport(
    repo_root: Path,
    directory: Path,
    run: Callable[[Sequence[str]], str],
    edges: int | None = None,
) -> list[str]:
    """Run the bulk-transport spike (`scripts.spike_bulk_transport`, ADR-058 D10) inside the
    deployment's network, the only place the graph store is reachable from. It touches only
    scratch databases named `spike_bulk_*`, which it drops afterwards: no case is made, no vault
    is opened and the Conduit is left running. Run it with the store otherwise idle."""
    argv = [
        *_compose(directory / "compose.yaml"),
        "run",
        "--rm",
        "--no-deps",
        "--entrypoint",
        "python",
        *_checkout_mounts(repo_root),
        "api",
        "-m",
        "scripts.spike_bulk_transport",
    ]
    if edges is not None:
        argv += ["--edges", str(edges)]
    output = run(argv)
    return [line.strip() for line in output.splitlines() if line.strip()]


def _valid_probe_sizes(text: str) -> bool:
    parts = text.split(",")
    if not 2 <= len(parts) <= 5 or not all(p.isdigit() for p in parts):
        return False
    sizes = [int(p) for p in parts]
    return sizes == sorted(set(sizes)) and all(100 <= n <= 50_000 for n in sizes)


def _probe_lookup_cost(
    repo_root: Path,
    directory: Path,
    run: Callable[[Sequence[str]], str],
    sizes: str | None = None,
) -> list[str]:
    """Run the lookup-cost probe (`scripts.probe_lookup_cost`, ADR-058 Amendment 5) inside the
    deployment's network. Like the spike it touches only a scratch database named `spike_bulk_*`,
    which it drops afterwards: no case, no vault, the Conduit left running. Run it with the store
    otherwise idle."""
    argv = [
        *_compose(directory / "compose.yaml"),
        "run",
        "--rm",
        "--no-deps",
        "--entrypoint",
        "python",
        *_checkout_mounts(repo_root),
        "api",
        "-m",
        "scripts.probe_lookup_cost",
    ]
    if sizes is not None:
        argv += ["--sizes", sizes]
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
    *,
    restore: bool,
    graph_fraud_rows: int | None,
    data_root: Path,
) -> list[str]:
    """Put right the edges a load got wrong (ADR-056 Amendment 17): `--repair-strays` removes the
    copies of an id stored twice and writes the edge once; `--restore-missing` writes edges the
    dataset has and the graph lacks. Both write the edge again from the dataset, so the container
    gets the file and the same graph sample the load used. Like an inspection they make no case,
    load no events, and leave the Conduit running: they touch only the graph database. Without
    `apply` they are a dry run."""
    argv = [
        *_compose(directory / "compose.yaml"),
        "run",
        "--rm",
        "--no-deps",
        "--entrypoint",
        "python",
        *_checkout_mounts(repo_root),
        "-v",
        f"{data_root}:{CONTAINER_DATA}:ro",
        "api",
        "-m",
        spec.script,
        "--restore-missing" if restore else "--repair-strays",
        "--data-dir",
        CONTAINER_DATA,
        "--attested-checkout",
    ]
    sample = DEFAULT_GRAPH_SAMPLE if graph_fraud_rows is None else graph_fraud_rows
    if sample > 0:
        argv += ["--graph-fraud-rows", str(sample)]
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
    accept_strays: int = 0,
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
        *_checkout_mounts(repo_root),
        "api",
        "-m",
        "scripts.clear_shared_stores",
        "--vault",
        vault,
    ]
    if confirm is not None:
        argv += ["--confirm", confirm]
    if accept_strays:
        argv += ["--accept-strays", str(accept_strays)]
    if running:
        run([*compose, "stop", "api"])
    try:
        output = run(argv)
    finally:
        if running:
            run([*compose, "up", "-d", "--wait", "api"])
    return [line.strip() for line in output.splitlines() if line.strip()]


def main(
    argv: list[str] | None = None,
    *,
    datasets: Mapping[str, Dataset] = DATASETS,
    code_mounts: Sequence[tuple[Path, str]] = (),
) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    # ADR-114 Amendment 4 decision 7: the deployment's names reach its proxy on this machine.
    from harness.site import answer_localhost_with_loopback

    answer_localhost_with_loopback()
    stop_api = "--stop-api" in args
    replace_graph = "--replace-graph" in args
    replace_events = "--replace-events" in args
    replace_links = "--replace-links" in args
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
    restore_missing = "--restore-missing" in args
    clear_shared_stores = "--clear-shared-stores" in args
    reset_live = "--reset-live" in args
    release_batch_2 = "--release-batch-2" in args
    publish_reports_fallback = "--publish-reports-fallback" in args
    check = "--check" in args
    asked_steps = sorted({step for d in datasets.values() for step in d.mid_demo_steps} & set(args))
    if len(asked_steps) > 1:
        print(f"{' and '.join(asked_steps)} are run one at a time", file=sys.stderr)
        return 2
    mid_demo_step = asked_steps[0] if asked_steps else None
    confirm: str | None = None
    if "--confirm" in args:
        value = args[args.index("--confirm") + 1 :][:1]
        if not value or value[0].startswith("--"):
            print("--confirm takes the counts the dry run reported, v:e:n", file=sys.stderr)
            return 2
        confirm = value[0]
    accept_strays = 0
    if "--accept-strays" in args:
        value = args[args.index("--accept-strays") + 1 :][:1]
        if not value or not value[0].isdigit():
            print("--accept-strays takes the number of strays, for example 8", file=sys.stderr)
            return 2
        accept_strays = int(value[0])
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
    compare: tuple[str, str] | None = None
    if "--compare-vaults" in args:
        pair = args[args.index("--compare-vaults") + 1 :][:2]
        if len(pair) != 2 or any(v.startswith("--") for v in pair):
            print(
                "--compare-vaults takes two vault ids, for example paysim paysim-perftst",
                file=sys.stderr,
            )
            return 2
        compare = (pair[0], pair[1])
    spike = "--spike-bulk-transport" in args
    spike_edges: int | None = None
    if "--spike-edges" in args:
        value = args[args.index("--spike-edges") + 1 :][:1]
        if not value or not value[0].isdigit():
            print("--spike-edges takes a number, for example 10000", file=sys.stderr)
            return 2
        spike_edges = int(value[0])
    probe = "--probe-lookup-cost" in args
    probe_sizes: str | None = None
    if "--probe-sizes" in args:
        value = args[args.index("--probe-sizes") + 1 :][:1]
        if not value or value[0].startswith("--"):
            print(
                "--probe-sizes takes account counts, for example 1000,5000,15000", file=sys.stderr
            )
            return 2
        probe_sizes = value[0]
    method: str | None = None
    if "--method" in args:
        value = args[args.index("--method") + 1 :][:1]
        if not value or value[0] not in ("upsert", "bulk"):
            print("--method takes upsert or bulk", file=sys.stderr)
            return 2
        method = value[0]
    sample: int | None = None
    if "--graph-fraud-rows" in args:
        value = args[args.index("--graph-fraud-rows") + 1 :][:1]
        if not value or not (value[0] == "all" or value[0].isdigit()):
            print("--graph-fraud-rows takes a number, or 'all'", file=sys.stderr)
            return 2
        sample = 0 if value[0] == "all" else int(value[0])
    revert: tuple[str, str] | None = None
    if "--revert-load" in args:
        value = args[args.index("--revert-load") + 1 :][:1]
        who = args[args.index("--reverted-by") + 1 :][:1] if "--reverted-by" in args else []
        if not value or value[0].startswith("--") or not who or who[0].startswith("--"):
            print(
                "--revert-load takes a load's or a run's id, and --reverted-by the person "
                "reverting it, for example --revert-load 01K... --reverted-by osprey-demo-engineer",
                file=sys.stderr,
            )
            return 2
        revert = (value[0], who[0])
    takes_a_value = {
        "--revert-load",
        "--reverted-by",
        "--vault",
        "--method",
        "--spike-edges",
        "--probe-sizes",
        "--inspect-record",
        "--graph-fraud-rows",
        "--repair-limit",
        "--confirm",
        "--accept-strays",
        "--case-domains",
        "--public-id",
    }
    case_domains: list[str] | None = None
    if "--case-domains" in args:
        value = args[args.index("--case-domains") + 1 :][:1]
        if not value or value[0].startswith("--"):
            print("--case-domains takes packs, for example niem or fibo,niem", file=sys.stderr)
            return 2
        case_domains = [d for d in value[0].split(",") if d]
    public_id: str | None = None
    if "--public-id" in args:
        value = args[args.index("--public-id") + 1 :][:1]
        if not value or value[0].startswith("--"):
            print("--public-id takes the dataset's id, for example vast-2012-mc2", file=sys.stderr)
            return 2
        public_id = value[0]
    names = [
        a
        for i, a in enumerate(args)
        if not a.startswith("--")
        and not (i > 0 and args[i - 1] in takes_a_value)
        and not (compare and a in compare and i > args.index("--compare-vaults"))
    ]
    if len(names) != 1:
        print(
            f"usage: seed_internal <{'|'.join(sorted(datasets))}> [--stop-api] "
            "[--replace-graph] [--replace-events] [--replace-links] [--reset-graph-database] "
            "[--vault ID] "
            "[--method upsert|bulk] "
            "[--compare-vaults A B] [--spike-bulk-transport [--spike-edges N]] "
            "[--probe-lookup-cost [--probe-sizes A,B,C]] "
            "[--graph-fraud-rows N|all] "
            "[--repair-strays | --restore-missing [--apply] [--repair-limit N]] "
            "[--clear-shared-stores --vault ID [--accept-strays N] [--confirm V:E:N]] "
            "[--reset-live | --release-batch-2 | --publish-reports-fallback | --check] "
            "[--release-week-2 | --release-list-update | --reset-week-2] "
            "[--revert-load ID --reverted-by YOU --stop-api]",
            file=sys.stderr,
        )
        return 2
    try:
        # Its output was shown as it arrived.
        seed_internal(
            names[0],
            stop_api=stop_api,
            replace_graph=replace_graph,
            replace_events=replace_events,
            replace_links=replace_links,
            reset_graph_database=reset_database,
            vault=vault,
            graph_fraud_rows=sample,
            method=method,
            compare_vaults=compare,
            spike_bulk_transport=spike,
            spike_edges=spike_edges,
            probe_lookup_cost=probe,
            probe_sizes=probe_sizes,
            inspect=inspect,
            inspect_record=record,
            repair_strays=repair_strays,
            restore_missing=restore_missing,
            apply=apply,
            repair_limit=repair_limit,
            clear_shared_stores=clear_shared_stores,
            confirm=confirm,
            accept_strays=accept_strays,
            reset_live=reset_live,
            release_batch_2=release_batch_2,
            publish_reports_fallback=publish_reports_fallback,
            check=check,
            mid_demo_step=mid_demo_step,
            datasets=datasets,
            code_mounts=code_mounts,
            case_domains=case_domains,
            public_id=public_id,
            revert_load=revert,
        )
    except (SeedRefused, SeedFailed) as error:
        print(f"seed: {error}", file=sys.stderr)
        return 1
    if spike:
        print(
            "seed: spike finished; its scratch databases were dropped and nothing else was touched."
        )
        return 0
    if probe:
        print(
            "seed: probe finished; its scratch database was dropped and nothing else was touched."
        )
        return 0
    if compare:
        print("seed: comparison finished; nothing was changed.")
        return 0
    if inspect:
        print("seed: inspection finished; nothing was changed.")
        return 0
    if clear_shared_stores:
        print("seed: clearing finished; read the report above for what was, or was not, deleted.")
        return 0
    if reset_live:
        print("seed: reset finished; the report above says what it restored and could not undo.")
        return 0
    if revert:
        print("seed: revert finished; the report above says what it took back.")
        return 0
    if release_batch_2 or publish_reports_fallback or check or mid_demo_step:
        print("seed: done; the Conduit was left running.")
        return 0
    if repair_strays or restore_missing:
        print(
            "seed: repair finished; read the report above for what was written."
            if apply
            else "seed: dry run finished; nothing was changed."
        )
        return 0
    print(f"seed: {names[0]} is loaded. Sign in and choose it from the case picker.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
