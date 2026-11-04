"""Demo packs through the command (ADR-114 decision 5; Amendment 3 decision 4).

A pack is seeded by the product's own `scripts.seed_internal`; PaySim, which is a download rather
than generated, is checked by `scripts.demo_packs verify` before anything else starts.
"""

from __future__ import annotations

import filecmp
import json
import shutil
import tarfile
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path

from .answers import RESOLUTION_OFF_PACKS
from .home import CommandRefused, python_for
from .run import Capture, Runner, StepFailed

#: The pack id each pack is seeded under in `scripts.seed_internal.DATASETS`.
PACK_KEYS = {
    "hmp": "hmp",
    "fixture-corp": "fixture-corp",
    "operation-ledger": "ledger",
    "paysim": "paysim",
    "enron": "enron",
    "prison-intelligence": "prison-intelligence",
    "prison-intelligence-scale": "prison-intelligence-scale",
    # ADR-138: the synthetic STIX 2.1 intrusion case, the cyber starter's demo.
    "cyber-intrusion": "cyber-intrusion",
}
#: Build order step 25 (c), ADR-127 Amendment 46: `RESOLUTION_OFF_PACKS` (from the answers, which
#: turn resolution off for them at install) load only while post-ingest resolution is off. A live
#: load in the Prison Intelligence demonstration would otherwise queue resolution, whose worker
#: writes `SAME_AS` links across the corpus, and every rehearsal reset would refuse. Resolution is
#: the whole deployment's setting; no case or dataset can turn it off on its own.
#: The deployment's rendered switch (`harness.render`), as `scripts.seed_internal` reads it.
RESOLUTION_SWITCH = "OSPREY_POST_INGEST_RESOLUTION"
#: PaySim's source page. A test holds this to the pack's own `source_page`.
PAYSIM_SOURCE_PAGE = "https://www.kaggle.com/datasets/ealaxi/paysim1"
PAYSIM_FOLDER = "PaySIM_Dataset"

# --- Enron (ADR-114 Amendment 23): real data, downloaded by the person and accepted in words ---
ENRON_SOURCE_PAGE = "https://www.cs.cmu.edu/~enron/"
ENRON_FILE = "enron_mail_20150507.tar.gz"
ENRON_FOLDER = "Enron_Mails"
#: The May 7, 2015 file's SHA-256 — `scripts.demo_packs.ENRON_SHA256`; a test holds the two equal.
ENRON_SHA256 = "b3da1b3fe0369ec3140bb4fbce94702c33b7da810ec15d718b3fadf5cd748ca7"
#: The packs that are real people's data: never added by an install (ADR-114 Amendment 23).
REAL_DATA_PACKS = ("enron",)
#: The acceptance record's name and words — `scripts.real_data_acknowledgement`'s own; a test holds
#: the two equal (the command does not import the checkout's scripts).
ENRON_RECORD = "ACCEPTED_REAL_DATA.json"
ENRON_STATEMENT = (
    "This corpus is real people's email: their names, addresses and private correspondence. No "
    "licence is stated for it; Carnegie Mellon University distributes it as a resource for "
    "researchers and asks that you be sensitive to the privacy of the people involved. Your "
    "organisation needs its own lawful basis to process this personal data. It stays on this "
    "machine and is never shared by OspreyFlow."
)


def demo_data_root(product: Path, env: Mapping[str, str], *, home: Path | None = None) -> Path:
    """Where demo data lives: `OSPREYFLOW_DEMO_DATA`, else an `OspreyFlow_Data` beside the product
    (the developer layout, as `scripts.seed_internal` has it), else `~/OspreyFlow/demo-data`."""
    chosen = env.get("OSPREYFLOW_DEMO_DATA")
    if chosen:
        return Path(chosen).expanduser()
    sibling = product.parent / "OspreyFlow_Data"
    if sibling.is_dir():
        return sibling
    return (home or Path.home()) / "OspreyFlow" / "demo-data"


def pack_ids(product: Path, capture: Capture) -> tuple[str, ...]:
    """The packs this checkout offers, asked of the checkout itself."""
    code, output = capture([*python_for(product), "-m", "scripts.demo_packs", "--ids"], cwd=product)
    if code != 0:
        raise CommandRefused(
            "This checkout could not list its demo packs (scripts.demo_packs --ids failed). "
            "Is the checkout complete, and has `uv sync` been run in it?"
        )
    return tuple(line.strip() for line in output.splitlines() if line.strip())


def list_packs(product: Path, run: Runner) -> int:
    return run([*python_for(product), "-m", "scripts.demo_packs"], cwd=product)


def _place(file: Path, root: Path) -> Path:
    destination = root / PAYSIM_FOLDER / file.name
    if destination.exists() and destination.resolve() == file.resolve():
        return destination
    if destination.is_file() and filecmp.cmp(file, destination, shallow=False):
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(file, destination)
    return destination


def _unpack_enron(file: Path, root: Path) -> None:
    """The tarball's `maildir/` becomes `<root>/Enron_Mails/`, unpacked beside it first so a failed
    unpack leaves nothing half-there. Members are extracted with the `data` filter: nothing outside
    the folder, no links out, no device files."""
    staging = root / f".{ENRON_FOLDER}.unpacking"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    with tarfile.open(file, "r:gz") as tar:
        tar.extractall(staging, filter="data")
    mail = staging / "maildir"
    if not mail.is_dir():
        shutil.rmtree(staging)
        raise CommandRefused(f"{file.name} holds no maildir/ folder; it is not the Enron corpus.")
    mail.rename(root / ENRON_FOLDER)
    shutil.rmtree(staging)


def _record_acceptance(folder: Path, source_file: str) -> None:
    (folder / ENRON_RECORD).write_text(
        json.dumps(
            {
                "dataset": "enron",
                "accepted": True,
                "accepted_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "source_file": source_file,
                "sha256": ENRON_SHA256 if source_file else "",
                "statement": ENRON_STATEMENT,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _enron(
    product: Path,
    run: Runner,
    root: Path,
    file: Path | None,
    ask: Callable[[str, str], str] | None,
    accept_real_data: bool,
) -> bool:
    """Checks, explains, asks, unpacks and records; `False` when the person declined."""
    folder = root / ENRON_FOLDER
    if file is None and not folder.is_dir():
        raise CommandRefused(
            f"The Enron corpus is a download you make yourself: get {ENRON_FILE} from "
            f"{ENRON_SOURCE_PAGE} and pass it with --file PATH. It is real people's email; "
            "OspreyFlow never carries it."
        )
    if file is not None:
        file = file.expanduser()
        verify = [*python_for(product), "-m", "scripts.demo_packs", "verify", "enron", str(file)]
        code = run(verify, cwd=product)
        if code != 0:
            raise StepFailed("check the Enron file", code)
    print()
    print("The Enron email corpus is REAL DATA.")
    print(ENRON_STATEMENT)
    print(f"Its source and terms: {ENRON_SOURCE_PAGE}")
    if accept_real_data:
        print("You accepted with --accept-real-data.")
    else:
        answer = ask("Type yes to accept this and add it", "no") if ask else "no"
        if answer.strip().lower() != "yes":
            print("Nothing was added.")
            return False
    if file is not None and not folder.is_dir():
        print(f"Unpacking {file.name} into {folder} …")
        _unpack_enron(file, root)
    _record_acceptance(folder, file.name if file is not None else "")
    return True


def add_pack(
    product: Path,
    run: Runner,
    env: Mapping[str, str],
    pack: str,
    file: Path | None = None,
    *,
    ask: Callable[[str, str], str] | None = None,
    accept_real_data: bool = False,
    case_domains: tuple[str, ...] | None = None,
    deployment_env: Mapping[str, str] | None = None,
    deployment: Path | None = None,
    settings: Path | None = None,
    apply_command: str = "ospreyflow apply",
) -> None:
    """Seed `pack` into its own case. `case_domains` (a starter's, ADR-138) are the domain packs the
    case is set to while nobody has chosen; `deployment_env` points the seed at a deployment kept
    by name (`OSPREYFLOW_DEPLOYMENT_DIR`). `deployment` is that deployment's folder, `settings` the
    `osprey.yaml` that `apply_command` applies. Raises `CommandRefused` before anything starts when
    the request cannot be honoured, and `StepFailed` when a step it ran exits non-zero."""
    if pack not in PACK_KEYS:
        raise CommandRefused(
            f"There is no demo pack called '{pack}'. The packs are: {', '.join(PACK_KEYS)}."
        )
    if pack in RESOLUTION_OFF_PACKS and deployment is not None:
        _require_resolution_off(deployment, settings, apply_command)
    python = python_for(product)
    root = demo_data_root(product, env)
    if pack == "paysim":
        if file is None:
            raise CommandRefused(
                "PaySim is a download, not generated: download the file from "
                f"{PAYSIM_SOURCE_PAGE} and give it with --file PATH."
            )
        file = file.expanduser()
        verify = [*python, "-m", "scripts.demo_packs", "verify", "paysim", str(file)]
        code = run(verify, cwd=product)
        if code != 0:
            raise StepFailed("check the PaySim file", code)
        _place(file, root)
    if pack == "enron" and not _enron(product, run, root, file, ask, accept_real_data):
        return
    domains = ["--case-domains", ",".join(case_domains)] if case_domains is not None else []
    code = run(
        [*python, "-m", "scripts.seed_internal", PACK_KEYS[pack], "--stop-api", *domains],
        env={"OSPREYFLOW_DEMO_DATA": str(root), **(deployment_env or {})},
        cwd=product,
    )
    if code != 0:
        raise StepFailed(f"load the {pack} demo pack", code)


def resolution_switch(deployment: Path) -> str | None:
    """The deployment's rendered `OSPREY_POST_INGEST_RESOLUTION`, as its Conduit reads it: `on` when
    the line is missing (a deployment rendered before the switch existed), None when nothing is
    installed there."""
    env = deployment / "deployment.env"
    if not env.is_file():
        return None
    value = "on"
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{RESOLUTION_SWITCH}="):
            value = line.partition("=")[2].strip() or "on"
    return value


def _require_resolution_off(deployment: Path, settings: Path | None, apply_command: str) -> None:
    """ADR-127 Amendment 46: the Prison Intelligence pack refuses, in words and before anything
    starts, while post-ingest resolution is on. Where nothing is installed, the seed says so."""
    value = resolution_switch(deployment)
    if value is None or value == "off":
        return
    where = f"in {settings}" if settings is not None else "in the deployment's osprey.yaml"
    raise CommandRefused(
        "The Prison Intelligence pack needs post-ingest resolution off, and this deployment has it "
        f"on ({RESOLUTION_SWITCH} in {deployment / 'deployment.env'}). With it on, a live load in "
        'the demonstration adds automatic "same as" links, and every rehearsal reset then refuses. '
        f"Set post_ingest_resolution: false under components: {where}, run {apply_command}, then "
        "add the pack again. Resolution is the whole deployment's setting: no case or dataset can "
        "turn it off on its own. Nothing was added."
    )


# --- A public dataset of the administrator's choosing (ADR-138 decision 3) --------------------

#: The words a public dataset holding real personal data is accepted with: Enron's path, for any
#: dataset whose manifest says so (rule 9; ADR-035 §C3).
PUBLIC_REAL_DATA_STATEMENT = (
    "Its manifest says this dataset holds REAL personal data: real people's names and details. "
    "Your organisation needs its own lawful basis to process it. It stays on this machine and is "
    "never shared by OspreyFlow, and it never belongs in a repository or a test run."
)


def add_public(
    product: Path,
    run: Runner,
    env: Mapping[str, str],
    file: Path | None,
    manifest: str | None,
    *,
    capture: Capture,
    ask: Callable[[str, str], str] | None = None,
    accept_real_data: bool = False,
    deployment_env: Mapping[str, str] | None = None,
) -> bool:
    """`ospreyflow demo add public --file <path> --manifest <dataset.yaml>`: the file is checked
    against its manifest's checksum, by the checkout's own `scripts.public_dataset`, before anything
    else happens; real personal data is accepted in words (or `--accept-real-data`); then the file,
    its manifest and its recipe are placed in the demo data folder and loaded into a case of their
    own. `False` when the person declined."""
    if file is None or not manifest:
        raise CommandRefused(
            "A public dataset is your own download, named by its manifest: give both, as "
            "ospreyflow demo add public --file <the downloaded file> --manifest <dataset.yaml, or "
            "a catalogue id such as vast-2012-mc2>. python -m scripts.public_dataset --list names "
            "the catalogue."
        )
    file = file.expanduser()
    python = python_for(product)
    code, said = capture(
        [*python, "-m", "scripts.public_dataset", "verify", "--manifest", manifest, "--file",
         str(file), "--json"],
        cwd=product,
    )  # fmt: skip
    if code != 0:
        raise CommandRefused(said.strip() or "The dataset's file does not match its manifest.")
    try:
        summary = json.loads(said.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise CommandRefused(
            "The checkout's dataset check answered in an unexpected form."
        ) from None
    print(f"{file.name} is the file {summary['name']}'s manifest names (SHA-256 checked).")
    print(f"Source: {summary['source_page']}")
    print(f"Terms: {summary['licence']}")
    if summary.get("real_personal_data"):
        print()
        print(f"{summary['name']} is REAL DATA.")
        print(PUBLIC_REAL_DATA_STATEMENT)
        if accept_real_data:
            print("You accepted with --accept-real-data.")
        else:
            answer = ask("Type yes to accept this and add it", "no") if ask else "no"
            if answer.strip().lower() != "yes":
                print("Nothing was added.")
                return False
    root = demo_data_root(product, env)
    stage = [*python, "-m", "scripts.public_dataset", "stage", "--manifest", manifest,
             "--file", str(file), "--into", str(root)]  # fmt: skip
    if summary.get("real_personal_data"):
        stage.append("--accepted")
    code = run(stage, cwd=product)
    if code != 0:
        raise StepFailed("place the dataset in the demo data folder", code)
    code = run(
        [*python, "-m", "scripts.seed_internal", "public", "--stop-api", "--public-id",
         str(summary["id"])],
        env={"OSPREYFLOW_DEMO_DATA": str(root), **(deployment_env or {})},
        cwd=product,
    )  # fmt: skip
    if code != 0:
        raise StepFailed(f"load {summary['name']}", code)
    return True
